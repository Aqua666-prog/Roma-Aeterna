#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ROMA AETERNA — безопасное неблокирующее воспроизведение готовой озвучки.

Поддерживаемые структуры файлов:
    audio/tech/<id>.wav
    audio/great_people/<id>.wav
    audio/world_wonders/<id>.wav

Также поддерживается прежнее расположение генератора:
    data/quotes/audio/<category>/<id>.wav

Модуль не является обязательным для запуска игры: если аудиофайл или плеер
отсутствуют, play_voiceover() просто вернёт False и игра продолжит работу.
"""
from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Final

_AUDIO_DIRS: Final[dict[str, str]] = {
    "tech": "tech",
    "technology": "tech",
    "technologies": "tech",
    "great_people": "great_people",
    "great_person": "great_people",
    "people": "great_people",
    "world_wonders": "world_wonders",
    "world_wonder": "world_wonders",
    "wonders": "world_wonders",
    "wonder": "world_wonders",
}

_BASE_DIR = Path(__file__).resolve().parent
_AUDIO_ROOTS: Final[tuple[Path, ...]] = (
    _BASE_DIR / "data" / "quotes" / "audio_full",
    _BASE_DIR / "audio",
    _BASE_DIR / "data" / "quotes" / "audio",
)
_LOCK = threading.RLock()
_PROCESS: subprocess.Popen | None = None
_BACKEND: str | None = None
_WARNED_NO_PLAYER = False


def _safe_id(value: object) -> str:
    """Оставляет только безопасное имя файла без возможности выйти из audio/."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    # Идентификаторы игры состоят из букв, цифр, подчёркиваний и дефисов.
    cleaned = "".join(ch for ch in raw if ch.isalnum() or ch in {"_", "-"})
    return cleaned


def _voiceover_candidates(category: str, entry_id: object) -> list[Path]:
    safe_id = _safe_id(entry_id)
    if not safe_id:
        return []

    candidates: list[Path] = []
    for root in _AUDIO_ROOTS:
        resolved_root = root.resolve()

        # audio_full: все файлы лежат прямо в корне
        if resolved_root.name == "audio_full":
            for ext in ("mp3","wav"):
                candidates.append((resolved_root / f"{safe_id}.{ext}").resolve())
            continue

        folder = _AUDIO_DIRS.get(str(category or "").strip().lower())
        if not folder:
            continue
        for ext in ("mp3","wav"):
            candidates.append((resolved_root / folder / f"{safe_id}.{ext}").resolve())
    return candidates


def voiceover_path(category: str, entry_id: object) -> Path | None:
    """Возвращает существующий WAV или MP3."""
    candidates = _voiceover_candidates(category, entry_id)
    for path in candidates:
        if path.is_file() and path.stat().st_size > 44:
            return path
    # Для диагностики возвращаем предпочтительный путь.
    if candidates:
        for p in candidates:
            if p.suffix.lower() == ".mp3":
                return p
        return candidates[0]
    return None


def _detect_backend() -> str | None:
    """Выбирает первый доступный плеер без обязательных Python-зависимостей."""
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND or None

    if os.name == "nt":
        try:
            import winsound  # noqa: F401
        except ImportError:
            pass
        else:
            _BACKEND = "winsound"
            return _BACKEND

    candidates = (
        "termux-media-player",  # Android + Termux:API
        "mpv",                  # лучший универсальный вариант для Termux/Linux
        "ffplay",               # входит в ffmpeg
        "paplay",               # PulseAudio
        "aplay",                # ALSA
        "play",                 # SoX
        "afplay",               # macOS
    )
    for command in candidates:
        if shutil.which(command):
            _BACKEND = command
            return _BACKEND

    _BACKEND = ""
    return None


def available_backend() -> str | None:
    """Возвращает имя найденного аудиоплеера или None."""
    return _detect_backend()


