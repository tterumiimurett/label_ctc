"""Read-only reconciliation of current Prolific state and local evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


class SubmissionReader(Protocol):
    def list_submissions(
        self, *, study_id: str, cursor: str | None = None, page_size: int = 100
    ) -> dict[str, Any]: ...


def _read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _local_evidence(data_dir: Path) -> dict[str, dict[str, set[str]]]:
    evidence: dict[str, dict[str, set[str]]] = {}
    locations = {
        "final_result": data_dir / "submissions",
        "archived_result": data_dir / "excluded-results",
        "draft": data_dir / "drafts",
        "assignment": data_dir,
    }
    for kind, directory in locations.items():
        paths = directory.glob("*.json") if directory.exists() else []
        for path in paths:
            if kind == "assignment" and path.name != "assignments.json":
                continue
            if kind == "assignment":
                payload = _read(path) or {}
                records = payload.values() if isinstance(payload, dict) else []
            else:
                record = _read(path)
                records = [record] if record else []
            for record in records:
                if not isinstance(record, dict):
                    continue
                worker = record.get("worker") or record
                session_id = worker.get("session_id")
                if not session_id:
                    continue
                item = evidence.setdefault(session_id, {})
                item.setdefault(kind, set()).add(path.name)
    return evidence


def _local_participants(data_dir: Path) -> dict[str, set[str]]:
    participants: dict[str, set[str]] = {}
    for directory in (data_dir / "submissions", data_dir / "excluded-results", data_dir / "drafts"):
        for path in directory.glob("*.json") if directory.exists() else []:
            record = _read(path)
            worker = (record or {}).get("worker") or {}
            participant = worker.get("prolific_pid")
            session_id = worker.get("session_id")
            if participant and session_id:
                participants.setdefault(str(participant), set()).add(str(session_id))
    return participants


def _pages(reader: SubmissionReader, study_id: str) -> list[dict[str, Any]]:
    submissions: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        page = reader.list_submissions(study_id=study_id, cursor=cursor, page_size=100)
        if not isinstance(page, dict):
            raise ValueError("submission page is not an object")
        results = page.get("results", page.get("data", []))
        if not isinstance(results, list):
            raise ValueError("submission results are not a list")
        submissions.extend(item for item in results if isinstance(item, dict))
        next_cursor = page.get("next_cursor", page.get("next"))
        if isinstance(next_cursor, dict):
            next_cursor = next_cursor.get("cursor") or next_cursor.get("id")
        if not next_cursor:
            return submissions
        if not isinstance(next_cursor, str) or next_cursor == cursor:
            raise ValueError("invalid or repeated submission cursor")
        cursor = next_cursor


def _code_class(code: Any) -> str:
    normalized = str(code or "").strip().upper()
    if normalized == "NOCODE":
        return "nocode"
    if not normalized:
        return "absent"
    return "unknown" if normalized not in {"OK", "COMPLETE", "COMPLETED"} else "normal"


def reconcile_current_state(
    reader: SubmissionReader, data_dir: Path, study_id: str
) -> dict[str, Any]:
    """Return a JSON-ready report without writing local or platform state."""
    evidence = _local_evidence(data_dir)
    participants = _local_participants(data_dir)
    try:
        platform = _pages(reader, study_id)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "status": "platform_query_failed",
            "error": str(error),
            "counts": {"platform_submissions": 0, "local_final_results": sum("final_result" in e for e in evidence.values()),
                       "temporary_claims": sum("assignment" in e for e in evidence.values())},
            "submissions": [], "writes_performed": False,
        }

    local_final = sum("final_result" in item for item in evidence.values())
    claims = sum("assignment" in item and "final_result" not in item for item in evidence.values())
    rows = []
    for submission in platform:
        session_id = str(submission.get("id") or submission.get("submission_id") or "")
        item = evidence.get(session_id, {})
        # Local filenames are not identity proof; inspect worker identity in matching records.
        identity_mismatch = False
        for kind, names in item.items():
            directory = data_dir / ("submissions" if kind == "final_result" else "excluded-results" if kind == "archived_result" else "drafts")
            for name in names:
                record = _read(directory / name) if kind != "assignment" else None
                worker = (record or {}).get("worker") or (record or {})
                if worker and any(worker.get(key) != expected for key, expected in (
                    ("study_id", study_id), ("session_id", session_id),
                    ("prolific_pid", submission.get("participant_id")),
                ) if expected is not None):
                    identity_mismatch = True
        status = str(submission.get("status", "")).upper().replace("_", "-")
        participant_id = submission.get("participant_id")
        has_other_session = any(
            other != session_id for sessions in participants.values() for other in sessions
        )
        if (participant_id and any(
            other != session_id for other in participants.get(str(participant_id), set())
        )) or (item and has_other_session):
            item = dict(item)
            item["other_session_result"] = set()
        if identity_mismatch:
            classification, action = "identity_mismatch", "manual_review"
        elif "final_result" in item:
            classification, action = "matched", "none"
        elif status == "AWAITING REVIEW":
            classification, action = "awaiting_without_final_result", "review_missing_result"
        elif status == "RETURNED":
            classification, action = "returned_with_local_evidence" if item else "returned_without_local_result", "review_returned"
        elif status == "TIMED-OUT":
            classification, action = "timed_out_with_local_evidence" if item else "timed_out_without_local_result", "review_timeout" if item else "release_claim_proposal"
        else:
            classification, action = "unmatched", "manual_review"
        rows.append({
            "submission_id": submission.get("id") or submission.get("submission_id"),
            "session_id": session_id,
            "study_id": submission.get("study_id"),
            "participant_id": submission.get("participant_id"),
            "status": status,
            "completion_code_class": _code_class(submission.get("entered_code")),
            "classification": classification,
            "evidence": sorted(item),
            "proposed_action": action,
        })
    return {"status": "ok", "study_id": study_id, "counts": {
        "platform_submissions": len(platform), "local_final_results": local_final,
        "temporary_claims": claims,
    }, "submissions": rows, "writes_performed": False}
