#!/usr/bin/env python3
"""Package the 160 existing TC cases for blinded lab annotation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import wave


SOURCES = (
    ("batch.json", "batch-media"),
    ("heldout-34.json", "heldout-media"),
    ("test80.json", "test80-media"),
)
SEED = 20261011


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepend_spoken_context(
    pi_bench: Path, case: dict, record: dict, cropped_audio: Path, output_audio: Path
) -> float:
    """Restore the exact input timeline before question_start_s to the stereo clip."""

    question_start = float(record["payload"]["timing"]["question_start_s"])
    predictions_path = (
        pi_bench / "runs/ctc_suff_sensitivity_analysis_20260802"
        / case["model"] / "predictions.jsonl"
    )
    # The prediction audio carries the model channel on the same timeline as
    # the original user input. Read only the matching case.
    with predictions_path.open(encoding="utf-8") as handle:
        prediction = next(
            (row for row in map(json.loads, handle)
             if row["id"] == case["sample_id"]),
            None,
        )
    if prediction is None or prediction.get("status") != "ok":
        raise ValueError(f"missing model prediction: {case['key']}")
    user_path = Path(record["audio"]["input"][0]["path"])
    model_path = predictions_path.parent / prediction["output_path"]
    with wave.open(str(user_path), "rb") as user, wave.open(str(model_path), "rb") as model, wave.open(str(cropped_audio), "rb") as crop:
        rate = crop.getframerate()
        if not all(wav.getnchannels() == channels and wav.getsampwidth() == 2 and wav.getframerate() == rate
                   for wav, channels in ((user, 1), (model, 1), (crop, 2))):
            raise ValueError(f"audio format mismatch: {case['key']}")
        prefix_frames = round(question_start * rate)
        if user.getnframes() < prefix_frames or model.getnframes() < prefix_frames:
            raise ValueError(f"spoken context shorter than question start: {case['key']}")
        left = user.readframes(prefix_frames)
        right = model.readframes(prefix_frames)
        prefix = bytearray(prefix_frames * 4)
        prefix[0::4], prefix[1::4] = left[0::2], left[1::2]
        prefix[2::4], prefix[3::4] = right[0::2], right[1::2]
        with wave.open(str(output_audio), "wb") as result:
            result.setnchannels(2)
            result.setsampwidth(2)
            result.setframerate(rate)
            result.writeframes(prefix)
            result.writeframes(crop.readframes(crop.getnframes()))
    return prefix_frames / rate


def build(pi_bench: Path, output: Path, private_mapping_output: Path) -> dict:
    if output.resolve() == private_mapping_output.resolve() or output.resolve() in private_mapping_output.resolve().parents:
        raise ValueError("private mapping must be outside the upload directory")
    source = pi_bench / ".scratch/ctc-human-audit-preview"
    asr_path = pi_bench / ".scratch/ctc-human-audit-asr-35/cases-with-asr.json"
    initial_asr = {case["key"]: case for case in json.loads(asr_path.read_text(encoding="utf-8"))["cases"]}
    records = {
        record["id"]: record
        for record in json.loads((pi_bench / "dataset/ctc_suff_sensitivity_analysis_20260802.json").read_text(encoding="utf-8"))["records"]
    }
    output.mkdir(parents=True, exist_ok=True)
    audio_dir = output / "audio"
    audio_dir.mkdir(exist_ok=True)

    cases = []
    mapping = []
    seen = set()
    for manifest_name, media_dir in SOURCES:
        manifest = json.loads((source / manifest_name).read_text(encoding="utf-8"))
        for case in manifest["cases"]:
            key = case["key"]
            if key in seen:
                raise ValueError(f"duplicate case key: {key}")
            seen.add(key)
            audio_source = source / media_dir / f"{key}.wav"
            with wave.open(str(audio_source), "rb") as wav:
                if wav.getnchannels() != 2 or wav.getnframes() == 0:
                    raise ValueError(f"expected nonempty stereo WAV: {audio_source}")
                duration = wav.getnframes() / wav.getframerate()
            filler_end = float(case["filler_end_s"])
            if not 0 <= filler_end < duration:
                raise ValueError(f"invalid filler position: {key}")
            audio_target = audio_dir / f"{key}.wav"
            record = records[case["sample_id"]]
            context_mode = record["metadata"]["sensitivity_condition"]["context_mode"]
            if context_mode != case["context_mode"]:
                raise ValueError(f"context mode mismatch: {key}")
            context_text = record.get("context") or ""
            if context_mode == "text":
                if not context_text.strip():
                    raise ValueError(f"missing written context: {key}")
                question_start = 0.0
                shutil.copyfile(audio_source, audio_target)
            elif context_mode == "spoken":
                if context_text.strip():
                    raise ValueError(f"unexpected written context: {key}")
                question_start = prepend_spoken_context(pi_bench, case, record, audio_source, audio_target)
                filler_end += question_start
            else:
                raise ValueError(f"unsupported context mode: {context_mode}")

            transcript = case.get("canonical_asr_transcript")
            if not transcript and manifest_name == "batch.json" and key in initial_asr:
                segments = initial_asr[key].get("asr_segments") or []
                transcript = " ".join(str(segment["transcript"]).strip() for segment in segments)
            transcript = transcript or case["model_transcript"]
            cases.append({
                "key": key,
                "audio": f"/audio/{key}.wav",
                "filler_end_s": filler_end,
                "question_start_s": question_start,
                "context_mode": context_mode,
                "context_text": context_text,
                "user_transcript": case["user_transcript"],
                "model_transcript": transcript,
                "audio_sha256": sha256(audio_target),
            })
            mapping.append({"key": key, "cohort": manifest_name, "model": case["model"],
                            "sample_id": case["sample_id"], "context_mode": case["context_mode"]})
    if len(cases) != 160:
        raise ValueError(f"expected 160 cases, got {len(cases)}")
    random.Random(SEED).shuffle(cases)
    manifest = {"schema": "lab-ctc-agreement-160-v2", "case_count": 160, "cases": cases}
    (output / "tasks.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksums = [f"{sha256(output / 'tasks.json')}  tasks.json"]
    checksums.extend(f"{case['audio_sha256']}  audio/{case['key']}.wav" for case in sorted(cases, key=lambda item: item["key"]))
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    private_mapping_output.parent.mkdir(parents=True, exist_ok=True)
    private_mapping_output.write_text(json.dumps({"schema": "private-ctc-case-map-v1", "cases": mapping},
                                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi-bench", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-mapping-output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build(args.pi_bench, args.output, args.private_mapping_output)
    print(f"Packaged {manifest['case_count']} blinded TC cases in {args.output}")


if __name__ == "__main__":
    main()
