# Project: 40th Birthday Party App

## What this is
The central web app for the host's 40th birthday party. The home page (`/`) lists the
party features; the music quiz (run live as part of a speech) is the first, at
`/quiz/`, with more planned. Not a general-purpose product — optimize for reliability
on one specific night over flexibility or future reuse. When in doubt, pick the
simplest thing that cannot break mid-party.

App layout: `core` is the shared party app (Player identity, welcome/registration,
demographics, the quiz, and Drinky); `pages` serves the home page; `accounts` holds
the host's User model.

## Party features beyond the quiz
- **Start screen (built):** `/start/` is the projector's arrival screen — the
  address `rethrow.dk` as a huge hero line and nothing else static; the host
  explains joining verbally rather than the screen listing steps. Under it, two
  htmx-polled counters: registered guests, and (only while a Drinky round is
  open) that round's "X af Y har pustet" progress, so the same screen can stay
  up during the first Drinky rounds. Public, no login, no navbar, same projector
  styling as the other big-screen pages. Sized to be read from ~15 m on a 40" TV, which is roughly
  that screen's limit: only the address is genuinely legible that far back, and
  the rest is deliberately secondary rather than uniformly scaled up. Its type
  keys off a `--u` custom property (`min(1vh, 0.5625vw)`) which equals 1vh on a
  16:9 screen but falls back to width on a narrower one, so the portrait-TV
  question below doesn't make these lines overflow. It belongs to **no single
  feature** deliberately: the view sits in `core` with the URL at the site root
  (like `/velkommen/` and `/profil/`), so the evening can open with Drinky, the
  quiz, or anything added later without the join instructions living inside the
  wrong app. It previously lived in the quiz projector's `waiting` state, which
  broke once the party stopped starting with the quiz.
- **Demographics (built):** right after signup, guests land on `/profil/` — four
  quick questions: age (validated 25-75), gender, number of kids (0-4), relation to
  the host (Familie / Ven / Grindsted). **Required, not skippable**: `player_required`
  (the same decorator gating every guest-facing view) redirects any registered guest
  with incomplete demographics to `/profil/?next=<where they were headed>` until it's
  filled in — so nobody reaches home, the quiz, or any future feature first. No edit
  entry point after that: a misclick stands. Stored as optional-at-the-model-level
  fields on `Player`
  (`demographics_done` property); `welcome()` also routes returning players there
  directly if incomplete.
- **Drinky (built, was "funthing2"):** guests periodically measure their alcohol
  level on a breathalyzer at the party and enter readings. The host creates a
  `DrinkyRound` from `/drinky/vaert/` (auto-numbered "Runde N", starts closed), with
  an optional title (e.g. a time like "15.00") shown instead of the number wherever
  the round appears — including the results charts' round labels, so the time-series
  reads as an actual timeline of the evening rather than arbitrary round numbers.
  Opening a round auto-closes any other open one — only one is ever live at a time.
  The host panel is **not** polled: it holds the new-round title input, and a
  periodic htmx swap wiped whatever was being typed into it. It renders once on
  load and again after each host action, and shows only which round is open. The
  live submitted-counter it used to carry now lives on `/start/`, which has no
  inputs to clobber.
  While a round is open, guests on `/drinky/` (gated by `player_required`, htmx-polled
  like the quiz) enter a promille reading from 0.00 to 2.99, with a nudge to rinse
  their mouth with a non-alcoholic drink first for an accurate reading and to answer
  honestly since results are anonymous; **one-shot** — the first submission per round
  locks it, no edits. Results live at `/drinky/projektor/`
  (public, no login, like the quiz projector) — the host opens it manually whenever
  they're ready to reveal, no auto-trigger. It renders Chart.js charts (vendored
  locally at `static/vendor/chart.min.js`, one deliberate exception to the
  "no hand-written JS" rule, scoped to this page only) in tabs. **All bar charts**
  — the time-series line versions read poorly on a TV and were dropped. The four
  grouped charts (by relation, by number of kids 0-1 / 2 / 3+, by gender, by
  age bracket — currently <=37 / 38-42 / >=43, retunable by editing the
  `DRINKY_AGE_BRACKETS` list in `core/views.py`) put the group on the x-axis with
  one bar per round inside each group, with round colours shared across those four
  tabs so a given round is the same colour on each. The overall-average chart has
  no groups, so it is simply one bar per round, all in the same blue — it is one
  population over time, and per-round colours would imply a split that isn't
  there. Everything is sized off the viewport (`vh`) and fills the screen,
  including the Chart.js font and legend sizes, since the page is read from ~10 m
  away on a 40" TV; each chart is built lazily the first time its tab is shown,
  because Chart.js measures its container at construction and a still-hidden pane
  measures 0. Series cross to the page as ordered `[[label, values], ...]` lists
  rather than `{label: values}` objects: JavaScript hoists index-like object keys
  ahead of the rest, so a bucket labelled "2" jumped to the front of the x-axis
  while "0-1" and "3+" stayed in place. **Aggregate-only, by design**:
  no guest is ever named, and any group average built from fewer than
  `DRINKY_MIN_GROUP_SIZE` (2) readings is dropped so a tiny bucket can't single
  someone out — this is the "decide deliberately how small a group may be shown"
  call flagged earlier, now resolved. The kid counts collapse to three buckets
  (0-1 / 2 / 3+) for a related but distinct reason: suppression is applied *per
  round*, so a thin bucket doesn't merely risk being empty, it risks appearing in
  some rounds and vanishing in others as its few members skip a reading — which
  reads as a broken chart rather than as "too few people". Barely any guest is
  childless and exactly one family has 4 kids, so those ends are merged inward.
  Guests still enter their real count on `/profil/` (0-4) — only the chart
  buckets merge, and the merge happens before the group-size filter so a pooled
  bucket can actually clear it.

