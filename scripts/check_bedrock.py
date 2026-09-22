#!/usr/bin/env python3
"""Ask Bedrock one question and say plainly what went wrong if it will not answer.

Wrong key, wrong region and model-access-not-enabled all surface in the app as
the same thing — a canned description — because the chain is built to degrade
quietly. That is right for a demo and useless for debugging, so this separates
them before a 30-minute Ring token is spent finding out.

    py scripts/check_bedrock.py          # Windows
    python3 scripts/check_bedrock.py     # macOS, Linux

Credentials come from the environment, or from .env if one is there.
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from threshold.config import load_dotenv  # noqa: E402
from threshold.providers.base import ProviderError  # noqa: E402
from threshold.providers.bedrock import BedrockProvider  # noqa: E402

# What to suggest for each way the provider gives up. The 403 is the one worth
# spelling out: model access is off by default in a new AWS account, so the
# likeliest first run looks exactly like a bad password.
HINTS = {
    "forbidden": [
        "Check the key can call bedrock:InvokeModel - AmazonBedrockFullAccess is the blunt fix.",
        "Anthropic models may ask a first-time user for use case details before answering.",
        "The Model access console page is retired: models enable themselves on first invoke.",
    ],
    "http": [
        "A 400 here usually means the model id is not available in this region.",
        "The default id is a cross-region profile needing us-east-1, us-east-2 or us-west-2.",
    ],
    "unreachable": [
        "Bedrock could not be reached at all — check the network or a proxy.",
    ],
    "throttled": [
        "Throttled rather than refused, so the credentials are fine. Try again.",
    ],
}


def main() -> int:
    load_dotenv()
    provider = BedrockProvider.from_env(dict(os.environ))
    if provider is None:
        print("No Bedrock credentials found.")
        print()
        print("Set AWS_BEARER_TOKEN_BEDROCK to a Bedrock API key from the console,")
        print("or AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY for an IAM access key.")
        print("Either the environment or a .env file beside the README will do.")
        return 1

    print(f"region  {provider.region}")
    print(f"model   {provider.model_id}")
    print(f"auth    {'Bedrock API key' if provider.api_key else 'IAM access key, SigV4'}")
    print("asking Bedrock for one line of JSON...")

    started = time.monotonic()
    try:
        answer = provider.complete_json(
            system="You reply with JSON and nothing else.",
            prompt='Reply with exactly {"ok": true}',
            max_tokens=64,
        )
    except ProviderError as exc:
        elapsed = (time.monotonic() - started) * 1000
        print()
        print(f"Bedrock did not answer ({exc.kind}, after {elapsed:.0f} ms):")
        print(f"  {exc}")
        for hint in HINTS.get(exc.kind, []):
            print(f"  - {hint}")
        return 1

    elapsed = (time.monotonic() - started) * 1000
    print()
    print(f"Bedrock answered in {elapsed:.0f} ms: {answer}")
    print()
    print("Credentials, region and model access are all good.")
    print("This is a text round-trip and is not the number to quote: a frame is")
    print("much larger, and the app reports its own latency with each description.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
