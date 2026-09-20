"""Everything the runtime reads from the environment, in one place."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8765
    db_path: str = "threshold.db"
    ring_token: str = ""
    ring_base_url: str = "https://api.amazonvision.com"
    ntfy_topic: str = ""
    offline: bool = False          # use the emulator instead of the real API
    device_id: str = ""            # pinned device, otherwise the first found

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Config":
        env = dict(os.environ if env is None else env)
        truthy = lambda k: str(env.get(k, "")).lower() in ("1", "true", "yes", "on")  # noqa: E731
        return cls(
            host=env.get("THRESHOLD_HOST") or "127.0.0.1",
            port=int(env.get("THRESHOLD_PORT") or 8765),
            db_path=env.get("THRESHOLD_DB") or "threshold.db",
            ring_token=env.get("RING_TOKEN", ""),
            ring_base_url=env.get("RING_BASE_URL") or "https://api.amazonvision.com",
            ntfy_topic=env.get("THRESHOLD_NTFY_TOPIC", ""),
            offline=truthy("THRESHOLD_OFFLINE"),
            device_id=env.get("RING_DEVICE_ID", ""),
        )
