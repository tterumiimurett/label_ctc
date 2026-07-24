#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8002}"
SOURCE_TASKS="${SOURCE_TASKS:-label_studio/data/tasks_test_predictions.json}"
AUTO_LABELS="${AUTO_LABELS:-label_studio/data/high_confidence_candidates_*.jsonl}"
DATA_DIR="${DATA_DIR:-prolific/ctc_verification_app/data}"
BUNDLE_SIZE="${BUNDLE_SIZE:-1}"
REDUNDANCY="${REDUNDANCY:-1}"
COMPLETION_URL="${COMPLETION_URL:-https://app.prolific.com/submissions/complete}"

exec uv run python prolific/ctc_verification_app/app.py \
  --host "$HOST" \
  --port "$PORT" \
  --source-tasks "$SOURCE_TASKS" \
  --auto-labels "$AUTO_LABELS" \
  --data-dir "$DATA_DIR" \
  --bundle-size "$BUNDLE_SIZE" \
  --redundancy "$REDUNDANCY" \
  --completion-url "$COMPLETION_URL"
