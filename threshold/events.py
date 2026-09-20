"""The one event shape that everything downstream consumes.

Perception produces it, memory stores it, rules match on it, narration reads
it. Keeping a single schema is what makes three features one product: change
this and all three change together, which is the point.

Validation is strict and total. A model that returns a subject we do not know
gets coerced to "unknown" rather than propagating a novel string into the
rules engine, where it would silently match nothing forever.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

SUBJECTS = ("person", "vehicle", "animal", "package", "nothing", "unknown")
TRIGGERS = ("motion", "package", "vehicle", "ding", "manual")


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


@dataclass
class Event:
    """One thing that happened at the door."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    at: float = field(default_factory=time.time)
    trigger: str = "motion"
    subject: str = "unknown"
    descriptors: tuple[str, ...] = ()
    action: str = ""
    point: tuple[float, float] | None = None
    zone_ids: tuple[str, ...] = ()
    dwell_s: float = 0.0
    night: bool = False
    confidence: float = 0.0
    summary: str = ""
    source: str = "live"          # live | seeded — never conflated
    provider: str = ""            # which model rung answered
    device_id: str = ""

    @classmethod
    def from_model(cls, payload: dict[str, Any], *, trigger: str = "motion", **extra) -> "Event":
        subject = str(payload.get("subject") or "unknown").lower().strip()
        if subject not in SUBJECTS:
            subject = "unknown"

        descriptors = payload.get("descriptors") or []
        if isinstance(descriptors, str):
            descriptors = [descriptors]
        descriptors = tuple(str(d).strip() for d in descriptors if str(d).strip())[:6]

        point = None
        raw_point = payload.get("point")
        if isinstance(raw_point, dict) and "x" in raw_point and "y" in raw_point:
            point = (_clamp(raw_point.get("x"), 0, 1, 0.5), _clamp(raw_point.get("y"), 0, 1, 0.5))

        return cls(
            trigger=trigger if trigger in TRIGGERS else "motion",
            subject=subject,
            descriptors=descriptors,
            action=str(payload.get("action") or "").strip()[:200],
            point=point,
            dwell_s=_clamp(payload.get("dwell_s"), 0, 3600, 0.0),
            night=bool(payload.get("night")),
            confidence=_clamp(payload.get("confidence"), 0, 1, 0.0),
            summary=str(payload.get("summary") or "").strip()[:400],
            **extra,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["descriptors"] = list(self.descriptors)
        d["zone_ids"] = list(self.zone_ids)
        d["point"] = list(self.point) if self.point else None
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        d = dict(d)
        d["descriptors"] = tuple(d.get("descriptors") or ())
        d["zone_ids"] = tuple(d.get("zone_ids") or ())
        point = d.get("point")
        d["point"] = tuple(point) if point else None
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @property
    def is_noteworthy(self) -> bool:
        """Whether this is worth a person's attention at all.

        The default answer for a doorbell is no. Eleven of twelve alerts are a
        cat, and a system that forwards all twelve is the thing people mute.
        """
        if self.subject in ("nothing", "animal"):
            return False
        if self.subject == "unknown" and self.confidence < 0.4:
            return False
        return True
