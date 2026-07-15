#!/usr/bin/env python3
"""Read-only human/LLM review server for CTC/PP pilot results."""

from __future__ import annotations

import argparse
import glob
import json
import mimetypes
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]


def clip_info(task_id_value: str) -> tuple[str, float | None, float | None]:
    stem = task_id_value.removesuffix(".wav")
    if stem.startswith("seamless_ctc_"):
        stem = stem.removeprefix("seamless_ctc_")
    parts = stem.split("_")
    interaction_id = "_".join(parts[:3]) if len(parts) >= 3 else stem
    if len(parts) >= 5 and parts[-2].isdigit() and parts[-1].isdigit():
        return interaction_id, int(parts[-2]) / 100.0, int(parts[-1]) / 100.0
    return interaction_id, None, None


def candidate_times(candidate: dict) -> tuple[float | None, float | None]:
    parts = str(candidate.get("candidate_key", "")).split("|")
    if len(parts) >= 5:
        try:
            return float(parts[3]), float(parts[4])
        except ValueError:
            pass
    context = candidate.get("turn_completion_context") or {}
    return context.get("candidate_dialogue_start_s"), context.get("candidate_dialogue_end_s")


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def relative_region(source: dict | None, clip_start: float | None) -> dict | None:
    if not isinstance(source, dict) or clip_start is None:
        return None
    start = source.get("start")
    end = source.get("end", source.get("stop"))
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return None
    return {
        "start": max(0, round(start - clip_start, 2)),
        "end": max(0, round(end - clip_start, 2)),
        "transcript": source.get("transcript") or source.get("utterance") or "",
    }


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


