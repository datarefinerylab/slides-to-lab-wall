# The lab wall

## Geometry

The workstation drives one 3840×1080 output, set up by the Lab Display Composer. Only the middle band is visible: six screens of 640×360 side by side at y = 360–720. Together they form a **3840×360** strip, about 10.7:1.

```
x:   0     640    1280   1920   2560   3200   3840
     ┌──────┬──────┬──────┬──────┬──────┬──────┐  y=360
     │  1   │  2   │  3   │  4   │  5   │  6   │
     └──────┴──────┴──────┴──────┴──────┴──────┘  y=720
```

Each screen has its own bezel, so text never crosses a gap between screens unless it is very large. Keep separate items inside separate screens, or span them generously (2–5 = 2560 px).

If the lab changes its screens, override the geometry in the deck config:
```js
wall: { width:3840, height:1080, bandY:360, bandHeight:360, screens:6, screenWidth:640 }
```
On the wall, press `C` to show screen numbers and outlines and check the alignment.

## What each slide shows

Each slide may hold a `<template class="wall">`. Its child elements are placed on screen ranges:

```html
<template class="wall">
  <div data-screens="2-5"><div class="w-kick">Results</div><div class="w-title" data-fit>Rooms found correctly</div></div>
</template>
```

- `data-screens`: `"3"`, `"2-5"`, `"1-6"` / `"all"`. Default `2-5`.
- Each placed element is a 360 px tall flex column (centered vertically, padding 30px 48px) at `left = (a-1)×640`, `width = (b-a+1)×640`. Override with inline style or classes.
- `data-step="N"` and `data-build` work in wall templates too, in step with the slide's click builds.
- `data-fit` on a text element with a fixed height or max-height shrinks it until it fits.
- `data-bg="…"` on the `<template>` sets the whole band's background for that slide.
- Widgets (`.ld-results`, `.ld-poll`, `.ld-count`, `.ld-qr`, `.ld-phones`) work on the wall and update live.
- Wall pieces are not inside `.slide`, so style them with their own classes (`.w-title`, `.w-kick` …) in the deck's `<style>`.

**Screens not covered by the template** are filled by the engine:
- **Screen 1**: progress. Section name, `07 / 18`, progress bar.
- **Screen 6**: the join QR code and phone count on question slides; otherwise the talk title (and `wall.logo` if set).

Cover screen 1 or 6 in the template (for example `data-screens="1-6"`) to use them for content instead.

**No template**: an automatic view is built from the slide. It uses the section, the title (`[data-wall-title]` or the first h1/h2/h3), the first paragraph or bullet, and a `[data-wall]` image or svg if there is one. Question and results slides show their widget. This is a fallback only. Write a template for every slide.

## Designing for 3840×360

The wall is very wide and very short, and people look at it from across the room. Do not shrink the slide onto it. Reshape the idea:

| Slide | Wall (screens 2–5 unless noted) |
|---|---|
| Title slide | Kicker (event or section) plus the title, about 80–100 px |
| Bullets | 3–4 bullets as side-by-side columns (one per screen), 34–40 px, using the same builds |
| One big statement or quote | The statement, large, across `1-6` with a strong background |
| Chart | The chart redrawn as simple bars or columns across 2–3 screens, plus the takeaway sentence on the others |
| Picture, diagram or photo | The picture on 1–2 screens (cropped to a wide shape), with the title beside it |
| Table | The 2–4 key numbers as big figures, one per screen |
| Section divider | The section name, large, across `1-6` |
| Question slide | `.ld-poll` (question and options) on 2–5. The QR code is on 6 automatically |
| Results slide | The question (small) plus `.ld-results` on 2–5 |

Sizes that read well: kicker 22–26 px uppercase, title 72–100 px, body 32–40 px, big figures 120–160 px. Keep the deck's colours and fonts so the wall clearly belongs to the slides.

## Checking

`snap.py` makes `wall-NN.png` (3840×360) for every slide with all builds shown. Look at each one. Nothing may be cut off, no text may be smaller than about 28 px, and no single word may sit right on a screen gap. You can also open `my-talk/?wall&s=N` locally and use ← / → to step through.

## How sync works (for troubleshooting)

- The presenter's laptop keeps a **wall code**: a random 8 characters, stored in the browser and shared by every deck on the same site. The wall link is `<site>/#w.<code>`.
- With the wall **on** (`W`), every slide or build change is posted to the relay topic `labdeck-wall-<code>` (ntfy.sh by default).
- The workstation page listens to that topic. When the message comes from another deck on the same site, it switches to that deck by itself. With no deck presenting, it shows a "Ready for the next talk" page.
- Both computers need internet access, but they do not need the same network. Messages carry only the slide number, the build step, the deck address and the question session id.
- A fixed code for a lab (so any laptop drives the same wall link): `wall: { code: 'ourlab2026' }` in each deck. Anyone who knows the code can move the wall, so use something not guessable.
- Optional: `wall: { firebase: 'https://….firebasedatabase.app' }` uses a Firebase database instead of ntfy for the wall.

Workstation setup is once: open the wall link in Chrome, press `F11` (or click once for full screen), bookmark it. If it shows the wrong part of the output, press `C`.
