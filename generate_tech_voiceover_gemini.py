#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Озвучка технологий Roma Aeterna через Gemini TTS.

Источник: <корень игры>/tech_quotes.json
Вывод:   <корень игры>/data/quotes/audio_full/<id>.mp3
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Any

try:
    from reference_formatter import format_source_reference
except ImportError as exc:
    raise SystemExit(
        "Не найден reference_formatter.py. Положи его рядом с генератором."
    ) from exc

MODEL_DEFAULT = "gemini-3.1-flash-tts-preview"
VOICE_DEFAULT = "Orus"
RATE = 24_000
CHANNELS = 1
SAMPLE_WIDTH = 2

BUILTIN_STYLE = """Read only in Russian.

Audio profile:
An educated Roman historian and former senator, a man about 60–70 years old.
His voice is deep, mature, calm, warm, natural, and authoritative.

Scene:
A quiet archival chamber in ancient Rome. He is reading an official chronicle
for preservation in the state archives.

Director's notes:
Use clear Russian diction, stable breathing, a moderate unhurried pace, and
natural pauses only where punctuation requires them. Keep the delivery
restrained and dignified. Pronounce all personal names, place names, titles,
Latin words, numerals, and source references carefully and naturally.

Do not whisper, rasp, tremble, shout, overact, sing, or imitate a damaged
recording. Do not add background sounds, music, room echo, distortion, clicks,
mouth noises, filler words, introductions, conclusions, or extra phrases.
Read the transcript exactly as written. Do not translate, paraphrase, repeat,
omit, or add words.

Begin speaking with the first word after the next blank line. Stop after the
last word. Do not speak these instructions."""


def clean(value: object) -> str:
    return str(value or "").replace("+", "").strip()


def find_root(start: Path) -> Path:
    for path in (start, *start.parents):
        if (path / "tech_quotes.json").is_file():
            return path
        if (path / "roma_aeterna.py").is_file():
            return path
    return start


def load_entries(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Не найден файл: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Ошибка JSON в {path}: {exc}") from exc
    if not isinstance(data, list):
        raise SystemExit("Корнем tech_quotes.json должен быть JSON-массив.")
    return [item for item in data if isinstance(item, dict)]


def prepare_text(entry: dict[str, Any]) -> tuple[str, str]:
    quote = clean(entry.get("tts_quote") or entry.get("voice_quote") or entry.get("quote"))
    source = clean(entry.get("source"))
    spoken_source = format_source_reference(source)
    quote = quote.strip(" «»\"\t\r\n")
    if quote and quote[-1] not in ".!?…":
        quote += "."
    text = f"{quote}\n\n{spoken_source}" if spoken_source else quote
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, spoken_source


def validate(entries: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, 1):
        entry_id = clean(entry.get("id"))
        if not entry_id:
            errors.append(f"Запись {index}: отсутствует id")
            continue
        if entry_id in seen:
            errors.append(f"Повтор id: {entry_id}")
        seen.add(entry_id)
        if "tts_source" in entry:
            errors.append(f"{entry_id}: поле tts_source должно быть удалено")
        if not clean(entry.get("quote")):
            errors.append(f"{entry_id}: отсутствует quote")
        if not clean(entry.get("source")):
            errors.append(f"{entry_id}: отсутствует source")
        if "+" in json.dumps(entry, ensure_ascii=False):
            errors.append(f"{entry_id}: остались старые знаки +")
        try:
            _, spoken = prepare_text(entry)
            if clean(entry.get("source")) and not spoken:
                errors.append(f"{entry_id}: не получена устная ссылка")
        except Exception as exc:
            errors.append(f"{entry_id}: ссылка не разобрана: {exc}")
    return errors


def read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def get_api_key(root: Path, script_dir: Path) -> str:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    for path in dict.fromkeys((root / ".env", script_dir / ".env")):
        values = read_env(path)
        for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            value = values.get(name, "").strip()
            if value:
                return value
    raise SystemExit(
        "Не найден API-ключ. Создай в корне игры файл .env:\n"
        "GEMINI_API_KEY=твой_ключ\n\n"
        "Файл .env не публикуй на GitHub."
    )


def get_style(root: Path, requested: str | None) -> tuple[str, Path | None]:
    if requested:
        path = Path(requested).expanduser()
        if not path.is_absolute():
            path = root / path
        if not path.is_file():
            raise SystemExit(f"Не найден файл промпта: {path}")
        return path.read_text(encoding="utf-8").strip(), path
    path = root / "gemini_voice_prompt.txt"
    if path.is_file() and path.stat().st_size:
        return path.read_text(encoding="utf-8").strip(), path
    return BUILTIN_STYLE, None


def make_prompt(style: str, transcript: str) -> str:
    return f"{style.rstrip()}\n\n{transcript.strip()}"


def make_client(api_key: str):
    try:
        from google import genai  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Не установлен google-genai. Выполни:\n"
            "python -m pip install -U google-genai"
        ) from exc
    client = genai.Client(api_key=api_key)
    if not hasattr(client, "interactions"):
        raise SystemExit(
            "Старая версия google-genai. Обнови:\n"
            "python -m pip install -U google-genai"
        )
    return client


