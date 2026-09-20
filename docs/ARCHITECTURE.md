# Architecture

## The pipeline

One event shape (`threshold/events.py`) is produced once per trigger and then
read by three consumers. Everything else follows from that.

```
      Ring Playground                     browser                    server
  ---------------------            -------------------      ----------------------
   motion / package /   ---------> WHEP peer connection
   vehicle simulation               |
                                    | canvas frame grab
                                    v
                               POST /api/observe  ------->  perception (model, once)
                                                                  |
                                                     structured event (typed, validated)
                                                                  |
                                          +-----------------------+---------------------+
                                          v                       v                     v
                                     memory (SQLite)         rules (code)          narration
                                     baseline, anomalies     zone geometry         announcement
                                                             deterministic         caption, reason
                                                                  |
                                                                  v
                                                              notify: speech / screen / push
```

## Why the token never reaches the browser

WebRTC can only live in the page, but the Ring token must not. So the browser
builds the SDP offer, posts it to `/api/whep`, and the server signs the request
to Ring with the token it holds. The answer goes back to the page. The page
never sees a credential, and a screenshot of the demo leaks nothing.

## Why a model compiles but never decides

A rule is compiled once into `threshold/rules/model.Rule` — a dataclass of
plain conditions. `evaluate.py` then judges every event against it in ordinary
code, recording a verdict per clause rather than short-circuiting, so the
interface can say *"did not fire: it was 14:10, outside your 23:00–06:00
window"*.

Three things follow:

1. **Reproducibility.** The same event and rule always give the same answer.
2. **Explainability.** Every verdict names the clause responsible.
3. **Testability.** The rules engine has no model, key or network in it, so
   the whole of it runs in milliseconds in CI.

The one thing the model is genuinely better at — reading an English sentence —
happens once, at authoring time, where a human is present to check the result.

## Why zone membership is geometry, not a question

The model is never asked which zone something is in. It would agree with
whatever the prompt implied. Instead, perception returns a normalised point and
`rules/geometry.py` runs point-in-polygon against the vertices Ring reports.
Arithmetic cannot be talked round.

## Failure behaviour

| What fails | What happens |
|---|---|
| Token expires | Detected locally before any request; the interface counts down and says to generate a new one |
| Bedrock unreachable or throttled | The chain steps to the next rung; the interface names which rungs were skipped |
| Every provider fails | An event is still recorded saying something happened and could not be described. Silence is the one thing a doorbell must not do |
| Model returns prose or a fenced block | `providers/salvage.py` recovers the object by brace counting |
| Model returns a subject we do not know | Coerced to `unknown` rather than leaking a novel string into the rules engine, where it would silently match nothing forever |
| Ring returns an HTML error page | Reported as "not JSON — a proxy or captive portal usually causes this", not as a JSON parse error |
| Too little history | The silence anomaly stays quiet. Claiming a routine from two days of data would frighten someone about their parent for no reason |

## Dependencies

None at runtime. The Ring client, the SigV4 signing, the HTTP server and the
front end are all standard library or plain browser APIs. `git clone` and run.
