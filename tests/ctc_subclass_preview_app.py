#!/usr/bin/env python3
"""Read-only local preview server for CTC subclass JSONL output."""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
from collections import Counter, defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSONL = (
    ROOT
    / "tables"
    / "high_confidence_candidates_test_doubao_gemini_audio_check_subclass.jsonl"
)
DEFAULT_SOURCE_TASKS = ROOT / "label_studio" / "data" / "tasks_test_predictions.json"
STATIC_DIR = Path(__file__).with_name("ctc_subclass_preview_static")
VENDOR_DIR = ROOT / "mturk" / "vendor"
AUDIO_STEM_RE = re.compile(
    r"seamless_ctc_(V\d+_S\d+_I\d+)_(\d+)_(\d+)"
)

CATEGORY_LABELS = {
    "stuck_word": "Stuck word",
    "stuck_guide": "Stuck guide",
    "not_stuck": "Not stuck",
    "not_ctc": "Not CTC",
    "unclassified": "Unclassified",
}


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {error}") from error
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            row["_preview_line_number"] = line_number
            rows.append(row)
    if not rows:
        raise ValueError(f"No JSONL rows found in {path}")
    return rows


def candidate_window(candidate: dict) -> tuple[str, float | None, float | None]:
    parts = str(candidate.get("candidate_key", "")).split("|")
    interaction_id = str(candidate.get("interaction_id") or (parts[0] if parts else ""))
    if len(parts) >= 5:
        try:
            return interaction_id, float(parts[3]), float(parts[4])
        except ValueError:
            pass
    context = candidate.get("turn_completion_context") or {}
    return (
        interaction_id,
        context.get("candidate_dialogue_start_s"),
        context.get("candidate_dialogue_end_s"),
    )


def load_source_task_index(path: Path) -> dict[str, list[dict]]:
    tasks = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        raise ValueError(f"{path}: expected a JSON list")

    by_interaction: dict[str, list[dict]] = defaultdict(list)
    for task in tasks:
        data = task.get("data") or {}
        audio_url = str(data.get("audio") or data.get("audio_url") or "")
        audio_stem = Path(urlparse(audio_url).path).stem
        match = AUDIO_STEM_RE.fullmatch(audio_stem)
        if not audio_url or not match:
            continue
        by_interaction[match.group(1)].append(
            {
                "task_id": audio_stem,
                "audio_url": audio_url,
                "clip_start_centiseconds": int(match.group(2)),
                "clip_end_centiseconds": int(match.group(3)),
                "left_speaker": str(data.get("user") or ""),
                "right_speaker": str(data.get("assistant") or ""),
                "path_seg": str(data.get("path_seg") or ""),
            }
        )
    return dict(by_interaction)


def match_source_task(
    candidate: dict,
    source_task_index: dict[str, list[dict]],
    tolerance_centiseconds: float = 1.01,
) -> dict | None:
    interaction_id, clip_start, clip_end = candidate_window(candidate)
    if not isinstance(clip_start, (int, float)) or not isinstance(clip_end, (int, float)):
        return None
    choices = source_task_index.get(interaction_id) or []
    if not choices:
        return None
    start_centiseconds = clip_start * 100
    end_centiseconds = clip_end * 100
    best = min(
        choices,
        key=lambda task: (
            abs(task["clip_start_centiseconds"] - start_centiseconds)
            + abs(task["clip_end_centiseconds"] - end_centiseconds)
        ),
    )
    start_delta = abs(best["clip_start_centiseconds"] - start_centiseconds)
    end_delta = abs(best["clip_end_centiseconds"] - end_centiseconds)
    if start_delta > tolerance_centiseconds or end_delta > tolerance_centiseconds:
        return None
    return {
        **best,
        "match_start_delta_centiseconds": round(start_delta, 3),
        "match_end_delta_centiseconds": round(end_delta, 3),
    }


def normalize_category(candidate: dict) -> str:
    subclass = str(candidate.get("subclass") or "").strip().lower().replace("_", " ")
    llm_kind = str(candidate.get("subclass_llm_kind") or "").strip().lower()
    if subclass == "stuck word" or (
        candidate.get("subclass_is_stuck") is True and llm_kind == "word"
    ):
        return "stuck_word"
    if subclass in {"stuck guide", "stuck guidance", "guiding question"} or (
        candidate.get("subclass_is_stuck") is True
        and llm_kind in {"guide", "guidance", "guiding_question"}
    ):
        return "stuck_guide"
    if subclass in {"unstuck", "not stuck"} or candidate.get("subclass_is_stuck") is False:
        return "not_stuck"
    if candidate.get("pred_is_ctc") is False:
        return "not_ctc"
    return "unclassified"


