#!/usr/bin/env python3
"""Take a picture of every slide of a LabDeck deck, and of its lab-wall view, with headless Chrome.

Usage:
  python3 snap.py SITE_ROOT DECK_FOLDER [--out DIR] [--ref DIR] [--only deck|wall] [--slides 1,4-6]
                  [--format jpg|png] [--tabs 4] [--top 8] [--pdf]

  SITE_ROOT    the folder that gets published (it holds labdeck/ and the deck folder)
  DECK_FOLDER  the deck's folder inside it, for example my-talk
  --out DIR    where pictures go (default: SITE_ROOT/../labdeck-snaps/DECK_FOLDER)
  --ref DIR    pictures of the original slides (slide-01.png or .jpg ...): every slide gets a difference
               score, and worst.jpg shows the most different ones next to the original. Look there first.
  --only       only the deck or only the wall
  --slides     which slides (1-based), default all
  --format     jpg (default, about 3x faster) or png
  --tabs       Chrome windows working at the same time (default 4)
  --top        how many slides go into worst.jpg (default 8)
  --pdf        also print the whole deck to DIR/deck.pdf

Writes deck-01.jpg ..., wall-01.jpg ..., worst.jpg (with --ref), walls-1.jpg ... (the wall views
stacked, 13 per sheet) and index.html (original | web | wall for every slide, most different first).
Pictures show every build step, and demo answers on interactive slides.

How it stays fast: one Chrome stays open, with its GPU on (software drawing makes a window's first
picture of a text-heavy deck take 10-30 s); each window loads the deck once and steps through its
share of the slides in the page (no reloads); each picture waits until fonts and pictures are
ready, with transitions switched off, so nothing is caught half faded. On Apple silicon Chrome
is started as arm64 even from an Intel (Rosetta) Python, which is otherwise 3-5x slower.
Needs only Python 3.8+ (standard library) and Google Chrome (or Chromium / Edge / Brave).
"""
import argparse, base64, functools, html, http.server, json, os, re, shutil, socket, struct, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request


def find_chrome():
    env = os.environ.get('CHROME')
    if env and os.path.exists(env):
        return env
    for c in ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
              '/Applications/Chromium.app/Contents/MacOS/Chromium',
              '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
              '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
              r'C:\Program Files\Google\Chrome\Application\chrome.exe',
              r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe']:
        if os.path.exists(c):
            return c
    for n in ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'chrome', 'msedge']:
        p = shutil.which(n)
        if p:
            return p
    sys.exit('Could not find Chrome. Install Google Chrome, or set CHROME=/path/to/chrome.')


def native_prefix():
    """On Apple silicon an Intel (Rosetta) Python would start the Intel build of Chrome: force arm64."""
    if sys.platform == 'darwin':
        try:
            r = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], capture_output=True, text=True)
            if r.stdout.strip() == '1' and shutil.which('arch'):
                return ['arch', '-arm64']
        except OSError:
            pass
    return []


def parse_range(spec, n):
    if not spec:
        return list(range(1, n + 1))
    out = []
    for part in spec.split(','):
        a, _, b = part.partition('-')
        out += list(range(int(a), int(b or a) + 1))
    return [i for i in out if 1 <= i <= n]


def chunks(xs, k):
    """split xs into k contiguous runs: each window walks one run without reloading"""
    k = max(1, min(k, len(xs)))
    size, extra = divmod(len(xs), k)
    out, at = [], 0
    for j in range(k):
        m = size + (1 if j < extra else 0)
        out.append(xs[at:at + m])
        at += m
    return [c for c in out if c]


