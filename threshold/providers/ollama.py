"""A vision model running on this machine, through Ollama.

Here for two reasons. The practical one: Bedrock needs an account, and an
account can be inside an organisation whose policy forbids the call — which is
exactly what happened here. The better one: a doorbell that describes your
front door without sending the picture anywhere is a stronger position than
one that does, particularly for the caretaking case this is aimed at.

No dependency is added. Ollama is a separate program the user already runs;
this is plain HTTP to it over the standard library, and if it is not running
the rung drops out of the chain like any other.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .base import Provider, ProviderError
from .salvage import salvage_json

DEFAULT_HOST = "http://127.0.0.1:11434"


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        host: str = DEFAULT_HOST,
        timeout: float = 120.0,
        opener=None,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout
        self._opener = opener or self._urllib_open

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "OllamaProvider | None":
        # Opt-in by naming a model. Probing localhost on every run would be
        # cheap but surprising, and the model has to be chosen anyway: the
        # tag must be one that reports the "vision" capability.
        model = (env.get("THRESHOLD_OLLAMA_MODEL") or "").strip()
        if not model:
            return None
        return cls(model, host=env.get("THRESHOLD_OLLAMA_HOST") or DEFAULT_HOST)

    # -- transport ---------------------------------------------------------

    def _urllib_open(self, url: str, headers: dict[str, str], body: bytes):
        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except Exception as exc:
            raise ProviderError(
                f"could not reach Ollama at {self.host}: {exc}. Is it running?",
                kind="unreachable",
                retryable=True,
            ) from exc

    # -- interface ---------------------------------------------------------

    def complete_json(self, *, system: str, prompt: str, images=None, max_tokens: int = 1024) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            # Ollama takes bare base64 on the message, not content blocks.
            message["images"] = list(images)

        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, message],
            "stream": False,
            "format": "json",
            # Thinking off. num_predict caps thinking and answer together, so a
            # reasoning model spends the budget deliberating and returns an
            # empty content field — which arrives here as "no JSON object" and
            # sends you looking for a parsing bug. It is also three times
            # faster, and a doorbell wants predictable latency more than it
            # wants deliberation.
            "think": False,
            "options": {"temperature": 0, "num_predict": max_tokens},
        }

        status, raw = self._opener(
            f"{self.host}/api/chat",
            {"Content-Type": "application/json"},
            json.dumps(payload).encode("utf-8"),
        )
        text = raw.decode("utf-8", "replace")

        if status == 404:
            raise ProviderError(
                f"Ollama has no model tagged {self.model}. Pull it first, or set "
                "THRESHOLD_OLLAMA_MODEL to one that is installed.",
                kind="missing_model",
            )
        if status >= 400:
            raise ProviderError(f"Ollama returned {status}: {text[:300]}", kind="http", retryable=status >= 500)

        try:
            response = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("Ollama returned something that was not JSON", kind="malformed") from exc

        content = ((response.get("message") or {}).get("content")) or ""
        parsed = salvage_json(content)
        if parsed is None:
            raise ProviderError("the model did not return a JSON object", kind="malformed")
        return parsed
