"""Amazon Bedrock, signed by hand with SigV4.

No boto3. Signing a request is about sixty lines of hmac and the payload is
plain JSON, so the whole runtime stays dependency-free — which also means the
thing a judge clones runs with nothing but a Python install.

Uses the Anthropic Messages format on Bedrock's `invoke` endpoint, which is
what carries images.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import Provider, ProviderError
from .salvage import salvage_json

DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
DEFAULT_REGION = "us-east-1"


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


class BedrockProvider(Provider):
    name = "bedrock"

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        *,
        session_token: str | None = None,
        region: str = DEFAULT_REGION,
        model_id: str = DEFAULT_MODEL,
        timeout: float = 45.0,
        opener=None,
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        self.region = region
        self.model_id = model_id
        self.timeout = timeout
        self._opener = opener or self._urllib_open

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "BedrockProvider | None":
        ak = env.get("AWS_ACCESS_KEY_ID")
        sk = env.get("AWS_SECRET_ACCESS_KEY")
        if not ak or not sk:
            return None  # unconfigured: drop out of the chain, no network call
        return cls(
            ak,
            sk,
            session_token=env.get("AWS_SESSION_TOKEN"),
            region=env.get("AWS_REGION") or DEFAULT_REGION,
            model_id=env.get("THRESHOLD_BEDROCK_MODEL") or DEFAULT_MODEL,
        )

    # -- transport ---------------------------------------------------------

    def _urllib_open(self, url: str, headers: dict[str, str], body: bytes):
        req = urllib.request.Request(url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except Exception as exc:
            raise ProviderError(f"could not reach Bedrock: {exc}", kind="unreachable", retryable=True) from exc

    def _invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        host = f"bedrock-runtime.{self.region}.amazonaws.com"
        path = f"/model/{self.model_id}/invoke"
        url = f"https://{host}{path}"
        body = json.dumps(payload).encode("utf-8")

        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        payload_hash = hashlib.sha256(body).hexdigest()
        canonical_headers = f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        if self.session_token:
            canonical_headers += f"x-amz-security-token:{self.session_token}\n"
            signed_headers += ";x-amz-security-token"

        canonical_request = "\n".join(
            ["POST", urllib.parse.quote(path, safe="/-_.~"), "", canonical_headers, signed_headers, payload_hash]
        )
        scope = f"{date_stamp}/{self.region}/bedrock/aws4_request"
        to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signature = hmac.new(
            _signing_key(self.secret_key, date_stamp, self.region, "bedrock"),
            to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Amz-Date": amz_date,
            "X-Amz-Content-Sha256": payload_hash,
            "Authorization": (
                f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
                f"SignedHeaders={signed_headers}, Signature={signature}"
            ),
        }
        if self.session_token:
            headers["X-Amz-Security-Token"] = self.session_token

        status, raw = self._opener(url, headers, body)
        text = raw.decode("utf-8", "replace")

        if status == 403:
            raise ProviderError(
                "Bedrock refused the request; check the key, the region, and that "
                "model access is enabled for this model id",
                kind="forbidden",
            )
        if status == 429:
            raise ProviderError("Bedrock throttled the request", kind="throttled", retryable=True)
        if status >= 400:
            raise ProviderError(f"Bedrock returned {status}: {text[:300]}", kind="http", retryable=status >= 500)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProviderError("Bedrock returned something that was not JSON", kind="malformed") from exc

    # -- interface ---------------------------------------------------------

    def complete_json(self, *, system: str, prompt: str, images=None, max_tokens: int = 1024) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        for image_b64 in images or []:
            content.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64},
                }
            )
        content.append({"type": "text", "text": prompt})

        response = self._invoke(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": content}],
            }
        )

        text = ""
        for block in response.get("content") or []:
            if block.get("type") == "text":
                text += block.get("text") or ""

        parsed = salvage_json(text)
        if parsed is None:
            raise ProviderError("the model did not return a JSON object", kind="malformed")
        return parsed
