"""Turning an event into something a person can hear or read.

Deterministic on purpose. The model already did the perceiving; asking it
again to phrase the result would make the same event come out differently
twice, which is intolerable for a screen reader and untestable besides.

Three outputs, because three kinds of listener need different lengths:

  announcement — what a screen reader or speaker says, full sentence, no jargon
  caption      — what sits under the video, short enough to read at a glance
  reason       — why this was surfaced at all, so the alert is accountable
"""

from __future__ import annotations

from .events import Event

_ARTICLE = {
    "person": "Someone",
    "vehicle": "A vehicle",
    "animal": "An animal",
    "package": "A package",
    "nothing": "Nothing",
    "unknown": "Something",
}


def _join(parts: list[str]) -> str:
    parts = [p for p in parts if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def announcement(event: Event, *, zone_names: dict[str, str] | None = None) -> str:
    """One spoken sentence. This is the product for a blind user."""
    if event.subject == "nothing":
        return "Nothing is at the door."
    if event.provider == "none":
        return "The camera picked something up, but it could not be described."

    zone_names = zone_names or {}
    subject = _ARTICLE.get(event.subject, "Something")

    descriptors = _join(list(event.descriptors))
    if event.subject == "person" and descriptors:
        opening = f"Someone {descriptors}" if descriptors.startswith(("wearing", "holding", "carrying")) else f"{subject}, {descriptors},"
    elif descriptors:
        opening = f"{subject}, {descriptors},"
    else:
        opening = subject

    action = event.action or "is at the door"
    if not action.startswith(("is ", "are ", "has ", "was ")):
        action = "is " + action

    sentence = f"{opening} {action}".replace(",  ", ", ").strip()
    if not sentence.endswith("."):
        sentence += "."

    where = _join([zone_names.get(z, "the motion zone") for z in event.zone_ids])
    if where:
        sentence += f" In {where}."

    if event.dwell_s >= 20:
        sentence += f" It has been there for about {int(event.dwell_s)} seconds."

    if event.confidence < 0.45:
        # Said out loud rather than shown as a number. A person deciding
        # whether to open their door deserves to know the machine is unsure.
        sentence += " I am not certain about this one."

    return sentence


def caption(event: Event) -> str:
    """Short enough to read under a video without pausing it."""
    if event.subject == "nothing":
        return "Nothing at the door"
    subject = _ARTICLE.get(event.subject, "Something")
    action = event.action.split(",")[0][:60] if event.action else "at the door"
    return f"{subject} — {action}".strip(" —")


def reason(event: Event, *, matched_rules: list[str] | None = None, anomaly: str | None = None) -> str:
    """Why the person is hearing about this.

    An alert that cannot explain itself is an alert people eventually mute.
    """
    if matched_rules:
        return "Because you asked to be told: " + _join(matched_rules) + "."
    if anomaly:
        return anomaly
    if event.is_noteworthy:
        return "Someone was at the door."
    return "Not passed on — this looked like ordinary background movement."


def render(event: Event, *, zone_names=None, matched_rules=None, anomaly=None) -> dict[str, str]:
    return {
        "announcement": announcement(event, zone_names=zone_names),
        "caption": caption(event),
        "reason": reason(event, matched_rules=matched_rules, anomaly=anomaly),
    }
