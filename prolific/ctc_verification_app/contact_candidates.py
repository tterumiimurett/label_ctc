"""Read-only, durable candidate generation for missing Prolific results."""
from __future__ import annotations

import json
import os
import threading
import argparse
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
class VerifiedMessageScope:
    """Local operator evidence for an approved, accessible workspace query."""
    researcher_id: str
    workspace_id: str
    coverage_start: datetime
    coverage_end: datetime
    workspace_visibility_verified: bool
    verification_note: str
    checked_at: datetime | None = None
    expires_at: datetime | None = None

    def valid_for(self, started_at: Any, now: datetime) -> bool:
        if not self.workspace_visibility_verified or not self.verification_note.strip():
            return False
        if self.checked_at is None or self.expires_at is None:
            return False
        if self.coverage_start < now - timedelta(days=30) or self.coverage_end < now:
            return False
        if self.checked_at > now or self.expires_at < now:
            return False
        if not isinstance(started_at, str):
            return False
        try:
            started = _dt(started_at)
        except ValueError:
            return False
        return self.coverage_start <= started <= now

@dataclass(frozen=True)
class ContactDecision:
    session_id: str
    decision: str
    evidence: list[str]
    message: str | None = None
    participant_id: str | None = None
    study_id: str | None = None
    reason: str | None = None
    def as_dict(self) -> dict[str, Any]:
        result = {"session_id": self.session_id, "decision": self.decision, "evidence": self.evidence}
        if self.message is not None: result["message"] = self.message
        if self.participant_id is not None: result["participant_id"] = self.participant_id
        if self.study_id is not None: result["study_id"] = self.study_id
        if self.reason is not None: result["reason"] = self.reason
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

_MANUAL_EVIDENCE = {"draft", "archived_result", "read_error", "other_session_result", "save_error", "identity_mismatch", "local_read_error"}

def queue_manual_review(entry: dict[str, Any], sid: str, study: Any, pid: Any, evidence: set[str], reason: str) -> ContactDecision:
    """Persist manual disposition while separating trusted and observed identity."""
    evidence = set(entry.get("evidence", [])) | set(evidence)
    trusted_identity = entry.get("identity_status") != "observed"
    original_study = entry.get("study_id") if trusted_identity else None
    original_pid = entry.get("participant_id") if trusted_identity else None
    if isinstance(original_study, str):
        if isinstance(study, str) and original_study != study:
            entry["observed_study_id"] = study
            evidence.add("observed_study_id_conflict")
        elif not isinstance(study, str):
            entry["observed_study_id"] = f"invalid:{type(study).__name__}"
            evidence.add("observed_study_id_invalid")
    elif isinstance(study, str):
        entry.update({"study_id": study, "observed_study_id": study, "identity_status": "observed"})
    else:
        entry["observed_study_id"] = f"invalid:{type(study).__name__}"
        evidence.add("observed_study_id_invalid")
    if isinstance(original_pid, str):
        if isinstance(pid, str) and original_pid != pid:
            entry["observed_participant_id"] = pid
            evidence.add("observed_participant_id_conflict")
        elif not isinstance(pid, str):
            entry["observed_participant_id"] = f"invalid:{type(pid).__name__}"
            evidence.add("observed_participant_id_invalid")
    elif isinstance(pid, str):
        entry.update({"participant_id": pid, "observed_participant_id": pid, "identity_status": "observed"})
    else:
        entry["observed_participant_id"] = f"invalid:{type(pid).__name__}"
        evidence.add("observed_participant_id_invalid")
    if entry.get("session_id") not in {None, sid}:
        entry["observed_session_id"] = sid
        evidence.add("observed_session_id_conflict")
    else:
        entry.setdefault("session_id", sid)
    complete = sorted(evidence | {reason})
    entry.update({"state": "manual_review", "reason": reason, "evidence": complete})
    trusted_study = original_study if isinstance(original_study, str) else (entry.get("study_id") if entry.get("identity_status") == "observed" else None)
    trusted_pid = original_pid if isinstance(original_pid, str) else (entry.get("participant_id") if entry.get("identity_status") == "observed" else None)
    return ContactDecision(sid, "manual_review", complete, participant_id=trusted_pid, study_id=trusted_study, reason=reason)


