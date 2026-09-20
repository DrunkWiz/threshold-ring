"""English in, typed rule out — once.

The model is asked for a compilation, not a decision. That distinction is the
whole design: a decision made by a model has to be re-made every time and can
come out differently, while a compilation can be inspected, stored, tested and
explained back to the person who wrote it.

There is also a keyword compiler underneath. It handles the common shapes
("after dark", "more than 30 seconds", "a person", "in the driveway") with no
model at all, which means rule authoring keeps working with no AWS account —
and gives the model's output something to be checked against.
"""

from __future__ import annotations

import re
from typing import Any

from ..providers import Chain, ProviderError
from .model import Rule

SYSTEM = """You compile a sentence into a doorbell rule. Answer with one JSON object, nothing else.

{
  "name": "a short label, 2-5 words",
  "subject": "any" | "person" | "vehicle" | "animal" | "package",
  "zone": "any" | "inside" | "outside",
  "min_dwell_s": number of seconds it must stay, 0 if not stated,
  "time_window": {"from": "HH:MM", "to": "HH:MM"},
  "night_only": true only if the person said night or dark,
  "min_confidence": 0.0 unless they asked for certainty,
  "channels": ["screen"] and/or "speech", "push"
}

Only include what the sentence actually says. Do not invent a time window, a
dwell time or a zone that was not asked for. If the sentence mentions the
driveway, the porch, the path or any named area, use "inside"; the camera's
zones are the areas the person drew."""

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "sixty": 60,
}


def keyword_compile(text: str) -> dict[str, Any]:
    """A small deterministic compiler for the sentences people actually write."""
    lowered = text.lower()
    payload: dict[str, Any] = {"name": text.strip()[:60] or "Rule", "channels": ["screen"]}

    for subject in ("person", "people", "someone", "somebody", "vehicle", "car", "van",
                    "animal", "cat", "dog", "package", "parcel", "delivery"):
        if re.search(rf"\b{subject}\b", lowered):
            payload["subject"] = {
                "people": "person", "someone": "person", "somebody": "person",
                "car": "vehicle", "van": "vehicle",
                "cat": "animal", "dog": "animal",
                "parcel": "package", "delivery": "package",
            }.get(subject, subject)
            break

    if any(word in lowered for word in ("driveway", "porch", "path", "zone", "gate", "doorstep", "step")):
        payload["zone"] = "inside"

    if any(word in lowered for word in ("night", "dark", "after hours")):
        payload["night_only"] = True

    match = re.search(r"(?:more than|over|at least|longer than)\s+(\w+)\s*(second|sec|minute|min)", lowered)
    if match:
        count = _NUMBER_WORDS.get(match.group(1))
        if count is None:
            try:
                count = float(match.group(1))
            except ValueError:
                count = 0
        payload["min_dwell_s"] = count * (60 if match.group(2).startswith("min") else 1)

    window = re.search(r"between\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:and|to|-)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", lowered)
    if window:
        def hhmm(hour: str, minute: str | None, meridiem: str | None) -> str:
            h = int(hour) % 12
            if meridiem == "pm":
                h += 12
            elif meridiem is None and int(hour) > 12:
                h = int(hour)
            return f"{h:02d}:{int(minute or 0):02d}"

        payload["time_window"] = {
            "from": hhmm(window.group(1), window.group(2), window.group(3)),
            "to": hhmm(window.group(4), window.group(5), window.group(6)),
        }

    if "say" in lowered or "speak" in lowered or "out loud" in lowered:
        payload["channels"].append("speech")
    if "phone" in lowered or "notify" in lowered or "push" in lowered or "text me" in lowered:
        payload["channels"].append("push")

    return payload


def compile_rule(text: str, chain: Chain | None = None) -> tuple[Rule, list[dict[str, Any]]]:
    """Compile a sentence, preferring the model and falling back to keywords.

    Returns the rule and the chain's attempt log, so the interface can say
    which rung compiled it — or that no model was involved at all.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("a rule needs a sentence")

    attempts: list[dict[str, Any]] = []
    if chain is not None:
        try:
            payload, provider = chain.complete_json(system=SYSTEM, prompt=text, max_tokens=400)
            attempts = list(chain.attempts)
            if provider != "fake":
                return Rule.from_payload(payload, source_text=text, compiled_by=provider), attempts
            # The fake answers with a placeholder, which is worse than the
            # keyword compiler for a real sentence. Prefer the keywords.
        except ProviderError:
            attempts = list(chain.attempts)

    return Rule.from_payload(keyword_compile(text), source_text=text, compiled_by="keyword"), attempts