- **Party date:** ~2026-07-31 (~25 days from project start on 2026-07-06)
- **Guests:** ~35 people, playing on their own phones
- **Questions:** 10-13 rounds, each built around a ~30s pre-trimmed song clip

## Format & scoring
Each round:
0. **Interlude (speech step):** before each question opens, the projector shows a
   full-screen picture (uploaded per question) while the host talks. Guests' phones
   show a quiet waiting screen (their score/rank). When the talk is done, the host
   opens the question from the control panel.
1. Host opens the question and manually starts the ~30s clip in a local music player
   on the projector laptop (the host panel shows a "play clip N" reminder). **Music is
   deliberately offline** — local files on the laptop, not streamed by the app — so a
   network hiccup can never stall audio mid-question.
2. Guests answer two things on their phone:
   - **Artist** — multiple choice (4 options).
   - **Year** — free-form integer input (e.g. 1986).
3. Guests may change their answer freely until the host closes the question.
4. Host manually closes the question when ready ("5 more seconds..." → click). **No
   automatic timer** — deliberate choice, so lag or live-speech improvisation can't
   derail things. Closing locks answers, computes points, and reveals in **one step**
   (a separate "closed" holding state was deliberately dropped as an unnecessary click).
5. Reveal: correct answer + updated leaderboard on the projector; each guest's phone
   shows their own result, points earned, and current rank. The host panel also has a
   confirm-guarded "one step back" action that reverses any transition (its one risky
   use — reopening a question after reveal — is a host-judgment call).

**Scoring per question:**
- Artist correct: **5 points**
- Year: **5** exact, **4** if ±1, **3** if ±2, **2** if ±3, **1** if ±4, **0** if ±5+.
- Ties on the leaderboard share placement (no tiebreaker).

## Participants & roles
- **Guests:** register once site-wide at `/velkommen/` (nickname only — no Django
  auth); every guest-facing page is gated by the `player_required` decorator, which
  redirects unregistered visitors there and attaches `request.player` otherwise.
  Identity persists via a cookie/token tied to their Player row, so a refreshed or
  dropped phone rejoins with score intact. All features share this one Player. Late
  joining is allowed at any point (missed questions simply score 0); everyone
  registered appears on the quiz leaderboard.
- **Host:** logs in as a real `accounts.User` (`AUTH_USER_MODEL = 'accounts.User'`) to
  reach the control panel: show interlude / open question / close-and-reveal /
  next interlude, plus a step-back action. Shows a live "X of Y have answered"
  counter to help pace the room, and reminders for which clip to cue on the laptop.
- **Projector page:** driven by the laptop connected to projector + speakers (audio
  played manually from local files, outside the app). Cycles through: interlude
  picture (during speech) → question → reveal + leaderboard. Also shows the
  answered-counter while a question is open. No navbar (all other pages share a
  Bootstrap navbar from base.html). Its `waiting` state is only a title card —
  the join instructions live on `/start/` (see below), not repeated here.
