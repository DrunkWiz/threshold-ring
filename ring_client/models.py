"""Typed views over the Ring Partner API's JSON:API payloads.

The API speaks JSON:API, so every useful field sits two levels down under
`data.attributes` and relationships are links rather than values. These
dataclasses flatten that once, at the edge, so nothing downstream has to know
the wire shape.

Every parser is defensive in the same way: a missing field becomes None rather
than a KeyError, because a device that reports no battery is normal and should
not crash a narration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _attrs(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return {}
    attrs = data.get("attributes")
    return attrs if isinstance(attrs, dict) else {}


@dataclass(frozen=True)
class Device:
    id: str
    name: str
    image_url: str | None = None

    @classmethod
    def from_json(cls, item: dict[str, Any]) -> "Device":
        attrs = item.get("attributes") or {}
        return cls(
            id=item.get("id", ""),
            name=attrs.get("name") or "Unnamed device",
            image_url=attrs.get("image_url"),
        )


@dataclass(frozen=True)
class Zone:
    """A motion zone, as normalised polygon vertices in [0, 1].

    Ring gives the vertices in image space with the origin top-left, so a
    point from a detector's bounding box can be tested against it directly
    once both are normalised. This is the one piece of geometry the API hands
    out and almost nobody uses.
    """

    id: str
    vertices: tuple[tuple[float, float], ...]

    @property
    def is_degenerate(self) -> bool:
        return len(self.vertices) < 3


@dataclass(frozen=True)
class Capabilities:
    motion_detection: bool
    snapshot: bool
    video_max_resolution: int | None
    video_codecs: tuple[str, ...]
    sensors: tuple[str, ...]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Capabilities":
        a = _attrs(payload)
        motion = a.get("motion_detection") or {}
        image = a.get("image_enhancements") or {}
        video = a.get("video") or {}
        # Sensor families are reported as null when absent, which is how the
        # Playground device reports every one of them.
        sensor_keys = (
            "flood_detection",
            "freeze_detection",
            "tamper_detection",
            "contact_detection",
            "smoke_detection",
            "glass_break_detection",
            "co_detection_listener",
        )
        sensors = tuple(k.replace("_detection", "").replace("_listener", "") for k in sensor_keys if a.get(k))
        return cls(
            motion_detection=bool(motion.get("configurations")),
            snapshot="snapshot" in (image.get("configurations") or []),
            video_max_resolution=video.get("max_resolution"),
            video_codecs=tuple(video.get("codecs") or ()),
            sensors=sensors,
            raw=a,
        )


@dataclass(frozen=True)
class Configurations:
    motion_enabled: bool
    zones: tuple[Zone, ...]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Configurations":
        a = _attrs(payload)
        motion = a.get("motion_detection") or {}
        zones = []
        for z in motion.get("motion_zones") or []:
            verts = []
            for v in z.get("vertices") or []:
                try:
                    verts.append((float(v["x"]), float(v["y"])))
                except (KeyError, TypeError, ValueError):
                    continue  # a malformed vertex drops out; the zone survives
            zones.append(Zone(id=z.get("id", ""), vertices=tuple(verts)))
        return cls(
            motion_enabled=str(motion.get("enabled", "")).lower() in ("on", "true", "1"),
            zones=tuple(zones),
            raw=a,
        )


@dataclass(frozen=True)
class Status:
    online: bool
    reported_at: str | None

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Status":
        a = _attrs(payload)
        return cls(online=bool(a.get("online")), reported_at=a.get("reported_at"))


@dataclass(frozen=True)
class User:
    id: str
    first_name: str | None
    last_name: str | None
    email: str | None

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "User":
        data = payload.get("data") or {}
        a = _attrs(payload)
        return cls(
            id=data.get("id", ""),
            first_name=a.get("first_name"),
            last_name=a.get("last_name"),
            email=a.get("email"),
        )
