"""An offline stand-in for the Ring Partner API.

Built from responses actually captured from the Playground on 20 Sep 2026, so
the shapes are real rather than imagined — including the parts that surprised
us, like history coming back empty and every sensor family reporting null.

Two reasons this exists. Tests must run with no key and no network, and the
Playground token dies after thirty minutes, which is not long enough to debug
in. Point the client at `Emulator().opener` and everything downstream behaves
the same.
"""

from __future__ import annotations

import json
import time
from typing import Any

DEVICE_ID = (
    "ava1.ring.device.5YFRWRIF34VGJ4S3I7MCOPNIOIVKPLWEA5XXGBDXEDI273XW3HR2"
    "2AZEFFCBBEBMHHMQV7A2LEX3VVYITH6RJNK6PJTEFDGO"
)
LOCATION_ID = (
    "ava1.ring.location.X4ARNMSLWIUKARQXN5J3Y6MIZEI3ECJ5AKSYKFF5OA26I3FWGT"
    "UMNPH5TG74ZY33K22FIJ3JSOY3OOSWEKIQCRDDWQLYMA4CI6ENGMPUJVVR5LZ3QCOHX6NYAM"
)

# The eight vertices the real Playground doorbell reports, origin top-left,
# normalised to [0, 1]. The whole rules engine is tested against these.
MOTION_ZONE_VERTICES = [
    {"x": 0, "y": 0},
    {"x": 0.5, "y": 0},
    {"x": 1, "y": 0},
    {"x": 1, "y": 0.6},
    {"x": 1, "y": 1},
    {"x": 0.5, "y": 1},
    {"x": 0, "y": 1},
    {"x": 0, "y": 0.6},
]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Emulator:
    """Serves the captured payloads. `fail_with` forces an error path."""

    def __init__(self, *, fail_with: int | None = None, history: list[dict[str, Any]] | None = None):
        self.fail_with = fail_with
        self.history = history or []
        self.calls: list[tuple[str, str]] = []

    def opener(self, method: str, url: str, headers: dict[str, str], body: bytes | None):
        path = url.split("api.amazonvision.com", 1)[-1]
        self.calls.append((method, path))

        if self.fail_with:
            return self.fail_with, b'{"errors":[{"code":"forced"}]}', {}
        if not headers.get("Authorization", "").startswith("Bearer "):
            return 401, b'{"errors":[{"code":"missing_bearer"}]}', {}

        payload = self._route(method, path, body)
        if payload is None:
            return 404, b'{"errors":[{"code":"not_found"}]}', {}
        if isinstance(payload, tuple):
            status, data, extra_headers = payload
            raw = data if isinstance(data, bytes) else json.dumps(data).encode()
            return status, raw, extra_headers
        return 200, json.dumps(payload).encode(), {}

    def _route(self, method: str, path: str, body: bytes | None):
        d = f"/v1/devices/{DEVICE_ID}"
        if method == "GET" and path == "/v1/devices":
            return {
                "data": [
                    {
                        "type": "devices",
                        "id": DEVICE_ID,
                        "attributes": {
                            "name": "Playground Device",
                            "image_url": "https://app-content.ring.com/shared/images/devices/square_device_images/DoorbellPro/rvdp_3x.png",
                        },
                        "relationships": {},
                    }
                ],
                "meta": {"time": _now()},
            }
        if method == "GET" and path == f"{d}/capabilities":
            return {
                "data": {
                    "type": "device-capabilities",
                    "id": "ava1.ring.device.capabilities.EMULATED",
                    "attributes": {
                        "battery_status": None,
                        "image_enhancements": {"configurations": ["color_night_vision", "privacy_zones", "snapshot"]},
                        "flood_detection": None,
                        "freeze_detection": None,
                        "tamper_detection": None,
                        "co_detection_listener": None,
                        "audio": {"customizable_slots": None, "supported_actions": None},
                        "motion_detection": {"configurations": ["enabled", "motion_zones"]},
                        "glass_break_detection": None,
                        "contact_detection": None,
                        "smoke_detection": None,
                        "video": {
                            "configurations": ["resolution_mode"],
                            "codecs": ["AVC"],
                            "ratio": "16:9",
                            "max_resolution": 1080,
                            "supported_resolutions": [1080],
                        },
                    },
                }
            }
        if method == "GET" and path == f"{d}/configurations":
            return {
                "data": {
                    "type": "device-configurations",
                    "id": "ava1.ring.device.configurations.EMULATED",
                    "attributes": {
                        "motion_detection": {
                            "enabled": "on",
                            "motion_zones": [
                                {"id": "f63ce706-67ef-4ae3-9447-bc3cf87d54c2", "vertices": MOTION_ZONE_VERTICES}
                            ],
                        },
                        "image_enhancements": {"color_night_vision": "off", "hdr": "off"},
                    },
                }
            }
        if method == "GET" and path == f"{d}/status":
            return {
                "data": {
                    "type": "device-status",
                    "id": "ava1.ring.device.status.EMULATED",
                    "attributes": {
                        "audio": {"snooze": {"active": None, "until": None}},
                        "state": None,
                        "reported_at": _now(),
                        "online": True,
                    },
                },
                "meta": {"time": _now()},
            }
        if method == "GET" and path == "/v1/users/me":
            return {
                "data": {
                    "type": "users",
                    "id": "ava1.ring.account.EMULATED",
                    "attributes": {
                        "first_name": "Playground",
                        "last_name": "User",
                        "email": "devportal_emulated@example.com",
                    },
                }
            }
        if method == "GET" and path == "/v1/locations":
            return {
                "data": [{"type": "locations", "id": LOCATION_ID, "attributes": {"country": "US", "state": "CA"}}],
                "meta": {"time": _now()},
            }
        if method == "GET" and path == f"/v1/history/devices/{DEVICE_ID}/events":
            # Empty, exactly as the real API answers for this device.
            return {"data": self.history}
        if method == "POST" and path == f"{d}/media/streaming/whep/sessions":
            answer = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=emulated\r\nt=0 0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\n"
            return (201, answer.encode(), {"Location": f"https://api.amazonvision.com{path}/emulated-session"})
        if method in ("POST", "PATCH", "PUT", "DELETE"):
            # Anything that writes is refused, because the read-only token
            # would be refused too. Better to learn that offline.
            return (403, {"errors": [{"code": "insufficient_scope"}]}, {})
        return None
