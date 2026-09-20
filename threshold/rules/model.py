"""The typed rule.

This is the contract between the part of the system that understands English
and the part that has to be right. A model turns a sentence into one of these,
once. From then on nothing is interpreted: the evaluator reads fields.

Every field is optional with a permissive default, because a rule that fails
to parse cleanly should narrow to "tell me about everything" rather than
silently matching nothing. A noisy rule gets fixed; a silent one gets trusted.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from ..events import SUBJECTS

CHANNELS = ("screen", "speech", "push")
_TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _minutes(value: Any, default: int) -> int:
    if isinstance(value, str):
        match = _TIME.match(value.strip())
        if match:
            return int(match.group(1)) * 60 + int(match.group(2))
    return default


@dataclass
class Rule:
    """One compiled rule.

    `source_text` is kept so the interface can show the person the sentence
    they wrote next to what it became. Being able to see the compilation is
    what makes it trustworthy — and what lets them notice a misreading.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "Rule"
    source_text: str = ""
    subject: str = "any"                 # any | person | vehicle | animal | package
    zone: str = "any"                    # any | inside | outside | <zone id>
    min_dwell_s: float = 0.0
    from_minute: int = 0                 # inclusive, minutes past local midnight
    to_minute: int = 1439                # inclusive
    night_only: bool = False
    min_confidence: float = 0.0
    channels: tuple[str, ...] = ("screen",)
    enabled: bool = True
    compiled_by: str = ""                # which provider compiled it, or "keyword"

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, source_text: str = "", compiled_by: str = "") -> "Rule":
        subject = str(payload.get("subject") or "any").lower().strip()
        if subject not in SUBJECTS and subject != "any":
            subject = "any"

        window = payload.get("time_window") or {}
        from_minute = _minutes(window.get("from"), 0)
        to_minute = _minutes(window.get("to"), 1439)

        channels = payload.get("channels") or ["screen"]
        if isinstance(channels, str):
            channels = [channels]
        channels = tuple(c for c in (str(x).lower().strip() for x in channels) if c in CHANNELS) or ("screen",)

        try:
            dwell = max(0.0, float(payload.get("min_dwell_s") or 0))
        except (TypeError, ValueError):
            dwell = 0.0
        try:
            confidence = min(1.0, max(0.0, float(payload.get("min_confidence") or 0)))
        except (TypeError, ValueError):
            confidence = 0.0

        return cls(
            name=str(payload.get("name") or "Rule").strip()[:80],
            source_text=source_text,
            subject=subject,
            zone=str(payload.get("zone") or "any").strip() or "any",
            min_dwell_s=dwell,
            from_minute=from_minute,
            to_minute=to_minute,
            night_only=bool(payload.get("night_only")),
            min_confidence=confidence,
            channels=channels,
            compiled_by=compiled_by,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["channels"] = list(self.channels)
        d["window_label"] = self.window_label
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Rule":
        known = {f for f in cls.__dataclass_fields__}
        d = {k: v for k, v in d.items() if k in known}
        d["channels"] = tuple(d.get("channels") or ("screen",))
        return cls(**d)

    @property
    def window_label(self) -> str:
        if self.from_minute == 0 and self.to_minute >= 1439:
            return "any time"
        fmt = lambda m: f"{m // 60:02d}:{m % 60:02d}"  # noqa: E731
        return f"{fmt(self.from_minute)} to {fmt(self.to_minute)}"

    def explain(self) -> str:
        """The rule in a sentence, so the person can check the compilation."""
        who = "anything" if self.subject == "any" else f"a {self.subject}"
        where = {"any": "", "inside": " inside a motion zone", "outside": " outside every motion zone"}.get(
            self.zone, f" in zone {self.zone[:8]}"
        )
        when = "" if self.window_label == "any time" else f", between {self.window_label}"
        night = " and only at night" if self.night_only else ""
        dwell = f", if it stays at least {int(self.min_dwell_s)} seconds" if self.min_dwell_s else ""
        return f"Tell me when {who}{where} is seen{when}{night}{dwell}."
