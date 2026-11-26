/*! LabDeck v1: web slides, a six-screen lab wall that follows them, and live phone questions.
    https://github.com/datarefinerylab/slides-to-lab-wall · MIT licence
    You never need to edit this file. Each deck sets window.LABDECK before loading it. */
(() => {
'use strict';
const VERSION = 1;

/* ================= configuration ================= */
const USER = window.LABDECK || {};
const C = Object.assign({
  title: document.title, author: '', date: '',
  width: 1920, height: 1080,          // the size the slides are designed at
  transition: 'fade', duration: 600,  // default for slides without data-transition
  polls: {},                          // audience questions; empty means a plain deck
  relay: 'https://ntfy.sh',           // where answers and wall messages travel
  firebase: '',                       // optional Firebase Realtime Database URL for big rooms
  home: '',                           // where the wall link points (e.g. '../' for the deck list)
}, USER);
C.wall = Object.assign({ width: 3840, height: 1080, bandY: 360, bandHeight: 360, screens: 6, screenWidth: 640, code: '', firebase: '', logo: '' }, USER.wall || {});
const POLLS = C.polls && typeof C.polls === 'object' ? C.polls : {};
for (const id of Object.keys(POLLS)) {
  const P = POLLS[id];
  if (!/^[A-Za-z0-9_-]{1,24}$/.test(id) || !P || typeof P !== 'object') { delete POLLS[id]; continue; }
  if (!Array.isArray(P.opts) || !P.opts.length) P.type = 'cloud';
  else if (P.type !== 'multi') P.type = 'single';
  P.q = String(P.q || ''); P.max = Math.min(80, +P.max || 40);
}
const HAS_POLLS = Object.keys(POLLS).length > 0;

/* ================= helpers ================= */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const k in attrs) {
    const v = attrs[k];
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else if (k === 'style') e.style.cssText = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  return add(e, ...kids);
}
function add(el, ...kids) { for (const k of kids.flat(Infinity)) if (k != null && k !== false) el.append(k.nodeType ? k : document.createTextNode(String(k))); return el; }
const ls = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};
const NS = 'ld:' + location.pathname.replace(/index\.html?$/, '') + ':';   // per deck
const ABC = 'abcdefghjkmnpqrstuvwxyz23456789';
const rid = n => Array.from(crypto.getRandomValues(new Uint8Array(n)), b => ABC[b % ABC.length]).join('');
const b64e = s => btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const b64d = s => { try { return atob(String(s).replace(/-/g, '+').replace(/_/g, '/')); } catch { return ''; } };
const hash = s => { let x = 2166136261; for (let i = 0; i < s.length; i++) { x ^= s.charCodeAt(i); x = Math.imul(x, 16777619); } return x >>> 0; };
const pct = (a, b) => b ? Math.round(100 * a / b) : 0;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const LOCAL = !/^https?:$/.test(location.protocol) || /^(localhost|127\.|\[::1\])/.test(location.hostname);
const cleanCode = s => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 16);
const pageUrl = (u = location.href) => { const x = new URL(u, location.href); return x.origin + x.pathname.replace(/index\.html?$/, ''); };
const relayTopic = name => String(C.relay).replace(/\/+$/, '') + '/labdeck-' + name;
function cleanFb(u) {
  u = String(u || '').trim().replace(/\/+$/, '');
  if (!u) return '';
  try {
    const x = new URL(u);
    const okHost = /(\.firebaseio\.com|\.firebasedatabase\.app)$/.test(x.hostname) || (LOCAL && /^(localhost|127\.0\.0\.1)$/.test(x.hostname));
    if (!okHost || (x.protocol !== 'https:' && !LOCAL)) return '';
    return x.origin + x.pathname.replace(/\/+$/, '');
  } catch { return ''; }
}
const JUNK = new RegExp('[' + [[0, 31], [127, 127], [0x200b, 0x200f], [0x2028, 0x202f], [0xfeff, 0xfeff]].map(([a, b]) => '\\u' + a.toString(16).padStart(4, '0') + '-\\u' + b.toString(16).padStart(4, '0')).join('') + ']', 'g');
const normText = s => String(s).replace(JUNK, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
// web fonts can arrive after the first layout; anything measured is measured again then
let FONTGEN = 0;
const onFonts = f => { if (!document.fonts) return; document.fonts.addEventListener('loadingdone', () => { FONTGEN++; f(); }); document.fonts.ready.then(() => { FONTGEN++; f(); }); };
function bump(el) { el.classList.remove('ld-bump'); void el.offsetWidth; el.classList.add('ld-bump'); }
function fullscreen() { (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen())?.catch(() => {}); }
function qrSvg(text) {
  if (typeof qrcode !== 'function') return '';
  const q = qrcode(0, 'M'); q.addData(text); q.make();
  const n = q.getModuleCount(), m = 2; let d = '';
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (q.isDark(r, c)) d += `M${c + m} ${r + m}h1v1h-1z`;
  return `<svg viewBox="0 0 ${n + m * 2} ${n + m * 2}" shape-rendering="crispEdges" role="img" aria-label="QR code to answer on your phone"><rect width="100%" height="100%" fill="#fff"/><path d="${d}" fill="#000"/></svg>`;
}
// shrink text marked data-fit until it fits its box
function fitText(root) {
  for (const el of $$('[data-fit]', root).concat(root.matches && root.matches('[data-fit]') ? [root] : [])) {
    el.style.fontSize = '';
    let fs = parseFloat(getComputedStyle(el).fontSize) || 16;
    // tight line heights let letters poke out a little; only a real extra line counts as too tall
    const over = () => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + Math.max(2, fs * .3);
    for (let k = 0; k < 40 && over() && fs > 8; k++) { fs *= .93; el.style.fontSize = fs + 'px'; }
  }
}

/* ================= the slides ================= */
const HOST = document.getElementById('slides');
const SL = HOST ? $$(':scope > .slide', HOST) : [];
const pollsIn = el => [...new Set([el.dataset.poll, ...$$('[data-poll]', el).map(e => e.dataset.poll)].filter(p => p && Object.hasOwn(POLLS, p)))];
const SLIDE_POLLS = SL.map(pollsIn);
const ORDER = [...new Set([...SLIDE_POLLS.flat(), ...Object.keys(POLLS)])];
const LABEL = Object.fromEntries(ORDER.map((p, i) => [p, String(i + 1)]));
const isLive = i => !!(SLIDE_POLLS[i] && SLIDE_POLLS[i].length);
const askOf = i => {     // the question phones should jump to on this slide
  if (!SL[i]) return null;
  const w = SL[i].querySelector('.ld-poll[data-poll]');
  if (w && POLLS[w.dataset.poll]) return w.dataset.poll;
  if (SL[i].dataset.poll && POLLS[SL[i].dataset.poll]) return SL[i].dataset.poll;
  return SLIDE_POLLS[i][0] || null;
};
const sectionOf = i => { for (let j = i; j >= 0; j--) if (SL[j] && SL[j].dataset.section) return SL[j].dataset.section; return ''; };
const groupsOf = root => [...new Set($$('[data-step]', root).map(e => +e.dataset.step || 0))].sort((a, b) => a - b);
function setSteps(root, n, instant) {
  const open = new Set(groupsOf(root).slice(0, n));
  if (instant) root.classList.add('ld-instant');
  $$('[data-step]', root).forEach(e => e.classList.toggle('ld-in', open.has(+e.dataset.step || 0)));
  if (instant) { void root.offsetWidth; root.classList.remove('ld-instant'); }
}

/* ================= answers: {d: device, p: poll, v: option index, "0,2", or text} ================= */
function checkAnswer(a) {
  if (!a || typeof a !== 'object') return null;
  const d = String(a.d || ''), p = String(a.p || ''); let v = a.v;
  if (!/^[a-z0-9]{6,16}$/.test(d) || !Object.hasOwn(POLLS, p) || (typeof v !== 'string' && typeof v !== 'number')) return null;
  v = String(v); const P = POLLS[p];
  if (P.type === 'cloud') { v = normText(v).slice(0, P.max); if (!v) return null; }
  else {
    const ix = [...new Set(v.split(',').map(Number))];
    if (!ix.length || ix.some(i => !Number.isInteger(i) || i < 0 || i >= P.opts.length)) return null;
    if (P.type === 'single' && ix.length !== 1) return null;
    v = ix.sort((x, y) => x - y).join(',');
  }
  const t = Number(a.t) > 1e12 ? Number(a.t) : Date.now();
  return { d, p, v, t };
}
const DEMO_WORDS = ['more examples', 'live demo', 'the data', 'open questions', 'next steps', 'the method', 'more time', 'the results', 'live demo', 'the data', 'collaboration', 'more examples', 'the code', 'live demo', 'reproducibility'];
const pickW = (w, rnd) => { let r = rnd() * w.reduce((a, b) => a + b, 0); for (let i = 0; i < w.length; i++) { r -= w[i]; if (r <= 0) return i; } return 0; };
function demoAnswer(pid, k) {      // seeded, so the deck and the wall invent the very same answers
  let x = hash(pid + '|' + k);
  const rnd = () => { x = (x + 0x6D2B79F5) >>> 0; let t = Math.imul(x ^ (x >>> 15), 1 | x); t ^= t + Math.imul(t ^ (t >>> 7), 61 | t); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
  const P = POLLS[pid], d = 'demo' + String(k).padStart(4, '0');
  if (P.type === 'cloud') { const w = Array.isArray(P.demo) && P.demo.length ? P.demo : DEMO_WORDS; return { d, p: pid, v: String(w[k % w.length]) }; }
  const wts = Array.isArray(P.demo) && P.demo.length === P.opts.length ? P.demo : P.opts.map((_, i) => 1 + hash(pid + ':' + i) % 9);
  if (P.type === 'multi') { const s = new Set([pickW(wts, rnd)]); if (rnd() < .55) s.add(pickW(wts, rnd)); return { d, p: pid, v: [...s].join(',') }; }
  return { d, p: pid, v: String(pickW(wts, rnd)) };
}
function makeBoard(onChange) {
  const store = new Map(), hidden = new Set();
  let demo = false, trick = 0;
  const B = {
    store, hidden,
    get demo() { return demo; },
    ingest(raw, isDemo) {
      const a = checkAnswer(raw); if (!a) return;
      const k = a.d + '|' + a.p, old = store.get(k);
      if ((old && old.v === a.v) || store.size > 8000) return;
      if (old) a.t = old.t;
      if (isDemo) a.demo = true;
      store.set(k, a); onChange(a);
    },
    rows: pid => [...store.values()].filter(a => a.p === pid && (demo || !a.demo)),
    tally(pid) {
      const P = POLLS[pid], rows = B.rows(pid);
      if (P.type === 'cloud') {
        const m = new Map();
        for (const a of rows) { const e = m.get(a.v) || { text: a.v, c: 0, t: a.t }; e.c++; e.t = Math.min(e.t, a.t); m.set(a.v, e); }
        const all = [...m.values()].sort((a, b) => b.c - a.c || a.t - b.t);
        return { n: rows.length, all, items: all.filter(e => !hidden.has(pid + '|' + e.text)) };
      }
      const c = P.opts.map(() => 0);
      for (const a of rows) for (const i of a.v.split(',')) c[+i]++;
      return { n: rows.length, c };
    },
    phones: () => new Set([...store.values()].filter(a => demo || !a.demo).map(a => a.d)).size,
    setDemo(on) {
      demo = !!on; trick++;
      for (const [k, a] of store) if (a.demo) store.delete(k);
      if (demo) ORDER.forEach(pid => { for (let k = 0; k < 26; k++) B.ingest(demoAnswer(pid, k), true); });
      onChange(null);
    },
    trickle(pid) {   // on a question slide, demo answers drip in as if phones were answering
      const my = ++trick;
      for (const [k, a] of store) if (a.demo && a.p === pid) store.delete(k);
      onChange(null);
      let k = 0;
      const step = () => { if (my !== trick || !demo || k >= 26) return; B.ingest(demoAnswer(pid, k++), true); setTimeout(step, 120 + Math.random() * 380); };
      setTimeout(step, 1200);
    },
    clear() { store.clear(); },
  };
  return B;
}

/* ================= transport: phones -> deck (and the wall) ================= */
function watchLatest(url, on, status) {     // the newest message on a relay topic, then live ones
  let stop = false, es = null, timer, newest = 0, seen = '';
  const take = m => { try { if (m && m.event === 'message' && m.id !== seen && m.time >= newest) { newest = m.time; seen = m.id; on(JSON.parse(m.message)); } } catch {} };
  const sweep = async () => {
    try {
      const r = await fetch(`${url}/json?poll=1&since=latest`, { cache: 'no-store' });
      if (!r.ok) throw 0;
      (await r.text()).split('\n').forEach(l => { if (l.trim()) { try { take(JSON.parse(l)); } catch {} } });
      status(true);
    } catch { status(false); }
    if (!stop) timer = setTimeout(sweep, es && es.readyState === 1 ? 30000 : 4000);
  };
  try {
    es = new EventSource(`${url}/sse`);
    es.onopen = () => status(true);
    es.onmessage = e => { try { take(JSON.parse(e.data)); } catch {} };
  } catch {}
  sweep();
  return () => { stop = true; clearTimeout(timer); if (es) es.close(); };
}
function pollJson(url, on, status, every) {
  let stop = false, timer, last = '';
  const tick = async () => {
    try { const r = await fetch(url, { cache: 'no-store' }); if (!r.ok) throw 0; const t = await r.text(); if (t !== last) { last = t; const j = JSON.parse(t); if (j) on(j); } status(true); }
    catch { status(false); }
    if (!stop) timer = setTimeout(tick, every);
  };
  tick();
  return () => { stop = true; clearTimeout(timer); };
}
function makeTransport(fb, room) {
  if (fb) {
    const base = `${fb}/rooms/${room}`;
    return {
      kind: 'Firebase',
      send: a => fetch(`${base}/a/${a.d}/${a.p}.json`, { method: 'PUT', body: JSON.stringify({ v: a.v, t: Date.now() }) }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); }),
      listen(on, status) {
        let stop = false, timer;
        const tick = async () => {
          try {
            const r = await fetch(`${base}/a.json`, { cache: 'no-store' });
            if (!r.ok) throw 0;
            const j = (await r.json()) || {};
            for (const d in j) for (const p in (j[d] || {})) { const x = j[d][p]; if (x) on({ d, p, v: x.v, t: x.t }); }
            status(true);
          } catch { status(false); }
          if (!stop) timer = setTimeout(tick, 2000);
        };
        tick();
        return () => { stop = true; clearTimeout(timer); };
      },
      setState: s => fetch(`${base}/s.json`, { method: 'PUT', body: JSON.stringify(s) }).catch(() => {}),
      watchState: on => pollJson(`${base}/s.json`, on, () => {}, 2500),
    };
  }
  const url = relayTopic(room), now = relayTopic(room + '-now');
  return {
    kind: 'Relay',
    send: a => fetch(url, { method: 'POST', body: JSON.stringify({ d: a.d, p: a.p, v: a.v }) }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); }),
    listen(on, status) {
      let stop = false, es = null, live = false, timer, lastOk = 0;
      const take = m => { try { if (m && m.event === 'message') { const a = JSON.parse(m.message); a.t = m.time * 1000; on(a); } } catch {} };
      const sweep = async () => {   // history, and a safety net when the live stream is blocked
        try {
          const r = await fetch(`${url}/json?poll=1&since=all`, { cache: 'no-store' });
          if (!r.ok) throw 0;
          (await r.text()).split('\n').forEach(l => { if (l.trim()) { try { take(JSON.parse(l)); } catch {} } });
          lastOk = Date.now(); status(true);
        } catch { if (!live) status(false); }
        if (!stop) timer = setTimeout(sweep, live ? 30000 : 8000);
      };
      try {
        es = new EventSource(`${url}/sse`);
        es.onopen = () => { live = true; status(true); };
        es.onmessage = e => { live = true; try { take(JSON.parse(e.data)); } catch {} };
        es.onerror = () => { live = false; if (Date.now() - lastOk > 20000) status(false); };
      } catch {}
      sweep();
      return () => { stop = true; clearTimeout(timer); if (es) es.close(); };
    },
    setState: s => fetch(now, { method: 'POST', body: JSON.stringify(s) }).catch(() => {}),
    watchState: on => watchLatest(now, on, () => {}),
  };
}