# ---------------- a small WebSocket client (standard library only) ----------------
class WS:
    def __init__(self, url, timeout=30):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(('GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                           'Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n' % (u.path, u.hostname, u.port, key)).encode())
        self.buf = bytearray()
        while b'\r\n\r\n' not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError('DevTools closed the connection')
            self.buf += chunk
        end = self.buf.index(b'\r\n\r\n')
        status = bytes(self.buf[:end]).split(b'\r\n')[0]
        del self.buf[:end + 4]
        if b' 101' not in status:
            raise ConnectionError('DevTools refused the WebSocket: %r' % status)

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise ConnectionError('DevTools closed the connection')
            self.buf += chunk
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def _frame(self, op, data):
        head = bytes([0x80 | op])
        n = len(data)
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack('>H', n)
        else:
            head += bytes([0x80 | 127]) + struct.pack('>Q', n)
        mask = os.urandom(4)
        if n:
            k = (mask * (n // 4 + 1))[:n]
            data = (int.from_bytes(data, 'big') ^ int.from_bytes(k, 'big')).to_bytes(n, 'big')
        self.sock.sendall(head + mask + data)

    def send(self, text):
        self._frame(0x1, text.encode())

    def recv(self):
        parts = []
        while True:
            b1, b2 = self._read(2)
            op, n = b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack('>H', self._read(2))[0]
            elif n == 127:
                n = struct.unpack('>Q', self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if op == 0x8:
                raise ConnectionError('DevTools closed the connection')
            if op == 0x9:
                self._frame(0xA, data)
                continue
            if op == 0xA:
                continue
            parts.append(data)
            if b1 & 0x80:
                return b''.join(parts).decode('utf-8')

    def settimeout(self, t):
        self.sock.settimeout(t)

    def close(self):
        try:
            self._frame(0x8, b'')
            self.sock.close()
        except OSError:
            pass


# ---------------- one Chrome window driven over the DevTools protocol ----------------
READY_JS = r'''(async () => {
  const t0 = performance.now(), budget = %d;
  const left = () => Math.max(0, budget - (performance.now() - t0));
  const within = p => Promise.race([p, new Promise(r => setTimeout(r, left()))]);
  if (document.readyState !== 'complete') await within(new Promise(r => addEventListener('load', r, { once: true })));
  await within(document.fonts ? document.fonts.ready : Promise.resolve());
  if (!document.getElementById('snap-still')) {
    const st = document.createElement('style'); st.id = 'snap-still';
    st.textContent = '*,*::before,*::after{transition:none!important;animation:none!important}';
    document.head.appendChild(st);
  }
  await new Promise(r => setTimeout(r, 30));      // not requestAnimationFrame: headless runs few frames
  const imgs = [...document.images].filter(i => i.getBoundingClientRect().width > 0);
  await within(Promise.all(imgs.map(i => i.decode().catch(() => {}))));
  await within(document.fonts ? document.fonts.ready : Promise.resolve());
  await new Promise(r => setTimeout(r, 120));
  return { ms: Math.round(performance.now() - t0), broken: imgs.filter(i => !i.naturalWidth).map(i => i.getAttribute('src')) };
})()'''

# step the deck in the page: go to slide i and show all of its builds (as ?static does)
DECK_GO = ("(window.LabDeck && LabDeck.go) ? (LabDeck.go(%d), document.querySelectorAll('section.slide')[%d]"
           ".querySelectorAll('[data-step]').forEach(e => e.classList.add('ld-in')), true) : false")
WALL_NEXT = "dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight' })), true"


class Window:
    def __init__(self, port):
        # its own window, not a background tab: headless Chrome hardly draws background tabs,
        # so their screenshots stall for many seconds
        ver = json.load(urllib.request.urlopen('http://127.0.0.1:%d/json/version' % port, timeout=10))
        b = WS(ver['webSocketDebuggerUrl'])
        b.send(json.dumps({'id': 1, 'method': 'Target.createTarget', 'params': {'url': 'about:blank', 'newWindow': True}}))
        while True:
            msg = json.loads(b.recv())
            if msg.get('id') == 1:
                break
        b.close()
        if 'error' in msg:
            raise RuntimeError(msg['error'])
        self.port, self.target = port, msg['result']['targetId']
        self.ws = WS('ws://127.0.0.1:%d/devtools/page/%s' % (port, self.target))
        self.n, self.size, self.events = 0, None, []
        self.call('Page.enable')
        self.call('Emulation.setFocusEmulationEnabled', enabled=True)
        self.call('Emulation.setEmulatedMedia', features=[{'name': 'prefers-reduced-motion', 'value': 'reduce'}])

    def call(self, method, **params):
        self.n += 1
        my = self.n
        self.ws.send(json.dumps({'id': my, 'method': method, 'params': params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get('id') == my:
                if 'error' in msg:
                    raise RuntimeError('%s: %s' % (method, msg['error']))
                return msg.get('result', {})
            if 'method' in msg:
                self.events.append(msg['method'])

    def wait_event(self, name, timeout=20):
        if name in self.events:
            return True
        end = time.time() + timeout
        try:
            while time.time() < end:
                self.ws.settimeout(max(0.1, end - time.time()))
                if json.loads(self.ws.recv()).get('method') == name:
                    return True
        except socket.timeout:
            return False
        finally:
            self.ws.settimeout(30)
        return False

    def resize(self, size):
        if size != self.size:
            self.call('Emulation.setDeviceMetricsOverride', width=size[0], height=size[1], deviceScaleFactor=1, mobile=False)
            self.size = size

    def open(self, url, size):
        self.resize(size)
        self.events = []
        self.call('Page.navigate', url=url)
        self.wait_event('Page.loadEventFired')        # never run the ready check in the page being left

    def js(self, expr, wait=False):
        r = self.call('Runtime.evaluate', expression=expr, awaitPromise=wait, returnByValue=True)
        return r.get('result', {}).get('value')

    def capture(self, file, fmt):
        enc = {'format': 'jpeg', 'quality': 92} if fmt == 'jpg' else {'format': 'png'}
        self.ws.settimeout(90)                          # a window's first picture can take a while
        try:
            shot = self.call('Page.captureScreenshot', clip={'x': 0, 'y': 0, 'width': self.size[0], 'height': self.size[1], 'scale': 1}, **enc)
        finally:
            self.ws.settimeout(30)
        with open(file, 'wb') as f:
            f.write(base64.b64decode(shot['data']))

    def close(self):
        self.ws.close()
        try:
            urllib.request.urlopen('http://127.0.0.1:%d/json/close/%s' % (self.port, self.target), timeout=2)
        except OSError:
            pass


# difference between two pictures, worked out in the page (no Python image libraries needed):
# small greyscale, slightly blurred so that tiny shifts do not count; 0 = the same
DIFF_JS = r'''(async (pairs) => {
  const load = src => new Promise(r => { const i = new Image(); i.onload = () => r(i); i.onerror = () => r(null); i.src = src; });
  const W = 480, H = 270, c = document.createElement('canvas'); c.width = W; c.height = H;
  const x = c.getContext('2d', { willReadFrequently: true });
  const grey = img => {
    x.filter = 'none'; x.fillStyle = '#fff'; x.fillRect(0, 0, W, H);
    x.filter = 'blur(1.2px)'; x.drawImage(img, 0, 0, W, H);
    const d = x.getImageData(0, 0, W, H).data, g = new Float32Array(W * H);
    for (let i = 0, j = 0; i < d.length; i += 4, j++) g[j] = .299 * d[i] + .587 * d[i + 1] + .114 * d[i + 2];
    return g;
  };
  const out = [];
  for (const [n, a, b] of pairs) {
    const A = await load(a), B = await load(b);
    if (!A || !B) continue;
    const ga = grey(A), gb = grey(B);
    let s = 0; for (let i = 0; i < ga.length; i++) s += Math.abs(ga[i] - gb[i]);
    out.push([n, s / ga.length]);
  }
  return out;
})(%s)'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('root'); ap.add_argument('deck')
    ap.add_argument('--out'); ap.add_argument('--ref'); ap.add_argument('--only', choices=['deck', 'wall'])
    ap.add_argument('--slides'); ap.add_argument('--pdf', action='store_true')
    ap.add_argument('--format', choices=['jpg', 'png'], default='jpg')
    ap.add_argument('--tabs', type=int, default=4); ap.add_argument('--top', type=int, default=8)
    a = ap.parse_args()
    t0 = time.time()
    root = os.path.abspath(a.root)
    page = os.path.join(root, a.deck, 'index.html')
    if not os.path.exists(page):
        sys.exit('No deck at %s' % page)
    src = open(page, encoding='utf-8').read()
    n = len(re.findall(r'<section\b[^>]*\bclass\s*=\s*["\'][^"\']*\bslide\b', src))
    m = re.search(r'width\s*:\s*(\d+)\s*,\s*height\s*:\s*(\d+)', src)
    w, h = (int(m.group(1)), int(m.group(2))) if m else (1920, 1080)
    out = os.path.abspath(a.out or os.path.join(root, '..', 'labdeck-snaps', a.deck))
    ref = os.path.abspath(a.ref) if a.ref else None
    os.makedirs(out, exist_ok=True)
    ext = a.format

    def ref_name(i):
        """the original picture of slide i (slide-01.png from render_slides.py, or .jpg), or None"""
        for e in ('png', 'jpg', 'jpeg'):
            if ref and os.path.exists(os.path.join(ref, 'slide-%02d.%s' % (i, e))):
                return 'slide-%02d.%s' % (i, e)
        return None
    slides = parse_range(a.slides, n)
    kinds = [k for k in ('deck', 'wall') if a.only in (None, k)]
    for k in kinds:
        for i in slides:
            for e in ('jpg', 'png'):
                f = os.path.join(out, '%s-%02d.%s' % (k, i, e))
                if os.path.exists(f):
                    os.remove(f)

    # one local server: the site, plus the original pictures and the output folder for the review pages
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def translate_path(self, path):
            p = urllib.parse.unquote(urllib.parse.urlparse(path).path)
            for prefix, folder in (('/__ref/', ref), ('/__out/', out)):
                if folder and p.startswith(prefix):
                    return os.path.join(folder, os.path.basename(p))
            return super().translate_path(path)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=root))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    origin = 'http://127.0.0.1:%d' % srv.server_address[1]
    base = '%s/%s/' % (origin, urllib.parse.quote(a.deck))

    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    prof = tempfile.mkdtemp(prefix='labdeck-chrome-')
    chrome = subprocess.Popen(native_prefix() + [find_chrome(), '--headless=new', '--hide-scrollbars',
                              '--no-first-run', '--no-default-browser-check', '--mute-audio',
                              '--remote-debugging-port=%d' % port, '--remote-allow-origins=*',
                              '--user-data-dir=%s' % prof, 'about:blank'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    problems, lock = [], threading.Lock()
    ranked = []
    try:
        for _ in range(300):
            try:
                urllib.request.urlopen('http://127.0.0.1:%d/json/version' % port, timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            sys.exit('Chrome did not start. Is it installed? Set CHROME=/path/to/chrome.')

        def url_of(kind, i):
            return base + ('?s=%d&static&demo' % i if kind == 'deck' else '?wall&band&demo&s=%d' % i)

        def run(kind, run_slides):
            size = (w, h) if kind == 'deck' else (3840, 360)
            win, prev = Window(port), None
            for i in run_slides:
                file = os.path.join(out, '%s-%02d.%s' % (kind, i, ext))
                for attempt in (1, 2):
                    try:
                        if prev is None or attempt == 2 or (kind == 'wall' and i != prev + 1):
                            win.open(url_of(kind, i), size)
                            if kind == 'deck':
                                win.js(DECK_GO % (i - 1, i - 1))
                        elif kind == 'deck':
                            if not win.js(DECK_GO % (i - 1, i - 1)):
                                win.open(url_of(kind, i), size)
                        else:
                            win.js(WALL_NEXT)
                        info = win.js(READY_JS % 8000, wait=True) or {}
                        win.capture(file, ext)
                        if info.get('broken'):
                            with lock:
                                problems.append('%s: missing pictures %s' % (os.path.basename(file), info['broken']))
                        prev = i
                        break
                    except (OSError, ConnectionError, RuntimeError, ValueError) as e:
                        win.close()             # a stuck window: replace it and load this slide once more
                        win, prev = Window(port), None
                        if attempt == 2:
                            with lock:
                                problems.append('%s: %s' % (os.path.basename(file), e))
            win.close()

        per = max(1, a.tabs // len(kinds))
        threads = [threading.Thread(target=run, args=(k, c)) for k in kinds for c in chunks(slides, per)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        print('%d pictures in %.0fs' % (len(slides) * len(kinds), time.time() - t0))

        win = Window(port)
        if a.pdf:
            win.open(base + '?print', (w, h))
            win.js(READY_JS % 15000, wait=True)
            pdf = win.call('Page.printToPDF', printBackground=True, preferCSSPageSize=True)
            with open(os.path.join(out, 'deck.pdf'), 'wb') as f:
                f.write(base64.b64decode(pdf['data']))

        # rank the slides by how different they look from the original
        if ref and 'deck' in kinds:
            pairs = [[i, '/__ref/' + ref_name(i), '/__out/deck-%02d.%s' % (i, ext)] for i in slides
                     if ref_name(i) and os.path.exists(os.path.join(out, 'deck-%02d.%s' % (i, ext)))]
            if pairs:
                win.open(origin + '/__out/', (800, 600))
                ranked = sorted(((sc, i) for i, sc in (win.js(DIFF_JS % json.dumps(pairs), wait=True) or [])), reverse=True)
                json.dump([{'slide': i, 'diff': round(sc, 2)} for sc, i in ranked], open(os.path.join(out, 'diff.json'), 'w'), indent=1)

        # review sheets, drawn by Chrome: the most different slides next to the original, and the wall views
        def sheet(name, body, size):
            open(os.path.join(out, name + '.html'), 'w', encoding='utf-8').write(
                '<!doctype html><meta charset="utf-8"><style>body{margin:0;background:#c00}img{display:block}'
                '.row{display:flex;gap:10px;margin-bottom:10px}</style>' + body)
            win.open(origin + '/__out/' + name + '.html', size)
            win.js(READY_JS % 15000, wait=True)
            win.capture(os.path.join(out, name + '.jpg'), 'jpg')
            os.remove(os.path.join(out, name + '.html'))
        top = [i for _, i in ranked[:a.top]]
        if top:
            sheet('worst', ''.join('<div class="row"><img src="/__ref/%s" width=960 height=540>'
                                   '<img src="/__out/deck-%02d.%s" width=960 height=540></div>' % (ref_name(i), i, ext) for i in top),
                  (1930, 550 * len(top)))
        if 'wall' in kinds:
            for g in range(0, len(slides), 13):
                part = slides[g:g + 13]
                sheet('walls-%d' % (g // 13 + 1), ''.join('<div class="row"><img src="/__out/wall-%02d.%s" width=1920 height=180></div>'
                                                         % (i, ext) for i in part), (1920, 190 * len(part)))
        win.close()
    finally:
        chrome.terminate()
        try:
            chrome.wait(5)
        except subprocess.TimeoutExpired:
            chrome.kill()
        shutil.rmtree(prof, ignore_errors=True)
        srv.shutdown()

    # index.html: original | web | wall for every slide, the most different first
    score = {i: sc for sc, i in ranked}
    order = [i for _, i in ranked] + [i for i in slides if i not in score]
    rows = []
    for i in order:
        cells = []
        r = os.path.join(ref, ref_name(i)) if ref_name(i) else None
        if r:
            cells.append('<figure><img src="file://%s"><figcaption>original %d</figcaption></figure>' % (html.escape(r), i))
        if 'deck' in kinds:
            cap = 'web %d' % i + (' · difference %.1f' % score[i] if i in score else '')
            cells.append('<figure><img src="deck-%02d.%s"><figcaption>%s</figcaption></figure>' % (i, ext, cap))
        wall = ('<figure class="wall"><img src="wall-%02d.%s"><figcaption>lab wall %d</figcaption></figure>' % (i, ext, i)) if 'wall' in kinds else ''
        rows.append('<section><div class="pair">%s</div>%s</section>' % (''.join(cells), wall))
    open(os.path.join(out, 'index.html'), 'w', encoding='utf-8').write(
        '<!doctype html><meta charset="utf-8"><title>Deck check</title><style>body{background:#222;color:#ddd;font:14px system-ui;margin:20px}'
        'section{margin:0 0 40px}.pair{display:flex;gap:16px}.pair figure{flex:1}figure{margin:0}img{width:100%;display:block;background:#000}'
        '.wall{margin-top:10px}figcaption{padding:4px 0}</style>' + ''.join(rows))

    print('%d slides found, pictures in %s (%.0fs in all)' % (n, out, time.time() - t0))
    if ranked:
        print('Most different from the original (slide: score): ' + ', '.join('%d: %.1f' % (i, sc) for sc, i in ranked[:a.top]))
        print('Look at %s first.' % os.path.join(out, 'worst.jpg'))
    if 'wall' in kinds:
        print('Wall views: %s' % ', '.join(sorted(f for f in os.listdir(out) if f.startswith('walls-') and f.endswith('.jpg'))))
    print('Open %s for every slide.' % os.path.join(out, 'index.html'))
    for p in problems:
        print('PROBLEM', p)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
