#!/usr/bin/env python3
"""Make a picture of every original slide (slide-01.png, ...), to compare the web deck against.

Usage:
  python3 render_slides.py SOURCE OUT_DIR [--width 1920]

SOURCE can be .pptx, .ppt, .key, .odp or .pdf. The script tries, in order:
  1. a PDF as given
  2. LibreOffice (soffice), if installed
  3. on a Mac: PowerPoint, then Keynote (they open briefly and close again)
and then turns the PDF into pictures with pdftoppm (poppler) or, on a Mac, the built-in PDFKit.
If nothing works it says so: then export a PDF from the presentation app (File > Export > PDF)
and run this again on the PDF.
"""
import argparse, glob, os, shutil, subprocess, sys, tempfile

SWIFT = r'''
import AppKit
import PDFKit
let a = CommandLine.arguments
guard let doc = PDFDocument(url: URL(fileURLWithPath: a[1])) else { print("cannot open PDF"); exit(1) }
let width = CGFloat(Double(a[3]) ?? 1920)
for i in 0..<doc.pageCount {
  guard let page = doc.page(at: i) else { continue }
  let box = page.bounds(for: .mediaBox)
  let s = width / box.width
  let w = Int(box.width * s), h = Int(box.height * s)
  guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { continue }
  NSGraphicsContext.saveGraphicsState()
  let ctx = NSGraphicsContext(bitmapImageRep: rep)!
  NSGraphicsContext.current = ctx
  ctx.cgContext.setFillColor(NSColor.white.cgColor)
  ctx.cgContext.fill(CGRect(x: 0, y: 0, width: w, height: h))
  ctx.cgContext.scaleBy(x: s, y: s)
  page.draw(with: .mediaBox, to: ctx.cgContext)
  NSGraphicsContext.restoreGraphicsState()
  let png = rep.representation(using: .png, properties: [:])!
  try! png.write(to: URL(fileURLWithPath: String(format: "%@/slide-%02d.png", a[2], i + 1)))
}
print(doc.pageCount)
'''

def run(cmd, timeout=240):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return subprocess.CompletedProcess(cmd, 1, '', str(e))

def osa(script, timeout=300):
    return run(['osascript', '-e', script], timeout=timeout)

def to_pdf(src, tmp):
    ext = os.path.splitext(src)[1].lower()
    if ext == '.pdf':
        return src, 'the PDF itself'
    soffice = shutil.which('soffice') or shutil.which('libreoffice') or ('/Applications/LibreOffice.app/Contents/MacOS/soffice' if os.path.exists('/Applications/LibreOffice.app/Contents/MacOS/soffice') else None)
    if soffice:
        r = run([soffice, '--headless', '--convert-to', 'pdf', '--outdir', tmp, src])
        pdf = os.path.join(tmp, os.path.splitext(os.path.basename(src))[0] + '.pdf')
        if os.path.exists(pdf):
            return pdf, 'LibreOffice'
    if sys.platform == 'darwin':
        pdf = os.path.join(tmp, 'slides.pdf')
        q = lambda p: p.replace('\\', '\\\\').replace('"', '\\"')
        if ext in ('.pptx', '.ppt') and os.path.exists('/Applications/Microsoft PowerPoint.app'):
            osa(f'''tell application "Microsoft PowerPoint"
  open POSIX file "{q(src)}"
  set p to active presentation
  save p in POSIX file "{q(pdf)}" as save as PDF
  close p saving no
end tell''', timeout=120)       # PowerPoint may sit on a "Grant File Access" dialog: do not wait 5 minutes
            if os.path.exists(pdf):
                return pdf, 'PowerPoint'
            print('PowerPoint did not export (it may be waiting on a "Grant File Access" dialog); trying Keynote.', file=sys.stderr)
        if os.path.exists('/Applications/Keynote.app'):
            osa(f'''tell application "Keynote"
  set d to open POSIX file "{q(src)}"
  export d to POSIX file "{q(pdf)}" as PDF
  close d saving no
end tell''')
            if os.path.exists(pdf):
                return pdf, 'Keynote'
    return None, None

def to_png(pdf, out, width):
    if shutil.which('pdftoppm'):
        r = run(['pdftoppm', '-png', '-scale-to-x', str(width), '-scale-to-y', '-1', pdf, os.path.join(out, 'slide')])
        made = sorted(glob.glob(os.path.join(out, 'slide-*.png')))
        if made:
            for f in made:     # pdftoppm numbers as slide-1 or slide-01 depending on page count
                n = int(os.path.basename(f)[6:-4])
                os.replace(f, os.path.join(out, 'slide-%02d.png' % n))
            return 'pdftoppm'
    if sys.platform == 'darwin' and shutil.which('swift'):
        with tempfile.TemporaryDirectory() as t:
            sw = os.path.join(t, 'render.swift')
            open(sw, 'w').write(SWIFT)
            r = run(['swift', sw, pdf, out, str(width)], timeout=600)
        if glob.glob(os.path.join(out, 'slide-*.png')):
            return 'PDFKit'
    return None

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('source'); ap.add_argument('out'); ap.add_argument('--width', type=int, default=1920)
    a = ap.parse_args()
    src, out = os.path.abspath(a.source), os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(out, 'slide-*.png')):
        os.remove(f)
    with tempfile.TemporaryDirectory() as tmp:
        pdf, how = to_pdf(src, tmp)
        if not pdf:
            sys.exit('Could not turn the presentation into a PDF here (no LibreOffice, PowerPoint or Keynote that answered).\n'
                     'Export a PDF from the presentation app (File > Export > PDF) and run this script on the PDF.')
        if pdf != src:
            shutil.copy(pdf, os.path.join(out, 'slides.pdf'))
        tool = to_png(pdf, out, a.width)
    if not tool:
        sys.exit('Made a PDF (%s) but could not turn it into pictures: install poppler (pdftoppm), or run on a Mac.' % os.path.join(out, 'slides.pdf'))
    n = len(glob.glob(os.path.join(out, 'slide-*.png')))
    print('%d slide pictures in %s (PDF from %s, pictures by %s)' % (n, out, how, tool))

if __name__ == '__main__':
    main()
