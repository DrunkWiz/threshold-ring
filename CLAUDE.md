# Threshold — working notes for Claude Code

Read this first. It is the project's memory: what we're building, what is
already decided, and what must not be claimed. Prior work happened in a
Claude (Cowork) session; everything that mattered is written down here.

## What this is

A submission for the **Amazon "Build, Ship, Shape" developer hackathon, Ring
track**. Solo entry. Deadline **24 Oct 2026, 3:00am SGT** (23 Oct, 12:00pm PDT).

Threshold watches a Ring doorbell and turns each event into one plain sentence
a person can act on. Eleven of twelve doorbell alerts are a cat; the twelfth is
not, and most people solve that by muting all twelve.

Also entered in two mini challenges: **AWS Builder** (Bedrock is in the
critical path) and **Open Source** (`ring_client/` is extracted as its own
MIT-licensed repo). Only one can win alongside the track prize.

## The architecture, in one line each

One pipeline, three consumers. Perception produces one structured event
(`threshold/events.py`); narration, memory and rules all read it.

- `ring_client/` — typed Ring Partner API client, `urllib` only, plus an
  offline emulator built from payloads actually captured from the Playground.
- `threshold/perception.py` — the only model call that sees a picture.
- `threshold/memory.py` — SQLite baseline; silence, novelty, frequency anomalies.
- `threshold/narration.py` — deterministic. Announcement, caption, reason.
- `threshold/rules/` — `compile.py` (model, once) · `evaluate.py` (code, always)
  · `geometry.py` (point-in-polygon on the real motion zone).
- `threshold/providers/` — Bedrock with hand-rolled SigV4, a fake rung, a chain.
- `threshold/server.py` — stdlib HTTP + the WHEP proxy that keeps the token
  out of the browser.
- `web/` — no build step, plain ES modules.

`docs/ARCHITECTURE.md` has the diagram and the failure table.

## Decisions — do not undo these without a reason

- **The model compiles; code decides.** English becomes a typed `Rule` once.
  Every event after that is judged deterministically, with a verdict recorded
  per clause so the interface can say *why* a rule did not fire. Do not move
  adjudication into the model to "make it smarter".
- **Zone membership is arithmetic, never a question to the model.** A model
  asked "is this in the driveway?" agrees with whatever the prompt implied.
  There is a test where the model names a zone and the geometry overrules it.
- **Read-only is a position, not an apology.** The Playground token carries
  only `ava.v1:read`. Threshold is a witness: it never claims to switch on a
  light it cannot switch on.
- **Seeded history is labelled everywhere** — in the DB (`source="seeded"`),
  the API, the counts and the interface's honesty panel. Ring's history
  endpoint returns nothing for the Playground device, so a baseline has to be
  generated; presenting generated data as observed would sink the entry.
- **Total perception failure still records an event.** Silence is the one
  thing a doorbell must not do.
- **No runtime dependencies.** Not for the Ring client, the SigV4 signing, the
  server, or the front end. A judge clones and runs. Keep it that way: if you
  are about to add a dependency, find another way first.
- **The perception prompt forbids guessing intent, character or identity.** A
  doorbell that calls someone suspicious does real harm. There is a test
  asserting those lines are present.

## Commands

```bash
THRESHOLD_OFFLINE=1 python3 -m threshold.server   # emulator, seeded history, canned descriptions
python3 -m threshold.server                       # live; paste a Playground token in the page
python3 scripts/run_tests.py                      # 134 tests, ~2s, network blocked by a guard
```

On Windows use `py`, not `python3` — there `python3` is a Microsoft Store stub
that exits without running. Verified on the record/demo laptop, 21 Sep 2026.

Token: <https://developer.amazon.com/ring/console/playground> → Generate token.
Lasts 30 minutes; the page counts it down.

## The state of things

Everything is written and green, and **the live path has now run** — 21 Sep
2026, on the Windows laptop the demo will be recorded on. Verified against the
real `api.amazonvision.com`: token accepted, device resolved, scopes confirmed
`ava.v1:read`, a WHEP session opened through the proxy (201, 1280x720, audio
and video tracks live), a frame pulled off that stream and carried through
perception, narration and the rules engine. Nothing in that path needed
fixing. The token countdown was correct throughout, including at expiry.

**Bedrock has still never run, and on this AWS account it cannot.** Account
755400271187 sits inside AWS Organization o-f9bzz6q6aa (management account
103021624162), whose service control policy p-9pjv83er explicitly denies both
`bedrock:CallWithBearerToken` **and** `bedrock:PutUseCaseForModelAccess`.

