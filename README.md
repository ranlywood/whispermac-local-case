# WhisperMac

Локальный voice-to-text для macOS на `mlx-whisper` без облачных API и без API-ключей.

Автор материала: [t.me/ei_ai_channel](https://t.me/ei_ai_channel)

## Что это

`WhisperMac` записывает голос с микрофона, транскрибирует локально и вставляет текст в активное приложение через `Cmd+V`.

Ключевой фокус этого кейса:
- низкая задержка для длинных диктовок;
- стабильное качество без облачных сервисов;
- контроль приватности (strict local mode + отключаемое логирование).

## Почему стало быстрее

В проекте реализованы 4 принципа:
- streaming-обработка чанков без повторной конкатенации всего буфера;
- backlog-flush после stop (без одного гигантского хвоста);
- адаптивный final-pass только при проблемных случаях;
- фильтр тишины/галлюцинаций на `no_speech_prob`.

## Приватность

- API-ключи не используются.
- По умолчанию отключена телеметрия Hugging Face (`HF_HUB_DISABLE_TELEMETRY=1`).
- Для офлайн режима после первичного кэша модели:
  - `WHISPERMAC_STRICT_LOCAL=1`
  - это включает `HF_HUB_OFFLINE=1` и `TRANSFORMERS_OFFLINE=1`.

Подробно: [`SECURITY.md`](SECURITY.md)

## Быстрый старт (macOS)

```bash
git clone <your-repo-url>
cd whispermac-local-case
./setup.sh
open ./dist/WhisperMac.app
```

`setup.sh` делает всё необходимое:
- проверяет Homebrew Python + Tk (>= 8.6);
- пересоздаёт `venv` на Homebrew Python;
- ставит зависимости;
- предзагружает модель;
- собирает `dist/WhisperMac.app`.

Разрешения в macOS (важно: именно для `WhisperMac.app`):
- `System Settings -> Privacy & Security -> Microphone -> WhisperMac ✅`
- `System Settings -> Privacy & Security -> Accessibility -> WhisperMac ✅`
- если выданы после запуска: перезапусти `WhisperMac.app`

## Платформы

- macOS: поддерживается.
- Windows: сейчас не поддерживается, так как приложение использует macOS-специфичные `Quartz` и `AppKit`.
- Linux: не поддерживается в текущей реализации UI и горячих клавиш.

## Безопасный запуск (рекомендуется)

```bash
./scripts/launch_secure.sh
```

Скрипт запускает приложение с:
- `WHISPERMAC_STRICT_LOCAL=auto` (включается только если модель уже в кэше)
- `WHISPERMAC_SAVE_TRANSCRIPTS=0`
- `WHISPERMAC_SAVE_PERF_LOG=1`

После того как модель уже скачана, можно включить full offline:

```bash
WHISPERMAC_STRICT_LOCAL=1 ./scripts/launch_secure.sh
```

## Сборка .app bundle (иконка в Dock)

```bash
./scripts/build_app.sh
open ./dist/WhisperMac.app
```

Если запускать через `.app`, в Dock будет имя и иконка WhisperMac (не Python).

## Запуск без .app (dev mode)

```bash
./scripts/launch_secure.sh
```

## Тюнинг

```bash
export WHISPERMAC_CHUNK_SEC=10
export WHISPERMAC_WORKER_POLL_SEC=0.20
export WHISPERMAC_FINAL_PASS_MIN_SEC=15
export WHISPERMAC_FINAL_PASS_MAX_SEC=95
python whisper_mac.py
```

Полезные env:
- `WHISPERMAC_MODEL_REPO` - HF repo или локальный путь к модели.
- `WHISPERMAC_LANGUAGE` - язык (по умолчанию `ru`).
- `WHISPERMAC_PY_FORMULA` - Homebrew Python formula для `setup.sh` (по умолчанию `python@3.12`).
- `WHISPERMAC_TK_FORMULA` - Homebrew Tk formula для `setup.sh` (по умолчанию `python-tk@3.12`).
- `WHISPERMAC_STRICT_LOCAL=1` - только локальный режим после кэша.
- `WHISPERMAC_DOCK_MODE=regular|accessory` - отображение в Dock.
- `WHISPERMAC_MIC_ICON=/path/to/mic.png` - кастомная PNG-иконка микрофона (по умолчанию используется встроенный canvas-стиль).
- `WHISPERMAC_SAVE_TRANSCRIPTS=0` - не писать `~/whisper_log.txt`.
- `WHISPERMAC_SAVE_PERF_LOG=0` - не писать `~/whisper_perf.log`.

## Публичный релиз-чек

Перед публикацией прогоняй:

```bash
./scripts/preflight_share.sh
```

Скрипт проверяет:
- потенциальные секреты;
- персональные абсолютные пути;
- крупные бинарники, которые не должны попасть в репо.

## Материалы кейса

- Кейс: [`docs/CASE_STUDY_RU.md`](docs/CASE_STUDY_RU.md)
- Драфт поста: [`docs/POST_DRAFT_RU.md`](docs/POST_DRAFT_RU.md)
