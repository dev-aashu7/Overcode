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

from tinyfish_client import (
    DEFAULT_PORTAL_URL,
    TIMING_END_BOUNDARY,
    TIMING_START_BOUNDARY,
    load_env_file,
    verify_policy,
)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
RUNS_LOG_PATH = BASE_DIR / "runs_log.jsonl"
DEFAULT_PORT = int(os.getenv("MEDVERIFY_PORT", "8080"))

NON_LIVE_STATUSES = {
    "INVALID_INPUT",
    "INVALID_URL",
    "UNAUTHORIZED_PORTAL",
    "MISSING_API_KEY",
    "INVALID_JSON",
}

LIVE_RUN_STATUS: dict = {
    "state": "IDLE",
    "status": "Idle",
    "updated_at_utc": None,
}


def _update_live_run_status(state_code: str, status_text: str) -> None:
    """Update shared runtime status so /api/status can report 'Waiting for human check'."""
    LIVE_RUN_STATUS["state"] = state_code
    LIVE_RUN_STATUS["status"] = status_text
    LIVE_RUN_STATUS["updated_at_utc"] = datetime.now(timezone.utc).isoformat()


def _compute_live_timing_stats() -> dict:
    """
    Compute honest timing telemetry from runs_log.jsonl.
    If fewer than 3 live SDK runs exist, label as a single-run observation rather than
    claiming a statistically meaningful average or manual baseline comparison.
    """
    live_durations: list[float] = []
    if RUNS_LOG_PATH.is_file():
        try:
            for line in RUNS_LOG_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                status = str(row.get("run_status") or "")
                elapsed = row.get("elapsed_seconds")
                is_live = row.get("is_measured_live_run")
                if is_live is None:
                    is_live = status not in NON_LIVE_STATUSES and isinstance(elapsed, (int, float)) and elapsed >= 0.5
                if (
                    is_live
                    and row.get("success") is True
                    and row.get("stopped_at_review") is True
                    and isinstance(elapsed, (int, float))
                    and elapsed > 0
                ):
                    live_durations.append(float(elapsed))
        except Exception:
            pass

    count = len(live_durations)
    avg_sec = round(sum(live_durations) / count, 2) if count >= 5 else None
    if count == 0:
        label = "Single-run observation (no completed live runs logged yet)"
    elif count == 1:
        label = "Single-run observation (1 completed live run)"
    elif count < 5:
        label = f"Single-run observation ({count} completed live runs; <5 for average)"
    else:
        label = f"Measured across {count} completed live runs (avg {avg_sec}s)"

    return {
        "measured_live_runs_count": count,
        "average_live_elapsed_seconds": avg_sec,
        "observation_label": label,
        "start_boundary": TIMING_START_BOUNDARY,
        "end_boundary": TIMING_END_BOUNDARY,
        "manual_baseline_note": "No manual baseline measured in this environment",
    }


def _append_run_log(result: dict) -> None:
    """Append real backend verification runs to runs_log.jsonl for evaluation evidence."""
    try:
        acc = result.get("field_accuracy") or {}
        timing = result.get("timing") or {}
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "policy_id": result.get("policy_id"),
            "extracted_policy_id": result.get("extracted_policy_id"),
            "run_status": result.get("run_status"),
            "success": result.get("success"),
            "policy_status": result.get("policy_status"),
            "stopped_at_review": result.get("stopped_at_review"),
            "submitted": result.get("submitted"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "is_measured_live_run": timing.get("is_measured_live_run"),
            "field_accuracy_verified": acc.get("verified"),
            "total_checks": acc.get("total_checks"),
            "passed_count": acc.get("passed_count"),
            "mismatch_count": acc.get("mismatch_count"),
            "not_verified_count": acc.get("not_verified_count"),
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
                    "timing_stats": _compute_live_timing_stats(),
                    "live_run_status": dict(LIVE_RUN_STATUS),
                },
            )
            return

        if route == "/api/status":
            self._send_json(200, dict(LIVE_RUN_STATUS))
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

        _update_live_run_status("RUNNING_TINYFISH", "Running TinyFish Cloud Agent")
        try:
            result = verify_policy(
                policy_id=data.get("policy_id", ""),
                diagnosis=data.get("diagnosis", ""),
                estimated_cost=data.get("estimated_cost", ""),
                portal_url=data.get("portal_url", DEFAULT_PORTAL_URL),
                room_category=data.get("room_category", "Semi-Private"),
                hospital_name=data.get("hospital_name", "Apollo Care Superspecialty Hospital"),
                doctor_name=data.get("doctor_name", "Dr. Rajesh K. Mehta"),
                use_sample_document=bool(data.get("use_sample_document", True)),
                enable_playwright_fallback=bool(data.get("enable_playwright_fallback", False)),
                human_check_timeout_seconds=float(data.get("human_check_timeout_seconds", 300.0)),
                status_callback=_update_live_run_status,
            )
        finally:
            _update_live_run_status("IDLE", "Idle")
        _append_run_log(result)
        stats = _compute_live_timing_stats()
        if isinstance(result.get("timing"), dict):
            result["timing"]["measured_live_runs_count"] = stats["measured_live_runs_count"]
            result["timing"]["average_live_elapsed_seconds"] = stats["average_live_elapsed_seconds"]
            if result["timing"].get("is_measured_live_run"):
                result["timing"]["observation_label"] = stats["observation_label"]
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
