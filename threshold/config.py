"""Everything the runtime reads from the environment, in one place."""

from __future__ import annotations

import os
from dataclasses import dataclass


def load_dotenv(path: str | None = None) -> None:
    """Fold a `.env` file into the environment, leaving anything already set.

    Only `scripts/demo.sh` used to do this, so keys written to `.env` were
    ignored in silence by `python -m threshold.server`: you got canned
    descriptions and nothing said why. Entry points call this, library code
    does not, which is what keeps the tests hermetic on a machine that has a
    real `.env` sitting in the repo.
    """
    if path is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, ".env")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError:
        return

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        # A real environment variable beats the file, so a one-off
        # `RING_TOKEN=... python -m threshold.server` still wins.
        os.environ.setdefault(key.strip(), value)


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
