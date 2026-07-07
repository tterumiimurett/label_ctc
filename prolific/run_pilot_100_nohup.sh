#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

COMPLETION_CODE="${COMPLETION_CODE:?Set COMPLETION_CODE to the code from your Prolific study.}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
TASKS="${TASKS:-label_studio/data/tasks_pilot_100.json}"
DATA_DIR="${DATA_DIR:-prolific/conversation_annotation_app/data/pilot_100}"
LOG_DIR="${LOG_DIR:-logs}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/prolific_pilot_100.log}"
PID_FILE="${PID_FILE:-$LOG_DIR/prolific_pilot_100.pid}"

if [[ ! -f "$TASKS" ]]; then
  echo "Task file not found: $TASKS" >&2
  exit 1
fi

mkdir -p "$DATA_DIR" "$LOG_DIR"

if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(<"$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "Pilot server is already running with PID $existing_pid." >&2
    exit 1
  fi
fi

nohup uv run python prolific/conversation_annotation_app/app.py \
  --host "$HOST" \
  --port "$PORT" \
  --tasks "$TASKS" \
  --data-dir "$DATA_DIR" \
  --bundle-size 1 \
  --redundancy 1 \
  --completion-url "https://app.prolific.com/submissions/complete?cc=$COMPLETION_CODE" \
  >"$LOG_FILE" 2>&1 &

pid="$!"
echo "$pid" >"$PID_FILE"

echo "Started pilot server with PID $pid."
echo "Log: $LOG_FILE"
echo "Health check: curl http://$HOST:$PORT/healthz"
