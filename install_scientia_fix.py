#!/usr/bin/env python3
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
TARGET_DIR = Path.cwd().resolve()
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

FILES = (
    "roma_aeterna.py",
    "roma_technology_overhaul.py",
    "roma_voice.py",
    "technologies.lua",
    "technology_tree_100.json",
    "tech_quotes.json",
    "mods/core/technologies.lua",
    "data/quotes/tech_quotes.json",
)


def main() -> None:
    if PACKAGE_DIR == TARGET_DIR:
        print("Файлы уже находятся в текущей папке. Распакуйте архив рядом с проектом")
        print("или запустите установщик из отдельной распакованной папки.")
        return

    backup = TARGET_DIR / f"backup_scientia_{STAMP}"
    copied = 0
    for relative in FILES:
        source = PACKAGE_DIR / relative
        target = TARGET_DIR / relative
        if not source.is_file():
            raise FileNotFoundError(f"В пакете отсутствует {relative}")
        if target.exists():
            backup_target = backup / relative
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1

    print(f"Готово: установлено файлов — {copied}.")
    if backup.exists():
        print(f"Резервная копия: {backup}")
    print("Теперь выполните: python roma_aeterna.py --update-integrity")


if __name__ == "__main__":
    main()