def stop_voiceover() -> None:
    """Останавливает текущую реплику, не затрагивая игровую логику."""
    global _PROCESS
    with _LOCK:
        backend = _detect_backend()

        if backend == "winsound":
            try:
                import winsound
                winsound.PlaySound(None, 0)
            except Exception:
                pass

        if backend == "termux-media-player":
            try:
                subprocess.run(
                    ["termux-media-player", "stop"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=2,
                    check=False,
                )
            except Exception:
                pass

        proc = _PROCESS
        _PROCESS = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def _command_for(backend: str, path: Path, volume: int) -> list[str] | None:
    volume = max(0, min(100, int(volume)))
    if backend == "termux-media-player":
        return ["termux-media-player", "play", str(path)]
    if backend == "mpv":
        return [
            "mpv", "--no-video", "--really-quiet", "--no-terminal",
            f"--volume={volume}", str(path),
        ]
    if backend == "ffplay":
        return [
            "ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
            "-volume", str(volume), str(path),
        ]
    if backend == "paplay":
        # PulseAudio использует диапазон 0..65536.
        pa_volume = int(round(volume / 100 * 65536))
        return ["paplay", f"--volume={pa_volume}", str(path)]
    if backend == "aplay":
        return ["aplay", "-q", str(path)]
    if backend == "play":
        return ["play", "-q", str(path), "vol", f"{volume / 100:.2f}"]
    if backend == "afplay":
        return ["afplay", "-v", f"{volume / 100:.2f}", str(path)]
    return None


def play_voiceover(
    category: str,
    entry_id: object,
    *,
    enabled: bool = True,
    volume: int = 85,
    interrupt: bool = True,
) -> bool:
    """Неблокирующе запускает готовый WAV и возвращает успех запуска.

    Любая проблема — отсутствие файла, плеера или системная ошибка — считается
    мягкой: функция возвращает False, а игра продолжает работу.
    """
    global _PROCESS, _WARNED_NO_PLAYER

    if not enabled:
        return False
    path = voiceover_path(category, entry_id)
    if path is None or not path.is_file() or path.stat().st_size <= 44:
        return False

    backend = _detect_backend()
    if not backend:
        _WARNED_NO_PLAYER = True
        return False

    with _LOCK:
        if interrupt:
            stop_voiceover()

        try:
            if backend == "winsound":
                import winsound
                winsound.PlaySound(
                    str(path),
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
                return True

            command = _command_for(backend, path, volume)
            if not command:
                return False

            # start_new_session не даёт Ctrl+C в игре случайно убить дочерний
            # плеер вместе с терминалом; stop_voiceover() завершает его явно.
            _PROCESS = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=(os.name != "nt"),
            )
            return True
        except (OSError, ValueError, subprocess.SubprocessError):
            _PROCESS = None
            return False


def diagnostics() -> dict[str, object]:
    """Краткая диагностика доступных каталогов и аудиоплеера."""
    def count_unique(folder: str) -> int:
        names: set[str] = set()
        for root in _AUDIO_ROOTS:
            directory = root / folder
            if directory.is_dir():
                names.update(path.name for path in directory.glob("*.wav"))
                names.update(path.name for path in directory.glob("*.mp3"))
        return len(names)

    existing_roots = [str(root) for root in _AUDIO_ROOTS if root.is_dir()]
    return {
        "audio_root": existing_roots[0] if existing_roots else str(_AUDIO_ROOTS[0]),
        "audio_roots": [str(root) for root in _AUDIO_ROOTS],
        "audio_root_exists": bool(existing_roots),
        "backend": _detect_backend(),
        "tech_files": count_unique("tech"),
        "great_people_files": count_unique("great_people"),
        "world_wonders_files": count_unique("world_wonders"),
    }


atexit.register(stop_voiceover)

__all__ = [
    "available_backend",
    "diagnostics",
    "play_voiceover",
    "stop_voiceover",
    "voiceover_path",
]