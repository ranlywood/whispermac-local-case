# Security & Privacy

## 1. Data flow

- Аудио обрабатывается локально на устройстве (MLX Whisper).
- Транскрипт вставляется в активное приложение через системный буфер обмена.
- Опционально создаются локальные файлы:
  - `~/whisper_log.txt` (транскрипт)
  - `~/whisper_perf.log` (метрики скорости)

## 2. Network behavior

- API-ключи не требуются и в коде не используются.
- На первом запуске модель может быть скачана из Hugging Face.
- После кэширования можно принудительно включить offline-only:
  - `WHISPERMAC_STRICT_LOCAL=1`
  - это активирует `HF_HUB_OFFLINE=1` и `TRANSFORMERS_OFFLINE=1`.

## 3. Recommended secure mode

Для приватных сессий:

```bash
WHISPERMAC_STRICT_LOCAL=1 \
WHISPERMAC_SAVE_TRANSCRIPTS=0 \
WHISPERMAC_SAVE_PERF_LOG=1 \
python whisper_mac.py
```

## 4. Before publishing repository

1. Убедись, что в репо не попали `venv/`, `WhisperMac.app/`, `*.dSYM`.
2. Удали/не добавляй пользовательские логи и транскрипты.
3. Прогони:

```bash
./scripts/preflight_share.sh
```

## 5. Threat model (short)

- Защищает от утечки через облачные ASR API (их нет).
- Не защищает, если устройство уже скомпрометировано локально.
- Не защищает от лог-утечек, если включено сохранение транскрипта.

