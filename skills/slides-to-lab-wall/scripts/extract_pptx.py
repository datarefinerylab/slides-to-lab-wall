#!/usr/bin/env python3
"""Read a PowerPoint file (.pptx) and write down everything needed to rebuild it on the web.

Usage:
  python3 extract_pptx.py talk.pptx OUT_DIR [--width 1920]

Writes:
  OUT_DIR/outline.md    a readable slide-by-slide summary (read this first)
  OUT_DIR/outline.json  the same, complete: positions, text runs, colours, builds, notes
  OUT_DIR/media/        every picture used by the slides

Positions and sizes are in pixels of a deck that is --width pixels wide (1920 by default),
so they can be used directly in the deck's CSS. Font sizes are given in pt and in those px.
Uses only the Python standard library.
"""
import argparse, colorsys, json, os, posixpath, re, shutil, sys, zipfile
import xml.etree.ElementTree as ET

NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'c': 'http://schemas.openxmlformats.org/drawingml/2006/chart',
    'rel': 'http://schemas.openxmlformats.org/package/2006/relationships',
    'p14': 'http://schemas.microsoft.com/office/powerpoint/2010/main',
    'mc': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
}
R_ID = '{%s}id' % NS['r']
R_EMBED = '{%s}embed' % NS['r']

def local(tag):
    return tag.rsplit('}', 1)[-1]

class Pkg:
    def __init__(self, path):
        self.z = zipfile.ZipFile(path)
        self.names = set(self.z.namelist())
    def xml(self, name):
        return ET.fromstring(self.z.read(name)) if name in self.names else None
    def rels(self, part):
        d, f = posixpath.split(part)
        rp = posixpath.join(d, '_rels', f + '.rels')
        out = {}
        root = self.xml(rp)
        if root is None:
            return out
        for r in root.findall('rel:Relationship', NS):
            tgt = r.get('Target')
            if r.get('TargetMode') != 'External':
                tgt = posixpath.normpath(posixpath.join(d, tgt))
            out[r.get('Id')] = (r.get('Type', '').rsplit('/', 1)[-1], tgt)
        return out
    def rel_of_type(self, part, kind):
        for _, (t, tgt) in self.rels(part).items():
            if t == kind:
                return tgt
        return None

# ---------------- colours ----------------
def hex_to_rgb(h):
    h = h.strip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

def rgb_to_hex(rgb):
    return '#' + ''.join('%02x' % max(0, min(255, round(c * 255))) for c in rgb)

def apply_mods(hexv, el):
    r, g, b = hex_to_rgb(hexv)
    hh, l, s = colorsys.rgb_to_hls(r, g, b)
    alpha = None
    for m in el:
        v = int(m.get('val', '0')) / 100000
        n = local(m.tag)
        if n == 'lumMod': l *= v
        elif n == 'lumOff': l += v
        elif n == 'tint': l = l + (1 - l) * (1 - v)
        elif n == 'shade': l *= v
        elif n == 'satMod': s *= v
        elif n == 'alpha': alpha = v
    out = rgb_to_hex(colorsys.hls_to_rgb(hh, max(0, min(1, l)), max(0, min(1, s))))
    return out if alpha is None or alpha >= 1 else out + '%02x' % round(alpha * 255)

class Theme:
    def __init__(self, root, clrmap):
        self.colors, self.fonts = {}, {}
        self.clrmap = clrmap or {}
        if root is None:
            return
        cs = root.find('.//a:clrScheme', NS)
        if cs is not None:
            for c in cs:
                v = c.find('a:srgbClr', NS)
                s = c.find('a:sysClr', NS)
                self.colors[local(c.tag)] = '#' + (v.get('val') if v is not None else (s.get('lastClr') if s is not None else '000000')).lower()
        fs = root.find('.//a:fontScheme', NS)
        if fs is not None:
            for k in ('majorFont', 'minorFont'):
                f = fs.find('a:%s/a:latin' % k, NS)
                if f is not None:
                    self.fonts[k] = f.get('typeface')
    def color(self, holder):
        """Colour from an element that contains srgbClr / schemeClr / sysClr / prstClr."""
        if holder is None:
            return None
        for el in holder:
            n = local(el.tag)
            if n == 'srgbClr':
                return apply_mods('#' + el.get('val').lower(), el)
            if n == 'schemeClr':
                key = el.get('val')
                key = self.clrmap.get(key, {'bg1': 'lt1', 'tx1': 'dk1', 'bg2': 'lt2', 'tx2': 'dk2'}.get(key, key))
                base = self.colors.get(key)
                return apply_mods(base, el) if base else None
            if n == 'sysClr':
                return apply_mods('#' + (el.get('lastClr') or '000000').lower(), el)
            if n == 'prstClr':
                return el.get('val')
        return None
    def font(self, name):
        if not name:
            return None
        if name.startswith('+mj'):
            return self.fonts.get('majorFont')
        if name.startswith('+mn'):
            return self.fonts.get('minorFont')
        return name

