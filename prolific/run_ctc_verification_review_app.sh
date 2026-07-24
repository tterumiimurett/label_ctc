#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8003}"
DATA_DIR="${DATA_DIR:-prolific/ctc_verification_app/data}"

uv run python prolific/ctc_verification_review_app/app.py \
  --host "$HOST" \
  --port "$PORT" \
  --data-dir "$DATA_DIR"
