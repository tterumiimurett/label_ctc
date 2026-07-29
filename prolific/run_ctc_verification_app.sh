#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8002}"
SOURCE_TASKS="${SOURCE_TASKS:-label_studio/data/seamless_ctc_train_upload_checkpoint.jsonl}"
AUTO_LABELS="${AUTO_LABELS:-tables/ctc_verification_train_balanced_800.jsonl}"
DATA_DIR="${DATA_DIR:-prolific/ctc_verification_app/data}"
BUNDLE_SIZE="${BUNDLE_SIZE:-5}"
REDUNDANCY="${REDUNDANCY:-3}"
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
