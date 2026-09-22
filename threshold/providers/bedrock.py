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


def _aws_message(body: str) -> str:
    """The sentence AWS actually wrote, out of the JSON it wraps it in.

    Worth the trouble: a refusal can be a missing permission, a model that is
    not enabled, or an organisation's service control policy denying the whole
    action — and only AWS knows which. Guessing on its behalf sends people to
    fix the wrong thing.
    """
    try:
        parsed = json.loads(body)
    except (TypeError, ValueError):
        return body.strip()[:300]
    if isinstance(parsed, dict):
        for key in ("Message", "message", "errorMessage"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:300]
    return body.strip()[:300]


def _signing_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


class BedrockProvider(Provider):
    name = "bedrock"

    def __init__(
        self,
        access_key: str = "",
        secret_key: str = "",
        *,
        api_key: str = "",
        session_token: str | None = None,
        region: str = DEFAULT_REGION,
        model_id: str = DEFAULT_MODEL,
        timeout: float = 45.0,
        opener=None,
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.api_key = api_key
        self.session_token = session_token
        self.region = region
        self.model_id = model_id
        self.timeout = timeout
        self._opener = opener or self._urllib_open

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "BedrockProvider | None":
        # AWS_BEARER_TOKEN_BEDROCK is AWS's own name for a Bedrock API key, so
        # a key generated in the console works with no renaming. It wins over
        # an access key pair because it is the narrower credential.
        api_key = (env.get("AWS_BEARER_TOKEN_BEDROCK") or "").strip()
        ak = env.get("AWS_ACCESS_KEY_ID")
        sk = env.get("AWS_SECRET_ACCESS_KEY")
        if not api_key and not (ak and sk):
            return None  # unconfigured: drop out of the chain, no network call
        return cls(
            ak or "",
            sk or "",
            api_key=api_key,
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

    def _auth_headers(self, host: str, path: str, body: bytes) -> dict[str, str]:
        """Bearer token if there is one, otherwise sign the request.

        AWS added Bedrock API keys after this provider was written. They are a
        single value and a plain header, so they are the easier path and the
        one the console now pushes you towards; the SigV4 branch stays because
        IAM access keys are still what a long-lived deployment is given.
        """
        if self.api_key:
            return {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }

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
        return headers

    def _invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        host = f"bedrock-runtime.{self.region}.amazonaws.com"
        path = f"/model/{self.model_id}/invoke"
        url = f"https://{host}{path}"
        body = json.dumps(payload).encode("utf-8")

        headers = self._auth_headers(host, path, body)

        status, raw = self._opener(url, headers, body)
        text = raw.decode("utf-8", "replace")

        if status == 403:
            detail = _aws_message(text)
            raise ProviderError(
                "Bedrock refused the request; check the credential, the region, and that "
                "model access is enabled for this model id."
                + (f" AWS said: {detail}" if detail else ""),
                kind="forbidden",
            )
        if status == 429:
            raise ProviderError("Bedrock throttled the request", kind="throttled", retryable=True)
        if status >= 400:
            detail = _aws_message(text)
            # Bedrock returns 404 when an account has not filled in Anthropic's
            # use case form — an onboarding state reported as a missing
            # resource, which reads like a wrong model id and sends you
            # checking the one thing that is right. Seen on 23 Sep against an
            # account whose text call had already succeeded.
            if "use case details" in detail.lower():
                raise ProviderError(
                    "Bedrock wants Anthropic's use case details form filled in for this "
                    "account before it will answer, and reports that as a 404. Submit it "
                    f"in the Bedrock console, then wait 15 minutes. AWS said: {detail}",
                    kind="use_case_form",
                    retryable=True,
                )
            raise ProviderError(f"Bedrock returned {status}: {detail}", kind="http", retryable=status >= 500)
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
