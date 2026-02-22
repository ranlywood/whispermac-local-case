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
cd whisper-mac
./setup.sh
source venv/bin/activate
python whisper_mac.py
```

Выдай разрешения в macOS:
- `Privacy & Security -> Microphone`
- `Privacy & Security -> Accessibility`

## Платформы

- macOS: поддерживается.
- Windows: сейчас не поддерживается, так как приложение использует macOS-специфичные `Quartz` и `AppKit`.
- Linux: не поддерживается в текущей реализации UI и горячих клавиш.

## Безопасный запуск (рекомендуется)

```bash
./scripts/launch_secure.sh
```

Скрипт запускает приложение с:
- `WHISPERMAC_STRICT_LOCAL=0` (safe default для первого запуска)
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
- `WHISPERMAC_STRICT_LOCAL=1` - только локальный режим после кэша.
- `WHISPERMAC_DOCK_MODE=regular|accessory` - отображение в Dock.
- `WHISPERMAC_APP_ICON=/path/to/AppIcon.icns` - кастомная иконка в Dock.
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
