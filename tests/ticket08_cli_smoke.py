"""Executable Ticket 8 CLI smoke test using localhost-only controlled services."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


class ControlledApi(BaseHTTPRequestHandler):
    state = {
        "id": "S1",
        "study_id": "STUDY-FIXTURE",
        "participant": "P-FIXTURE",
        "status": "AWAITING REVIEW",
        "started_at": "2026-01-01T00:00:00Z",
    }

    def _write(self, value: dict[str, Any]) -> None:
        raw = json.dumps(value).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path.startswith("/api/v1/messages/"):
            self._write({"results": [], "_links": {"self": {"href": self.path}}})
        elif "?" in self.path:
            self._write({"results": [self.state], "meta": {"count": 1}, "_links": {"self": {"href": self.path}}})
        else:
            self._write(self.state)

    def do_POST(self) -> None:
        self._write({"id": "CONTROLLED-MESSAGE"})

    def log_message(self, *_args: Any) -> None:
        pass


def run_command(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def main() -> None:
    root_repo = Path(__file__).resolve().parents[1]
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="ticket08-cli-") as temporary:
        root = Path(temporary)
        data_dir = root / "data"
        candidate = root / "candidate.jsonl"
        candidate.write_text(json.dumps({
            "candidate_key": "fixture-candidate",
            "pred_is_ctc": True,
            "audio_verify": {"verify_is_ctc": True},
            "tos_audio": {"outer_url": "http://127.0.0.1/fixture.wav"},
        }) + "\n", encoding="utf-8")
        consent = root / "consent.json"
        consent.write_text(json.dumps({"records": []}) + "\n", encoding="utf-8")
        api = ThreadingHTTPServer(("127.0.0.1", 0), ControlledApi)
        thread = threading.Thread(target=api.serve_forever, daemon=True)
        thread.start()
        try:
            api_base = f"http://127.0.0.1:{api.server_address[1]}/api/v1"
            config = {
                "study_id": "STUDY-FIXTURE",
                "data_dir": str(data_dir),
                "base_url": api_base,
                "token": "CONTROLLED_FIXTURE_ONLY",
                "auto_labels": [str(candidate)],
                "routine_policy": True,
                "activation_boundary": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                "verified_message_scope": {
                    "researcher_id": "RESEARCHER-FIXTURE",
                    "workspace_id": "WORKSPACE-FIXTURE",
                    "coverage_start": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                    "coverage_end": (now + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                    "workspace_visibility_verified": True,
                    "verification_note": "localhost controlled fixture",
                    "checked_at": now.isoformat().replace("+00:00", "Z"),
                    "expires_at": (now + timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                },
                "consent_evidence_path": str(consent),
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            report = {"status": "ok", "study_id": "STUDY-FIXTURE", "submissions": [{
                "session_id": "S1", "study_id": "STUDY-FIXTURE", "participant_id": "P-FIXTURE",
                "status": "AWAITING REVIEW", "classification": "awaiting_without_final_result",
                "proposed_action": "review_missing_result", "evidence": ["assignment"],
            }]}
            report_path = root / "report.json"
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            journal = root / "journal.jsonl"
            cli = [sys.executable, "-m", "prolific.ctc_verification_app.activation_cli", "--journal", str(journal)]
            preview = json.loads(run_command(cli + ["preview", "--report", str(report_path)], root_repo))
            approval = run_command(cli + [
                "approve", "--approval", str(data_dir / "approval.json"), "--study-id", "STUDY-FIXTURE",
                "--preview-sha256", preview["preview_sha256"], "--approved-by", "fixture-reviewer",
                "--routine-policy", "--preview-report", str(report_path),
            ], root_repo)
            status_before = run_command(cli + ["status"], root_repo)
            receiver = subprocess.Popen(cli + ["receiver", "--config", str(config_path), "--secret", "CONTROLLED_SECRET", "--port", "38991"], cwd=root_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(0.7)
            body = json.dumps({"event_type": "submission.status.change", "resource_id": "S1"}).encode("utf-8")
            timestamp = str(int(now.timestamp()))
            signature = base64.b64encode(hmac.new(b"CONTROLLED_SECRET", timestamp.encode() + body, hashlib.sha256).digest()).decode()
            request = urllib.request.Request(
                f"http://127.0.0.1:{receiver_port(receiver)}/", data=body, method="POST",
                headers={"X-Prolific-Request-Signature": signature, "X-Prolific-Request-Timestamp": timestamp, "X-Event-ID": "E1", "X-Timestamp": timestamp},
            )
            receiver_response = json.loads(urllib.request.urlopen(request, timeout=5).read())
            receiver.send_signal(signal.SIGTERM)
            receiver.wait(timeout=5)
            scheduler = subprocess.Popen(cli + ["scheduler", "--config", str(config_path), "--interval", "0.1"], cwd=root_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(0.5)
            scheduler.send_signal(signal.SIGTERM)
            scheduler.wait(timeout=5)
            disabled = run_command(cli + ["disable", "fixture stop"], root_repo)
            status_after = run_command(cli + ["status"], root_repo)
            restart_status = run_command(cli + ["status"], root_repo)
            output = {"preview": preview, "approval": json.loads(approval), "status_before": json.loads(status_before), "receiver_response": receiver_response, "scheduler_exit": scheduler.returncode, "disabled": json.loads(disabled), "status_after": json.loads(status_after), "restart_status": json.loads(restart_status), "controlled_api": True}
            print(json.dumps(output, sort_keys=True))
        finally:
            api.shutdown()
            api.server_close()
            thread.join(timeout=5)


def receiver_port(process: subprocess.Popen[str]) -> int:
    return 38991


if __name__ == "__main__":
    main()