# ---------------- shapes ----------------
class Ctx:
    def __init__(self, pkg, theme, scale, media_dir, media_map):
        self.pkg, self.theme, self.scale, self.media_dir, self.media_map = pkg, theme, scale, media_dir, media_map

def fill_of(ctx, sppr):
    if sppr is None:
        return None
    if sppr.find('a:noFill', NS) is not None:
        return 'none'
    sf = sppr.find('a:solidFill', NS)
    if sf is not None:
        return ctx.theme.color(sf)
    gf = sppr.find('a:gradFill', NS)
    if gf is not None:
        stops = [(int(gs.get('pos', '0')) / 1000, ctx.theme.color(gs)) for gs in gf.findall('a:gsLst/a:gs', NS)]
        lin = gf.find('a:lin', NS)
        ang = int(lin.get('ang', '0')) / 60000 if lin is not None else 0
        return 'linear-gradient(%ddeg, %s)' % (round(ang + 90), ', '.join('%s %d%%' % (c, p) for p, c in stops if c))
    return None

def line_of(ctx, sppr):
    if sppr is None:
        return None
    ln = sppr.find('a:ln', NS)
    if ln is None or ln.find('a:noFill', NS) is not None:
        return None
    c = ctx.theme.color(ln.find('a:solidFill', NS))
    w = int(ln.get('w', '12700')) * ctx.scale
    return {'color': c, 'width_px': round(w, 1)} if c else None

def media(ctx, part, rid):
    rel = ctx.pkg.rels(part).get(rid)
    if not rel or rel[1] not in ctx.pkg.names:
        return None
    src = rel[1]
    if src not in ctx.media_map:
        name = posixpath.basename(src)
        base, ext = os.path.splitext(name)
        k, out = 1, name
        while out in ctx.media_map.values():
            k += 1
            out = '%s-%d%s' % (base, k, ext)
        ctx.media_map[src] = out
        os.makedirs(ctx.media_dir, exist_ok=True)
        with open(os.path.join(ctx.media_dir, out), 'wb') as f:
            f.write(ctx.pkg.z.read(src))
    return 'media/' + ctx.media_map[src]

def text_of(ctx, txbody):
    if txbody is None:
        return []
    paras = []
    for p in txbody.findall('a:p', NS):
        ppr = p.find('a:pPr', NS)
        para = {'level': int(ppr.get('lvl', '0')) if ppr is not None else 0,
                'align': {'ctr': 'center', 'r': 'right', 'just': 'justify', 'l': 'left'}.get(ppr.get('algn')) if ppr is not None else None,
                'bullet': None, 'runs': []}
        if ppr is not None:
            if ppr.find('a:buNone', NS) is not None:
                para['bullet'] = 'none'
            elif ppr.find('a:buChar', NS) is not None:
                para['bullet'] = ppr.find('a:buChar', NS).get('char')
            elif ppr.find('a:buAutoNum', NS) is not None:
                para['bullet'] = ppr.find('a:buAutoNum', NS).get('type')
        for r in p:
            n = local(r.tag)
            if n not in ('r', 'fld', 'br'):
                continue
            if n == 'br':
                para['runs'].append({'text': '\n'})
                continue
            t = r.find('a:t', NS)
            rpr = r.find('a:rPr', NS)
            run = {'text': t.text if t is not None and t.text else ''}
            if rpr is not None:
                if rpr.get('sz'):
                    pt = int(rpr.get('sz')) / 100
                    run['size_pt'] = pt
                    run['size_px'] = round(pt * 12700 * ctx.scale, 1)
                if rpr.get('b') == '1': run['bold'] = True
                if rpr.get('i') == '1': run['italic'] = True
                if rpr.get('u') not in (None, 'none'): run['underline'] = True
                c = ctx.theme.color(rpr.find('a:solidFill', NS))
                if c: run['color'] = c
                lat = rpr.find('a:latin', NS)
                if lat is not None: run['font'] = ctx.theme.font(lat.get('typeface'))
                link = rpr.find('a:hlinkClick', NS)
                if link is not None and link.get(R_ID):
                    rel = ctx.pkg.rels(ctx.part).get(link.get(R_ID))
                    if rel: run['link'] = rel[1]
            para['runs'].append(run)
        paras.append(para)
    while paras and not ''.join(r['text'] for r in paras[-1]['runs']).strip():
        paras.pop()
    return paras

