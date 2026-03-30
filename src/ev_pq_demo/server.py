from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import threading
from urllib.parse import unquote, urlparse
import webbrowser

from .scenarios import get_preset, list_presets
from .simulator import GLOSSARY, build_site_config, list_policy_metadata, run_simulation


STATIC_DIR = Path(__file__).resolve().parent / "static"


class DemoRequestHandler(BaseHTTPRequestHandler):
    server_version = "EVPQDemo/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/scenarios":
            self._send_json(
                {
                    "scenarios": [preset.to_dict() for preset in list_presets()],
                    "policies": list_policy_metadata(),
                    "glossary": GLOSSARY,
                }
            )
            return

        if path in {"/", "/index.html"}:
            self._serve_static("index.html")
            return

        if path.startswith("/static/"):
            relative = path.removeprefix("/static/")
            self._serve_static(relative)
            return

        self._send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/simulate":
            self._send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length) or b"{}")
            result = self._simulate(payload)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except json.JSONDecodeError:
            self._send_json({"error": "Request body must be valid JSON."}, status=HTTPStatus.BAD_REQUEST)
            return

        self._send_json(result)

    def log_message(self, format: str, *args) -> None:
        return

    def _simulate(self, payload: dict) -> dict:
        scenario_key = payload.get("scenario_key") or list_presets()[0].key
        preset = get_preset(str(scenario_key))

        duration_hours = max(int(payload.get("duration_hours", preset.default_duration_hours)), 1)
        step_minutes = max(int(payload.get("step_minutes", preset.default_step_minutes)), 1)
        seed = int(payload.get("seed", 7))
        policy_key = str(payload.get("policy", preset.default_policy))

        site_payload = dict(preset.recommended_site)
        site_payload.update(payload.get("site", {}))
        site = build_site_config(site_payload)

        sessions = preset.generator(seed, duration_hours)
        label = payload.get("label") or f"{preset.name} / {policy_key.replace('_', ' ').title()}"
        result = run_simulation(
            sessions,
            site,
            policy_key,
            step_minutes=step_minutes,
            duration_hours=duration_hours,
            label=label,
        )
        result["scenario"] = preset.to_dict()
        return result

    def _serve_static(self, relative_path: str) -> None:
        safe_relative = unquote(relative_path).lstrip("/")
        target = (STATIC_DIR / safe_relative).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists() or not target.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "Static asset not found")
            return

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)


def create_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), DemoRequestHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the EV charging + PQ demonstrator.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", default=8000, type=int, help="Port to listen on.")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not try to open a browser automatically.",
    )
    args = parser.parse_args(argv)

    server = create_server(args.host, args.port)
    browser_url = f"http://127.0.0.1:{args.port}"
    listen_url = f"http://{args.host}:{args.port}"

    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(browser_url)).start()

    print(f"EV Charging + PQ demonstrator running at {listen_url}")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()

    return 0

