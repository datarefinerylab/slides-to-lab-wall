# Writing a LabDeck

A deck is one `index.html` in its own folder, next to the shared `labdeck/` engine folder:

```
slide-decks/
  index.html          talk list (also the wall's waiting page)
  labdeck/            engine: labdeck.js, labdeck.css, qrcode.js (never edit)
  my-talk/
    index.html        the deck
    assets/           pictures, fonts, cropped regions of the original
```

Start from `templates/deck.html` (`deckrepo.py setup` does this). It has the right `<head>`, theme block, config and script order.

## Page structure

```html
<link rel="stylesheet" href="../labdeck/labdeck.css">
<style> :root{ --ld-bg:…; } /* theme + slide styles */ </style>
<main id="slides">
  <section class="slide" data-section="Introduction" data-transition="fade">
    …slide content…
    <template class="wall">…what the six screens show…</template>
    <aside class="notes">Speaker notes</aside>
  </section>
  …
</main>
<script>window.LABDECK = { title:'…', width:1920, height:1080, home:'../', polls:{} };</script>
<script src="../labdeck/qrcode.js"></script>
<script src="../labdeck/labdeck.js"></script>
```

Rules:
- Slides are the direct `<section class="slide">` children of `<main id="slides">`, in presenting order.
- Each slide is a fixed stage of `width × height` deck pixels (default 1920×1080). The engine scales it to the window and letterboxes it. **Design in deck pixels.** Absolute positioning (`position:absolute; left:…px; top:…px; width:…px`) is fine and usually the most faithful way to copy a PowerPoint layout. The slide is `position:relative; overflow:hidden`.
- Only the shown slide is visible. Do not rely on scrolling.
- Keep everything self-contained: relative paths to `assets/`, Google Fonts or local `@font-face`, no build step, no frameworks.
- `<aside class="notes">` is never displayed.

## Config: `window.LABDECK`

| Key | Default | Meaning |
|---|---|---|
| `title`, `author`, `date` | page title, '', '' | Shown on the wall's brand screen and the phone page |
| `width`, `height` | 1920, 1080 | Design size of every slide (4:3 → 1440×1080) |
| `transition`, `duration` | `'fade'`, 600 | Default for slides without `data-transition` |
| `home` | `''` | Where the wall link points. Use `'../'` (the talk list) so one workstation link serves every talk |
| `polls` | `{}` | Audience questions (see `interactive.md`). Empty = plain deck: no QR, no phone page, no network for answers |
| `firebase` | `''` | Optional Realtime Database URL for big rooms |
| `relay` | `'https://ntfy.sh'` | Message relay for answers and wall sync |
| `wall` | see `wall.md` | Wall geometry, fixed wall code, logo |

## Slide attributes

| Attribute | On | Values |
|---|---|---|
| `data-transition` | slide | `fade` · `push` · `cover` (alias `slide`) · `uncover` · `wipe` · `zoom` · `morph` · `none` (alias `cut`) |
| `data-duration` | slide | ms, 50–4000 |
| `data-section` | slide | Section name; carries forward to later slides; shown on wall screen 1 |
| `data-title` | slide | Fallback title for the automatic wall view |
| `data-qr` | slide | `off` (no floating QR on this question slide), `left`, `top` (move it) |
| `data-step="N"` | any element | Appears on click N (several elements may share a number) |
| `data-build` | with data-step | `fade` (default) · `rise` · `zoom` · `wipe` · `appear` |
| `data-morph="name"` | element | With `morph`: elements with the same name on the two slides fly between positions |
| `data-noclick` | element | Clicking it does not advance the slide |
| `data-wall` | img / svg | Used as the picture in the automatic wall view |
| `data-wall-title` | element | Used as the title in the automatic wall view |
| `data-fit` | element with a fixed box | Text shrinks until it fits (useful for the wall) |

A slide's transition plays when you arrive **at** it. Going back plays it in reverse. When you go back into a slide, all its builds are already shown.

## Theme variables

Set these in `:root`. The engine's own pieces (QR card, results, phone page, wall chrome) use them, so they match the deck.

| Variable | Use |
|---|---|
| `--ld-bg`, `--ld-fg` | Background and text |
| `--ld-acc` | Accent: results bars, highlights, progress bar |
| `--ld-hot` | Second accent: newest words, leading answer |
| `--ld-font`, `--ld-font-display` | Body and heading fonts |
| `--ld-mono` | Code |
| `--ld-mute`, `--ld-line`, `--ld-panel` | Derived greys (override if needed) |
| `--ld-letterbox` | Colour around the stage when the window is not the deck's shape |
| `--ld-wall-bg` | Wall background (defaults to `--ld-bg`) |

Style slide content with your own classes, scoped under `.slide` where it matters. Wall content is **not** inside `.slide`, so give wall pieces their own classes (for example `.w-title`).

## Widgets (only with polls)

Empty elements the engine fills in. They work on slides and in wall templates.

| Element | Shows |
|---|---|
| `<div class="ld-poll" data-poll="id" data-parts="q opts count">` | The question, its options (or hint) and the live answer count; any subset of parts |
| `<div class="ld-results" data-poll="id" data-parts="n chart">` | Live bars (single/multi) or a word cloud (cloud). `data-max` = most words (40). `data-empty` = text before the first answer |
| `<span class="ld-count" data-poll="id">` | Number of answers |
| `<span class="ld-phones">` | Number of phones that joined |
| `<div class="ld-qr" data-caption="Scan to answer">` | QR code for the phone page. Give it a size, e.g. `width:320px` |

Size the widgets with CSS (`.slide .ld-results{position:absolute;left:…;width:…;height:…}`). The word cloud fills its box, so give it a height.

## URL options (for checking)

| Address | Shows |
|---|---|
| `…/my-talk/?s=5` | Start at slide 5 |
| `?static` | All builds shown, no transitions, no network (used by `snap.py`) |
| `?demo` | Demo answers on |
| `?print` | Every slide as a page; print to PDF |
| `?wall&s=5[&band][&demo][&step=1]` | Offline preview of slide 5's wall view (`band` = only the 3840×360 band) |

## Keys (presenter)

→ / Space / click right: next (builds included) · ← / click left: back · Home/End · number + Enter: go to slide ·
`F` full screen · `B` black · `W` wall on/off · `A` panel (wall link, phone link, export, demo) · `H` status chip · `M` calm motion ·
`Q` big QR and `D` demo answers (only with polls).
