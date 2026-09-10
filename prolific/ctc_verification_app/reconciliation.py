"""Read-only reconciliation using Prolific's list/detail submission APIs."""
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class SubmissionReader(Protocol):
    def list_submissions(self, *, study: str, page: int = 1, page_size: int = 100) -> dict[str, Any]: ...
    def get_submission(self, submission_id: str) -> dict[str, Any]: ...


@dataclass
class LocalRecord:
    kind: str
    path: str
    session_id: str
    participant_id: str | None
    study_id: str | None
    submitted: bool | None
    assigned_at: str | None
    tasks: list[Any] | None
    error: str | None = None


@dataclass
class LocalSnapshot:
    records: list[LocalRecord]
    fatal_error: str | None = None


def _identity(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("id", "participant_id", "user_id"):
            found = _identity(value.get(key))
            if found:
                return found
    return None


def _record(path: Path, kind: str, *, session_hint: str | None = None, payload: Any = None) -> LocalRecord:
    if payload is None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return LocalRecord(kind, str(path), session_hint or path.stem, None, None, None, None, None, str(error))
    if not isinstance(payload, dict):
        return LocalRecord(kind, str(path), session_hint or path.stem, None, None, None, None, None, "JSON root is not an object")
    worker = payload.get("worker")
    if kind == "assignment" and isinstance(payload, dict):
        worker = payload
    if not isinstance(worker, dict):
        return LocalRecord(kind, str(path), session_hint or path.stem, None, None, None, None, None, "worker is not an object")
    session = _identity(worker.get("session_id")) or session_hint or path.stem
    tasks = payload.get("tasks")
    if kind in {"final_result", "archived_result"} and not isinstance(tasks, list):
        return LocalRecord(kind, str(path), session, None, None, None, None, None, "result tasks is not a list")
    return LocalRecord(kind, str(path), session, _identity(worker.get("prolific_pid") or worker.get("participant_id")),
                       _identity(worker.get("study_id") or payload.get("study_id")),
                       payload.get("submitted") if isinstance(payload.get("submitted"), bool) else None,
                       payload.get("assigned_at"), tasks if isinstance(tasks, list) else None)


def _local_snapshot(data_dir: Path) -> LocalSnapshot:
    if not data_dir.exists():
        return LocalSnapshot([], "local data directory does not exist")
    if not data_dir.is_dir():
        return LocalSnapshot([], "local data path is not a directory")
    records: list[LocalRecord] = []
    roots = (("final_result", data_dir / "submissions"), ("draft", data_dir / "drafts"),
             ("archived_result", data_dir / "excluded-results"), ("archived_result", data_dir / "excluded_submissions"))
    try:
        for kind, root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*.json"):
                if kind == "archived_result" and path.name.lower().startswith("manifest"):
                    continue
                parsed = _record(path, kind)
                # A manifest is evidence about an archive, not an archived answer.
                if kind == "archived_result" and parsed.error is None and parsed.tasks is None:
                    continue
                records.append(parsed)
        assignments = data_dir / "assignments.json"
        if assignments.exists():
            payload = json.loads(assignments.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("assignments JSON root is not an object")
            for session_id, assignment in payload.items():
                records.append(_record(assignments, "assignment", session_hint=str(session_id), payload=assignment))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return LocalSnapshot(records, f"local storage traversal/schema failure: {error}")
    return LocalSnapshot(records)


def _next_page_href(response: dict[str, Any], resource: str) -> str | None:
    if "next" in response:
        value = response["next"]
    else:
        links = response.get("_links")
        if links is None:
            return None
        if not isinstance(links, dict):
            raise ValueError(f"{resource} _links must be an object")
        next_link = links.get("next")
        if next_link is None:
            return None
        if not isinstance(next_link, dict) or "href" not in next_link:
            raise ValueError(f"{resource} _links.next must contain href")
        value = next_link["href"]
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{resource} next must be a URL")
    return value


def _pagination_count(response: dict[str, Any], resource: str) -> int | None:
    meta = response.get("meta")
    if meta is None:
        return None
    if not isinstance(meta, dict):
        raise ValueError(f"{resource} meta must be an object")
    count = meta.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"{resource} meta.count must be a non-negative integer")
    return count


def _message_page_results(response: Any) -> list[Any]:
    if not isinstance(response, dict) or not isinstance(response.get("results"), list):
        raise ValueError("message response must contain a results list")
    if not isinstance(response.get("_links"), dict):
        raise ValueError("message response must contain _links")
    return response["results"]


def _pages(reader: SubmissionReader, study_id: str, page_size: int = 100) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen_submission_ids: set[str] = set()
    expected_count: int | None = None
    page = 1
    seen_pages: set[int] = set()
    next_origin: str | None = None
    while page not in seen_pages:
        seen_pages.add(page)
        response = reader.list_submissions(study=study_id, page=page, page_size=page_size)
        if not isinstance(response, dict) or "results" not in response or not isinstance(response["results"], list):
            raise ValueError("submission response must contain a results list")
        if any(not isinstance(item, dict) for item in response["results"]):
            raise ValueError("submission results contain a non-object entry")
        page_count = _pagination_count(response, "submission")
        if page_count is None:
            raise ValueError("submission meta.count is required")
        if expected_count is not None and page_count != expected_count:
            raise ValueError("submission meta.count changed during pagination")
        expected_count = page_count
        for item in response["results"]:
            submission_id = item.get("id")
            if isinstance(submission_id, str) and submission_id in seen_submission_ids:
                continue
            if isinstance(submission_id, str):
                seen_submission_ids.add(submission_id)
            result.append(item)
        next_value = _next_page_href(response, "submission")
        if not next_value:
            if expected_count is not None and len(result) != expected_count:
                raise ValueError("unique submission count does not match meta.count")
            return result
        parsed = urlparse(next_value)
        if parsed.netloc:
            if next_origin is None:
                next_origin = parsed.netloc
            elif parsed.netloc != next_origin:
                raise ValueError("submission next URL changes origin")
        query = parse_qs(parsed.query)
        next_page = query.get("page", [None])[0]
        if not next_page or parsed.scheme not in {"", "http", "https"}:
            raise ValueError("submission next URL has no page")
        try:
            page = int(next_page)
        except ValueError as error:
            raise ValueError("submission next page is invalid") from error
        if page in seen_pages:
            raise ValueError("submission pagination loop")
    raise ValueError("submission pagination loop")


def _code_class(code: Any, valid_codes: set[str] | None) -> str:
    normalized = str(code or "").strip().upper()
    if normalized == "NOCODE": return "nocode"
    if not normalized: return "absent"
    if valid_codes is None: return "unavailable"
    return "normal" if normalized in valid_codes else "unknown"


def reconcile_current_state(reader: SubmissionReader, data_dir: Path, study_id: str,
                            valid_completion_codes: set[str] | None = None, now: Any = None,
                            assignment_timeout_minutes: int = 240) -> dict[str, Any]:
    snapshot = _local_snapshot(data_dir)
    if snapshot.fatal_error:
        return {"status": "local_storage_failed", "error": snapshot.fatal_error, "counts": {}, "submissions": [], "writes_performed": False}
    try:
        summaries = _pages(reader, study_id)
        platform = []
        for summary in summaries:
            submission_id = summary.get("id")
            if not isinstance(submission_id, str) or not submission_id:
                raise ValueError("submission summary has no string id")
            detail = reader.get_submission(submission_id)
            if not isinstance(detail, dict) or not isinstance(detail.get("id"), str):
                raise ValueError("submission detail is not an object with an id")
            if detail["id"] != submission_id or not detail.get("study_id") or not detail.get("participant") or not detail.get("status"):
                raise ValueError("submission detail is missing required identity or status")
            platform.append(detail)
    except (OSError, ValueError, HTTPError, URLError, json.JSONDecodeError) as error:
        return {"status": "platform_query_failed", "error": str(error), "counts": {}, "submissions": [], "writes_performed": False}
    by_session: dict[str, list[LocalRecord]] = {}
    for record in snapshot.records: by_session.setdefault(record.session_id, []).append(record)
    local_final = sum(r.kind == "final_result" and r.study_id == study_id and not r.error for r in snapshot.records)
    reference = now or datetime.now(timezone.utc)
    if isinstance(reference, str): reference = datetime.fromisoformat(reference.replace("Z", "+00:00"))
    claims = 0
    for record in snapshot.records:
        if record.kind != "assignment" or record.study_id != study_id or record.error or record.submitted is True: continue
        try:
            expired = bool(record.assigned_at and (reference - datetime.fromisoformat(record.assigned_at.replace("Z", "+00:00"))).total_seconds() > assignment_timeout_minutes * 60)
        except ValueError:
            expired = False
        claims += not expired
    rows = []
    for submission in platform:
        session_id = str(submission.get("id") or "")
        participant = _identity(submission.get("participant"))
        local = by_session.get(session_id, [])
        errors = sorted({r.error for r in local if r.error})
        identity_mismatch = not session_id or not participant or _identity(submission.get("study_id")) != study_id
        matching = []
        for record in local:
            if record.error: continue
            if record.study_id != study_id or record.session_id != session_id or record.participant_id != participant: identity_mismatch = True
            else: matching.append(record)
        other_session = bool(participant and any(r.participant_id == participant and r.study_id == study_id and r.session_id != session_id and not r.error for r in snapshot.records))
        final = any(r.kind == "final_result" and r.tasks for r in matching)
        status = str(submission.get("status", "")).upper().replace("_", " ").replace("-", " ")
        evidence = sorted({r.kind for r in local if not r.error} | ({"read_error"} if errors else set()) | ({"other_session_result"} if other_session else set()))
        if errors: classification, action = "local_read_error", "manual_review"
        elif identity_mismatch: classification, action = "identity_mismatch", "manual_review"
        elif status == "RETURNED": classification, action = ("returned_with_local_result" if final else "returned_without_local_result"), ("review_returned_with_result" if final else "release_claim_proposal")
        elif status == "TIMED OUT": classification, action = ("timed_out_with_local_result" if final else "timed_out_without_local_result"), ("review_timeout_with_result" if final else "release_claim_proposal")
        elif status == "AWAITING REVIEW": classification, action = ("matched" if final else "awaiting_without_final_result"), ("none" if final else "review_missing_result")
        else: classification, action = ("matched" if final else "unmatched"), ("none" if final else "manual_review")
        rows.append({"submission_id": submission.get("id"), "session_id": session_id, "study_id": submission.get("study_id"), "participant_id": participant, "status": status, "return_requested": submission.get("return_requested"), "completion_code_class": _code_class(submission.get("entered_code"), valid_completion_codes), "classification": classification, "evidence": evidence, "errors": errors, "proposed_action": action})
    return {"status": "ok", "study_id": study_id, "counts": {"platform_submissions": len(platform), "local_final_results": local_final, "temporary_claims": claims}, "submissions": rows, "writes_performed": False}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


class ProlificSubmissionClient:
    def __init__(self, token: str | None = None, base_url: str = "https://api.prolific.com/api/v1", *, timeout: float = 20, retries: int = 2, rate_delay: float = 0.0):
        self.token = token or os.environ.get("PROLIFIC_API_TOKEN")
        if not self.token: raise ValueError("PROLIFIC_API_TOKEN is required")
        self.base_url = base_url.rstrip("/")
        parsed_base = urlparse(self.base_url)
        self.scheme, self.origin = parsed_base.scheme, parsed_base.netloc
        self.messages_path = urlparse(urljoin(self.base_url + "/", "messages/")).path.rstrip("/")
        self.timeout, self.retries, self.rate_delay = timeout, retries, rate_delay
        self.opener = build_opener(_NoRedirect())

    def _get(self, path: str, query: dict[str, Any] | None = None) -> dict[str, Any]:
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        if query: url += "?" + urlencode(query)
        parsed_url = urlparse(url)
        if (parsed_url.scheme, parsed_url.netloc) != (self.scheme, self.origin): raise ValueError("request leaves configured API origin")
        for attempt in range(self.retries + 1):
            request = Request(url, headers={"Authorization": f"Token {self.token}", "Accept": "application/json"})
            try:
                with self.opener.open(request, timeout=self.timeout) as response: payload = json.loads(response.read().decode("utf-8"))
                if self.rate_delay: time.sleep(self.rate_delay)
                return payload
            except HTTPError as error:
                if error.code not in {429, 500, 502, 503, 504} or attempt == self.retries: raise
                time.sleep(float(error.headers.get("Retry-After", "1")))
            except (URLError, TimeoutError):
                if attempt == self.retries: raise
                time.sleep(2 ** attempt)
        raise RuntimeError("unreachable")

    def list_submissions(self, *, study: str, page: int = 1, page_size: int = 100) -> dict[str, Any]:
        return self._get("submissions/", {"study": study, "page": page, "page_size": page_size})

    def get_submission(self, submission_id: str) -> dict[str, Any]:
        return self._get(f"submissions/{submission_id}/")

    def _validate_message_continuation(self, next_url: str, query: dict[str, Any]) -> None:
        parsed = urlparse(next_url)
        if parsed.path.rstrip("/") != self.messages_path:
            raise ValueError("message continuation changes resource path")
        actual = parse_qs(parsed.query)
        scope_keys = {"created_after", "user_id", "study_id", "workspace_id"}
        for key in scope_keys:
            expected = query.get(key)
            values = actual.get(key)
            if expected is None:
                if values is not None:
                    raise ValueError("message continuation changes query scope")
            elif values != [str(expected)]:
                raise ValueError("message continuation changes query scope")

    def get_messages(self, *, created_after: str, study_id: str | None = None,
                     workspace_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
        """Read messages using only combinations allowed by the official contract."""
        if not user_id and not created_after:
            raise ValueError("created_after or user_id is required")
        if user_id and study_id:
            raise ValueError("study_id cannot be combined with user_id")
        query: dict[str, Any] = {"created_after": created_after}
        if user_id: query["user_id"] = user_id
        if study_id: query["study_id"] = study_id
        if workspace_id: query["workspace_id"] = workspace_id
        response = self._get("messages/", query)
        first_results = _message_page_results(response)
        combined = dict(response)
        combined["results"] = list(first_results)
        seen_urls: set[str] = set()
        next_url = _next_page_href(response, "message")
        while next_url:
            self._validate_message_continuation(next_url, query)
            if next_url in seen_urls:
                raise ValueError("message pagination loop")
            seen_urls.add(next_url)
            page = self._get(next_url)
            combined["results"].extend(_message_page_results(page))
            next_url = _next_page_href(page, "message")
        return combined

    def send_message(self, *, recipient_id: str, body: str, study_id: str) -> dict[str, Any]:
        """Send one ordinary message, preserving the approved request wording."""
        url = urljoin(self.base_url + "/", "messages/")
        if urlparse(url).netloc != self.origin:
            raise ValueError("request leaves configured API origin")
        payload = json.dumps({"recipient_id": recipient_id, "body": body, "study_id": study_id}).encode("utf-8")
        request = Request(url, data=payload, method="POST", headers={
            "Authorization": f"Token {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        with self.opener.open(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print a read-only Prolific reconciliation report")
    parser.add_argument("--study-id", required=True); parser.add_argument("--data-dir", type=Path, required=True); parser.add_argument("--token"); parser.add_argument("--base-url", default="https://api.prolific.com/api/v1"); parser.add_argument("--completion-code", action="append")
    args = parser.parse_args(argv)
    try: client = ProlificSubmissionClient(args.token, args.base_url)
    except ValueError as error: parser.error(str(error))
    report = reconcile_current_state(client, args.data_dir, args.study_id, set(args.completion_code) if args.completion_code else None)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)); return 0 if report["status"] == "ok" else 2


if __name__ == "__main__": raise SystemExit(main())
