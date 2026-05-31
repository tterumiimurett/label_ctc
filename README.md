# CTC / PP Annotation Tools

This repo contains two related annotation paths:

- `build_mturk_audio_mvp.py` generates the existing single-task MTurk-style HTML preview.
- `conversation_annotation_app/app.py` runs a Prolific-compatible pilot server with one `/annotate` page, `/api/assign` task assignment, and `/api/submit` JSON saving.

## Run The Prolific Pilot App

The pilot app uses only the Python standard library plus the existing repo code.
After `git pull` on a server, start it with:

```bash
COMPLETION_URL='https://app.prolific.com/submissions/complete?cc=YOUR_CODE' \
scripts/run_annotation_app.sh
```

The script listens on `0.0.0.0:8000` by default and reads `label_studio_tasks_test_predictions.json`.
Override settings with environment variables:

```bash
HOST=0.0.0.0 \
PORT=8000 \
TASKS=label_studio_tasks_dev_predictions.json \
DATA_DIR=conversation_annotation_app/data \
BUNDLE_SIZE=1 \
REDUNDANCY=3 \
COMPLETION_URL='https://app.prolific.com/submissions/complete?cc=YOUR_CODE' \
scripts/run_annotation_app.sh
```

Equivalent direct Python command:

```bash
python conversation_annotation_app/app.py \
  --host 0.0.0.0 \
  --port 8000 \
  --tasks label_studio_tasks_test_predictions.json \
  --bundle-size 1 \
  --completion-url 'https://app.prolific.com/submissions/complete?cc=YOUR_CODE'
```

Open the annotation page with Prolific URL parameters:

```text
http://127.0.0.1:8000/annotate?PROLIFIC_PID=PILOT_PID&STUDY_ID=PILOT_STUDY&SESSION_ID=PILOT_SESSION
```

For Prolific, set the study URL to:

```text
https://your-domain.com/annotate?PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}
```

Do not send workers to `/api/assign` directly. `/api/assign` is the JSON endpoint that the browser page calls after `/annotate` loads.

## How Prolific Fits In

Prolific handles recruitment, payment, and completion tracking. This app handles task assignment, the annotation UI, and JSON storage.

The integration has two edges:

- Entry: Prolific sends workers to `/annotate` with `PROLIFIC_PID`, `STUDY_ID`, and `SESSION_ID`.
- Exit: after `/api/submit` saves the JSON successfully, the browser redirects to `COMPLETION_URL`.

Worker flow:

1. A worker clicks the Prolific study link.
2. Prolific opens `/annotate?...` with real participant/session IDs.
3. The page calls `/api/assign` and receives one audio task by default.
4. The worker labels the file-level CTC/PP status and edits the relevant timestamped segments.
5. The page posts the annotation JSON to `/api/submit`.
6. The server writes `conversation_annotation_app/data/submissions/SESSION_ID.json`.
7. The browser redirects to the Prolific completion URL only after the save succeeds.

URL roles:

```text
/annotate    Worker-facing annotation page
/api/assign  Internal JSON task-assignment endpoint
/api/submit  Internal JSON submission endpoint
/healthz     Server health check
```

## Saved Data

Assignments are stored in:

```text
conversation_annotation_app/data/assignments.json
```

Submissions are stored as one JSON file per Prolific session:

```text
conversation_annotation_app/data/submissions/SESSION_ID.json
```

`--bundle-size 1` assigns one audio task per Prolific session. Increase it later for a multi-task pilot; if you do, every task in the bundle must have its own file-level label before submit.

Each submission uses `conversation-annotation-v2` and includes:

- `worker`: `PROLIFIC_PID`, `STUDY_ID`, `SESSION_ID`
- `assignment`: bundle metadata
- `tasks`: file-level CTC/PP labels, timestamped segments, transcripts, and UI metadata

## Local Checks

```bash
python -m unittest -v
python -m py_compile conversation_annotation_app/app.py
```