- **UI language:** Danish for everything guest- and projector-facing. Code, comments,
  admin, and commit messages in English.

## Stack & technical decisions
- **Django + server-rendered templates + htmx polling.** PythonAnywhere does not
  support WebSockets, so all live updates (guest, projector, host panel) poll via htmx
  (~every 2s) and swap server-rendered HTML fragments. No JSON API layer, no DRF, no
  Channels, no JS build step, no hand-written JS — with one deliberate exception: the
  Drinky results page (`/drinky/projektor/`) uses vendored Chart.js plus a small
  inline script to feed it server-rendered JSON and switch tabs, since a chart library
  can't be driven by htmx swaps alone. Scoped to that one page only.
- **Bootstrap 5** for layout/components (host's preferred framework), plus a small
  custom stylesheet for the projector page (very large type, high contrast, dim room)
  and phone tap targets.
- **All static assets vendored locally** (Bootstrap, htmx) — no CDNs at party time.
- **Cache-busting: bump `?v=` in `base.html` whenever `site.css` or `quiz.css` changes.**
  Storage is plain `StaticFilesStorage` (no hashed filenames), and PythonAnywhere's
  static mappings send a long cache header, so an edited stylesheet otherwise stays
  invisible on already-loaded phones and on the projector laptop until a hard refresh —
  not something 35 guests can be asked to do mid-party. `ManifestStaticFilesStorage`
  would automate it but 500s on any file missing from the manifest; the manual param
  was chosen as the thing that cannot break on the night. Vendored files are exempt:
  they never change.
- **Database: MySQL in production, SQLite for local dev.** PythonAnywhere's network
  storage makes SQLite locking unreliable under concurrent writes (35 guests submitting
  in the same seconds). Paid plan includes MySQL.
- **Hosting:** PythonAnywhere, paid plan, custom domain **rethrow.dk**. Standard WSGI
  setup; static/media served via PythonAnywhere's static file mappings.
- **Audio:** ~30s pre-trimmed clips live as local files on the projector laptop and
  are played manually (VLC or similar), named/ordered to match question order. The
  app stores no audio — chosen for runtime safety and manageability over remote
  control (decided 2026-07-17; replaced an earlier host-panel play/stop design).
- **Question authoring:** Django admin only — no custom setup UI.
- Keep the polling endpoints cheap (a couple of queries max): ~35 phones polling every
  2s is ~18 req/s sustained.

## Data model (sketch)
- `Quiz` — the event; holds state (waiting / interlude / question open / revealed /
  finished) and a pointer to the current question.
- `Question` — artist choices, correct artist, correct year, optional interlude image
  (shown on the projector before this question opens), order.
- `Player` — party-wide guest identity: globally unique nickname + token (cookie).
  Not a Django User, not tied to a quiz; shared by all party features.
- `Answer` — Player × Question, chosen artist, guessed year, computed points.

## Open questions / to verify during build
- Idea under consideration (2026-07-17, not decided): show the question content
  (artist options / year input) on the same page as the interlude, at least on the
  phones — i.e. guests could see or answer the question already during the speech
  step instead of the quiet waiting screen. Just a thought for now; do not build
  without confirming. Current leaning: keep the existing flow — interlude → talk →
  music + open question in one step — which needs no change.
- Rehearsal: do a full dry run (multiple phones + projector laptop + local music
  player) on the real PythonAnywhere deployment well before the party.
- Nickname policy: globally unique (case-insensitive); host can rename/remove via
  admin. Pre-party testing occupies nicknames — clear test Players before the party.
- Considering turning the 40" projector/TV on its side for a portrait ("high")
  viewport (raised 2026-07-30, testing on the real TV 2026-07-31). The projector
  CSS (`static/css/quiz.css`) sizes type almost entirely in `vh`, tuned for 16:9
  landscape — flipping to portrait roughly doubles effective height vs width, so
  text would render much larger than intended and layouts like the reveal bar
  chart / 4-option question grid would look cramped sideways. Not broken outright
  (text wraps, flex/grid adapt), but not tuned for it either. If portrait is kept
  after testing, revisit the sizing (e.g. `clamp()`/`min(vw, vh)`) rather than
  leaving it as-is.
