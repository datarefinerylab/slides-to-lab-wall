# Audience questions

A deck can be **plain** (most talks) or have **questions** on some slides. Both use the same engine, and nothing needs switching on:

| | Plain deck (`polls: {}`) | Deck with questions |
|---|---|---|
| QR code | Never | Only on slides that contain a question or its results |
| Phone page | Does not exist | `…/my-talk/#j.<session>` follows the presenter's current question |
| Network for answers | None | Phones post answers to the relay; the deck and wall listen |
| Wall screen 6 | Talk title | Join QR and phone count on question slides, talk title elsewhere |
| Keys | — | `Q` big QR, `D` demo answers |

Slides without a question look exactly like the original, even in a deck with questions.

## Defining questions

```js
polls: {
  when:  { q: 'When do you usually review code?', opts: ['First thing', 'After lunch', 'When asked', 'Rarely'] },
  tools: { q: 'Which tools do you use?', type: 'multi', opts: ['GitHub', 'GitLab', 'Gerrit', 'Other'] },
  hard:  { q: 'In one or two words: what makes review hard?', hint: 'Short words work best', max: 30 },
}
```

| Key | Meaning |
|---|---|
| id | 1–24 letters, digits, `-` or `_` |
| `q` | The question |
| `opts` | Answer options. With no `opts`, the question is a **word cloud** (free text) |
| `type` | `single` (default with opts) or `multi` |
| `hint` | Word cloud: helper line under the question |
| `max` | Word cloud: most characters per answer (40, at most 80) |
| `demo` | Rehearsal answers: weights per option (`[5,8,3,1]`) or words for a cloud |

Numbering ("Question 1, 2 …") follows the order the questions first appear in the slides.

## Placing them

Usual pattern: a question slide, then a results slide (or both on one slide).

```html
<section class="slide" data-section="Review habits">
  <h2 class="title">When do you usually review code?</h2>
  <div class="ld-poll" data-poll="when" data-parts="opts count"></div>
</section>
<section class="slide">
  <h2 class="title">When we review</h2>
  <div class="ld-results" data-poll="when"></div>
</section>
```

- A slide is a **question slide** when it contains any widget with `data-poll` (or the slide itself has `data-poll="id"`).
- On question slides a QR code floats in the corner unless the slide has its own `<div class="ld-qr">`. Add `data-qr="off"` to hide it, or `data-qr="left"` / `"top"` to move it. Leave room for it (about 300×360 px, bottom right) in the layout.
- Phones jump to the question of the slide being shown (the `.ld-poll` widget first, then the slide's `data-poll`). On a results slide, phones see that question and can still change their answer.
- Style the widgets like the deck (fonts and colours come from the `--ld-*` variables). Results rows are a grid: `.ld-bar{grid-template-columns:label bar percent count}`.
- In "Suggest a few" mode, propose 2–3 questions that fit the talk's flow (an opener to warm up, one before a key result, one at the end), as a short list, and wait for the user's yes before adding them.

## In the talk

- The **session** is a random id kept in the presenter's browser. Answers survive reloads. `A` → *Start a new session* gives a fresh empty session (export first).
- `A` → *Export CSV* / *Copy as JSON*: phone (anonymous number), question, answer, time.
- Word cloud: click a word on the deck to hide it (also on the wall). Useful for unwanted answers.
- `D` / `?demo`: made-up answers, the same on the deck and on the wall, for rehearsing. They never appear in the counts in the panel or in exports.
- Phones need internet, not the lab Wi-Fi. The deck must be opened from its published address (GitHub Pages): a deck opened from `localhost` or a file shows a warning, because phones cannot reach it.

## Big rooms: Firebase (optional)

ntfy.sh is free and needs no setup, but it limits how many messages one address can send. Past about 25 phones answering at once, use a free Firebase Realtime Database:

1. console.firebase.google.com → new project → Build → Realtime Database → Create (any location, start in **test mode**).
2. Rules (Realtime Database → Rules):
   ```json
   { "rules": {
       "rooms": { "$room": { ".read": true,
         "a": { "$dev": { "$poll": { ".write": true, ".validate": "newData.hasChildren(['v','t'])" } } },
         "s": { ".write": true } } },
       "walls": { "$code": { ".read": true, ".write": true } } } }
   ```
3. Put the database URL (`https://<project>-default-rtdb.<region>.firebasedatabase.app`) in the deck: `firebase: '…'`, or paste it in `A` → *Firebase database* while presenting.

The phone link then carries the database address, so phones use it too.

## Privacy

Answers are anonymous: each phone gets a random id and nothing else is collected. Messages go through the public relay (ntfy.sh) or your Firebase project. Do not ask for personal or sensitive information in questions.
