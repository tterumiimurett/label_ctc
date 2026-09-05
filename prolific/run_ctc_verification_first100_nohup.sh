#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPLETION_CODE="${COMPLETION_CODE:?Set COMPLETION_CODE to the code from your Prolific study.}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8002}"
SOURCE_TASKS="${SOURCE_TASKS:-label_studio/data/seamless_ctc_train_upload_checkpoint.jsonl}"
AUTO_LABELS="${AUTO_LABELS:-tables/ctc_verification_train_balanced_first100.jsonl}"
DATA_DIR="${DATA_DIR:-prolific/ctc_verification_app/data_train_first100_prolific}"
BUNDLE_SIZE="${BUNDLE_SIZE:-1}"
REDUNDANCY="${REDUNDANCY:-3}"
ASSIGNMENT_TIMEOUT_MINUTES="${ASSIGNMENT_TIMEOUT_MINUTES:-240}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/prolific_ctc_verification_first100.log}"
PID_FILE="${PID_FILE:-$LOG_DIR/prolific_ctc_verification_first100.pid}"

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
read -r -a python_cmd <<< "$PYTHON_BIN"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(<"$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "CTC verification first100 server is already running with PID $existing_pid." >&2
    exit 1
  fi
fi

nohup "${python_cmd[@]}" prolific/ctc_verification_app/app.py \
  --host "$HOST" \
  --port "$PORT" \
  --source-tasks "$SOURCE_TASKS" \
  --auto-labels "$AUTO_LABELS" \
  --data-dir "$DATA_DIR" \
  --bundle-size "$BUNDLE_SIZE" \
  --redundancy "$REDUNDANCY" \
  --assignment-timeout-minutes "$ASSIGNMENT_TIMEOUT_MINUTES" \
  --completion-url "https://app.prolific.com/submissions/complete?cc=$COMPLETION_CODE" \
  >"$LOG_FILE" 2>&1 &

pid="$!"
echo "$pid" >"$PID_FILE"

echo "Started CTC verification first100 server with PID $pid."
echo "Log: $LOG_FILE"
echo "Health check: curl http://$HOST:$PORT/healthz"