def ph_key(sp):
    ph = sp.find('.//p:nvPr/p:ph', NS)
    if ph is None:
        return None
    return (ph.get('type', 'body'), ph.get('idx'))

def find_ph(tree, key):
    """The matching placeholder in a layout or master."""
    if tree is None or key is None:
        return None
    typ, idx = key
    best = None
    for sp in tree.iter('{%s}sp' % NS['p']):
        k = ph_key(sp)
        if not k:
            continue
        if idx is not None and k[1] == idx:
            return sp
        if k[0] == typ or (typ in ('ctrTitle',) and k[0] == 'title') or (typ in ('subTitle', 'obj') and k[0] == 'body'):
            best = best or sp
    return best

def xfrm_of(el):
    x = el.find('p:spPr/a:xfrm', NS)
    if x is None:
        x = el.find('p:grpSpPr/a:xfrm', NS)
    if x is None:
        x = el.find('p:xfrm', NS)
    return x

def box(xfrm, ctx, tf):
    off, ext = xfrm.find('a:off', NS), xfrm.find('a:ext', NS)
    if off is None or ext is None:
        return None
    x, y, w, h = int(off.get('x')), int(off.get('y')), int(ext.get('cx')), int(ext.get('cy'))
    x, y, w, h = tf(x, y, w, h)
    s = ctx.scale
    out = {'x': round(x * s, 1), 'y': round(y * s, 1), 'w': round(w * s, 1), 'h': round(h * s, 1)}
    if xfrm.get('rot'): out['rotation_deg'] = round(int(xfrm.get('rot')) / 60000, 2)
    if xfrm.get('flipH') == '1': out['flip_h'] = True
    if xfrm.get('flipV') == '1': out['flip_v'] = True
    return out

def chart_data(ctx, part, rid):
    rel = ctx.pkg.rels(part).get(rid)
    if not rel:
        return None
    root = ctx.pkg.xml(rel[1])
    if root is None:
        return None
    pa = root.find('.//c:plotArea', NS)
    out = {'charts': []}
    title = root.find('.//c:title', NS)
    if title is not None:
        out['title'] = ''.join(t.text or '' for t in title.iter('{%s}t' % NS['a']))
    for ch in (pa if pa is not None else []):
        n = local(ch.tag)
        if not n.endswith('Chart'):
            continue
        entry = {'type': n, 'series': []}
        bd = ch.find('c:barDir', NS)
        if bd is not None: entry['direction'] = bd.get('val')
        for ser in ch.findall('c:ser', NS):
            name = ''.join(v.text or '' for v in ser.findall('c:tx//c:v', NS))
            cats = [v.text for v in ser.findall('c:cat//c:pt/c:v', NS)]
            vals = [v.text for v in ser.findall('c:val//c:pt/c:v', NS)] or [v.text for v in ser.findall('c:yVal//c:pt/c:v', NS)]
            sp = ser.find('c:spPr', NS)
            entry['series'].append({'name': name, 'categories': cats, 'values': vals, 'color': fill_of(ctx, sp)})
        out['charts'].append(entry)
    return out

