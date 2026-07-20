#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор MP3-озвучки технологий Roma Aeterna через Edge TTS.

Единственный источник данных:
    <корень игры>/tech_quotes.json

На экране хранится компактная ссылка:
    Цицерон. Об ораторе. X. 2. 195.

Перед синтезом она автоматически превращается в устную:
    Цицерон. Об ораторе. Книга десятая. Глава вторая.
    Параграф сто девяносто пятый.

Файлы создаются здесь:
    <корень игры>/data/quotes/audio_full/<id>.mp3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

try:
    from reference_formatter import format_source_reference
except ImportError as exc:
    raise SystemExit(
        "Не найден reference_formatter.py. Положи его рядом с генератором."
    ) from exc

DEFAULT_VOICE = "ru-RU-DmitryNeural"
DEFAULT_RATE = "-8%"
DEFAULT_VOLUME = "+0%"
DEFAULT_PITCH = "+0Hz"


def find_project_root(script_dir: Path) -> Path:
    """Ищет корень игры вверх от расположения генератора."""
    candidates = [script_dir, *script_dir.parents]
    for candidate in candidates:
        if (candidate / "tech_quotes.json").is_file():
            return candidate
        if (candidate / "roma_aeterna.py").is_file():
            return candidate
    return script_dir


def strip_legacy_marks(value: object) -> str:
    return str(value or "").replace("+", "").strip()


def read_entries(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Не найден канонический файл: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Ошибка JSON в {path}: {exc}")
    if not isinstance(payload, list):
        raise SystemExit("Корнем tech_quotes.json должен быть JSON-массив.")
    return [entry for entry in payload if isinstance(entry, dict)]


def entry_text(entry: dict) -> tuple[str, str]:
    quote = strip_legacy_marks(entry.get("tts_quote") or entry.get("voice_quote") or entry.get("quote"))
    source = strip_legacy_marks(entry.get("source"))
    spoken_source = format_source_reference(source)
    quote = quote.strip(" «»\"\t\r\n")
    if quote and quote[-1] not in ".!?…":
        quote += "."
    text = f"{quote} ... {spoken_source}" if spoken_source else quote
    text = re.sub(r"\s+", " ", text).strip()
    return text, spoken_source


def validate(entries: list[dict]) -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    for index, entry in enumerate(entries, 1):
        entry_id = strip_legacy_marks(entry.get("id"))
        if not entry_id:
            errors.append(f"Запись {index}: отсутствует id")
            continue
        if entry_id in ids:
            errors.append(f"Повтор id: {entry_id}")
        ids.add(entry_id)
        if "tts_source" in entry:
            errors.append(f"{entry_id}: поле tts_source должно быть удалено")
        if not strip_legacy_marks(entry.get("quote")):
            errors.append(f"{entry_id}: отсутствует quote")
        source = strip_legacy_marks(entry.get("source"))
        if not source:
            errors.append(f"{entry_id}: отсутствует source")
        if "+" in json.dumps(entry, ensure_ascii=False):
            errors.append(f"{entry_id}: остались старые знаки +")
        try:
            _text, spoken = entry_text(entry)
        except Exception as exc:
            errors.append(f"{entry_id}: ссылка не разобрана: {exc}")
            continue
        if source and not spoken:
            errors.append(f"{entry_id}: не получена устная ссылка")
    return errors


def import_edge_tts():
    try:
        import edge_tts  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Не установлен edge-tts. Выполни:\n"
            "pip install edge-tts --break-system-packages"
        ) from exc
    return edge_tts


async def synthesize_one(
    entry: dict,
    out_dir: Path,
    *,
    voice: str,
    rate: str,
    volume: str,
    pitch: str,
    overwrite: bool,
    retries: int = 3,
) -> tuple[str, str]:
    entry_id = strip_legacy_marks(entry.get("id"))
    out_path = out_dir / f"{entry_id}.mp3"
    if out_path.is_file() and out_path.stat().st_size > 0 and not overwrite:
        return entry_id, "пропущено"

    edge_tts = import_edge_tts()
    text, _spoken_source = entry_text(entry)
    out_dir.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            communicator = edge_tts.Communicate(
                text,
                voice,
                rate=rate,
                volume=volume,
                pitch=pitch,
            )
            await communicator.save(str(out_path))
            if not out_path.is_file() or out_path.stat().st_size == 0:
                raise RuntimeError("создан пустой MP3")
            return entry_id, "готово"
        except Exception as exc:
            last_error = exc
            if out_path.exists():
                out_path.unlink(missing_ok=True)
            if attempt < retries:
                await asyncio.sleep(attempt * 2)
    return entry_id, f"ошибка: {last_error}"


async def async_main(args: argparse.Namespace) -> int:
    script_dir = Path(__file__).resolve().parent
    root = find_project_root(script_dir)
    json_path = root / "tech_quotes.json"
    legacy_path = root / "data" / "quotes" / "tech_quotes.json"
    out_dir = root / "data" / "quotes" / "audio_full"

    entries = read_entries(json_path)
    errors = validate(entries)
    print(f"Канонический JSON: {json_path}")
    print(f"Каталог MP3: {out_dir}")
    if legacy_path.is_file():
        print(f"ВНИМАНИЕ: старая копия игнорируется и её можно удалить: {legacy_path}")
    print(f"Технологий: {len(entries)}")
    if errors:
        for error in errors:
            print(f"ОШИБКА: {error}")
        return 1

    if args.check:
        print("Проверка пройдена: один source, tts_source отсутствует.")
        return 0

    selected = entries
    if args.only:
        wanted = set(args.only)
        selected = [entry for entry in entries if strip_legacy_marks(entry.get("id")) in wanted]
        missing = wanted - {strip_legacy_marks(entry.get("id")) for entry in selected}
        if missing:
            print("Не найдены ID: " + ", ".join(sorted(missing)))
            return 2

    if args.preview:
        for entry in selected[: args.preview]:
            text, spoken = entry_text(entry)
            print(f"\n[{entry['id']}]\nЭкран: {entry['source']}\nОзвучка источника: {spoken}\nПолный текст: {text}")
        return 0

    transcript: list[str] = []
    failed = 0
    for index, entry in enumerate(selected, 1):
        entry_id = strip_legacy_marks(entry.get("id"))
        text, _ = entry_text(entry)
        transcript.append(f"{entry_id}\t{text}")
        print(f"[{index}/{len(selected)}] {entry_id}")
        _entry_id, status = await synthesize_one(
            entry,
            out_dir,
            voice=args.voice,
            rate=args.rate,
            volume=args.volume,
            pitch=args.pitch,
            overwrite=args.overwrite,
        )
        print(f"    {status}")
        if status.startswith("ошибка"):
            failed += 1

    (out_dir / "_tech_transcript.txt").write_text(
        "\n".join(transcript) + "\n", encoding="utf-8"
    )
    print(f"Завершено. Ошибок: {failed}.")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MP3-озвучка технологий Roma Aeterna")
    parser.add_argument("--overwrite", action="store_true", help="перезаписать существующие MP3")
    parser.add_argument("--check", action="store_true", help="только проверить JSON")
    parser.add_argument("--preview", type=int, metavar="N", help="показать N подготовленных реплик")
    parser.add_argument("--only", nargs="+", metavar="ID", help="озвучить только указанные ID")
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--rate", default=DEFAULT_RATE)
    parser.add_argument("--volume", default=DEFAULT_VOLUME)
    parser.add_argument("--pitch", default=DEFAULT_PITCH)
    return parser


def main() -> int:
    return asyncio.run(async_main(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
