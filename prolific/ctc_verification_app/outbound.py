"""Opt-in, durable sending of approved missing-result return requests."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from .contact_candidates import APPROVED_MESSAGE, ContactLedger, outbound_attempted


class OutboundAdapter(Protocol):
    def reconcile(self) -> dict[str, Any]: ...
    def inspect_messages(self, *, session_id: str, participant_id: str, study_id: str) -> str: ...
    def send_message(self, *, recipient_id: str, body: str, study_id: str) -> dict[str, Any]: ...


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _decision(session_id: str, decision: str, reason: str | None = None) -> dict[str, str]:
    result = {"session_id": session_id, "decision": decision}
    if reason is not None:
        result["reason"] = reason
    return result


def _recover_without_resend(entry: dict[str, Any], session_id: str, participant_id: str, study_id: str, fresh: OutboundAdapter) -> dict[str, str] | None:
    """Reconcile an interrupted attempt; never issues a second send."""
    try:
        history = fresh.inspect_messages(session_id=session_id, participant_id=participant_id, study_id=study_id)
    except Exception as error:
        entry.update({"state": "delivery_unknown", "recovery": "history_query_failed", "error": str(error)})
        return _decision(session_id, "delivery_unknown", "history_query_failed")
    if history == "already_contacted":
        entry.update({"state": "sent", "send_outcome": "confirmed_during_recovery", "confirmed_at": _timestamp()})
        return _decision(session_id, "sent", "confirmed_during_recovery")
    entry.update({"state": "delivery_unknown", "recovery": "not_confirmed"})
    return _decision(session_id, "delivery_unknown", "reconciliation_required")


def send_approved_return_requests(
    report: dict[str, Any], ledger: ContactLedger, fresh: OutboundAdapter, *,
    approved_sessions: set[str], enabled: bool = False,
) -> dict[str, Any]:
    """Send one validated ordinary message per explicitly approved candidate, if enabled."""
    if not enabled:
        return {"status": "disabled", "decisions": [], "writes_performed": False}
    if report.get("status") != "ok":
        return {"status": "pending", "decisions": [], "writes_performed": False}

    def run_locked() -> dict[str, Any]:
        state = ledger.read()
        sessions = state.setdefault("sessions", {})
        decisions: list[dict[str, str]] = []
        current_report = fresh.reconcile()
        if current_report.get("status") != "ok":
            return {"status": "pending", "decisions": [], "writes_performed": False}
        current = {row.get("session_id"): row for row in current_report.get("submissions", []) if isinstance(row, dict)}
        for session_id in sorted(approved_sessions):
            entry = sessions.get(session_id)
            if not isinstance(entry, dict) or entry.get("state") not in {"candidate", "sending", "delivery_unknown", "sent"}:
                decisions.append(_decision(session_id, "manual_review", "not_an_approved_candidate")); continue
            row = current.get(session_id)
            if not isinstance(row, dict):
                decisions.append(_decision(session_id, "cancelled", "fresh_submission_missing")); continue
            participant_id, study_id = row.get("participant_id"), row.get("study_id")
            if entry.get("participant_id") != participant_id or entry.get("study_id") != study_id:
                entry.update({"state": "manual_review", "reason": "fresh_identity_changed"})
                decisions.append(_decision(session_id, "manual_review", "fresh_identity_changed")); continue
            if not isinstance(participant_id, str) or not isinstance(study_id, str):
                entry.update({"state": "manual_review", "reason": "missing_identity"})
                decisions.append(_decision(session_id, "manual_review", "missing_identity")); continue
            if entry.get("state") == "sent" or entry.get("send_outcome") == "accepted" or entry.get("message_id"):
                entry["state"] = "sent"
                decisions.append(_decision(session_id, "sent", "already_acknowledged")); continue
            if outbound_attempted(entry) or entry.get("state") in {"sending", "delivery_unknown"}:
                decisions.append(_recover_without_resend(entry, session_id, participant_id, study_id, fresh)); continue
            latest_report = fresh.reconcile()
            if latest_report.get("status") != "ok":
                entry.update({"state": "delivery_unknown", "reason": "latest_reconciliation_unavailable"})
                decisions.append(_decision(session_id, "delivery_unknown", "latest_reconciliation_unavailable")); continue
            row = next((item for item in latest_report.get("submissions", []) if isinstance(item, dict) and item.get("session_id") == session_id), None)
            if not isinstance(row, dict):
                decisions.append(_decision(session_id, "cancelled", "fresh_submission_missing")); continue
            participant_id, study_id = row.get("participant_id"), row.get("study_id")
            if entry.get("participant_id") != participant_id or entry.get("study_id") != study_id:
                entry.update({"state": "manual_review", "reason": "fresh_identity_changed"})
                decisions.append(_decision(session_id, "manual_review", "fresh_identity_changed")); continue
            evidence = {str(item) for item in row.get("evidence", []) if isinstance(item, str)}
            evidence.update(str(item) for item in row.get("errors", []) if isinstance(item, str))
            blocked = evidence & {"draft", "archived_result", "other_session_result", "read_error", "local_read_error", "identity_mismatch", "save_error"}
            if blocked or row.get("errors") or row.get("return_requested"):
                entry.update({"state": "manual_review", "reason": "fresh_uncertain_evidence", "evidence": sorted(evidence | ({"return_requested"} if row.get("return_requested") else set()))})
                decisions.append(_decision(session_id, "manual_review", "fresh_uncertain_evidence")); continue
            if row.get("status") != "AWAITING REVIEW" or row.get("classification") != "awaiting_without_final_result":
                entry.update({"state": "cancelled", "cancelled_at": _timestamp(), "reason": "fresh_status_or_result_changed"})
                decisions.append(_decision(session_id, "cancelled", "fresh_status_or_result_changed")); continue
            try:
                history = fresh.inspect_messages(session_id=session_id, participant_id=participant_id, study_id=study_id)
            except Exception as error:
                entry.update({"state": "delivery_unknown", "reason": "message_history_query_failed", "error": str(error)})
                decisions.append(_decision(session_id, "delivery_unknown", "message_history_query_failed"))
                continue
            if history == "already_contacted":
                entry.update({"state": "contacted", "contacted_at": _timestamp(), "reason": "history_already_contacted"})
                decisions.append(_decision(session_id, "already_contacted")); continue
            if history != "clear":
                entry.update({"state": "manual_review", "reason": "message_history_not_clear"})
                decisions.append(_decision(session_id, "manual_review", "message_history_not_clear")); continue
            body = APPROVED_MESSAGE.format(SESSION_ID=session_id)
            entry.update({"state": "sending", "send_attempted_at": _timestamp(), "send_body": body, "send_operation": "ordinary_message", "send_attempt_count": 1})
            ledger.write(state)
            try:
                response = fresh.send_message(recipient_id=participant_id, body=body, study_id=study_id)
            except Exception as error:
                entry.update({"state": "delivery_unknown", "send_outcome": "unknown", "error": str(error)})
                decisions.append(_decision(session_id, "delivery_unknown", "reconciliation_required")); continue
            if not isinstance(response, dict) or not isinstance(response.get("id"), str) or not response["id"]:
                entry.update({"state": "delivery_unknown", "send_outcome": "ambiguous_response", "response_evidence": repr(response)})
                decisions.append(_decision(session_id, "delivery_unknown", "ambiguous_response")); continue
            entry.update({"state": "sent", "send_outcome": "accepted", "message_id": response["id"], "response_evidence": {"id": response["id"]}, "sent_at": _timestamp(), "return_status_unchanged": True})
            decisions.append(_decision(session_id, "sent"))
        ledger.write(state)
        return {"status": "ok", "decisions": decisions, "writes_performed": True}

    if hasattr(ledger, "locked"):
        with ledger.locked():
            return run_locked()
    return run_locked()
