"""Read-only webhook and periodic triggers for current-state reconciliation.

This module deliberately owns triggering and event durability only.  It does not
create subscriptions, mutate assignments, archive results, or contact workers.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from .reconciliation import SubmissionReader, reconcile_current_state


class TriggerStore(Protocol):
    def accept(self, event_id: str, timestamp: int, payload: dict[str, Any]) -> bool: ...


class JsonTriggerStore:
    """Small atomic JSON ledger, suitable for a single scheduled worker."""

    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"events": {}, "latest_by_resource": {}}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("events", {}), dict):
            raise ValueError("trigger ledger has invalid schema")
        value.setdefault("latest_by_resource", {})
        return value

    def accept(self, event_id: str, timestamp: int, payload: dict[str, Any]) -> bool:
        state = self._read()
        if event_id in state["events"]:
            return False
        resource = payload.get("resource_id")
        latest = state["latest_by_resource"].get(resource) if resource else None
        state["events"][event_id] = {"timestamp": timestamp, "payload": payload}
        is_current = latest is None or timestamp >= latest["timestamp"]
        if resource and is_current:
            state["latest_by_resource"][resource] = {"timestamp": timestamp, "event_id": event_id}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return is_current


def verify_signature(body: bytes, secret: str, signature: str, timestamp: str) -> bool:
    """Verify Prolific's base64 HMAC-SHA256(timestamp + body) contract."""
    digest = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)


@dataclass(frozen=True)
class TriggerResult:
    accepted: bool
    status: str
    report: dict[str, Any] | None = None


class ReconciliationTrigger:
    def __init__(self, reader: SubmissionReader, data_dir: Path, study_id: str,
                 store: TriggerStore, *, valid_completion_codes: set[str] | None = None,
                 now: Callable[[], datetime] | None = None, production_enabled: bool = False):
        if production_enabled:
            raise ValueError("Ticket 07 is read-only; production execution is not supported")
        self.reader, self.data_dir, self.study_id, self.store = reader, data_dir, study_id, store
        self.valid_completion_codes = valid_completion_codes
        self.now = now or (lambda: datetime.now(timezone.utc))

    def _run(self) -> dict[str, Any]:
        return reconcile_current_state(self.reader, self.data_dir, self.study_id,
                                       self.valid_completion_codes, now=self.now())

    def handle(self, body: bytes, headers: dict[str, str], secret: str) -> TriggerResult:
        signature = headers.get("X-Prolific-Request-Signature", "")
        timestamp_text = headers.get("X-Prolific-Request-Timestamp", "")
        event_id = headers.get("X-Event-ID", "")
        if not signature or not timestamp_text or not event_id or not verify_signature(body, secret, signature, timestamp_text):
            return TriggerResult(False, "rejected_signature")
        try:
            timestamp = int(timestamp_text)
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict) or payload.get("event_type") != "submission.status.change":
                return TriggerResult(False, "ignored_event")
            if not isinstance(payload.get("resource_id"), str) or not payload["resource_id"]:
                return TriggerResult(False, "invalid_event")
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return TriggerResult(False, "invalid_event")
        if not self.store.accept(event_id, timestamp, payload):
            return TriggerResult(True, "duplicate")
        report = self._run()
        return TriggerResult(True, "reconciled", report)

    def periodic(self) -> dict[str, Any]:
        """Run the same current-state read for scheduler/backfill compensation."""
        return self._run()
