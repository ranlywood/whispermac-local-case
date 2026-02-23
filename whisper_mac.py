#!/usr/bin/env python3
"""
WhisperMac — голосовой ввод для macOS (streaming + real-time EQ)
"""

import math
import os
import subprocess
import threading
import time

import numpy as np
import sounddevice as sd
import mlx_whisper
import tkinter as tk

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)
from AppKit import NSWorkspace


# ═══════════════════════════════════════════════════
def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Отключаем телеметрию Hugging Face по умолчанию.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

# Для строгого локального режима после первичного кэша модели:
# WHISPERMAC_STRICT_LOCAL=1 -> без сетевых запросов.
STRICT_LOCAL_MODE = _env_bool("WHISPERMAC_STRICT_LOCAL", False)
if STRICT_LOCAL_MODE:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

MODEL_REPO   = os.getenv("WHISPERMAC_MODEL_REPO", "mlx-community/whisper-large-v3-mlx-4bit")
LANGUAGE     = os.getenv("WHISPERMAC_LANGUAGE", "ru")
SAMPLE_RATE  = 16000
MIN_DURATION = 0.3
SAVE_TRANSCRIPTS = _env_bool("WHISPERMAC_SAVE_TRANSCRIPTS", True)
SAVE_PERF_LOG = _env_bool("WHISPERMAC_SAVE_PERF_LOG", True)

CHUNK_SEC    = max(5.0, _env_float("WHISPERMAC_CHUNK_SEC", 10.0))
WORKER_POLL_SEC = max(0.05, _env_float("WHISPERMAC_WORKER_POLL_SEC", 0.20))
FINAL_PASS_MIN_SEC = max(5.0, _env_float("WHISPERMAC_FINAL_PASS_MIN_SEC", 15.0))
FINAL_PASS_MAX_SEC = max(
    FINAL_PASS_MIN_SEC,
    _env_float("WHISPERMAC_FINAL_PASS_MAX_SEC", 95.0),
)
LOW_CONF_LOGPROB = _env_float("WHISPERMAC_LOW_CONF_LOGPROB", -1.15)
SILENCE_SKIP_NO_SPEECH = min(
    0.99,
    max(0.5, _env_float("WHISPERMAC_SILENCE_SKIP_NO_SPEECH", 0.83)),
)
SILENCE_SKIP_MAX_CHARS = int(max(8, _env_float("WHISPERMAC_SILENCE_SKIP_MAX_CHARS", 36)))
FINAL_TEMPERATURES = (0.0, 0.2, 0.4, 0.6)
HOTWORDS_PROMPT = "WhisperMac, Whisper Flow, Miro, Zoom, Claude Code, ChatGPT."
# ═══════════════════════════════════════════════════

W, H   = 228, 52
RADIUS = H // 2
MIC_X = 22

BG         = "#0D0D0F"
PILL       = "#1C1C1E"
C_IDLE     = "#3A3A3C"
C_REC      = "#FF375F"
C_PROC     = "#FF9F0A"
C_MIC_BG     = "#2C2C2E"   # круг микрофона в покое
C_MIC_BG_ON  = "#FF375F"   # круг микрофона при записи
C_MIC_SYM    = "#D7DBE2"   # символ микрофона в покое
C_MIC_SYM_ON = "#FF375F"   # символ микрофона при записи
C_CLOSE_BG   = "#2C2C2E"
C_CLOSE_HV   = "#3A3A3C"
C_CLOSE_X    = "#8E8E93"

BAR_COUNT = 7
BAR_W     = 3
BAR_STEP  = 7
BARS_X    = 74
BAR_MIN   = 2.0
BAR_MAX   = 18.0

# EQ smoothing
EQ_ATTACK        = 0.86
EQ_DECAY         = 0.28    # плавнее спад, меньше "рваности"
EQ_RMS_THRESHOLD = 0.0038  # ниже этого — тишина
EQ_RMS_ALPHA     = 0.42    # сглаживание RMS для плавного live-ответа
EQ_RMS_FULL      = 0.028   # rms, при котором бары считаются "полными"
EQ_VISUAL_GAMMA  = 0.62    # усиливает видимую реакцию на среднюю громкость
EQ_WOBBLE_MAX    = 0.16    # добавляет "живость" баров при речи

V_KEY = 9


def log(msg):
    print(f"  {msg}", flush=True)


def frontmost_bundle():
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return app.bundleIdentifier() if app else None


def activate_bundle(bid):
    NSApplicationActivateIgnoringOtherApps = 2
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if app.bundleIdentifier() == bid:
            app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
            return True
    return False


