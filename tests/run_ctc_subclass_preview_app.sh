#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8004}"
JSONL="${JSONL:-tables/high_confidence_candidates_test_doubao_gemini_audio_check_subclass.jsonl}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

if [[ -z "${SOURCE_TASKS+x}" ]]; then
  case "$(basename "$JSONL")" in
    *"_dev_"*)
      SOURCE_TASKS="label_studio/data/tasks_dev_predictions.json"
      ;;
    *"_test_"*)
      SOURCE_TASKS="label_studio/data/tasks_test_predictions.json"
      ;;
    *)
      SOURCE_TASKS=""
      ;;
  esac
fi

APP_ARGS=(
  --host "$HOST"
  --port "$PORT"
  --jsonl "$JSONL"
)

if [[ -n "$SOURCE_TASKS" ]]; then
  APP_ARGS+=(--source-tasks "$SOURCE_TASKS")
else
  APP_ARGS+=(--no-source-tasks)
fi

exec "$PYTHON_BIN" tests/ctc_subclass_preview_app.py "${APP_ARGS[@]}"
