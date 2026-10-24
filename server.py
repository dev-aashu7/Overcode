"""
server.py
---------
Lightweight Python HTTP & API server for the MedVerify Web Application.
Connects the frontend (frontend/) directly to tinyfish_client.verify_policy().

Security & Architecture:
- Keeps TINYFISH_API_KEY strictly on the Python backend (never exposed to frontend code).
- Uses https://medverify-tpa-portal.vercel.app/ as the default configurable portal URL.
- Preserves tinyfish_client.verify_policy() and logs real verification telemetry.

Usage:
    python server.py
    # Then open http://localhost:8080 in your browser.
"""

import json
import mimetypes
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from tinyfish_client import DEFAULT_PORTAL_URL, load_env_file, verify_policy

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
RUNS_LOG_PATH = BASE_DIR / "runs_log.jsonl"
DEFAULT_PORT = int(os.getenv("MEDVERIFY_PORT", "8080"))


def _append_run_log(result: dict) -> None:
    """Append real backend verification runs to runs_log.jsonl for evaluation evidence."""
    try:
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "policy_id": result.get("policy_id"),
            "run_status": result.get("run_status"),
            "success": result.get("success"),
            "policy_status": result.get("policy_status"),
            "stopped_at_review": result.get("stopped_at_review"),
            "submitted": result.get("submitted"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "field_accuracy_verified": (result.get("field_accuracy") or {}).get("verified"),
        }
        with RUNS_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


class MedVerifyRequestHandler(BaseHTTPRequestHandler):
    """Serves the frontend static assets and /api/health + /api/verify JSON endpoints."""

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, file_path: Path) -> None:
        if not file_path.is_file():
            self.send_error(404, "File not found")
            return
        content = file_path.read_bytes()
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path

        if route == "/api/health":
            load_env_file()
            self._send_json(
                200,
                {
                    "status": "ok",
                    "environment": "SANDBOX",
                    "api_key_configured": bool(os.getenv("TINYFISH_API_KEY")),
                    "submission_lock": True,
                    "default_portal_url": os.getenv("MOCK_PORTAL_URL", DEFAULT_PORTAL_URL),
                },
            )
            return

        if route in ("/", "/index.html"):
            self._serve_static(FRONTEND_DIR / "index.html")
            return

        # Serve static files inside frontend/ safely
        rel_path = route.lstrip("/")
        candidate = (FRONTEND_DIR / rel_path).resolve()
        if str(candidate).startswith(str(FRONTEND_DIR.resolve())) and candidate.is_file():
            self._serve_static(candidate)
            return

        self.send_error(404, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/verify":
            self._send_json(404, {"success": False, "error": "Unknown API endpoint."})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(raw_body)
        except Exception as exc:
            self._send_json(
                400,
                {
                    "success": False,
                    "run_status": "INVALID_JSON",
                    "error": f"Invalid JSON request body: {exc}",
                    "submitted": False,
                },
            )
            return

        result = verify_policy(
            policy_id=data.get("policy_id", ""),
            diagnosis=data.get("diagnosis", ""),
            estimated_cost=data.get("estimated_cost", ""),
            portal_url=data.get("portal_url", DEFAULT_PORTAL_URL),
            room_category=data.get("room_category", "Semi-Private"),
            hospital_name=data.get("hospital_name", "Apollo Care Superspecialty Hospital"),
            doctor_name=data.get("doctor_name", "Dr. Rajesh K. Mehta"),
            use_sample_document=bool(data.get("use_sample_document", True)),
        )
        _append_run_log(result)
        self._send_json(200, result)

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        sys.stdout.write(f"[MedVerify] {self.address_string()} - {format % args}\n")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    server = ThreadingHTTPServer(("0.0.0.0", port), MedVerifyRequestHandler)
    print(f"MedVerify Web Server running at http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    main()