def cmd_v():
    for pressed in (True, False):
        e = CGEventCreateKeyboardEvent(None, V_KEY, pressed)
        CGEventSetFlags(e, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, e)


def _clean_chunk(text: str) -> str:
    """Убирает артефакты Whisper на границах чанков."""
    import re
    text = text.strip()
    # Убираем ведущие/замыкающие точки, многоточия, пробелы
    text = re.sub(r'^[\s\.…]+', '', text)
    text = re.sub(r'[\s\.…]+$', '', text)
    return text.strip()


def _join_chunks(parts: list) -> str:
    cleaned = [_clean_chunk(p) for p in parts]
    cleaned = [p for p in cleaned if p]
    return " ".join(cleaned)


def _prompt_from_parts(parts: list) -> str:
    """Короткий prompt для смешанной русско-английской речи."""
    tail = _join_chunks(parts)[-180:] if parts else ""
    return f"{HOTWORDS_PROMPT}\n{tail}" if tail else HOTWORDS_PROMPT


def _is_repetition_loop(text: str) -> bool:
    """Детектирует типичный whisper-loop c многократным повтором одной фразы."""
    import re
    words = re.findall(r"[\w$]+", text.lower())
    if len(words) < 12:
        return False

    def max_consecutive_repeat(n: int) -> int:
        best = 1
        i = 0
        end = len(words) - 2 * n
        while i <= end:
            gram = words[i:i+n]
            j = i + n
            run = 1
            while j + n <= len(words) and words[j:j+n] == gram:
                run += 1
                j += n
            if run > best:
                best = run
            i = i + 1 if run == 1 else j
        return best

    # Главный сигнал: подряд много раз повторяется одна и та же короткая фраза.
    for n in (2, 3):
        if max_consecutive_repeat(n) >= 5:
            return True

    def max_ngram_count(n: int) -> tuple:
        from collections import Counter
        grams = [tuple(words[i:i+n]) for i in range(len(words) - n + 1)]
        if not grams:
            return (), 0
        gram, count = Counter(grams).most_common(1)[0]
        return gram, count

    # Если один и тот же биграм/триграм покрывает заметную часть текста — это loop.
    for n in (2, 3):
        gram, count = max_ngram_count(n)
        if count >= 10 and (count * n) / max(1, len(words)) >= 0.08:
            return True

    # Отдельный сигнал: многократно повторяется короткая конструкция, напр. "выиграли $0".
    m = re.search(r"(\b[\w$]+(?:\s+[\w$]+){0,2}\b)(?:[\s,.;:!?-]+\1){6,}", text.lower())
    if m:
        return True

    # Еще один сильный индикатор артефакта: ненормально много "$0".
    zero_dollars = sum(1 for w in words if w == "$0" or w.endswith("$0"))
    if zero_dollars >= 6 and zero_dollars / len(words) >= 0.04:
        return True

    return False


def _collapse_repetition_loop(text: str) -> str:
    """Последняя защита: схлопывает подряд идущие повторы короткой фразы."""
    import re
    prev = None
    cur = text
    pattern = re.compile(
        r"(\b[\w$]+(?:\s+[\w$]+){0,2}\b)(?:[\s,.;:!?-]+\1){3,}",
        re.IGNORECASE,
    )
    while prev != cur:
        prev = cur
        cur = pattern.sub(r"\1", cur)
    return cur


def _segment_quality(result: dict) -> tuple:
    segments = result.get("segments") or []
    if not segments:
        return 0.0, 0.0
    avg_logprob = sum(float(s.get("avg_logprob", 0.0)) for s in segments) / len(segments)
    avg_no_speech = sum(float(s.get("no_speech_prob", 0.0)) for s in segments) / len(segments)
    return avg_logprob, avg_no_speech


def _likely_silence_hallucination(text: str, avg_no_speech: float) -> bool:
    if not text:
        return False
    return avg_no_speech >= SILENCE_SKIP_NO_SPEECH and len(text.strip()) <= SILENCE_SKIP_MAX_CHARS


def pill_points(x1, y1, x2, y2, r):
    return [
        x1+r, y1,   x2-r, y1,
        x2,   y1,   x2,   y1+r,
        x2,   y2-r, x2,   y2,
        x2-r, y2,   x1+r, y2,
        x1,   y2,   x1,   y2-r,
        x1,   y1+r, x1,   y1,
    ]


