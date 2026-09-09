"""Read-only reconciliation of current Prolific state and local evidence."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SubmissionReader(Protocol):
    def list_submissions(self, *, study_id: str, cursor: str | None = None, page_size: int = 100) -> dict[str, Any]: ...


@dataclass
class LocalRecord:
    kind: str
    path: str
    session_id: str
    participant_id: str | None
    study_id: str | None
    submitted: bool | None
    assigned_at: str | None
    payload: dict[str, Any] | None
    error: str | None = None


def _identity(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("id", "participant_id", "user_id"):
            result = _identity(value.get(key))
            if result:
                return result
    return None


def _read_record(path: Path, kind: str, session_hint: str | None = None) -> LocalRecord:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON root is not an object")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return LocalRecord(kind, str(path), session_hint or path.stem, None, None, None, None, None, str(error))
    worker = payload.get("worker") or payload
    return LocalRecord(
        kind, str(path), str(worker.get("session_id") or session_hint or path.stem),
        _identity(worker.get("prolific_pid") or worker.get("participant_id")),
        _identity(worker.get("study_id") or payload.get("study_id")),
        payload.get("submitted") if isinstance(payload.get("submitted"), bool) else None,
        payload.get("assigned_at"), payload,
    )


def _local_records(data_dir: Path) -> list[LocalRecord]:
    records: list[LocalRecord] = []
    roots = (("final_result", data_dir / "submissions"), ("draft", data_dir / "drafts"),
             ("archived_result", data_dir / "excluded-results"),
             ("archived_result", data_dir / "excluded_submissions"))
    for kind, root in roots:
        if root.exists():
            for path in root.rglob("*.json"):
                records.append(_read_record(path, kind))
    assignments = data_dir / "assignments.json"
    if assignments.exists():
        try:
            payload = json.loads(assignments.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("assignments JSON root is not an object")
            for session_id, assignment in payload.items():
                if not isinstance(assignment, dict):
                    records.append(_read_record(assignments, "assignment", str(session_id)))
                    continue
                records.append(_read_record(assignments, "assignment", str(session_id)))
                records[-1].payload = assignment
                records[-1].session_id = str(session_id)
                records[-1].participant_id = _identity(assignment.get("prolific_pid") or assignment.get("participant_id"))
                records[-1].study_id = _identity(assignment.get("study_id"))
                records[-1].submitted = assignment.get("submitted") if isinstance(assignment.get("submitted"), bool) else None
                records[-1].assigned_at = assignment.get("assigned_at")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            records.append(LocalRecord("assignment", str(assignments), "", None, None, None, None, None, str(error)))
    return records


def _pages(reader: SubmissionReader, study_id: str) -> list[dict[str, Any]]:
    result, cursor = [], None
    while True:
        page = reader.list_submissions(study_id=study_id, cursor=cursor, page_size=100)
        if not isinstance(page, dict):
            raise ValueError("submission page is not an object")
        items = page.get("results", page.get("data", []))
        if not isinstance(items, list):
            raise ValueError("submission results are not a list")
        result.extend(item for item in items if isinstance(item, dict))
        next_cursor = page.get("next_cursor", page.get("next"))
        if isinstance(next_cursor, dict):
            next_cursor = next_cursor.get("cursor") or next_cursor.get("id")
        if not next_cursor:
            return result
        if not isinstance(next_cursor, str) or next_cursor == cursor:
            raise ValueError("invalid or repeated submission cursor")
        cursor = next_cursor


def _code_class(code: Any, valid_codes: set[str]) -> str:
    normalized = str(code or "").strip().upper()
    if normalized == "NOCODE": return "nocode"
    if not normalized: return "absent"
    return "normal" if normalized in valid_codes else "unknown"


def _platform_identity(submission: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    participant = submission.get("participant_id") or submission.get("participant")
    return (_identity(submission.get("study_id")), str(submission.get("id") or submission.get("submission_id") or "") or None, _identity(participant))


def reconcile_current_state(reader: SubmissionReader, data_dir: Path, study_id: str,
                            valid_completion_codes: set[str] | None = None,
                            now: Any = None, assignment_timeout_minutes: int = 240) -> dict[str, Any]:
    valid_codes = {str(code).strip().upper() for code in (valid_completion_codes or {"OK", "COMPLETE", "COMPLETED"})}
    records = _local_records(data_dir)
    by_session: dict[str, list[LocalRecord]] = {}
    for record in records: by_session.setdefault(record.session_id, []).append(record)
    try: platform = _pages(reader, study_id)
    except (OSError, ValueError, HTTPError, URLError, json.JSONDecodeError) as error:
        return {"status": "platform_query_failed", "error": str(error), "counts": {"platform_submissions": 0,
                "local_final_results": sum(r.kind == "final_result" and not r.error for r in records),
                "temporary_claims": 0}, "submissions": [], "writes_performed": False}
    local_final = sum(r.kind == "final_result" and not r.error for r in records)
    reference_time = now or datetime.now(timezone.utc)
    if isinstance(reference_time, str):
        reference_time = datetime.fromisoformat(reference_time.replace("Z", "+00:00"))
    claims = 0
    for record in records:
        if record.kind != "assignment" or record.error or record.submitted is True:
            continue
        assigned_at = record.assigned_at
        expired = False
        if assigned_at:
            try:
                expired = (reference_time - datetime.fromisoformat(assigned_at.replace("Z", "+00:00"))).total_seconds() > assignment_timeout_minutes * 60
            except ValueError:
                pass
        if not expired:
            claims += 1
    rows = []
    for submission in platform:
        platform_study, session_id, participant = _platform_identity(submission)
        local = by_session.get(session_id or "", [])
        errors = sorted({r.error for r in local if r.error})
        identity_mismatch = bool(platform_study != study_id or not session_id or not participant)
        matching = []
        for record in local:
            if record.error: continue
            if record.study_id != study_id or record.session_id != session_id or record.participant_id != participant:
                identity_mismatch = True
            else: matching.append(record)
        local_participants = {r.participant_id for r in local if r.participant_id and not r.error}
        other_session = any(r.participant_id == participant and r.study_id == study_id and r.session_id != session_id
                             and not r.error for r in records) if participant else False
        other_session = other_session or any(
            r.participant_id in local_participants and r.study_id == study_id and
            r.session_id != session_id and not r.error for r in records
        )
        status = str(submission.get("status", "")).upper().replace("_", "-")
        final = any(r.kind == "final_result" for r in matching)
        evidence = sorted({r.kind for r in local if not r.error} | ({"read_error"} if errors else set()) |
                          ({"other_session_result"} if other_session else set()))
        if errors: classification, action = "local_read_error", "manual_review"
        elif identity_mismatch: classification, action = "identity_mismatch", "manual_review"
        elif status == "RETURNED": classification, action = ("returned_with_local_result" if final else "returned_without_local_result"), ("review_returned_with_result" if final else "release_claim_proposal")
        elif status == "TIMED-OUT": classification, action = ("timed_out_with_local_result" if final else "timed_out_without_local_result"), ("review_timeout_with_result" if final else "release_claim_proposal")
        elif status == "AWAITING REVIEW": classification, action = ("matched" if final else "awaiting_without_final_result"), ("none" if final else "review_missing_result")
        else: classification, action = ("matched" if final else "unmatched"), ("none" if final else "manual_review")
        rows.append({"submission_id": submission.get("id") or submission.get("submission_id"), "session_id": session_id,
                     "study_id": platform_study, "participant_id": participant, "status": status,
                     "completion_code_class": _code_class(submission.get("entered_code"), valid_codes),
                     "classification": classification, "evidence": evidence, "errors": errors,
                     "proposed_action": action})
    return {"status": "ok", "study_id": study_id, "counts": {"platform_submissions": len(platform),
            "local_final_results": local_final, "temporary_claims": claims}, "submissions": rows, "writes_performed": False}


class ProlificSubmissionClient:
    """Small read-only API adapter with pagination, retry and rate-limit handling."""
    def __init__(self, token: str, base_url: str = "https://api.prolific.com/api/v1", *, timeout: float = 20,
                 retries: int = 2, rate_delay: float = 0.0):
        self.token, self.base_url, self.timeout, self.retries, self.rate_delay = token, base_url.rstrip("/"), timeout, retries, rate_delay

    def list_submissions(self, *, study_id: str, cursor: str | None = None, page_size: int = 100) -> dict[str, Any]:
        params = f"?study_id={study_id}&page_size={page_size}" + (f"&cursor={cursor}" if cursor else "")
        for attempt in range(self.retries + 1):
            request = Request(self.base_url + "/submissions/" + params, headers={"Authorization": f"Token {self.token}", "Accept": "application/json"})
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if self.rate_delay: time.sleep(self.rate_delay)
                return payload
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == self.retries: raise
                time.sleep(float(error.headers.get("Retry-After", "1")))
            except (URLError, TimeoutError) :
                if attempt == self.retries: raise
                time.sleep(2 ** attempt)
        raise RuntimeError("unreachable")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a read-only Prolific reconciliation report")
    parser.add_argument("--study-id", required=True); parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--token"); parser.add_argument("--base-url", default="https://api.prolific.com/api/v1")
    parser.add_argument("--completion-code", action="append", default=[])
    args = parser.parse_args(argv)
    if not args.token: parser.error("--token is required for the read-only API client")
    report = reconcile_current_state(ProlificSubmissionClient(args.token, args.base_url), args.data_dir, args.study_id,
                                     set(args.completion_code) or None)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)); return 0 if report["status"] == "ok" else 2


if __name__ == "__main__": raise SystemExit(main())
