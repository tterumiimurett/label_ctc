#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPLETION_CODE="${COMPLETION_CODE:?Set COMPLETION_CODE to the code from your Prolific study.}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8002}"
SOURCE_TASKS="${SOURCE_TASKS:-label_studio/data/tasks_test_predictions.json}"
AUTO_LABELS="${AUTO_LABELS:-label_studio/data/high_confidence_candidates_*.jsonl}"
DATA_DIR="${DATA_DIR:-prolific/ctc_verification_app/data}"
BUNDLE_SIZE="${BUNDLE_SIZE:-1}"
REDUNDANCY="${REDUNDANCY:-1}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/prolific_ctc_verification.log}"
PID_FILE="${PID_FILE:-$LOG_DIR/prolific_ctc_verification.pid}"

if [[ ! -f "$SOURCE_TASKS" ]]; then
  echo "Source task file not found: $SOURCE_TASKS" >&2
  exit 1
fi

shopt -s nullglob
auto_label_files=( $AUTO_LABELS )
shopt -u nullglob
if [[ "${#auto_label_files[@]}" -eq 0 ]]; then
  echo "No pre-annotation files matched AUTO_LABELS: $AUTO_LABELS" >&2
  exit 1
fi

mkdir -p "$DATA_DIR" "$LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(<"$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "CTC verification server is already running with PID $existing_pid." >&2
    exit 1
  fi
fi

nohup uv run python prolific/ctc_verification_app/app.py \
  --host "$HOST" \
  --port "$PORT" \
  --source-tasks "$SOURCE_TASKS" \
  --auto-labels "$AUTO_LABELS" \
  --data-dir "$DATA_DIR" \
  --bundle-size "$BUNDLE_SIZE" \
  --redundancy "$REDUNDANCY" \
  --completion-url "https://app.prolific.com/submissions/complete?cc=$COMPLETION_CODE" \
  >"$LOG_FILE" 2>&1 &

pid="$!"
echo "$pid" >"$PID_FILE"

echo "Started CTC verification server with PID $pid."
echo "Log: $LOG_FILE"
echo "Health check: curl http://$HOST:$PORT/healthz"
