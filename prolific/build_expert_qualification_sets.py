#!/usr/bin/env python3
"""Build reviewable teaching and blind qualification sets for CTC annotators."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "tables"
ANALYSIS_CSV = (
    ROOT
    / "prolific/ctc_verification_app/data_internal_train_100/analysis/three_experts/all_candidates.csv"
)
RESEARCHER_REVIEW = (
    ROOT
    / "prolific/ctc_verification_app/data_train_first100_prolific/researcher"
    / "adjudications/majority_remaining_review/researcher_review.json"
)
OUTPUT_DIR = TABLES / "expert_qualification_v1"
EXPERTS = ("terumi", "shutong", "zhifeng")


def parse_value(value: str) -> bool | str | None:
    if value == "True":
        return True
    if value == "False":
        return False
    return value or None


def expert_values(row: dict[str, str], field: str) -> list[bool | str | None]:
    return [parse_value(row[f"{expert}_{field}"]) for expert in EXPERTS]


def unanimous_value(row: dict[str, str], field: str) -> bool | str | None:
    values = expert_values(row, field)
    return values[0] if len(set(values)) == 1 else None


def spread_select(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    """Select deterministic, evenly spaced rows from a task-id-sorted pool."""
    ordered = sorted(rows, key=lambda row: row["task_id"])
    if len(ordered) < count:
        raise ValueError(f"Need {count} rows but only found {len(ordered)}")
    indices = [round((index + 0.5) * len(ordered) / count - 0.5) for index in range(count)]
    return [ordered[index] for index in indices]


def candidate_id(candidate: dict[str, Any]) -> str:
    key = str(candidate.get("candidate_key", ""))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def load_raw_candidates(wanted_ids: set[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(TABLES.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                candidate = json.loads(line)
                current_id = candidate_id(candidate)
                if current_id in wanted_ids and current_id not in found:
                    candidate["_qualification_source_file"] = path.name
                    candidate["_qualification_source_line"] = line_number
                    found[current_id] = candidate
        if len(found) == len(wanted_ids):
            break
    missing = wanted_ids - found.keys()
    if missing:
        raise ValueError(f"Could not locate raw candidates: {sorted(missing)}")
    return found


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> None:
    with ANALYSIS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        expert_rows = list(csv.DictReader(handle))
    expert_by_id = {row["candidate_id"]: row for row in expert_rows}

    researcher = json.loads(RESEARCHER_REVIEW.read_text(encoding="utf-8"))
    researcher_by_id = {row["candidate_id"]: row for row in researcher["tasks"]}

    teaching_specs = [
        ("110a3a0f03d3826b", "clear_non_ctc", False, "研究者判定：完全错误的 CTC 误报"),
        ("e8798b5a00333287", "clear_non_ctc", False, "研究者判定：完全错误的 CTC 误报"),
        ("a2720d355324f0e4", "confusing_non_ctc", False, "研究者判定：容易犹豫，但不是 CTC"),
        ("6001a77bac141d65", "confusing_non_ctc", False, "研究者判定：容易犹豫，但不是 CTC"),
        ("444e6e7fed72d15d", "poor_quality_ctc", True, "研究者判定：是 CTC，但样本质量差"),
        ("6203b69de3fbc04d", "expert_anchor_ctc", True, "三专家一致：CTC、stuck、符合意图"),
        ("b358fe578f895ae5", "expert_anchor_non_ctc", False, "三专家一致：非 CTC"),
        ("9decb676256bd3ee", "expert_anchor_ctc_not_stuck", True, "三专家一致：CTC，但主说话人未卡壳"),
    ]
    teaching_ids = {item[0] for item in teaching_specs}

    unanimous_ctc = [
        row for row in expert_rows if unanimous_value(row, "relevant_interruption") is True
    ]
    unanimous_non_ctc = [
        row for row in expert_rows if unanimous_value(row, "relevant_interruption") is False
    ]

    ambiguous_pool = [
        row
        for row in unanimous_ctc
        if unanimous_value(row, "speaker_stuck") is None
        and row["candidate_id"] not in teaching_ids
    ]
    ambiguous = spread_select(ambiguous_pool, 4)

    stuck_false_ids = {"8905890adc7205dc", "1599c74513cf67ca"}
    secondary = [expert_by_id[current_id] for current_id in sorted(stuck_false_ids)]
    secondary_positive_pool = [
        row
        for row in unanimous_ctc
        if unanimous_value(row, "speaker_stuck") is True
        and unanimous_value(row, "word_phrase_fits") is True
        and unanimous_value(row, "interruption_type") == "word_phrase"
        and row["candidate_id"] not in teaching_ids
    ]
    secondary.extend(spread_select(secondary_positive_pool, 2))

    reserved_ids = teaching_ids | {row["candidate_id"] for row in ambiguous + secondary}
    clear_positive_pool = [
        row
        for row in unanimous_ctc
        if unanimous_value(row, "speaker_stuck") is True
        and unanimous_value(row, "word_phrase_fits") is True
        and unanimous_value(row, "interruption_type") == "word_phrase"
        and row["candidate_id"] not in reserved_ids
    ]
    clear_positive = spread_select(clear_positive_pool, 8)
    clear_negative = spread_select(
        [row for row in unanimous_non_ctc if row["candidate_id"] not in reserved_ids], 8
    )

    qualification_groups = [
        ("clear_ctc", clear_positive),
        ("clear_non_ctc", clear_negative),
        ("confusing_ctc", ambiguous),
        ("secondary_fields", secondary),
    ]
    qualification_rows = [row for _, rows in qualification_groups for row in rows]
    qualification_ids = {row["candidate_id"] for row in qualification_rows}
    if len(qualification_ids) != 24:
        raise AssertionError("Qualification set must contain 24 unique candidates")
    if qualification_ids & teaching_ids:
        raise AssertionError("Teaching and qualification sets must be disjoint")

    raw = load_raw_candidates(teaching_ids | qualification_ids)
    # Some historical source rows predate public audio URL enrichment. The expert
    # comparison CSV retains the exact URL used in the original annotation UI.
    for current_id, candidate in raw.items():
        tos_audio = candidate.get("tos_audio") or {}
        if tos_audio.get("outer_url") or tos_audio.get("inner_url"):
            continue
        expert_row = expert_by_id.get(current_id)
        if expert_row and expert_row.get("audio_url"):
            candidate["tos_audio"] = {**tos_audio, "outer_url": expert_row["audio_url"]}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(
        OUTPUT_DIR / "teaching_8.jsonl",
        [raw[current_id] for current_id, *_ in teaching_specs],
    )
    write_jsonl(
        OUTPUT_DIR / "qualification_24.jsonl",
        [raw[row["candidate_id"]] for row in qualification_rows],
    )

    teaching_manifest = []
    for current_id, category, gold_ctc, explanation in teaching_specs:
        source = researcher_by_id.get(current_id) or expert_by_id.get(current_id)
        teaching_manifest.append(
            {
                "candidate_id": current_id,
                "task_id": source["task_id"],
                "category": category,
                "gold": {"relevant_interruption": gold_ctc},
                "explanation": explanation,
            }
        )

    qualification_manifest = []
    for category, rows in qualification_groups:
        for row in rows:
            ctc = unanimous_value(row, "relevant_interruption")
            scorable_fields = ["relevant_interruption"]
            gold: dict[str, bool | str] = {"relevant_interruption": ctc}  # type: ignore[dict-item]
            if category == "secondary_fields":
                for field in ("speaker_stuck", "word_phrase_fits", "interruption_type"):
                    value = unanimous_value(row, field)
                    if value is not None:
                        gold[field] = value
                        scorable_fields.append(field)
            qualification_manifest.append(
                {
                    "candidate_id": row["candidate_id"],
                    "task_id": row["task_id"],
                    "category": category,
                    "gold": gold,
                    "scorable_fields": scorable_fields,
                    "expert_values": {
                        field: expert_values(row, field)
                        for field in (
                            "relevant_interruption",
                            "speaker_stuck",
                            "word_phrase_fits",
                            "interruption_type",
                        )
                    },
                }
            )

    manifest = {
        "schema_version": "ctc-expert-qualification-v1",
        "status": "draft_pending_researcher_review",
        "gold_authority": "unanimous labels from Terumi, Shutong, and Zhifeng",
        "teaching": teaching_manifest,
        "qualification": qualification_manifest,
        "proposed_pass_policy": {
            "ctc_agreement_minimum": 0.8,
            "clear_ctc_and_non_ctc_required": "100%",
            "secondary_scorable_fields_required": "100%",
            "confusing_ctc_errors": "count toward overall CTC agreement but are not single-item failures",
            "timing": "recorded for analysis; not a qualification gate in v1",
        },
        "known_coverage_gap": (
            "No unanimous expert CTC example has word_phrase_fits=false, so v1 does not "
            "test recognition of a semantically non-fitting completion."
        ),
    }
    (OUTPUT_DIR / "gold_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
