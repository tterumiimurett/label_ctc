#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
TASKS="${TASKS:-label_studio/data/tasks_test_predictions.json}"
DATA_DIR="${DATA_DIR:-prolific/conversation_annotation_app/data}"
BUNDLE_SIZE="${BUNDLE_SIZE:-1}"
REDUNDANCY="${REDUNDANCY:-3}"
COMPLETION_URL="${COMPLETION_URL:-https://app.prolific.com/submissions/complete}"

exec python prolific/conversation_annotation_app/app.py \
  --host "$HOST" \
  --port "$PORT" \
  --tasks "$TASKS" \
  --data-dir "$DATA_DIR" \
  --bundle-size "$BUNDLE_SIZE" \
  --redundancy "$REDUNDANCY" \
  --completion-url "$COMPLETION_URL"