def _manual(entry: dict[str, Any], sid: str, study: Any, pid: Any, evidence: set[str], reason: str) -> ContactDecision:
    decision = queue_manual_review(entry, sid, study, pid, evidence, reason)
    entry["message"] = APPROVED_MESSAGE.format(SESSION_ID=sid)
    return decision


def outbound_attempted(entry: dict[str, Any]) -> bool:
    """Irreversible barrier: an outbound operation may never be started twice."""
    return bool(entry.get("send_attempted_at") or entry.get("send_attempt_count") or entry.get("send_operation"))


def _local_manual_reason(row: dict[str, Any], evidence: set[str], *, fresh: bool = False) -> str | None:
    classification = row.get("classification")
    if classification in {"local_read_error", "identity_mismatch"}:
        return str(classification)
    if row.get("errors"):
        return "fresh_local_errors" if fresh else "local_errors"
    if evidence & _MANUAL_EVIDENCE:
        return "fresh_uncertain_local_evidence" if fresh else "uncertain_local_evidence"
    return None

def _run(report: dict[str, Any], ledger: ContactLedger, fresh: FreshReconciliation, now: datetime, wait_minutes: int, candidate_origin: str) -> dict[str, Any]:
    if report.get("status") != "ok": return {"status": "pending", "decisions": [], "error": report.get("error", "reconciliation unavailable")}
    study = report.get("study_id")
    if not isinstance(study, str) or not study: return {"status": "manual_review", "decisions": [{"decision": "manual_review", "evidence": ["missing_study_id"]}]}
    state = ledger.read(); sessions = state.setdefault("sessions", {}); decisions = []
    for row in report.get("submissions", []):
        if not isinstance(row, dict) or row.get("status") != "AWAITING REVIEW": continue
        sid, pid = row.get("session_id"), row.get("participant_id")
        if not isinstance(sid, str) or not sid: continue
        evidence = {str(item) for item in row.get("evidence", []) if isinstance(item, str)}
        evidence.update(f"local_error:{item}" for item in row.get("errors", []) if isinstance(item, str) and item)
        entry = sessions.setdefault(sid, {"state": "observed"})
        if entry.get("state") == "manual_review":
            continue
        if outbound_attempted(entry):
            if entry.get("state") == "sent" or entry.get("send_outcome") == "accepted" or entry.get("message_id"):
                decisions.append(queue_manual_review(entry, sid, study, pid, {"acknowledged_send"}, "acknowledged_send_requires_confirmation"))
                continue
            if entry.get("state") not in {"sending", "delivery_unknown"}:
                entry.update({"state": "delivery_unknown", "reason": "outbound_attempt_requires_recovery"})
            continue
        manual_reason = _local_manual_reason(row, evidence)
        if manual_reason:
            decisions.append(_manual(entry, sid, study, pid, evidence, manual_reason)); continue
        if row.get("classification") != "awaiting_without_final_result":
            if entry.get("first_missing_at"):
                decisions.append(queue_manual_review(entry, sid, study, pid, evidence, "answer_or_status_arrived_after_missing_detection"))
            else:
                entry["state"] = "resolved"
            continue
        if not isinstance(pid, str) or not pid:
            decisions.append(_manual(entry, sid, study, pid, evidence, "missing_participant_identity")); continue
        if bool(row.get("return_requested")):
            if entry.get("first_missing_at"):
                decisions.append(queue_manual_review(entry, sid, study, pid, evidence, "prior_contact_after_missing_detection"))
            else:
                entry["state"] = "contacted"
            continue
        if entry.get("study_id") and (entry.get("study_id"), entry.get("participant_id")) != (study, pid):
            decisions.append(_manual(entry, sid, study, pid, evidence, "identity_changed_since_observation")); continue
        if not entry.get("first_missing_at"):
            entry.update({"state": "observed", "study_id": study, "participant_id": pid, "first_missing_at": _ts(now), "evidence": sorted(evidence)})
            continue
        try: due = _dt(entry["first_missing_at"]) + timedelta(minutes=wait_minutes)
        except (TypeError, ValueError):
            decisions.append(_manual(entry, sid, study, pid, evidence, "invalid_missing_observation_time")); continue
        if now < due: decisions.append(ContactDecision(sid, "waiting", ["missing_result_wait_window"])); continue
        if entry.get("state") in {"candidate", "contacted", "manual_review"}: continue
        fresh_report = fresh.reconcile()
        if fresh_report.get("status") != "ok":
            entry.update({"state": "pending", "study_id": study, "participant_id": pid,
                          "reason": "fresh_reconciliation_unavailable",
                          "evidence": sorted(evidence | {"fresh_reconciliation_unavailable"}),
                          "message": APPROVED_MESSAGE.format(SESSION_ID=sid)})
            decisions.append(ContactDecision(sid, "pending", entry["evidence"], entry["message"], pid, study, entry["reason"])); continue
        current = next((item for item in fresh_report.get("submissions", []) if isinstance(item, dict) and item.get("session_id") == sid), None)
        if not current: decisions.append(_manual(entry, sid, study, pid, evidence, "fresh_submission_missing")); continue
        current_evidence = {str(item) for item in current.get("evidence", []) if isinstance(item, str)}
        current_evidence.update(f"local_error:{item}" for item in current.get("errors", []) if isinstance(item, str) and item)
        if current.get("study_id") != study or current.get("participant_id") != pid:
            decisions.append(_manual(entry, sid, study, pid, current_evidence, "fresh_identity_mismatch")); continue
        manual_reason = _local_manual_reason(current, current_evidence, fresh=True)
        if manual_reason:
            decisions.append(_manual(entry, sid, study, pid, current_evidence, manual_reason)); continue
        if (current.get("status") != "AWAITING REVIEW" or current.get("classification") != "awaiting_without_final_result"):
            decisions.append(queue_manual_review(entry, sid, study, pid, current_evidence, "answer_or_status_arrived_after_missing_detection")); continue
        if bool(current.get("return_requested")):
            decisions.append(queue_manual_review(entry, sid, study, pid, current_evidence, "prior_contact_after_missing_detection")); continue
        history = fresh.inspect_messages(session_id=sid, participant_id=pid, study_id=study)
        if history != "clear":
            if history == "prior_contact":
                decisions.append(queue_manual_review(entry, sid, study, pid, {"prior_contact"}, "prior_contact_after_missing_detection")); continue
            decisions.append(_manual(entry, sid, study, pid, {"fresh_message_history_" + history}, "message_history_not_proven_clear")); continue
        candidate_evidence = set(entry.get("evidence", [])) | current_evidence | {"fresh_reconciliation", "fresh_message_history_clear"}
        if candidate_origin == "unknown":
            decisions.append(queue_manual_review(entry, sid, study, pid, candidate_evidence, "candidate_origin_unknown")); continue
        entry.update({"state": "candidate", "candidate_at": _ts(now), "candidate_origin": candidate_origin, "candidate_evidence": sorted(candidate_evidence), "candidate_message": APPROVED_MESSAGE.format(SESSION_ID=sid)})
        decisions.append(ContactDecision(sid, "candidate", entry["candidate_evidence"], entry["candidate_message"]))
    ledger.write(state)
    return {"status": "ok", "study_id": study, "decisions": [d.as_dict() for d in decisions], "writes_performed": True}