class App:
    EXCLUDED = {"python", "whisper-mac", "com.apple.finder"}

    def __init__(self):
        self.ready      = False
        self.recording  = False
        self.processing = False
        self.chunks     = []
        self._chunks_lock = threading.Lock()
        self.stream     = None
        self.target     = None
        self._recording_started_at = None
        self._frame     = 0
        self._drag_ox   = 0
        self._drag_oy   = 0
        self._dragging  = False
        self._hold_key_down = False
        self._hold_started_recording = False
        self._keyboard_listener = None
        self._keyboard_mod = None
        self._hold_key_mode = self._normalize_hold_key_mode(
            os.getenv("WHISPERMAC_HOLD_KEY", "off")
        )

        # Real-time EQ levels (driven by FFT in audio callback)
        self._eq_levels = np.zeros(BAR_COUNT, dtype=np.float32)
        self._eq_smooth = np.zeros(BAR_COUNT, dtype=np.float32)
        self._rms_smooth = 0.0

        # PNG-иконка микрофона
        self._mic_photo_idle   = None
        self._mic_photo_active = None
        self._mic_item         = None

        # ── Окно ────────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.96)
        self.root.configure(bg=BG)
        self._load_mic_images()

        sx = self.root.winfo_screenwidth()  - W - 28
        sy = self.root.winfo_screenheight() - H - 96
        self.root.geometry(f"{W}x{H}+{sx}+{sy}")

        # ── Canvas ───────────────────────────────────────────────
        self.cv = tk.Canvas(self.root, width=W, height=H,
                            bg=BG, highlightthickness=0)
        self.cv.pack()

        # Пилл
        self.cv.create_polygon(
            pill_points(0, 0, W, H, RADIUS),
            smooth=True, fill=PILL, outline=""
        )

        # Иконка микрофона (рисованная)
        self._draw_mic(recording=False)

        # Спиннер загрузки
        self.spinner = self.cv.create_text(
            28, H // 2, text="◌", font=("Helvetica", 22), fill="#636366"
        )
        self.cv.itemconfig("mic", state="hidden")

        # Эквалайзер
        cy = H // 2
        self.bars = []
        for i in range(BAR_COUNT):
            x = BARS_X + i * BAR_STEP
            b = self.cv.create_rectangle(
                x, cy - BAR_MIN, x + BAR_W, cy + BAR_MIN,
                fill=C_IDLE, outline="", tags="bar"
            )
            self.bars.append((b, x))

        # Кнопка закрытия (рисованная)
        self._draw_close()

        # ── Биндинги ────────────────────────────────────────────
        self.cv.tag_bind("close", "<Button-1>",
                         lambda e: self.root.destroy())
        self.cv.tag_bind("close", "<Enter>",
                         lambda e: self.cv.itemconfig(self._close_bg,
                                                      fill=C_CLOSE_HV))
        self.cv.tag_bind("close", "<Leave>",
                         lambda e: self.cv.itemconfig(self._close_bg,
                                                      fill=C_CLOSE_BG))

        self.cv.bind("<ButtonPress-1>",  self._press)
        self.cv.bind("<B1-Motion>",       self._motion)
        self.cv.bind("<ButtonRelease-1>", self._release)

        self.root.bind("<Destroy>", self._on_destroy)

        self._setup_hold_key_listener()
        self._track_app()
        self._tick()
        threading.Thread(target=self._load_model, daemon=True).start()

    def _normalize_hold_key_mode(self, raw: str) -> str:
        mode = (raw or "").strip().lower()
        if mode in {"right_option", "option_r", "alt_r"}:
            return "right_option"
        return "off"

    def _setup_hold_key_listener(self):
        if self._hold_key_mode == "off":
            log("Hold-to-talk: off")
            return
        try:
            from pynput import keyboard
        except Exception as ex:
            log(f"Hold-to-talk отключен: не удалось загрузить pynput ({ex})")
            self._hold_key_mode = "off"
            return

        self._keyboard_mod = keyboard
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_global_key_press,
            on_release=self._on_global_key_release,
        )
        self._keyboard_listener.daemon = True
        self._keyboard_listener.start()
        log("Hold-to-talk: right option (нажал -> запись, отпустил -> вставка)")

    def _on_destroy(self, event):
        if event.widget is self.root:
            try:
                if self._keyboard_listener:
                    self._keyboard_listener.stop()
            except Exception:
                pass

    def _is_hold_key(self, key) -> bool:
        if self._hold_key_mode != "right_option" or self._keyboard_mod is None:
            return False
        alt_right = getattr(self._keyboard_mod.Key, "alt_r", None)
        alt_graph = getattr(self._keyboard_mod.Key, "alt_gr", None)
        return key == alt_right or key == alt_graph

    def _on_global_key_press(self, key):
        if not self._is_hold_key(key):
            return
        if self._hold_key_down:
            return
        self._hold_key_down = True
        try:
            self.root.after(0, self._handle_hold_key_down)
        except Exception:
            pass

    def _on_global_key_release(self, key):
        if not self._is_hold_key(key):
            return
        if not self._hold_key_down:
            return
        self._hold_key_down = False
        try:
            self.root.after(0, self._handle_hold_key_up)
        except Exception:
            pass

    def _handle_hold_key_down(self):
        if not self.ready or self.processing or self.recording:
            self._hold_started_recording = False
            return
        self._hold_started_recording = True
        self._start_rec()

    def _handle_hold_key_up(self):
        if self._hold_started_recording and self.recording:
            self._stop_rec()
        self._hold_started_recording = False

    # ── Загрузка PNG-иконки ─────────────────────────────────────
    def _load_mic_images(self):
        try:
            from PIL import Image, ImageTk
            from pathlib import Path

            # По умолчанию используем канвас-иконку (как на референсе UI).
            if not _env_bool("WHISPERMAC_USE_PNG_MIC_ICON", True):
                raise FileNotFoundError("PNG mic icon disabled by default")

            env_icon = os.getenv("WHISPERMAC_MIC_ICON")
            candidates = [
                Path(env_icon).expanduser() if env_icon else None,
                Path.home() / "Downloads" / "микро.png",
                Path.home() / "Downloads" / "micro.png",
                Path(__file__).resolve().parent / "assets" / "mic.png",
            ]
            icon_path = None
            for path in candidates:
                if path and path.exists():
                    icon_path = path
                    break

            if icon_path is None:
                raise FileNotFoundError("No mic icon found")

            img  = Image.open(icon_path).convert("RGBA")
            img  = img.resize((28, 28), Image.LANCZOS)
            data = np.array(img, dtype=np.uint8)

            # Убираем светлый фон → прозрачность
            white = (data[:,:,0] > 200) & (data[:,:,1] > 200) & (data[:,:,2] > 200)
            data[white, 3] = 0
            mask = data[:,:,3] > 10

            # Idle: серый (#8E8E93)
            d_idle = data.copy()
            d_idle[mask, 0] = 0xD7
            d_idle[mask, 1] = 0xDB
            d_idle[mask, 2] = 0xE2

            # Active: оригинальный розовый
            d_active = data.copy()

            self._mic_photo_idle   = ImageTk.PhotoImage(Image.fromarray(d_idle,   "RGBA"))
            self._mic_photo_active = ImageTk.PhotoImage(Image.fromarray(d_active, "RGBA"))
            log(f"Иконка микрофона загружена: {icon_path}")
        except Exception as ex:
            log(f"PNG-иконка недоступна, используем canvas: {ex}")

    def _open_privacy_panel(self, key: str):
        try:
            subprocess.run(
                ["open", f"x-apple.systempreferences:com.apple.preference.security?Privacy_{key}"],
                check=False,
            )
        except Exception as ex:
            log(f"Не удалось открыть настройки Privacy_{key}: {ex}")

    # ── Рисование иконок ────────────────────────────────────────
    def _draw_mic(self, recording=False):
        """Иконка микрофона — PNG если доступен, иначе canvas-примитивы."""
        x, cy = MIC_X, H // 2

        if self._mic_photo_idle and self._mic_photo_active:
            photo = self._mic_photo_active if recording else self._mic_photo_idle
            self._mic_item = self.cv.create_image(
                x, cy, image=photo, anchor="center", tags="mic"
            )
            return

        # ── Fallback: canvas-примитивы (классический стиль без круга) ──────
        sym = C_MIC_SYM_ON if recording else C_MIC_SYM

        cw, ch, lw = 8, 11, 1.8
        cap_top = cy - 7
        cap_bot = cap_top + ch
        self.cv.create_arc(x-cw//2, cap_top, x+cw//2, cap_top+cw,
                           start=0, extent=180, style="arc",
                           outline=sym, width=lw, tags=("mic", "mic_sym"))
        self.cv.create_line(x-cw//2, cap_top+cw//2, x-cw//2, cap_bot,
                            fill=sym, width=lw, tags=("mic", "mic_sym"))
        self.cv.create_line(x+cw//2, cap_top+cw//2, x+cw//2, cap_bot,
                            fill=sym, width=lw, tags=("mic", "mic_sym"))
        self.cv.create_arc(x-cw//2, cap_bot-cw, x+cw//2, cap_bot,
                           start=180, extent=180, style="arc",
                           outline=sym, width=lw, tags=("mic", "mic_sym"))
        sr = 5
        self.cv.create_arc(x-sr, cap_bot, x+sr, cap_bot+sr*2,
                           start=0, extent=-180, style="arc",
                           outline=sym, width=lw, tags=("mic", "mic_sym"))
        self.cv.create_line(x-4, cap_bot+sr*2, x+4, cap_bot+sr*2,
                            fill=sym, width=lw, capstyle="round",
                            tags=("mic", "mic_sym"))

    def _set_mic_color(self, recording=False):
        if self._mic_item and self._mic_photo_idle and self._mic_photo_active:
            photo = self._mic_photo_active if recording else self._mic_photo_idle
            self.cv.itemconfig(self._mic_item, image=photo)
            self._current_mic_photo = photo   # не допускаем garbage collection
            return

        # Fallback: canvas-примитивы
        sym = C_MIC_SYM_ON if recording else C_MIC_SYM
        for item in self.cv.find_withtag("mic_sym"):
            t = self.cv.type(item)
            if t == "line":
                self.cv.itemconfig(item, fill=sym)
            elif t == "arc":
                self.cv.itemconfig(item, outline=sym)

    def _draw_close(self):
        """Круглая кнопка закрытия с крестиком."""
        cx = W - 22
        cy_c = H // 2
        self._close_bg = self.cv.create_oval(
            cx - 13, cy_c - 13, cx + 13, cy_c + 13,
            fill=C_CLOSE_BG, outline="", tags="close"
        )
        d = 5
        lw = 1
        self.cv.create_line(cx-d, cy_c-d, cx+d, cy_c+d,
                             fill=C_CLOSE_X, width=lw,
                             capstyle="round", tags="close")
        self.cv.create_line(cx-d, cy_c+d, cx+d, cy_c-d,
                             fill=C_CLOSE_X, width=lw,
                             capstyle="round", tags="close")

    # ── Drag ────────────────────────────────────────────────────
    def _press(self, e):
        if e.x > W - 44:
            return
        self._drag_ox = e.x
        self._drag_oy = e.y
        self._dragging = False

    def _motion(self, e):
        if e.x > W - 44:
            return
        if abs(e.x - self._drag_ox) + abs(e.y - self._drag_oy) > 4:
            self._dragging = True
        if self._dragging:
            self.root.geometry(
                f"+{self.root.winfo_x() + e.x - self._drag_ox}"
                f"+{self.root.winfo_y() + e.y - self._drag_oy}"
            )

    def _release(self, e):
        if e.x > W - 44:
            return
        if not self._dragging:
            self._toggle()
        self._dragging = False

    # ── Запись ──────────────────────────────────────────────────
    def _toggle(self):
        if not self.ready or self.processing:
            return
        if not self.recording:
            self._start_rec()
        else:
            self._stop_rec()

    def _start_rec(self):
        with self._chunks_lock:
            self.chunks = []
        self._eq_levels[:] = 0
        self._eq_smooth[:] = 0
        self._rms_smooth = 0.0
        self._recording_started_at = time.perf_counter()
        self.target    = frontmost_bundle() or self.target
        self.recording = True
        self._set_mic_color(recording=True)
        log(
            f"Конфиг: chunk={CHUNK_SEC:.1f}s, poll={WORKER_POLL_SEC:.2f}s, "
            f"final-pass={FINAL_PASS_MIN_SEC:.0f}-{FINAL_PASS_MAX_SEC:.0f}s"
        )
        log(
            f"Privacy: strict_local={'on' if STRICT_LOCAL_MODE else 'off'}, "
            f"save_transcripts={'on' if SAVE_TRANSCRIPTS else 'off'}, "
            f"save_perf={'on' if SAVE_PERF_LOG else 'off'}"
        )
        log(f"Запись... ({self.target})")
        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                blocksize=1024, latency="low", callback=self._audio_cb
            )
            self.stream.start()
        except Exception as ex:
            log(f"Ошибка: {ex}")
            err = str(ex).lower()
            if any(k in err for k in ("permission", "not permitted", "unauthorized", "access")):
                self._open_privacy_panel("Microphone")
            self._reset()
            return
        threading.Thread(target=self._streaming_worker, daemon=True).start()

    def _stop_rec(self):
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        self.processing = True
        self._set_mic_color(recording=False)

    # ── Аудио-коллбэк (real-time FFT для эквалайзера) ───────────
    def _audio_cb(self, indata, frames, time_info, status):
        frame = indata.flatten()
        with self._chunks_lock:
            self.chunks.append(indata.copy())

        if len(frame) < 64:
            return

        # Сначала проверяем реальную громкость
        rms = float(np.sqrt(np.mean(frame ** 2)))
        self._rms_smooth = (
            (1.0 - EQ_RMS_ALPHA) * self._rms_smooth + EQ_RMS_ALPHA * rms
        )
        gate = EQ_RMS_THRESHOLD

        if self._rms_smooth <= gate:
            self._eq_levels[:] = 0
            return

        # FFT → частотные полосы
        windowed = frame * np.hanning(len(frame))
        fft_vals  = np.abs(np.fft.rfft(windowed))
        n_bins    = len(fft_vals)

        levels = np.array([
            np.mean(fft_vals[n_bins * i // BAR_COUNT : n_bins * (i+1) // BAR_COUNT])
            for i in range(BAR_COUNT)
        ], dtype=np.float32)

        peak = levels.max()
        if peak > 1e-6:
            # Нормализуем форму (0–1), затем масштабируем по реальной громкости
            shape = levels / peak
            denom = max(1e-6, EQ_RMS_FULL - EQ_RMS_THRESHOLD)
            amplitude = min(
                1.0,
                max(0.0, (self._rms_smooth - EQ_RMS_THRESHOLD) / denom),
            )
            # Чуть поднимаем средние уровни, чтобы анимация читалась живее.
            amplitude = amplitude ** 0.72
            self._eq_levels[:] = (shape * amplitude).astype(np.float32)
        else:
            self._eq_levels[:] = 0

    def _transcribe_audio(
        self,
        audio,
        *,
        prompt=None,
        final=False,
        condition_on_previous_text=True,
        temperature=None,
    ):
        opts = dict(
            path_or_hf_repo=MODEL_REPO,
            language=LANGUAGE,
            initial_prompt=prompt,
            condition_on_previous_text=condition_on_previous_text,
        )
        # Beam search в mlx_whisper пока не реализован.
        opts["temperature"] = (
            temperature if temperature is not None
            else (FINAL_TEMPERATURES if final else 0.0)
        )
        return mlx_whisper.transcribe(audio, **opts)

    def _take_new_audio(self, chunk_idx: int) -> tuple:
        with self._chunks_lock:
            total = len(self.chunks)
            if chunk_idx >= total:
                return chunk_idx, None
            new_chunks = self.chunks[chunk_idx:total]
            chunk_idx = total
        if not new_chunks:
            return chunk_idx, None
        new_audio = np.concatenate([c.flatten() for c in new_chunks])
        return chunk_idx, new_audio

    def _decode_piece(self, audio: np.ndarray, parts: list, label: str) -> tuple:
        prompt = _prompt_from_parts(parts)
        started = time.perf_counter()
        result = self._transcribe_audio(audio, prompt=prompt, final=False)
        elapsed = time.perf_counter() - started
        text = result.get("text", "").strip()
        avg_logprob, avg_no_speech = _segment_quality(result)
        if _likely_silence_hallucination(text, avg_no_speech):
            log(
                f"[{label}] пропуск (тишина): no_speech={avg_no_speech:.2f}, "
                f"text='{text[:24]}'"
            )
            return "", elapsed, avg_logprob, avg_no_speech
        if text:
            log(f"[{label}] {text}")
        return text, elapsed, avg_logprob, avg_no_speech

    # ── Streaming воркер ────────────────────────────────────────
    def _streaming_worker(self):
        """
        Эффективный воркер для длинных записей.
        Хранит pending-буфер, потребляет только НОВЫЕ чанки —
        не конкатенирует весь массив каждую итерацию.
        """
        CHUNK      = int(CHUNK_SEC * SAMPLE_RATE)
        parts      = []
        pending    = np.array([], dtype=np.float32)   # необработанный буфер
        chunk_idx  = 0                                 # сколько чанков уже взяли
        decode_time_sec = 0.0
        processed_audio_sec = 0.0
        low_conf_chunks = 0
        decoded_chunks = 0

        while self.recording:
            time.sleep(WORKER_POLL_SEC)

            # Берём только новые чанки с момента последней итерации
            chunk_idx, new_audio = self._take_new_audio(chunk_idx)
            if new_audio is None:
                continue
            pending   = np.concatenate([pending, new_audio]) if len(pending) else new_audio

            # Обрабатываем все полные чанки из буфера
            # (если модель отстала — догоняем в цикле)
            while len(pending) >= CHUNK:
                segment = pending[:CHUNK]
                pending = pending[CHUNK:]

                text, elapsed, avg_logprob, _ = self._decode_piece(
                    segment, parts, "chunk"
                )
                decode_time_sec += elapsed
                processed_audio_sec += len(segment) / SAMPLE_RATE
                decoded_chunks += 1
                if avg_logprob <= LOW_CONF_LOGPROB:
                    low_conf_chunks += 1
                if text:
                    parts.append(text)

        # Запись остановлена — добираем остаток
        chunk_idx, new_audio = self._take_new_audio(chunk_idx)
        if new_audio is not None:
            pending   = np.concatenate([pending, new_audio]) if len(pending) else new_audio

        # Если во время записи модель отстала, догоняем backlog кусками.
        while len(pending) >= CHUNK:
            segment = pending[:CHUNK]
            pending = pending[CHUNK:]
            text, elapsed, avg_logprob, _ = self._decode_piece(segment, parts, "flush")
            decode_time_sec += elapsed
            processed_audio_sec += len(segment) / SAMPLE_RATE
            decoded_chunks += 1
            if avg_logprob <= LOW_CONF_LOGPROB:
                low_conf_chunks += 1
            if text:
                parts.append(text)

        amp = float(np.max(np.abs(pending))) if len(pending) else 0
        if len(pending) / SAMPLE_RATE >= MIN_DURATION and amp > 0.001:
            text, elapsed, avg_logprob, _ = self._decode_piece(pending, parts, "tail")
            decode_time_sec += elapsed
            processed_audio_sec += len(pending) / SAMPLE_RATE
            decoded_chunks += 1
            if avg_logprob <= LOW_CONF_LOGPROB:
                low_conf_chunks += 1
            if text:
                parts.append(text)

        chunk_full = _join_chunks(parts)
        full = chunk_full

        # Финальный quality-pass по всей записи: выше точность на длинных фразах.
        with self._chunks_lock:
            all_audio = (
                np.concatenate([c.flatten() for c in self.chunks])
                if self.chunks else np.array([], dtype=np.float32)
            )
        if len(all_audio):
            audio_sec = len(all_audio) / SAMPLE_RATE
            low_conf_ratio = (
                (low_conf_chunks / decoded_chunks)
                if decoded_chunks else 0.0
            )
            need_final_pass = (
                FINAL_PASS_MIN_SEC <= audio_sec <= FINAL_PASS_MAX_SEC
                and (
                    _is_repetition_loop(chunk_full)
                    or not chunk_full
                    or low_conf_ratio >= 0.35
                )
            )
            if need_final_pass and audio_sec >= MIN_DURATION:
                try:
                    final_res = self._transcribe_audio(
                        all_audio,
                        prompt=HOTWORDS_PROMPT,
                        final=True,
                        # Этот режим в Whisper меньше зацикливается на повторах.
                        condition_on_previous_text=False,
                    )
                    final_text = final_res.get("text", "").strip()
                    if final_text:
                        if _is_repetition_loop(final_text):
                            log("[final] обнаружен loop-повтор, пробую safe-pass")
                            safe_res = self._transcribe_audio(
                                all_audio,
                                prompt=None,
                                final=False,
                                condition_on_previous_text=False,
                                temperature=0.0,
                            )
                            safe_text = safe_res.get("text", "").strip()
                            if safe_text and not _is_repetition_loop(safe_text):
                                log(f"[final-safe] {safe_text}")
                                full = safe_text
                            else:
                                log("[final] loop остался, fallback на chunk-текст")
                                full = chunk_full
                        else:
                            log(f"[final] {final_text}")
                            full = final_text
                except Exception as ex:
                    log(f"[final] fallback на чанки: {ex}")
            elif audio_sec > FINAL_PASS_MAX_SEC:
                skip_line = (
                    f"[final] пропуск полного pass: запись {audio_sec:.1f}s > "
                    f"{FINAL_PASS_MAX_SEC:.0f}s"
                )
                log(skip_line)
                self._save_perf(skip_line)

        if full and _is_repetition_loop(full):
            collapsed = _collapse_repetition_loop(full).strip()
            if collapsed and collapsed != full:
                log("[post] схлопнул повторяющийся loop-текст")
                full = collapsed

        record_wall_sec = 0.0
        if self._recording_started_at is not None:
            record_wall_sec = max(0.0, time.perf_counter() - self._recording_started_at)
        if processed_audio_sec > 0:
            rtf = decode_time_sec / processed_audio_sec
            perf_line = (
                f"[perf] обработано {processed_audio_sec:.1f}s аудио за "
                f"{decode_time_sec:.2f}s (RTF={rtf:.2f}x), запись шла {record_wall_sec:.1f}s"
            )
            log(perf_line)
            self._save_perf(perf_line)

        log(f"→ {full}")
        if full:
            self._save(full)
            self.root.after(0, lambda t=full: self._paste_and_reset(t))
        else:
            self.root.after(0, self._reset)

    # ── Вспомогательные ─────────────────────────────────────────
    def _save(self, text):
        if not SAVE_TRANSCRIPTS:
            return
        from datetime import datetime
        from pathlib import Path
        with open(Path.home() / "whisper_log.txt", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {text}\n")

    def _save_perf(self, text):
        if not SAVE_PERF_LOG:
            return
        from datetime import datetime
        from pathlib import Path
        with open(Path.home() / "whisper_perf.log", "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {text}\n")

    def _paste_and_reset(self, text):
        subprocess.run(["pbcopy"], input=text, text=True)
        time.sleep(0.05)   # буфер обмена должен осесть
        log(f"Cmd+V → {frontmost_bundle()}")
        cmd_v()
        self._reset()

    def _reset(self):
        self.processing  = False
        self._eq_levels[:] = 0
        self._set_mic_color(recording=False)

    # ── Анимация ────────────────────────────────────────────────
    def _tick(self):
        self._frame += 1
        t  = self._frame * 0.12
        cy = H // 2

        if self.recording:
            # Attack/decay smoothing для ощущения VU-метра
            target = np.power(np.clip(self._eq_levels, 0.0, 1.0), EQ_VISUAL_GAMMA)
            rising = target > self._eq_smooth
            self._eq_smooth = np.where(
                rising,
                self._eq_smooth + (target - self._eq_smooth) * EQ_ATTACK,
                self._eq_smooth * (1.0 - EQ_DECAY)
            )
            energy = float(np.mean(target))
            for i, (b, bx) in enumerate(self.bars):
                wobble = 0.0
                if energy > 0.03:
                    wobble = (
                        0.5 + 0.5 * math.sin(t * (5.2 + i * 0.15) + i * 0.9)
                    ) * EQ_WOBBLE_MAX * energy
                level = min(1.0, self._eq_smooth[i] + wobble)
                h = BAR_MIN + level * BAR_MAX
                self.cv.coords(b, bx, cy - h, bx + BAR_W, cy + h)
                self.cv.itemconfig(b, fill=C_REC)

        elif self.processing:
            for i, (b, bx) in enumerate(self.bars):
                h = BAR_MIN + abs(math.sin(t * 4.0 + i * 0.5)) * BAR_MAX * 0.55
                self.cv.coords(b, bx, cy - h, bx + BAR_W, cy + h)
                self.cv.itemconfig(b, fill=C_PROC)

        else:
            for b, bx in self.bars:
                self.cv.coords(b, bx, cy - BAR_MIN, bx + BAR_W, cy + BAR_MIN)
                self.cv.itemconfig(b, fill=C_IDLE)

        if not self.ready:
            self.cv.itemconfig(
                self.spinner,
                text="◜◝◞◟"[self._frame // 4 % 4]
            )

        self.root.after(33, self._tick)

    def _track_app(self):
        try:
            b = frontmost_bundle()
            if b and not any(ex in b.lower() for ex in self.EXCLUDED):
                self.target = b
        except Exception:
            pass
        self.root.after(300, self._track_app)

    def _load_model(self):
        log("Загружаю модель...")
        log(f"Model: {MODEL_REPO}")
        if STRICT_LOCAL_MODE:
            log("Strict local mode: offline-only")
        dummy = np.zeros(SAMPLE_RATE, dtype=np.float32)
        self._transcribe_audio(dummy, prompt=HOTWORDS_PROMPT, final=False)
        log("Готово")
        self.root.after(0, self._on_ready)

    def _on_ready(self):
        self.ready = True
        self.cv.itemconfig(self.spinner, state="hidden")
        self.cv.itemconfig("mic",        state="normal")

    def run(self):
        log("WhisperMac запущен")
        from AppKit import (
            NSApplication,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
        )

        dock_mode = os.getenv("WHISPERMAC_DOCK_MODE", "regular").strip().lower()
        app = NSApplication.sharedApplication()
        if dock_mode == "accessory":
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            log("Dock mode: accessory")
        else:
            app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
            log("Dock mode: regular")

        self.root.mainloop()


if __name__ == "__main__":
    App().run()