def relative_time(value, clip_start: float | None) -> float | None:
    if not isinstance(value, (int, float)) or not isinstance(clip_start, (int, float)):
        return None
    return round(value - clip_start, 3)


def timeline_region(source, clip_start: float | None) -> dict | None:
    if not isinstance(source, dict):
        return None
    start = source.get("start")
    end = source.get("end", source.get("stop"))
    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        return None
    return {
        "absolute_start": start,
        "absolute_end": end,
        "relative_start": relative_time(start, clip_start),
        "relative_end": relative_time(end, clip_start),
        "text": str(
            source.get("word")
            or source.get("transcript")
            or source.get("utterance")
            or ""
        ),
        "score": source.get("score"),
    }


def preview_item(candidate: dict, source_task: dict | None) -> dict:
    interaction_id, clip_start, clip_end = candidate_window(candidate)
    category = normalize_category(candidate)
    main_last_word = timeline_region(
        candidate.get("main_speaker_last_word_before_interruption"),
        clip_start,
    )
    interrupter_first_word = timeline_region(
        candidate.get("interrupter_first_word"),
        clip_start,
    )
    interrupted_region = timeline_region(
        candidate.get("interrupted_segment_context"),
        clip_start,
    )
    interrupting_region = timeline_region(
        candidate.get("interrupter_matched_dialogue_turn"),
        clip_start,
    )

    dialogue = []
    for turn in candidate.get("dialogue") or []:
        if not isinstance(turn, dict):
            continue
        dialogue.append(
            {
                "speaker": str(turn.get("speaker") or ""),
                "absolute_start": turn.get("start"),
                "absolute_end": turn.get("stop", turn.get("end")),
                "relative_start": relative_time(turn.get("start"), clip_start),
                "relative_end": relative_time(
                    turn.get("stop", turn.get("end")),
                    clip_start,
                ),
                "utterance": str(turn.get("utterance") or ""),
            }
        )

    raw = dict(candidate)
    raw.pop("_preview_line_number", None)
    return {
        "line_number": candidate["_preview_line_number"],
        "interaction_id": interaction_id,
        "candidate_key": str(candidate.get("candidate_key") or ""),
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "pred_is_ctc": candidate.get("pred_is_ctc"),
        "audio_url": source_task.get("audio_url", "") if source_task else "",
        "audio_match": source_task,
        "clip": {
            "absolute_start": clip_start,
            "absolute_end": clip_end,
            "duration": round(clip_end - clip_start, 3)
            if isinstance(clip_start, (int, float))
            and isinstance(clip_end, (int, float))
            else None,
        },
        "speakers": {
            "main": str(candidate.get("victim_id") or ""),
            "interrupter": str(candidate.get("interrupter_id") or ""),
            "left": source_task.get("left_speaker", "") if source_task else "",
            "right": source_task.get("right_speaker", "") if source_task else "",
        },
        "classification": {
            "subclass": candidate.get("subclass"),
            "subclass_status": candidate.get("subclass_status"),
            "subclass_is_stuck": candidate.get("subclass_is_stuck"),
            "threshold_ms": candidate.get("subclass_threshold_ms"),
            "gap_seconds": candidate.get("subclass_gap_seconds"),
            "gap_ms": candidate.get("subclass_gap_ms"),
            "llm_kind": candidate.get("subclass_llm_kind"),
            "llm_confidence": candidate.get("subclass_llm_confidence"),
            "llm_reasoning": candidate.get("subclass_llm_reasoning"),
            "llm_backend": candidate.get("subclass_llm_backend"),
            "llm_model": candidate.get("subclass_llm_model"),
            "error": candidate.get("subclass_error"),
            "error_message": candidate.get("subclass_error_message"),
        },
        "timeline": {
            "main_last_word": main_last_word,
            "main_last_word_end_absolute": candidate.get(
                "main_speaker_last_word_end_time"
            ),
            "main_last_word_end_relative": relative_time(
                candidate.get("main_speaker_last_word_end_time"),
                clip_start,
            ),
            "interrupter_first_word": interrupter_first_word,
            "interrupter_first_word_start_absolute": candidate.get(
                "interrupter_first_word_start_time"
            ),
            "interrupter_first_word_start_relative": relative_time(
                candidate.get("interrupter_first_word_start_time"),
                clip_start,
            ),
            "interrupter_start_absolute": candidate.get("interrupter_start_time"),
            "interrupter_start_relative": relative_time(
                candidate.get("interrupter_start_time"),
                clip_start,
            ),
            "interrupted_region": interrupted_region,
            "interrupting_region": interrupting_region,
        },
        "context": {
            "main_before_interrupt": str(
                candidate.get("main_speaker_pre_interrupt_transcript") or ""
            ),
            "interrupter_after_start": str(
                candidate.get("interrupter_post_start_utterance") or ""
            ),
            "pred_completion_target": str(candidate.get("pred_completion_target") or ""),
            "pred_reasoning": str(candidate.get("pred_reasoning") or ""),
            "audio_evidence": str(
                (candidate.get("audio_verify") or {}).get("verify_audio_evidence") or ""
            ),
            "text_evidence": str(
                (candidate.get("audio_verify") or {}).get("verify_text_evidence") or ""
            ),
            "dialogue": dialogue,
        },
        "raw": raw,
    }


