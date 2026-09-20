# Devpost submission — draft answers

Fill the repo URL, video URL and GitHub username before submitting.

---

## Project name

**Threshold — a doorbell that explains itself**

## Elevator pitch (200 characters)

Eleven of your twelve doorbell alerts are a cat. Threshold describes who is
actually at the door, learns what is normal for it, and only interrupts you
for reasons you wrote yourself.

## Track

Ring.

## Mini challenges

**AWS Builder** and **Open Source**. (Only one can win alongside the track
prize; both are genuinely used.)

## What it does

Threshold watches a Ring doorbell and turns each event into one plain sentence
a person can act on — spoken aloud, captioned on screen, or pushed to a phone.
It learns the rhythm of a particular door and notices when that rhythm breaks,
including the case that matters most in care: a morning where nothing happened
at all. And it lets you write what you want to be told about in English —
*"tell me if a vehicle stops in the driveway after dark"* — which is compiled
once into a typed rule and then evaluated by deterministic code against the
motion-zone polygon the Ring API actually reports.

Three outputs, one pipeline: perception, memory, rules.

## How we built it

Python 3.11 with **no runtime dependencies at all** — the Ring client, the AWS
SigV4 signing, the HTTP server and the front end are standard library and plain
browser APIs.

- **`ring_client/`** — a typed client for the Ring Partner API over `urllib`,
  with an offline emulator built from responses captured from the Playground.
  Released separately under MIT, because Ring ships no SDK.
- **Perception** — frames are grabbed from the live WHEP stream in the browser
  and sent to **Amazon Bedrock**, which returns one structured event. The
  prompt forbids guessing intent, character or identity: a doorbell that calls
  someone suspicious does real harm to real people.
- **Memory** — SQLite. Counts per weekday-hour bucket give a baseline; three
  anomalies are computed from it (silence, novelty, frequency).
- **Rules** — compiled once by a model into a typed dataclass, then evaluated
  in plain code with a verdict recorded per clause, so every alert can say
  which condition fired it. Zone membership is a point-in-polygon test against
  the real vertices, never a question put to the model.
- **Providers** — a fallback chain. A provider with no credentials drops out
  locally with no network call; one that fails mid-turn steps aside; the first
  that answers wins. With no AWS account at all the project still runs end to
  end on canned descriptions and says so in the interface.

106 tests run in about three seconds with the network cut off by a guard in
the test runner.

## Challenges

The Playground token is read-only, so the product had to be designed as a
witness rather than a controller. And Ring's history endpoint returns nothing
for a Playground device even after firing an event, so there was no past to
learn from — we generate a labelled synthetic fortnight and separate it from
live data everywhere it appears, rather than quietly presenting generated data
as observed.

Finding the Playground at all was the biggest one. Ring's development guide and
FAQ both say testing requires real devices and an active Ring Protection plan.
See the friction log.

## Accomplishments

The rules engine: English in, typed rule out, deterministic from then on, with
an explanation for every verdict including the ones that did not fire. And an
honesty table in the interface itself, not only the README.

## What we learned

Where to put a model, and where not to. Compilation is a good use of one;
adjudication is not.

## What's next

Webhooks instead of polling, the moment Ring can simulate them. Several
meaningfully shaped motion zones. A carer-facing view for the silence anomaly.

## Built with

`python` · `ring-partner-api` · `whep` · `webrtc` · `amazon-bedrock` ·
`sqlite` · `sigv4` · `ntfy` · no-dependencies

---

# Required extra fields

## Product feedback

**Ring Appstore API.** Used for device discovery, capabilities, configurations,
status, locations, users, event history, and WHEP live video. The data model is
clean and the JSON:API shape is predictable once you have written the flattening
layer. Live video over WHEP worked first time with a Playground token, which was
the single best surprise of the project. What needs work: there is no SDK in any
language, so everyone writes the same `urllib` wrapper; the docs contradict the
Playground about whether hardware is required; the token's read-only scope is
invisible unless you decode the JWT; simulated events never reach event history,
so the event-driven path cannot be tested end to end; and `/v1/devices/{id}/events`
returns 403 rather than 404, which sends you hunting for a permissions problem
instead of a typo. Onboarding was genuinely rough for the first hour and
genuinely good after it. Would we build with it again: yes.

**Ring Developer Playground.** The most valuable thing on the developer site and
the hardest to find. A virtual device, a one-click token and live video with no
hardware. Two asks: say the scopes on screen, and make the token last longer
than one debugging session.

**Ring MCP server.** Used in the editor for documentation lookup. It answers
questions about the docs accurately, which saved several tab-hunts. It does not
simulate devices — worth stating on the page, because the name suggests more.

**AWS Bedrock.** Used for two things: turning camera frames into a structured
event, and compiling an English sentence into a typed rule. Called directly over
HTTPS with hand-rolled SigV4 rather than boto3, to keep the project
dependency-free — the signing is about sixty lines and worked without drama.
The Anthropic Messages format on Bedrock made the image path simple. What needs
work: a first-time 403 for a model you have not enabled reads as a credentials
problem, and the fix (enabling model access in the console) is not mentioned in
the error. Would we build with it again: yes.

## Open Source mini challenge

- **Contribution URL:** <!-- the ring-client repo -->
- **Repo URL:** <!-- the Threshold repo -->
- **GitHub username:** <!-- yours -->
- **What it is.** `ring-client` — a typed, dependency-free Python client for the
  Ring Partner API, MIT licensed, extracted from this project and released as
  its own repository. It ships an offline emulator built from real captured
  Playground responses, so anyone can develop and test a Ring integration with
  no hardware, no subscription, and no 30-minute token expiring mid-session.
- **How it works.** One `RingClient` class over `urllib`, typed dataclasses for
  the JSON:API payloads, an error class per failure mode the API actually
  produces, local token-expiry detection, and a swappable transport so the
  emulator drops in for tests.
- **Why it matters.** Ring ships no SDK in any language. Every integrator
  currently writes the same wrapper and rediscovers the same five surprises.
  This is that wrapper, with the surprises documented in the tests.

## AWS Builder mini challenge

Amazon Bedrock is in the critical path: it performs the visual understanding
that produces every event, and it compiles rules from English. Integration is
in `threshold/providers/bedrock.py` — direct HTTPS with hand-rolled SigV4
signing, no SDK. The fallback chain in `threshold/providers/__init__.py` shows
how it degrades when Bedrock is unavailable.

## Did the project exist before the hackathon?

No. Everything in the repository was written during the submission window.
