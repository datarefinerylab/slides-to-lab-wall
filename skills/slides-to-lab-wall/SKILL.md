---
name: slides-to-lab-wall
description: Turn a presentation (PowerPoint, Keynote, PDF or Google Slides) into a web deck on GitHub Pages that looks like the original, with its transitions and builds, and drives the lab's six-screen display wall in sync while you present from a laptop. Audience questions answered on phones by QR code can be added on chosen slides. Use when someone wants their slides on the web or on the lab wall or display screens, wants slides synced to the lab workstation, or wants live polls or a QR code for questions in a talk.
---

# Slides to lab wall

You turn the user's presentation into a **LabDeck**. A LabDeck is one web page with three uses:

| Who opens it | Address | What it does |
|---|---|---|
| The presenter, on a laptop | `…/my-talk/` | The slides, matching the original's look, transitions and click builds |
| The lab workstation | `…/#w.<wall code>` | The six display screens (3840×1080 output; six 640×360 screens side by side in the middle band) show a matching view of each slide, in sync |
| The audience, by QR code (optional) | `…/my-talk/#j.<session>` | Phones answer the questions; results appear live on the slide and the wall |

The engine (`engine/`) does all of the navigation, sync, wall, phone, QR and results work. Never rewrite it. You only write the deck's content and styling: one `index.html` per talk, following `references/authoring.md`.

Paths such as `scripts/…`, `templates/…` and `references/…` are inside this skill's folder. Run the scripts by their full path. They need only Python 3.8+ (standard library), git, the GitHub CLI (`gh`) and Google Chrome.

## 1. Ask once, then work

Ask everything in **one** message (use the AskUserQuestion tool if you have it). Ask only what you cannot find out yourself, and leave out anything the user already said:

1. **Source**: the presentation file or link (.pptx, .key, .pdf, or a Google Slides link). Skip this if it was given.
2. **Where it goes**: default to the GitHub repository `<their GitHub login>/slide-decks`, with a folder named after the talk (for example `slide-decks/lab-meeting-may`). Run `gh api user --jq .login` first, so you can show the real default. If they already have a decks repository, offer that one.
3. **Look and transitions**: default to *"Match the original"*, which copies the original's colours, fonts, layout, transitions and click builds as closely as the web allows. The other option is *"Change something"*, followed by their description (for example "dark background", "no animations", "use the lab colours").
4. **Audience questions**: default to *"None"*. The other options are *"On slides I'll name"* (they say which slides, and what to ask or let you propose) and *"Suggest a few"* (you propose 2–3 questions at natural points, and they confirm).

Do not ask about anything else: not the wall layout, fonts, sizes, keys or hosting details. Use the defaults in this file and decide sensibly. If the GitHub CLI is not signed in (`gh auth status`), tell the user to run `gh auth login` and stop until they have.

## 2. Read the source

Work in a scratch folder (for example `./.labdeck-work/<slug>/`) that you do not publish.

- **PowerPoint (.pptx)**:
  ```bash
  python3 scripts/extract_pptx.py talk.pptx WORK/extract      # outline.md, outline.json, media/
  python3 scripts/render_slides.py talk.pptx WORK/original    # slide-01.png … (what it really looks like)
  ```
  Read `outline.md` first. Then look at every `original/slide-NN.png`. The pictures are the truth for the look; the outline is the truth for text, positions (already in deck pixels), colours, fonts, transitions, click builds and notes.
- **Keynote (.key)**: on a Mac, export it to .pptx with Keynote and continue as for PowerPoint:
  `osascript -e 'tell application "Keynote" to export (open POSIX file "/abs/talk.key") to POSIX file "/abs/talk.pptx" as Microsoft PowerPoint'`.
  If that fails, ask for a .pptx or PDF export.
- **PDF**: `render_slides.py talk.pdf WORK/original`, then rebuild from the pictures. Get the text with `pdftotext -layout` if it is installed; otherwise read it from the pictures. There are no transitions or builds: use the deck default (`fade`).
- **Google Slides**: download it with `curl -L "https://docs.google.com/presentation/d/<ID>/export/pptx" -o talk.pptx`. That only works when the file is shared as "anyone with the link"; otherwise ask the user for File → Download → PowerPoint. Then continue as for PowerPoint.

If `render_slides.py` cannot make pictures (no LibreOffice, PowerPoint or Keynote), ask the user once for a PDF export of the slides. You need the pictures to match the look.

## 3. Set up the deck folder

```bash
python3 scripts/deckrepo.py setup --repo OWNER/slide-decks --slug my-talk --title "My Talk" --clone ./slide-decks
```

This clones the repository, or creates it (public) if it does not exist yet. It also copies the engine into `labdeck/`, makes the talk list page, and starts `my-talk/index.html` from `templates/deck.html`. Copy the pictures you use from `WORK/extract/media/` into `my-talk/assets/`.

