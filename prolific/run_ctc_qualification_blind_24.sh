#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8007}"
DATA_DIR="${DATA_DIR:-prolific/ctc_verification_app/data_qualification_blind_24}"
REVIEW_URL="http://127.0.0.1:$PORT/verify?PROLIFIC_PID=qualification_reviewer&STUDY_ID=ctc_qualification_v1&SESSION_ID=ctc_qualification_v1_reviewer"

echo "Open: $REVIEW_URL"
echo "Results: $DATA_DIR/submissions"

exec "$PYTHON_BIN" prolific/ctc_verification_app/app.py \
  --host "$HOST" \
  --port "$PORT" \
  --auto-labels tables/expert_qualification_v1/qualification_24.jsonl \
  --data-dir "$DATA_DIR" \
  --bundle-size 24 \
  --redundancy 1 \
  --assignment-timeout-minutes 0 \
  --include-non-ctc \
  --completion-url "$REVIEW_URL"
