# Matching the original

By default the web deck should be hard to tell apart from the original when shown full screen. The slide pictures (`original/slide-NN.png`) decide what it should look like. The outline (`outline.md` / `outline.json` from `extract_pptx.py`) gives exact values.

## Reading the outline

- `outline.md` starts with the deck size, theme colours and fonts, then one block per slide. Each block lists the layout name, background, transition, number of click builds, every shape with `@ x,y wxh` in **deck px**, its text with size, font, colour and bullets, tables, chart data, pictures (`media/…`) and notes.
- `outline.json` has everything in full: text runs, alignment, line spacing, fills, lines, crop, rotation, group children, `build_step`/`build_effect`, `transition.labdeck`/`duration_ms`.
- Placeholder positions are already resolved from the layout and master, and text sizes are given in pt and in deck px. Use the px values.
- Shapes from the **layout and master** (logos, bars, footers) are listed under each slide's layout. Put repeated pieces in a shared CSS class or a small template, not copied by hand onto every slide with drift.

## Mapping to HTML and CSS

| PowerPoint | Web |
|---|---|
| Slide size 13.33×7.5 in (16:9) / 10×7.5 (4:3) | `width:1920,height:1080` / `width:1440,height:1080` |
| Shape at x,y w×h | `position:absolute;left:Xpx;top:Ypx;width:Wpx;height:Hpx` |
| Text box anchor (top/middle/bottom) | `display:flex;flex-direction:column;justify-content:flex-start/center/flex-end` |
| Body inset (0.1 in / 0.05 in default) | `padding:7px 14px` at 1920 wide (scale 1920/12192000 EMU) |
| Font size N pt | the outline's px value (pt × 2.0 at 1920 wide for 16:9) |
| Line spacing 90% | `line-height:.9` (PowerPoint 100% ≈ CSS 1.2 for most fonts; compare against the picture) |
| Space before/after | `margin-top` / `margin-bottom` in px |
| Bullets and levels | `<ul>` with custom `::before` markers matching the bullet character and colour; level indent from the outline |
| Theme colours | `--ld-*` variables plus your own (`--navy`, `--teal` …) in `:root` |
| Gradient fill | `linear-gradient(…)` with the stops from the outline |
| Picture with crop | `<img>` in a box with `overflow:hidden`, or `object-fit:cover` + `object-position` |
| Rounded rectangle, line, arrow | `div` with `border-radius`, or inline SVG |
| Table | `<table>` with the same column widths, borders and fills |
| Simple chart (bar/column/line/pie) | Inline SVG rebuilt from the chart data (sharp and can animate). Match colours, axes and labels |
| SmartArt, complex diagrams, equations, 3D, WordArt | A crop of `original/slide-NN.png` placed as an image at the same position |
| Video/audio | `<video>`/`<audio>` with the file from `media/` (clicks on them do not advance) |
| Speaker notes | `<aside class="notes">` |
| Slide number / footer / date | Text in the same place, filled with the slide number |

When something is too hard to rebuild faithfully, a cropped picture is better than a rough copy. Never place the **whole** slide picture as the slide: text must stay real text.

## Fonts

Use the original font when it is available on the web. Otherwise use the closest metric-compatible one, so line breaks match.

| Original | Web |
|---|---|
| Calibri | `"Calibri","Carlito"` (Carlito on Google Fonts is metric-compatible) |
| Cambria | `"Cambria","Caladea"` |
| Arial / Helvetica | `Arial,"Liberation Sans","Arimo",sans-serif` |
| Times New Roman | `"Times New Roman","Tinos",serif` |
| Courier New | `"Courier New","Cousine",monospace` |
| Segoe UI | `"Segoe UI","Selawik","Open Sans",sans-serif` |
| Aptos (new Office default) | `"Aptos","Inter",sans-serif`, then check the line breaks |
| Century Gothic | `"Century Gothic","Questrial",sans-serif` |
| Gill Sans | `"Gill Sans","Gillius ADF","Lato",sans-serif` |
| Helvetica Neue (Keynote) | `"Helvetica Neue","Inter",Arial,sans-serif` |
| Any Google font (Roboto, Lato, Montserrat, Open Sans, Source Sans …) | The same from Google Fonts |

If the font files are in the presentation or provided by the user, and their licence allows web use, put them in `assets/fonts/` with `@font-face`. After a font change, compare line breaks against the pictures again.

## Transitions

`extract_pptx.py` already maps each transition to a LabDeck one (`transition.labdeck`) and gives its duration. Put it on the slide that the transition leads **into**:

| PowerPoint / Keynote | `data-transition` |
|---|---|
| Fade, Dissolve, Reveal, Flash | `fade` |
| Push, Pan, Conveyor, Gallery, Switch, Flip | `push` |
| Cover, Slide in | `cover` |
| Uncover, Pull, Peel off, Page curl | `uncover` |
| Wipe, Split, Wheel, Blinds, Doors, Curtains | `wipe` |
| Zoom, Shape (circle/diamond), Vortex, Window | `zoom` |
| Morph (PowerPoint) / Magic Move (Keynote) | `morph`, with matching `data-morph` names on the two slides |
| Cut / none | `none` |

The deck-wide default (`transition` in `LABDECK`) should be the most common transition in the original. Then only the exceptions need `data-transition`.

## Click builds

`build_step` is the click number and `build_effect` the closest LabDeck build:

| PowerPoint entrance | `data-build` |
|---|---|
| Appear | `appear` |
| Fade | `fade` |
| Fly in, Float in, Rise up | `rise` |
| Wipe, Split, Wheel | `wipe` |
| Zoom, Grow/Turn, Swivel | `zoom` |

- "With previous" and "after previous" effects share the click number of the click they follow.
- Builds on single paragraphs ("by paragraph"): put `data-step` on each `<li>`, numbered in order.
- Emphasis and exit effects do not map. Show the end state, or split the slide in two if the exit matters to the story.
- Add the same `data-step` numbers to the matching parts of the slide's wall template, so the wall builds with the slide.

## When the user asks for changes

Apply them on top of the matched deck:
- "No animations / simpler": `transition:'fade'` (or `'none'`) for all slides, keep builds only where they carry meaning, or remove them.
- "Dark theme", "our lab colours": change the `:root` variables and the colour classes, then check the contrast of every slide in the snaps.
- "Bigger text": scale the type, re-check that nothing overflows.
- "Different transitions": change `transition` / `data-transition`.

Say in one line what you changed when you report back.