## 4. Build the slides

Follow `references/authoring.md` for the deck format and `references/style-matching.md` for matching the original. The essentials:

- Set `width`/`height` in `window.LABDECK` from the outline (1920×1080 for 16:9, 1440×1080 for 4:3).
- Put the theme in the `--ld-*` variables: background, text, accent, fonts. The engine's QR code, results, wall and phone pages take their colours from those variables, so everything matches.
- Use one `<section class="slide">` per visible slide, in order. Skip hidden slides unless the user wants them.
- **Match the original by default.** Place things where the outline says (absolute positions in deck px are fine and usually the most faithful). Use the same fonts (see the font table), sizes, colours, bullets, backgrounds and repeated layout elements (logos, bars, footers, slide numbers).
- Rebuild text, tables and simple charts as real HTML or SVG. They stay sharp and can animate. For things that cannot be rebuilt faithfully (SmartArt, complex diagrams, equations drawn as pictures, 3D), crop that region from `original/slide-NN.png` into `assets/` and place it as an image.
- **Transitions**: `data-transition` from the outline's `labdeck` value, plus `data-duration`. **Click builds**: `data-step="N"` and `data-build` from the outline. **Morph**: give matching elements on the two slides the same `data-morph` name.
- Keep speaker notes in `<aside class="notes">`.
- If the user asked for style changes, apply them on top of the matched deck, and only those changes.

## 5. Decide what the six screens show

Every slide gets a `<template class="wall">` that you write. The engine's automatic view is only a fallback. Follow `references/wall.md`: by default screen 1 shows progress and screen 6 shows the QR code (on question slides) or the talk title. Screens 2–5 (2560×360 together) carry the slide's main idea in large type: the title or key statement, the key number or picture, and builds in step with the slide. Never shrink a whole slide onto the wall. Reshape it for a very wide, very short display.

## 6. Audience questions (only if asked for)

Follow `references/interactive.md`. In short:
- Add each question to `polls` in `window.LABDECK` (`single`, `multi` or `cloud` for short words).
- Usually a question slide with `<div class="ld-poll" data-poll="id">` is followed by a results slide with `<div class="ld-results" data-poll="id">`, both styled like the rest of the deck.
- Question slides get a QR code automatically. All other slides stay exactly as in the original, with no QR code.
- A deck with no questions has no QR code, no phone page and no answer traffic at all.

## 7. Check it against the original

```bash
python3 scripts/snap.py ./slide-decks my-talk --ref WORK/original --out WORK/snaps
```

This takes a picture of every slide (all builds shown, demo answers on question slides) and every wall view, and makes `WORK/snaps/index.html` showing original | web | wall for each slide.

- **Look at every pair** and fix every difference you can see: position, size, line breaks, font, colour, missing elements, cropping. Repeat until they match.
- Then check the wall pictures. Text must be large and readable, nothing may be cut off, and each wall view must clearly belong to its slide.
- If you have a browser tool, also open the deck locally (`python3 -m http.server` in the clone). Click through it once to see the transitions and builds, and check the console for errors.

## 8. Publish

```bash
python3 scripts/deckrepo.py publish --clone ./slide-decks --slug my-talk
```

This commits, pushes, turns on GitHub Pages (from `main`, root folder), waits until the deck is live and prints its address. If Pages cannot be turned on (for example a private repository on a free account), pass on the message it prints.

## 9. Tell the user how to present

End with this, filled in, in plain words:

- **Your deck:** `https://OWNER.github.io/slide-decks/my-talk/`. Open it on the laptop and press `F` for full screen. `→`/`Space` moves forward (builds included), `←` goes back.
- **Lab wall, one time only:** on the laptop, press `W` (the wall turns on), then `A` → *Lab wall* → *Copy wall link*. On the lab workstation, open that link in Chrome and press `F11`, then bookmark it. It stays the same for all future talks from this laptop browser and switches to whichever deck you present. Press `C` on the wall to check the six screens line up.
- **Audience questions** (only if there are any): the QR code appears by itself on question slides, and `Q` shows it full screen. Press `D` to rehearse with demo answers. After the talk, use `A` → *Export CSV*.
- **To change something** (a slide, the style, a transition, the wall view): ask, and you will update and republish.

## Defaults

- Deck size 1920×1080 (16:9). Engine defaults for everything else.
- The wall geometry comes from the Lab Display Composer: 3840×1080 output, six 640×360 screens at y = 360–720. If the lab's screens change, set `wall: { … }` in `LABDECK` (see `references/wall.md`).
- Sync goes through the public ntfy.sh relay, with no server to run. Both computers only need internet, not the same network. For rooms with more than about 25 phones, see the Firebase section in `references/interactive.md`.