class SubclassPreviewStore:
    def __init__(
        self,
        jsonl_path: Path,
        source_tasks_path: Path | None,
    ) -> None:
        self.jsonl_path = jsonl_path
        self.source_tasks_path = source_tasks_path
        source_task_index = (
            load_source_task_index(source_tasks_path) if source_tasks_path else {}
        )
        self.items = []
        for candidate in read_jsonl(jsonl_path):
            source_task = match_source_task(candidate, source_task_index)
            self.items.append(preview_item(candidate, source_task))

    def preview_data(self) -> dict:
        counts = Counter(item["category"] for item in self.items)
        return {
            "status": "ok",
            "summary": {
                "rows": len(self.items),
                "subclassed_ctc_rows": sum(
                    counts[key]
                    for key in ("stuck_word", "stuck_guide", "not_stuck")
                ),
                "audio_matched": sum(bool(item["audio_url"]) for item in self.items),
                "jsonl_path": str(self.jsonl_path),
                "source_tasks_path": (
                    str(self.source_tasks_path) if self.source_tasks_path else None
                ),
                "category_counts": {
                    key: counts.get(key, 0) for key in CATEGORY_LABELS
                },
            },
            "items": self.items,
        }


def make_handler(store: SubclassPreviewStore):
    static_root = STATIC_DIR.resolve()
    vendor_root = VENDOR_DIR.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "CtcSubclassPreviewHTTP/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/preview"):
                self.send_static(STATIC_DIR / "preview.html", static_root)
            elif parsed.path == "/healthz":
                summary = store.preview_data()["summary"]
                self.send_json({"status": "ok", "summary": summary})
            elif parsed.path == "/api/preview":
                self.send_json(store.preview_data())
            elif parsed.path.startswith("/static/"):
                self.send_static(
                    STATIC_DIR / parsed.path.removeprefix("/static/"),
                    static_root,
                )
            elif parsed.path.startswith("/vendor/"):
                self.send_static(
                    VENDOR_DIR / parsed.path.removeprefix("/vendor/"),
                    vendor_root,
                )
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def send_json(self, data, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_static(self, path: Path, allowed_root: Path) -> None:
            resolved = path.resolve()
            if not resolved.is_file() or (
                allowed_root not in resolved.parents and resolved != allowed_root
            ):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = resolved.read_bytes()
            content_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--source-tasks", type=Path, default=DEFAULT_SOURCE_TASKS)
    parser.add_argument(
        "--no-source-tasks",
        action="store_true",
        help="Load JSONL metadata without attempting to match playable audio.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8004)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_tasks_path = None if args.no_source_tasks else args.source_tasks.resolve()
    store = SubclassPreviewStore(args.jsonl.resolve(), source_tasks_path)
    summary = store.preview_data()["summary"]
    handler = make_handler(store)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(
        "Loaded "
        f"{summary['rows']} rows "
        f"({summary['subclassed_ctc_rows']} subclassed CTC rows, "
        f"{summary['audio_matched']} audio matches)."
    )
    print(f"Serving CTC subclass preview at http://{args.host}:{args.port}/preview")
    server.serve_forever()


if __name__ == "__main__":
    main()
