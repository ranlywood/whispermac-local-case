#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="WhisperMac"
DIST_DIR="$ROOT_DIR/dist"
APP_DIR="$DIST_DIR/${APP_NAME}.app"
ICONSET_DIR="$ROOT_DIR/AppIcon.iconset"
ICNS_PATH="$DIST_DIR/AppIcon.icns"
INSTALL_DIR="/Applications/${APP_NAME}.app"
INSTALL_TO_APPLICATIONS="${WHISPERMAC_INSTALL_APPLICATIONS:-1}"

mkdir -p "$DIST_DIR"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

if [[ ! -d "$ICONSET_DIR" ]]; then
  echo "Не найден набор иконок: $ICONSET_DIR"
  exit 1
fi

if ! command -v iconutil >/dev/null 2>&1; then
  echo "Не найден iconutil (нужны Xcode Command Line Tools)."
  exit 1
fi

iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"
cp "$ICNS_PATH" "$APP_DIR/Contents/Resources/AppIcon.icns"

cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>WhisperMac</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIdentifier</key>
  <string>com.whispermac.local</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>WhisperMac</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
  <key>NSMicrophoneUsageDescription</key>
  <string>WhisperMac uses microphone input to transcribe your speech locally.</string>
</dict>
</plist>
PLIST

cat > "$APP_DIR/Contents/MacOS/WhisperMac" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="__PROJECT_DIR__"
PY_BIN="$PROJECT_DIR/venv/bin/python"
LAUNCH_SCRIPT="$PROJECT_DIR/scripts/launch_secure.sh"

if [[ ! -x "$PY_BIN" ]]; then
  osascript -e 'display alert "WhisperMac: нужна установка" message "Сначала запусти ./setup.sh в директории проекта." as critical'
  exit 1
fi

if [[ ! -x "$LAUNCH_SCRIPT" ]]; then
  osascript -e 'display alert "WhisperMac: ошибка запуска" message "Не найден scripts/launch_secure.sh или он не исполняемый." as critical'
  exit 1
fi

export HF_HUB_DISABLE_TELEMETRY=1
export WHISPERMAC_DOCK_MODE="${WHISPERMAC_DOCK_MODE:-regular}"
export WHISPERMAC_SAVE_TRANSCRIPTS="${WHISPERMAC_SAVE_TRANSCRIPTS:-0}"
export WHISPERMAC_HOLD_KEY="${WHISPERMAC_HOLD_KEY:-right_option}"

exec "$LAUNCH_SCRIPT"
LAUNCHER

sed -i '' "s|__PROJECT_DIR__|$ROOT_DIR|g" "$APP_DIR/Contents/MacOS/WhisperMac"
chmod +x "$APP_DIR/Contents/MacOS/WhisperMac"

LAUNCH_APP="$APP_DIR"
if [[ "$INSTALL_TO_APPLICATIONS" == "1" ]]; then
  INSTALL_BACKUP="${INSTALL_DIR}.backup-$(date +%Y%m%d-%H%M%S)"
  if [[ -d "$INSTALL_DIR" ]]; then
    if mv "$INSTALL_DIR" "$INSTALL_BACKUP" 2>/dev/null; then
      echo "Старый /Applications bundle сохранен:"
      echo "  $INSTALL_BACKUP"
    else
      echo "Предупреждение: не удалось сделать backup $INSTALL_DIR (нет прав?)."
    fi
  fi

  if cp -R "$APP_DIR" "$INSTALL_DIR" 2>/dev/null; then
    LAUNCH_APP="$INSTALL_DIR"
  else
    if [[ -d "$INSTALL_BACKUP" && ! -d "$INSTALL_DIR" ]]; then
      mv "$INSTALL_BACKUP" "$INSTALL_DIR" 2>/dev/null || true
    fi
    echo "Предупреждение: не удалось обновить $INSTALL_DIR, использую dist bundle."
  fi
fi

echo "Собран app bundle:"
echo "  $APP_DIR"
echo
echo "Запуск (актуальный app):"
echo "  open \"$LAUNCH_APP\""
echo
echo "Разрешения (обязательны для вставки/горячих клавиш):"
echo "  1) Системные настройки -> Конфиденциальность и безопасность -> Микрофон -> WhisperMac ✅"
echo "  2) Системные настройки -> Конфиденциальность и безопасность -> Универсальный доступ -> WhisperMac ✅"
echo "  3) Если выданы после запуска: закрой и открой WhisperMac.app заново"
