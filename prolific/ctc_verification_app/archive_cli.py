"""Archive local results using fresh platform status; never send messages.

Execution is opt-in. Run once per timer tick; an advisory lock rejects overlap.
Reports contain identities and fixed reason codes, never API bodies or credentials.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
from typing import Any, Protocol

from .app import TASK_LOCK, VerificationStore, atomic_write_json, read_json, store_lock
from .reconciliation import ProlificSubmissionClient


class SubmissionReader(Protocol):
    def get_submission(self, submission_id: str) -> dict[str, Any]: ...


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected object")
    return value


def _consent_records(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    records = _object(path).get("records")
    if not isinstance(records, list):
        raise ValueError("invalid consent evidence")
    result = {}
    for record in records:
        if not isinstance(record, dict) or any(not isinstance(record.get(k), str) or not record[k] for k in ("record_id", "session_id", "study_id", "participant_id")) or not isinstance(record.get("consent_withdrawn"), bool):
            raise ValueError("invalid consent record")
        sid = record["session_id"]
        if sid in result and result[sid] != record:
            raise ValueError("conflicting consent evidence")
        result[sid] = record
    return result


def poll_archives(store: VerificationStore, reader: SubmissionReader, study_id: str, *, execute: bool = False, consent_path: Path | None = None) -> dict[str, Any]:
    """Inspect local finals and interrupted archives, preserving all uncertain data."""
    if not store.data_dir.is_dir() or not store.submissions_dir.is_dir():
        raise ValueError("data directory unavailable")
    consent = _consent_records(consent_path)
    lifecycle = _object(store.lifecycle_path) if store.lifecycle_path.exists() else {}
    if any(not isinstance(record, dict) for record in lifecycle.values()):
        raise ValueError("invalid lifecycle data")
    pending = {sid: record for sid, record in lifecycle.items() if isinstance(record, dict) and record.get("status") in {"PENDING", "TIMED_OUT_PENDING"}}
    candidates = {path.stem for path in store.submissions_dir.glob("*.json")} | set(pending)
    rows = []
    for sid in sorted(candidates):
        row: dict[str, Any] = {"session_id": sid, "outcome": "manual_review"}
        rows.append(row)
        try:
            if re.fullmatch(r"[A-Za-z0-9_-]+", sid) is None:
                row["reason"] = "invalid_session_id"
                continue
            path = store.submissions_dir / f"{sid}.json"
            intent = pending.get(sid)
            worker = _object(path).get("worker") if path.exists() else None
            if worker is None and intent:
                worker = {"session_id": intent.get("session_id"), "study_id": intent.get("study_id"), "prolific_pid": intent.get("participant_id")}
            if not isinstance(worker, dict) or worker.get("session_id") != sid or worker.get("study_id") != study_id or not isinstance(worker.get("prolific_pid"), str) or not worker["prolific_pid"]:
                row["reason"] = "local_identity_invalid"
                continue
            participant = worker["prolific_pid"]
            row["participant_id"] = participant
            detail = reader.get_submission(sid)
            if not isinstance(detail, dict):
                row["reason"] = "platform_response_invalid"
                continue
            remote_pid = detail.get("participant")
            if isinstance(remote_pid, dict):
                remote_pid = remote_pid.get("id")
            if detail.get("id") != sid or detail.get("study_id") != study_id or remote_pid != participant:
                row["reason"] = "platform_identity_mismatch"
                continue
            evidence = consent.get(sid)
            if evidence and (evidence["study_id"] != study_id or evidence["participant_id"] != participant or evidence["consent_withdrawn"]):
                row["reason"] = "consent_requires_review"
                continue
            if detail.get("consent_withdrawn") not in (None, False):
                row["reason"] = "platform_consent_requires_review"
                continue
            status = str(detail.get("status", "")).upper().replace("_", "-")
            if status not in {"RETURNED", "TIMED-OUT"}:
                row.update(outcome="manual_review" if intent else "unchanged", reason="pending_status_changed" if intent else "not_archive_status")
                continue
            row["platform_status"] = status
            if intent and (intent.get("session_id") != sid or intent.get("study_id") != study_id or intent.get("participant_id") != participant or (intent.get("kind") == "timeout") != (status == "TIMED-OUT")):
                row["reason"] = "intent_identity_or_status_mismatch"
                continue
            if not execute:
                row["outcome"] = "would_archive"
                continue
            if intent:
                # Resume only this freshly verified intent; never drain others implicitly.
                with TASK_LOCK, store_lock(store.lifecycle_lock_path):
                    current = read_json(store.lifecycle_path, {})
                    if current.get(sid) != intent:
                        row["reason"] = "intent_changed"
                        continue
                    expected_source = store.submissions_dir / f"{sid}.json"
                    destination = Path(intent.get("destination") or "")
                    category = "prolific_timed_out" if status == "TIMED-OUT" else "prolific_returned"
                    if intent.get("source") != str(expected_source) or destination.name != f"{sid}.json" or destination.parent.name != category or destination.parent.parent.parent.resolve() != (store.data_dir / "excluded_submissions").resolve():
                        row["reason"] = "intent_path_invalid"
                        continue
                    result = store._resume_exclusion_lifecycle(sid, current)
            elif status == "RETURNED":
                result = store.reconcile_returned(detail)
            else:
                result = store.reconcile_timed_out(detail, recover_pending=False)
            row["outcome"] = result.get("status", "manual_review")
            if result.get("status") == "manual_review":
                row["reason"] = "store_requires_review"
            if result.get("action") in {"archived_result", "released_claim"}:
                row["action"] = result["action"]
        except Exception:
            # Deliberately omit exception text: HTTP exceptions may contain secrets.
            row.update(outcome="manual_review", reason="read_or_archive_failed")
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "study_id": study_id, "execute": execute, "counts": dict(Counter(row["outcome"] for row in rows)), "sessions": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        config = _object(args.config)
        data_dir = Path(config["data_dir"])
        if not data_dir.is_dir() or not (data_dir / "submissions").is_dir():
            raise ValueError("data directory unavailable")
        args.report.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (data_dir / ".archive-poll.lock").open("a", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print('{"status":"already_running"}')
                return 0
            store = VerificationStore([], list(config["auto_labels"]), data_dir, int(config.get("bundle_size", 1)), int(config.get("redundancy", 3)), "", False)
            client = ProlificSubmissionClient(config.get("token"), str(config.get("base_url", "https://api.prolific.com/api/v1")), retries=0)
            report = poll_archives(store, client, config["study_id"], execute=args.execute, consent_path=Path(config["consent_evidence_path"]) if config.get("consent_evidence_path") else None)
            atomic_write_json(args.report, report)
            print(json.dumps({"status": "complete", "counts": report["counts"]}, sort_keys=True))
            return 0
    except Exception:
        print('{"status":"failed","reason":"configuration_or_data_unavailable"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
