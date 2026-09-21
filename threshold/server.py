"""HTTP for the browser, standard library only.

The browser has to own the WebRTC peer connection — that is the only place a
WHEP session can live — but the Ring token must not go anywhere near the page.
So the SDP offer comes here, this process signs it with the token, and the
answer goes back. The token never reaches JavaScript.

`http.server` rather than a framework, for the same reason there are no
runtime dependencies anywhere else: `git clone && python -m threshold.server`
has to work on a machine with nothing installed, including a judge's.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ring_client import RingError

from .app import Threshold
from .config import Config, load_dotenv

WEB_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
MAX_BODY = 12 * 1024 * 1024  # a couple of JPEG frames, with room to spare


class Handler(BaseHTTPRequestHandler):
    server_version = "Threshold/1.0"
    app: Threshold = None  # type: ignore[assignment]
    lock = threading.Lock()

    # -- plumbing ----------------------------------------------------------

    def log_message(self, fmt, *args):  # quieter, and on one line
        print(f"  {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    def _send(self, status: int, payload: Any, content_type: str = "application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("request body too large")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON body: {exc}") from exc

    def _read_text(self) -> str:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length).decode("utf-8") if length > 0 else ""

    # -- routes ------------------------------------------------------------

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/state":
            return self._guard(lambda: self._send(200, self.app.state()))
        if path == "/api/health":
            return self._send(200, {"ok": True, "offline": self.app.config.offline})
        return self._static(path)

    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/api/connect":
            return self._guard(lambda: self._send(200, self.app.connect(self._read_json().get("token"))))

        if path == "/api/observe":
            def run():
                body = self._read_json()
                frames = body.get("frames") or []
                if not frames:
                    return self._send(400, {"error": "no frames were sent"})
                # Accept data URLs as well as bare base64, because that is what
                # canvas.toDataURL gives you and stripping it in two places
                # invites one of them to be forgotten.
                frames = [f.split(",", 1)[-1] if f.startswith("data:") else f for f in frames][:3]
                self._send(200, self.app.observe(frames=frames, trigger=body.get("trigger") or "motion"))

            return self._guard(run)

        if path == "/api/rules":
            def run():
                text = (self._read_json().get("text") or "").strip()
                if not text:
                    return self._send(400, {"error": "write the rule as a sentence"})
                self._send(200, self.app.add_rule(text))

            return self._guard(run)

        if path == "/api/seed":
            return self._guard(lambda: self._send(200, self.app.seed_history(int(self._read_json().get("days") or 14))))

        if path == "/api/whep":
            def run():
                offer = self._read_text()
                if not offer.strip():
                    return self._send(400, {"error": "no SDP offer"})
                answer, location = self.app.whep(offer)
                self.send_response(201)
                self.send_header("Content-Type", "application/sdp")
                self.send_header("Location", location)
                self.send_header("Content-Length", str(len(answer.encode())))
                self.end_headers()
                self.wfile.write(answer.encode())

            return self._guard(run)

        return self._send(404, {"error": "no such endpoint"})

    def do_DELETE(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/rules/"):
            rule_id = path.rsplit("/", 1)[-1]
            return self._guard(lambda: self._send(200, {"removed": self.app.remove_rule(rule_id)}))
        return self._send(404, {"error": "no such endpoint"})

    # -- helpers -----------------------------------------------------------

    def _guard(self, fn):
        """One place where every failure becomes a sentence a person can act on."""
        with self.lock:
            try:
                return fn()
            except RingError as exc:
                self.app._last_error = str(exc)
                return self._send(
                    400,
                    {"error": str(exc), "kind": type(exc).__name__, "token": self.app.token_state()},
                )
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception as exc:  # noqa: BLE001
                traceback.print_exc()
                return self._send(500, {"error": f"unexpected failure: {exc}"})

    def _static(self, path: str):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_ROOT, rel))
        if not full.startswith(WEB_ROOT) or not os.path.isfile(full):
            return self._send(404, {"error": "not found"})
        content_type = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as fh:
            self._send(200, fh.read(), content_type)


def serve(config: Config | None = None) -> None:
    if config is None:
        load_dotenv()
    config = config or Config.from_env()
    app = Threshold(config)
    app.preset_rules()
    Handler.app = app

    if config.offline:
        app.connect()
        app.seed_history()

    httpd = ThreadingHTTPServer((config.host, config.port), Handler)
    mode = "offline (emulated Ring API)" if config.offline else "live"
    print(f"Threshold listening on http://{config.host}:{config.port}  [{mode}]")
    print(f"Model providers: {', '.join(app.chain.names)}")
    if not config.offline and not config.ring_token:
        print("No RING_TOKEN set — paste a Playground token in the interface.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        httpd.server_close()
        app.memory.close()


if __name__ == "__main__":
    serve()