def shapes(ctx, tree, part, layout, master, tf=lambda x, y, w, h: (x, y, w, h)):
    out = []
    if tree is None:
        return out
    for el in tree:
        n = local(el.tag)
        if n not in ('sp', 'pic', 'grpSp', 'graphicFrame', 'cxnSp'):
            continue
        nv = el.find('*/p:cNvPr', NS)
        item = {'id': nv.get('id') if nv is not None else None, 'name': nv.get('name') if nv is not None else '', 'kind': n}
        if nv is not None and nv.get('descr'): item['alt'] = nv.get('descr')
        if nv is not None and nv.get('hidden') == '1': item['hidden'] = True
        key = ph_key(el)
        if key: item['placeholder'] = key[0]
        x = xfrm_of(el)
        if x is None and key:          # placeholders inherit their place from the layout, then the master
            for src in (find_ph(layout, key), find_ph(master, key)):
                if src is not None and xfrm_of(src) is not None:
                    x = xfrm_of(src)
                    break
        if x is not None:
            b = box(x, ctx, tf)
            if b: item.update(b)
        sppr = el.find('p:spPr', NS)
        if n == 'sp' or n == 'cxnSp':
            geo = sppr.find('a:prstGeom', NS) if sppr is not None else None
            if geo is not None and geo.get('prst') not in ('rect',): item['geometry'] = geo.get('prst')
            f = fill_of(ctx, sppr)
            if f: item['fill'] = f
            ln = line_of(ctx, sppr)
            if ln: item['line'] = ln
            bp = sppr.find('a:blipFill/a:blip', NS) if sppr is not None else None
            if bp is not None and bp.get(R_EMBED): item['image'] = media(ctx, part, bp.get(R_EMBED))
            body = el.find('p:txBody', NS)
            t = text_of(ctx, body)
            if t:
                item['kind'] = 'text'
                item['paragraphs'] = t
                bpr = body.find('a:bodyPr', NS)
                if bpr is not None and bpr.get('anchor'):
                    item['valign'] = {'t': 'top', 'ctr': 'middle', 'b': 'bottom'}.get(bpr.get('anchor'))
        elif n == 'pic':
            blip = el.find('p:blipFill/a:blip', NS)
            if blip is not None and blip.get(R_EMBED):
                item['image'] = media(ctx, part, blip.get(R_EMBED))
            src = el.find('p:blipFill/a:srcRect', NS)
            if src is not None and src.attrib:
                item['crop_pct'] = {k: int(v) / 1000 for k, v in src.attrib.items()}
            vid = el.find('.//a:videoFile', NS)
            if vid is not None:
                rel = ctx.pkg.rels(part).get(vid.get(R_ID) or vid.get('{%s}link' % NS['r']))
                item['video'] = rel[1] if rel else True
        elif n == 'graphicFrame':
            gd = el.find('a:graphic/a:graphicData', NS)
            uri = gd.get('uri', '') if gd is not None else ''
            if uri.endswith('/table'):
                item['kind'] = 'table'
                rows = []
                for tr in gd.findall('.//a:tr', NS):
                    rows.append([' '.join(''.join(t.text or '' for t in p.iter('{%s}t' % NS['a'])) for p in tc.findall('.//a:p', NS)).strip() for tc in tr.findall('a:tc', NS)])
                item['rows'] = rows
            elif uri.endswith('/chart'):
                item['kind'] = 'chart'
                c = gd.find('c:chart', NS)
                if c is not None: item['chart'] = chart_data(ctx, part, c.get(R_ID))
            elif 'diagram' in uri:
                item['kind'] = 'smartart'
                item['note'] = 'SmartArt: rebuild from the slide picture'
            else:
                item['kind'] = 'object'
        elif n == 'grpSp':
            gx = el.find('p:grpSpPr/a:xfrm', NS)
            inner = tf
            if gx is not None and gx.find('a:chOff', NS) is not None:
                o, e = gx.find('a:off', NS), gx.find('a:ext', NS)
                co, ce = gx.find('a:chOff', NS), gx.find('a:chExt', NS)
                ox, oy, ex, ey = int(o.get('x')), int(o.get('y')), int(e.get('cx')), int(e.get('cy'))
                cx, cy, cex, cey = int(co.get('x')), int(co.get('y')), int(ce.get('cx')) or 1, int(ce.get('cy')) or 1
                sx, sy = ex / cex, ey / cey
                def inner(x, y, w, h, tf=tf, ox=ox, oy=oy, cx=cx, cy=cy, sx=sx, sy=sy):
                    return tf(ox + (x - cx) * sx, oy + (y - cy) * sy, w * sx, h * sy)
            item['children'] = shapes(ctx, el, part, layout, master, inner)
        out.append(item)
    return out

