#!/usr/bin/env python3
"""Prolific app for annotating pre-labelled stuck-speech interruptions."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import mimetypes
import os
import re
import sys
import tempfile
import threading
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPLETION_URL = "https://app.prolific.com/submissions/complete"
SCHEMA_VERSION = "ctc-verification-v1"
TASK_LOCK = threading.Lock()

@contextmanager
def store_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
FILLER_WORDS = {"ah", "eh", "er", "hm", "hmm", "mhm", "mm", "oh", "ok", "okay", "uh", "uhh", "um", "umm", "yeah", "yep"}
FILLER_PHRASES = {"uh huh", "uh-huh", "mhm", "mm hmm", "you know"}
DEFAULT_ASSIGNMENT_TIMEOUT_MINUTES = 240


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_transcript(text: str | None) -> str:
    normalized = re.sub(r"[^\w\s'-]+", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", normalized).strip()


def has_non_filler_word(text: str | None) -> bool:
    normalized = normalize_transcript(text)
    if not normalized or normalized in FILLER_PHRASES:
        return False
    return any(word.strip("'") not in FILLER_WORDS for word in normalized.split())


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
    finally:
        if os.path.exists(name): os.unlink(name)


def atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


def first(params: dict[str, list[str]], key: str) -> str:
    return (params.get(key) or [""])[0].strip()


def validate_worker(params: dict[str, list[str]]) -> tuple[dict[str, str] | None, list[str]]:
    worker = {
        "prolific_pid": first(params, "PROLIFIC_PID"),
        "study_id": first(params, "STUDY_ID"),
        "session_id": first(params, "SESSION_ID"),
    }
    errors = [
        f"Missing {name}."
        for name, value in worker.items()
        if not value
    ]
    return (None if errors else worker), errors


def task_id_from_candidate(candidate: dict) -> str:
    parts = str(candidate.get("candidate_key", "")).split("|")
    if len(parts) < 5:
        return ""
    try:
        start = float(parts[3])
        end = float(parts[4])
    except ValueError:
        return ""
    return f"seamless_ctc_{parts[0]}_{int(start * 100 + 0.5):06d}_{int(end * 100 + 0.5):06d}"


def candidate_window(candidate: dict) -> tuple[float | None, float | None]:
    parts = str(candidate.get("candidate_key", "")).split("|")
    if len(parts) >= 5:
        try:
            return float(parts[3]), float(parts[4])
        except ValueError:
            pass
    context = candidate.get("turn_completion_context") or {}
    return context.get("candidate_dialogue_start_s"), context.get("candidate_dialogue_end_s")


def relative_time(value: float | None, clip_start: float | None) -> float | None:
    if not isinstance(value, (int, float)) or clip_start is None:
        return None
    return round(max(0, value - clip_start), 2)


def relative_region(source: dict | None, clip_start: float | None) -> dict | None:
    if not isinstance(source, dict):
        return None
    start = source.get("start")
    end = source.get("end", source.get("stop"))
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return None
    return {
        "start": relative_time(start, clip_start),
        "end": relative_time(end, clip_start),
        "transcript": source.get("transcript") or source.get("utterance") or "",
    }


def load_source_tasks(paths: list[Path]) -> dict[str, dict]:
    task_by_id: dict[str, dict] = {}
    for path in paths:
        if path.suffix == ".jsonl":
            raw_tasks = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        else:
            raw_tasks = json.loads(path.read_text(encoding="utf-8"))
        for task in raw_tasks:
            data = task.get("data") or task
            audio_url = data.get("audio") or data.get("audio_url") or data.get("outer_url") or ""
            if not audio_url:
                continue
            task_id = Path(audio_url).stem
            task_by_id[task_id] = {
                "task_id": task_id,
                "audio_url": audio_url,
                "path_seg": data.get("path_seg", ""),
                "inner_url": data.get("inner_url", ""),
                "user": data.get("user", data.get("victim_id", "")),
                "assistant": data.get("assistant", data.get("interrupter_id", "")),
            }
    return task_by_id


def load_auto_candidates(patterns: list[str]) -> list[dict]:
    rows: list[dict] = []
    for pattern in dict.fromkeys(patterns):
        for path_name in sorted(glob.glob(pattern)):
            path = Path(path_name)
            with path.open(encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    candidate = json.loads(line)
                    candidate["_source_file"] = path.name
                    candidate["_line_number"] = line_number
                    rows.append(candidate)
    return rows


def candidate_audio_url(candidate: dict) -> str:
    tos_audio = candidate.get("tos_audio") or {}
    if isinstance(tos_audio, dict):
        return str(tos_audio.get("outer_url") or tos_audio.get("inner_url") or "")
    return ""


def default_stall_time(candidate: dict, clip_start: float | None) -> float | None:
    last_word_end = relative_time(candidate.get("main_speaker_last_word_end_time"), clip_start)
    if last_word_end is not None:
        return last_word_end
    word = candidate.get("interrupted_word") or {}
    word_time = relative_time(word.get("end"), clip_start)
    if word_time is not None:
        return word_time
    start_time = relative_time(candidate.get("interrupter_start_time"), clip_start)
    if start_time is not None:
        return start_time
    region = relative_region(candidate.get("interrupted_segment_context"), clip_start)
    return region.get("end") if region else None


def verification_task(candidate: dict, source_task: dict) -> dict:
    clip_start, clip_end = candidate_window(candidate)
    candidate_key = candidate.get("candidate_key", "")
    candidate_id = hashlib.sha1(candidate_key.encode("utf-8")).hexdigest()[:16]
    audio_url = source_task.get("audio_url") or candidate_audio_url(candidate)
    task_id = source_task.get("task_id") or task_id_from_candidate(candidate)
    tos_audio = candidate.get("tos_audio") or {}
    left_speaker = source_task.get("user", "")
    right_speaker = source_task.get("assistant", "")
    if isinstance(tos_audio, dict):
        left_channel = tos_audio.get("left_channel") or {}
        right_channel = tos_audio.get("right_channel") or {}
        left_speaker = left_speaker or left_channel.get("speaker_id", "")
        right_speaker = right_speaker or right_channel.get("speaker_id", "")
    interrupted_region = relative_region(
        candidate.get("interrupted_segment_context"),
        clip_start,
    )
    interrupting_region = relative_region(
        candidate.get("interrupter_matched_dialogue_turn"),
        clip_start,
    )
    return {
        "candidate_id": candidate_id,
        "task_id": task_id,
        "audio_url": audio_url,
        "clip_start": clip_start,
        "clip_end": clip_end,
        "duration": round(clip_end - clip_start, 2)
        if isinstance(clip_start, (int, float)) and isinstance(clip_end, (int, float))
        else None,
        "speakers": {
            "interrupted": candidate.get("victim_id", ""),
            "interrupting": candidate.get("interrupter_id", ""),
            "left": left_speaker,
            "right": right_speaker,
        },
        "prelabel": {
            "candidate_key": candidate_key,
            "source_file": candidate.get("_source_file", ""),
            "line_number": candidate.get("_line_number"),
            "pred_confidence": candidate.get("pred_confidence", ""),
            "pred_completion_target": candidate.get("pred_completion_target", ""),
            "audio_verify": candidate.get("audio_verify"),
            "main_speaker_pre_interrupt_transcript": candidate.get(
                "main_speaker_pre_interrupt_transcript",
                "",
            ),
            "interrupter_post_start_utterance": candidate.get(
                "interrupter_post_start_utterance",
                "",
            ),
            "victim_text": candidate.get("victim_text", ""),
            "interrupter_text": candidate.get("interrupter_text", ""),
        },
        "regions": {
            "interrupted": interrupted_region,
            "interrupting": interrupting_region,
        },
        "prelabels": {
            "stall_time": default_stall_time(candidate, clip_start),
            "interrupting_start_time": interrupting_region.get("start")
            if interrupting_region
            else relative_time(candidate.get("interrupter_start_time"), clip_start),
        },
    }


def load_verification_tasks(
    source_task_paths: list[Path],
    auto_label_patterns: list[str],
    include_audio_unverified: bool = False,
    include_non_ctc: bool = False,
) -> list[dict]:
    source_tasks = load_source_tasks(source_task_paths)
    tasks = []
    seen_candidate_ids: set[str] = set()
    for candidate in load_auto_candidates(auto_label_patterns):
        if not include_non_ctc and candidate.get("pred_is_ctc") is not True:
            continue
        audio_verify = candidate.get("audio_verify") or {}
        if (
            not include_non_ctc
            and not include_audio_unverified
            and audio_verify.get("verify_is_ctc") is not True
        ):
            continue
        source_task = source_tasks.get(task_id_from_candidate(candidate)) or {}
        if not source_task and not candidate_audio_url(candidate):
            continue
        task = verification_task(candidate, source_task)
        if task["candidate_id"] in seen_candidate_ids:
            continue
        seen_candidate_ids.add(task["candidate_id"])
        tasks.append(task)
    tasks.sort(key=lambda task: task["task_id"])
    if not tasks:
        raise ValueError("No pre-labelled CTC candidates matched the source tasks.")
    return tasks


class VerificationStore:
    def __init__(
        self,
        source_task_paths: list[Path],
        auto_label_patterns: list[str],
        data_dir: Path,
        bundle_size: int,
        redundancy: int,
        completion_url: str,
        include_audio_unverified: bool,
        include_non_ctc: bool = False,
        assignment_timeout_minutes: int = DEFAULT_ASSIGNMENT_TIMEOUT_MINUTES,
    ) -> None:
        self.tasks = load_verification_tasks(
            source_task_paths,
            auto_label_patterns,
            include_audio_unverified=include_audio_unverified,
            include_non_ctc=include_non_ctc,
        )
        self.data_dir = data_dir
        self.assignments_path = data_dir / "assignments.json"
        self.lifecycle_path = data_dir / "returned-lifecycle.json"
        self.lifecycle_lock_path = data_dir / ".lifecycle.lock"
        self.submissions_dir = data_dir / "submissions"
        self.drafts_dir = data_dir / "drafts"
        self.bundle_size = bundle_size
        self.redundancy = redundancy
        self.completion_url = completion_url
        self.assignment_timeout_minutes = assignment_timeout_minutes

    def assign(self, worker: dict[str, str]) -> dict:
        session_id = worker["session_id"]
        with TASK_LOCK, store_lock(self.lifecycle_lock_path):
            blocked = self._operation_gate(session_id)
            if blocked: return blocked
            assignments = read_json(self.assignments_path, {})
            existing = assignments.get(session_id)
            lifecycle = read_json(self.lifecycle_path, {})
            self._recover_timed_out_intents(lifecycle, assignments)
            if session_id in lifecycle and lifecycle[session_id].get("status") in {"RETURNED", "TIMED_OUT"}:
                return {"status": "error", "errors": ["This returned session cannot be assigned again."]}
            if existing:
                if any(
                    existing.get(key) != worker.get(key)
                    for key in ("prolific_pid", "study_id")
                ):
                    return {
                        "status": "error",
                        "errors": ["SESSION_ID is already assigned to a different participant."],
                    }
                current_candidate_ids = {task["candidate_id"] for task in self.tasks}
                if len(existing.get("candidate_ids", [])) != self.bundle_size or any(
                    candidate_id not in current_candidate_ids
                    for candidate_id in existing.get("candidate_ids", [])
                ):
                    del assignments[session_id]
                    atomic_write_json(self.assignments_path, assignments)
                else:
                    return self._assignment_response(existing, worker)

            task_counts = self._claim_counts(assignments)
            existing_worker_candidates = {
                candidate_id
                for assignment in assignments.values()
                if assignment.get("prolific_pid") == worker["prolific_pid"]
                for candidate_id in assignment.get("candidate_ids", [])
            }
            existing_worker_candidates.update(
                self._submitted_candidate_ids_for_worker(worker["prolific_pid"])
            )
            candidates = [
                task
                for task in self.tasks
                if task_counts.get(task["candidate_id"], 0) < self.redundancy
                and task["candidate_id"] not in existing_worker_candidates
            ]
            if len(candidates) < self.bundle_size:
                return {
                    "status": "error",
                    "errors": [
                        "No unassigned pre-labelled candidates remain for this study. "
                        "Please return the Prolific submission."
                    ],
                }
            candidates.sort(key=lambda task: (task_counts.get(task["candidate_id"], 0), task["task_id"]))
            chosen = candidates[: self.bundle_size]
            assignment = {
                "bundle_id": f"bundle_{len(assignments):05d}",
                "session_id": session_id,
                "prolific_pid": worker["prolific_pid"],
                "study_id": worker["study_id"],
                "candidate_ids": [task["candidate_id"] for task in chosen],
                "assigned_at": utc_now(),
                "submitted": False,
            }
            assignments[session_id] = assignment
            atomic_write_json(self.assignments_path, assignments)
            return self._assignment_response(assignment, worker)

    def reconcile_returned(self, submission: dict, *, processed_at: str | None = None, consent_withdrawn: bool = False) -> dict:
        """Run the validated returned transaction; safe to resume after interruption."""
        if consent_withdrawn:
            return {"status": "manual_review", "reason": "consent withdrawal requires separate handling"}
        if not isinstance(submission, dict) or str(submission.get("status", "")).upper() != "RETURNED":
            return {"status": "manual_review", "reason": "current platform status is not RETURNED"}
        session_id = str(submission.get("id") or "")
        participant = submission.get("participant")
        participant_id = participant.get("id") if isinstance(participant, dict) else participant
        study_id = submission.get("study_id")
        if not session_id or not participant_id or not study_id:
            return {"status": "manual_review", "reason": "returned observation lacks identity"}
        with TASK_LOCK, store_lock(self.lifecycle_lock_path):
            lifecycle = read_json(self.lifecycle_path, {}); prior = lifecycle.get(session_id)
            if prior and (prior.get("kind") == "timeout" or str(prior.get("status", "")).startswith("TIMED_OUT")):
                if any(prior.get(key) != value for key, value in (("session_id", session_id), ("study_id", study_id), ("participant_id", participant_id))):
                    return {"status": "manual_review", "reason": "timeout lifecycle identity mismatch"}
                return {"status": "manual_review", "reason": "timed-out lifecycle cannot be processed as RETURNED"}
            if prior and prior.get("status") == "RETURNED": return {"status": "already_processed", "session_id": session_id}
            if prior: return self._resume_returned(session_id, lifecycle)
            assignments = read_json(self.assignments_path, {})
            assignment = assignments.get(session_id)
            if assignment and any(assignment.get(k) != v for k, v in (("session_id", session_id), ("study_id", study_id), ("prolific_pid", participant_id))):
                return {"status": "manual_review", "reason": "assignment identity mismatch"}
            result_path = self.submissions_dir / f"{safe_name(session_id)}.json"; result = read_json(result_path, None) if result_path.exists() else None
            if result is not None:
                worker = result.get("worker") or {}
                if any(worker.get(k) != v for k, v in (("session_id", session_id), ("study_id", study_id), ("prolific_pid", participant_id))):
                    return {"status": "manual_review", "reason": "result identity mismatch"}
                raw = result_path.read_bytes(); destination = self.data_dir / "excluded_submissions" / datetime.now(timezone.utc).strftime("%Y-%m-%d") / "prolific_returned" / f"{safe_name(session_id)}.json"
                if destination.exists() and destination.read_bytes() != raw: return {"status": "manual_review", "reason": "archive collision differs"}
                action = "archived_result"; source = str(result_path); dest = str(destination); digest = hashlib.sha256(raw).hexdigest()
            else:
                raw = b""; action = "released_claim"; source = None; dest = None; digest = None
            intent = {"status": "PENDING", "stage": "intent", "session_id": session_id, "study_id": study_id, "participant_id": participant_id, "assignment": assignment, "source": source, "destination": dest, "sha256": digest, "reason": "platform RETURNED", "processed_at": processed_at or utc_now(), "action": action}
            lifecycle[session_id] = intent; atomic_write_json(self.lifecycle_path, lifecycle)
            return self._resume_returned(session_id, lifecycle)

    def reconcile_timed_out(self, submission: dict, *, processed_at: str | None = None) -> dict:
        """Release an answerless timed-out claim; answered sessions need review."""
        if not isinstance(submission, dict) or str(submission.get("status", "")).upper().replace("_", "-") != "TIMED-OUT":
            return {"status": "manual_review", "reason": "current platform status is not TIMED-OUT"}
        session_id = str(submission.get("id") or "")
        participant = submission.get("participant")
        participant_id = participant.get("id") if isinstance(participant, dict) else participant
        study_id = submission.get("study_id")
        if not session_id or not participant_id or not study_id:
            return {"status": "manual_review", "reason": "timeout observation lacks identity"}
        with TASK_LOCK, store_lock(self.lifecycle_lock_path):
            lifecycle = read_json(self.lifecycle_path, {})
            assignments = read_json(self.assignments_path, {})
            self._recover_timed_out_intents(lifecycle, assignments)
            prior = lifecycle.get(session_id)
            if prior and (prior.get("kind") == "timeout" or str(prior.get("status", "")).startswith("TIMED_OUT")):
                if any(prior.get(key) != value for key, value in (("session_id", session_id), ("study_id", study_id), ("participant_id", participant_id))):
                    return {"status": "manual_review", "reason": "timeout lifecycle identity mismatch"}
                if prior.get("status") == "TIMED_OUT":
                    return {"status": "already_processed", "session_id": session_id}
                return {"status": "manual_review", "reason": "timed-out lifecycle requires manual review"}
            if prior:
                return {"status": "manual_review", "reason": "session has an incompatible lifecycle"}
            assignment = assignments.get(session_id)
            if assignment and any(assignment.get(k) != v for k, v in (("session_id", session_id), ("study_id", study_id), ("prolific_pid", participant_id))):
                return {"status": "manual_review", "reason": "assignment identity mismatch"}
            result_path = self.submissions_dir / f"{safe_name(session_id)}.json"
            if result_path.exists():
                result = read_json(result_path, None)
                if not isinstance(result, dict):
                    return {"status": "manual_review", "reason": "timed-out result is unreadable"}
                worker = result.get("worker") or {}
                if any(worker.get(k) != v for k, v in (("session_id", session_id), ("study_id", study_id), ("prolific_pid", participant_id))):
                    return {"status": "manual_review", "reason": "timed-out result identity mismatch"}
                raw = result_path.read_bytes()
                destination = self.data_dir / "excluded_submissions" / datetime.now(timezone.utc).strftime("%Y-%m-%d") / "prolific_timed_out" / f"{safe_name(session_id)}.json"
                if destination.exists() and destination.read_bytes() != raw:
                    return {"status": "manual_review", "reason": "timed-out archive collision differs"}
                record = {"kind": "timeout", "status": "TIMED_OUT_PENDING", "stage": "intent", "session_id": session_id,
                          "study_id": study_id, "participant_id": participant_id, "assignment": assignment,
                          "source": str(result_path), "destination": str(destination),
                          "sha256": hashlib.sha256(raw).hexdigest(), "reason": "platform TIMED-OUT",
                          "processed_at": processed_at or utc_now(), "action": "archived_result"}
                lifecycle[session_id] = record
                atomic_write_json(self.lifecycle_path, lifecycle)
                return self._resume_returned(session_id, lifecycle)
            record = {"kind": "timeout", "status": "TIMED_OUT", "stage": "claim_release", "session_id": session_id, "study_id": study_id,
                      "participant_id": participant_id, "assignment": assignment, "reason": "platform TIMED-OUT",
                      "processed_at": processed_at or utc_now(), "action": "released_claim"}
            lifecycle[session_id] = record
            atomic_write_json(self.lifecycle_path, lifecycle)
            if assignment is not None:
                current = read_json(self.assignments_path, {}).get(session_id)
                if current != assignment:
                    record["status"] = "TIMED_OUT_MANUAL"; record["stage"] = "claim_release_conflict"
                    atomic_write_json(self.lifecycle_path, lifecycle)
                    return {"status": "manual_review", "reason": "assignment changed during timeout"}
                assignments.pop(session_id, None)
                atomic_write_json(self.assignments_path, assignments)
            record["stage"] = "complete"
            atomic_write_json(self.lifecycle_path, lifecycle)
            return {"status": "processed", "session_id": session_id, "action": "released_claim"}

    def _resume_returned(self, session_id: str, lifecycle: dict) -> dict:
        record = lifecycle[session_id]; source = Path(record["source"]) if record.get("source") else None; destination = Path(record["destination"]) if record.get("destination") else None
        if destination:
            if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() != record["sha256"]: return {"status": "manual_review", "reason": "archive hash mismatch"}
            if not destination.exists():
                if not source or not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest() != record["sha256"]: return {"status": "manual_review", "reason": "source missing or hash mismatch"}
                atomic_write_bytes(destination, source.read_bytes())
            record["stage"] = "archive_written"; lifecycle[session_id] = record; atomic_write_json(self.lifecycle_path, lifecycle)
            if source.exists():
                if hashlib.sha256(source.read_bytes()).hexdigest() != record["sha256"]: return {"status": "manual_review", "reason": "source changed"}
                source.unlink()
            record["stage"] = "source_removed"
        assignments = read_json(self.assignments_path, {}); expected = record.get("assignment")
        current = assignments.get(session_id)
        if current is not None and expected is not None and current != expected: return {"status": "manual_review", "reason": "assignment changed during return"}
        if current is not None: del assignments[session_id]; atomic_write_json(self.assignments_path, assignments)
        record["stage"] = "assignment_removed"
        record["status"] = "TIMED_OUT" if record.get("kind") == "timeout" else "RETURNED"
        lifecycle[session_id] = record
        atomic_write_json(self.lifecycle_path, lifecycle)
        return {"status": "processed", "session_id": session_id, "action": record["action"]}

    def _recover_timed_out_intents(self, lifecycle: dict, assignments: dict) -> None:
        """Drain timeout releases globally while holding the lifecycle lock."""
        changed = False
        for session_id, record in list(lifecycle.items()):
            if record.get("kind") != "timeout":
                continue
            if record.get("status") == "TIMED_OUT_PENDING":
                self._resume_returned(session_id, lifecycle)
                continue
            if record.get("status") != "TIMED_OUT" or record.get("stage") != "claim_release":
                continue
            result_path = self.submissions_dir / f"{safe_name(session_id)}.json"
            if result_path.exists():
                record["status"] = "TIMED_OUT_MANUAL"
                record["stage"] = "final_result_conflict"
                lifecycle[session_id] = record
                changed = True
                continue
            expected = record.get("assignment")
            current = assignments.get(session_id)
            if current is not None and current != expected:
                record["status"] = "TIMED_OUT_MANUAL"
                record["stage"] = "claim_release_conflict"
                lifecycle[session_id] = record
                changed = True
                continue
            if current is not None:
                assignments.pop(session_id, None)
                atomic_write_json(self.assignments_path, assignments)
            record["stage"] = "complete"
            lifecycle[session_id] = record
            changed = True
        if changed:
            atomic_write_json(self.lifecycle_path, lifecycle)

    def _recover_returned_intents(self) -> None:
        lifecycle = read_json(self.lifecycle_path, {})
        for session_id, record in list(lifecycle.items()):
            if record.get("status") == "PENDING": self._resume_returned(session_id, lifecycle)

    def _claim_counts(self, assignments: dict) -> dict[str, int]:
        counts = {
            candidate_id: len(prolific_pids)
            for candidate_id, prolific_pids in self._submitted_participants_by_candidate().items()
        }
        for assignment in assignments.values():
            if assignment.get("submitted") or self._assignment_is_expired(assignment):
                continue
            for candidate_id in assignment.get("candidate_ids", []):
                counts[candidate_id] = counts.get(candidate_id, 0) + 1
        return counts

    def _assignment_is_expired(self, assignment: dict) -> bool:
        if self.assignment_timeout_minutes <= 0:
            return False
        assigned_at = parse_utc_timestamp(assignment.get("assigned_at"))
        if assigned_at is None:
            return False
        age_seconds = (datetime.now(timezone.utc) - assigned_at).total_seconds()
        return age_seconds > self.assignment_timeout_minutes * 60

    def _submitted_participants_by_candidate(self) -> dict[str, set[str]]:
        participants: dict[str, set[str]] = {}
        for path in self.submissions_dir.glob("*.json"):
            try:
                payload = read_json(path, {})
            except (OSError, json.JSONDecodeError):
                continue
            worker = payload.get("worker") or {}
            prolific_pid = worker.get("prolific_pid")
            if not prolific_pid:
                continue
            for task in payload.get("tasks", []):
                candidate_id = task.get("candidate_id")
                if candidate_id:
                    participants.setdefault(candidate_id, set()).add(prolific_pid)
        return participants

    def _submitted_candidate_ids_for_worker(self, prolific_pid: str) -> set[str]:
        candidate_ids: set[str] = set()
        for path in self.submissions_dir.glob("*.json"):
            try:
                payload = read_json(path, {})
            except (OSError, json.JSONDecodeError):
                continue
            worker = payload.get("worker") or {}
            if worker.get("prolific_pid") != prolific_pid:
                continue
            for task in payload.get("tasks", []):
                candidate_id = task.get("candidate_id")
                if candidate_id:
                    candidate_ids.add(candidate_id)
        return candidate_ids

    def _assignment_response(self, assignment: dict, worker: dict[str, str]) -> dict:
        task_by_id = {task["candidate_id"]: task for task in self.tasks}
        assigned_tasks = [task_by_id[candidate_id] for candidate_id in assignment["candidate_ids"]]
        return {
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "worker": worker,
            "assignment": {
                "bundle_id": assignment["bundle_id"],
                "assigned_at": assignment["assigned_at"],
                "task_count": len(assigned_tasks),
            },
            "completion_url": self.completion_url,
            "tasks": assigned_tasks,
        }

    def _operation_gate(self, session_id: str) -> dict | None:
        try:
            self._recover_returned_intents()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return {"status": "error", "errors": [f"Returned lifecycle recovery requires manual review: {error}"]}
        lifecycle = read_json(self.lifecycle_path, {})
        assignments = read_json(self.assignments_path, {})
        self._recover_timed_out_intents(lifecycle, assignments)
        record = lifecycle.get(session_id)
        if record and record.get("status") not in {"RETURNED", "TIMED_OUT"}:
            return {"status": "error", "errors": ["This session has an unresolved returned lifecycle; manual review is required."]}
        if record and record.get("status") in {"RETURNED", "TIMED_OUT"}:
            return {"status": "error", "errors": ["This returned session cannot be used again."]}
        return None

    def load_draft(self, worker: dict[str, str]) -> dict:
        session_id = worker["session_id"]
        with TASK_LOCK, store_lock(self.lifecycle_lock_path):
            blocked = self._operation_gate(session_id)
            if blocked: return blocked
            assignments = read_json(self.assignments_path, {})
            assignment = assignments.get(session_id)
            errors = self._assignment_identity_errors(assignment, worker)
            if errors:
                return {"status": "error", "errors": errors}
            if assignment.get("submitted"):
                return {"status": "ok", "draft": None}
            draft = read_json(self.drafts_dir / f"{safe_name(session_id)}.json", None)
            return {"status": "ok", "draft": draft}

    def save_draft(self, payload: dict) -> dict:
        worker = payload.get("worker") if isinstance(payload, dict) else None
        session_id = worker.get("session_id") if isinstance(worker, dict) else ""
        if not session_id:
            return {"status": "error", "errors": ["Draft is missing worker.session_id."]}
        with TASK_LOCK, store_lock(self.lifecycle_lock_path):
            blocked = self._operation_gate(session_id)
            if blocked: return blocked
            assignments = read_json(self.assignments_path, {})
            assignment = assignments.get(session_id)
            errors = self._assignment_identity_errors(assignment, worker)
            if errors:
                return {"status": "error", "errors": errors}
            if assignment.get("submitted"):
                return {"status": "error", "errors": ["Cannot save a draft after submission."]}
            expected = set(assignment.get("candidate_ids", []))
            draft_ids = {
                item.get("task", {}).get("candidate_id")
                for item in payload.get("taskState", [])
                if isinstance(item, dict)
            }
            if expected != draft_ids:
                return {
                    "status": "error",
                    "errors": ["Draft candidate_ids do not match assigned candidate_ids."],
                }
            payload["server_metadata"] = {
                "saved_at": utc_now(),
                "assignment": assignment,
            }
            atomic_write_json(self.drafts_dir / f"{safe_name(session_id)}.json", payload)
        return {"status": "ok"}

    def _assignment_identity_errors(self, assignment: dict | None, worker: dict) -> list[str]:
        if not assignment:
            return ["No assignment exists for this SESSION_ID."]
        if any(
            assignment.get(key) != worker.get(key)
            for key in ("prolific_pid", "study_id", "session_id")
        ):
            return ["Worker identity does not match this assignment."]
        return []

    def submit(self, payload: dict) -> dict:
        worker = payload.get("worker") if isinstance(payload, dict) else None
        session_id = worker.get("session_id") if isinstance(worker, dict) else ""
        if not session_id:
            return {"status": "error", "errors": validate_submission(payload)}
        with TASK_LOCK, store_lock(self.lifecycle_lock_path):
            blocked = self._operation_gate(session_id)
            if blocked: return blocked
            assignments = read_json(self.assignments_path, {})
            assignment = assignments.get(session_id)
            if not assignment:
                return {"status": "error", "errors": ["No assignment exists for this SESSION_ID."]}
            if any(
                assignment.get(key) != worker.get(key)
                for key in ("prolific_pid", "study_id", "session_id")
            ):
                return {
                    "status": "error",
                    "errors": ["Worker identity does not match this assignment."],
                }
            if assignment.get("submitted"):
                return {
                    "status": "ok",
                    "completion_url": self.completion_url,
                    "already_submitted": True,
                }
            errors = validate_submission(payload)
            if errors:
                return {"status": "error", "errors": errors}
            expected = set(assignment.get("candidate_ids", []))
            received_task_ids = [task.get("candidate_id", "") for task in payload.get("tasks", [])]
            received = set(received_task_ids)
            if expected != received:
                return {
                    "status": "error",
                    "errors": ["Submitted candidate_ids do not match assigned candidate_ids."],
                }
            if len(received) != len(received_task_ids):
                return {"status": "error", "errors": ["Submission contains duplicate candidate_ids."]}
            submitted_participants = self._submitted_participants_by_candidate()
            capacity_errors = []
            for candidate_id in received:
                previous_participants = submitted_participants.get(candidate_id, set())
                if worker["prolific_pid"] in previous_participants:
                    capacity_errors.append(
                        "This participant has already submitted this candidate in another session."
                    )
                elif len(previous_participants) >= self.redundancy:
                    capacity_errors.append(
                        "This candidate already has the required number of submitted annotations."
                    )
            if capacity_errors:
                return {"status": "error", "errors": sorted(set(capacity_errors))}
            payload["server_metadata"] = {
                "received_at": utc_now(),
                "assignment": assignment,
            }
            atomic_write_json(self.submissions_dir / f"{safe_name(session_id)}.json", payload)
            draft_path = self.drafts_dir / f"{safe_name(session_id)}.json"
            if draft_path.exists():
                draft_path.unlink()
            assignment["submitted"] = True
            assignment["submitted_at"] = payload["server_metadata"]["received_at"]
            assignments[session_id] = assignment
            atomic_write_json(self.assignments_path, assignments)
        return {"status": "ok", "completion_url": self.completion_url}


def validate_submission(payload: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["Submission must be a JSON object."]
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}.")
    worker = payload.get("worker") or {}
    if not isinstance(worker, dict):
        worker = {}
    for key in ("prolific_pid", "study_id", "session_id"):
        if not worker.get(key):
            errors.append(f"Missing worker.{key}.")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("Submission must include at least one task.")
        return errors
    word_phrase_types = {"word_phrase", "word_phrase_confident", "word_phrase_unsure"}
    valid_types = word_phrase_types | {"guiding_question", "other"}
    for index, task in enumerate(tasks, 1):
        prefix = f"Item {index}"
        if not isinstance(task, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        if not task.get("candidate_id"):
            errors.append(f"{prefix}: missing candidate_id.")
        if not task.get("task_id"):
            errors.append(f"{prefix}: missing task_id.")
        relevant_interruption = task.get("relevant_interruption")
        if not isinstance(relevant_interruption, bool):
            errors.append(
                f"{prefix}: answer whether the second speaker's utterance completes the first speaker's unfinished sentence."
            )
            continue
        if relevant_interruption is False:
            continue
        interrupting_start_time = task.get("interrupting_start_time")
        duration = task.get("duration")
        if not isinstance(interrupting_start_time, (int, float)):
            errors.append(f"{prefix}: mark the start timestamp of the interrupting utterance.")
        elif isinstance(duration, (int, float)) and not 0 <= interrupting_start_time <= duration:
            errors.append(
                f"{prefix}: start timestamp of the interrupting utterance must be within the audio clip."
            )
        if task.get("interrupting_start_checked") is not True:
            errors.append(
                f"{prefix}: confirm that you checked the start of the interrupting utterance."
            )
        if not str(task.get("corrected_interrupted_transcript") or "").strip():
            errors.append(
                f"{prefix}: enter the interrupted utterance transcript and remove words after the interruption."
            )
        speaker_stuck = task.get("speaker_stuck")
        if not isinstance(speaker_stuck, bool):
            errors.append(
                f"{prefix}: answer whether the interrupted speaker is stuck before the other speaker steps in."
            )
            continue
        candidate_valid = task.get("candidate_valid")
        if not isinstance(candidate_valid, bool):
            candidate_valid = relevant_interruption is True and speaker_stuck is True
        interruption_type = task.get("interruption_type")
        if candidate_valid and speaker_stuck is True and interruption_type not in valid_types:
            errors.append(f"{prefix}: select a valid interruption type.")
        if relevant_interruption is True and speaker_stuck is False and interruption_type not in ("", None, "not_applicable"):
            errors.append(f"{prefix}: interruption type should be blank when the speaker is not stuck.")
        skip_intention_fit = speaker_stuck is True and interruption_type == "guiding_question"
        word_phrase_fits = task.get("word_phrase_fits")
        if (
            relevant_interruption is True
            and not skip_intention_fit
            and not isinstance(word_phrase_fits, bool)
            and word_phrase_fits != "unsure"
        ):
            errors.append(
                f"{prefix}: answer whether the interrupting utterance correctly fits the speaker's intention."
            )
        if task.get("transcript_checked") is not True:
            errors.append(
                f"{prefix}: confirm that you checked the transcript and removed words after interruption."
            )
        if not isinstance(task.get("interrupter_becomes_main_speaker"), bool):
            errors.append(f"{prefix}: answer whether the interrupter becomes the main speaker.")
        if candidate_valid and speaker_stuck is True and interruption_type in word_phrase_types:
            if not has_non_filler_word(task.get("corrected_interrupting_transcript")):
                errors.append(
                    f"{prefix}: word/phrase interruptions should include at least one non-filler word in the interrupting transcript."
                )
        stall_time = task.get("stall_time")
        if relevant_interruption is True:
            if not isinstance(stall_time, (int, float)):
                errors.append(f"{prefix}: mark the end timestamp of the last word before the interruption.")
            elif isinstance(duration, (int, float)) and not 0 <= stall_time <= duration:
                errors.append(
                    f"{prefix}: end timestamp of the last word before the interruption must be within the audio clip."
                )
            elif isinstance(interrupting_start_time, (int, float)) and stall_time >= interrupting_start_time:
                errors.append(
                    f"{prefix}: end timestamp of the last word must be before the start timestamp of the interrupting utterance."
                )
    return errors


def make_handler(store: VerificationStore, static_dir: Path):
    static_root = static_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "CtcVerificationHTTP/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/verify"):
                self.send_static(static_dir / "verify.html")
            elif parsed.path == "/healthz":
                self.send_json({"status": "ok", "task_count": len(store.tasks)})
            elif parsed.path == "/api/assign":
                params = parse_qs(parsed.query)
                worker, errors = validate_worker(params)
                if errors:
                    self.send_json({"status": "error", "errors": errors}, HTTPStatus.BAD_REQUEST)
                    return
                self.send_json(store.assign(worker))
            elif parsed.path == "/api/draft":
                params = parse_qs(parsed.query)
                worker, errors = validate_worker(params)
                if errors:
                    self.send_json({"status": "error", "errors": errors}, HTTPStatus.BAD_REQUEST)
                    return
                response = store.load_draft(worker)
                status = HTTPStatus.OK if response["status"] == "ok" else HTTPStatus.BAD_REQUEST
                self.send_json(response, status)
            elif parsed.path.startswith("/static/"):
                self.send_static(static_dir / parsed.path.removeprefix("/static/"))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path not in ("/api/submit", "/api/draft"):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, json.JSONDecodeError):
                self.send_json(
                    {"status": "error", "errors": ["Request body must be JSON."]},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            response = store.submit(payload) if parsed.path == "/api/submit" else store.save_draft(payload)
            status = HTTPStatus.OK if response["status"] == "ok" else HTTPStatus.BAD_REQUEST
            self.send_json(response, status)

        def send_json(self, data, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_static(self, path: Path) -> None:
            resolved = path.resolve()
            if not resolved.is_file() or (
                static_root not in resolved.parents and resolved != static_root
            ):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
            file_size = resolved.stat().st_size
            range_header = self.headers.get("Range")
            start = 0
            end = file_size - 1
            status = HTTPStatus.OK
            if range_header:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
                if not match:
                    self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    return
                start_text, end_text = match.groups()
                if start_text:
                    start = int(start_text)
                    end = int(end_text) if end_text else file_size - 1
                elif end_text:
                    suffix_length = int(end_text)
                    start = max(file_size - suffix_length, 0)
                    end = file_size - 1
                if start >= file_size or end < start:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{file_size}")
                    self.end_headers()
                    return
                end = min(end, file_size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
            content_length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(content_length))
            if status == HTTPStatus.PARTIAL_CONTENT:
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with resolved.open("rb") as handle:
                handle.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = handle.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

        def log_message(self, format: str, *args) -> None:
            print(f"{self.address_string()} - {format % args}", file=sys.stderr)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-tasks",
        action="append",
        type=Path,
        default=None,
        help="Task JSON containing playable audio URLs. Can be passed multiple times.",
    )
    parser.add_argument(
        "--auto-labels",
        action="append",
        default=None,
        help="Glob for pre-label JSONL files. Can be passed multiple times.",
    )
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).with_name("data"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--bundle-size", type=int, default=1)
    parser.add_argument("--redundancy", type=int, default=1)
    parser.add_argument(
        "--assignment-timeout-minutes",
        type=int,
        default=DEFAULT_ASSIGNMENT_TIMEOUT_MINUTES,
        help=(
            "Pending assignment claim timeout. Expired unsubmitted assignments stop "
            "counting toward redundancy; use 0 to disable."
        ),
    )
    parser.add_argument("--completion-url", default=DEFAULT_COMPLETION_URL)
    parser.add_argument(
        "--include-audio-unverified",
        action="store_true",
        help="Include pre-labelled candidates not confirmed by the audio verifier.",
    )
    parser.add_argument(
        "--include-non-ctc",
        action="store_true",
        help="Include rows pre-labelled as non-CTC. Intended for internal calibration runs.",
    )
    args = parser.parse_args()
    if args.source_tasks is None:
        args.source_tasks = [ROOT / "label_studio" / "data" / "tasks_test_predictions.json"]
    if args.auto_labels is None:
        args.auto_labels = [
            str(ROOT / "label_studio" / "data" / "high_confidence_candidates_*.jsonl")
        ]
    return args


def main() -> None:
    args = parse_args()
    store = VerificationStore(
        source_task_paths=args.source_tasks,
        auto_label_patterns=args.auto_labels,
        data_dir=args.data_dir,
        bundle_size=args.bundle_size,
        redundancy=args.redundancy,
        completion_url=args.completion_url,
        include_audio_unverified=args.include_audio_unverified,
        include_non_ctc=args.include_non_ctc,
        assignment_timeout_minutes=args.assignment_timeout_minutes,
    )
    handler = make_handler(store, Path(__file__).with_name("static"))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving interruption type annotation app at http://{args.host}:{args.port}/verify")
    print(f"Loaded {len(store.tasks)} pre-labelled candidates")
    server.serve_forever()


if __name__ == "__main__":
    main()