/* ================= transport: deck -> lab wall ================= */
function makeWallLink(code) {
  const fb = cleanFb(C.wall.firebase);
  if (fb) {
    const url = `${fb}/walls/${code}.json`;
    return { push: st => fetch(url, { method: 'PUT', body: JSON.stringify(st) }).then(r => r.ok), watch: (on, status) => pollJson(url, on, status, 800) };
  }
  const url = relayTopic('wall-' + code);
  return { push: st => fetch(url, { method: 'POST', body: JSON.stringify(st) }).then(r => r.ok), watch: (on, status) => watchLatest(url, on, status) };
}
function wallCode() {
  const fixed = cleanCode(C.wall.code);
  if (fixed.length >= 4) return fixed;
  const w = ls.get('ld:wall', {});        // shared by every deck on this site, so one wall link serves all talks
  if (!/^[a-z0-9]{4,16}$/.test(w.code || '')) { w.code = rid(8); ls.set('ld:wall', w); }
  return w.code;
}

/* ================= widgets: questions, results, QR, counts (deck and wall) ================= */
function mountWidgets(root, B, ctx) {
  const ups = [];
  $$('.ld-poll[data-poll]', root).forEach(w => {
    const pid = w.dataset.poll, P = POLLS[pid]; if (!P) return;
    const parts = (w.dataset.parts || 'q opts count').split(/\s+/), num = h('b', { text: '0' });
    w.replaceChildren();
    add(w, parts.includes('q') && h('div', { class: 'ld-q', text: P.q }),
      parts.includes('opts') && (P.type === 'cloud' ? (P.hint && h('div', { class: 'ld-hint', text: P.hint })) : h('ol', { class: 'ld-opts' }, P.opts.map(o => h('li', { text: o })))),
      parts.includes('count') && h('div', { class: 'ld-num' }, num, h('span', { text: 'answers' })));
    let shown = 0;
    ups.push(() => { const n = B.rows(pid).length; if (n !== shown) { num.textContent = n; if (n > shown) bump(num); shown = n; } });
  });
  $$('.ld-results[data-poll]', root).forEach(w => {
    const pid = w.dataset.poll, P = POLLS[pid]; if (!P) return;
    const parts = (w.dataset.parts || 'n chart').split(/\s+/), nEl = h('b', { text: '0' });
    const empty = h('div', { class: 'ld-empty', text: w.dataset.empty || 'Waiting for the first answer…' });
    w.replaceChildren();
    add(w, parts.includes('n') && h('div', { class: 'ld-n' }, nEl, h('span', { text: 'answers' })), empty);
    if (P.type === 'cloud') {
      const box = add(w, h('div', { class: 'ld-cloud' })).lastChild, max = +w.dataset.max || 40;
      let sig = '', before = new Set();
      ups.push(() => {
        const t = B.tally(pid), list = t.items.slice(0, max);
        nEl.textContent = t.n; empty.hidden = list.length > 0; box.hidden = !list.length;
        const s = list.map(e => e.text + ':' + e.c).join('|') + '@' + box.clientWidth + 'x' + box.clientHeight + '#' + FONTGEN;
        if (s === sig) return; sig = s;
        const mx = list.length ? list[0].c : 1, fs = parseFloat(getComputedStyle(w).fontSize) || 24;
        // start big (as big as the box allows), then shrink everything together until it fits
        const base = Math.max(fs * clamp(3.4 / Math.sqrt(list.length || 1), .9, 2.2), box.clientHeight ? Math.min(box.clientHeight / 2.6, box.clientHeight * 1.1 / Math.sqrt(list.length || 1)) : 0);
        const spans = list.map((it, r) => h('span', { class: (r === 0 && it.c > 1 ? 'ld-top' : it.c === 1 ? 'ld-one' : '') + (before.size && !before.has(it.text) ? ' ld-new' : ''), text: it.text, title: ctx.onWord ? 'Click to hide or show' : null, onclick: ctx.onWord ? e => { e.stopPropagation(); ctx.onWord(pid, it.text); } : null }));
        before = new Set(list.map(it => it.text));
        box.replaceChildren(...spans);
        // measure the words themselves: a centred, wrapped cloud overflows up and down, which scrollHeight misses
        const fits = () => {
          if (!box.clientHeight) return true;
          const b = box.getBoundingClientRect(); let t = Infinity, u = -Infinity, l = Infinity, r = -Infinity;
          for (const sp of spans) { const q = sp.getBoundingClientRect(); t = Math.min(t, q.top); u = Math.max(u, q.bottom); l = Math.min(l, q.left); r = Math.max(r, q.right); }
          return u - t <= b.height + 1 && r - l <= b.width + 1;
        };
        for (let k = 1; k > .2; k *= .92) {   // shrink everything together until the cloud fits its box
          spans.forEach((sp, r) => sp.style.fontSize = Math.round(base * k * (1 + (mx > 1 ? (list[r].c - 1) / (mx - 1) : 0))) + 'px');
          if (fits()) break;
        }
      });
    } else {
      const rows = P.opts.map(o => { const p = h('span', { class: 'ld-p', text: '0%' }), c = h('span', { class: 'ld-c', text: '0' }); return { el: h('div', { class: 'ld-bar' }, h('span', { class: 'ld-l', text: o }), h('span', { class: 'ld-t' }, h('i')), p, c), p, c }; });
      const bars = add(w, h('div', { class: 'ld-bars' }, rows.map(r => r.el))).lastChild;
      ups.push(() => {
        const t = B.tally(pid), mx = Math.max(1, ...t.c); nEl.textContent = t.n; empty.hidden = t.n > 0; bars.hidden = !t.n;
        rows.forEach((r, i) => { r.el.style.setProperty('--v', t.n ? t.c[i] / mx : 0); r.el.classList.toggle('ld-lead', t.n > 0 && t.c[i] === mx); r.p.textContent = pct(t.c[i], t.n) + '%'; r.c.textContent = t.c[i]; });
      });
    }
  });
  $$('.ld-count[data-poll]', root).forEach(w => { const pid = w.dataset.poll; if (!POLLS[pid]) return; let shown = -1; ups.push(() => { const n = B.rows(pid).length; if (n !== shown) { w.textContent = n; if (shown >= 0 && n > shown) bump(w); shown = n; } }); });
  $$('.ld-phones', root).forEach(w => ups.push(() => { w.textContent = B.phones(); }));
  $$('.ld-qr', root).forEach(w => {
    const box = h('div', { class: 'ld-qr-code' }), cap = w.dataset.caption != null ? w.dataset.caption : 'Scan to answer';
    w.replaceChildren(box); if (cap) add(w, h('div', { class: 'ld-qr-cap', text: cap }));
    let last = '';
    ups.push(() => { const u = ctx.joinUrl(); if (u !== last) { last = u; box.innerHTML = qrSvg(u); } });
  });
  return () => ups.forEach(f => f());
}

