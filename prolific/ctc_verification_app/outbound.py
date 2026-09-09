"""Opt-in, durable sending of approved missing-result return requests."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from .contact_candidates import APPROVED_MESSAGE, ContactLedger


class OutboundAdapter(Protocol):
    def reconcile(self) -> dict[str, Any]: ...
    def inspect_messages(self, *, session_id: str, participant_id: str, study_id: str) -> str: ...
    def send_message(self, *, recipient_id: str, body: str, study_id: str) -> dict[str, Any]: ...


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def send_approved_return_requests(
    report: dict[str, Any],
    ledger: ContactLedger,
    fresh: OutboundAdapter,
    *,
    approved_sessions: set[str],
    enabled: bool = False,
) -> dict[str, Any]:
    """Send one ordinary message per explicitly approved candidate, if enabled."""
    if not enabled:
        return {"status": "disabled", "decisions": [], "writes_performed": False}
    if report.get("status") != "ok":
        return {"status": "pending", "decisions": [], "writes_performed": False}

    state = ledger.read()
    sessions = state.setdefault("sessions", {})
    decisions: list[dict[str, Any]] = []
    current_report = fresh.reconcile()
    if current_report.get("status") != "ok":
        return {"status": "pending", "decisions": [], "writes_performed": False}
    current = {
        row.get("session_id"): row
        for row in current_report.get("submissions", [])
        if isinstance(row, dict)
    }

    for session_id in sorted(approved_sessions):
        entry = sessions.get(session_id)
        if not isinstance(entry, dict) or entry.get("state") != "candidate":
            decisions.append({"session_id": session_id, "decision": "manual_review", "reason": "not_an_approved_candidate"})
            continue
        row = current.get(session_id)
        if not isinstance(row, dict):
            decisions.append({"session_id": session_id, "decision": "cancelled", "reason": "fresh_submission_missing"})
            continue
        participant_id = row.get("participant_id")
        study_id = row.get("study_id")
        if (row.get("status") != "AWAITING REVIEW"
                or row.get("classification") != "awaiting_without_final_result"
                or not isinstance(participant_id, str)
                or not isinstance(study_id, str)):
            entry.update({"state": "cancelled", "cancelled_at": _timestamp(), "reason": "fresh_status_or_result_changed"})
            decisions.append({"session_id": session_id, "decision": "cancelled", "reason": "fresh_status_or_result_changed"})
            continue

        history = fresh.inspect_messages(session_id=session_id, participant_id=participant_id, study_id=study_id)
        if history == "already_contacted":
            entry.update({"state": "contacted", "contacted_at": _timestamp(), "reason": "history_already_contacted"})
            decisions.append({"session_id": session_id, "decision": "already_contacted"})
            continue
        if history != "clear":
            entry.update({"state": "manual_review", "reason": "message_history_not_clear"})
            decisions.append({"session_id": session_id, "decision": "manual_review", "reason": "message_history_not_clear"})
            continue

        body = APPROVED_MESSAGE.format(SESSION_ID=session_id)
        entry.update({"state": "sending", "send_attempted_at": _timestamp(), "send_body": body, "send_operation": "ordinary_message", "send_attempt_count": 1})
        ledger.write(state)
        try:
            fresh.send_message(recipient_id=participant_id, body=body, study_id=study_id)
        except Exception as error:
            confirmation = fresh.inspect_messages(session_id=session_id, participant_id=participant_id, study_id=study_id)
            if confirmation == "already_contacted":
                entry.update({"state": "sent", "send_outcome": "confirmed_after_error", "confirmed_at": _timestamp()})
                decisions.append({"session_id": session_id, "decision": "sent", "reason": "confirmed_after_error"})
            else:
                entry.update({"state": "delivery_unknown", "send_outcome": "unknown", "error": str(error)})
                decisions.append({"session_id": session_id, "decision": "delivery_unknown", "reason": "reconciliation_required"})
            continue
        entry.update({"state": "sent", "send_outcome": "accepted", "sent_at": _timestamp(), "return_status_unchanged": True})
        decisions.append({"session_id": session_id, "decision": "sent"})

    ledger.write(state)
    return {"status": "ok", "decisions": decisions, "writes_performed": True}
