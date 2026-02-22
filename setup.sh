#!/bin/bash
# Установка WhisperMac

set -e

echo "=== WhisperMac — установка ==="
echo ""

# PortAudio (нужен для записи звука)
if ! brew list portaudio &>/dev/null; then
    echo "[1/3] Устанавливаю portaudio..."
    brew install portaudio
else
    echo "[1/3] portaudio уже установлен"
fi

# Виртуальное окружение
echo "[2/3] Создаю виртуальное окружение..."
python3 -m venv venv
source venv/bin/activate

# Зависимости
echo "[3/3] Устанавливаю Python-зависимости..."
pip install -r requirements.txt

echo ""
echo "=== Готово! ==="
echo ""
echo "Запуск:"
echo "  cd $(pwd)"
echo "  source venv/bin/activate"
echo "  python whisper_mac.py"
echo ""
echo "ВАЖНО — дай разрешения в Системных настройках:"
echo "  1. Конфиденциальность → Микрофон → Терминал ✅"
echo "  2. Конфиденциальность → Универсальный доступ → Терминал ✅"