def decode_audio(interaction: Any) -> bytes:
    audio = getattr(interaction, "output_audio", None)
    data = getattr(audio, "data", None) if audio is not None else None
    if data is None:
        raise RuntimeError("Gemini не вернул аудио")
    if isinstance(data, str):
        result = base64.b64decode(data, validate=True)
    elif isinstance(data, (bytes, bytearray, memoryview)):
        raw = bytes(data)
        try:
            result = base64.b64decode(raw, validate=True)
        except Exception:
            result = raw
    else:
        raise RuntimeError(f"Неизвестный тип аудио: {type(data).__name__}")
    if len(result) < 100:
        raise RuntimeError("Gemini вернул слишком короткое аудио")
    return result


def write_wav(path: Path, audio: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if audio.startswith(b"RIFF") and audio[8:12] == b"WAVE":
        path.write_bytes(audio)
        return
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(RATE)
        wav.writeframes(audio)


def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise SystemExit(
            "Для MP3 нужен ffmpeg. В Termux выполни:\n"
            "pkg install ffmpeg\n\n"
            "Или используй --format wav."
        )
    return path


def wav_to_mp3(ffmpeg: str, source: Path, target: Path, bitrate: str) -> None:
    result = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
         "-vn", "-codec:a", "libmp3lame", "-b:a", bitrate, str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        message = (result.stderr or result.stdout or "неизвестная ошибка").strip()
        raise RuntimeError(f"ffmpeg: {message}")


def existing(out_dir: Path, entry_id: str) -> list[Path]:
    found: list[Path] = []
    for ext, minimum in (("mp3", 128), ("wav", 44)):
        path = out_dir / f"{entry_id}.{ext}"
        if path.is_file() and path.stat().st_size > minimum:
            found.append(path)
    return found


def generate_pcm(client: Any, model: str, voice: str, prompt: str) -> bytes:
    interaction = client.interactions.create(
        model=model,
        input=prompt,
        response_format={"type": "audio"},
        generation_config={"speech_config": [{"voice": voice}]},
    )
    return decode_audio(interaction)


def synthesize(
    client: Any,
    entry: dict[str, Any],
    out_dir: Path,
    style: str,
    model: str,
    voice: str,
    output_format: str,
    bitrate: str,
    overwrite: bool,
    retries: int,
    ffmpeg: str | None,
) -> tuple[str, str]:
    entry_id = clean(entry.get("id"))
    final = out_dir / f"{entry_id}.{output_format}"
    other = out_dir / f"{entry_id}.{'wav' if output_format == 'mp3' else 'mp3'}"
    found = existing(out_dir, entry_id)
    if found and not overwrite:
        return entry_id, "пропущено: " + ", ".join(p.name for p in found)

    transcript, _ = prepare_text(entry)
    prompt = make_prompt(style, transcript)
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_wav = out_dir / f".{entry_id}.gemini.tmp.wav"
    temp_final = out_dir / f".{entry_id}.gemini.tmp.{output_format}"
    last_error: Exception | None = None

    for attempt in range(1, retries + 1):
        try:
            temp_wav.unlink(missing_ok=True)
            temp_final.unlink(missing_ok=True)
            audio = generate_pcm(client, model, voice, prompt)
            write_wav(temp_wav, audio)
            if output_format == "mp3":
                if ffmpeg is None:
                    raise RuntimeError("ffmpeg не найден")
                wav_to_mp3(ffmpeg, temp_wav, temp_final, bitrate)
                if not temp_final.is_file() or temp_final.stat().st_size < 128:
                    raise RuntimeError("создан пустой MP3")
                temp_final.replace(final)
                temp_wav.unlink(missing_ok=True)
            else:
                if not temp_wav.is_file() or temp_wav.stat().st_size <= 44:
                    raise RuntimeError("создан пустой WAV")
                temp_wav.replace(final)
            other.unlink(missing_ok=True)
            return entry_id, f"готово: {final.name}"
        except Exception as exc:
            last_error = exc
            temp_wav.unlink(missing_ok=True)
            temp_final.unlink(missing_ok=True)
            if attempt < retries:
                wait = min(30, 3 * (2 ** (attempt - 1)))
                print(f"    попытка {attempt}/{retries}: {exc}")
                print(f"    повтор через {wait} с...")
                time.sleep(wait)
    return entry_id, f"ошибка: {last_error}"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Gemini TTS для технологий Roma Aeterna")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--check", action="store_true")
    p.add_argument("--preview", type=int, metavar="N")
    p.add_argument("--only", nargs="+", metavar="ID")
    p.add_argument("--model", default=MODEL_DEFAULT)
    p.add_argument("--voice", default=VOICE_DEFAULT)
    p.add_argument("--format", choices=("mp3", "wav"), default="mp3", dest="output_format")
    p.add_argument("--bitrate", default="128k")
    p.add_argument("--prompt-file", metavar="PATH")
    p.add_argument("--retries", type=int, default=4)
    p.add_argument("--delay", type=float, default=1.0)
    return p


