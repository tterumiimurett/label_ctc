#!/usr/bin/env python3
"""Read-only review server for CTC verification submissions."""

from __future__ import annotations

import argparse
import json
import mimetypes
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def display_bool(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unanswered"


class VerificationReviewStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.submissions_dir = data_dir / "submissions"

    def review_data(self) -> dict:
        submission_paths = sorted(self.submissions_dir.glob("*.json"))
        items = []
        for path in submission_paths:
            payload = read_json(path)
            submitted_at = (
                (payload.get("server_metadata") or {}).get("received_at")
                or (payload.get("ui_metadata") or {}).get("submitted_at")
                or ""
            )
            worker = payload.get("worker") or {}
            assignment = payload.get("assignment") or {}
            for task_index, task in enumerate(payload.get("tasks") or [], 1):
                items.append(self._item(path, payload, task, task_index, submitted_at, worker, assignment))
        items.sort(key=lambda item: (item["submitted_at"] or "", item["task_id"], item["submission_file"]))
        return {
            "status": "ok",
            "summary": {
                "submission_files": len(submission_paths),
                "items": len(items),
                "data_dir": str(self.data_dir),
                "latest_submitted_at": max((item["submitted_at"] for item in items), default=""),
            },
            "items": items,
        }

    def _item(
        self,
        path: Path,
        payload: dict,
        task: dict,
        task_index: int,
        submitted_at: str,
        worker: dict,
        assignment: dict,
    ) -> dict:
        regions = task.get("regions") or {}
        interrupted = regions.get("interrupted") or {}
        interrupting = regions.get("interrupting") or {}
        speaker_stuck = task.get("speaker_stuck")
        return {
            "submission_file": path.name,
            "task_index": task_index,
            "schema_version": payload.get("schema_version", ""),
            "submitted_at": submitted_at,
            "submitted_rank": (parse_datetime(submitted_at) or datetime.fromtimestamp(
                path.stat().st_mtime,
                timezone.utc,
            )).isoformat(),
            "worker": worker,
            "assignment": assignment,
            "task_id": task.get("task_id", ""),
            "candidate_id": task.get("candidate_id", ""),
            "audio_url": task.get("audio_url", ""),
            "duration": task.get("duration"),
            "prelabel_candidate_key": task.get("prelabel_candidate_key", ""),
            "speaker_stuck": speaker_stuck,
            "candidate_valid": task.get("candidate_valid", speaker_stuck is True),
            "interruption_type": task.get("interruption_type", ""),
            "stall_time": task.get("stall_time"),
            "interrupter_becomes_main_speaker": task.get("interrupter_becomes_main_speaker"),
            "corrected_interrupted_transcript": task.get("corrected_interrupted_transcript", ""),
            "corrected_interrupting_transcript": task.get("corrected_interrupting_transcript", ""),
            "note": task.get("note", ""),
            "regions": {
                "interrupted": interrupted,
                "interrupting": interrupting,
            },
            "summary_label": self._summary_label(task),
        }

    def _summary_label(self, task: dict) -> str:
        if task.get("speaker_stuck") is False:
            return "Not stuck"
        if task.get("speaker_stuck") is not True:
            return "Unanswered"
        interruption_type = task.get("interruption_type") or "Unspecified type"
        return f"Stuck: {interruption_type}"


def make_handler(store: VerificationReviewStore, static_dir: Path):
    static_root = static_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "CtcVerificationReviewHTTP/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/review"):
                self.send_static(static_dir / "review.html")
            elif parsed.path == "/healthz":
                self.send_json({"status": "ok"})
            elif parsed.path == "/api/review":
                self.send_json(store.review_data())
            elif parsed.path.startswith("/static/"):
                self.send_static(static_dir / parsed.path.removeprefix("/static/"))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

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

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "prolific" / "ctc_verification_app" / "data",
        help="CTC verification runtime data directory containing submissions/.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8003)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = VerificationReviewStore(args.data_dir)
    handler = make_handler(store, Path(__file__).with_name("static"))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving CTC verification result review app at http://{args.host}:{args.port}/review")
    server.serve_forever()


if __name__ == "__main__":
    main()
