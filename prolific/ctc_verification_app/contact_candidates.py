"""Create read-only contact candidates for missing AWAITING REVIEW results.

This module deliberately stops before an outbound API call.  The reconciliation
module supplies current rows; this module persists observations and produces a
reviewable candidate or a manual-review decision.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol


WAIT_MINUTES = 10
APPROVED_MESSAGE = (
    "Hello, our records show that your Prolific submission is awaiting review, "
    "but we could not find a final annotation result for this session: {SESSION_ID}. "
    "If you were unable to complete the annotation, please return this submission "
    "on Prolific. If you believe you submitted your answers successfully, please "
    "reply so we can investigate. We’re sorry for the inconvenience."
)


class ContactLedger(Protocol):
    def read(self) -> dict[str, Any]: ...
    def write(self, value: dict[str, Any]) -> None: ...


class MessageHistory(Protocol):
    def inspect(self, *, study_id: str, session_id: str, participant_id: str) -> str: ...


@dataclass(frozen=True)
class ContactDecision:
    session_id: str
    decision: str
    evidence: list[str]
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "session_id": self.session_id,
            "decision": self.decision,
            "evidence": self.evidence,
        }
        if self.message is not None:
            result["message"] = self.message
        return result


class JsonContactLedger:
    """Small durable ledger; writes are atomic and contain no participant data beyond IDs."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"sessions": {}}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("sessions", {}), dict):
            raise ValueError("contact ledger must contain a sessions object")
        return payload

    def write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    raise ValueError("now must be a datetime or ISO timestamp")


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_contact_candidates(
    report: dict[str, Any],
    ledger: ContactLedger,
    history: MessageHistory,
    *,
    now: datetime | str | None = None,
    wait_minutes: int = WAIT_MINUTES,
) -> dict[str, Any]:
    """Return proposed candidates without sending messages or changing platform state."""
    if report.get("status") != "ok":
        return {"status": "pending", "decisions": [], "error": report.get("error", "reconciliation unavailable")}
    study_id = report.get("study_id")
    if not isinstance(study_id, str) or not study_id:
        return {"status": "manual_review", "decisions": [{"decision": "manual_review", "evidence": ["missing_study_id"]}]}
    reference = _as_datetime(now or datetime.now(timezone.utc))
    state = ledger.read()
    sessions = state.setdefault("sessions", {})
    decisions: list[ContactDecision] = []

    for row in report.get("submissions", []):
        if not isinstance(row, dict) or row.get("status") != "AWAITING REVIEW":
            continue
        session_id = row.get("session_id")
        participant_id = row.get("participant_id")
        if not isinstance(session_id, str) or not session_id:
            continue
        evidence = list(row.get("evidence", [])) if isinstance(row.get("evidence"), list) else []
        entry = sessions.setdefault(session_id, {"state": "observed"})
        if row.get("classification") != "awaiting_without_final_result":
            if entry.get("state") in {"observed", "due"}:
                entry["state"] = "resolved"
            continue
        if not isinstance(participant_id, str) or not participant_id or row.get("errors") or any(
            marker in evidence for marker in ("other_session_result", "read_error")
        ):
            decisions.append(ContactDecision(session_id, "manual_review", sorted(set(evidence + ["identity_or_storage_uncertain"]))))
            continue
        if row.get("return_requested") is True:
            entry["state"] = "contacted"
            decisions.append(ContactDecision(session_id, "already_contacted", ["platform_return_requested"]))
            continue
        first_seen = entry.get("first_missing_at")
        if not first_seen:
            entry.update({"state": "observed", "first_missing_at": _timestamp(reference), "study_id": study_id, "participant_id": participant_id})
            continue
        try:
            due = _as_datetime(first_seen) + timedelta(minutes=wait_minutes)
        except ValueError:
            decisions.append(ContactDecision(session_id, "manual_review", ["invalid_missing_observation_time"]))
            continue
        if reference < due:
            decisions.append(ContactDecision(session_id, "waiting", ["missing_result_wait_window"]))
            continue
        if entry.get("state") in {"candidate", "contacted", "manual_review"}:
            continue
        if row.get("study_id") != study_id or row.get("participant_id") != participant_id:
            entry["state"] = "manual_review"
            decisions.append(ContactDecision(session_id, "manual_review", ["identity_mismatch"])); continue
        history_state = history.inspect(study_id=study_id, session_id=session_id, participant_id=participant_id)
        if history_state == "already_contacted":
            entry["state"] = "contacted"
            decisions.append(ContactDecision(session_id, "already_contacted", ["existing_return_request_or_session_message"])); continue
        if history_state in {"ambiguous", "unavailable"}:
            entry["state"] = "manual_review"
            decisions.append(ContactDecision(session_id, "manual_review", [f"message_history_{history_state}"])); continue
        if history_state != "clear":
            entry["state"] = "manual_review"
            decisions.append(ContactDecision(session_id, "manual_review", ["invalid_message_history_result"])); continue
        entry["state"] = "candidate"
        entry["candidate_at"] = _timestamp(reference)
        decisions.append(ContactDecision(session_id, "candidate", ["awaiting_review_without_final_result", "wait_elapsed", "message_history_clear"], APPROVED_MESSAGE.format(SESSION_ID=session_id)))
    ledger.write(state)
    return {"status": "ok", "study_id": study_id, "decisions": [decision.as_dict() for decision in decisions], "writes_performed": True}
