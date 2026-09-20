"""The seam every model provider sits behind.

One method, `complete_json`, because everything Threshold asks a model for is
a structured object: a perception event, or a compiled rule. Narration is not
here on purpose — it is deterministic and needs no model at all.
"""

from __future__ import annotations

from typing import Any


class ProviderError(Exception):
    """A provider failed in a way the chain should step over."""

    def __init__(self, message: str, *, kind: str = "error", retryable: bool = False):
        super().__init__(message)
        self.kind = kind
        self.retryable = retryable


class Provider:
    name = "base"

    def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        images: list[str] | None = None,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "Provider | None":
        """Build from environment, or return None when unconfigured.

        Returning None rather than raising matters: a provider with no
        credentials should drop out of the chain locally, without a network
        call that will obviously fail.
        """
        raise NotImplementedError
