"""Read-only, durable candidate generation for missing Prolific results."""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Protocol

WAIT_MINUTES = 10
APPROVED_MESSAGE = ("Hello, our records show that your Prolific submission is awaiting review, "
    "but we could not find a final annotation result for this session: {SESSION_ID}. "
    "If you were unable to complete the annotation, please return this submission on Prolific. "
    "If you believe you submitted your answers successfully, please reply so we can investigate. "
    "We’re sorry for the inconvenience.")

class ContactLedger(Protocol):
    def read(self) -> dict[str, Any]: ...
    def write(self, value: dict[str, Any]) -> None: ...

class FreshReconciliation(Protocol):
    def reconcile(self) -> dict[str, Any]: ...
    def inspect_messages(self, *, session_id: str, participant_id: str, study_id: str) -> str: ...

@dataclass(frozen=True)
class ContactDecision:
    session_id: str
    decision: str
    evidence: list[str]
    message: str | None = None
    def as_dict(self) -> dict[str, Any]:
        result = {"session_id": self.session_id, "decision": self.decision, "evidence": self.evidence}
        if self.message is not None: result["message"] = self.message
        return result

class JsonContactLedger:
    """Atomic JSON ledger with a process and thread lock around read/modify/write."""
    _locks: dict[str, threading.RLock] = {}
    _locks_guard = threading.Lock()
    def __init__(self, path: Path):
        self.path = path
        with self._locks_guard: self._lock = self._locks.setdefault(str(path.resolve()), threading.RLock())
    def read(self) -> dict[str, Any]:
        if not self.path.exists(): return {"sessions": {}}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("sessions", {}), dict): raise ValueError("contact ledger must contain sessions")
        return value
    def write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)
    @contextmanager
    def locked(self) -> Iterator[None]:
        with self._lock:
            lock_path = self.path.with_name(self.path.name + ".lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open("a+", encoding="utf-8") as handle:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try: yield
                finally: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

def _dt(value: Any) -> datetime:
    if isinstance(value, datetime): return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str): return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("invalid timestamp")

def _ts(value: datetime) -> str: return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

_MANUAL_EVIDENCE = {"draft", "archived_result", "read_error", "other_session_result", "save_error", "identity_mismatch"}

