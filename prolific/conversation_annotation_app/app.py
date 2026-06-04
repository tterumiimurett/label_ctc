#!/usr/bin/env python3
"""Minimal Prolific-compatible CTC/PP annotation server.

This intentionally uses only the Python standard library so a freshly pulled
repo can run a pilot without installing a web framework.
"""

from __future__ import annotations

import argparse
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mturk.build_mturk_audio_mvp import build_payload  # noqa: E402


DEFAULT_COMPLETION_URL = "https://app.prolific.com/submissions/complete"
SCHEMA_VERSION = "conversation-annotation-v2"
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
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def dataset_name(input_path: Path) -> str:
    stem = input_path.stem.lower()
    if "_test_" in stem:
        return "test"
    if "_dev_" in stem:
        return "dev"
    return input_path.stem


def task_id(payload: dict) -> str:
    audio_name = Path(payload["source"]["audio"]).stem
    if audio_name:
        return audio_name
    return f"{payload['source']['dataset']}_task_{payload['source']['task_index']:05d}"


def conversation_payload(task: dict, dataset: str, task_index: int) -> dict:
    payload = build_payload(task, dataset, task_index)
    source = payload["source"]
    source["task_id"] = task_id(payload)
    payload["schema_version"] = SCHEMA_VERSION
    payload["task"] = {
        "task_id": source["task_id"],
        "dataset": source["dataset"],
        "task_index": source["task_index"],
        "audio_url": source["audio"],
        "path_seg": source.get("path_seg", ""),
    }
    payload["choices"]["audio_quality"] = ["usable", "noisy_but_usable", "unusable"]
    payload["choices"]["transcript_quality"] = [
        "good",
        "needs_minor_correction",
        "needs_major_correction",
    ]
    return payload


def load_tasks(tasks_path: Path) -> list[dict]:
    raw_tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError(f"No tasks found in {tasks_path}")
    dataset = dataset_name(tasks_path)
    return [
        conversation_payload(task, dataset, index)
        for index, task in enumerate(raw_tasks)
    ]


class AnnotationStore:
    def __init__(
        self,
        tasks_path: Path,
        data_dir: Path,
        bundle_size: int,
        redundancy: int,
        completion_url: str,
    ) -> None:
        self.tasks = load_tasks(tasks_path)
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
                return self._assignment_response(existing, worker)

            task_counts = self._assigned_counts(assignments)
            existing_worker_tasks = {
                task_id
                for assignment in assignments.values()
                if assignment.get("prolific_pid") == worker["prolific_pid"]
                for task_id in assignment.get("task_ids", [])
            }
            candidates = [
                task
                for task in self.tasks
                if task_counts.get(task["task"]["task_id"], 0) < self.redundancy
                and task["task"]["task_id"] not in existing_worker_tasks
            ]
            if len(candidates) < self.bundle_size:
                candidates = [
                    task
                    for task in self.tasks
                    if task["task"]["task_id"] not in existing_worker_tasks
                ] or self.tasks
            candidates.sort(
                key=lambda task: (
                    task_counts.get(task["task"]["task_id"], 0),
                    task["task"]["task_index"],
                )
            )
            chosen = candidates[: self.bundle_size]
            assignment = {
                "bundle_id": f"bundle_{len(assignments):05d}",
                "session_id": session_id,
                "prolific_pid": worker["prolific_pid"],
                "study_id": worker["study_id"],
                "task_ids": [task["task"]["task_id"] for task in chosen],
                "assigned_at": utc_now(),
                "submitted": False,
            }
            assignments[session_id] = assignment
            atomic_write_json(self.assignments_path, assignments)
            return self._assignment_response(assignment, worker)

    def _assigned_counts(self, assignments: dict) -> dict[str, int]:
        counts: dict[str, int] = {}
        for assignment in assignments.values():
            for assigned_task_id in assignment.get("task_ids", []):
                counts[assigned_task_id] = counts.get(assigned_task_id, 0) + 1
        return counts

    def _assignment_response(self, assignment: dict, worker: dict[str, str]) -> dict:
        task_by_id = {task["task"]["task_id"]: task for task in self.tasks}
        assigned_tasks = [task_by_id[task_id] for task_id in assignment["task_ids"]]
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
        errors = validate_submission(payload)
        if errors:
            return {"status": "error", "errors": errors}
        worker = payload["worker"]
        session_id = worker["session_id"]
        with TASK_LOCK:
            assignments = read_json(self.assignments_path, {})
            assignment = assignments.get(session_id)
            if not assignment:
                return {"status": "error", "errors": ["No assignment exists for this SESSION_ID."]}
            expected = set(assignment.get("task_ids", []))
            received = {task.get("task_id", "") for task in payload.get("tasks", [])}
            if expected != received:
                return {
                    "status": "error",
                    "errors": ["Submitted task_ids do not match assigned task_ids."],
                }
            payload["server_metadata"] = {
                "received_at": utc_now(),
                "assignment": assignment,
            }
            output_path = self.submissions_dir / f"{safe_name(session_id)}.json"
            atomic_write_json(output_path, payload)
            assignment["submitted"] = True
            assignment["submitted_at"] = payload["server_metadata"]["received_at"]
            assignments[session_id] = assignment
            atomic_write_json(self.assignments_path, assignments)
        return {"status": "ok", "completion_url": self.completion_url}


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


