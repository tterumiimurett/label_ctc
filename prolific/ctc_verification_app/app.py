#!/usr/bin/env python3
"""Prolific app for annotating pre-labelled stuck-speech interruptions."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import mimetypes
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPLETION_URL = "https://app.prolific.com/submissions/complete"
SCHEMA_VERSION = "ctc-verification-v1"
TASK_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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
        raw_tasks = json.loads(path.read_text(encoding="utf-8"))
        for task in raw_tasks:
            data = task.get("data") or {}
            audio_url = data.get("audio") or data.get("audio_url") or ""
            if not audio_url:
                continue
            task_id = Path(audio_url).stem
            task_by_id[task_id] = {
                "task_id": task_id,
                "audio_url": audio_url,
                "path_seg": data.get("path_seg", ""),
                "inner_url": data.get("inner_url", ""),
                "user": data.get("user", ""),
                "assistant": data.get("assistant", ""),
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


def default_stall_time(candidate: dict, clip_start: float | None) -> float | None:
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
        "task_id": source_task["task_id"],
        "audio_url": source_task["audio_url"],
        "clip_start": clip_start,
        "clip_end": clip_end,
        "duration": round(clip_end - clip_start, 2)
        if isinstance(clip_start, (int, float)) and isinstance(clip_end, (int, float))
        else None,
        "speakers": {
            "interrupted": candidate.get("victim_id", ""),
            "interrupting": candidate.get("interrupter_id", ""),
            "left": source_task.get("user", ""),
            "right": source_task.get("assistant", ""),
        },
        "prelabel": {
            "candidate_key": candidate_key,
            "source_file": candidate.get("_source_file", ""),
            "line_number": candidate.get("_line_number"),
            "pred_confidence": candidate.get("pred_confidence", ""),
            "pred_completion_target": candidate.get("pred_completion_target", ""),
            "pred_reasoning": candidate.get("pred_reasoning", ""),
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
        },
    }


def load_verification_tasks(
    source_task_paths: list[Path],
    auto_label_patterns: list[str],
    include_audio_unverified: bool = False,
) -> list[dict]:
    source_tasks = load_source_tasks(source_task_paths)
    tasks = []
    seen_candidate_ids: set[str] = set()
    for candidate in load_auto_candidates(auto_label_patterns):
        if candidate.get("pred_is_ctc") is not True:
            continue
        audio_verify = candidate.get("audio_verify") or {}
        if not include_audio_unverified and audio_verify.get("verify_is_ctc") is not True:
            continue
        source_task = source_tasks.get(task_id_from_candidate(candidate))
        if not source_task:
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
    ) -> None:
        self.tasks = load_verification_tasks(
            source_task_paths,
            auto_label_patterns,
            include_audio_unverified=include_audio_unverified,
        )
        self.data_dir = data_dir
        self.assignments_path = data_dir / "assignments.json"
        self.submissions_dir = data_dir / "submissions"
        self.bundle_size = bundle_size
        self.redundancy = redundancy
        self.completion_url = completion_url

    def assign(self, worker: dict[str, str]) -> dict:
        session_id = worker["session_id"]
        with TASK_LOCK:
            assignments = read_json(self.assignments_path, {})
            existing = assignments.get(session_id)
            if existing:
                if any(
                    existing.get(key) != worker.get(key)
                    for key in ("prolific_pid", "study_id")
                ):
                    return {
                        "status": "error",
                        "errors": ["SESSION_ID is already assigned to a different participant."],
                    }
                return self._assignment_response(existing, worker)

            task_counts = self._assigned_counts(assignments)
            existing_worker_candidates = {
                candidate_id
                for assignment in assignments.values()
                if assignment.get("prolific_pid") == worker["prolific_pid"]
                for candidate_id in assignment.get("candidate_ids", [])
            }
            candidates = [
                task
                for task in self.tasks
                if task_counts.get(task["candidate_id"], 0) < self.redundancy
                and task["candidate_id"] not in existing_worker_candidates
            ]
            if len(candidates) < self.bundle_size:
                candidates = [
                    task
                    for task in self.tasks
                    if task["candidate_id"] not in existing_worker_candidates
                ] or self.tasks
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

    def _assigned_counts(self, assignments: dict) -> dict[str, int]:
        counts: dict[str, int] = {}
        for assignment in assignments.values():
            for candidate_id in assignment.get("candidate_ids", []):
                counts[candidate_id] = counts.get(candidate_id, 0) + 1
        return counts

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

    def submit(self, payload: dict) -> dict:
        worker = payload.get("worker") if isinstance(payload, dict) else None
        session_id = worker.get("session_id") if isinstance(worker, dict) else ""
        if not session_id:
            return {"status": "error", "errors": validate_submission(payload)}
        with TASK_LOCK:
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
            received = {task.get("candidate_id", "") for task in payload.get("tasks", [])}
            if expected != received:
                return {
                    "status": "error",
                    "errors": ["Submitted candidate_ids do not match assigned candidate_ids."],
                }
            payload["server_metadata"] = {
                "received_at": utc_now(),
                "assignment": assignment,
            }
            atomic_write_json(self.submissions_dir / f"{safe_name(session_id)}.json", payload)
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
    valid_types = {"word_phrase_confident", "word_phrase_unsure", "guiding_question"}
    for index, task in enumerate(tasks, 1):
        prefix = f"Task {index}"
        if not isinstance(task, dict):
            errors.append(f"{prefix} must be an object.")
            continue
        if not task.get("candidate_id"):
            errors.append(f"{prefix}: missing candidate_id.")
        if not task.get("task_id"):
            errors.append(f"{prefix}: missing task_id.")
        speaker_stuck = task.get("speaker_stuck")
        if not isinstance(speaker_stuck, bool):
            errors.append(
                f"{prefix}: answer whether the interrupted speaker is stuck before the other speaker steps in."
            )
            continue
        candidate_valid = task.get("candidate_valid")
        if not isinstance(candidate_valid, bool):
            candidate_valid = speaker_stuck is True
        interruption_type = task.get("interruption_type")
        if candidate_valid and speaker_stuck is True and interruption_type not in valid_types:
            errors.append(f"{prefix}: select a valid interruption type.")
        if candidate_valid and speaker_stuck is False and interruption_type not in ("", None, "not_applicable"):
            errors.append(f"{prefix}: interruption type should be blank when the speaker is not stuck.")
        stall_time = task.get("stall_time")
        duration = task.get("duration")
        if candidate_valid and speaker_stuck is True:
            if not isinstance(stall_time, (int, float)):
                errors.append(f"{prefix}: mark the last stuck word timestamp.")
            elif isinstance(duration, (int, float)) and not 0 <= stall_time <= duration:
                errors.append(f"{prefix}: last stuck word timestamp must be within the audio clip.")
            else:
                interrupted = ((task.get("regions") or {}).get("interrupted") or {})
                interrupted_start = interrupted.get("start")
                interrupted_end = interrupted.get("end")
                tolerance = 0.01
                if isinstance(interrupted_start, (int, float)) and stall_time <= interrupted_start + tolerance:
                    errors.append(
                        f"{prefix}: last stuck word timestamp must be after the start of the interrupted utterance."
                    )
                if isinstance(interrupted_end, (int, float)) and stall_time > interrupted_end + tolerance:
                    errors.append(
                        f"{prefix}: last stuck word timestamp must be within the interrupted utterance."
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
            elif parsed.path.startswith("/static/"):
                self.send_static(static_dir / parsed.path.removeprefix("/static/"))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/submit":
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
            response = store.submit(payload)
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
            body = resolved.read_bytes()
            content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
    parser.add_argument("--completion-url", default=DEFAULT_COMPLETION_URL)
    parser.add_argument(
        "--include-audio-unverified",
        action="store_true",
        help="Include pre-labelled candidates not confirmed by the audio verifier.",
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
    )
    handler = make_handler(store, Path(__file__).with_name("static"))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving interruption type annotation app at http://{args.host}:{args.port}/verify")
    print(f"Loaded {len(store.tasks)} pre-labelled CTC candidates")
    server.serve_forever()


if __name__ == "__main__":
    main()