class ReviewStore:
    def __init__(self, data_dir: Path, auto_label_patterns: list[str]) -> None:
        self.data_dir = data_dir
        self.submissions_dir = data_dir / "submissions"
        self.auto_label_patterns = auto_label_patterns

    def review_data(self) -> dict:
        submissions = self._latest_submissions_by_task()
        auto_candidates = load_auto_candidates(self.auto_label_patterns)
        auto_by_interaction: dict[str, list[dict]] = {}
        for candidate in auto_candidates:
            auto_by_interaction.setdefault(candidate.get("interaction_id", ""), []).append(candidate)

        items = []
        for submission in submissions:
            task = submission["task"]
            task_id_value = task.get("task_id", "")
            _, clip_start, clip_end = clip_info(task_id_value)
            matches = self._matching_auto_candidates(task_id_value, auto_by_interaction)
            items.append(
                {
                    "task_id": task_id_value,
                    "audio_url": task.get("audio_url", ""),
                    "clip_start": clip_start,
                    "clip_end": clip_end,
                    "submission_file": submission["path"].name,
                    "submitted_at": submission["submitted_at"],
                    "duplicate_submission_count": submission["duplicate_count"],
                    "human": {
                        "worker": submission["payload"].get("worker", {}),
                        "phenomena": task.get("phenomena", []),
                        "segments": task.get("segments", []),
                    },
                    "llm_candidates": [
                        self._review_candidate_payload(candidate, clip_start)
                        for candidate in matches
                    ],
                }
            )
        return {
            "status": "ok",
            "summary": {
                "items": len(items),
                "submission_files": len(list(self.submissions_dir.glob("*.json"))),
                "auto_candidates": len(auto_candidates),
                "auto_files": sorted(
                    {Path(path).name for pattern in self.auto_label_patterns for path in glob.glob(pattern)}
                ),
            },
            "items": items,
        }

    def _latest_submissions_by_task(self) -> list[dict]:
        latest: dict[str, dict] = {}
        counts: dict[str, int] = {}
        for path in sorted(self.submissions_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            submitted_at = (
                (payload.get("ui_metadata") or {}).get("submitted_at")
                or (payload.get("server_metadata") or {}).get("received_at")
                or ""
            )
            rank = parse_datetime(submitted_at) or datetime.fromtimestamp(
                path.stat().st_mtime,
                timezone.utc,
            )
            for task in payload.get("tasks", []):
                task_id_value = task.get("task_id", "")
                counts[task_id_value] = counts.get(task_id_value, 0) + 1
                existing = latest.get(task_id_value)
                if existing is None or rank > existing["rank"]:
                    latest[task_id_value] = {
                        "rank": rank,
                        "path": path,
                        "payload": payload,
                        "task": task,
                        "submitted_at": submitted_at,
                    }
        rows = []
        for task_id_value, row in latest.items():
            row["duplicate_count"] = counts.get(task_id_value, 1)
            rows.append(row)
        rows.sort(key=lambda row: row["task"].get("task_id", ""))
        return rows

    def _matching_auto_candidates(
        self,
        task_id_value: str,
        auto_by_interaction: dict[str, list[dict]],
        tolerance: float = 0.06,
    ) -> list[dict]:
        interaction_id, clip_start, clip_end = clip_info(task_id_value)
        if clip_start is None or clip_end is None:
            return []
        matches = []
        for candidate in auto_by_interaction.get(interaction_id, []):
            candidate_start, candidate_end = candidate_times(candidate)
            if not isinstance(candidate_start, (int, float)) or not isinstance(
                candidate_end,
                (int, float),
            ):
                continue
            if (
                abs(candidate_start - clip_start) <= tolerance
                and abs(candidate_end - clip_end) <= tolerance
            ):
                matches.append(candidate)
        return matches

    def _review_candidate_payload(self, candidate: dict, clip_start: float | None) -> dict:
        return {
            "source_file": candidate.get("_source_file", ""),
            "line_number": candidate.get("_line_number"),
            "candidate_key": candidate.get("candidate_key", ""),
            "interaction_id": candidate.get("interaction_id", ""),
            "pred_is_ctc": candidate.get("pred_is_ctc"),
            "pred_confidence": candidate.get("pred_confidence", ""),
            "pred_completion_target": candidate.get("pred_completion_target", ""),
            "pred_error_type_if_not_ctc": candidate.get("pred_error_type_if_not_ctc", ""),
            "pred_reasoning": candidate.get("pred_reasoning", ""),
            "text_pred_is_ctc": candidate.get("text_pred_is_ctc"),
            "audio_verify": candidate.get("audio_verify"),
            "victim_id": candidate.get("victim_id", ""),
            "interrupter_id": candidate.get("interrupter_id", ""),
            "victim_text": candidate.get("victim_text", ""),
            "interrupter_text": candidate.get("interrupter_text", ""),
            "main_speaker_pre_interrupt_transcript": candidate.get(
                "main_speaker_pre_interrupt_transcript",
                "",
            ),
            "interrupter_post_start_utterance": candidate.get(
                "interrupter_post_start_utterance",
                "",
            ),
            "interrupter_start_time": candidate.get("interrupter_start_time"),
            "regions": {
                "interrupted": relative_region(
                    candidate.get("interrupted_segment_context"),
                    clip_start,
                ),
                "interrupting": relative_region(
                    candidate.get("interrupter_matched_dialogue_turn"),
                    clip_start,
                ),
            },
        }


def make_handler(store: ReviewStore, static_dir: Path):
    static_root = static_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "LabelReviewHTTP/0.1"

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
        default=ROOT / "prolific" / "conversation_annotation_app" / "data" / "pilot_100",
        help="Annotation runtime data directory containing submissions/.",
    )
    parser.add_argument(
        "--auto-labels",
        action="append",
        default=None,
        help="Glob for LLM auto-label JSONL files. Can be passed multiple times.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    if args.auto_labels is None:
        args.auto_labels = [
            str(ROOT / "label_studio" / "data" / "high_confidence_candidates_*.jsonl")
        ]
    return args


def main() -> None:
    args = parse_args()
    store = ReviewStore(args.data_dir, args.auto_labels)
    handler = make_handler(store, Path(__file__).with_name("static"))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving review app at http://{args.host}:{args.port}/review")
    server.serve_forever()


if __name__ == "__main__":
    main()
