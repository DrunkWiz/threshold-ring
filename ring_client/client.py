"""A typed client for the Ring Partner API, standard library only.

Ring ships no SDK. This is the smallest thing that makes the API pleasant to
use from Python: one class, explicit errors, no dependencies, and a transport
seam so the whole suite can run offline against the emulator.

Base URL is `https://api.amazonvision.com`. Note that event history lives
under `/v1/history/devices/{id}/events`, not under the device resource where
you would look for it first.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable

from .errors import (
    Forbidden,
    NotFound,
    RateLimited,
    RingError,
    TokenExpired,
    TokenInvalid,
    Unreachable,
)
from .models import Capabilities, Configurations, Device, Status, User

BASE_URL = "https://api.amazonvision.com"
USER_AGENT = "threshold-ring-client/1.0 (+https://github.com/)"


def token_expiry(token: str) -> float | None:
    """Read `exp` out of a JWT without verifying it.

    We are not authenticating anything here — the server does that. We only
    want to know when to stop sending a token that is already dead, so the
    interface can show a countdown and say "generate a new one" before the
    demo falls over on camera.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        exp = claims.get("exp")
        return float(exp) if exp is not None else None
    except Exception:
        return None


def token_scopes(token: str) -> tuple[str, ...]:
    """The scopes a token carries.

    Worth surfacing: the Playground token is read-only (`ava.v1:read`) and
    nothing in the console says so. Knowing up front turns a baffling 403 into
    an explained one.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return tuple(claims.get("scopes") or ())
    except Exception:
        return ()


class RingClient:
    """Read access to one Ring account's devices.

    `opener` exists so tests (and the offline emulator) can swap the transport
    without monkeypatching urllib. It takes (method, url, headers, body) and
    returns (status, body_bytes, headers).
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 20.0,
        max_retries: int = 3,
        opener: Callable[..., tuple[int, bytes, dict[str, str]]] | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._opener = opener or self._urllib_open
        self._clock = clock
        self._sleep = sleep

    # -- transport ---------------------------------------------------------

    def _urllib_open(self, method: str, url: str, headers: dict[str, str], body: bytes | None):
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as exc:  # an HTTP answer, just not a happy one
            return exc.code, exc.read(), dict(exc.headers or {})
        except Exception as exc:  # no HTTP answer at all
            raise Unreachable(f"could not reach {url}: {exc}") from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        accept: str = "application/json",
    ) -> tuple[int, bytes, dict[str, str]]:
        expiry = token_expiry(self.token)
        if expiry is not None and expiry <= self._clock():
            raise TokenExpired(
                "the Ring token expired; Playground tokens last 30 minutes",
                status=401,
            )

        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": accept,
            "User-Agent": USER_AGENT,
        }
        if body is not None:
            headers["Content-Type"] = content_type

        attempt = 0
        while True:
            attempt += 1
            status, raw, resp_headers = self._opener(method, url, headers, body)
            if status == 429 and attempt <= self.max_retries:
                # Ring documents 100 requests per second. Back off rather than
                # hammering, and honour Retry-After when it is given.
                retry_after = resp_headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 0.5 * (2 ** (attempt - 1))
                self._sleep(delay)
                continue
            if status >= 500 and attempt <= self.max_retries:
                self._sleep(0.5 * (2 ** (attempt - 1)))
                continue
            return status, raw, resp_headers

    def _json(self, method: str, path: str, *, body: bytes | None = None) -> dict[str, Any]:
        status, raw, headers = self._request(method, path, body=body)
        text = raw.decode("utf-8", "replace")

        if status == 401:
            # Told apart deliberately: an expired token is the person's cue to
            # press a button, an invalid one means the token is wrong.
            if "expire" in text.lower():
                raise TokenExpired("the Ring token expired", status=status, body=text)
            raise TokenInvalid("the Ring token was rejected", status=status, body=text)
        if status == 403:
            scopes = ", ".join(token_scopes(self.token)) or "none"
            raise Forbidden(
                f"the API refused this call; the token's scopes are [{scopes}] "
                "and Playground tokens are read-only",
                status=status,
                body=text,
            )
        if status == 404:
            raise NotFound(f"no such resource: {path}", status=status, body=text)
        if status == 429:
            raise RateLimited("rate limited by the Ring API", status=status, body=text)
        if status >= 400:
            raise RingError(f"Ring API returned {status}", status=status, body=text)

        if not text.strip():
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            # An HTML error page from a proxy is the usual cause, and it is
            # worth saying so rather than reporting a JSON error.
            raise RingError(
                "the Ring API returned something that was not JSON "
                "(a proxy or captive portal usually causes this)",
                status=status,
                body=text[:500],
            ) from exc

    # -- resources ---------------------------------------------------------

    def devices(self) -> list[Device]:
        payload = self._json("GET", "/v1/devices")
        return [Device.from_json(item) for item in payload.get("data") or []]

    def capabilities(self, device_id: str) -> Capabilities:
        return Capabilities.from_json(self._json("GET", f"/v1/devices/{device_id}/capabilities"))

    def configurations(self, device_id: str) -> Configurations:
        return Configurations.from_json(self._json("GET", f"/v1/devices/{device_id}/configurations"))

    def status(self, device_id: str) -> Status:
        return Status.from_json(self._json("GET", f"/v1/devices/{device_id}/status"))

    def user(self) -> User:
        return User.from_json(self._json("GET", "/v1/users/me"))

    def locations(self) -> list[dict[str, Any]]:
        return list(self._json("GET", "/v1/locations").get("data") or [])

    def history(self, device_id: str) -> list[dict[str, Any]]:
        """Event history for a device.

        Returns an empty list for the Playground device even after firing a
        simulated event, which is why Threshold keeps its own history.
        """
        return list(self._json("GET", f"/v1/history/devices/{device_id}/events").get("data") or [])

    # -- live video --------------------------------------------------------

    def start_whep_session(self, device_id: str, sdp_offer: str) -> tuple[str, str]:
        """Open a WHEP session and return (sdp_answer, session_location).

        This is the one call that is not read-only in spirit, and it works with
        a Playground token anyway. The SDP offer comes from the browser, which
        is the only place a WebRTC peer connection can live; the token stays
        here on the server.
        """
        status, raw, headers = self._request(
            "POST",
            f"/v1/devices/{device_id}/media/streaming/whep/sessions",
            body=sdp_offer.encode("utf-8"),
            content_type="application/sdp",
            accept="application/sdp",
        )
        text = raw.decode("utf-8", "replace")
        if status == 403:
            raise Forbidden("the API refused to open a WHEP session", status=status, body=text)
        if status not in (200, 201):
            raise RingError(f"WHEP session failed with {status}", status=status, body=text)
        location = headers.get("Location") or headers.get("location") or ""
        return text, location
