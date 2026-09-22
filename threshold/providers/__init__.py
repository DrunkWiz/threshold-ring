"""Model providers and the chain that walks them.

The shape is deliberate and comes from a previous hackathon: a provider that
cannot be built is skipped without a network call, a provider that fails
mid-turn steps aside for the next, and the first one that answers wins. What
is *not* a fall-through is a bounded outcome we engineered ourselves — a
refusal, or a cap we set — because re-running that on another model spends a
second quota to arrive in the same place.
"""

from __future__ import annotations

import os
from typing import Any

from .base import Provider, ProviderError
from .bedrock import BedrockProvider
from .fake import FakeProvider
from .ollama import OllamaProvider
from .salvage import salvage_json

__all__ = [
    "Provider",
    "ProviderError",
    "BedrockProvider",
    "OllamaProvider",
    "FakeProvider",
    "salvage_json",
    "build_chain",
    "Chain",
]

_REGISTRY: dict[str, type[Provider]] = {
    "bedrock": BedrockProvider,
    "ollama": OllamaProvider,
    "fake": FakeProvider,
}


def build_chain(env: dict[str, str] | None = None) -> list[Provider]:
    """Providers in the order they should be tried.

    `THRESHOLD_PROVIDER` always goes first when it is configured, then
    `THRESHOLD_PROVIDER_CHAIN`. Anything without credentials drops out here,
    locally, rather than failing later over the network.
    """
    env = dict(os.environ if env is None else env)
    order: list[str] = []
    primary = env.get("THRESHOLD_PROVIDER", "").strip()
    if primary:
        order.append(primary)
    for name in (env.get("THRESHOLD_PROVIDER_CHAIN") or "bedrock,ollama,fake").split(","):
        name = name.strip()
        if name and name not in order:
            order.append(name)

    chain: list[Provider] = []
    for name in order:
        factory = _REGISTRY.get(name)
        if factory is None:
            continue
        built = factory.from_env(env)
        if built is not None:
            chain.append(built)

    # The fake is always the last rung. Without it a missing key means a dead
    # product; with it the product degrades to canned answers and says so.
    if not any(p.name == "fake" for p in chain):
        chain.append(FakeProvider())
    return chain


class Chain:
    """Runs a request down the chain and records what happened on each rung."""

    def __init__(self, providers: list[Provider]):
        if not providers:
            raise ValueError("a chain needs at least one provider")
        self.providers = providers
        self.attempts: list[dict[str, Any]] = []

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.providers]

    def complete_json(self, **kwargs) -> tuple[dict[str, Any], str]:
        self.attempts = []
        last: ProviderError | None = None
        for provider in self.providers:
            try:
                result = provider.complete_json(**kwargs)
            except ProviderError as exc:
                self.attempts.append({"provider": provider.name, "ok": False, "reason": f"{exc.kind}: {exc}"})
                last = exc
                continue
            except Exception as exc:  # a provider bug should not end the turn
                self.attempts.append({"provider": provider.name, "ok": False, "reason": f"crashed: {exc}"})
                last = ProviderError(str(exc))
                continue
            self.attempts.append({"provider": provider.name, "ok": True})
            return result, provider.name
        raise last or ProviderError("every provider failed")