def main() -> int:
    args = parser().parse_args()
    if args.retries < 1:
        raise SystemExit("--retries должен быть не меньше 1")
    if args.delay < 0:
        raise SystemExit("--delay не может быть отрицательным")

    script_dir = Path(__file__).resolve().parent
    root = find_root(script_dir)
    json_path = root / "tech_quotes.json"
    out_dir = root / "data" / "quotes" / "audio_full"
    entries = load_entries(json_path)
    errors = validate(entries)

    print(f"JSON: {json_path}")
    print(f"Аудио: {out_dir}")
    print(f"Модель: {args.model}")
    print(f"Голос: {args.voice}")
    print(f"Формат: {args.output_format.upper()}")
    print(f"Технологий: {len(entries)}")

    if errors:
        for error in errors:
            print(f"ОШИБКА: {error}")
        return 1

    selected = entries
    if args.only:
        wanted = set(args.only)
        selected = [e for e in entries if clean(e.get("id")) in wanted]
        missing = wanted - {clean(e.get("id")) for e in selected}
        if missing:
            print("Не найдены ID: " + ", ".join(sorted(missing)))
            return 2

    style, style_path = get_style(root, args.prompt_file)
    print(f"Промпт: {style_path or 'встроенный'}")

    if args.check:
        print("Проверка пройдена.")
        return 0

    if args.preview is not None:
        if args.preview < 1:
            raise SystemExit("--preview должен быть не меньше 1")
        for entry in selected[:args.preview]:
            text, spoken = prepare_text(entry)
            print(f"\n[{entry['id']}]\nИсточник на экране: {entry['source']}")
            print(f"Источник вслух: {spoken}\nТекст диктора:\n{text}")
            print(f"\nПолный запрос:\n{make_prompt(style, text)}")
        return 0

    ffmpeg = ffmpeg_path() if args.output_format == "mp3" else None
    client = make_client(get_api_key(root, script_dir))
    transcript_log: list[str] = []
    generated = skipped = failed = 0

    for index, entry in enumerate(selected, 1):
        entry_id = clean(entry.get("id"))
        text, _ = prepare_text(entry)
        transcript_log.append(f"{entry_id}\t{text.replace(chr(10), ' / ')}")
        print(f"[{index}/{len(selected)}] {entry_id}")
        _, status = synthesize(
            client, entry, out_dir, style, args.model, args.voice,
            args.output_format, args.bitrate, args.overwrite,
            args.retries, ffmpeg,
        )
        print(f"    {status}")
        if status.startswith("ошибка"):
            failed += 1
        elif status.startswith("пропущено"):
            skipped += 1
        else:
            generated += 1
            if args.delay and index < len(selected):
                time.sleep(args.delay)

    (out_dir / "_tech_transcript_gemini.txt").write_text(
        "\n".join(transcript_log) + "\n", encoding="utf-8"
    )
    print(f"\nГотово. Создано: {generated}. Пропущено: {skipped}. Ошибок: {failed}.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
