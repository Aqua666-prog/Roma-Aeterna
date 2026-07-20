#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install Scientia et Ars into an existing Roma Aeterna project."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import py_compile
import shutil
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent

ROOT_FILES = (
    "roma_aeterna.py",
    "roma_buildings.py",
    "roma_resources.py",
    "roma_technology_overhaul.py",
    "technologies.lua",
)


def backup_and_copy(source: Path, destination: Path, stamp: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        backup = destination.with_name(destination.name + f".bak_scientia_{stamp}")
        shutil.copy2(destination, backup)
        print(f"  backup: {backup}")
    shutil.copy2(source, destination)
    print(f"  installed: {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install the 100-technology Scientia et Ars overhaul."
    )
    parser.add_argument("project", type=Path, help="Roma Aeterna project directory")
    args = parser.parse_args()
    project = args.project.expanduser().resolve()
    if not (project / "roma_aeterna.py").is_file():
        parser.error(f"{project} does not contain roma_aeterna.py")

    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    for name in ROOT_FILES:
        source = PACKAGE_DIR / name
        if not source.is_file():
            raise FileNotFoundError(source)
        backup_and_copy(source, project / name, stamp)

    quote_source = PACKAGE_DIR / "tech_quotes.json"
    quote_destination = project / "data" / "quotes" / "tech_quotes.json"
    backup_and_copy(quote_source, quote_destination, stamp)

    # Fast post-install validation without starting the game.
    for name in ("roma_aeterna.py", "roma_buildings.py", "roma_resources.py", "roma_technology_overhaul.py"):
        py_compile.compile(str(project / name), doraise=True)

    sys.path.insert(0, str(project))
    import roma_technology_overhaul as overhaul
    errors = overhaul.validate()
    if errors:
        raise RuntimeError("; ".join(errors))

    quote_rows = json.loads(quote_destination.read_text(encoding="utf-8"))
    if len(quote_rows) != 100:
        raise RuntimeError(f"tech_quotes.json: expected 100 entries, got {len(quote_rows)}")

    print("\nScientia et Ars installed successfully.")
    print("The old 75 technical IDs are preserved; existing saves remain compatible.")
    print("Start the game normally or run: python roma_aeterna.py --self-test")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
