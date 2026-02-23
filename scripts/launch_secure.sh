#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_REPO="${WHISPERMAC_MODEL_REPO:-mlx-community/whisper-large-v3-mlx-4bit}"
STRICT_LOCAL_RAW="${WHISPERMAC_STRICT_LOCAL:-auto}"

if [[ ! -d "$ROOT_DIR/venv" ]]; then
  echo "Не найден venv. Сначала запусти ./setup.sh"
  exit 1
fi

source "$ROOT_DIR/venv/bin/activate"

is_model_cached() {
  python - <<'PY'
import os
import sys
from huggingface_hub import snapshot_download

repo = os.getenv("MODEL_REPO")
try:
    snapshot_download(repo_id=repo, local_files_only=True)
    print("1")
except Exception:
    print("0")
PY
}

CACHED="0"
if [[ "$STRICT_LOCAL_RAW" == "auto" || "$STRICT_LOCAL_RAW" == "1" ]]; then
  CACHED="$(MODEL_REPO="$MODEL_REPO" is_model_cached)"
fi

if [[ "$STRICT_LOCAL_RAW" == "auto" ]]; then
  if [[ "$CACHED" == "1" ]]; then
    STRICT_LOCAL_FINAL="1"
  else
    STRICT_LOCAL_FINAL="0"
  fi
elif [[ "$STRICT_LOCAL_RAW" == "1" ]]; then
  if [[ "$CACHED" == "1" ]]; then
    STRICT_LOCAL_FINAL="1"
  else
    echo "Предупреждение: запрошен strict local, но кэш модели не найден. Для первого запуска включаю online-режим."
    STRICT_LOCAL_FINAL="0"
  fi
else
  STRICT_LOCAL_FINAL="0"
fi

echo "WhisperMac: strict_local=$STRICT_LOCAL_FINAL (запрошено: $STRICT_LOCAL_RAW)"

export HF_HUB_DISABLE_TELEMETRY=1
export WHISPERMAC_STRICT_LOCAL="$STRICT_LOCAL_FINAL"
export WHISPERMAC_SAVE_TRANSCRIPTS="${WHISPERMAC_SAVE_TRANSCRIPTS:-0}"
export WHISPERMAC_SAVE_PERF_LOG="${WHISPERMAC_SAVE_PERF_LOG:-1}"
export WHISPERMAC_DOCK_MODE="${WHISPERMAC_DOCK_MODE:-regular}"
export WHISPERMAC_CHUNK_SEC="${WHISPERMAC_CHUNK_SEC:-5}"
export WHISPERMAC_FINAL_PASS_MIN_SEC="${WHISPERMAC_FINAL_PASS_MIN_SEC:-18}"
export WHISPERMAC_FINAL_PASS_MAX_SEC="${WHISPERMAC_FINAL_PASS_MAX_SEC:-3600}"
export WHISPERMAC_USE_PNG_MIC_ICON="${WHISPERMAC_USE_PNG_MIC_ICON:-1}"
export WHISPERMAC_HOLD_KEY="${WHISPERMAC_HOLD_KEY:-right_option}"

exec python "$ROOT_DIR/whisper_mac.py"