def build_contact_candidates(report: dict[str, Any], ledger: ContactLedger, fresh: FreshReconciliation, *, now: datetime | str | None = None, wait_minutes: int = WAIT_MINUTES, candidate_origin: str) -> dict[str, Any]:
    if wait_minutes != WAIT_MINUTES: raise ValueError("wait_minutes must be exactly ten minutes")
    if candidate_origin not in {"new", "historical", "unknown"}: raise ValueError("candidate_origin must be new, historical, or unknown")
    reference = _dt(now or datetime.now(timezone.utc))
    if hasattr(ledger, "locked"):
        with ledger.locked(): return _run(report, ledger, fresh, reference, wait_minutes, candidate_origin)
    return _run(report, ledger, fresh, reference, wait_minutes, candidate_origin)


class ProlificFreshReconciliation:
    """Fresh, read-only platform/local/chat adapter used at candidate time."""
    def __init__(self, reader: Any, data_dir: Path, study_id: str, *, valid_completion_codes: set[str] | None = None, scope: VerifiedMessageScope | None = None, now: datetime | None = None):
        self.reader, self.data_dir, self.study_id = reader, data_dir, study_id
        self.valid_completion_codes = valid_completion_codes
        self.scope = scope
        self.now = now

    def reconcile(self) -> dict[str, Any]:
        from .reconciliation import reconcile_current_state
        return reconcile_current_state(self.reader, self.data_dir, self.study_id, self.valid_completion_codes)

    def send_message(self, *, recipient_id: str, body: str, study_id: str) -> dict[str, Any]:
        """Delegate the single ordinary-message operation to the real API client."""
        return self.reader.send_message(recipient_id=recipient_id, body=body, study_id=study_id)

    def inspect_messages(self, *, session_id: str, participant_id: str, study_id: str) -> str:
        """Classify complete ordered participant/researcher history without inference."""
        if self.scope is None:
            return "unavailable"
        try:
            detail = self.reader.get_submission(session_id)
            participant = detail.get("participant")
            if isinstance(participant, dict):
                participant = participant.get("id") or participant.get("participant_id") or participant.get("user_id")
            now = self.now or datetime.now(timezone.utc)
            if detail.get("study_id") != study_id or participant != participant_id:
                return "ambiguous"
            if not self.scope.valid_for(detail.get("started_at"), now):
                return "unavailable"
            if detail.get("return_requested"):
                return "prior_contact"
            payload = self.reader.get_messages(user_id=participant_id, created_after=_ts(self.scope.coverage_start), workspace_id=self.scope.workspace_id)
            if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
                return "unavailable"
            messages = payload["results"]
            if any(not isinstance(message, dict) or not isinstance(message.get("created_at"), str) or not isinstance(message.get("sender_id"), str) for message in messages):
                return "ambiguous"
            if any(message["sender_id"] not in {self.scope.researcher_id, participant_id} for message in messages):
                return "ambiguous"
            ordered = sorted(messages, key=lambda message: _dt(message["created_at"]))
            timestamps = [_dt(message["created_at"]) for message in ordered]
            if len(timestamps) != len(set(timestamps)):
                return "ambiguous"
            if not ordered:
                return "clear"
            last_researcher = max((message for message in ordered if message["sender_id"] == self.scope.researcher_id), key=lambda message: _dt(message["created_at"]), default=None)
            if last_researcher is None:
                return "participant_reply"
            last_outgoing_time = _dt(last_researcher["created_at"])
            for message in ordered:
                if message["sender_id"] == participant_id and _dt(message["created_at"]) > last_outgoing_time:
                    return "participant_reply"
            for message in ordered:
                if message["sender_id"] == self.scope.researcher_id:
                    body = str(message.get("body", "")).lower()
                    if "return" in body and "submission" in body:
                        return "prior_contact"
            if detail.get("return_requested"):
                return "prior_contact"
            return "clear"
        except Exception:
            return "unavailable"


def queue_report(ledger: ContactLedger) -> dict[str, Any]:
    state = ledger.read()
    sessions = state.get("sessions", {})
    return {"sessions": {sid: item for sid, item in sessions.items()
                          if isinstance(item, dict) and item.get("state") in {"observed", "waiting", "pending", "manual_review", "candidate"}}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show durable Ticket 5 contact queue")
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(queue_report(JsonContactLedger(args.ledger)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
