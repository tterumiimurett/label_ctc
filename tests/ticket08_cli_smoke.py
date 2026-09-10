"""Executable localhost-only Ticket 8 CLI smoke test and fault regression."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import socket
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
    state: dict[str, Any] = {}
    post_count = 0

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
        type(self).post_count += 1
        self._write({"id": "CONTROLLED-MESSAGE"})

    def log_message(self, *_args: Any) -> None:
        pass


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run_command(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def wait_for_port(process: subprocess.Popen[str], port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"receiver exited early ({process.returncode}): {stderr}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("receiver readiness deadline exceeded")


def wait_for_periodic(events_path: Path, before: int, process: subprocess.Popen[str], timeout: float = 8.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise RuntimeError(f"scheduler exited early ({process.returncode}): {stderr}")
        if events_path.exists():
            state = json.loads(events_path.read_text(encoding="utf-8"))
            runs = state.get("periodic_runs", [])
            if len(runs) > before:
                return state
        time.sleep(0.05)
    raise RuntimeError("scheduler periodic cycle deadline exceeded")


def stop_process(process: subprocess.Popen[str] | None) -> tuple[int | None, str, str]:
    if process is None:
        return None, "", ""
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    stdout = process.stdout.read() if process.stdout else ""
    stderr = process.stderr.read() if process.stderr else ""
    return process.returncode, stdout, stderr


def signed_request(port: int, now: datetime, event_id: str) -> dict[str, Any]:
    body = json.dumps({"event_type": "submission.status.change", "resource_id": "S1"}).encode("utf-8")
    timestamp = str(int(now.timestamp()))
    signature = base64.b64encode(hmac.new(b"CONTROLLED_SECRET", timestamp.encode() + body, hashlib.sha256).digest()).decode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/", data=body, method="POST",
        headers={"X-Prolific-Request-Signature": signature, "X-Prolific-Request-Timestamp": timestamp, "X-Event-ID": event_id, "X-Timestamp": timestamp},
    )
    return json.loads(urllib.request.urlopen(request, timeout=5).read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fault-scheduler", action="store_true")
    args = parser.parse_args()
    root_repo = Path(__file__).resolve().parents[1]
    now = datetime.now(timezone.utc)
    ControlledApi.state = {"id": "S1", "study_id": "STUDY-FIXTURE", "participant": "P-FIXTURE", "status": "AWAITING REVIEW", "started_at": now.isoformat().replace("+00:00", "Z")}
    ControlledApi.post_count = 0
    with tempfile.TemporaryDirectory(prefix="ticket08-cli-") as temporary:
        root = Path(temporary)
        data_dir = root / "data"
        candidate = root / "candidate.jsonl"
        candidate.write_text(json.dumps({"candidate_key": "fixture-candidate", "pred_is_ctc": True, "audio_verify": {"verify_is_ctc": True}, "tos_audio": {"outer_url": "http://127.0.0.1/fixture.wav"}}) + "\n", encoding="utf-8")
        consent = root / "consent.json"
        consent.write_text(json.dumps({"records": []}) + "\n", encoding="utf-8")
        api = ThreadingHTTPServer(("127.0.0.1", 0), ControlledApi)
        api_thread = threading.Thread(target=api.serve_forever, daemon=True)
        api_thread.start()
        receiver: subprocess.Popen[str] | None = None
        scheduler: subprocess.Popen[str] | None = None
        restarted_receiver: subprocess.Popen[str] | None = None
        restarted_scheduler: subprocess.Popen[str] | None = None
        try:
            api_base = f"http://127.0.0.1:{api.server_address[1]}/api/v1"
            config = {"study_id": "STUDY-FIXTURE", "data_dir": str(data_dir), "base_url": api_base, "token": "CONTROLLED_FIXTURE_ONLY", "auto_labels": [str(candidate)], "routine_policy": True, "activation_boundary": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"), "verified_message_scope": {"researcher_id": "RESEARCHER-FIXTURE", "workspace_id": "WORKSPACE-FIXTURE", "coverage_start": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"), "coverage_end": (now + timedelta(days=1)).isoformat().replace("+00:00", "Z"), "workspace_visibility_verified": True, "verification_note": "localhost controlled fixture", "checked_at": now.isoformat().replace("+00:00", "Z"), "expires_at": (now + timedelta(days=1)).isoformat().replace("+00:00", "Z")}, "consent_evidence_path": str(consent)}
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
            report = {"status": "ok", "study_id": "STUDY-FIXTURE", "submissions": [{"session_id": "S1", "study_id": "STUDY-FIXTURE", "participant_id": "P-FIXTURE", "status": "AWAITING REVIEW", "classification": "awaiting_without_final_result", "proposed_action": "review_missing_result", "evidence": ["assignment"]}]}
            report_path = root / "report.json"
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            journal = root / "journal.jsonl"
            events_path = data_dir / "events.json"
            cli = [sys.executable, "-m", "prolific.ctc_verification_app.activation_cli", "--journal", str(journal)]
            preview = json.loads(run_command(cli + ["preview", "--report", str(report_path)], root_repo))
            approval = run_command(cli + ["approve", "--approval", str(data_dir / "approval.json"), "--study-id", "STUDY-FIXTURE", "--preview-sha256", preview["preview_sha256"], "--approved-by", "fixture-reviewer", "--routine-policy", "--preview-report", str(report_path)], root_repo)
            status_before = json.loads(run_command(cli + ["status"], root_repo))
            receiver_port = free_port()
            receiver = subprocess.Popen(cli + ["receiver", "--config", str(config_path), "--secret", "CONTROLLED_SECRET", "--port", str(receiver_port)], cwd=root_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            wait_for_port(receiver, receiver_port)
            receiver_response = signed_request(receiver_port, now, "E1")
            stop_process(receiver)
            receiver = None
            scheduler_cmd = cli + ["scheduler", "--config", str(config_path), "--interval", "0.1"]
            if args.fault_scheduler:
                scheduler = subprocess.Popen([sys.executable, "-c", "import sys; sys.stderr.write('injected scheduler fault'); sys.exit(7)"], cwd=root_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    wait_for_periodic(events_path, 0, scheduler, timeout=2)
                except RuntimeError as error:
                    raise RuntimeError(str(error)) from error
                raise AssertionError("fault scheduler unexpectedly completed a cycle")
            scheduler = subprocess.Popen(scheduler_cmd, cwd=root_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            first_state = wait_for_periodic(events_path, 0, scheduler)
            first_runs = len(first_state["periodic_runs"])
            stop_process(scheduler)
            scheduler = None
            disabled = json.loads(run_command(cli + ["disable", "fixture stop"], root_repo))
            restarted_port = free_port()
            restarted_receiver = subprocess.Popen(cli + ["receiver", "--config", str(config_path), "--secret", "CONTROLLED_SECRET", "--port", str(restarted_port)], cwd=root_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            wait_for_port(restarted_receiver, restarted_port)
            duplicate_response = signed_request(restarted_port, now, "E1")
            stop_process(restarted_receiver)
            restarted_receiver = None
            restarted_scheduler = subprocess.Popen(scheduler_cmd, cwd=root_repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            second_state = wait_for_periodic(events_path, first_runs, restarted_scheduler)
            second_runs = len(second_state["periodic_runs"])
            stop_process(restarted_scheduler)
            restarted_scheduler = None
            status_after = json.loads(run_command(cli + ["status"], root_repo))
            output = {"preview": preview, "approval": json.loads(approval), "status_before": status_before, "receiver_response": receiver_response, "first_scheduler_cycles": first_runs, "duplicate_response_after_restart": duplicate_response, "second_scheduler_cycles": second_runs, "disabled": disabled, "status_after_restart": status_after, "controlled_api": True, "post_count": ControlledApi.post_count, "writes_performed": False}
            assert first_runs >= 1 and second_runs > first_runs
            assert status_before["disabled"] is False and status_after["disabled"] is True
            assert ControlledApi.post_count == 0
            assert duplicate_response["status"] in {"completed", "busy"}
            print(json.dumps(output, sort_keys=True))
        finally:
            for process in (receiver, scheduler, restarted_receiver, restarted_scheduler):
                stop_process(process)
            api.shutdown()
            api.server_close()
            api_thread.join(timeout=5)


if __name__ == "__main__":
    main()