def background(ctx, *trees):
    for t in trees:
        if t is None:
            continue
        bg = t.find('p:cSld/p:bg', NS)
        if bg is None:
            continue
        pr = bg.find('p:bgPr', NS)
        if pr is not None:
            f = fill_of(ctx, pr)
            if f: return {'fill': f}
            blip = pr.find('a:blipFill/a:blip', NS)
            if blip is not None:
                return {'image': media(ctx, ctx.bg_part_for[id(t)], blip.get(R_EMBED))}
        ref = bg.find('p:bgRef', NS)
        if ref is not None:
            c = ctx.theme.color(ref)
            if c: return {'fill': c}
    return None

TRANSITIONS = {'fade': 'fade', 'push': 'push', 'wipe': 'wipe', 'cover': 'cover', 'pull': 'uncover', 'cut': 'none',
               'zoom': 'zoom', 'split': 'wipe', 'reveal': 'fade', 'morph': 'morph', 'dissolve': 'fade', 'randomBar': 'fade',
               'circle': 'zoom', 'diamond': 'zoom', 'plus': 'zoom', 'wedge': 'wipe', 'wheel': 'wipe', 'blinds': 'wipe',
               'checker': 'fade', 'comb': 'wipe', 'strips': 'wipe', 'newsflash': 'zoom', 'flash': 'fade', 'conveyor': 'push',
               'pan': 'push', 'ferris': 'push', 'gallery': 'push', 'flip': 'push', 'prism': 'push', 'doors': 'wipe',
               'window': 'zoom', 'vortex': 'zoom', 'ripple': 'zoom', 'shred': 'fade', 'switch': 'push', 'glitter': 'fade',
               'honeycomb': 'zoom', 'warp': 'zoom', 'flythrough': 'zoom', 'curtains': 'wipe', 'wind': 'push', 'prestige': 'fade',
               'fracture': 'fade', 'crush': 'zoom', 'peelOff': 'uncover', 'pageCurlDouble': 'uncover', 'pageCurlSingle': 'uncover',
               'airplane': 'uncover', 'origami': 'fade'}

def transition_of(root):
    if root is None:
        return None
    for tr in root.iter('{%s}transition' % NS['p']):
        kids = [k for k in tr if local(k.tag) not in ('sndAc', 'extLst')]
        typ = local(kids[0].tag) if kids else 'fade'
        dur = None
        for k, v in tr.attrib.items():
            if local(k) == 'dur':
                dur = int(v)
        if dur is None:
            dur = {'slow': 1000, 'med': 750, 'fast': 500}.get(tr.get('spd', 'fast'), 500)
        d = {'source': typ, 'labdeck': TRANSITIONS.get(typ, 'fade'), 'duration_ms': dur}
        if kids and kids[0].get('dir'): d['direction'] = kids[0].get('dir')
        if tr.get('advTm'): d['auto_advance_ms'] = int(tr.get('advTm'))
        return d
    return None

EFFECTS = {1: 'appear', 10: 'fade', 2: 'rise', 42: 'rise', 47: 'rise', 22: 'wipe', 53: 'zoom', 23: 'zoom', 21: 'wipe', 16: 'wipe', 12: 'wipe', 26: 'zoom', 31: 'zoom'}

def builds_of(root):
    """Click-by-click entrance animations: {shape id: (step, effect)}."""
    out, step = {}, 0
    if root is None:
        return out, 0
    timing = root.find('p:timing', NS)
    if timing is None:
        return out, 0
    for ctn in timing.iter('{%s}cTn' % NS['p']):
        if ctn.get('presetClass') != 'entr':
            continue
        node = ctn.get('nodeType')
        if node == 'clickEffect' or (node in ('withEffect', 'afterEffect') and step == 0):
            step += 1
        tgt = ctn.find('.//p:spTgt', NS)
        if tgt is not None and tgt.get('spid') not in out:
            out[tgt.get('spid')] = (step, EFFECTS.get(int(ctn.get('presetID', '10') or 10), 'fade'))
    return out, step

def mark_builds(items, builds):
    for it in items:
        if it.get('id') in builds:
            it['build_step'], it['build_effect'] = builds[it['id']]
        if 'children' in it:
            mark_builds(it['children'], builds)

def notes_of(pkg, part):
    n = pkg.rel_of_type(part, 'notesSlide')
    root = pkg.xml(n) if n else None
    if root is None:
        return ''
    for sp in root.iter('{%s}sp' % NS['p']):
        k = ph_key(sp)
        if k and k[0] == 'body':
            return '\n'.join(''.join(t.text or '' for t in p.iter('{%s}t' % NS['a'])) for p in sp.findall('.//a:p', NS)).strip()
    return ''

