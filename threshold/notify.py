"""Getting an alert to a person who is not looking at the screen.

Three channels, and all three are real. The API is read-only, so Threshold
never claims to switch on a light it cannot switch on — what it can genuinely
do is speak, caption, and push to a phone, so that is what the rules act on.

Push goes through ntfy.sh, which needs no account and no key: you subscribe to
a topic on your phone and anything posted to it arrives. That it works with no
credentials is exactly why it is the right choice for a demo someone else has
to be able to run.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Delivery:
    channel: str
    ok: bool
    detail: str = ""


_HEADER_PUNCTUATION = {
    "—": "-",    # em dash — every caption contains one
    "–": "-",
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "…": "...",
    " ": " ",
}


def _header_safe(text: str) -> str:
    """Make a string safe to put in an HTTP header.

    Headers are latin-1, and the narration uses typographic punctuation on
    purpose: every caption is "<subject> — <action>". Encoding that em dash
    raised UnicodeEncodeError inside urllib, which arrived here as "push
    unreachable" — so the push channel failed on essentially every real
    notification, while working fine for any test message typed in ASCII.
    """
    for fancy, plain in _HEADER_PUNCTUATION.items():
        text = text.replace(fancy, plain)
    return text.encode("latin-1", "replace").decode("latin-1")


@dataclass
class Notifier:
    """`speech` and `screen` are delivered by the browser; recorded here so the
    log shows everything that was sent, in one place."""

    ntfy_topic: str | None = None
    ntfy_server: str = "https://ntfy.sh"
    timeout: float = 8.0
    log: list[Delivery] = field(default_factory=list)
    opener: Any = None

    def send(self, channels: tuple[str, ...] | list[str], *, title: str, body: str) -> list[Delivery]:
        out: list[Delivery] = []
        for channel in channels:
            if channel == "push":
                out.append(self._push(title, body))
            else:
                # Handed to the browser in the response payload.
                out.append(Delivery(channel=channel, ok=True, detail="delivered in the interface"))
        self.log.extend(out)
        return out

    def _push(self, title: str, body: str) -> Delivery:
        if not self.ntfy_topic:
            return Delivery("push", False, "no push topic configured (set THRESHOLD_NTFY_TOPIC)")
        url = f"{self.ntfy_server.rstrip('/')}/{self.ntfy_topic}"
        headers = {"Title": _header_safe(title)[:120], "Content-Type": "text/plain; charset=utf-8"}
        data = body.encode("utf-8")
        try:
            if self.opener:
                status, _ = self.opener(url, headers, data)
            else:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    status = resp.status
        except urllib.error.HTTPError as exc:
            return Delivery("push", False, f"push rejected with {exc.code}")
        except Exception as exc:
            return Delivery("push", False, f"push unreachable: {exc}")
        return Delivery("push", 200 <= status < 300, f"ntfy returned {status}")

    def to_dict(self) -> dict[str, Any]:
        return {"topic_configured": bool(self.ntfy_topic), "sent": [d.__dict__ for d in self.log[-20:]]}
