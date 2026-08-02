#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8002}"
SOURCE_TASKS="${SOURCE_TASKS:-}"
AUTO_LABELS="${AUTO_LABELS:-tables/ctc_verification_internal_train_100.jsonl}"
DATA_DIR="${DATA_DIR:-prolific/ctc_verification_app/data_internal_train_100}"
BUNDLE_SIZE="${BUNDLE_SIZE:-100}"
REDUNDANCY="${REDUNDANCY:-1}"
COMPLETION_URL="${COMPLETION_URL:-http://127.0.0.1:$PORT/verify}"

cmd=(
  uv run python prolific/ctc_verification_app/app.py
  --host "$HOST"
  --port "$PORT"
  --auto-labels "$AUTO_LABELS"
  --data-dir "$DATA_DIR"
  --bundle-size "$BUNDLE_SIZE"
  --redundancy "$REDUNDANCY"
  --completion-url "$COMPLETION_URL"
)

if [[ -n "$SOURCE_TASKS" ]]; then
  cmd+=(--source-tasks "$SOURCE_TASKS")
fi

exec "${cmd[@]}"
