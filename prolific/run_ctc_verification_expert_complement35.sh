#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8005}"
DATA_DIR="${DATA_DIR:-prolific/ctc_verification_app/data_expert_complement35_20260912}"
REVIEW_URL="http://127.0.0.1:$PORT/verify?PROLIFIC_PID=expert&STUDY_ID=expert_complement35_20260912&SESSION_ID=expert_complement35_20260912_v1"

echo "Open: $REVIEW_URL"
echo "Review results and drafts: $DATA_DIR"
echo "Use the same URL and data directory to resume."

exec "$PYTHON_BIN" prolific/ctc_verification_app/app.py \
  --host "$HOST" \
  --port "$PORT" \
  --auto-labels tables/ctc_verification_expert_complement35_20260912.jsonl \
  --data-dir "$DATA_DIR" \
  --bundle-size 35 \
  --redundancy 1 \
  --assignment-timeout-minutes 0 \
  --completion-url "$REVIEW_URL"
