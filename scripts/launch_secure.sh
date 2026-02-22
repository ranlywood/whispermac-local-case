#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -d "$ROOT_DIR/venv" ]]; then
  echo "venv not found. Run ./setup.sh first."
  exit 1
fi

source "$ROOT_DIR/venv/bin/activate"

export HF_HUB_DISABLE_TELEMETRY=1
export WHISPERMAC_STRICT_LOCAL="${WHISPERMAC_STRICT_LOCAL:-1}"
export WHISPERMAC_SAVE_TRANSCRIPTS="${WHISPERMAC_SAVE_TRANSCRIPTS:-0}"
export WHISPERMAC_SAVE_PERF_LOG="${WHISPERMAC_SAVE_PERF_LOG:-1}"

exec python "$ROOT_DIR/whisper_mac.py"

