#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="WhisperMac"
DIST_DIR="$ROOT_DIR/dist"
APP_DIR="$DIST_DIR/${APP_NAME}.app"
ICONSET_DIR="$ROOT_DIR/AppIcon.iconset"
ICNS_PATH="$DIST_DIR/AppIcon.icns"

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

BUNDLE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT_DIR="$(cd "$BUNDLE_DIR/../.." && pwd)"
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

exec "$LAUNCH_SCRIPT"
LAUNCHER

chmod +x "$APP_DIR/Contents/MacOS/WhisperMac"

echo "Собран app bundle:"
echo "  $APP_DIR"
echo
echo "Запуск:"
echo "  open \"$APP_DIR\""
echo
echo "Разрешения (обязательны для вставки/горячих клавиш):"
echo "  1) Системные настройки -> Конфиденциальность и безопасность -> Микрофон -> WhisperMac ✅"
echo "  2) Системные настройки -> Конфиденциальность и безопасность -> Универсальный доступ -> WhisperMac ✅"
echo "  3) Если выданы после запуска: закрой и открой WhisperMac.app заново"
