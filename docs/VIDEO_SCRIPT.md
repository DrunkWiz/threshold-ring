# The three-minute video — shot list and voiceover

Read the voiceover lines as written. They are timed at roughly 150 words a
minute, which is a comfortable narrating pace, and each beat's word count is
sized to its slot. If you ad-lib you will overrun; judges are not required to
watch past three minutes and most will not watch past ninety seconds.

Record beats 1–3 and 5 at any time. **Beat 4 has to be filmed inside one of
the windows listed under it** — the silence anomaly is computed, not staged,
so it only exists when the clock says it does.

---

## Before you press record

Do all of this in one sitting, in this order. The Playground token lasts
thirty minutes, which is the real constraint.

1. **Fix Bedrock first, or change what you say in beat 2.** As of the last
   check the account still has not had Anthropic's use case details form
   submitted, so every description comes from the canned rung and the
   interface correctly says `described by fake`. On camera that reads as a
   product that does not work. Submit the form in the Bedrock console, wait
   fifteen minutes, then confirm:

   ```
   py scripts/check_bedrock.py
   ```

   You want `auth  IAM access key, SigV4` followed by an answer.

2. **Start clean.** The database must not be locked when you delete it, so
   stop any running server first.

   ```
   rm threshold.db
   py scripts/run_tests.py
   ```

3. **Start the server** and leave this window open:

   ```
   py -u -m threshold.server
   ```

4. **Phone ready.** Unlock it, open ntfy to your topic, turn the volume up,
   and put it in frame on a stand. Beat 3 needs the buzz on camera.

5. **Turn off everything that can interrupt.** Windows notifications, Slack,
   email. A Teams toast across your own demo is a bad look.

6. **Generate the Playground token last**, immediately before recording:
   <https://developer.amazon.com/ring/console/playground> → Generate token.
   Paste it, press Connect, confirm the countdown is running.

### Recording on this laptop

Windows Game Bar (`Win` + `Alt` + `R`) records the focused window and is
already installed, but it will not record File Explorer or the desktop, and
it cannot show your phone. Use **OBS** instead, with two sources: a display
capture for the screen and a webcam pointed at the phone, so the buzz in
beat 3 and the notifications in beat 1 are the same take.

Record at 1080p. Record the voiceover live if your mic is decent — it keeps
the timing honest. If you dub it afterwards, record the screen silently
first, then read against the picture.

---

## Beat 1 — 0:00 to 0:20 — the problem

**On screen:** your phone's lock screen, twelve doorbell notifications,
scrolling slowly. Eleven of them are the cat.

> Twelve motion alerts from my doorbell today. Eleven of them are this cat.
> One of them was a parcel I missed. The usual fix is to turn the
> notifications off — and then you have a doorbell that tells you nothing
> at all.

Hold on the last notification for a beat before cutting.

---

## Beat 2 — 0:20 to 1:00 — it speaks

**On screen:** the Threshold interface, live stream playing, token countdown
visible in the corner. Fire a Motion event from the Playground console, then
press **Describe what you see**.

> This is Threshold. It is watching a live WebRTC stream from a Ring
> Playground device. That countdown is the thirty-minute token — and it never
> reaches the browser. The server signs the handshake and proxies the stream.

*(press Describe — then stop talking and let it speak)*

> Not a clip to scrub through. Not "motion detected". One sentence, and
> underneath it, the reason: everything the model actually saw, as structured
> data. Subject, position in frame, dwell time, confidence, and which model
> answered.

Make sure `described by bedrock` is legible on screen when you say that last
line. If it says `fake`, go back to step 1.

---

## Beat 3 — 1:00 to 1:40 — you write the rule

**On screen:** type the rule into the box, press Compile, show the plain
English explanation and the zone polygon, then fire a Vehicle event from the
Playground. Cut to the phone as it buzzes.

Type exactly: `Tell me if a vehicle stops in the driveway after dark`

> You decide what is worth interrupting you, in English.

*(typing — let it land, then press Compile)*

> The model compiles that once, into a typed rule. Then it is out of the loop.
> Every event after this is judged by code, against the actual motion-zone
> polygon the Ring API reports — that is a point-in-polygon test, not a
> question I put to a language model, because a model asked "is this in the
> driveway" agrees with whatever the prompt implied.

*(fire Vehicle — phone buzzes, hold on it)*

> And when a rule does not fire, it can tell you which condition failed.

---

## Beat 4 — 1:40 to 2:20 — what is normal, and what is missing

**Film this inside one of these windows.** Outside them the alert will not
appear, because there is nothing unusual about the hour:

| Window | Days |
| --- | --- |
| 08:00–08:59 | Monday to Friday |
| 09:00–09:59 | Tuesday and Friday |
| 11:00–11:59 | Tuesday and Friday |

Next few: **Mon 5 Oct 08:00**, **Tue 6 Oct 08:00 / 09:00 / 11:00**,
**Wed 7 Oct 08:00**.

Press **Seed a fortnight of history**, then reload the page — and do not
press Describe during that hour, because a real person arriving is exactly
what cancels the alert.

**On screen:** the heatmap filling in, then the table view, then the red-ruled
silence alert above it.

> It also learns the rhythm of one particular door. This is a fortnight of
> history — and it is labelled seeded, everywhere, because Ring's history
> endpoint returns nothing for a Playground device, and presenting generated
> data as observed would be a lie.
>
> From that baseline it computes three anomalies. This is the one that
> matters.

*(the silence alert, held on screen)*

> Nothing has happened at the door this hour, on a morning when something
> usually does. That is the carer who did not arrive. It is the only alert in
> the product that fires on nothing happening at all.

---

## Beat 5 — 2:20 to 3:00 — what is real

**On screen:** the architecture diagram from `docs/ARCHITECTURE.md`, then cut
back to the honesty panel in the interface.

> One pipeline, three consumers. Perception produces one structured event, and
> narration, memory and rules all read the same one.
>
> Python, standard library only. No dependencies in the Ring client, the AWS
> signing, the server or the front end — a judge clones it and runs it. The
> Ring client is MIT and split out on its own, because Ring ships no SDK and
> the next person should not have to write one.

*(cut to the honesty panel)*

> And this panel says at all times which parts are real and which are seeded,
> and which model rung answered. A doorbell that explains itself should start
> by being honest about itself.

Cut on that line. Do not add an outro.

---

## After

Upload unlisted to YouTube, then put the URL in the `## Video` section of
`docs/SUBMISSION.md` and in the Devpost "Video demo link" field. Devpost
requires it to be on YouTube, Vimeo, Facebook Video or Youku, publicly
viewable, and under three minutes.
