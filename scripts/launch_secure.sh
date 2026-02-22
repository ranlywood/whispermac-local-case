#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -d "$ROOT_DIR/venv" ]]; then
  echo "venv not found. Run ./setup.sh first."
  exit 1
fi

source "$ROOT_DIR/venv/bin/activate"

export HF_HUB_DISABLE_TELEMETRY=1
# Для первого запуска (когда модель еще не скачана) strict-local по умолчанию выключен.
# Включай явно: WHISPERMAC_STRICT_LOCAL=1 ./scripts/launch_secure.sh
export WHISPERMAC_STRICT_LOCAL="${WHISPERMAC_STRICT_LOCAL:-0}"
export WHISPERMAC_SAVE_TRANSCRIPTS="${WHISPERMAC_SAVE_TRANSCRIPTS:-0}"
export WHISPERMAC_SAVE_PERF_LOG="${WHISPERMAC_SAVE_PERF_LOG:-1}"
export WHISPERMAC_DOCK_MODE="${WHISPERMAC_DOCK_MODE:-regular}"
export WHISPERMAC_CHUNK_SEC="${WHISPERMAC_CHUNK_SEC:-5}"
export WHISPERMAC_FINAL_PASS_MIN_SEC="${WHISPERMAC_FINAL_PASS_MIN_SEC:-18}"
export WHISPERMAC_FINAL_PASS_MAX_SEC="${WHISPERMAC_FINAL_PASS_MAX_SEC:-3600}"

exec python "$ROOT_DIR/whisper_mac.py"
