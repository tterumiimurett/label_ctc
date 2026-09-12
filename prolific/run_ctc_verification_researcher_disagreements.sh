#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8006}"
REVIEW_SET="${REVIEW_SET:-all}"
case "$REVIEW_SET" in
  all) BUNDLE_SIZE=65 ;;
  unanimous) BUNDLE_SIZE=4 ;;
  *) echo "REVIEW_SET must be all or unanimous." >&2; exit 1 ;;
esac
STUDY="researcher_disagreement_${REVIEW_SET}_v1"
DATA_DIR="${DATA_DIR:-prolific/ctc_verification_app/data_researcher_disagreement_${REVIEW_SET}_v1}"
REVIEW_URL="http://127.0.0.1:$PORT/verify?PROLIFIC_PID=expert&STUDY_ID=$STUDY&SESSION_ID=$STUDY"

echo "Open: $REVIEW_URL"
echo "Candidates: $BUNDLE_SIZE"
echo "Results and drafts: $DATA_DIR"

exec "$PYTHON_BIN" prolific/ctc_verification_app/app.py \
  --host 127.0.0.1 \
  --port "$PORT" \
  --auto-labels "tables/ctc_verification_researcher_disagreement_${REVIEW_SET}.jsonl" \
  --data-dir "$DATA_DIR" \
  --bundle-size "$BUNDLE_SIZE" \
  --redundancy 1 \
  --assignment-timeout-minutes 0 \
  --completion-url "$REVIEW_URL"
