"""Errors raised by the Ring client.

Every failure mode the Partner API has shown us gets its own class, because
"something went wrong" is not an answer you can act on at three in the morning
while recording a demo.
"""


class RingError(Exception):
    """Base class. Carries the HTTP status and the body we could not parse."""

    def __init__(self, message: str, *, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class TokenExpired(RingError):
    """The bearer token's `exp` has passed, or the API said so.

    Checked locally before the request goes out, so a dead token costs no
    round trip and the interface can say "generate a new one" instead of
    relaying a 401 the person cannot interpret.
    """


class TokenInvalid(RingError):
    """A 401 that is not an expiry: malformed token, wrong audience, revoked."""


class Forbidden(RingError):
    """A 403.

    Usually means the token's scopes do not cover this call. The Playground
    token carries only `ava.v1:read`, so every write lands here.
    """


class NotFound(RingError):
    """A 404: no such device, or an endpoint that does not exist."""


class RateLimited(RingError):
    """A 429. `retry_after` is seconds, when the server bothered to say."""

    def __init__(self, message: str, *, status=None, body="", retry_after: float | None = None):
        super().__init__(message, status=status, body=body)
        self.retry_after = retry_after


class Unreachable(RingError):
    """The request never got an HTTP answer: DNS, TLS, timeout, proxy refusal.

    Distinct from every status above on purpose. An unreachable API is an
    environment problem (egress policy, offline laptop) and the fix is not the
    same as the fix for a 403.
    """
