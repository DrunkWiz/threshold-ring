"""Frames plus device context, in. One structured event, out.

This is the only place a model looks at a picture. Everything after it works
on the structured event, which is why narration, memory and rules can all be
deterministic and testable while still being driven by what the camera saw.

The prompt is written to get a *description*, not a judgement. "A man in a
blue jacket is standing at the door" is something a camera can support.
"Suspicious male loitering" is not, and a product that says it about the
wrong person does real harm. The system prompt says so explicitly, and the
schema has no field for a verdict.
"""

from __future__ import annotations

import time
from typing import Any

from .events import Event
from .providers import Chain, ProviderError
from .rules.geometry import zones_containing

SYSTEM = """You describe what a doorbell camera can see. You are careful, literal and brief.

Rules you must follow:
- Describe only what is visible. Never guess intent, character, or whether someone belongs.
- Never guess a person's race, nationality, age, gender or name. Describe clothing, what they carry, and what they do.
- If nobody and nothing is there, say so with subject "nothing".
- If the frames are too dark or blurred to tell, use subject "unknown" and a low confidence.

Answer with a single JSON object and nothing else:
{
  "subject": "person" | "vehicle" | "animal" | "package" | "nothing" | "unknown",
  "descriptors": ["short", "visual", "details"],
  "action": "what it is doing, one clause",
  "point": {"x": 0.0-1.0, "y": 0.0-1.0},   // where it is in frame, origin top-left
  "dwell_s": seconds it has been visible, a number,
  "night": true if the scene looks like night,
  "confidence": 0.0-1.0,
  "summary": "one plain sentence a person would want to hear"
}"""


class Perception:
    def __init__(self, chain: Chain, *, clock=time.time):
        self.chain = chain
        self._clock = clock
        self.last_latency_ms: float | None = None

    def observe(
        self,
        *,
        frames: list[str],
        trigger: str = "motion",
        zones: Any = (),
        device_id: str = "",
        device_name: str = "the front door",
        local_time: str | None = None,
    ) -> Event:
        """Turn frames into an event.

        `frames` are base64 JPEGs pulled off the WHEP stream in the browser.
        One or two is plenty: a burst costs latency, and latency is what kills
        a live demo.
        """
        when = local_time or time.strftime("%A %H:%M", time.localtime(self._clock()))
        prompt = (
            f"These frames are from {device_name}. Local time is {when}. "
            f"The camera reported a {trigger} event. Describe what you see."
        )

        started = self._clock()
        try:
            payload, provider_name = self.chain.complete_json(
                system=SYSTEM, prompt=prompt, images=frames, max_tokens=600
            )
        except ProviderError as exc:
            # Every rung failed. Rather than dropping the event, record that
            # something happened and that we could not see what — which is
            # itself true, and better than silence.
            self.last_latency_ms = (self._clock() - started) * 1000
            event = Event(
                trigger=trigger,
                subject="unknown",
                confidence=0.0,
                summary="Something triggered the camera, but the description could not be generated.",
                provider="none",
                device_id=device_id,
            )
            event.descriptors = (f"perception unavailable: {exc}",)
            return event

        self.last_latency_ms = (self._clock() - started) * 1000
        event = Event.from_model(payload, trigger=trigger, provider=provider_name, device_id=device_id)

        # The zone is decided here, by geometry, not by the model. Asking a
        # model "is this in the driveway?" invites it to agree with you.
        event.zone_ids = zones_containing(event.point, zones)
        return event
