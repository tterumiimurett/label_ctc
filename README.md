# CTC / PP Annotation Tools

This repo contains two annotation delivery paths plus shared Label Studio data tooling.

## Repository Layout

```text
prolific/      Prolific-compatible server, worker UI, runtime data dirs, and plan docs
mturk/         MTurk HTMLQuestion/layout generator, vendored JS, and generated previews
label_studio/  Label Studio config, input task data, exports, and summary utilities
tests/         unittest coverage for both delivery paths
```

## Prolific Pilot App

The Prolific path uses one `/annotate` page, `/api/assign` task assignment, and `/api/submit` JSON saving. Start it with:

```bash
COMPLETION_URL='https://app.prolific.com/submissions/complete?cc=YOUR_CODE' \
prolific/run_annotation_app.sh
```

The script listens on `0.0.0.0:8000` by default and reads `label_studio/data/tasks_test_predictions.json`. Override settings with environment variables:

```bash
HOST=0.0.0.0 \
PORT=8000 \
TASKS=label_studio/data/tasks_dev_predictions.json \
DATA_DIR=prolific/conversation_annotation_app/data \
BUNDLE_SIZE=1 \
REDUNDANCY=3 \
COMPLETION_URL='https://app.prolific.com/submissions/complete?cc=YOUR_CODE' \
prolific/run_annotation_app.sh
```

Equivalent direct Python command:

```bash
python prolific/conversation_annotation_app/app.py \
  --host 0.0.0.0 \
  --port 8000 \
  --tasks label_studio/data/tasks_test_predictions.json \
  --bundle-size 1 \
  --completion-url 'https://app.prolific.com/submissions/complete?cc=YOUR_CODE'
```

Set the Prolific study URL to:

```text
https://your-domain.com/annotate?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

Runtime data is stored under `prolific/conversation_annotation_app/data/`: assignments in `assignments.json`, submissions in `submissions/SESSION_ID.json`.

## MTurk Asset Generation

The MTurk path generates a single-task preview, HTMLQuestion XML, Requester UI Design Layout, and JavaScript probe:

```bash
python mturk/build_mturk_audio_mvp.py label_studio/data/tasks_test_predictions.json
```

Generated files go to `mturk/generated_mvp/` by default. `mturk/vendor/` contains vendored WaveSurfer assets that are embedded into MTurk layouts so previews do not depend on CDN loading.

## Label Studio Utilities

Prepare Label Studio tasks from source CSV:

```bash
python label_studio/prepare_tasks.py \
  label_studio/data/seamless_ctc_urls_split_ch_with_transcript_test.csv \
  label_studio/data/tasks_test_predictions.json
```

Summarize an export:

```bash
python label_studio/summarize_ctc_status.py \
  'label_studio/exports/labeled/labeled_export(1).json' \
  --csv-out label_studio/results/ctc_status_summary_example.csv
```

## Local Checks

```bash
python -m unittest discover -s tests -v
python -m py_compile prolific/conversation_annotation_app/app.py
```
