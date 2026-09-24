#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8006}"
DATA_DIR="${DATA_DIR:-prolific/ctc_verification_app/data_qualification_teaching_8}"
REVIEW_URL="http://127.0.0.1:$PORT/verify?PROLIFIC_PID=teaching_reviewer&STUDY_ID=ctc_teaching_v1&SESSION_ID=ctc_teaching_v1_reviewer"

echo "Open: $REVIEW_URL"
echo "Answers: tables/expert_qualification_v1/gold_manifest.json"

exec "$PYTHON_BIN" prolific/ctc_verification_app/app.py \
  --host "$HOST" \
  --port "$PORT" \
  --auto-labels tables/expert_qualification_v1/teaching_8.jsonl \
  --data-dir "$DATA_DIR" \
  --bundle-size 8 \
  --redundancy 1 \
  --assignment-timeout-minutes 0 \
  --include-non-ctc \
  --completion-url "$REVIEW_URL"
