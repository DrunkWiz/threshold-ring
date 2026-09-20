"""A synthetic fortnight, so the baseline has something to be a baseline of.

Ring's history endpoint returns an empty list for the Playground device even
after firing an event, so there is no past to learn from. Rather than pretend
otherwise, Threshold generates one and marks every generated row
`source="seeded"`. The interface shows the count, the API can exclude them,
and the README and the demo video both say so out loud.

The shape is a specific household on purpose — a carer on Tuesday and Friday
mornings, post on weekday mornings, a supermarket delivery on Thursday
evening, foxes at night. A baseline of uniform noise would make the silence
anomaly meaningless, because nothing would be normal enough to be missed.
"""

from __future__ import annotations

import random
import time
from typing import Iterable

from .events import Event

ROUTINE = [
    # (weekdays, hour, minute, subject, action, descriptors, probability)
    ((0, 1, 2, 3, 4), 8, 20, "person", "delivering the post", ("carrying a satchel",), 0.85),
    ((1, 4), 9, 30, "person", "arriving for a visit", ("wearing a blue tunic", "carrying a bag"), 0.95),
    ((1, 4), 11, 15, "person", "leaving the house", ("wearing a blue tunic",), 0.95),
    ((3,), 18, 40, "package", "left by the step", ("a cardboard box",), 0.7),
    ((0, 1, 2, 3, 4, 5, 6), 13, 5, "animal", "crossing the path", ("a cat",), 0.5),
    ((0, 1, 2, 3, 4, 5, 6), 2, 40, "animal", "moving across the frame", ("low to the ground",), 0.4),
    ((5,), 11, 0, "person", "visiting", ("carrying flowers",), 0.4),
    ((0, 1, 2, 3, 4, 5, 6), 19, 30, "vehicle", "pulling up outside", ("a white van",), 0.3),
]


def generate(
    *,
    days: int = 14,
    device_id: str = "",
    now: float | None = None,
    seed: int = 20260921,
    skip_last_morning: bool = True,
) -> list[Event]:
    """A fortnight of plausible events, oldest first.

    `skip_last_morning` leaves out this morning's carer visit, which is what
    gives the silence anomaly something true to notice during a demo. It is a
    deliberate hole in synthetic data, not a hidden one: the flag is in the
    signature and the interface names it.
    """
    rng = random.Random(seed)
    now = now or time.time()
    events: list[Event] = []

    for day_offset in range(days, 0, -1):
        day_start = now - day_offset * 86400
        weekday = time.localtime(day_start).tm_wday

        for weekdays, hour, minute, subject, action, descriptors, probability in ROUTINE:
            if weekday not in weekdays or rng.random() > probability:
                continue
            if skip_last_morning and day_offset == 1 and hour < 12 and subject == "person":
                continue

            lt = time.localtime(day_start)
            at = time.mktime(
                (lt.tm_year, lt.tm_mon, lt.tm_mday, hour, minute, 0, 0, 0, -1)
            ) + rng.randint(-900, 900)

            events.append(
                Event(
                    at=at,
                    trigger="motion" if subject != "package" else "package",
                    subject=subject,
                    descriptors=descriptors,
                    action=action,
                    point=(round(rng.uniform(0.25, 0.75), 3), round(rng.uniform(0.3, 0.8), 3)),
                    zone_ids=(),
                    dwell_s=rng.randint(4, 50),
                    night=hour < 6 or hour >= 20,
                    confidence=round(rng.uniform(0.7, 0.95), 2),
                    summary=f"{subject.capitalize()} {action}.",
                    source="seeded",
                    provider="seed",
                    device_id=device_id,
                )
            )

    events.sort(key=lambda e: e.at)
    return events


def describe(events: Iterable[Event]) -> str:
    events = list(events)
    if not events:
        return "No seeded history."
    span_days = (events[-1].at - events[0].at) / 86400
    return (
        f"{len(events)} seeded events across {span_days:.0f} days, "
        "marked source=seeded and excluded wherever the interface says 'live only'."
    )