/* ================= boot ================= */
const Q = new URLSearchParams(location.search);
const jm = location.hash.match(/^#j\.([a-z0-9]{4,12})(?:\.([\w-]+))?$/);
const wm = location.hash.match(/^#w\.([a-z0-9]{4,16})$/);
window.LabDeck = Object.assign(window.LabDeck || {}, { version: VERSION, slides: SL, polls: POLLS });
if (jm && HAS_POLLS) startPhone(jm[1], cleanFb(b64d(jm[2] || '')) || cleanFb(C.firebase));
else if (wm) startWall(wm[1], null);
else if (Q.has('wall')) startWall('', { i: (+Q.get('s') || 1) - 1, s: Q.has('step') ? +Q.get('step') : 99, demo: Q.has('demo') });
else if (SL.length) Q.has('print') ? startPrint() : startDeck();

/* ================================================================
   DECK: the laptop
   ================================================================ */
function startDeck() {
  const root = document.documentElement;
  root.classList.add('ld-deck');
  const STATIC = Q.has('static');
  if (STATIC) root.classList.add('ld-static');

  /* ---- session ---- */
  const cfg = Object.assign({ room: rid(7), fb: cleanFb(C.firebase), hidden: [] }, ls.get(NS + 'cfg', {}));
  cfg.fb = cleanFb(cfg.fb);
  const saveCfg = () => ls.set(NS + 'cfg', cfg);
  saveCfg();
  const wallPrefs = () => ls.get('ld:wall', {});
  const wallOn = () => !!wallPrefs().on;
  const joinUrl = () => location.href.split(/[?#]/)[0] + '#j.' + cfg.room + (cfg.fb ? '.' + b64e(cfg.fb) : '');
  const homeUrl = () => (C.home ? new URL(C.home, location.href).href : location.href).split(/[?#]/)[0];
  const wallUrl = () => homeUrl() + '#w.' + wallCode();

  /* ---- answers ---- */
  let dirty = false, connected = false, transport = null, stopListen = null;
  const B = makeBoard(a => { if (a && !a.demo) dirty = true; later(); });
  cfg.hidden.forEach(x => B.hidden.add(String(x)));
  (ls.get(NS + 'a:' + cfg.room, []) || []).forEach(a => B.ingest(a, false));
  setInterval(() => { if (dirty) { dirty = false; ls.set(NS + 'a:' + cfg.room, [...B.store.values()].filter(a => !a.demo)); } }, 1500);
  function connect() {
    if (stopListen) stopListen(); stopListen = null; connected = false;
    if (!HAS_POLLS || STATIC) return;       // ?static is for checking pictures: no network
    transport = makeTransport(cfg.fb, cfg.room);
    stopListen = transport.listen(a => B.ingest(a, false), ok => { connected = ok; status(); });
  }
  function onWord(pid, text) {
    const k = pid + '|' + text; B.hidden.has(k) ? B.hidden.delete(k) : B.hidden.add(k);
    cfg.hidden = [...B.hidden]; saveCfg(); refresh(); if (!panel.hidden) drawPanel();
  }

  /* ---- stage ---- */
  HOST.classList.add('ld-stage');
  HOST.style.width = C.width + 'px'; HOST.style.height = C.height + 'px';
  const scale = () => Math.min(innerWidth / C.width, innerHeight / C.height);
  const fit = () => HOST.style.setProperty('--ld-s', scale());
  SL.forEach(el => el.setAttribute('aria-hidden', 'true'));
  const qrFloat = add(HOST, h('div', { class: 'ld-float', hidden: true }, h('div', { class: 'ld-qr-code' }), h('div', { class: 'ld-qr-cap', text: 'Scan to answer' }))).lastChild;
  const qrBig = add(HOST, h('div', { class: 'ld-bigqr', hidden: true }, h('div', { class: 'ld-qr-code' }), h('div', { class: 'ld-qr-cap', text: 'Scan to answer' }), h('small', { class: 'ld-qr-sub' }))).lastChild;
  const ups = SL.map(el => mountWidgets(el, B, { joinUrl, onWord }));
  SL.forEach(el => setSteps(el, 0, true));
  const chip = add(document.body, h('div', { class: 'ld-chip', hidden: true })).lastChild;
  const toastEl = add(document.body, h('div', { class: 'ld-toast' })).lastChild;
  const black = add(document.body, h('div', { class: 'ld-black', hidden: true })).lastChild;
  const panel = add(document.body, h('div', { class: 'ld-panel', hidden: true })).lastChild;
  let tt = 0;
  function toast(t) { toastEl.textContent = t; toastEl.classList.add('on'); clearTimeout(tt); tt = setTimeout(() => toastEl.classList.remove('on'), 1800); }
  function drawQR() {
    const svg = qrSvg(joinUrl());
    $$('.ld-qr-code', qrFloat).concat($$('.ld-qr-code', qrBig)).forEach(b => b.innerHTML = svg);
    $('.ld-qr-sub', qrBig).textContent = LOCAL ? 'This page is open from this computer, so phones cannot reach it yet. Publish it first.' : joinUrl().replace(/^https?:\/\//, '');
    refresh();
  }

  /* ---- transitions ---- */
  let cur = -1, step = 0, running = [], token = 0;
  const calm = () => STATIC || root.classList.contains('ld-calm') || matchMedia('(prefers-reduced-motion: reduce)').matches;
  function transition(from, to, dir) {
    running.forEach(a => a.finish()); running = [];       // a transition still playing jumps to its end
    const my = ++token;
    SL.forEach(s => { s.style.zIndex = ''; if (s !== to && s !== from) s.classList.remove('on'); });
    to.classList.add('on'); to.setAttribute('aria-hidden', 'false');
    if (!from || from === to) return;
    from.setAttribute('aria-hidden', 'true');
    const owner = dir > 0 ? to : from;    // going back replays the slide's own transition in reverse
    const kind = calm() || !to.animate ? 'none' : (owner.dataset.transition || C.transition);
    const dur = clamp(+(owner.dataset.duration || C.duration) || 600, 50, 4000);
    const mine = [];
    const done = () => { if (my === token) { from.classList.remove('on'); from.style.zIndex = to.style.zIndex = ''; } mine.forEach(a => a.cancel()); };
    if (kind === 'none' || kind === 'cut') { done(); return; }
    const o = { duration: dur, easing: 'cubic-bezier(.45,0,.2,1)', fill: 'both' }, X = 100 * dir;
    const run = (el, kf) => { const a = el.animate(kf, o); running.push(a); mine.push(a); return a; };
    let last;
    to.style.zIndex = 2; from.style.zIndex = 1;
    if (kind === 'push') { run(from, [{ transform: 'none' }, { transform: `translateX(${-X}%)` }]); last = run(to, [{ transform: `translateX(${X}%)` }, { transform: 'none' }]); }
    else if (kind === 'cover' || kind === 'slide') last = run(to, [{ transform: `translateX(${X}%)` }, { transform: 'none' }]);
    else if (kind === 'uncover') { from.style.zIndex = 3; last = run(from, [{ transform: 'none' }, { transform: `translateX(${-X}%)` }]); }
    else if (kind === 'wipe') last = run(to, [{ clipPath: dir > 0 ? 'inset(0 100% 0 0)' : 'inset(0 0 0 100%)' }, { clipPath: 'inset(0 0 0 0)' }]);
    else if (kind === 'zoom') { run(from, [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: `scale(${dir > 0 ? 1.08 : .92})` }]); last = run(to, [{ opacity: 0, transform: `scale(${dir > 0 ? .92 : 1.08})` }, { opacity: 1, transform: 'none' }]); }
    else if (kind === 'morph') last = morph(from, to, o, run);
    else last = run(to, [{ opacity: 0 }, { opacity: 1 }]);          // fade
    last.onfinish = done;
  }
  // morph: pieces with the same data-morph name fly from their old place; the rest fades in
  function morph(from, to, o, run) {
    const olds = new Map($$('[data-morph]', from).map(e => [e.dataset.morph, e])), s = scale();
    const flyers = $$('[data-morph]', to).filter(e => olds.has(e.dataset.morph));
    const last = run(to, [{ opacity: 1 }, { opacity: 1 }]);
    for (const b of flyers) {
      const a = olds.get(b.dataset.morph), ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      if (!rb.width || !rb.height) continue;
      const base = getComputedStyle(b).transform, tail = base && base !== 'none' ? ' ' + base : '';
      run(b, [{ transformOrigin: '0 0', transform: `translate(${(ra.left - rb.left) / s}px,${(ra.top - rb.top) / s}px) scale(${ra.width / rb.width},${ra.height / rb.height})${tail}` }, { transformOrigin: '0 0', transform: base === 'none' ? 'none' : base }]);
    }
    for (const kid of to.children) if (!flyers.some(f => kid === f || kid.contains(f))) run(kid, [{ opacity: 0 }, { opacity: 0, offset: .3 }, { opacity: 1 }]);
    return last;
  }

  /* ---- navigation ---- */
  function show(i, st, dir) {
    i = clamp(i, 0, SL.length - 1);
    const from = cur >= 0 ? SL[cur] : null, changed = i !== cur;
    cur = i; step = clamp(st, 0, groupsOf(SL[i]).length);
    if (changed) { setSteps(SL[i], step, true); transition(from, SL[i], dir || 1); }
    else setSteps(SL[i], step, calm());
    if (changed) {
      fitText(SL[i]);
      if (B.demo && !STATIC && SL[i].querySelector('.ld-poll[data-poll]')) B.trickle(SL[i].querySelector('.ld-poll[data-poll]').dataset.poll);
      pushAsk();
    }
    refresh();
    ls.set(NS + 'pos', { i, s: step, room: cfg.room, at: Date.now() });
  }
  function next() { if (step < groupsOf(SL[cur]).length) show(cur, step + 1, 1); else if (cur < SL.length - 1) show(cur + 1, 0, 1); }
  function prev() { if (step > 0) show(cur, step - 1, -1); else if (cur > 0) show(cur - 1, groupsOf(SL[cur - 1]).length, -1); }
  function go(i) { show(i, 0, i >= cur ? 1 : -1); }

  /* ---- phones follow the question on screen ---- */
  let askSent = null, askTimer = 0;
  function pushAsk() {
    if (!HAS_POLLS || !transport) return;
    const p = askOf(cur); if (!p || p === askSent) return;
    clearTimeout(askTimer);
    askTimer = setTimeout(() => { if (askOf(cur) !== p) return; askSent = p; transport.setState({ p, n: Date.now() }); }, 600);
  }

  /* ---- lab wall: the six screens follow this deck ---- */
  let wall = makeWallLink(wallCode()), wallSent = '', wallTimer = 0, wallPause = 0, wallOk = null;
  const wallState = () => JSON.stringify({ v: VERSION, u: pageUrl(), t: C.title, i: cur, s: step, n: SL.length, room: HAS_POLLS ? cfg.room : '', fb: cfg.fb ? b64e(cfg.fb) : '', demo: B.demo, hid: [...B.hidden].slice(-60) });
  function wallSync(force) {
    if (!wallOn() || STATIC || cur < 0 || Date.now() < wallPause) return;
    if (!force && wallState() === wallSent) return;
    clearTimeout(wallTimer);
    wallTimer = setTimeout(() => {      // wait until the slide settles: clicking through five slides sends one message
      const v = wallState(); if (v === wallSent && !force) return;
      wallSent = v;
      wall.push(JSON.parse(v)).then(ok => { if (!ok) throw 0; wallOk = true; status(); }).catch(() => { wallSent = ''; wallOk = false; wallPause = Date.now() + 8000; status(); });
    }, 300);
  }
  function wallToggle() {
    const w = wallPrefs(); w.on = !w.on; ls.set('ld:wall', w);
    wallSent = ''; wallPause = 0; wallOk = null;
    toast(w.on ? 'Lab wall on' : 'Lab wall off');
    if (w.on) wallSync(true);
    status(); if (!panel.hidden) drawPanel();
  }
  addEventListener('storage', e => { if (e.key === 'ld:wall') { wall = makeWallLink(wallCode()); wallSent = ''; status(); } });

  /* ---- refresh, status ---- */
  let rf = 0;
  function later() { if (!rf) rf = setTimeout(() => { rf = 0; refresh(); }, 140); }
  function refresh() {
    if (cur < 0) return;
    ups[cur]();
    const s = SL[cur];
    qrFloat.hidden = !(HAS_POLLS && isLive(cur) && !s.querySelector('.ld-qr') && s.dataset.qr !== 'off');
    if (qrFloat.dataset.side !== (s.dataset.qr || '')) qrFloat.dataset.side = s.dataset.qr || '';
    status();
  }
  function status() {
    const n = B.phones();
    chip.replaceChildren(
      h('span', { text: `${cur + 1} / ${SL.length}` + (groupsOf(SL[cur] || HOST).length ? ` · step ${step}` : '') }),
      wallOn() && h('span', { class: wallOk === false ? 'ld-bad' : 'ld-ok', text: wallOk === false ? 'Wall: no connection' : 'Wall on' }),
      HAS_POLLS && h('span', null, h('i', { class: 'ld-dot' + (connected ? ' ok' : '') }), n + (n === 1 ? ' phone' : ' phones')),
      B.demo && h('span', { class: 'ld-bad', text: 'Demo data' }));
    wallSync();
  }
  setInterval(status, 2000);

  /* ---- panel (A) ---- */
  let armed = false, ptimer = 0;
  function copy(text, btn) { navigator.clipboard?.writeText(text).then(() => { const o = btn.textContent; btn.textContent = 'Copied'; setTimeout(() => btn.textContent = o, 1200); }, () => {}); }
  function download(name, text, type) { const a = h('a', { href: URL.createObjectURL(new Blob([text], { type })), download: name }); document.body.append(a); a.click(); a.remove(); }
  function exportRows() {
    const devs = new Map();
    return [...B.store.values()].filter(a => !a.demo).sort((a, b) => a.t - b.t).map(a => {
      if (!devs.has(a.d)) devs.set(a.d, 'phone' + String(devs.size + 1).padStart(2, '0'));
      const P = POLLS[a.p];
      return { phone: devs.get(a.d), question: LABEL[a.p], text: P.q, answer: P.type === 'cloud' ? a.v : a.v.split(',').map(i => P.opts[+i]).join(' | '), time: new Date(a.t).toISOString() };
    });
  }
  const slug = () => (C.title || 'deck').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'deck';
  function drawPanel() {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName || '')) return;
    const real = [...B.store.values()].filter(a => !a.demo), nPh = new Set(real.map(a => a.d)).size;
    const card = (title, ...kids) => h('section', { class: 'ld-card' }, h('h2', { text: title }), kids);
    const fbIn = h('input', { id: 'ldFb', type: 'url', placeholder: 'https://your-project-default-rtdb.europe-west1.firebasedatabase.app', value: cfg.fb, spellcheck: 'false' }), fbMsg = h('p', { class: 'ld-help' });
    const keys = [['→ Space', 'next (and builds)'], ['←', 'back'], ['Home / End', 'first / last slide'], ['number, Enter', 'go to that slide'], ['A', 'this panel'], ['W', 'lab wall on or off'], ['F', 'full screen'], ['B', 'black screen'], ['H', 'status chip'], ['M', 'calm motion']];
    if (HAS_POLLS) keys.push(['Q', 'big QR code'], ['D', 'demo answers']);
    const pn = h('div', { class: 'ld-pn' },
      h('header', null, h('h1', { text: C.title || 'Setup' }), h('button', { class: 'ld-btn pri', text: 'Back to slides', onclick: togglePanel })),
      card('Lab wall',
        h('p', { class: 'ld-help', text: 'Six screens in a row follow these slides. Do this once on the lab workstation: open the link below in Chrome and press F11. Keep it bookmarked. The same link serves every talk you give from this browser, and it switches to whichever deck you are presenting.' }),
        h('div', { class: 'ld-link', text: wallUrl() }),
        h('div', { class: 'ld-row' },
          h('button', { class: 'ld-btn' + (wallOn() ? '' : ' pri'), text: wallOn() ? 'Turn the wall off' : 'Turn the wall on', onclick: wallToggle }),
          h('button', { class: 'ld-btn', text: 'Copy wall link', onclick: e => copy(wallUrl(), e.currentTarget) }),
          h('span', { class: 'ld-help', text: wallOn() ? (wallOk === false ? 'On, but the last message did not go out. Check the internet connection.' : 'On: each slide change goes to the wall (W).') : 'Off: nothing is sent (W).' })),
        LOCAL && h('p', { class: 'ld-help ld-warn', text: 'This page is open from this computer, so the workstation cannot open the link. Present from the published page (GitHub Pages).' })),
      HAS_POLLS && card('Audience questions',
        h('div', { class: 'ld-tiles' },
          h('div', null, h('b', { text: nPh }), h('span', { text: 'phones' })),
          h('div', null, h('b', { text: real.length }), h('span', { text: 'answers' })),
          h('div', null, h('b', { text: connected ? 'Live' : 'Offline' }), h('span', { text: (transport ? transport.kind : '') + ' · session ' + cfg.room }))),
        h('div', { class: 'ld-link', text: joinUrl() }),
        h('div', { class: 'ld-row' },
          h('button', { class: 'ld-btn', text: 'Copy phone link', onclick: e => copy(joinUrl(), e.currentTarget) }),
          h('button', { class: 'ld-btn', text: 'Export CSV', onclick: () => { const r = exportRows(), esc = v => '"' + String(v).replace(/"/g, '""') + '"'; download(`${slug()}-${cfg.room}.csv`, ['phone,question,text,answer,time', ...r.map(x => [x.phone, x.question, x.text, x.answer, x.time].map(esc).join(','))].join('\n'), 'text/csv'); } }),
          h('button', { class: 'ld-btn', text: 'Copy as JSON', onclick: e => copy(JSON.stringify(exportRows(), null, 1), e.currentTarget) }),
          h('button', { class: 'ld-btn', text: B.demo ? 'Turn demo answers off' : 'Rehearse with demo answers', onclick: () => setDemo(!B.demo) }),
          h('button', { class: 'ld-btn warn', text: armed ? 'Really start empty? Export first.' : 'Start a new session', onclick: newSession })),
        LOCAL && h('p', { class: 'ld-help ld-warn', text: 'This page is open from this computer, so phones cannot reach it. Present from the published page.' }),
        B.demo && h('p', { class: 'ld-help ld-warn', text: 'Demo answers are on. The breakdowns include made-up answers; the tiles and exports never do.' }),
        h('div', { class: 'ld-grid' }, ORDER.map(pid => {
          const P = POLLS[pid], t = B.tally(pid);
          const body = P.type === 'cloud'
            ? h('div', { class: 'ld-words' }, t.all.length ? t.all.map(e => h('button', { class: B.hidden.has(pid + '|' + e.text) ? 'off' : '', title: 'Show or hide on screen', onclick: () => onWord(pid, e.text) }, e.text, h('b', { text: '×' + e.c }))) : h('span', { class: 'ld-help', text: 'No answers yet.' }))
            : h('div', null, P.opts.map((o, i) => h('div', { class: 'ld-mb', style: `--v:${t.n ? t.c[i] / t.n : 0}` }, h('span', { text: o }), h('span', { class: 'p', text: pct(t.c[i], t.n) + '%' }), h('span', { class: 'c', text: t.c[i] }), h('span', { class: 't' }, h('i')))));
          return h('div', { class: 'ld-poll-card' }, h('h3', { text: P.q }), h('div', { class: 'ld-meta', text: `Question ${LABEL[pid]} · ${t.n} answers` + (P.type === 'cloud' ? ' · click a word to hide it' : '') }), body);
        })),
        h('div', { class: 'ld-row', style: 'align-items:flex-end' },
          h('label', { class: 'ld-field' }, h('span', { text: 'Firebase database (optional, for rooms over about 25 phones)' }), fbIn),
          h('button', { class: 'ld-btn', text: 'Save', onclick: () => { const v = cleanFb(fbIn.value); if (fbIn.value.trim() && !v) { fbMsg.textContent = 'That is not a Firebase database URL. It ends in firebaseio.com or firebasedatabase.app.'; return; } cfg.fb = v; saveCfg(); connect(); drawQR(); wallSync(true); drawPanel(); } })),
        fbMsg),
      card('Keys', h('div', { class: 'ld-keys' }, keys.map(([k, t]) => h('div', null, h('kbd', { text: k }), t)))),
      h('div', { class: 'ld-row' }, h('button', { class: 'ld-btn', text: root.classList.contains('ld-calm') ? 'Full motion' : 'Calm motion', onclick: () => { root.classList.toggle('ld-calm'); drawPanel(); } })),
    );
    const keep = panel.scrollTop; panel.replaceChildren(pn); panel.scrollTop = keep;
  }
  function togglePanel() {
    panel.hidden = !panel.hidden; clearInterval(ptimer);
    if (!panel.hidden) { drawPanel(); ptimer = setInterval(() => { if (!armed) drawPanel(); }, 2500); }
  }
  function newSession() {
    if (!armed) { armed = true; drawPanel(); setTimeout(() => { armed = false; if (!panel.hidden) drawPanel(); }, 4000); return; }
    armed = false; cfg.room = rid(7); cfg.hidden = []; B.hidden.clear(); saveCfg(); B.clear(); askSent = null;
    connect(); drawQR(); wallSync(true); go(0); drawPanel();
  }
  function setDemo(on) {
    B.setDemo(on);
    if (on && SL[cur].querySelector('.ld-poll[data-poll]')) B.trickle(SL[cur].querySelector('.ld-poll[data-poll]').dataset.poll);
    toast(on ? 'Demo answers on' : 'Demo answers off');
    refresh(); if (!panel.hidden) drawPanel();
  }

  /* ---- input ---- */
  let digits = '', dt = 0;
  addEventListener('keydown', e => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const k = e.key, typing = /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName);
    if (!panel.hidden) { if (!typing && (k === 'Escape' || k.toLowerCase() === 'a')) togglePanel(); return; }
    if (typing) return;
    if (/^[0-9]$/.test(k)) { digits += k; clearTimeout(dt); dt = setTimeout(() => digits = '', 1500); toast('Go to slide ' + digits + ' (Enter)'); return; }
    if (k === 'Enter' && digits) { const n = +digits; digits = ''; if (n >= 1) go(n - 1); return; }
    if (!black.hidden && k !== 'b' && k !== 'B' && k !== '.') { black.hidden = true; }
    if (['ArrowRight', 'ArrowDown', ' ', 'PageDown', 'Enter'].includes(k)) { e.preventDefault(); next(); }
    else if (['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace'].includes(k)) { e.preventDefault(); prev(); }
    else if (k === 'Home') go(0);
    else if (k === 'End') go(SL.length - 1);
    else if (k === 'Escape') qrBig.hidden = true;
    else switch (k.toLowerCase()) {
      case 'a': togglePanel(); break;
      case 'w': wallToggle(); break;
      case 'f': fullscreen(); break;
      case 'b': case '.': black.hidden = !black.hidden; break;
      case 'h': chip.hidden = !chip.hidden; break;
      case 'm': root.classList.toggle('ld-calm'); toast(root.classList.contains('ld-calm') ? 'Calm motion' : 'Full motion'); break;
      case 'q': if (HAS_POLLS) qrBig.hidden = !qrBig.hidden; break;
      case 'd': if (HAS_POLLS) setDemo(!B.demo); break;
    }
  });
  HOST.addEventListener('click', e => {
    if (e.target.closest('a,button,input,select,textarea,video,audio,iframe,[data-noclick]')) return;
    if (!qrBig.hidden) { qrBig.hidden = true; return; }
    if (e.target.closest('.ld-float')) { qrBig.hidden = false; return; }
    if (e.clientX < innerWidth * .2) prev(); else next();
  });
  let tx = null;
  HOST.addEventListener('touchstart', e => { tx = e.touches[0].clientX; }, { passive: true });
  HOST.addEventListener('touchend', e => { if (tx == null) return; const d = e.changedTouches[0].clientX - tx; tx = null; if (Math.abs(d) > 50) { d < 0 ? next() : prev(); } }, { passive: true });
  addEventListener('resize', () => { fit(); fitText(SL[cur]); later(); });

  /* ---- start ---- */
  fit(); connect(); drawQR();
  if (Q.has('demo')) B.setDemo(true);
  const pos = ls.get(NS + 'pos', null), want = Q.has('s') ? (+Q.get('s') || 1) - 1 : null;
  if (want != null) show(want, STATIC ? 99 : 0, 1);
  else if (pos && pos.room === cfg.room && pos.i > 0 && pos.i < SL.length && Date.now() - (pos.at || 0) < 3 * 3600e3) show(pos.i, pos.s || 0, 1);
  else show(0, 0, 1);
  if (STATIC) SL.forEach(el => setSteps(el, 99, true));
  onFonts(() => { fitText(SL[cur]); later(); });
  Object.defineProperties(window.LabDeck, Object.getOwnPropertyDescriptors({ go, next, prev, get cur() { return cur; }, get step() { return step; }, board: B, cfg, wallUrl, joinUrl, wallState, wallToggle, setDemo }));
}

/* ================================================================
   PRINT (?print): every slide, every build, one page each
   ================================================================ */
function startPrint() {
  const root = document.documentElement;
  root.classList.add('ld-print');
  add(document.head, h('style', { text: `@page{size:${C.width}px ${C.height}px;margin:0}` }));
  HOST.style.width = C.width + 'px';
  const B = makeBoard(() => {});
  SL.forEach(el => { el.style.width = C.width + 'px'; el.style.height = C.height + 'px'; el.classList.add('on'); setSteps(el, 99, true); mountWidgets(el, B, { joinUrl: () => location.href.split(/[?#]/)[0] })(); });
  document.fonts?.ready.then(() => SL.forEach(fitText));
}

/* ================================================================
   PHONE (#j.<session>): answer the questions
   ================================================================ */
function startPhone(room, fb) {
  const root = document.documentElement;
  root.classList.add('ld-phone-mode');
  if (HOST) HOST.hidden = true;
  document.title = (C.title || 'Questions') + ' · answer';
  const T = makeTransport(fb, room), KEY = NS + 'ph:' + room;
  const st = ls.get(KEY, null) || { dev: rid(10), sent: {} };
  const save = () => ls.set(KEY, st); save();
  let cur = ORDER.findIndex(p => !st.sent[p]); if (cur < 0) cur = ORDER.length - 1;
  let live = null, draft = {}, touched = false;
  const app = add(document.body, h('div', { class: 'ld-phone' },
    h('header', null, h('span', { class: 'ld-ph-brand', text: C.title || '' }), h('span', { class: 'ld-ph-live', text: 'Following the screen' })),
    h('nav', { class: 'ld-ph-steps', 'aria-label': 'Questions' }), h('main'),
    h('footer', { text: 'No names. No login. Answers show up on the big screen.' }))).lastChild;
  const steps = $('nav', app), main = $('main', app);
  steps.hidden = ORDER.length < 2;
  const sayOf = (p, v) => POLLS[p].type === 'cloud' ? v : v.split(',').map(i => POLLS[p].opts[+i]).join(', ');
  async function flush(p, tries = 0) {
    const s = st.sent[p]; if (!s || s.ok) return;
    try { await T.send({ d: st.dev, p, v: s.v }); s.ok = true; s.err = false; save(); }
    catch { s.err = tries >= 5; save(); if (tries < 5) setTimeout(() => flush(p, tries + 1), 1500 * (tries + 1)); }
    if (ORDER[cur] === p) render();
  }
  function submit(p, v) { st.sent[p] = { v, ok: false }; save(); touched = false; delete draft[p]; render(); flush(p); }
  function goTo(i) { cur = clamp(i, 0, ORDER.length - 1); touched = false; render(); scrollTo({ top: 0 }); }
  function render() {
    const p = ORDER[cur], P = POLLS[p], s = st.sent[p];
    steps.replaceChildren(...ORDER.map((id, i) => h('button', { class: (st.sent[id] ? 'done ' : '') + (i === cur ? 'cur' : ''), text: LABEL[id], 'aria-label': 'Question ' + LABEL[id], 'aria-current': i === cur ? 'step' : null, onclick: () => goTo(i) })));
    const card = h('section', { class: 'ld-ph-card' }, ORDER.length > 1 && h('div', { class: 'ld-ph-lab', text: 'Question ' + LABEL[p] + ' of ' + ORDER.length }), h('h1', { text: P.q }));
    if (s) {
      add(card,
        h('div', { class: 'ld-ph-ok' + (s.ok ? '' : ' wait') }, h('i'), s.ok ? 'Sent. Look up.' : (s.err ? 'Not sent yet' : 'Sending…')),
        h('p', { class: 'ld-ph-said' }, 'You said: ', h('b', { text: sayOf(p, s.v) })),
        s.err && h('p', { class: 'ld-ph-err', text: 'The network dropped it. Your answer is saved on this phone.' }),
        s.err && h('button', { class: 'ld-ph-next', text: 'Try again', onclick: () => { s.err = false; render(); flush(p); } }),
        h('button', { class: 'ld-ph-next', text: 'Change my answer', onclick: () => { delete st.sent[p]; save(); render(); } }),
        cur < ORDER.length - 1 ? h('button', { class: 'ld-ph-next', text: 'Next question', onclick: () => goTo(cur + 1) }) : null);
    } else if (P.type === 'cloud') {
      const send = h('button', { class: 'ld-ph-send', text: 'Send', disabled: true });
      const inp = h('input', { class: 'ld-ph-text', type: 'text', maxlength: P.max, placeholder: 'Type here', autocomplete: 'off', autocapitalize: 'none', enterkeyhint: 'send', 'aria-label': P.q });
      inp.value = draft[p] || '';
      const upd = () => { draft[p] = inp.value; touched = !!inp.value.trim(); send.disabled = !normText(inp.value); };
      inp.addEventListener('input', upd); upd();
      const go = () => { const v = normText(inp.value).slice(0, P.max); if (v) submit(p, v); };
      inp.addEventListener('keydown', e => { if (e.key === 'Enter') go(); });
      send.addEventListener('click', go);
      add(card, P.hint && h('p', { class: 'ld-ph-hint', text: P.hint }), inp, send);
    } else {
      const multi = P.type === 'multi', sel = new Set(draft[p] || []);
      const send = h('button', { class: 'ld-ph-send', text: 'Send', disabled: !sel.size });
      const box = h('div', { class: 'ld-ph-opts' + (multi ? ' multi' : ''), role: multi ? 'group' : 'radiogroup' });
      P.opts.forEach((o, i) => {
        const b = h('button', { text: o, class: sel.has(i) ? 'sel' : '', role: multi ? 'checkbox' : 'radio', 'aria-checked': String(sel.has(i)) });
        b.addEventListener('click', () => {
          if (multi) { sel.has(i) ? sel.delete(i) : sel.add(i); } else { sel.clear(); sel.add(i); }
          draft[p] = [...sel]; touched = sel.size > 0;
          [...box.children].forEach((c, j) => { c.classList.toggle('sel', sel.has(j)); c.setAttribute('aria-checked', String(sel.has(j))); });
          send.disabled = !sel.size;
        });
        box.append(b);
      });
      send.addEventListener('click', () => { if (sel.size) submit(p, [...sel].sort((a, b) => a - b).join(',')); });
      add(card, (P.hint || multi) && h('p', { class: 'ld-ph-hint', text: P.hint || 'Pick all that apply.' }), box, send);
    }
    const kids = [card];
    if (live && live !== p && !st.sent[live]) kids.push(h('button', { class: 'ld-ph-pill', text: 'Go to the question on screen (' + LABEL[live] + ')', onclick: () => goTo(ORDER.indexOf(live)) }));
    main.replaceChildren(...kids);
  }
  T.watchState(s => {
    const lp = s && Object.hasOwn(POLLS, s.p) ? s.p : null;
    if (lp === live) return;
    live = lp;
    if (lp && lp !== ORDER[cur] && !touched) goTo(ORDER.indexOf(lp)); else render();
  });
  ORDER.forEach(p => { if (st.sent[p] && !st.sent[p].ok) flush(p); });
  render();
}

/* ================================================================
   LAB WALL (#w.<wall code>): the workstation. It follows whichever deck
   is presenting with that wall code, and counts the answers itself.
   ?wall&s=N previews slide N offline (for checking a deck).
   ================================================================ */
function startWall(code, preview) {
  const root = document.documentElement, W = C.wall, SW = W.screenWidth, N = W.screens;
  root.classList.add('ld-wall-mode');
  if (HOST) HOST.hidden = true;
  document.title = 'Lab wall' + (C.title && SL.length ? ' · ' + C.title : '');
  const host = add(document.body, h('div', { class: 'ld-wall' })).lastChild;
  const stage = add(host, h('div', { class: 'ld-wst', style: `width:${W.width}px;height:${W.height}px` })).lastChild;
  const band = add(stage, h('div', { class: 'ld-band', style: `top:${W.bandY}px;height:${W.bandHeight}px;width:${N * SW}px` })).lastChild;
  const msg = add(stage, h('div', { class: 'ld-wmsg', style: `top:${W.bandY + W.bandHeight - 40}px;left:${SW}px;width:${(N - 2) * SW}px`, hidden: true })).lastChild;
  const BAND = !!preview && Q.has('band');     // preview only the screens (for screenshots)
  const fit = () => {
    if (BAND) { const s = innerWidth / (N * SW); stage.style.transform = `translate(0,${-W.bandY * s}px) scale(${s})`; return; }
    const s = Math.min(innerWidth / W.width, innerHeight / W.height);
    stage.style.transform = `translate(${(innerWidth - W.width * s) / 2}px,${(innerHeight - W.height * s) / 2}px) scale(${s})`;
  };
  addEventListener('resize', fit); fit();

  let room = '', fb = '', stopA = null, okA = true, okW = !!preview, gotState = !!preview, lostSince = 0, cur = -1, step = 99, layer = null;
  const B = makeBoard(() => later());
  const joinUrl = () => location.href.split(/[?#]/)[0] + '#j.' + (room || 'preview') + (fb ? '.' + b64e(fb) : '');
  function useRoom(r, f) {
    r = cleanCode(r).slice(0, 12); f = cleanFb(f);
    if (r === room && f === fb) return;
    room = r; fb = f; B.clear(); if (stopA) stopA(); stopA = null; okA = true;
    if (HAS_POLLS && room) stopA = makeTransport(fb, room).listen(a => B.ingest(a, false), ok => { okA = ok; later(); });
    if (layer) layer.up();
  }

  /* ---- what each slide shows on the wall ---- */
  const range = (txt, def) => {
    const t = String(txt || def).trim().toLowerCase();
    if (t === 'all') return [1, N];
    const m = t.match(/^(\d+)(?:\s*-\s*(\d+))?$/); if (!m) return range(def, def);
    const a = clamp(+m[1], 1, N), b = clamp(+(m[2] || m[1]), a, N); return [a, b];
  };
  const place = (el, a, b) => { el.classList.add('ld-ws'); el.style.left = (a - 1) * SW + 'px'; el.style.width = (b - a + 1) * SW + 'px'; return el; };
  const textOf = el => el ? el.textContent.replace(/\s+/g, ' ').trim() : '';
  function autoParts(i) {       // no <template class="wall">: build a sensible view from the slide itself
    const el = SL[i], mid = `2-${N - 1}`;
    const res = el.querySelector('.ld-results[data-poll]'), ask = el.querySelector('.ld-poll[data-poll]');
    const tEl = el.querySelector('[data-wall-title]') || el.querySelector('h1,h2,h3,.title');
    const title = textOf(tEl) || (el.dataset.title || '');
    const sub = $$('p,li,h4,h5,h6', el).map(textOf).find(t => t && t !== title && t.length > 2) || '';
    const kick = sectionOf(i);
    if (res || ask) {
      const pid = (res || ask).dataset.poll;
      return [h('div', { 'data-screens': mid, class: 'ld-auto ld-auto-live' },
        h('div', { class: 'ld-auto-kick', text: res ? 'Results' : 'Question ' + (LABEL[pid] || '') }),
        res ? h('div', { class: 'ld-auto-q', 'data-fit': '', text: POLLS[pid].q }) : null,
        res ? h('div', { class: 'ld-results', 'data-poll': pid }) : h('div', { class: 'ld-poll', 'data-poll': pid }))];
    }
    const img = el.querySelector('[data-wall]');      // a picture marked for the wall: <img data-wall> or <svg data-wall>
    const text = h('div', { 'data-screens': img ? `2-${Math.max(2, N - 3)}` : mid, class: 'ld-auto' },
      kick && h('div', { class: 'ld-auto-kick', text: kick }),
      h('div', { class: 'ld-auto-title', 'data-fit': '', text: title || C.title || '' }),
      sub && h('div', { class: 'ld-auto-sub', 'data-fit': '', text: sub }));
    const out = [text];
    if (img) out.push(h('div', { 'data-screens': `${Math.max(3, N - 2)}-${N - 1}`, class: 'ld-auto-img' }, img.tagName === 'IMG' ? h('img', { src: img.currentSrc || img.src, alt: '' }) : img.cloneNode(true)));
    return out;
  }
  function chrome(kind, at, i) {
    const el = place(h('div', { class: 'ld-chrome ld-chrome-' + kind }), at, at);
    if (kind === 'progress') {
      const n = SL.length, sec = sectionOf(i);
      add(el, h('div', { class: 'ld-c-kick', 'data-fit': '', text: sec || C.title || '' }),
        h('div', { class: 'ld-c-big' }, String(i + 1).padStart(2, '0'), h('span', { text: ' / ' + String(n).padStart(2, '0') })),
        h('div', { class: 'ld-c-bar' }, h('i', { style: `width:${n ? 100 * (i + 1) / n : 0}%` })));
    } else if (kind === 'join') {
      add(el, h('div', { class: 'ld-qr', 'data-caption': '' }), h('div', { class: 'ld-c-txt' }, h('div', { class: 'ld-c-kick', text: 'Scan to answer' }), h('div', { class: 'ld-c-ph' }, h('b', { class: 'ld-phones', text: '0' }), h('span', { text: 'phones' }))));
    } else {
      if (C.wall.logo) add(el, h('img', { class: 'ld-c-logo', src: C.wall.logo, alt: '' }));
      add(el, h('div', { class: 'ld-c-title', 'data-fit': '', text: C.title || '' }), (C.author || C.date) && h('div', { class: 'ld-c-sub', text: [C.author, C.date].filter(Boolean).join(' · ') }));
    }
    return el;
  }
  function build(i) {
    const el = SL[i], lay = h('div', { class: 'ld-wl' }), covered = new Set();
    const tpl = el.querySelector(':scope > template.wall');
    const parts = tpl ? [...tpl.content.cloneNode(true).children] : autoParts(i);
    if (tpl && tpl.dataset.bg) lay.style.background = tpl.dataset.bg;
    for (const p of parts) { const [a, b] = range(p.dataset.screens, `2-${N - 1}`); for (let k = a; k <= b; k++) covered.add(k); lay.append(place(p, a, b)); }
    if (!covered.has(1)) lay.append(chrome('progress', 1, i));
    if (!covered.has(N)) lay.append(chrome(HAS_POLLS && isLive(i) ? 'join' : 'brand', N, i));
    const up = mountWidgets(lay, B, { joinUrl });
    return { el: lay, i, up };
  }
  function lobby() {
    const lay = h('div', { class: 'ld-wl ld-lobby' });
    lay.append(place(h('div', { class: 'ld-ws ld-auto' }, h('div', { class: 'ld-auto-kick', text: 'Lab wall' }), h('div', { class: 'ld-auto-title', text: 'Ready for the next talk.' }), h('div', { class: 'ld-auto-sub', text: 'On the presenting laptop, open the deck and press W.' })), 2, N - 1));
    return { el: lay, i: -1, up: () => {} };
  }
  function swap(next) {
    const old = layer; layer = next;
    band.append(next.el); next.up(); fitText(next.el); next.up();
    setSteps(next.el, step, true);
    void next.el.offsetWidth; next.el.classList.add('on');
    if (old) { old.el.classList.remove('on'); setTimeout(() => old.el.remove(), 800); }
  }
  function show(i, s) {
    if (!SL.length) { if (!layer) swap(lobby()); return; }
    i = clamp(i, 0, SL.length - 1);
    if (i !== cur || !layer || layer.i < 0) {
      cur = i; step = s; swap(build(i));
      const ask = SL[i].querySelector('.ld-poll[data-poll]');
      if (B.demo && ask && !preview) B.trickle(ask.dataset.poll);
    } else if (s !== step) { step = s; setSteps(layer.el, step, false); }
    refresh();
  }
  function refresh() {
    if (layer) layer.up();
    const ok = okA && okW;
    if (ok) lostSince = 0; else if (!lostSince) lostSince = Date.now();
    msg.hidden = preview || (gotState && !(lostSince && Date.now() - lostSince > 8000));
    msg.textContent = !gotState ? 'Waiting for the deck · on the presenting laptop press W' : 'No connection · check this computer’s internet';
    msg.classList.toggle('bad', gotState);
  }
  let rf = 0;
  function later() { if (!rf) rf = setTimeout(() => { rf = 0; refresh(); }, 150); }
  setInterval(refresh, 2000);

  /* ---- following the deck ---- */
  const allowed = u => { try { const x = new URL(u, location.href); return x.origin === location.origin || (x.protocol === 'https:' && /\.github\.io$/.test(x.hostname)); } catch { return false; } };
  function onState(st) {
    if (!st || typeof st !== 'object') return;
    if (st.u && pageUrl(st.u) !== pageUrl()) {       // another deck is presenting: load it, keep the wall link
      if (allowed(st.u)) location.replace(pageUrl(st.u) + location.hash);
      return;
    }
    gotState = true;
    useRoom(st.room || '', b64d(st.fb || '') || C.firebase);
    B.hidden.clear(); (Array.isArray(st.hid) ? st.hid : []).forEach(x => B.hidden.add(String(x)));
    if (!!st.demo !== B.demo) B.setDemo(!!st.demo);
    show(Number(st.i) || 0, Number.isFinite(+st.s) ? +st.s : 0);
  }

  /* ---- keys: C screen numbers, F full screen ---- */
  let cal = null;
  function calibrate() {
    if (cal) { cal.remove(); cal = null; return; }
    cal = h('div', { class: 'ld-cal' },
      h('div', { class: 'off', style: `top:0;height:${W.bandY}px`, text: 'outside the screens (not visible)' }),
      h('div', { class: 'off', style: `top:${W.bandY + W.bandHeight}px;bottom:0`, text: 'outside the screens (not visible)' }),
      Array.from({ length: N }, (_, i) => h('div', { class: 's', style: `left:${i * SW}px;width:${SW}px;top:${W.bandY}px;height:${W.bandHeight}px` }, String(i + 1), h('small', { text: `${SW}×${W.bandHeight} at x ${i * SW}` }))));
    stage.append(cal);
  }
  addEventListener('keydown', e => {
    const k = e.key.toLowerCase();
    if (k === 'c') calibrate(); else if (k === 'f') fullscreen();
    else if (preview && (k === 'arrowright' || k === 'arrowleft')) show(cur + (k === 'arrowright' ? 1 : -1), 99);
  });
  addEventListener('click', () => { if (!document.fullscreenElement && !preview) document.documentElement.requestFullscreen()?.catch(() => {}); });
  let ct; addEventListener('mousemove', () => { document.body.style.cursor = 'default'; clearTimeout(ct); ct = setTimeout(() => document.body.style.cursor = '', 1500); });

  onFonts(() => { if (layer) { fitText(layer.el); later(); } });
  if (preview) {
    room = 'preview';
    if (preview.demo) B.setDemo(true);
    step = preview.s; show(preview.i, preview.s);
  } else {
    show(0, 0);
    makeWallLink(code).watch(onState, ok => { okW = ok; later(); });
  }
  refresh();
  window.LabDeck.wall = { onState, show, board: B, get cur() { return cur; }, get step() { return step; } };
}
})();
