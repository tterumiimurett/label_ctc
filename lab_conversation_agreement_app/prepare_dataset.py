#!/usr/bin/env python3
"""Build blinded 100-case Clarification and Backchannel agreement batches."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
from functools import lru_cache

import numpy as np
import soundfile as sf


SEED = 20260924
RUN_REL = Path("runs/rerun-all-task-clean")
EVAL_REL = RUN_REL / "evaluation-canonical-final-20260805-v1/outputs"
MODEL_QUOTAS = {
    "doubao_s2s": 25,
    "gpt_realtime": 25,
    "freeze_omni": 25,
    "salmonn_omni": 13,
    "salmonn_omni_before_sft": 12,
}
VARIANTS = ("with_system_prompt", "no_system_prompt")


def rows(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def prediction_path(root: Path, model: str, task: str, variant: str) -> Path:
    candidates = [
        root / RUN_REL / "canonical-goal-20260803/models" / model / task / variant / "predictions.jsonl",
        root / RUN_REL / "models" / model / task / variant / "predictions.jsonl",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"no predictions for {model}/{task}/{variant}")


def model_audio_path(predictions: Path, prediction: dict) -> Path:
    path = predictions.parent / prediction["output_path"]
    if path.is_file():
        return path
    provenance = prediction.get("metadata", {}).get("clean_provenance", {})
    fallback = provenance.get("selected_saved_artifact_check", {}).get("output_wav_path")
    if fallback and Path(fallback).is_file():
        return Path(fallback)
    raise FileNotFoundError(path)


@lru_cache(maxsize=4)
def dataset_records(path: str) -> dict[str, dict]:
    document = json.loads(Path(path).read_text())
    return {item["id"]: item for item in document["records"]}


def input_audio(root: Path, prediction: dict) -> tuple[np.ndarray, int, float]:
    provenance = prediction.get("metadata", {}).get("clean_provenance", {})
    clock = provenance.get("input_clock") or prediction.get("metadata", {}).get("input_clock") or {}
    source = Path(clock.get("source_path") or prediction["path"])
    if not clock:
        dataset_path = root / "dataset" / f"{prediction['dataset']}.json"
        record = dataset_records(str(dataset_path))[prediction["id"]]
        spec = record["audio"]["input"][0]
        clock = {
            "window_start_s": spec.get("window", {}).get("start_s", 0),
            "adapter_input_duration_s": spec.get("window", {}).get("end_s", 0) - spec.get("window", {}).get("start_s", 0),
            "channel": spec.get("channel"),
        }
    audio, rate = sf.read(source, always_2d=True, dtype="float32")
    channel = clock.get("channel")
    channel_index = 1 if channel == "right" and audio.shape[1] > 1 else 0
    start = float(clock.get("window_start_s") or 0)
    duration = float(clock.get("adapter_input_duration_s") or (len(audio) / rate))
    begin = int(start * rate)
    segment = audio[begin : begin + int(duration * rate), channel_index]
    return segment, rate, duration


def read_mono(path: Path, target_rate: int) -> np.ndarray:
    audio, rate = sf.read(path, always_2d=True, dtype="float32")
    if rate != target_rate:
        source = audio[:, 0]
        old = np.arange(len(source), dtype=np.float64)
        new = np.linspace(0, max(0, len(source) - 1), round(len(source) * target_rate / rate))
        return np.interp(new, old, source).astype(np.float32)
    return audio[:, 0]


def write_stereo(path: Path, user: np.ndarray, model: np.ndarray, rate: int, start_s: float, end_s: float) -> None:
    start = max(0, int(start_s * rate))
    end = max(start + 1, int(end_s * rate))
    stereo = np.zeros((end - start, 2), dtype=np.float32)
    for channel, source in enumerate((user, model)):
        source_end = min(len(source), end)
        if source_end > start:
            stereo[: source_end - start, channel] = source[start:source_end]
    peak = float(np.max(np.abs(stereo)))
    if peak > 1:
        stereo /= peak
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, stereo, rate, subtype="PCM_16")


def transcript(prediction: dict) -> str:
    segments = prediction.get("asr_segments") or prediction.get("raw_transcript") or []
    return " ".join(str(item.get("transcript", "")).strip() for item in segments).strip()


def select_clarification(root: Path, model: str, quota: int, rng: random.Random, output: Path) -> list[dict]:
    pool = []
    for variant in VARIANTS:
        pred_path = prediction_path(root, model, "clarification", variant)
        for prediction in rows(pred_path):
            if prediction.get("status") != "ok":
                continue
            try:
                user, rate, question_end = input_audio(root, prediction)
                model_audio = read_mono(model_audio_path(pred_path, prediction), rate)
            except (FileNotFoundError, RuntimeError, ValueError):
                continue
            if len(model_audio) <= int(question_end * rate) or np.max(np.abs(model_audio[int(question_end * rate) :])) < .005:
                continue
            pool.append((variant, prediction, user, model_audio, rate, question_end))
    rng.shuffle(pool)
    chosen = []
    variant_counts = {variant: 0 for variant in VARIANTS}
    for variant, prediction, user, model_audio, rate, question_end in pool:
        key = hashlib.sha256(f"clarification:{model}:{variant}:{prediction['id']}".encode()).hexdigest()[:16]
        start = max(0, question_end - 1.5)
        end = min(len(model_audio) / rate, question_end + 20)
        write_stereo(output / "audio" / f"{key}.wav", user, model_audio, rate, start, end)
        chosen.append({
            "key": key,
            "task_type": "clarification",
            "audio": f"/audio/{key}.wav",
            "anchor_s": round(question_end - start, 3),
            "anchor_label": "问题结束",
            "user_transcript": "",
            "model_transcript": transcript(prediction),
        })
        variant_counts[variant] += 1
        if len(chosen) == quota:
            break
    if len(chosen) != quota:
        raise RuntimeError(f"clarification {model}: selected {len(chosen)}/{quota}")
    return chosen


def select_backchannel(root: Path, model: str, quota: int, rng: random.Random, output: Path) -> list[dict]:
    pool = {True: [], False: []}
    for variant in VARIANTS:
        pred_path = prediction_path(root, model, "backchannel", variant)
        predictions = {row["id"]: row for row in rows(pred_path)}
        evaluation_path = root / EVAL_REL / model / "backchannel" / variant / "task/evaluation-results.jsonl"
        for evaluation in rows(evaluation_path):
            prediction = predictions.get(evaluation["id"])
            if not prediction or prediction.get("status") != "ok" or evaluation.get("status") != "scored":
                continue
            for utterance in evaluation.get("metadata", {}).get("utterances", []):
                start, end = utterance.get("start_sec"), utterance.get("end_sec")
                label = utterance.get("is_backchannel")
                if not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or not isinstance(label, bool):
                    continue
                pool[label].append((variant, pred_path, prediction, utterance))
    for values in pool.values():
        rng.shuffle(values)
    positive_target = (quota + 1) // 2
    candidates = pool[True][:positive_target] + pool[False][: quota - positive_target]
    rng.shuffle(candidates)
    chosen = []
    for variant, pred_path, prediction, utterance in candidates:
        try:
            user, rate, _ = input_audio(root, prediction)
            model_audio = read_mono(model_audio_path(pred_path, prediction), rate)
        except (FileNotFoundError, RuntimeError, ValueError):
            continue
        event_start, event_end = float(utterance["start_sec"]), float(utterance["end_sec"])
        clip_start, clip_end = max(0, event_start - 6), min(len(model_audio) / rate, event_end + 2)
        key = hashlib.sha256(
            f"backchannel:{model}:{variant}:{prediction['id']}:{utterance['utterance_index']}".encode()
        ).hexdigest()[:16]
        write_stereo(output / "audio" / f"{key}.wav", user, model_audio, rate, clip_start, clip_end)
        user_context = " ".join(item.get("text", "") for item in utterance.get("user_context", []))
        chosen.append({
            "key": key,
            "task_type": "backchannel",
            "audio": f"/audio/{key}.wav",
            "anchor_s": round(event_start - clip_start, 3),
            "anchor_end_s": round(event_end - clip_start, 3),
            "anchor_label": "模型候选片段",
            "user_transcript": user_context,
            "model_transcript": utterance.get("asr_text", ""),
        })
    if len(chosen) != quota:
        raise RuntimeError(f"backchannel {model}: selected {len(chosen)}/{quota}; pools={ {k: len(v) for k,v in pool.items()} }")
    return chosen


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-bench", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(SEED)
    args.output.mkdir(parents=True, exist_ok=True)
    cases = []
    for model, quota in MODEL_QUOTAS.items():
        cases.extend(select_clarification(args.pi_bench, model, quota, rng, args.output))
        cases.extend(select_backchannel(args.pi_bench, model, quota, rng, args.output))
    rng.shuffle(cases)
    manifest = {
        "schema_version": "conversation-agreement-v1",
        "seed": SEED,
        "case_counts": {"clarification": 100, "backchannel": 100},
        "cases": cases,
    }
    (args.output / "tasks.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"total": len(cases), "counts": manifest["case_counts"]}))


if __name__ == "__main__":
    main()