def validate_submission(payload: dict) -> list[str]:
    errors: list[str] = []
    worker = payload.get("worker") or {}
    for key in ("prolific_pid", "study_id", "session_id"):
        if not worker.get(key):
            errors.append(f"Missing worker.{key}.")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("Submission must include at least one task.")
        return errors
    for task_index, task in enumerate(tasks, 1):
        if not task.get("task_id"):
            errors.append(f"Task {task_index} is missing task_id.")
        file_level = task.get("file_level") or {}
        if not file_level.get("target_status"):
            errors.append(f"Task {task_index} needs at least one file-level target_status.")
        if not file_level.get("audio_quality"):
            errors.append(f"Task {task_index} needs audio_quality.")
        if not file_level.get("transcript_quality"):
            errors.append(f"Task {task_index} needs transcript_quality.")
        segments = task.get("segments") or []
        if not segments:
            errors.append(f"Task {task_index} needs at least one timestamp segment.")
        for segment_index, segment in enumerate(segments, 1):
            start = segment.get("start")
            end = segment.get("end")
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                errors.append(f"Task {task_index} segment {segment_index} needs numeric times.")
            elif end <= start:
                errors.append(f"Task {task_index} segment {segment_index} must have start < end.")
            if not str(segment.get("transcript", "")).strip():
                errors.append(f"Task {task_index} segment {segment_index} needs transcript.")
    return errors


def first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key) or [""]
    return values[0].strip()


def safe_name(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "_" for character in value)


def make_handler(store: AnnotationStore, static_dir: Path):
    class Handler(BaseHTTPRequestHandler):
        server_version = "ConversationAnnotationHTTP/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/annotate"):
                self.send_static(static_dir / "annotate.html")
            elif parsed.path == "/healthz":
                self.send_json({"status": "ok", "task_count": len(store.tasks)})
            elif parsed.path.startswith("/static/"):
                self.send_static(static_dir / parsed.path.removeprefix("/static/"))
            elif parsed.path == "/api/assign":
                params = parse_qs(parsed.query)
                worker, errors = validate_worker(params)
                if errors:
                    self.send_json({"status": "error", "errors": errors}, HTTPStatus.BAD_REQUEST)
                    return
                self.send_json(store.assign(worker))
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
            if not path.is_file() or static_dir not in path.resolve().parents and path.resolve() != static_dir:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
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
        "--tasks",
        type=Path,
        default=ROOT / "label_studio" / "data" / "tasks_test_predictions.json",
        help="Label Studio task JSON with predictions/annotations.",
    )
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).with_name("data"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--bundle-size",
        type=int,
        default=1,
        help="Number of audio tasks assigned to one Prolific session.",
    )
    parser.add_argument("--redundancy", type=int, default=3)
    parser.add_argument("--completion-url", default=DEFAULT_COMPLETION_URL)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = AnnotationStore(
        tasks_path=args.tasks,
        data_dir=args.data_dir,
        bundle_size=args.bundle_size,
        redundancy=args.redundancy,
        completion_url=args.completion_url,
    )
    handler = make_handler(store, Path(__file__).with_name("static"))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving annotation app at http://{args.host}:{args.port}/annotate")
    print(f"Loaded {len(store.tasks)} tasks from {args.tasks}")
    server.serve_forever()


if __name__ == "__main__":
    main()
