#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATASET_DIR="${DATASET_DIR:?Set DATASET_DIR to the downloaded Hugging Face dataset directory}"
ANNOTATORS="${ANNOTATORS:?Set ANNOTATORS to the private annotators.json path}"
DATA_DIR="${DATA_DIR:-$ROOT_DIR/lab_conversation_agreement_data}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"

exec python "$ROOT_DIR/lab_conversation_agreement_app/app.py" \
  --dataset-dir "$DATASET_DIR" \
  --annotators "$ANNOTATORS" \
  --data-dir "$DATA_DIR" \
  --host "$HOST" \
  --port "$PORT"
