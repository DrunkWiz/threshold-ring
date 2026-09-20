# Friction log — Ring Appstore API

Format as the hackathon asks: the task, the steps, expected versus actual,
severity, workaround, suggestion. Dates are when we hit each one.

---

## 1. The docs say you need hardware. The Playground says otherwise.

**Severity: high** — this nearly cost you the entry.

**Task.** Decide whether the Ring track was possible at all with no Ring device.

**Steps.** Read the Devpost track description ("A physical Ring device is not
required"), then the [development guide](https://developer.amazon.com/docs/ring/develop.html),
then the [FAQ](https://developer.amazon.com/docs/ring/developer-faq.html).

**Expected.** The docs to agree with the hackathon page.

**Actual.** The development guide lists as prerequisites "Ring account with an
active Ring Protection subscription plan" and "Ring devices registered to your
account". The FAQ says each staging user "needs an active Ring Protection plan
or trial on their own Ring account". Neither page mentions the Playground. The
sample app's README says outright that it "requires actual Ring devices". We
concluded the track was closed to us and began costing out a different one.

Only on the release-notes page (28 May 2026) did we find the Playground — which
issues a token *and* a virtual "Playground Device" that answers device, status,
capabilities, configurations, locations and users, and streams live video.

**Workaround.** Find the release notes. There is no other signpost.

**Suggestion.** Put one sentence at the top of Getting Started and in the FAQ:
*"You can call every read endpoint and stream live video with no hardware and
no subscription using the Playground."* We would guess this single omission
costs the Ring track a meaningful share of its entrants.

---

## 2. The Playground token is read-only, and nothing says so

**Severity: medium**

**Task.** Capture a snapshot on demand.

**Steps.** Generate a Playground token, `POST` to the media endpoints.

**Expected.** Either it works, or the console tells me it will not.

**Actual.** 403, with no indication why. The reason is only visible by
base64-decoding the JWT payload yourself, where `"scopes": ["ava.v1:read"]`
sits. Nothing in the Playground, the token panel or the error says the token
is read-only.

**Workaround.** Decode the token and design around reads. Our client now does
this automatically and puts the scopes into the 403 message, so the next
person gets a sentence instead of a status code.

**Suggestion.** Show the granted scopes beside the token in the Playground, and
grey out or mark the endpoints a Playground token cannot reach.

---

## 3. Simulated events never reach event history

**Severity: medium**

**Task.** Build something that reacts to an event and then looks back at the
history of events, which is the shape of any caretaking or pattern feature.

**Steps.** Fire Motion in the Playground, then
`GET /v1/history/devices/{id}/events`.

**Expected.** The event I just fired.

**Actual.** `{"data": []}`. The simulated event opens a live stream but is
never recorded. So the entire history-shaped half of the product cannot be
exercised at all without hardware, even though everything else can.

**Workaround.** Threshold keeps its own event store and ships a labelled
synthetic fortnight so a baseline exists to compare against. Every generated
row is marked `source="seeded"` and counted separately in the interface,
because quietly presenting generated data as observed data would be dishonest.

**Suggestion.** Write simulated events into history. It is the difference
between testing one endpoint and testing an integration.

---

## 4. Event history is not where you look for it

**Severity: low**

**Task.** Read a device's event history.

**Steps.** Tried `/v1/devices/{id}/events` first, by analogy with
`/v1/devices/{id}/status` and `/v1/devices/{id}/capabilities`.

**Expected.** A 404, or the history.

**Actual.** A **403**, which reads as a permissions problem and sent us to check
scopes rather than the path. The real route is
`/v1/history/devices/{id}/events` — device-scoped, but under a different root.

**Suggestion.** Return 404 for a path that does not exist, and cross-link the
history endpoint from the device resource docs.

---

## 5. The Playground device's single motion zone covers the whole frame

**Severity: low**, but it shapes what you can honestly demo.

**Task.** Build rules that depend on where in frame something happened.

**Actual.** `GET /v1/devices/{id}/configurations` returns one zone with eight
vertices spanning (0,0) to (1,1) — the entire image. So "inside a motion zone"
matches everything on this device, and a demo implying otherwise would be
showing something false. We have a test asserting this, so nobody on the
project can claim otherwise by accident.

**Suggestion.** Give the Playground device two or three overlapping,
differently shaped zones with meaningful names. Zone geometry is one of the
most interesting things the API exposes and it is currently untestable.

---

## 6. CORS blocks browser calls from anywhere but the console

**Severity: low**

**Task.** Probe the media endpoints quickly from a browser console.

**Actual.** `TypeError: Failed to fetch` — indistinguishable from the endpoint
not existing, so it teaches you nothing about which it was.

**Workaround.** Proxy through a local server, which is the right architecture
anyway: the token must not be in the page. Threshold's server signs the WHEP
exchange so the browser never sees the token.

**Suggestion.** Document that the API is server-to-server, and say so in the
Playground where the copyable `curl` sits.

---

# Feature requests

| Request | Why | Urgency |
|---|---|---|
| A hosted webhook simulator that posts real payloads to a URL you supply | Webhooks are the whole event model, and today they need a published app plus a public endpoint. Without this, no hackathon entrant can test the primary integration path. | **critical** |
| Simulated events recorded into event history | Turns the Playground from an endpoint tester into an integration tester. | important |
| Playground device with several meaningful motion zones | Makes the most interesting geometry in the API usable. | important |
| Longer or refreshable Playground tokens | 30 minutes is shorter than one debugging session, and a live demo can expire mid-sentence. | important |
| Scopes shown in the Playground UI | Turns a bare 403 into an answer. | nice-to-have |
| An official typed client for one language | There is no SDK. Everyone writes the same `urllib` wrapper. Ours is MIT-licensed if it helps. | nice-to-have |
