"""The application: one pipeline, three consumers.

    frames + trigger
        -> perception  (a model, once)
        -> memory      (record, and compare against the baseline)
        -> rules       (deterministic, over the real motion zones)
        -> narration   (deterministic)
        -> notify

Kept separate from the HTTP layer so the whole product can be exercised in a
test without a socket, which is most of why the suite runs in under a second.
"""

from __future__ import annotations

import time
from typing import Any

from ring_client import Emulator, RingClient, RingError, token_expiry, token_scopes
from ring_client.emulator import DEVICE_ID as EMULATED_DEVICE_ID

from .config import Config
from .events import Event
from .memory import Memory
from .narration import render
from .notify import Notifier
from .perception import Perception
from .providers import Chain, build_chain
from .rules import Rule, channels_for, compile_rule, evaluate_all
from .seed import describe, generate


class Threshold:
    def __init__(self, config: Config, *, chain: Chain | None = None, clock=time.time, opener=None):
        self.config = config
        self.clock = clock
        self.memory = Memory(config.db_path, clock=clock)
        self.chain = chain or Chain(build_chain())
        self.perception = Perception(self.chain, clock=clock)
        self.notifier = Notifier(ntfy_topic=config.ntfy_topic or None)
        self.rules: list[Rule] = []
        self.token: str = config.ring_token
        self._opener = opener
        self._device: Any = None
        self._zones: tuple = ()
        self._capabilities: dict[str, Any] = {}
        self._last_error: str = ""

    # -- Ring --------------------------------------------------------------

    def client(self) -> RingClient:
        if self.config.offline:
            return RingClient(self.token or "offline.eyJzY29wZXMiOltdfQ.x", opener=Emulator().opener)
        if not self.token:
            raise RingError("no Ring token yet; generate one in the Playground and paste it in")
        return RingClient(self.token, base_url=self.config.ring_base_url, opener=self._opener)

    def connect(self, token: str | None = None) -> dict[str, Any]:
        """Pick up a token, find the device, and cache the motion zones."""
        if token:
            self.token = token.strip()
        client = self.client()

        devices = client.devices()
        if not devices:
            raise RingError("this Ring account has no devices the API can see")
        device = next((d for d in devices if d.id == self.config.device_id), devices[0])

        self._device = device
        configurations = client.configurations(device.id)
        self._zones = configurations.zones
        capabilities = client.capabilities(device.id)
        status = client.status(device.id)

        self._capabilities = {
            "motion_detection": capabilities.motion_detection,
            "snapshot": capabilities.snapshot,
            "max_resolution": capabilities.video_max_resolution,
            "codecs": list(capabilities.video_codecs),
            "sensors": list(capabilities.sensors),
        }
        self._online = status.online

        return {
            "device": {"id": device.id, "name": device.name, "image_url": device.image_url},
            "online": status.online,
            "zones": [{"id": z.id, "vertices": [list(v) for v in z.vertices]} for z in self._zones],
            "capabilities": self._capabilities,
            "token": self.token_state(),
            "offline": self.config.offline,
        }

    def token_state(self) -> dict[str, Any]:
        if not self.token:
            return {"present": False, "seconds_left": 0, "scopes": []}
        expiry = token_expiry(self.token)
        left = max(0, int(expiry - self.clock())) if expiry else 0
        return {
            "present": True,
            "seconds_left": left,
            "expired": expiry is not None and left <= 0,
            "scopes": list(token_scopes(self.token)),
            # Said plainly, because the console does not say it anywhere.
            "read_only": "ava.v1:read" in token_scopes(self.token) and len(token_scopes(self.token)) == 1,
        }

    def whep(self, sdp_offer: str) -> tuple[str, str]:
        device = self._device
        if device is None:
            raise RingError("connect to the device before starting a stream")
        return self.client().start_whep_session(device.id, sdp_offer)

    @property
    def zone_names(self) -> dict[str, str]:
        if len(self._zones) == 1:
            return {self._zones[0].id: "the motion zone"}
        return {z.id: f"zone {i + 1}" for i, z in enumerate(self._zones)}

    # -- the pipeline ------------------------------------------------------

    def observe(self, *, frames: list[str], trigger: str = "motion") -> dict[str, Any]:
        device_id = self._device.id if self._device else (EMULATED_DEVICE_ID if self.config.offline else "")
        device_name = self._device.name if self._device else "the front door"

        event = self.perception.observe(
            frames=frames,
            trigger=trigger,
            zones=self._zones,
            device_id=device_id,
            device_name=device_name,
        )

        baseline = self.memory.baseline()
        anomalies = self.memory.check_event(event, baseline=baseline)
        self.memory.record(event)

        decisions = evaluate_all(self.rules, event)
        fired = [d for d in decisions if d.fired]
        channels = channels_for(decisions, self.rules)

        spoken = render(
            event,
            zone_names=self.zone_names,
            matched_rules=[d.rule_name for d in fired],
            anomaly=anomalies[0].message if anomalies else None,
        )

        deliveries = []
        if fired or anomalies:
            targets = channels or ("screen",)
            deliveries = [
                d.__dict__
                for d in self.notifier.send(targets, title=spoken["caption"], body=spoken["announcement"])
            ]

        return {
            "event": event.to_dict(),
            "narration": spoken,
            "decisions": [d.to_dict() for d in decisions],
            "anomalies": [a.__dict__ for a in anomalies],
            "deliveries": deliveries,
            "noteworthy": event.is_noteworthy or bool(fired) or bool(anomalies),
            "provider_attempts": self.chain.attempts,
            "latency_ms": round(self.perception.last_latency_ms or 0, 1),
        }

    # -- rules -------------------------------------------------------------

    def add_rule(self, text: str) -> dict[str, Any]:
        rule, attempts = compile_rule(text, self.chain)
        self.rules.append(rule)
        return {"rule": rule.to_dict(), "explanation": rule.explain(), "attempts": attempts}

    def remove_rule(self, rule_id: str) -> bool:
        before = len(self.rules)
        self.rules = [r for r in self.rules if r.id != rule_id]
        return len(self.rules) != before

    def preset_rules(self) -> None:
        """Three rules that make the product useful the moment it opens."""
        for text in (
            "Say out loud when a person is at the door",
            "Tell me if a vehicle stops in the driveway after dark",
            "Notify my phone if someone waits more than 30 seconds",
        ):
            self.add_rule(text)

    # -- history -----------------------------------------------------------

    def seed_history(self, days: int = 14) -> dict[str, Any]:
        self.memory.clear(source="seeded")
        device_id = self._device.id if self._device else ""
        events = generate(days=days, device_id=device_id, now=self.clock())
        self.memory.record_many(events)
        return {"seeded": len(events), "description": describe(events)}

    def state(self) -> dict[str, Any]:
        recent = self.memory.recent(limit=40)
        baseline = self.memory.baseline()
        silence = self.memory.check_silence()
        return {
            "token": self.token_state(),
            "offline": self.config.offline,
            "device": (
                {"id": self._device.id, "name": self._device.name, "image_url": self._device.image_url}
                if self._device
                else None
            ),
            "zones": [{"id": z.id, "vertices": [list(v) for v in z.vertices]} for z in self._zones],
            "capabilities": self._capabilities,
            "online": getattr(self, "_online", None),
            "rules": [r.to_dict() for r in self.rules],
            "events": [e.to_dict() for e in recent],
            "counts": {
                "total": self.memory.count(),
                "seeded": self.memory.count(source="seeded"),
                "live": self.memory.count() - self.memory.count(source="seeded"),
            },
            "baseline": baseline,
            "silence": silence.__dict__ if silence else None,
            "providers": self.chain.names,
            "push_configured": bool(self.config.ntfy_topic),
            "last_error": self._last_error,
        }
