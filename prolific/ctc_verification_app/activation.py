"""Ticket 8 activation boundary.

The controller deliberately separates inspection from mutation.  It can be
used with a temporary ``VerificationStore`` and an adapter implementing the
already-reviewed outbound contract; production activation remains a human
decision and is rejected unless every gate is explicit.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol


class ActionAdapter(Protocol):
    def reconcile(self) -> dict[str, Any]: ...
    def inspect_messages(self, *, session_id: str, participant_id: str, study_id: str) -> str: ...
    def send_message(self, *, recipient_id: str, body: str, study_id: str) -> dict[str, Any]: ...


class ActionLog:
    """Atomic append-only JSONL audit log plus a durable disable switch."""
    def __init__(self, path: Path):
        self.path = path
        self.disable_path = path.with_suffix(path.suffix + ".disabled")
        self._lock = threading.RLock()

    @property
    def disabled(self) -> bool:
        return self.disable_path.exists()

    def disable(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("disable reason is required")
        self.disable_path.parent.mkdir(parents=True, exist_ok=True)
        self.disable_path.write_text(reason.strip() + "\n", encoding="utf-8")
        self.record("future_actions_disabled", {"reason": reason.strip()})

    def record(self, kind: str, data: dict[str, Any]) -> dict[str, Any]:
        event = {"event_id": uuid.uuid4().hex, "kind": kind, "data": data}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        return event


def _identity(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in ("id", "participant_id", "user_id"):
            found = _identity(value.get(key))
            if found:
                return found
    return None


class ActivationController:
    def __init__(self, *, reader: Any, study_id: str, action_log: ActionLog,
                 workspace_id: str | None = None, permissions_verified: bool = False,
                 identity_verified: bool = False, production: bool = False):
        self.reader, self.study_id, self.log = reader, study_id, action_log
        self.workspace_id = workspace_id
        self.permissions_verified = permissions_verified
        self.identity_verified = identity_verified
        self.production = production

    def preview(self, report: dict[str, Any]) -> dict[str, Any]:
        """Return proposed mutations; this method never calls a write API."""
        gates = {
            "study_id": bool(self.study_id),
            "workspace_id": bool(self.workspace_id),
            "permissions_verified": self.permissions_verified,
            "identity_verified": self.identity_verified,
            "read_only_report": report.get("status") == "ok" and report.get("writes_performed") is False,
        }
        actions: list[dict[str, Any]] = []
        for row in report.get("submissions", []) if isinstance(report, dict) else []:
            if not isinstance(row, dict):
                continue
            sid, pid = row.get("session_id"), row.get("participant_id")
            proposed = row.get("proposed_action")
            if not isinstance(sid, str) or row.get("study_id") != self.study_id or not isinstance(pid, str):
                proposed = "manual_review"
            actions.append({"session_id": sid, "participant_id": pid, "proposed_action": proposed,
                            "status": row.get("status"), "evidence": row.get("evidence", []),
                            "identity_verified": proposed != "manual_review"})
        result = {"status": "preview", "gates": gates, "actions": actions,
                  "activation_allowed": all(gates.values()) and not self.log.disabled and not self.production}
        self.log.record("action_preview", {"gates": gates, "action_count": len(actions), "sha256": hashlib.sha256(json.dumps(actions, sort_keys=True).encode()).hexdigest()})
        return result

    def execute(self, report: dict[str, Any], *, archive: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
                release: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
                candidates: Callable[..., dict[str, Any]] | None = None,
                candidate_origin: str | None = None) -> dict[str, Any]:
        preview = self.preview(report)
        if self.production:
            raise PermissionError("production execution requires separate human activation")
        if not preview["activation_allowed"]:
            return {"status": "blocked", "reason": "activation_gates_failed", "preview": preview}
        if candidates is not None and candidate_origin not in {"new", "historical", "unknown"}:
            raise ValueError("candidate_origin must be explicitly new, historical, or unknown")
        results: list[dict[str, Any]] = []
        for action in preview["actions"]:
            sid = action["session_id"]
            try:
                proposed = action["proposed_action"]
                if proposed == "archived_result" and archive: value = archive(action)
                elif proposed == "release_claim_proposal" and release: value = release(action)
                elif proposed == "review_missing_result" and candidates: value = candidates(candidate_origin=candidate_origin)
                else: value = {"status": "no_mutation", "action": proposed}
                item = {"session_id": sid, "result": value}
                self.log.record("action_completed", item); results.append(item)
            except Exception as error:
                item = {"session_id": sid, "status": "failed", "error_type": type(error).__name__}
                self.log.record("action_failed", item); results.append(item)
        return {"status": "ok", "results": results, "writes_performed": bool(results)}

