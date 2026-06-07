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
PY_BIN="$ROOT_DIR/venv/bin/python"
LAUNCHER_SRC="$ROOT_DIR/launcher.c"

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

if [[ ! -x "$PY_BIN" ]]; then
  echo "Не найден Python venv: $PY_BIN"
  echo "Сначала запусти ./setup.sh в директории проекта."
  exit 1
fi

if [[ ! -f "$LAUNCHER_SRC" ]]; then
  echo "Не найден native launcher: $LAUNCHER_SRC"
  exit 1
fi

if ! command -v clang >/dev/null 2>&1; then
  echo "Не найден clang (нужны Xcode Command Line Tools)."
  exit 1
fi

PY_VERSION="$("$PY_BIN" - <<'PY'
import sysconfig
print(sysconfig.get_config_var("VERSION") or "")
PY
)"
PY_INCLUDE="$("$PY_BIN" - <<'PY'
import sysconfig
print(sysconfig.get_config_var("INCLUDEPY") or "")
PY
)"
PY_LIBDIR="$("$PY_BIN" - <<'PY'
import sysconfig
print(sysconfig.get_config_var("LIBDIR") or "")
PY
)"
PY_LDFLAGS="$("$PY_BIN" - <<'PY'
import sysconfig
parts = [
    f"-L{sysconfig.get_config_var('LIBDIR')}",
    f"-lpython{sysconfig.get_config_var('VERSION')}",
    "-ldl",
    "-framework", "CoreFoundation",
]
print(" ".join(p for p in parts if p and p != "-LNone" and p != "-lpythonNone"))
PY
)"

if [[ -z "$PY_VERSION" || -z "$PY_INCLUDE" || -z "$PY_LIBDIR" ]]; then
  echo "Не удалось получить параметры сборки Python из $PY_BIN"
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
  <key>NSInputMonitoringUsageDescription</key>
  <string>WhisperMac listens for the hold-to-talk hotkey and sends paste keystrokes to insert transcribed text.</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>WhisperMac uses System Events as a fallback to paste transcribed text into the active app.</string>
</dict>
</plist>
PLIST

clang \
  "$LAUNCHER_SRC" \
  -o "$APP_DIR/Contents/MacOS/WhisperMac" \
  -I"$PY_INCLUDE" \
  -Wl,-rpath,"$PY_LIBDIR" \
  $PY_LDFLAGS \
  -DWHISPERMAC_PROJECT_DIR="\"$ROOT_DIR\"" \
  -DWHISPERMAC_PYTHON_VERSION="\"$PY_VERSION\""
chmod +x "$APP_DIR/Contents/MacOS/WhisperMac"

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP_DIR" >/dev/null
fi

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
echo "  3) Системные настройки -> Конфиденциальность и безопасность -> Мониторинг ввода -> WhisperMac ✅"
echo "  4) Если macOS спросит Automation/System Events -> Разрешить"
echo "  5) Если выданы после запуска: закрой и открой WhisperMac.app заново"