That second denial is the deadlock, confirmed 5 Oct by calling the control
plane directly with SigV4. `bedrock:InvokeModel` is *not* denied - it returns
the "use case details have not been submitted" 404 rather than a 403 - but
the only call that submits those details is denied, and the console uses the
same API, so the console route fails identically. Nothing done from inside
this account can unblock it.

Three ways out, in order of effort: the Organization's management account
submits the form once (it is inherited by every member account); or a plain
personal AWS account outside the Organization is used instead, where there is
no SCP at all and a demo's worth of Bedrock calls costs pennies; or the AWS
Builder mini challenge is dropped and `docs/SUBMISSION.md` rewritten, since it
currently claims frames are sent to Bedrock.

**Perception now runs locally instead**, on a vision model through Ollama
(`threshold/providers/ollama.py`). Verified end to end on 23 Sep: the model
described a test image correctly and the pipeline carried it through
narration. It costs nothing, needs no account, and means the picture never
leaves the machine — which is a better position for a doorbell than the one
it replaced, not merely a consolation.

The repo is on GitHub at <https://github.com/DrunkWiz/threshold-ring>, still
private. Working copy lives in `Documents/Github/`; the folder is still named
`Amazon_Ring_hacakthon` from before the rename, which is cosmetic but
confusing.

`ring_client/` has been split out to <https://github.com/DrunkWiz/ring-client>
(22 Sep, also private), with its own README, LICENSE and network-guarded
runner. Its 15 tests pass standalone. The copy in this repo remains the one
Threshold imports; the two will need keeping in step if the client changes.

### Next, in order

1. **Describe the real bird clip** with the local model and measure the frame
   round-trip. A 1x1 test image went through in under a second, which says
   nothing useful: a 1280x720 frame is a different proposition. If it is slow,
   narrate from a single keyframe rather than a burst. Needs a Playground
   token, so it has to be done in one sitting.
2. **Record the video** to the five beats below, then put its URL in the
   `## Video` section of `docs/SUBMISSION.md` — the last blank left.
3. **Make both repos public** before the deadline — `threshold-ring` and
   `ring-client`. The rules ask specifically for the MIT licence visible in
   About; GitHub already detects it on both, and both have descriptions.

### The video — three minutes, five beats

1. **0:00–0:20** A phone with twelve notifications. Eleven are a cat.
2. **0:20–1:00** Fire Motion. Threshold speaks. Captions on screen.
3. **1:00–1:40** Type a rule in English; watch it compile against the real
   zone; fire Vehicle; the phone buzzes on camera.
4. **1:40–2:20** The pattern view, and this morning's missing carer visit.
5. **2:20–3:00** Architecture, then what is real and what is seeded, plainly.

Lead with the narration. Judges are not required to watch past three minutes
and most will not watch past ninety seconds.

## Do not claim

- That Bedrock works on this account. It is refused by an organisation policy,
  and the SigV4 route has not been tried.
- That the local model describes the *doorbell* well. It has only been shown a
  1x1 test image so far. It was right about that image, which proves the
  wiring and nothing about the product.
- Any latency number until it is measured on the laptop you record on.
- That "inside a motion zone" narrows anything on the Playground device — its
  single zone covers the whole frame, and a test says so.

## Things the Ring API taught us the hard way

Full version with severities in `docs/FRICTION_LOG.md` (worth up to a 10%
judging bonus, so keep adding to it as you hit new ones).

- Base URL is `api.amazonvision.com`, not a ring.com host.
- Event history is at `/v1/history/devices/{id}/events`, and
  `/v1/devices/{id}/events` returns **403**, not 404 — which sends you hunting
  for a permissions problem instead of a typo.
- The Playground token is read-only and nothing says so; decode the JWT.
- The Playground gives a working **virtual device** — no hardware, no
  subscription — even though the dev guide and FAQ both say otherwise.
- Simulated events never reach event history.
- CORS blocks browser calls from anywhere but the console, so `Failed to
  fetch` tells you nothing about whether the endpoint exists.

## House style

- Comments explain *why*, especially where the obvious approach was tried and
  rejected. Several in this repo record real bugs; leave them.
- Tests carry the reasoning for the case they cover. New behaviour gets a test
  that says why it matters, not just that it works.
- Errors are sentences a person can act on, not relayed status codes.
