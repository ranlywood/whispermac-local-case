#!/usr/bin/env bash
# Установка WhisperMac

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

PY_FORMULA="${WHISPERMAC_PY_FORMULA:-python@3.12}"
TK_FORMULA="${WHISPERMAC_TK_FORMULA:-python-tk@3.12}"

echo "=== WhisperMac — установка ==="
echo ""

if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew не найден. Установи его: https://brew.sh"
    exit 1
fi

check_tk() {
    "$1" - <<'PY'
import sys
try:
    import tkinter as tk
    root = tk.Tk()
    version = root.tk.call("info", "patchlevel")
    root.destroy()
    print(version)
    major, minor = [int(p) for p in version.split(".")[:2]]
    if (major, minor) < (8, 6):
        raise RuntimeError(f"Tk {version} is too old (need >= 8.6)")
except Exception as exc:
    print(f"ERROR: {exc}")
    sys.exit(1)
PY
}

# PortAudio (нужен для записи звука)
if ! brew list portaudio &>/dev/null; then
    echo "[1/6] Устанавливаю portaudio..."
    brew install portaudio
else
    echo "[1/6] portaudio уже установлен"
fi

# Homebrew Python + Tk
if ! brew list "$PY_FORMULA" &>/dev/null; then
    echo "[2/6] Устанавливаю $PY_FORMULA..."
    brew install "$PY_FORMULA"
else
    echo "[2/6] $PY_FORMULA уже установлен"
fi

if ! brew list "$TK_FORMULA" &>/dev/null; then
    echo "      Устанавливаю $TK_FORMULA..."
    brew install "$TK_FORMULA"
fi

PY_PREFIX="$(brew --prefix "$PY_FORMULA")"
PYTHON_BIN="$PY_PREFIX/bin/python3.12"
if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="$PY_PREFIX/bin/python3"
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
    echo "Не удалось найти python из $PY_FORMULA"
    exit 1
fi

echo "      Проверяю Tk на $PYTHON_BIN..."
if ! TK_VER="$(check_tk "$PYTHON_BIN" 2>&1)"; then
    echo "      Tk check failed:"
    echo "$TK_VER"
    echo "      Пытаюсь переустановить $TK_FORMULA..."
    brew reinstall "$TK_FORMULA"
    TK_VER="$(check_tk "$PYTHON_BIN")"
fi
echo "      Tk version: $TK_VER"

# Виртуальное окружение
echo "[3/6] Пересоздаю venv на Homebrew Python..."
rm -rf venv
"$PYTHON_BIN" -m venv venv
source venv/bin/activate

# Зависимости
echo "[4/6] Устанавливаю Python-зависимости..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Предзагрузка модели (можно отключить: WHISPERMAC_PRELOAD_MODEL=0 ./setup.sh)
if [[ "${WHISPERMAC_PRELOAD_MODEL:-1}" == "1" ]]; then
    echo "[5/6] Предзагружаю модель Whisper (первый запуск может занять время)..."
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
    echo "[5/6] Пропускаю предзагрузку модели (WHISPERMAC_PRELOAD_MODEL=0)"
fi

echo "[6/6] Собираю macOS app bundle..."
./scripts/build_app.sh

LAUNCH_APP="$ROOT_DIR/dist/WhisperMac.app"
if [[ -d "/Applications/WhisperMac.app" ]]; then
    LAUNCH_APP="/Applications/WhisperMac.app"
fi

echo ""
echo "=== Готово! ==="
echo ""
echo "Запуск:"
echo "  open \"$LAUNCH_APP\""
echo ""
echo "ВАЖНО: выдай разрешения именно для WhisperMac.app:"
echo "  1. Системные настройки → Конфиденциальность и безопасность → Микрофон → WhisperMac ✅"
echo "  2. Системные настройки → Конфиденциальность и безопасность → Универсальный доступ → WhisperMac ✅"
echo "  3. Если выдал разрешения после запуска — перезапусти WhisperMac.app"
