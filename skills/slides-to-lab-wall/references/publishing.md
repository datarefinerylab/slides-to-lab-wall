# Publishing on GitHub Pages

## The repository

One repository holds all of a person's (or a group's) talks. The default is `<login>/slide-decks`:

```
index.html     talk list, rebuilt by deckrepo.py; also the wall's waiting page
labdeck/       the engine, refreshed from the skill on every publish
.nojekyll      tells GitHub Pages to serve files as they are
my-talk/       one folder per talk (lower-case, dashes)
```

The wall link points at the site root (`home:'../'` in each deck), so one bookmarked link on the workstation serves every talk in the repository.

`deckrepo.py publish` does commit → push → turn on Pages (branch `main`, folder `/`) → wait for the build → check the deck answers 200. It prints:
```json
{ "site": "https://owner.github.io/slide-decks/", "deck": "https://owner.github.io/slide-decks/my-talk/", "phones": false }
```

An organisation repository works the same (`--repo datarefinerylab/talks`), if the user may create repositories and Pages there.

## Updating a talk

Edit `my-talk/index.html`, run `snap.py` again, then `deckrepo.py publish --clone … --slug my-talk --message "Fix slide 4"`. Pages usually updates within a minute. Browsers may cache for a few minutes, so a reload with Shift helps.

## Private repositories

GitHub Pages from a private repository needs a paid plan (Pro, Team or Enterprise). On a free account, `publish` stops with that message. Options: make the repository public, or use a paid organisation. The Pages site itself is always public, even from a private repository (except with Enterprise access control), so do not publish confidential slides.

## Troubleshooting

| Problem | Fix |
|---|---|
| `gh: not signed in` | `gh auth login` (choose GitHub.com, HTTPS, log in in the browser) |
| Push rejected (non-fast-forward) | `git -C slide-decks pull --rebase`, then publish again |
| Pages 404 for a few minutes | First publish takes 1–3 minutes; `publish` waits up to 10 |
| Pages build errored | Usually a file over 100 MB, or a broken symlink. Remove it and publish again |
| Fonts look different online | The font was only installed on the laptop. Add it via Google Fonts or `@font-face` |
| Pictures missing online | Paths are case-sensitive on Pages: `assets/Photo.PNG` ≠ `assets/photo.png` |
| Wall does not follow | Press `W` on the laptop (the status chip, `H`, shows "Wall on"). Check that both computers are online. On the wall, the corner message says what it is waiting for |
| Wall shows a different talk | Another laptop with the same wall code is presenting. Turn its wall off (`W`) |
| Phones cannot answer | The deck must be the published address, not localhost. Check that phones have internet |
| Workstation link got lost | On the laptop: `A` → *Lab wall* → *Copy wall link* |
| New laptop or browser | It gets a new wall code. Copy the new wall link to the workstation, or set a fixed `wall.code` in the decks |
