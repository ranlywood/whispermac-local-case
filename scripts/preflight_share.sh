#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== WhisperMac preflight for public share =="

PATTERN='(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|api[_-]?key\s*[:=]\s*["'"'"'][^"'"'"']+["'"'"']|token\s*[:=]\s*["'"'"'][^"'"'"']+["'"'"']|secret\s*[:=]\s*["'"'"'][^"'"'"']+["'"'"']|password\s*[:=]\s*["'"'"'][^"'"'"']+["'"'"']|BEGIN [A-Z ]*PRIVATE KEY)'
EXCLUDES=(
  --glob '!.git/**'
  --glob '!venv/**'
  --glob '!__pycache__/**'
  --glob '!scripts/preflight_share.sh'
  --glob '!*.png'
  --glob '!*.icns'
  --glob '!*.pdf'
)

echo
echo "[1/3] Scanning for potential secrets..."
if rg -n --hidden -S "${EXCLUDES[@]}" "$PATTERN" .; then
  echo
  echo "Potential sensitive data found. Review before publishing."
  exit 1
fi
echo "OK: no obvious secrets found."

echo
echo "[2/3] Scanning for personal absolute paths..."
if rg -n --hidden -S "${EXCLUDES[@]}" '/Users/|C:\\\\Users\\\\|/home/' .; then
  echo
  echo "Potential personal paths found. Review if they should be removed."
  exit 1
fi
echo "OK: no personal absolute paths in tracked text files."

echo
echo "[3/3] Checking large files (>10MB) outside ignored dirs..."
LARGE_FILES="$(find . -type f ! -path './.git/*' ! -path './venv/*' ! -path './__pycache__/*' -size +10M)"
if [[ -n "$LARGE_FILES" ]]; then
  echo "$LARGE_FILES"
  echo
  echo "Large files detected. Keep only what you really want to publish."
  exit 1
fi
echo "OK: no oversized files detected."

echo
echo "Preflight passed."
