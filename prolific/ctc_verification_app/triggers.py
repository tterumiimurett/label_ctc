"""Read-only webhook receiver and periodic trigger for reconciliation.

No function in this module archives, releases, messages, subscribes, or deploys.
The receiver records an event as pending before querying the API, then marks it
completed only after reconciliation succeeds, so restart/API failures retry.
"""
from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Protocol

from .reconciliation import SubmissionReader, reconcile_current_state


class TriggerStore(Protocol):
    def begin(self, event_id: str, timestamp: int, payload: dict[str, Any]) -> str: ...
    def complete(self, event_id: str, status: str) -> None: ...
    def fail(self, event_id: str) -> None: ...


class JsonTriggerStore:
    """Atomic, process-safe ledger with pending/completed event stages."""

    def __init__(self, path: Path, *, processing_lease_seconds: float = 300.0):
        self.path = path
        self.processing_lease_seconds = processing_lease_seconds
        self.lock_path = path.with_suffix(path.suffix + ".lock")
        self._thread_lock = threading.RLock()

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"events": {}, "latest_by_resource": {}}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("events", {}), dict):
            raise ValueError("trigger ledger has invalid schema")
        value.setdefault("latest_by_resource", {})
        return value

    def _write(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def _locked(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.lock_path.open("a+")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return lock

    def begin(self, event_id: str, timestamp: int, payload: dict[str, Any]) -> str:
        with self._thread_lock:
            lock = self._locked()
            try:
                state = self._read(); existing = state["events"].get(event_id)
                if existing and existing.get("stage") == "completed": return "completed"
                resource = payload.get("resource_id")
                latest = state["latest_by_resource"].get(resource) if resource else None
                if existing and existing.get("stage") == "processing":
                    started = float(existing.get("processing_started", 0))
                    if time.time() - started < self.processing_lease_seconds: return "busy"
                    existing["stage"] = "pending"
                if existing and existing.get("stage") == "pending":
                    existing["stage"] = "processing"
                    existing["processing_started"] = time.time()
                    self._write(state)
                    return "retry"
                is_current = latest is None or timestamp >= latest["timestamp"]
                if not is_current: return "stale"
                state["events"][event_id] = {"timestamp": timestamp, "payload": payload, "stage": "processing", "processing_started": time.time()}
                if resource: state["latest_by_resource"][resource] = {"timestamp": timestamp, "event_id": event_id}
                self._write(state); return "new"
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN); lock.close()

    def fail(self, event_id: str) -> None:
        self.complete(event_id, "pending")

    def complete(self, event_id: str, status: str = "completed") -> None:
        with self._thread_lock:
            lock = self._locked()
            try:
                state = self._read()
                if event_id not in state["events"]: raise KeyError(event_id)
                state["events"][event_id]["stage"] = status
                self._write(state)
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN); lock.close()


def verify_signature(body: bytes, secret: str, signature: str, timestamp: str) -> bool:
    """Prolific contract: base64(HMAC-SHA256(secret, timestamp + raw body))."""
    digest = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


@dataclass(frozen=True)
class TriggerResult:
    accepted: bool
    status: str
    report: dict[str, Any] | None = None


class ReconciliationTrigger:
    def __init__(self, reader: SubmissionReader, data_dir: Path, study_id: str, store: TriggerStore, *,
                 valid_completion_codes: set[str] | None = None, now: Callable[[], datetime] | None = None,
                 production_enabled: bool = False):
        if production_enabled: raise ValueError("Ticket 07 is read-only; production execution is disabled")
        self.reader, self.data_dir, self.study_id, self.store = reader, data_dir, study_id, store
        self.valid_completion_codes = valid_completion_codes
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _run(self) -> dict[str, Any]:
        return reconcile_current_state(self.reader, self.data_dir, self.study_id, self.valid_completion_codes, now=self.now())

    def handle(self, body: bytes, headers: dict[str, str], secret: str) -> TriggerResult:
        signature, timestamp_text, event_id = (headers.get(k, "") for k in ("X-Prolific-Request-Signature", "X-Prolific-Request-Timestamp", "X-Event-ID"))
        if not signature or not timestamp_text or not event_id or not verify_signature(body, secret, signature, timestamp_text):
            return TriggerResult(False, "rejected_signature")
        try:
            timestamp = int(timestamp_text); payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("event_type") != "submission.status.change": return TriggerResult(False, "ignored_event")
            resource = payload.get("resource_id")
            if not isinstance(resource, str) or not resource: return TriggerResult(False, "invalid_event")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return TriggerResult(False, "invalid_event")
        stage = self.store.begin(event_id, timestamp, payload)
        if stage in {"completed", "stale", "busy"}: return TriggerResult(True, stage)
        try:
            detail = self.reader.get_submission(resource)
            if not isinstance(detail, dict) or detail.get("study_id") != self.study_id:
                self.store.complete(event_id, "ignored_wrong_study")
                return TriggerResult(True, "ignored_wrong_study")
            report = self._run()
            self.store.complete(event_id, "completed")
            return TriggerResult(True, "reconciled", report)
        except Exception:
            self.store.fail(event_id)
            return TriggerResult(True, "pending_retry")

    def periodic(self) -> dict[str, Any]:
        return self._run()


class _WebhookHandler(BaseHTTPRequestHandler):
    trigger: ReconciliationTrigger
    secret: str
    path: str

    def do_POST(self) -> None:
        if self.path != self.path_config:
            self.send_error(404); return
        try: length = int(self.headers.get("Content-Length", "-1"))
        except ValueError: length = -1
        if length < 0 or length > 1_000_000:
            self.send_error(400); return
        result = self.trigger.handle(self.rfile.read(length), dict(self.headers.items()), self.secret)
        code = 202 if result.accepted else 401
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(json.dumps({"status": result.status}).encode())

    def log_message(self, *_: Any) -> None: pass


def make_webhook_server(trigger: ReconciliationTrigger, secret: str, host: str = "127.0.0.1", port: int = 0, path: str = "/prolific/webhook") -> ThreadingHTTPServer:
    """Construct a real HTTP receiver; caller owns serve_forever/shutdown."""
    if trigger is None: raise ValueError("trigger is required")
    handler = type("ConfiguredWebhookHandler", (_WebhookHandler,), {"trigger": trigger, "secret": secret, "path_config": path})
    return ThreadingHTTPServer((host, port), handler)


def run_periodic(trigger: ReconciliationTrigger, interval_seconds: float, stop: threading.Event, *, production_enabled: bool = False) -> None:
    """Scheduler entrypoint. Interval is explicit and every failed read can recur."""
    if production_enabled: raise ValueError("production execution is disabled")
    if interval_seconds <= 0: raise ValueError("interval_seconds must be positive")
    while not stop.is_set():
        trigger.periodic(); stop.wait(interval_seconds)
