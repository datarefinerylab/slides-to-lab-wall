#!/usr/bin/env python3
"""Set up and publish the GitHub repository that hosts the decks (GitHub Pages).

  python3 deckrepo.py setup   --repo OWNER/NAME --slug my-talk --title "My Talk" [--clone DIR] [--private]
  python3 deckrepo.py publish --clone DIR [--slug my-talk] [--message "..."] [--no-wait]
  python3 deckrepo.py status  --clone DIR

setup    clones the repository (creating it if it does not exist), copies the LabDeck engine
         into labdeck/, makes the talk list page (index.html) if missing, and starts
         SLUG/index.html from the template (unless it already exists). Prints the folder to work in.
publish  refreshes the engine and the talk list, commits, pushes, turns GitHub Pages on,
         waits until the site is live and prints the deck link and the wall setup.
status   prints the Pages address and lists the talks.

Layout of the repository:
  index.html        talk list; also the lab wall's waiting page
  labdeck/          the engine (shared by every talk)
  my-talk/          one folder per talk: index.html and assets/
Needs git and the GitHub CLI (gh), signed in.
"""
import argparse, html, json, os, re, shutil, subprocess, sys, time, urllib.request

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(SKILL, 'engine')
TEMPLATES = os.path.join(SKILL, 'templates')

def sh(cmd, cwd=None, check=True, quiet=False):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit('Failed: %s\n%s' % (' '.join(cmd), (r.stderr or r.stdout).strip()))
    return r

def gh_json(args, check=False):
    r = sh(['gh'] + args, check=check)
    if r.returncode:
        return None
    try:
        return json.loads(r.stdout or 'null')
    except ValueError:
        return None

def need_tools():
    for t in ('git', 'gh'):
        if not shutil.which(t):
            sys.exit('%s is not installed. Install it first (GitHub CLI: https://cli.github.com).' % t)
    if sh(['gh', 'auth', 'status'], check=False).returncode:
        sys.exit('The GitHub CLI is not signed in. Run: gh auth login')

def repo_of(clone):
    url = sh(['git', 'remote', 'get-url', 'origin'], cwd=clone).stdout.strip()
    m = re.search(r'github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$', url)
    if not m:
        sys.exit('The clone at %s does not point at a GitHub repository.' % clone)
    return m.group(1), m.group(2)

def copy_engine(clone):
    dst = os.path.join(clone, 'labdeck')
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(ENGINE):
        shutil.copy(os.path.join(ENGINE, f), os.path.join(dst, f))
    open(os.path.join(clone, '.nojekyll'), 'a').close()

def talks(clone):
    out = []
    for d in sorted(os.listdir(clone)):
        page = os.path.join(clone, d, 'index.html')
        if d.startswith(('.', '_')) or d == 'labdeck' or not os.path.isfile(page):
            continue
        src = open(page, encoding='utf-8', errors='ignore').read()
        m = re.search(r'<title>(.*?)</title>', src, re.S)
        n = len(re.findall(r'<section\b[^>]*\bclass\s*=\s*["\'][^"\']*\bslide\b', src))
        out.append({'slug': d, 'title': html.unescape(m.group(1).strip()) if m else d, 'slides': n,
                    'labdeck': 'labdeck/labdeck.js' in src, 'questions': bool(re.search(r'\bpolls\s*:\s*\{\s*\w', src))})
    return out

def write_home(clone):
    page = os.path.join(clone, 'index.html')
    if not os.path.exists(page):
        shutil.copy(os.path.join(TEMPLATES, 'home.html'), page)
    src = open(page, encoding='utf-8').read()
    if '<!-- talks:start -->' not in src:
        return
    items = ''.join('    <li><a href="%s/"><span>%s</span><small>%s</small></a></li>\n' % (
        t['slug'], html.escape(t['title']), ('%d slides' % t['slides'] if t['slides'] else '') + (' · audience questions' if t['questions'] else ''))
        for t in talks(clone))
    src = re.sub(r'(<!-- talks:start -->\n).*?(<!-- talks:end -->)', lambda m: m.group(1) + items + m.group(2), src, flags=re.S)
    open(page, 'w', encoding='utf-8').write(src)

def pages_url(owner, name):
    info = gh_json(['api', 'repos/%s/%s/pages' % (owner, name)])
    if info and info.get('html_url'):
        return info['html_url'].rstrip('/') + '/'
    return ('https://%s.github.io/' % owner.lower()) + ('' if name.lower() == owner.lower() + '.github.io' else name + '/')

