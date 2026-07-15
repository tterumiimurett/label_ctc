#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8001}"
DATA_DIR="${DATA_DIR:-prolific/conversation_annotation_app/data/pilot_100}"
AUTO_LABELS="${AUTO_LABELS:-label_studio/data/high_confidence_candidates_*.jsonl}"

uv run python prolific/review_app/app.py \
  --host "$HOST" \
  --port "$PORT" \
  --data-dir "$DATA_DIR" \
  --auto-labels "$AUTO_LABELS"
