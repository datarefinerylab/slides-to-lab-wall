# Slides to lab wall

A Claude Code skill that takes your presentation and puts it on the lab's display wall.

```
your slides  ──►  web deck  ──►  GitHub Pages  ──►  laptop + lab wall in sync
(.pptx .key .pdf               (looks like the       (phones can answer
 Google Slides)                 original)             questions, if you want)
```

You give Claude your slides and answer up to four short questions. Claude then:

1. rebuilds the slides as a web page that matches the original (colours, fonts, layout, transitions, click builds),
2. designs a matching view of every slide for the six screens of the lab wall,
3. adds audience questions with a QR code, only if you want them,
4. checks every slide against the original, side by side,
5. publishes the deck on GitHub Pages and gives you the link.

You present from your laptop. The workstation driving the wall follows along: same slide, same click, live.

**Live examples:** [datarefinerylab.github.io/slides-to-lab-wall/examples](https://datarefinerylab.github.io/slides-to-lab-wall/examples/). One talk is plain, and one has audience questions. Open a deck and press `A` for the setup panel. Add `?wall&s=3` to a deck address to preview what the wall shows for slide 3.

---

## Install

You need [Claude Code](https://claude.com/claude-code), [git](https://git-scm.com), the [GitHub CLI](https://cli.github.com) signed in (`gh auth login`), Python 3 and Google Chrome.

**As a plugin** (recommended, it stays up to date). Type in Claude Code:

```
/plugin marketplace add datarefinerylab/slides-to-lab-wall
/plugin install slides-to-lab-wall@datarefinerylab
```

**Or copy the skill by hand:**

```bash
git clone https://github.com/datarefinerylab/slides-to-lab-wall
```

```bash
sh slides-to-lab-wall/install.sh
```

Start a new Claude Code session afterwards.

## Use

Say what you want, with your file:

> Put `~/Desktop/group-meeting.pptx` on the lab wall.

Claude asks, all at once:

| Question | Default |
|---|---|
| **Which slides?** A .pptx, .key, .pdf or Google Slides link (skipped if you already gave it) | — |
| **Where should it go?** | Your GitHub repo `slide-decks`, one folder per talk |
| **Look and transitions?** | **Match the original.** Or describe changes: "dark theme", "no animations", "our lab colours"… |
| **Audience questions?** | **None.** Or name the slides and questions, or let Claude suggest a few |

Then it works on its own and finishes with your deck link and what to do in the room. To change anything later, just ask ("make slide 4's chart bigger", "use push transitions", "add a question after the results"). Claude updates and republishes it.

## In the room

**On your laptop:** open your deck link and press `F` for full screen. `→` / `Space` / click goes forward (including builds), `←` goes back.

**On the lab workstation, once:**

1. On your laptop, press `W` to turn the wall on.
2. Press `A` → **Lab wall** → **Copy wall link**.
3. On the workstation, open that link in Chrome, press `F11`, and bookmark it.

That's all. The link stays the same for every talk you give from that laptop browser. The wall switches by itself to whichever deck you present, and shows "Ready for the next talk" in between. Press `C` on the wall to check that the six screens line up.

**With audience questions:** the QR code appears by itself on question slides (and on the wall's sixth screen). People scan it and answer on their phones; results appear live on the slide and on the wall. `Q` shows the QR code full screen. `D` rehearses with made-up answers. After the talk, use `A` → **Export CSV**. Slides without questions show no QR code at all.

### Keys

| Key | |
|---|---|
| `→` `Space` `←` | next / back (builds included) |
| number + `Enter` | go to that slide |
| `F` | full screen |
| `B` | black screen |
| `W` | lab wall on / off |
| `A` | setup panel: wall link, phone link, export, demo answers |
| `H` | hide the status chip |
| `M` | calm motion (no transitions) |
| `Q` / `D` | big QR code / demo answers (decks with questions only) |
| on the wall: `C` / `F` | screen outlines / full screen |

## The lab wall

The workstation drives one 3840×1080 output. Six 640×360 screens sit side by side in its middle band (y = 360–720). That strip is very wide and short, so the wall does not get a shrunken copy of the slide. Each slide gets its own wide view in the deck's style:

- **Screen 1:** progress (section, slide 07 / 18, a bar)
- **Screens 2–5:** the slide's main point in big type: title, key number, chart or picture, building in step with your clicks
- **Screen 6:** the QR code on question slides, otherwise the talk title

If the lab's screens change, the geometry is one setting (see [`references/wall.md`](skills/slides-to-lab-wall/references/wall.md)).

## How it works

- **One engine, many talks.** All the behaviour lives in a small script (`labdeck/`, about 1,000 lines, no dependencies) shared by every talk. Each talk is one `index.html` with its slides. Your repository looks like this:
  ```
  slide-decks/
    index.html       list of talks (also the wall's waiting page)
    labdeck/         the engine
    group-meeting/   one folder per talk
  ```
- **Sync without a server.** When the wall is on, your laptop posts the current slide and click to a free public message relay ([ntfy.sh](https://ntfy.sh)) under a random code. The workstation listens to the same code. The two computers only need internet, not the same network. Answers from phones travel the same way. Rooms with more than about 25 phones can use a free Firebase database instead (see [`references/interactive.md`](skills/slides-to-lab-wall/references/interactive.md)).
- **Privacy.** Messages contain only the slide number, the click step, the deck address, and anonymous answers. GitHub Pages sites are public, so don't publish confidential slides.

## What's in this repository

```
skills/slides-to-lab-wall/
  SKILL.md                 what Claude follows
  engine/                  labdeck.js, labdeck.css, qrcode.js
  templates/               starting deck and talk list
  scripts/
    extract_pptx.py        reads a .pptx: text, positions, colours, fonts, transitions, builds, notes, pictures
    render_slides.py       pictures of the original slides (LibreOffice, PowerPoint or Keynote)
    snap.py                pictures of the web deck and wall views, side by side with the original
    deckrepo.py            set up the GitHub repo, publish to Pages
  references/              authoring, wall, interactive, style matching, publishing
examples/                  two example talks (also live on GitHub Pages)
```

The scripts use only the Python standard library. You can also use them without Claude, for example `python3 skills/slides-to-lab-wall/scripts/snap.py examples plain`.

## Troubleshooting

| | |
|---|---|
| The wall doesn't move | Press `W` on the laptop: the status chip should say "Wall on". Both computers need internet |
| The wall shows someone else's talk | Another laptop with the same wall link is presenting. They press `W` to stop |
| Phones can't answer | Present from the published link, not a local file |
| New laptop | It gets a new wall link: copy it to the workstation again (`A` → Lab wall) |
| The deck isn't live yet | The first publish to GitHub Pages can take a few minutes |
| More | [`references/publishing.md`](skills/slides-to-lab-wall/references/publishing.md) |

## Licence

MIT. Includes the QR code generator by Kazuhiko Arase (MIT).
