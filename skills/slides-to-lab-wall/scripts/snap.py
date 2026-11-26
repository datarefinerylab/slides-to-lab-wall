#!/usr/bin/env python3
"""Take a picture of every slide of a LabDeck deck, and of its lab-wall view, with headless Chrome.

Usage:
  python3 snap.py SITE_ROOT DECK_FOLDER [--out DIR] [--ref DIR] [--only deck|wall] [--slides 1,4-6] [--pdf]

  SITE_ROOT    the folder that gets published (it holds labdeck/ and the deck folder)
  DECK_FOLDER  the deck's folder inside it, for example my-talk
  --out DIR    where pictures go (default: SITE_ROOT/../labdeck-snaps/DECK_FOLDER)
  --ref DIR    pictures of the original slides (slide-01.png ...), shown next to the web version
  --only       only the deck or only the wall
  --slides     which slides (1-based), default all
  --pdf        also print the whole deck to DIR/deck.pdf

Writes deck-01.png ..., wall-01.png ... and index.html, a side-by-side sheet to look at.
Pictures show every build step, and demo answers on interactive slides.
Needs only Python 3 and Google Chrome (or Chromium / Edge / Brave).
"""
import argparse, concurrent.futures as cf, functools, html, http.server, os, re, shutil, subprocess, sys, tempfile, threading, glob

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

def parse_range(spec, n):
    if not spec:
        return list(range(1, n + 1))
    out = []
    for part in spec.split(','):
        a, _, b = part.partition('-')
        out += list(range(int(a), int(b or a) + 1))
    return [i for i in out if 1 <= i <= n]

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('root'); ap.add_argument('deck')
    ap.add_argument('--out'); ap.add_argument('--ref'); ap.add_argument('--only', choices=['deck', 'wall'])
    ap.add_argument('--slides'); ap.add_argument('--pdf', action='store_true')
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    page = os.path.join(root, a.deck, 'index.html')
    if not os.path.exists(page):
        sys.exit(f'No deck at {page}')
    src = open(page, encoding='utf-8').read()
    n = len(re.findall(r'<section\b[^>]*\bclass\s*=\s*["\'][^"\']*\bslide\b', src))
    m = re.search(r'width\s*:\s*(\d+)\s*,\s*height\s*:\s*(\d+)', src)
    w, h = (int(m.group(1)), int(m.group(2))) if m else (1920, 1080)
    out = os.path.abspath(a.out or os.path.join(root, '..', 'labdeck-snaps', a.deck))
    os.makedirs(out, exist_ok=True)
    chrome = find_chrome()

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Quiet, directory=root)
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_address[1]}/{a.deck}/'

    def shoot(url, size, file):
        prof = tempfile.mkdtemp(prefix='labdeck-chrome-')
        try:
            subprocess.run([chrome, '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run',
                            '--no-default-browser-check', '--force-device-scale-factor=1', f'--user-data-dir={prof}',
                            f'--window-size={size[0]},{size[1]}', '--virtual-time-budget=5000',
                            f'--screenshot={file}', url], capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            print(f'Timed out: {url}', file=sys.stderr)
        finally:
            shutil.rmtree(prof, ignore_errors=True)
        return os.path.exists(file)

    slides = parse_range(a.slides, n)
    jobs = []
    for i in slides:
        if a.only != 'wall':
            jobs.append((f'{base}?s={i}&static&demo', (w, h), os.path.join(out, f'deck-{i:02d}.png')))
        if a.only != 'deck':
            jobs.append((f'{base}?wall&band&demo&s={i}', (3840, 360), os.path.join(out, f'wall-{i:02d}.png')))
    for _, _, f in jobs:
        if os.path.exists(f):
            os.remove(f)
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        ok = list(ex.map(lambda j: shoot(*j), jobs))
    if a.pdf:
        prof = tempfile.mkdtemp(prefix='labdeck-chrome-')
        subprocess.run([chrome, '--headless=new', '--disable-gpu', '--no-pdf-header-footer', f'--user-data-dir={prof}',
                        '--virtual-time-budget=5000', f'--print-to-pdf={os.path.join(out, "deck.pdf")}', f'{base}?print'],
                       capture_output=True, timeout=180)
        shutil.rmtree(prof, ignore_errors=True)
    srv.shutdown()

    refs = sorted(glob.glob(os.path.join(a.ref, '*.png')) + glob.glob(os.path.join(a.ref, '*.jpg'))) if a.ref else []
    def natural(p):
        return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', os.path.basename(p))]
    refs.sort(key=natural)
    rows = []
    for i in slides:
        cells = []
        if refs and i <= len(refs):
            cells.append(f'<figure><img src="file://{html.escape(refs[i - 1])}"><figcaption>original {i}</figcaption></figure>')
        if a.only != 'wall':
            cells.append(f'<figure><img src="deck-{i:02d}.png"><figcaption>web {i}</figcaption></figure>')
        wall = f'<figure class="wall"><img src="wall-{i:02d}.png"><figcaption>lab wall {i}</figcaption></figure>' if a.only != 'deck' else ''
        rows.append(f'<section><div class="pair">{"".join(cells)}</div>{wall}</section>')
    open(os.path.join(out, 'index.html'), 'w', encoding='utf-8').write(
        '<!doctype html><meta charset="utf-8"><title>Deck check</title><style>body{background:#222;color:#ddd;font:14px system-ui;margin:20px}'
        'section{margin:0 0 40px}.pair{display:flex;gap:16px}.pair figure{flex:1}figure{margin:0}img{width:100%;display:block;background:#000}'
        '.wall{margin-top:10px}figcaption{padding:4px 0}</style>' + ''.join(rows))
    bad = sum(1 for x in ok if not x)
    print(f'{n} slides found, {len(jobs) - bad} pictures written to {out}' + (f', {bad} failed' if bad else ''))
    print(f'Open {os.path.join(out, "index.html")} to compare.')

if __name__ == '__main__':
    main()
