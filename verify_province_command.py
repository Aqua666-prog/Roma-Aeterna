#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Автономная проверка патча Provinciae et Exercitus 4.1."""
from __future__ import annotations

import ast
import contextlib
import io
import importlib.util
import py_compile
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось создать import spec для {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def parse_lua_routes() -> dict[str, dict]:
    text = (ROOT / "provinces.lua").read_text(encoding="utf-8")
    lines = text.splitlines()
    depth = 0
    current: list[str] | None = None
    records: dict[str, dict] = {}
    for line in lines:
        before = depth
        if before == 1 and re.match(r"\s*\{\s*$", line):
            current = []
        if current is not None:
            current.append(line)
        depth += line.count("{") - line.count("}")
        if current is not None and depth == 1:
            block = "\n".join(current)
            current = None
            name = re.search(r'^\s*name\s*=\s*"([^"]+)"', block, re.M)
            access = re.search(r'^\s*campaign_access\s*=\s*"([^"]+)"', block, re.M)
            land = re.search(r"^\s*land_access\s*=\s*(true|false)", block, re.M)
            sea = re.search(r"^\s*sea_access\s*=\s*(true|false)", block, re.M)
            zone = re.search(r'^\s*sea_zone\s*=\s*"([^"]+)"', block, re.M)
            difficulty = re.search(r"^\s*landing_difficulty\s*=\s*(\d+)", block, re.M)
            if not (name and access and land and sea):
                raise AssertionError("В провинциальном блоке отсутствуют маршрутные поля")
            records[name.group(1)] = {
                "campaign_access": access.group(1),
                "land_access": land.group(1) == "true",
                "sea_access": sea.group(1) == "true",
                "sea_zone": zone.group(1) if zone else None,
                "landing_difficulty": int(difficulty.group(1)) if difficulty else None,
            }
    return records


def main() -> int:
    for filename in (
        "roma_aeterna.py",
        "roma_army_groups.py",
        "roma_navy.py",
        "roma_war_director.py",
        "roma_warfare_ai.py",
    ):
        py_compile.compile(str(ROOT / filename), doraise=True)
    print("[PASS] Компиляция Python-модулей")

    source = (ROOT / "roma_aeterna.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fallback = None
    functions = set()
    sea_zones = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions.add(node.name)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "DEFAULT_PROVINCE_CAMPAIGN_ACCESS":
                fallback = ast.literal_eval(node.value)
    # Последнее присваивание SEA_ZONES является действующим.
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SEA_ZONES" for t in node.targets):
            try:
                sea_zones = ast.literal_eval(node.value)
            except Exception:
                pass
    if fallback is None or sea_zones is None:
        raise AssertionError("Не найдены карта маршрутов или финальный граф морей")
    required = {
        "province_attack_routes", "campaign_provinces", "province_menu",
        "_target_province_overview", "province_sea_reachable", "province_land_reachable",
    }
    if not required <= functions:
        raise AssertionError(f"Не хватает функций: {sorted(required - functions)}")

    routes = parse_lua_routes()
    if set(routes) != set(fallback):
        raise AssertionError("Наборы провинций Python и Lua не совпадают")
    for name, row in routes.items():
        expected = fallback[name]
        for field in ("campaign_access", "land_access", "sea_access", "sea_zone", "landing_difficulty"):
            if row.get(field) != expected.get(field):
                raise AssertionError(f"{name}: поле {field} расходится между Lua и Python")
    counts = Counter(row["campaign_access"] for row in routes.values())
    if counts != Counter({"coastal": 31, "land": 9, "island": 4}):
        raise AssertionError(f"Неожиданное распределение провинций: {counts}")
    for zone in ("atlantic", "britannic", "northern"):
        if zone not in sea_zones:
            raise AssertionError(f"Отсутствует морской театр {zone}")

    def sea_distance(start: str, target: str) -> int | None:
        frontier = {start}
        visited = {start}
        for distance in range(8):
            if target in frontier:
                return distance
            nxt = set()
            for zone in frontier:
                for neighbor in sea_zones.get(zone, {}).get("neighbors", []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        nxt.add(neighbor)
            frontier = nxt
        return None

    if sea_distance("tyrrhenian", "atlantic") != 2 or sea_distance("tyrrhenian", "britannic") != 3:
        raise AssertionError("Северные морские театры соединены с Римом неверной дальностью")
    print(f"[PASS] Карта: {len(routes)} провинции; {dict(counts)}")
    print("[PASS] Атлантический, Британский и Северный морские театры")

    army = load("verify_army_groups", "roma_army_groups.py")

    class General:
        name = "Marcus Testus"
        talent_key = ""

    class Legion:
        def __init__(self, name: str):
            self.name = name
            self.strength = 92
            self.quality = 5
            self.morale = 80
            self.fatigue = 0
            self.general = General()
            self.location = "Roma"

    class Player:
        pass

    player = Player()
    player.turn = 3
    player.legions = [Legion("Legio I")]
    player.aux_units = [{
        "name": "Sagittarii", "army_uid": "AUX-1", "strength": 30,
        "attack": 6, "defense": 4, "morale": 70, "type": "лучники",
    }]
    player.artillery_inventory = {"ballista": 1}
    player.v24 = {"fleet": {
        "squadrons": [{
            "name": "Classis I", "type": "transport", "damage": 0,
            "morale": 75, "zone": "tyrrhenian", "order": "reserve",
        }],
        "sea_zone_control": {"tyrrhenian": 20},
        "landing_preparations": {"tyrrhenian": 10},
        "zone_piracy": {"tyrrhenian": 10},
        "zone_blockade": {},
    }}
    player.gold = 500
    player.grain = 500
    player.artillery_supplies = 30
    player.glory = 0
    player.city_campaigns = {}
    player.provinces = [{"name": "Latium"}]

    ctx = {
        "ARTILLERY_TYPES": {"ballista": {"siege": 10, "power": 5, "support": 4}},
        "FLEET_SQUADRON_TYPES": {"transport": {"cargo": 8, "power": 12, "maneuver": 3, "marines": 0}},
        "province_attack_routes": lambda _player, province: ["sea"] if province.get("campaign_access") == "island" else ["land", "sea"],
        "next_city_to_attack": lambda _player, province: province["cities"][0],
    }
    state = army.auto_organize(player, ctx, force=True)
    group = state["groups"][0]
    if army.group_transport_need(group) != 5:
        raise AssertionError("Неверно рассчитана транспортная нагрузка группы")
    if army._group_transport_capacity(player, group, ctx) != 8:
        raise AssertionError("Неверно рассчитана транспортная вместимость")
    power = army.group_power(player, group, ctx)
    if power["land"] <= 0 or power["naval"] <= 0:
        raise AssertionError("Смешанная группа не получила сухопутную/морскую мощь")
    sicilia = {
        "name": "Sicilia", "campaign_access": "island", "land_access": False,
        "sea_access": True, "sea_zone": "sicilian", "landing_difficulty": 45,
        "cities": [{"name": "Syracusae", "difficulty": 5}],
    }
    snapshot = army.province_operation_snapshot(player, sicilia, ctx)
    candidates = army._province_group_candidates(player, state, ctx, "sea")
    if snapshot["routes"] != ["sea"] or len(candidates) != 1:
        raise AssertionError("Островная операция не нашла пригодную группу")
    print("[PASS] Группа армий, магазинные категории и транспорт флота")
    print("[PASS] Островная цель доступна только морской операцией")

    war_director = load("verify_war_director", "roma_war_director.py")
    warfare = load("verify_warfare_ai", "roma_warfare_ai.py")
    if not hasattr(war_director, "open_province_menu") or not hasattr(warfare, "open_province_menu"):
        raise AssertionError("Военные модули не получили провинциальные отчёты")
    report_player = Player()
    report_player.turn = 1
    report_player.gold = 100
    report_player.grain = 100
    report_player.diplomacy = {}
    report_player.provinces = [{"name": "Latium"}]
    report_player.foreign_warfare = {"last_tick_turn": 1, "wars": {}, "history": []}
    report_player.war_director_3 = {
        "last_tick_turn": 1, "campaigns": [], "occupied_cities": {},
        "lost_provinces": {}, "blockades": {}, "history": [],
    }
    report_ctx = {
        "PROVINCES_DATA": [{
            "name": "Latium", "campaign_access": "coastal",
            "sea_zone": "tyrrhenian", "cities": [{"name": "Roma"}],
        }],
        "SEA_ZONES": {
            "tyrrhenian": {"name": "Mare Tyrrhenum", "provinces": ["Latium"]},
        },
        "pause": lambda *args, **kwargs: None,
    }
    with contextlib.redirect_stdout(io.StringIO()):
        war_director.open_province_menu(report_player, "Latium", report_ctx)
        warfare.open_province_menu(report_player, "Latium", report_ctx)
    print("[PASS] Провинциальные отчёты Bellum Provinciale и Bella Regnorum")

    final_menu_start = source.index("def _main_menu_sections_v2257")
    final_menu_end = source.index("def main_menu", final_menu_start)
    final_menu = source[final_menu_start:final_menu_end]
    for forbidden in (
        'MenuItem("A"', 'MenuItem("B"', 'MenuItem("F"',
        'MenuItem("T"', 'MenuItem("Z"',
    ):
        if forbidden in final_menu:
            raise AssertionError(f"В главном меню осталась старая кнопка: {forbidden}")
    for hidden_binding in ("choose('A')", "choose('B')", "choose('F')", "choose('T')", "choose('Z')"):
        if hidden_binding in source:
            raise AssertionError(f"В Textual-меню осталась старая привязка: {hidden_binding}")
    army_source = (ROOT / "roma_army_groups.py").read_text(encoding="utf-8")
    army_open = army_source[army_source.rindex("def open_menu("):]
    if "_operations_menu(" in army_open or "v25_island_menu" in army_source[army_source.index("def _naval_administration_menu"):army_source.index("def _archive_menu")]:
        raise AssertionError("Старые атаки остаются видимыми в штабе/адмиралтействе")
    print("[PASS] Старые военные кнопки и видимый центр операций удалены")

    print("\nВсе автономные проверки пройдены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
