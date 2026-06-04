#!/usr/bin/env python3
"""Summarize file-level CTC labels from a Label Studio JSON export."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def _latest_annotation(task: dict[str, Any]) -> dict[str, Any] | None:
    annotations = [ann for ann in task.get("annotations", []) if not ann.get("was_cancelled")]
    if not annotations:
        return None
    return max(annotations, key=lambda ann: ann.get("updated_at") or ann.get("created_at") or "")


def _ctc_status(annotation: dict[str, Any] | None) -> str:
    if not annotation:
        return "not_labeled"
    for result in annotation.get("result", []):
        if result.get("from_name") != "ctc_status":
            continue
        choices = result.get("value", {}).get("choices") or []
        return choices[0] if choices else "not_labeled"
    return "not_labeled"


def summarize(export_json: Path) -> tuple[Counter[str], dict[str, list[dict[str, str]]]]:
    tasks = json.loads(export_json.read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    rows_by_status: dict[str, list[dict[str, str]]] = defaultdict(list)

    for task in tasks:
        annotation = _latest_annotation(task)
        status = _ctc_status(annotation)
        counts[status] += 1
        rows_by_status[status].append(
            {
                "task_id": str(task.get("id", "")),
                "completed_by": str((annotation or {}).get("completed_by", "")),
                "updated_at": str((annotation or {}).get("updated_at", "")),
                "audio": str(task.get("data", {}).get("audio", "")),
                "path_seg": str(task.get("data", {}).get("path_seg", "")),
            }
        )

    return counts, rows_by_status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("export_json", type=Path)
    parser.add_argument("--csv-out", type=Path, help="Optional path for per-task CSV output.")
    args = parser.parse_args()

    counts, rows_by_status = summarize(args.export_json)
    total = sum(counts.values())
    print(f"total: {total}")
    for status in ("is_CTC", "not_CTC", "not_labeled"):
        print(f"{status}: {counts[status]}")

    if args.csv_out:
        with args.csv_out.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["ctc_status", "task_id", "completed_by", "updated_at", "audio", "path_seg"],
            )
            writer.writeheader()
            for status, rows in sorted(rows_by_status.items()):
                for row in rows:
                    writer.writerow({"ctc_status": status, **row})
        print(f"wrote: {args.csv_out}")


if __name__ == "__main__":
    main()