def setup(a):
    need_tools()
    owner, _, name = a.repo.partition('/')
    if not owner or not name:
        sys.exit('--repo must look like OWNER/NAME')
    clone = os.path.abspath(a.clone or name)
    if not os.path.isdir(os.path.join(clone, '.git')):
        exists = sh(['gh', 'repo', 'view', a.repo, '--json', 'name'], check=False).returncode == 0
        if not exists:
            sh(['gh', 'repo', 'create', a.repo, '--private' if a.private else '--public', '--description', 'Talks, published with LabDeck'])
            print('Created the repository %s.' % a.repo)
        r = sh(['gh', 'repo', 'clone', a.repo, clone], check=False)
        if r.returncode:
            sys.exit('Could not clone %s: %s' % (a.repo, r.stderr.strip()))
    else:
        sh(['git', 'pull', '--ff-only'], cwd=clone, check=False)
    copy_engine(clone)
    write_home(clone)
    if a.slug:
        slug = re.sub(r'[^a-z0-9-]+', '-', a.slug.lower()).strip('-')
        deck = os.path.join(clone, slug)
        os.makedirs(os.path.join(deck, 'assets'), exist_ok=True)
        page = os.path.join(deck, 'index.html')
        if not os.path.exists(page):
            t = open(os.path.join(TEMPLATES, 'deck.html'), encoding='utf-8').read()
            title = a.title or slug.replace('-', ' ').title()
            t = t.replace("'__TITLE__'", json.dumps(title)).replace('__TITLE__', html.escape(title)).replace('__SECTION__', '')
            open(page, 'w', encoding='utf-8').write(t)
            print('Started %s from the template.' % page)
        else:
            print('%s already exists; it was left as it is.' % page)
        write_home(clone)
    print(json.dumps({'clone': clone, 'deck': os.path.join(clone, a.slug) if a.slug else None,
                      'site': pages_url(owner, name)}, indent=1))

def publish(a):
    need_tools()
    clone = os.path.abspath(a.clone)
    owner, name = repo_of(clone)
    copy_engine(clone)
    write_home(clone)
    sh(['git', 'add', '-A'], cwd=clone)
    if sh(['git', 'diff', '--cached', '--quiet'], cwd=clone, check=False).returncode:
        sh(['git', 'commit', '-m', a.message or ('Publish %s' % (a.slug or 'talks'))], cwd=clone)
    branch = sh(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=clone).stdout.strip()
    if branch == 'HEAD':
        branch = 'main'
        sh(['git', 'checkout', '-B', branch], cwd=clone)
    r = sh(['git', 'push', '-u', 'origin', branch], cwd=clone, check=False)
    if r.returncode:
        sys.exit('Push failed:\n' + r.stderr.strip())
    # GitHub Pages: serve this branch from the repository root
    info = gh_json(['api', 'repos/%s/%s/pages' % (owner, name)])
    if not info:
        r = sh(['gh', 'api', '-X', 'POST', 'repos/%s/%s/pages' % (owner, name), '-f', 'source[branch]=%s' % branch, '-f', 'source[path]=/'], check=False)
        if r.returncode:
            vis = (gh_json(['repo', 'view', '%s/%s' % (owner, name), '--json', 'visibility']) or {}).get('visibility', '')
            hint = ' The repository is private; free GitHub accounts can only publish public repositories.' if vis == 'PRIVATE' else ''
            sys.exit('Could not turn on GitHub Pages: %s.%s Turn it on in the repository: Settings > Pages > Deploy from a branch > %s / (root).' % (r.stderr.strip() or r.stdout.strip(), hint, branch))
        print('Turned on GitHub Pages for %s/%s.' % (owner, name))
    site = pages_url(owner, name)
    deck = site + (a.slug + '/' if a.slug else '')
    head = sh(['git', 'rev-parse', 'HEAD'], cwd=clone).stdout.strip()
    if not a.no_wait:
        print('Waiting for GitHub Pages to publish (usually under a minute)...', flush=True)
        deadline = time.time() + 600
        while time.time() < deadline:
            b = gh_json(['api', 'repos/%s/%s/pages/builds/latest' % (owner, name)]) or {}
            if b.get('status') == 'built' and b.get('commit') == head:
                break
            if b.get('status') == 'errored' and b.get('commit') == head:
                sys.exit('GitHub Pages could not build the site: %s' % (b.get('error') or {}).get('message'))
            time.sleep(6)
        ok = False
        for _ in range(20):
            try:
                with urllib.request.urlopen(urllib.request.Request(deck, headers={'Cache-Control': 'no-cache'}), timeout=15) as resp:
                    ok = resp.status == 200
            except Exception:
                ok = False
            if ok:
                break
            time.sleep(5)
        print('Live: %s' % deck if ok else 'Pushed, but %s did not answer yet. GitHub Pages can take a few minutes the first time.' % deck)
    print(json.dumps({'site': site, 'deck': deck, 'phones': bool(a.slug) and any(t['slug'] == a.slug and t['questions'] for t in talks(clone))}, indent=1))

def status(a):
    clone = os.path.abspath(a.clone)
    owner, name = repo_of(clone)
    print(json.dumps({'repo': '%s/%s' % (owner, name), 'site': pages_url(owner, name), 'talks': talks(clone)}, indent=1))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('setup'); s.add_argument('--repo', required=True); s.add_argument('--slug'); s.add_argument('--title'); s.add_argument('--clone'); s.add_argument('--private', action='store_true')
    p = sub.add_parser('publish'); p.add_argument('--clone', required=True); p.add_argument('--slug'); p.add_argument('--message'); p.add_argument('--no-wait', action='store_true')
    t = sub.add_parser('status'); t.add_argument('--clone', required=True)
    a = ap.parse_args()
    {'setup': setup, 'publish': publish, 'status': status}[a.cmd](a)

if __name__ == '__main__':
    main()