def text_styles(ctx, master):
    out = {}
    if master is None:
        return out
    tx = master.find('p:txStyles', NS)
    if tx is None:
        return out
    for kind in ('titleStyle', 'bodyStyle'):
        st = tx.find('p:' + kind, NS)
        if st is None:
            continue
        levels = []
        for lvl in list(st)[:3]:
            d = lvl.find('a:defRPr', NS)
            if d is None:
                continue
            e = {}
            if d.get('sz'):
                e['size_pt'] = int(d.get('sz')) / 100
                e['size_px'] = round(e['size_pt'] * 12700 * ctx.scale, 1)
            if d.get('b') == '1': e['bold'] = True
            c = ctx.theme.color(d.find('a:solidFill', NS))
            if c: e['color'] = c
            lat = d.find('a:latin', NS)
            if lat is not None: e['font'] = ctx.theme.font(lat.get('typeface'))
            levels.append(e)
        out[kind] = levels
    return out

# ---------------- summary ----------------
def para_text(p):
    return ''.join(r['text'] for r in p['runs']).strip()

def md_items(items, depth=0):
    lines = []
    pad = '  ' * depth
    for it in items:
        if it.get('hidden'):
            continue
        pos = ' @ %s,%s %sx%s' % (round(it['x']), round(it['y']), round(it['w']), round(it['h'])) if 'x' in it else ''
        tags = []
        if it.get('placeholder'): tags.append(it['placeholder'])
        if it.get('build_step'): tags.append('click %d %s' % (it['build_step'], it['build_effect']))
        if it.get('fill') and it['fill'] != 'none': tags.append('fill ' + it['fill'])
        if it.get('rotation_deg'): tags.append('rot %s' % it['rotation_deg'])
        head = '%s- %s%s%s' % (pad, it['kind'], pos, (' (' + ', '.join(tags) + ')') if tags else '')
        if it.get('image'): head += ' image ' + it['image']
        lines.append(head)
        for p in it.get('paragraphs', []):
            t = para_text(p)
            if not t:
                continue
            first = next((r for r in p['runs'] if r.get('text', '').strip()), {})
            style = ', '.join(x for x in [('%spt' % first['size_pt']) if first.get('size_pt') else '', first.get('font', ''), first.get('color', ''), 'bold' if first.get('bold') else ''] if x)
            lines.append('%s    %s%s%s' % (pad, '  ' * p['level'], '• ' if p.get('bullet') not in (None, 'none') else '', t) + (' [%s]' % style if style else ''))
        if it.get('rows'):
            for r in it['rows'][:12]:
                lines.append('%s    | %s |' % (pad, ' | '.join(r)))
        if it.get('chart'):
            for c in it['chart'].get('charts', []):
                for s in c['series']:
                    lines.append('%s    %s %s: %s' % (pad, c['type'], s['name'], ', '.join('%s=%s' % kv for kv in zip(s['categories'] or range(1, 99), s['values']))))
        if it.get('children'):
            lines += md_items(it['children'], depth + 1)
    return lines

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pptx'); ap.add_argument('out'); ap.add_argument('--width', type=int, default=1920)
    a = ap.parse_args()
    pkg = Pkg(a.pptx)
    pres = pkg.xml('ppt/presentation.xml')
    if pres is None:
        sys.exit('Not a PowerPoint file: ppt/presentation.xml is missing.')
    sz = pres.find('p:sldSz', NS)
    cx, cy = int(sz.get('cx')), int(sz.get('cy'))
    scale = a.width / cx
    height = round(cy * scale)
    os.makedirs(a.out, exist_ok=True)
    media_dir = os.path.join(a.out, 'media')
    if os.path.isdir(media_dir):
        shutil.rmtree(media_dir)
    prels = pkg.rels('ppt/presentation.xml')
    slide_parts = [prels[s.get(R_ID)][1] for s in pres.findall('p:sldIdLst/p:sldId', NS) if s.get(R_ID) in prels]

    first_master = None
    slides, media_map = [], {}
    for i, part in enumerate(slide_parts, 1):
        root = pkg.xml(part)
        lay_part = pkg.rel_of_type(part, 'slideLayout')
        layout = pkg.xml(lay_part) if lay_part else None
        mas_part = pkg.rel_of_type(lay_part, 'slideMaster') if lay_part else None
        master = pkg.xml(mas_part) if mas_part else None
        theme_part = pkg.rel_of_type(mas_part, 'theme') if mas_part else None
        clrmap = {}
        cm = master.find('p:clrMap', NS) if master is not None else None
        if cm is not None: clrmap = dict(cm.attrib)
        theme = Theme(pkg.xml(theme_part) if theme_part else None, clrmap)
        ctx = Ctx(pkg, theme, scale, media_dir, media_map)
        ctx.part = part
        ctx.bg_part_for = {id(root): part, id(layout): lay_part, id(master): mas_part}
        if first_master is None:
            first_master = (ctx, master, theme)
        tree = root.find('p:cSld/p:spTree', NS)
        items = shapes(ctx, tree, part, layout, master)
        builds, nsteps = builds_of(root)
        mark_builds(items, builds)
        # pictures and shapes drawn by the layout (logos, bars) also appear on the slide
        lay_items = []
        if layout is not None and layout.find('p:cSld', NS) is not None and root.get('showMasterSp') != '0':
            ctx.part = lay_part
            lay_items = [x for x in shapes(ctx, layout.find('p:cSld/p:spTree', NS), lay_part, None, master) if not x.get('placeholder')]
            ctx.part = part
        title = ''
        for it in items:
            if it.get('placeholder') in ('title', 'ctrTitle') and it.get('paragraphs'):
                title = ' '.join(para_text(p) for p in it['paragraphs'])
                break
        slides.append({
            'n': i, 'title': title, 'hidden': root.get('show') == '0',
            'layout': (layout.find('p:cSld', NS).get('name') if layout is not None and layout.find('p:cSld', NS) is not None else None),
            'background': background(ctx, root, layout, master),
            'transition': transition_of(root), 'build_steps': nsteps,
            'layout_shapes': lay_items, 'shapes': items, 'notes': notes_of(pkg, part),
        })

    ctx0, master0, theme0 = first_master if first_master else (None, None, Theme(None, {}))
    data = {'source': os.path.basename(a.pptx), 'width': a.width, 'height': height,
            'aspect': '%d:%d' % ((16, 9) if abs(cx / cy - 16 / 9) < .01 else (4, 3) if abs(cx / cy - 4 / 3) < .01 else (cx, cy)),
            'theme': {'colors': theme0.colors, 'fonts': theme0.fonts, 'text_styles': text_styles(ctx0, master0) if ctx0 else {}},
            'slides': slides}
    with open(os.path.join(a.out, 'outline.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=1, ensure_ascii=False)

    md = ['# %s' % data['source'], '',
          'Deck size: %dx%d px (%s). Positions below are x,y widthxheight in those px.' % (a.width, height, data['aspect']), '',
          '## Theme', '', 'Colours: ' + ', '.join('%s %s' % kv for kv in theme0.colors.items()),
          'Fonts: headings %s, body %s' % (theme0.fonts.get('majorFont'), theme0.fonts.get('minorFont'))]
    for k, lv in data['theme']['text_styles'].items():
        md.append('%s: %s' % (k, '; '.join(', '.join('%s=%s' % kv for kv in e.items()) for e in lv)))
    for s in slides:
        md += ['', '## Slide %d%s%s' % (s['n'], (': ' + s['title']) if s['title'] else '', ' (hidden)' if s['hidden'] else '')]
        meta = []
        if s['layout']: meta.append('layout "%s"' % s['layout'])
        if s['background']: meta.append('background ' + ', '.join('%s %s' % kv for kv in s['background'].items()))
        if s['transition']: meta.append('transition %s -> data-transition="%s" %dms' % (s['transition']['source'], s['transition']['labdeck'], s['transition']['duration_ms']))
        if s['build_steps']: meta.append('%d click builds' % s['build_steps'])
        if meta: md.append('; '.join(meta))
        if s['layout_shapes']:
            md.append('From the layout:')
            md += md_items(s['layout_shapes'])
        md += md_items(s['shapes'])
        if s['notes']:
            md.append('Notes: ' + s['notes'].replace('\n', ' / '))
    with open(os.path.join(a.out, 'outline.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md) + '\n')
    print('%d slides, %dx%d px, %d pictures -> %s' % (len(slides), a.width, height, len(media_map), a.out))

if __name__ == '__main__':
    main()
