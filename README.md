# Threshold

**A doorbell that explains itself.** Built on the Ring Partner API for the
Amazon *Build, Ship, Shape* developer hackathon, Ring track.

Eleven of your twelve Ring notifications are a cat. One of them is not. Most
people solve that by muting all twelve. Threshold watches the door, describes
what it sees in plain language, learns what is normal for this particular
door, and only interrupts you for the reasons you asked for.

```
motion / package / vehicle
        |
        v
  frames off the live WHEP stream + device status + motion-zone polygon
        |
        v
   PERCEPTION ---> one structured event
        |
   +----+--------------------+---------------------+
   |                         |                     |
NARRATION                 MEMORY                 RULES
plain language,       what is normal for      English compiled to
screen reader first   this door               conditions on the
                                              real zone geometry
```

One pipeline, three consumers. Change the event shape and all three change
together — which is why this is a product rather than three features.

## The idea that holds it up

**A model compiles a rule once. Plain code evaluates it forever.**

You write *"tell me if a vehicle stops in the driveway after dark"*. That goes
to a model exactly once and comes back as a typed rule: a subject, a zone, a
dwell threshold, a time window. From then on every event is judged by
deterministic code — including a point-in-polygon test against the motion-zone
vertices Ring actually reports for your device.

So the same event always produces the same verdict, every verdict can explain
which clause decided it, and the whole rules engine is testable without a
model, a key or a network. The model is used where judgement is needed and
kept out of the loop where correctness is needed.

## What is real, and what is not

Stated here, in the interface, and out loud in the demo video.

| | |
|---|---|
| **Real** | Every Ring API call. The live video: a genuine WHEP session with a real SDP exchange. The motion-zone polygon the rules are evaluated against. The description of what the camera saw. |
| **Seeded** | The fortnight of past events behind the pattern view. Ring's history endpoint returns an empty list for the Playground device even after firing an event, so Threshold generates a plausible past, marks every row `source="seeded"`, and counts them separately everywhere. The generator is `threshold/seed.py`. |
| **Not attempted** | Anything that writes. The Playground token carries only `ava.v1:read`, so Threshold is a witness, not a controller. It never touches the door, and it never claims to switch on a light it cannot switch on. |

That last row is a design position, not an apology. For the caretaking case, a
system that can watch a front door but can never unlock it is the right shape.

## Running it

Python 3.11 or newer. **No runtime dependencies** — not for the Ring client,
not for the AWS calls, not for the server. `git clone` and go.

On Windows, run `py` wherever this README says `python3`. The `python3` on
PATH there is usually a Microsoft Store stub that prints an install prompt and
exits without running anything.

```bash
# offline: the emulator, a seeded fortnight, canned descriptions
THRESHOLD_OFFLINE=1 python3 -m threshold.server

# live: against a real Ring Playground token
python3 -m threshold.server           # then paste the token in the interface
```

Open <http://127.0.0.1:8765>.

To get a token: <https://developer.amazon.com/ring/console/playground> →
**Generate token**. It lasts 30 minutes; the interface counts it down so a
demo never discovers it expired mid-sentence.

For real descriptions instead of canned ones, set AWS credentials and
Threshold will use Bedrock:

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_REGION=us-east-1
export THRESHOLD_NTFY_TOPIC=threshold-demo-<something-unique>   # optional phone push
```

Or copy `.env.example` to `.env` and fill it in — the server reads it on
startup, and anything already set in the environment wins over the file. On
the first line of its output it prints the providers it actually built, so
`Model providers: fake` means your credentials did not arrive.

To check the credentials on their own, before starting anything:

```bash
python3 scripts/check_bedrock.py
```

One call, and it says which of the key, the region or model access is the
problem — all three otherwise look identical from inside the app, because the
provider chain is built to degrade quietly.

With no credentials it still runs end to end, clearly marked as canned. A
judge who cannot run your project scores what they can see, and that should
not be a stack trace.

### Environment

| Variable | Default | What it does |
|---|---|---|
| `THRESHOLD_OFFLINE` | off | Use the built-in Ring emulator instead of the real API |
| `RING_TOKEN` | — | Skip pasting the token in the interface |
| `RING_DEVICE_ID` | first found | Pin a specific device |
| `THRESHOLD_PROVIDER` | — | Force a model provider to the front of the chain |
| `THRESHOLD_PROVIDER_CHAIN` | `bedrock,fake` | The fallback ladder |
| `THRESHOLD_BEDROCK_MODEL` | Claude Sonnet on Bedrock | Model id |
| `THRESHOLD_NTFY_TOPIC` | — | ntfy.sh topic for phone push |
| `THRESHOLD_DB` | `threshold.db` | Where memory lives |
| `THRESHOLD_PORT` | `8765` | Port |

## Tests

```bash
python3 scripts/run_tests.py
```

112 tests, about two seconds, **no network**: the runner replaces
`socket.connect` so anything reaching past localhost fails loudly. That is a
guard, not a claim — and `tests/test_network_guard.py` proves the guard bites.

What they cover, and why each one exists, is written in the tests themselves.
The interesting ones:

- the time window that wraps midnight, because "between 11pm and 6am" is the
  most common thing anyone asks a doorbell for and the easiest to get silently
  backwards
- a ray passing exactly through a polygon vertex, the classic point-in-polygon bug
- a degenerate zone containing *nothing* rather than everything
- perception failing on every rung and still producing an event, because
  silence is the one thing a doorbell must not do
- the model naming a zone and being overruled by the geometry

## Layout

```
ring_client/        A typed Ring Partner API client, stdlib only, plus an
                    offline emulator built from real captured payloads.
                    Extracted as its own MIT-licensed repo — Ring ships no SDK.
threshold/
  perception.py     frames -> one structured event (the only model call that sees a picture)
  events.py         the single event schema everything shares
  memory.py         SQLite baseline; silence, novelty and frequency anomalies
  narration.py      event -> announcement, caption, reason (deterministic)
  rules/            compile.py (model, once) · evaluate.py (code, always) · geometry.py
  providers/        bedrock.py (SigV4 by hand) · fake.py · the fallback chain
  notify.py         speech, screen, phone push
  seed.py           the labelled synthetic fortnight
  server.py         stdlib HTTP, and the WHEP proxy that keeps the token server-side
web/                No build step. Plain ES modules.
```

## Notes for anyone building on the Ring API

Things that cost us time, in case they save you some:

- The base URL is `api.amazonvision.com`, not a ring.com host.
- Event history is at `/v1/history/devices/{id}/events` — not under the device
  resource, where you will look first.
- The Playground token is **read-only** (`ava.v1:read`) and nothing in the
  console says so. Decode it if a write returns 403.
- The Playground gives you a working **virtual device**, so you need no
  hardware and no subscription — even though the development guide and the FAQ
  both say testing needs real devices and a Ring Protection plan.
- Simulated events do **not** appear in event history.
- The device's single motion zone covers the entire frame, so "inside a zone"
  is not a narrowing condition on the Playground doorbell. There is a test that
  says so, to stop anyone claiming otherwise.

The full friction log is in [`docs/FRICTION_LOG.md`](docs/FRICTION_LOG.md).

## Licence

MIT. See [LICENSE](LICENSE).
