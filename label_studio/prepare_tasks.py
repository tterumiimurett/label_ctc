#!/usr/bin/env python3
"""Convert seamless CTC CSV rows into Label Studio audio tasks."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def _region_id(task_index: int, segment_index: int) -> str:
    return f"seg-{task_index:05d}-{segment_index:03d}"


def _channel_label(row: dict[str, str], user: str, assistant: str) -> str:
    speaker = row.get("speaker", "")
    if speaker == user:
        return "Left"
    if speaker == assistant:
        return "Right"
    return "Left"


def _audio_channel(label: str) -> int:
    return 0 if label == "Left" else 1


def convert_csv(input_csv: Path, prelabel_mode: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    task_index = 0

    with input_csv.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("outer_url"):
                if current:
                    tasks.append(current)
                task_index += 1
                current = {
                    "data": {
                        "audio": row["outer_url"],
                        "path_seg": row.get("path_seg", ""),
                        "inner_url": row.get("inner_url", ""),
                        "user": row.get("user", ""),
                        "assistant": row.get("assistant", ""),
                    },
                }
                if prelabel_mode == "predictions":
                    current["predictions"] = [
                        {
                            "model_version": "csv-start-stop-v1",
                            "score": 1.0,
                            "result": [],
                        }
                    ]
                else:
                    current["annotations"] = [
                        {
                            "result": [],
                            "was_cancelled": False,
                            "ground_truth": False,
                        }
                    ]

            if current is None:
                continue

            start = row.get("start", "").strip()
            stop = row.get("stop", "").strip()
            utterance = row.get("utterance", "").strip()
            if not start or not stop or not utterance:
                continue

            label = _channel_label(row, current["data"]["user"], current["data"]["assistant"])
            result = current[prelabel_mode][0]["result"]
            segment_index = len(result) // 2 + 1
            region_id = _region_id(task_index, segment_index)
            start_s = float(start)
            end_s = float(stop)

            result.append(
                {
                    "id": region_id,
                    "from_name": "channel",
                    "to_name": "audio_lr",
                    "type": "labels",
                    "value": {
                        "start": start_s,
                        "end": end_s,
                        "channel": _audio_channel(label),
                        "labels": [label],
                    },
                }
            )
            result.append(
                {
                    "id": region_id,
                    "from_name": "transcript",
                    "to_name": "audio_lr",
                    "type": "textarea",
                    "value": {
                        "start": start_s,
                        "end": end_s,
                        "channel": _audio_channel(label),
                        "text": [utterance],
                    },
                }
            )

    if current:
        tasks.append(current)

    return tasks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument(
        "--prelabel-mode",
        choices=("predictions", "annotations"),
        default="predictions",
        help="Use predictions for standard pre-annotations, or annotations for direct MVP editing.",
    )
    args = parser.parse_args()

    tasks = convert_csv(args.input_csv, args.prelabel_mode)
    args.output_json.write_text(
        json.dumps(tasks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(tasks)} Label Studio tasks to {args.output_json}")


if __name__ == "__main__":
    main()
