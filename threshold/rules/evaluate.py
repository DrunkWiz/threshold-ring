"""Deciding whether a rule fired, in plain deterministic code.

No model runs here, ever. The same event and the same rule always produce the
same decision, which is what makes the behaviour testable and what lets the
interface show exactly which clause was responsible.

Every clause records its own verdict rather than short-circuiting, because
"did not fire" is useless feedback and "did not fire: it was 14:10, outside
your 23:00–06:00 window" is a person fixing their own rule.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..events import Event
from .model import Rule


@dataclass
class Clause:
    name: str
    passed: bool
    detail: str


@dataclass
class Decision:
    rule_id: str
    rule_name: str
    fired: bool
    clauses: list[Clause] = field(default_factory=list)

    @property
    def blocking(self) -> list[Clause]:
        return [c for c in self.clauses if not c.passed]

    def explain(self) -> str:
        if self.fired:
            return f"{self.rule_name} fired: " + "; ".join(c.detail for c in self.clauses)
        blockers = self.blocking
        return f"{self.rule_name} did not fire: " + "; ".join(c.detail for c in blockers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "fired": self.fired,
            "explanation": self.explain(),
            "clauses": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in self.clauses],
        }


def _article(word: str) -> str:
    """"a" or "an". Small thing, but "saw a animal" reads as a bug to a judge."""
    return "an" if word[:1].lower() in "aeiou" else "a"


def _in_window(minute: int, start: int, end: int) -> bool:
    """Inclusive, and correct across midnight.

    "Between 11pm and 6am" is the single most common thing a person asks a
    doorbell for, and it is the window where start > end. Getting this wrong
    means the rule is silent exactly at night, which is when it matters.
    """
    if start <= end:
        return start <= minute <= end
    return minute >= start or minute <= end


def evaluate(rule: Rule, event: Event, *, now: float | None = None) -> Decision:
    decision = Decision(rule_id=rule.id, rule_name=rule.name, fired=False)

    if not rule.enabled:
        decision.clauses.append(Clause("enabled", False, "the rule is switched off"))
        return decision

    # subject
    if rule.subject == "any":
        decision.clauses.append(Clause("subject", True, "any subject matches"))
    else:
        ok = event.subject == rule.subject
        decision.clauses.append(
            Clause(
                "subject",
                ok,
                f"wanted {_article(rule.subject)} {rule.subject}, saw {_article(event.subject)} {event.subject}"
                if not ok
                else f"it is {_article(rule.subject)} {rule.subject}",
            )
        )

    # zone
    if rule.zone == "any":
        decision.clauses.append(Clause("zone", True, "anywhere in frame"))
    elif rule.zone == "inside":
        ok = bool(event.zone_ids)
        decision.clauses.append(
            Clause("zone", ok, "inside a motion zone" if ok else "it was outside every motion zone")
        )
    elif rule.zone == "outside":
        ok = not event.zone_ids
        decision.clauses.append(
            Clause("zone", ok, "outside every motion zone" if ok else "it was inside a motion zone")
        )
    else:
        ok = rule.zone in event.zone_ids
        decision.clauses.append(
            Clause("zone", ok, f"in zone {rule.zone[:8]}" if ok else f"not in zone {rule.zone[:8]}")
        )

    # dwell
    if rule.min_dwell_s:
        ok = event.dwell_s >= rule.min_dwell_s
        decision.clauses.append(
            Clause(
                "dwell",
                ok,
                f"stayed {int(event.dwell_s)}s, needed {int(rule.min_dwell_s)}s"
                if not ok
                else f"stayed {int(event.dwell_s)}s",
            )
        )

    # time window
    lt = time.localtime(now or event.at)
    minute_of_day = lt.tm_hour * 60 + lt.tm_min
    if rule.window_label != "any time":
        ok = _in_window(minute_of_day, rule.from_minute, rule.to_minute)
        decision.clauses.append(
            Clause(
                "window",
                ok,
                f"it was {lt.tm_hour:02d}:{lt.tm_min:02d}, outside {rule.window_label}"
                if not ok
                else f"within {rule.window_label}",
            )
        )

    # night
    if rule.night_only:
        ok = event.night
        decision.clauses.append(Clause("night", ok, "it is night" if ok else "the scene looked like daylight"))

    # confidence
    if rule.min_confidence:
        ok = event.confidence >= rule.min_confidence
        decision.clauses.append(
            Clause(
                "confidence",
                ok,
                f"confidence {event.confidence:.2f}, needed {rule.min_confidence:.2f}"
                if not ok
                else f"confidence {event.confidence:.2f}",
            )
        )

    decision.fired = all(c.passed for c in decision.clauses)
    return decision


def evaluate_all(rules: list[Rule], event: Event, *, now: float | None = None) -> list[Decision]:
    return [evaluate(rule, event, now=now) for rule in rules]


def channels_for(decisions: list[Decision], rules: list[Rule]) -> tuple[str, ...]:
    """Every channel any fired rule asked for, de-duplicated, order kept."""
    by_id = {r.id: r for r in rules}
    out: list[str] = []
    for decision in decisions:
        if not decision.fired:
            continue
        for channel in by_id.get(decision.rule_id, Rule()).channels:
            if channel not in out:
                out.append(channel)
    return tuple(out)
