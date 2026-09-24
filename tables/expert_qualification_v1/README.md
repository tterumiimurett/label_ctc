# CTC expert qualification v1

This directory is a draft pending researcher review in the original annotation UI.

- `teaching_8.jsonl`: eight disclosed examples for instruction and discussion.
- `qualification_24.jsonl`: a disjoint blind qualification set.
- `gold_manifest.json`: answers and scoring metadata. Do not give this file to annotators.

The qualification set contains eight unanimous CTC anchors, eight unanimous non-CTC
anchors, four unanimous-CTC cases with disagreement on secondary fields, and four
cases that score unanimous secondary fields. Only fields named in `scorable_fields`
are valid gold labels.

Proposed gates are 80% overall CTC agreement, 100% CTC accuracy on the 16 clear
anchors, and 100% accuracy on the explicitly scored `speaker_stuck`,
`word_phrase_fits`, and `interruption_type` fields. Timing is collected but is not a
v1 pass/fail gate.

There is no unanimous-expert CTC example with `word_phrase_fits=false`. This version
therefore cannot test whether an annotator correctly rejects a semantically
non-fitting completion.

Regenerate the files with:

```bash
python3 prolific/build_expert_qualification_sets.py
```

Review the teaching set in the existing UI with:

```bash
prolific/run_ctc_qualification_teaching_8.sh
```

Review the blind test with:

```bash
prolific/run_ctc_qualification_blind_24.sh
```
