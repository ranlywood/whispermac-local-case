#!/bin/bash
# Установка WhisperMac

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "=== WhisperMac — установка ==="
echo ""

# PortAudio (нужен для записи звука)
if ! brew list portaudio &>/dev/null; then
    echo "[1/4] Устанавливаю portaudio..."
    brew install portaudio
else
    echo "[1/4] portaudio уже установлен"
fi

# Виртуальное окружение
echo "[2/4] Создаю виртуальное окружение..."
python3 -m venv venv
source venv/bin/activate

# Зависимости
echo "[3/4] Устанавливаю Python-зависимости..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Предзагрузка модели (можно отключить: WHISPERMAC_PRELOAD_MODEL=0 ./setup.sh)
if [[ "${WHISPERMAC_PRELOAD_MODEL:-1}" == "1" ]]; then
    echo "[4/4] Предзагружаю модель Whisper (первый запуск может занять время)..."
    python - <<'PY'
import os
import numpy as np
import mlx_whisper

repo = os.getenv("WHISPERMAC_MODEL_REPO", "mlx-community/whisper-large-v3-mlx-4bit")
lang = os.getenv("WHISPERMAC_LANGUAGE", "ru")
print(f"  model={repo}")
dummy = np.zeros(16000, dtype=np.float32)
mlx_whisper.transcribe(dummy, path_or_hf_repo=repo, language=lang, temperature=0.0)
print("  model cache: ready")
PY
else
    echo "[4/4] Пропускаю предзагрузку модели (WHISPERMAC_PRELOAD_MODEL=0)"
fi

echo ""
echo "=== Готово! ==="
echo ""
echo "Запуск:"
echo "  cd $ROOT_DIR"
echo "  ./scripts/launch_secure.sh"
echo ""
echo "ВАЖНО — дай разрешения в Системных настройках:"
echo "  1. Конфиденциальность → Микрофон ✅"
echo "  2. Конфиденциальность → Универсальный доступ ✅"