def _run(report: dict[str, Any], ledger: ContactLedger, fresh: FreshReconciliation, now: datetime, wait_minutes: int) -> dict[str, Any]:
    if report.get("status") != "ok": return {"status": "pending", "decisions": [], "error": report.get("error", "reconciliation unavailable")}
    study = report.get("study_id")
    if not isinstance(study, str) or not study: return {"status": "manual_review", "decisions": [{"decision": "manual_review", "evidence": ["missing_study_id"]}]}
    state = ledger.read(); sessions = state.setdefault("sessions", {}); decisions = []
    for row in report.get("submissions", []):
        if not isinstance(row, dict) or row.get("status") != "AWAITING REVIEW": continue
        sid, pid = row.get("session_id"), row.get("participant_id")
        if not isinstance(sid, str) or not sid: continue
        evidence = {str(item) for item in row.get("evidence", []) if isinstance(item, str)}
        entry = sessions.setdefault(sid, {"state": "observed"})
        if row.get("classification") != "awaiting_without_final_result":
            entry["state"] = "resolved"; continue
        if not isinstance(pid, str) or not pid or row.get("errors") or evidence & _MANUAL_EVIDENCE:
            entry.update({"state": "manual_review", "evidence": sorted(evidence | {"uncertain_local_evidence"})})
            decisions.append(ContactDecision(sid, "manual_review", sorted(evidence | {"uncertain_local_evidence"}))); continue
        if row.get("return_requested") is True:
            entry["state"] = "contacted"; decisions.append(ContactDecision(sid, "already_contacted", ["platform_return_requested"])); continue
        if entry.get("study_id") and (entry.get("study_id"), entry.get("participant_id")) != (study, pid):
            entry["state"] = "manual_review"; decisions.append(ContactDecision(sid, "manual_review", ["identity_changed_since_observation"])); continue
        if not entry.get("first_missing_at"):
            entry.update({"state": "observed", "study_id": study, "participant_id": pid, "first_missing_at": _ts(now), "evidence": sorted(evidence)})
            continue
        try: due = _dt(entry["first_missing_at"]) + timedelta(minutes=wait_minutes)
        except (TypeError, ValueError):
            entry["state"] = "manual_review"; decisions.append(ContactDecision(sid, "manual_review", ["invalid_missing_observation_time"])); continue
        if now < due: decisions.append(ContactDecision(sid, "waiting", ["missing_result_wait_window"])); continue
        if entry.get("state") in {"candidate", "contacted", "manual_review"}: continue
        fresh_report = fresh.reconcile()
        if fresh_report.get("status") != "ok":
            decisions.append(ContactDecision(sid, "pending", ["fresh_reconciliation_unavailable"])); continue
        current = next((item for item in fresh_report.get("submissions", []) if isinstance(item, dict) and item.get("session_id") == sid), None)
        if not current: decisions.append(ContactDecision(sid, "manual_review", ["fresh_submission_missing"])); continue
        current_evidence = {str(item) for item in current.get("evidence", []) if isinstance(item, str)}
        if current.get("study_id") != study or current.get("participant_id") != pid:
            entry["state"] = "manual_review"; decisions.append(ContactDecision(sid, "manual_review", sorted(current_evidence | {"fresh_identity_mismatch"}))); continue
        if (current.get("status") != "AWAITING REVIEW" or current.get("classification") != "awaiting_without_final_result"):
            entry["state"] = "resolved"; decisions.append(ContactDecision(sid, "cancelled", ["fresh_status_or_result_changed"])); continue
        if current.get("errors") or current_evidence & _MANUAL_EVIDENCE:
            entry["state"] = "manual_review"; decisions.append(ContactDecision(sid, "manual_review", sorted(current_evidence | {"fresh_evidence_uncertain"}))); continue
        if current.get("return_requested") is True:
            entry["state"] = "contacted"; decisions.append(ContactDecision(sid, "already_contacted", ["platform_return_requested"])); continue
        history = fresh.inspect_messages(session_id=sid, participant_id=pid, study_id=study)
        if history != "clear":
            state_name = "contacted" if history == "already_contacted" else "manual_review"
            entry["state"] = state_name; decisions.append(ContactDecision(sid, "already_contacted" if history == "already_contacted" else "manual_review", ["fresh_message_history_" + history])); continue
        candidate_evidence = set(entry.get("evidence", [])) | current_evidence | {"fresh_reconciliation", "fresh_message_history_clear"}
        entry.update({"state": "candidate", "candidate_at": _ts(now), "candidate_evidence": sorted(candidate_evidence), "candidate_message": APPROVED_MESSAGE.format(SESSION_ID=sid)})
        decisions.append(ContactDecision(sid, "candidate", entry["candidate_evidence"], entry["candidate_message"]))
    ledger.write(state)
    return {"status": "ok", "study_id": study, "decisions": [d.as_dict() for d in decisions], "writes_performed": True}

def build_contact_candidates(report: dict[str, Any], ledger: ContactLedger, fresh: FreshReconciliation, *, now: datetime | str | None = None, wait_minutes: int = WAIT_MINUTES) -> dict[str, Any]:
    if wait_minutes < 1: raise ValueError("wait_minutes must be at least one minute")
    reference = _dt(now or datetime.now(timezone.utc))
    if hasattr(ledger, "locked"):
        with ledger.locked(): return _run(report, ledger, fresh, reference, wait_minutes)
    return _run(report, ledger, fresh, reference, wait_minutes)


class ProlificFreshReconciliation:
    """Fresh, read-only platform/local/chat adapter used at candidate time."""
    def __init__(self, reader: Any, data_dir: Path, study_id: str, *, valid_completion_codes: set[str] | None = None):
        self.reader, self.data_dir, self.study_id = reader, data_dir, study_id
        self.valid_completion_codes = valid_completion_codes

    def reconcile(self) -> dict[str, Any]:
        from .reconciliation import reconcile_current_state
        return reconcile_current_state(self.reader, self.data_dir, self.study_id, self.valid_completion_codes)

    def inspect_messages(self, *, session_id: str, participant_id: str, study_id: str) -> str:
        try:
            detail = self.reader.get_submission(session_id)
            participant = detail.get("participant")
            if isinstance(participant, dict):
                participant = participant.get("id") or participant.get("participant_id") or participant.get("user_id")
            if detail.get("study_id") != study_id or participant != participant_id:
                return "ambiguous"
            if detail.get("return_requested"):
                return "already_contacted"
            cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat().replace("+00:00", "Z")
            payload = self.reader.get_messages(user_id=participant_id, created_after=cutoff)
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                return "unavailable"
            matches = []
            for message in payload["results"]:
                if not isinstance(message, dict): return "ambiguous"
                body = str(message.get("body", message.get("content", "")))
                if session_id in body: matches.append(message)
            if matches: return "already_contacted"
            return "ambiguous" if payload["results"] else "clear"
        except Exception:
            return "unavailable"
