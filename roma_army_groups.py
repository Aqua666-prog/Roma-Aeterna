#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna 3.0 — EXERCITUS ROMANUS.

Оперативные армии Рима объединяют легионы, ауксилии, артиллерию и морские
эскадры. Модуль не импортирует основной файл и работает через ``player`` и
``ctx``. Старые сохранения мигрируют автоматически: существующие легионы,
ауксилии, артиллерия и корабли распределяются по армиям без удаления исходных
объектов.

Публичный контракт:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None)
    auto_organize(player, ctx=None, force=False)
    group_power(player, group_or_id, ctx=None)
    available_groups(player, ctx=None, naval=False)
    best_group(player, ctx=None, naval=False, location=None)
    apply_battle_result(player, group_or_id, won, margin, ctx=None, naval=False)
    open_menu(player, ctx=None)
"""
from __future__ import annotations

import random
import re
import textwrap
import uuid
from typing import Any

MODULE_VERSION = "3.0.0-exercitus"
SCHEMA_VERSION = 1
MAX_HISTORY = 300
MAX_LEGIONS_PER_GROUP = 4
MAX_AUXILIA_PER_GROUP = 6


def _i(value: Any, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        value = default
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _clamp(value: Any, low: int = 0, high: int = 100, default: int = 0) -> int:
    return _i(value, default, low, high)


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _ctx(ctx: dict | None) -> dict:
    return ctx if isinstance(ctx, dict) else {}


def _plain(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r"\[[^\]]+\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class UI:
    def __init__(self, ctx: dict | None = None):
        self.ctx = _ctx(ctx)
        self.C = self.ctx.get("C")

    def color(self, text: Any, color: str = "WHITE", bold: bool = False) -> str:
        fn = self.ctx.get("clr")
        if callable(fn) and self.C is not None:
            try:
                code = getattr(self.C, color, "")
                if bold:
                    code = getattr(self.C, "BOLD", "") + code
                return fn(str(text), code)
            except Exception:
                pass
        return str(text)

    def screen(self) -> None:
        fn = self.ctx.get("rui_screen_start") or self.ctx.get("clear")
        if callable(fn):
            try:
                fn(); return
            except Exception:
                pass

    def header(self, title: str, icon: str = "🦅", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try:
                fn(title, icon, getattr(self.C, "RED", ""), subtitle); return
            except TypeError:
                try:
                    fn(title, icon, getattr(self.C, "RED", "")); return
                except Exception:
                    pass
            except Exception:
                pass
        print(self.color(f"\n{'═' * 76}\n  {icon} {title}\n{'═' * 76}", "RED", True))
        if subtitle:
            self.wrap(subtitle, "GRAY")

    def section(self, title: str, color: str = "GOLD") -> None:
        fn = self.ctx.get("rui_section")
        if callable(fn) and self.C is not None:
            try:
                fn(title, getattr(self.C, color, "")); return
            except Exception:
                pass
        print(self.color(f"\n  ── {title} ──", color, True))

    def info(self, text: Any, color: str = "WHITE") -> None:
        fn = self.ctx.get("rui_info")
        if callable(fn) and self.C is not None:
            try:
                fn(str(text), getattr(self.C, color, "")); return
            except Exception:
                pass
        print(self.color("  " + str(text), color))

    def wrap(self, text: Any, color: str = "WHITE") -> None:
        fn = self.ctx.get("ui_wrap")
        if callable(fn) and self.C is not None:
            try:
                fn(str(text), color=getattr(self.C, color, "")); return
            except Exception:
                pass
        for line in textwrap.wrap(str(text), width=76, break_long_words=False):
            print(self.color("  " + line, color))

    def table(self, title: str, headers: list[str], rows: list[tuple], color: str = "CYAN") -> None:
        fn = self.ctx.get("rui_table")
        if callable(fn) and self.C is not None:
            try:
                fn(title, headers, rows, color=getattr(self.C, color, "")); return
            except Exception:
                pass
        self.section(title, color)
        widths = [len(_plain(h)) for h in headers]
        clean_rows: list[list[str]] = []
        for row in rows:
            clean = [_plain(v) for v in row]
            clean_rows.append(clean)
            for i, value in enumerate(clean[:len(widths)]):
                widths[i] = min(30, max(widths[i], len(value)))
        print("  " + " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
        print("  " + "-+-".join("-" * w for w in widths))
        for row in clean_rows:
            print("  " + " | ".join(row[i][:widths[i]].ljust(widths[i]) for i in range(len(headers))))

    def choice(self, prompt: str, valid: list[str]) -> str:
        valid = [str(x).upper() for x in valid]
        fn = self.ctx.get("read_choice")
        if callable(fn):
            try:
                return str(fn(self.color(prompt, "CYAN"), valid)).upper()
            except Exception:
                pass
        while True:
            answer = input(prompt).strip().upper()
            if answer in valid:
                return answer
            print("  Допустимо: " + ", ".join(valid))

    def pause(self, text: str = "Нажмите Enter, чтобы продолжить...") -> None:
        fn = self.ctx.get("rui_pause") or self.ctx.get("pause")
        if callable(fn):
            try:
                fn(text); return
            except TypeError:
                try:
                    fn(); return
                except Exception:
                    pass
            except Exception:
                pass
        input("\n  " + text)


DOCTRINES: dict[str, dict[str, Any]] = {
    "balanced": {
        "name": "Ars Consularis",
        "desc": "Сбалансированное соединение для полевой войны, осад и охраны коммуникаций.",
        "land": 1.00, "siege": 1.00, "naval": 1.00, "mobility": 1.00, "supply": 1.00,
    },
    "offensive": {
        "name": "Impetus Romanus",
        "desc": "Решительный поиск генерального сражения и быстрый штурм.",
        "land": 1.13, "siege": 1.08, "naval": 0.96, "mobility": 1.05, "supply": 0.90,
    },
    "defensive": {
        "name": "Cunctatio Fabiana",
        "desc": "Уклонение от невыгодного боя, укреплённые лагеря и изматывание врага.",
        "land": 1.08, "siege": 0.92, "naval": 1.00, "mobility": 0.92, "supply": 1.12,
    },
    "siege": {
        "name": "Oppugnatio",
        "desc": "Инженерные части, артиллерия и систематическое разрушение укреплений.",
        "land": 0.96, "siege": 1.28, "naval": 0.92, "mobility": 0.88, "supply": 0.95,
    },
    "maritime": {
        "name": "Mare Nostrum",
        "desc": "Флот, морская пехота, конвои и высадка на вражеском берегу.",
        "land": 0.94, "siege": 1.02, "naval": 1.25, "mobility": 1.08, "supply": 1.04,
    },
    "mobile": {
        "name": "Celeritas",
        "desc": "Лёгкие ауксилии, разведка, быстрый марш и перехват вражеских колонн.",
        "land": 1.02, "siege": 0.84, "naval": 1.00, "mobility": 1.25, "supply": 0.94,
    },
}

ROMAN_GROUP_NAMES = [
    "Exercitus Consularis", "Exercitus Italiae", "Exercitus Africae",
    "Exercitus Orientis", "Exercitus Galliarum", "Exercitus Maritimus",
    "Exercitus Praetorius", "Exercitus Danubianus", "Exercitus Hispanicus",
]


def _record(player: Any, state: dict, title: str, text: str, ctx: dict) -> None:
    item = {"turn": _i(getattr(player, "turn", 1), 1), "title": title, "text": text}
    state.setdefault("history", []).append(item)
    state["history"] = state["history"][-MAX_HISTORY:]
    log = ctx.get("log_event")
    if callable(log):
        try:
            log(player, f"{title}: {text}")
        except Exception:
            pass
    annales = ctx.get("ANNALES")
    if annales is not None and hasattr(annales, "record_event"):
        try:
            annales.record_event(
                player, category="military", title=title, text=text,
                reason="Реорганизация и действия оперативных армий Рима.",
                severity=2, data={"system": "exercitus_romanus"},
            )
        except Exception:
            pass


def _fleet(player: Any, ctx: dict) -> dict:
    # Roma 3.0.1: флот имеет отдельное ядро. Старый v24 используется только
    # как совместимый alias во время миграции сохранений.
    navy = ctx.get("NAVY")
    if navy is not None and hasattr(navy, "ensure_state"):
        try:
            return _dict(navy.ensure_state(player, ctx))
        except Exception:
            pass
    ensure = ctx.get("ensure_v24_state")
    if callable(ensure):
        try:
            ensure(player)
        except Exception:
            pass
    return _dict(_dict(getattr(player, "v24", {})).get("fleet"))


def _ensure_aux_ids(player: Any) -> None:
    for unit in _list(getattr(player, "aux_units", [])):
        if isinstance(unit, dict):
            unit.setdefault("army_uid", "AUX-" + uuid.uuid4().hex[:10])


def _legion_names(player: Any) -> list[str]:
    return [str(getattr(legion, "name", "Legio")) for legion in _list(getattr(player, "legions", []))]


def _legion(player: Any, name: str) -> Any | None:
    return next((legion for legion in _list(getattr(player, "legions", [])) if str(getattr(legion, "name", "")) == str(name)), None)


def _aux(player: Any, uid: str) -> dict | None:
    _ensure_aux_ids(player)
    return next((unit for unit in _list(getattr(player, "aux_units", [])) if isinstance(unit, dict) and unit.get("army_uid") == uid), None)


def _squadron(player: Any, name: str, ctx: dict) -> dict | None:
    return next((sq for sq in _list(_fleet(player, ctx).get("squadrons")) if isinstance(sq, dict) and str(sq.get("name")) == str(name)), None)


def _new_group(state: dict, name: str | None = None) -> dict:
    number = _i(state.get("next_number", 1), 1, 1)
    state["next_number"] = number + 1
    base_name = name or ROMAN_GROUP_NAMES[(number - 1) % len(ROMAN_GROUP_NAMES)]
    if any(g.get("name") == base_name for g in state.get("groups", [])):
        base_name = f"{base_name} {number}"
    return {
        "id": "EX-" + uuid.uuid4().hex[:10],
        "name": base_name,
        "commander": "",
        "doctrine": "balanced",
        "stance": "reserve",
        "location": "Roma",
        "target": None,
        "legions": [],
        "auxilia": [],
        "artillery": {},
        "fleet_squadrons": [],
        "supply": 85,
        "cohesion": 75,
        "experience": 0,
        "fatigue": 0,
        "battles": 0,
        "victories": 0,
        "created_turn": 1,
        "last_action_turn": 0,
    }


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    state = getattr(player, "army_group_system", None)
    if not isinstance(state, dict):
        state = {}
        player.army_group_system = state
    state.setdefault("schema", SCHEMA_VERSION)
    state.setdefault("version", MODULE_VERSION)
    state.setdefault("groups", [])
    state.setdefault("history", [])
    state.setdefault("next_number", 1)
    state.setdefault("last_tick_turn", 0)
    state.setdefault("migrated", False)
    state.setdefault("settings", {})
    state["settings"].setdefault("auto_reinforce", True)
    state["settings"].setdefault("auto_attach_new_units", True)
    state["settings"].setdefault("max_legions", MAX_LEGIONS_PER_GROUP)
    state["settings"].setdefault("max_auxilia", MAX_AUXILIA_PER_GROUP)

    _ensure_aux_ids(player)
    normalized = []
    for raw in _list(state.get("groups")):
        if not isinstance(raw, dict):
            continue
        group = dict(raw)
        group.setdefault("id", "EX-" + uuid.uuid4().hex[:10])
        group.setdefault("name", "Exercitus Romanus")
        group.setdefault("commander", "")
        group.setdefault("doctrine", "balanced")
        group.setdefault("stance", "reserve")
        group.setdefault("location", "Roma")
        group.setdefault("target", None)
        group.setdefault("legions", [])
        group.setdefault("auxilia", [])
        group.setdefault("artillery", {})
        group.setdefault("fleet_squadrons", [])
        group.setdefault("supply", 85)
        group.setdefault("cohesion", 75)
        group.setdefault("experience", 0)
        group.setdefault("fatigue", 0)
        group.setdefault("battles", 0)
        group.setdefault("victories", 0)
        group.setdefault("created_turn", _i(getattr(player, "turn", 1), 1))
        group.setdefault("last_action_turn", 0)
        if group["doctrine"] not in DOCTRINES:
            group["doctrine"] = "balanced"
        group["legions"] = [str(x) for x in _list(group.get("legions"))]
        group["auxilia"] = [str(x) for x in _list(group.get("auxilia"))]
        group["fleet_squadrons"] = [str(x) for x in _list(group.get("fleet_squadrons"))]
        group["artillery"] = {str(k): _i(v, 0, 0) for k, v in _dict(group.get("artillery")).items()}
        for key in ("supply", "cohesion", "fatigue"):
            group[key] = _clamp(group.get(key, 75), 0, 100, 75)
        for key in ("experience", "battles", "victories", "created_turn", "last_action_turn"):
            group[key] = _i(group.get(key, 0), 0, 0)
        normalized.append(group)
    state["groups"] = normalized
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state["last_tick_turn"] = _i(state.get("last_tick_turn", 0), 0, 0)
    state["next_number"] = _i(state.get("next_number", len(normalized) + 1), len(normalized) + 1, 1)
    state["schema"] = SCHEMA_VERSION
    state["version"] = MODULE_VERSION
    _validate_assignments(player, state, ctx)
    if not state["migrated"]:
        auto_organize(player, ctx, force=not bool(state["groups"]))
        state["migrated"] = True
    player.army_group_system = state
    return state


def _validate_assignments(player: Any, state: dict, ctx: dict) -> None:
    existing_legions = set(_legion_names(player))
    existing_aux = {u.get("army_uid") for u in _list(getattr(player, "aux_units", [])) if isinstance(u, dict)}
    existing_squadrons = {str(sq.get("name")) for sq in _list(_fleet(player, ctx).get("squadrons")) if isinstance(sq, dict)}
    inventory = _dict(getattr(player, "artillery_inventory", {}))
    used_legions: set[str] = set()
    used_aux: set[str] = set()
    used_squadrons: set[str] = set()
    used_artillery: dict[str, int] = {}
    for group in state.get("groups", []):
        legions = []
        for name in group.get("legions", []):
            if name in existing_legions and name not in used_legions:
                legions.append(name); used_legions.add(name)
        group["legions"] = legions
        auxilia = []
        for uid in group.get("auxilia", []):
            if uid in existing_aux and uid not in used_aux:
                auxilia.append(uid); used_aux.add(uid)
        group["auxilia"] = auxilia
        squadrons = []
        for name in group.get("fleet_squadrons", []):
            if name in existing_squadrons and name not in used_squadrons:
                squadrons.append(name); used_squadrons.add(name)
        group["fleet_squadrons"] = squadrons
        fixed_art = {}
        for key, qty in _dict(group.get("artillery")).items():
            available = max(0, _i(inventory.get(key, 0), 0) - used_artillery.get(key, 0))
            assigned = min(available, _i(qty, 0, 0))
            if assigned:
                fixed_art[key] = assigned
                used_artillery[key] = used_artillery.get(key, 0) + assigned
        group["artillery"] = fixed_art
        if group["legions"]:
            primary = _legion(player, group["legions"][0])
            if primary is not None:
                group["commander"] = str(getattr(getattr(primary, "general", None), "name", group.get("commander", "")))
                if group.get("location") in {"", "Roma", None}:
                    group["location"] = str(getattr(primary, "location", "Roma"))


def _unassigned(player: Any, state: dict, ctx: dict) -> dict:
    used_legions = {x for g in state["groups"] for x in g.get("legions", [])}
    used_aux = {x for g in state["groups"] for x in g.get("auxilia", [])}
    used_squadrons = {x for g in state["groups"] for x in g.get("fleet_squadrons", [])}
    used_artillery: dict[str, int] = {}
    for group in state["groups"]:
        for key, qty in group.get("artillery", {}).items():
            used_artillery[key] = used_artillery.get(key, 0) + _i(qty, 0)
    inventory = _dict(getattr(player, "artillery_inventory", {}))
    return {
        "legions": [name for name in _legion_names(player) if name not in used_legions],
        "auxilia": [u.get("army_uid") for u in _list(getattr(player, "aux_units", [])) if isinstance(u, dict) and u.get("army_uid") not in used_aux],
        "squadrons": [str(sq.get("name")) for sq in _list(_fleet(player, ctx).get("squadrons")) if isinstance(sq, dict) and str(sq.get("name")) not in used_squadrons],
        "artillery": {key: max(0, _i(qty, 0) - used_artillery.get(key, 0)) for key, qty in inventory.items()},
    }


def auto_organize(player: Any, ctx: dict | None = None, force: bool = False) -> dict:
    ctx = _ctx(ctx)
    state = getattr(player, "army_group_system", None)
    if not isinstance(state, dict):
        state = {"schema": SCHEMA_VERSION, "version": MODULE_VERSION, "groups": [], "history": [], "next_number": 1, "last_tick_turn": 0, "migrated": True, "settings": {}}
        player.army_group_system = state
    _ensure_aux_ids(player)
    if force:
        state["groups"] = []
        state["next_number"] = 1
    max_legions = _i(_dict(state.get("settings")).get("max_legions", MAX_LEGIONS_PER_GROUP), MAX_LEGIONS_PER_GROUP, 1, 8)
    max_aux = _i(_dict(state.get("settings")).get("max_auxilia", MAX_AUXILIA_PER_GROUP), MAX_AUXILIA_PER_GROUP, 1, 12)
    free = _unassigned(player, state, ctx)
    for i in range(0, len(free["legions"]), max_legions):
        group = _new_group(state)
        group["created_turn"] = _i(getattr(player, "turn", 1), 1)
        group["legions"] = free["legions"][i:i + max_legions]
        state["groups"].append(group)
    if not state["groups"] and (free["auxilia"] or any(free["artillery"].values()) or free["squadrons"]):
        group = _new_group(state, "Exercitus Praesidialis")
        group["created_turn"] = _i(getattr(player, "turn", 1), 1)
        state["groups"].append(group)
    if not state["groups"]:
        return state

    # Ауксилии распределяются по самым малым соединениям.
    for uid in free["auxilia"]:
        candidates = [g for g in state["groups"] if len(g.get("auxilia", [])) < max_aux]
        if not candidates:
            group = _new_group(state)
            state["groups"].append(group); candidates = [group]
        min(candidates, key=lambda g: len(g.get("auxilia", [])))["auxilia"].append(uid)

    # Артиллерия распределяется по числу легионов; остаток получает первое соединение.
    for key, qty in free["artillery"].items():
        qty = _i(qty, 0, 0)
        for _ in range(qty):
            target = min(
                state["groups"],
                key=lambda g: (g.get("artillery", {}).get(key, 0), -len(g.get("legions", []))),
            )
            target.setdefault("artillery", {})[key] = target.get("artillery", {}).get(key, 0) + 1

    # Эскадры образуют морское соединение либо прикрепляются к уже морскому.
    for name in free["squadrons"]:
        maritime = next((g for g in state["groups"] if g.get("doctrine") == "maritime"), None)
        if maritime is None:
            maritime = min(state["groups"], key=lambda g: len(g.get("fleet_squadrons", [])))
            if len(free["squadrons"]) >= 2:
                maritime["doctrine"] = "maritime"
                if maritime["name"].startswith("Exercitus Consularis"):
                    maritime["name"] = "Exercitus Maritimus"
        maritime.setdefault("fleet_squadrons", []).append(name)

    _validate_assignments(player, state, ctx)
    _record(player, state, "Реорганизация армии", f"Создано оперативных армий: {len(state['groups'])}.", ctx)
    return state


def get_group(player: Any, group_or_id: dict | str, ctx: dict | None = None) -> dict | None:
    state = ensure_state(player, ctx)
    if isinstance(group_or_id, dict):
        return group_or_id if group_or_id in state["groups"] else next((g for g in state["groups"] if g.get("id") == group_or_id.get("id")), None)
    return next((g for g in state["groups"] if g.get("id") == group_or_id or g.get("name") == group_or_id), None)


def _general_bonus(legion: Any, ctx: dict) -> tuple[int, int]:
    general = getattr(legion, "general", None)
    talent = str(getattr(general, "talent_key", ""))
    all_talents = _dict(ctx.get("ALL_TALENTS"))
    row = _dict(all_talents.get(talent))
    return _i(row.get("atk", 0), 0), _i(row.get("def_", 0), 0)


def group_power(player: Any, group_or_id: dict | str, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    group = get_group(player, group_or_id, ctx)
    if not group:
        return {"land": 0, "attack": 0, "defense": 0, "siege": 0, "naval": 0, "mobility": 0, "supply": 0, "cohesion": 0, "morale": 0, "readiness": 0}
    attack = defense = land = mobility = 0.0
    morale_values: list[int] = []
    for name in group.get("legions", []):
        legion = _legion(player, name)
        if legion is None:
            continue
        strength = _i(getattr(legion, "strength", 0), 0, 0, 100)
        quality = _i(getattr(legion, "quality", 1), 1, 1, 10)
        morale = _i(getattr(legion, "morale", 0), 0, 0, 100)
        fatigue = _i(getattr(legion, "fatigue", 0), 0, 0, 100)
        atk, deff = _general_bonus(legion, ctx)
        fatigue_mult = max(0.35, 1.0 - fatigue / 145.0)
        base = strength * (0.66 + quality * 0.055) * (0.72 + morale / 350.0) * fatigue_mult
        land += base
        attack += base * 0.54 + atk * 3
        defense += base * 0.56 + deff * 3
        mobility += 8 + quality * 0.8 - fatigue * 0.05
        morale_values.append(morale)
    aux_power_fn = ctx.get("aux_unit_power")
    for uid in group.get("auxilia", []):
        unit = _aux(player, uid)
        if not unit:
            continue
        if callable(aux_power_fn):
            try:
                power = _i(aux_power_fn(unit), 0)
            except Exception:
                power = 0
        else:
            power = _i(unit.get("strength", 0), 0) + _i(unit.get("attack", 0), 0) + _i(unit.get("defense", 0), 0)
        morale = _i(unit.get("morale", 70), 70, 0, 100)
        land += power * 0.85
        attack += power * 0.44 + _i(unit.get("attack", 0), 0)
        defense += power * 0.42 + _i(unit.get("defense", 0), 0)
        unit_type = str(unit.get("type", "")).lower()
        mobility += 13 if any(w in unit_type for w in ("кон", "развед", "луч")) else 7
        morale_values.append(morale)

    artillery_types = _dict(ctx.get("ARTILLERY_TYPES"))
    siege = 0.0
    support = 0.0
    for key, qty in group.get("artillery", {}).items():
        spec = _dict(artillery_types.get(key))
        qty = _i(qty, 0, 0)
        siege += qty * (_i(spec.get("siege", 0), 0) + _i(spec.get("power", 0), 0))
        support += qty * (_i(spec.get("support", 0), 0) + _i(spec.get("anti_barbarian", 0), 0) * 0.25)
    attack += support * 0.55
    defense += support * 0.35
    land += support * 0.45

    naval = 0.0
    squadron_value = ctx.get("_squadron_value_v25")
    for name in group.get("fleet_squadrons", []):
        sq = _squadron(player, name, ctx)
        if not sq:
            continue
        if callable(squadron_value):
            try:
                naval += _i(squadron_value(sq, "power"), 0)
                mobility += _i(squadron_value(sq, "maneuver"), 0) * 0.35
                land += _i(squadron_value(sq, "marines"), 0) * 0.35
            except Exception:
                naval += max(0, 20 - _i(sq.get("damage", 0), 0) // 5)
        else:
            naval += max(0, 20 - _i(sq.get("damage", 0), 0) // 5)
        morale_values.append(_i(sq.get("morale", 70), 70, 0, 100))

    doctrine = DOCTRINES.get(group.get("doctrine"), DOCTRINES["balanced"])
    tech_effect = ctx.get("tech_effect")
    tech_attack = tech_defense = tech_siege = 0.0
    if callable(tech_effect):
        try:
            tech_attack = _f(tech_effect(player, "battle_attack", 0), 0)
            tech_defense = _f(tech_effect(player, "battle_defense", 0), 0)
            tech_siege = _f(tech_effect(player, "battle_siege", 0), 0)
        except Exception:
            pass
    attack = (attack + tech_attack * 5) * _f(doctrine.get("land", 1.0), 1.0)
    defense = (defense + tech_defense * 5) * _f(doctrine.get("land", 1.0), 1.0)
    siege = (siege + tech_siege * 6) * _f(doctrine.get("siege", 1.0), 1.0)
    naval *= _f(doctrine.get("naval", 1.0), 1.0)
    mobility *= _f(doctrine.get("mobility", 1.0), 1.0)
    supply = _clamp(group.get("supply", 85), 0, 100, 85)
    cohesion = _clamp(group.get("cohesion", 75), 0, 100, 75)
    fatigue = _clamp(group.get("fatigue", 0), 0, 100, 0)
    morale = int(sum(morale_values) / len(morale_values)) if morale_values else 35
    readiness_mult = (0.55 + supply / 230.0) * (0.58 + cohesion / 240.0) * max(0.40, 1.0 - fatigue / 160.0)
    attack *= readiness_mult
    defense *= readiness_mult
    land = (land + attack * 0.22 + defense * 0.22) * readiness_mult
    siege *= (0.55 + supply / 210.0)
    naval *= (0.58 + supply / 220.0) * (0.62 + cohesion / 260.0)
    readiness = _clamp((supply + cohesion + morale + max(0, 100 - fatigue)) // 4, 0, 100, 0)
    return {
        "land": max(0, int(round(land))),
        "attack": max(0, int(round(attack))),
        "defense": max(0, int(round(defense))),
        "siege": max(0, int(round(siege))),
        "naval": max(0, int(round(naval))),
        "mobility": max(0, int(round(mobility))),
        "supply": supply,
        "cohesion": cohesion,
        "morale": morale,
        "readiness": readiness,
    }


def available_groups(player: Any, ctx: dict | None = None, naval: bool = False) -> list[dict]:
    state = ensure_state(player, ctx)
    result = []
    for group in state["groups"]:
        power = group_power(player, group, ctx)
        if group.get("stance") in {"destroyed", "interned"}:
            continue
        if naval and power["naval"] <= 0:
            continue
        if not naval and power["land"] <= 0:
            continue
        if power["readiness"] < 15:
            continue
        result.append(group)
    return result


def best_group(player: Any, ctx: dict | None = None, naval: bool = False, location: str | None = None) -> dict | None:
    groups = available_groups(player, ctx, naval=naval)
    if not groups:
        return None
    def score(group: dict) -> int:
        power = group_power(player, group, ctx)
        value = power["naval" if naval else "land"] + power["readiness"] * 2
        if location and group.get("location") == location:
            value += 45
        if group.get("stance") in {"defend", "intercept"}:
            value += 15
        return value
    return max(groups, key=score)


def apply_battle_result(
    player: Any,
    group_or_id: dict | str,
    won: bool,
    margin: int,
    ctx: dict | None = None,
    naval: bool = False,
) -> dict:
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    group = get_group(player, group_or_id, ctx)
    if not group:
        return {"losses": 0, "destroyed": []}
    margin = abs(_i(margin, 0))
    severity = min(42, (7 if won else 13) + margin // (5 if won else 3))
    destroyed: list[str] = []
    losses = 0
    if naval:
        for name in list(group.get("fleet_squadrons", [])):
            sq = _squadron(player, name, ctx)
            if not sq:
                continue
            damage = random.randint(max(2, severity // 4), max(4, severity // 2 + 3))
            if won:
                damage = max(1, damage // 2)
            sq["damage"] = _clamp(sq.get("damage", 0) + damage, 0, 100, 0)
            sq["morale"] = _clamp(sq.get("morale", 70) + (5 if won else -12), 0, 100, 70)
            sq["xp"] = _i(sq.get("xp", 0), 0) + (3 if won else 1)
            losses += damage
            if sq["damage"] >= 100:
                destroyed.append(name)
                try:
                    _fleet(player, ctx)["squadrons"].remove(sq)
                except (ValueError, KeyError):
                    pass
        group["fleet_squadrons"] = [n for n in group.get("fleet_squadrons", []) if n not in destroyed]
    else:
        for name in list(group.get("legions", [])):
            legion = _legion(player, name)
            if legion is None:
                continue
            loss = random.randint(max(2, severity // 5), max(5, severity // 2))
            if won:
                loss = max(1, loss // 2)
            legion.strength = max(0, _i(getattr(legion, "strength", 0), 0) - loss)
            legion.morale = _clamp(_i(getattr(legion, "morale", 70), 70) + (6 if won else -14), 0, 100, 70)
            legion.fatigue = _clamp(_i(getattr(legion, "fatigue", 0), 0) + (12 if won else 22), 0, 100, 0)
            legion.battles = _i(getattr(legion, "battles", 0), 0) + 1
            losses += loss
            if legion.strength <= 0:
                destroyed.append(name)
                try:
                    player.legions.remove(legion)
                except (ValueError, AttributeError):
                    pass
        group["legions"] = [n for n in group.get("legions", []) if n not in destroyed]
        for uid in list(group.get("auxilia", [])):
            unit = _aux(player, uid)
            if not unit:
                continue
            loss = random.randint(max(1, severity // 7), max(3, severity // 3))
            if won:
                loss = max(1, loss // 2)
            unit["strength"] = max(0, _i(unit.get("strength", 0), 0) - loss)
            unit["morale"] = _clamp(unit.get("morale", 70) + (5 if won else -16), 0, 100, 70)
            unit["xp"] = _i(unit.get("xp", 0), 0) + (3 if won else 1)
            losses += loss
            if unit["strength"] <= 0:
                destroyed.append(str(unit.get("name", uid)))
                try:
                    player.aux_units.remove(unit)
                except (ValueError, AttributeError):
                    pass
                group["auxilia"].remove(uid)
        if not won and group.get("artillery") and random.random() < min(0.60, severity / 75):
            key = random.choice(list(group["artillery"]))
            group["artillery"][key] = max(0, _i(group["artillery"].get(key, 0), 0) - 1)
            if group["artillery"][key] <= 0:
                group["artillery"].pop(key, None)
            inventory = _dict(getattr(player, "artillery_inventory", {}))
            if key in inventory:
                inventory[key] = max(0, _i(inventory.get(key, 0), 0) - 1)
            destroyed.append(f"артиллерия:{key}")
    group["battles"] = _i(group.get("battles", 0), 0) + 1
    group["experience"] = _i(group.get("experience", 0), 0) + (5 if won else 2)
    if won:
        group["victories"] = _i(group.get("victories", 0), 0) + 1
        group["cohesion"] = _clamp(group.get("cohesion", 75) + 4, 0, 100, 75)
    else:
        group["cohesion"] = _clamp(group.get("cohesion", 75) - 14, 0, 100, 75)
    group["supply"] = _clamp(group.get("supply", 85) - (8 if won else 15), 0, 100, 85)
    group["fatigue"] = _clamp(group.get("fatigue", 0) + (12 if won else 24), 0, 100, 0)
    group["last_action_turn"] = _i(getattr(player, "turn", 1), 1)
    outcome = "победила" if won else "потерпела поражение"
    _record(player, state, f"{group.get('name')} {outcome}", f"Потери: {losses}; утрачено: {', '.join(destroyed) if destroyed else 'ничего'}.", ctx)
    _validate_assignments(player, state, ctx)
    return {"losses": losses, "destroyed": destroyed}


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 1), 1)
    if state.get("last_tick_turn", 0) >= turn:
        return state
    state["last_tick_turn"] = turn
    if state.get("settings", {}).get("auto_attach_new_units", True):
        auto_organize(player, ctx, force=False)
    for group in state["groups"]:
        in_action = _i(group.get("last_action_turn", 0), 0) >= turn - 1
        supply_recovery = 4 if in_action else 9
        cohesion_recovery = 2 if in_action else 6
        fatigue_recovery = 8 if in_action else 18
        if group.get("stance") == "refit":
            supply_recovery += 8; cohesion_recovery += 5; fatigue_recovery += 12
        group["supply"] = _clamp(group.get("supply", 85) + supply_recovery, 0, 100, 85)
        group["cohesion"] = _clamp(group.get("cohesion", 75) + cohesion_recovery, 0, 100, 75)
        group["fatigue"] = _clamp(group.get("fatigue", 0) - fatigue_recovery, 0, 100, 0)
        # Синхронизация позиции легионов с оперативной армией.
        for name in group.get("legions", []):
            legion = _legion(player, name)
            if legion is not None and group.get("location"):
                legion.location = str(group["location"])
        if not group.get("legions") and not group.get("auxilia") and not group.get("fleet_squadrons") and not group.get("artillery"):
            group["stance"] = "empty"
    _validate_assignments(player, state, ctx)
    return state


def _group_rows(player: Any, state: dict, ctx: dict) -> list[tuple]:
    rows = []
    for i, group in enumerate(state["groups"], 1):
        p = group_power(player, group, ctx)
        composition = f"L{len(group.get('legions', []))}/A{len(group.get('auxilia', []))}/R{sum(group.get('artillery', {}).values())}/F{len(group.get('fleet_squadrons', []))}"
        rows.append((str(i), group.get("name"), composition, group.get("location"), DOCTRINES[group.get("doctrine", "balanced")]["name"], p["land"], p["naval"], p["readiness"]))
    return rows


def _detail(ui: UI, player: Any, group: dict, ctx: dict) -> None:
    p = group_power(player, group, ctx)
    ui.screen(); ui.header(group.get("name", "EXERCITUS"), "🦅", f"Командующий: {group.get('commander') or 'не назначен'}")
    ui.table("Оперативные показатели", ["Параметр", "Значение"], [
        ("Доктрина", DOCTRINES[group.get("doctrine", "balanced")]["name"]),
        ("Позиция / задача", f"{group.get('location')} / {group.get('stance')}"),
        ("Полевая мощь", p["land"]), ("Атака / защита", f"{p['attack']} / {p['defense']}"),
        ("Осада", p["siege"]), ("Флот", p["naval"]), ("Мобильность", p["mobility"]),
        ("Снабжение / спаянность", f"{p['supply']} / {p['cohesion']}"),
        ("Готовность", p["readiness"]), ("Бои / победы", f"{group.get('battles', 0)} / {group.get('victories', 0)}"),
    ], "GOLD")
    ui.section("Легионы", "RED")
    if group.get("legions"):
        for name in group["legions"]:
            legion = _legion(player, name)
            if legion:
                print(f"  • {name}: сила {getattr(legion, 'strength', 0)}, качество {getattr(legion, 'quality', 0)}, мораль {getattr(legion, 'morale', 0)}")
    else:
        ui.info("Нет легионов.", "GRAY")
    ui.section("Ауксилии", "CYAN")
    if group.get("auxilia"):
        for uid in group["auxilia"]:
            unit = _aux(player, uid)
            if unit:
                print(f"  • {unit.get('name')}: {unit.get('type')}, сила {unit.get('strength')}, мораль {unit.get('morale')}")
    else:
        ui.info("Нет ауксилий.", "GRAY")
    ui.section("Артиллерия и флот", "PURPLE")
    ui.info("Артиллерия: " + (", ".join(f"{k}×{v}" for k, v in group.get("artillery", {}).items()) or "нет"))
    ui.info("Эскадры: " + (", ".join(group.get("fleet_squadrons", [])) or "нет"))
    ui.pause()


def _select_group(ui: UI, state: dict) -> dict | None:
    if not state["groups"]:
        ui.info("Оперативных армий нет.", "GRAY"); ui.pause(); return None
    for i, group in enumerate(state["groups"], 1):
        print(f"  {i}. {group.get('name')}")
    pick = ui.choice("  Армия (Q — назад): ", [str(i) for i in range(1, len(state["groups"]) + 1)] + ["Q"])
    if pick == "Q":
        return None
    return state["groups"][int(pick) - 1]


def _attachments_menu(ui: UI, player: Any, group: dict, state: dict, ctx: dict) -> None:
    while True:
        _validate_assignments(player, state, ctx)
        free = _unassigned(player, state, ctx)
        ui.screen(); ui.header(f"СОСТАВ: {group.get('name')}", "🛡", "Прикрепление частей не создаёт копий и не удаляет исходные подразделения")
        ui.info(f"Легионы {len(group['legions'])}/{MAX_LEGIONS_PER_GROUP}; ауксилии {len(group['auxilia'])}/{MAX_AUXILIA_PER_GROUP}; эскадры {len(group['fleet_squadrons'])}.", "CYAN")
        print("  1. Прикрепить свободный легион")
        print("  2. Открепить легион")
        print("  3. Прикрепить ауксилию")
        print("  4. Открепить ауксилию")
        print("  5. Распределить свободную артиллерию")
        print("  6. Прикрепить эскадру")
        print("  7. Открепить эскадру")
        print("  Q. Назад")
        ch = ui.choice("  Решение: ", ["1", "2", "3", "4", "5", "6", "7", "Q"])
        if ch == "Q": return
        if ch == "1":
            if not free["legions"] or len(group["legions"]) >= MAX_LEGIONS_PER_GROUP:
                ui.info("Нет свободного места или свободных легионов.", "RED"); ui.pause(); continue
            for i, name in enumerate(free["legions"], 1): print(f"  {i}. {name}")
            p = ui.choice("  Легион: ", [str(i) for i in range(1, len(free["legions"]) + 1)] + ["Q"])
            if p != "Q": group["legions"].append(free["legions"][int(p) - 1])
        elif ch == "2":
            if not group["legions"]: ui.info("Нет легионов.", "GRAY"); ui.pause(); continue
            for i, name in enumerate(group["legions"], 1): print(f"  {i}. {name}")
            p = ui.choice("  Легион: ", [str(i) for i in range(1, len(group["legions"]) + 1)] + ["Q"])
            if p != "Q": group["legions"].pop(int(p) - 1)
        elif ch == "3":
            if not free["auxilia"] or len(group["auxilia"]) >= MAX_AUXILIA_PER_GROUP:
                ui.info("Нет свободного места или свободной ауксилии.", "RED"); ui.pause(); continue
            rows = []
            for i, uid in enumerate(free["auxilia"], 1):
                unit = _aux(player, uid); rows.append((str(i), unit.get("name") if unit else uid, unit.get("type") if unit else "", unit.get("strength") if unit else 0))
            ui.table("Свободная ауксилия", ["#", "Отряд", "Тип", "Сила"], rows)
            p = ui.choice("  Отряд: ", [str(i) for i in range(1, len(free["auxilia"]) + 1)] + ["Q"])
            if p != "Q": group["auxilia"].append(free["auxilia"][int(p) - 1])
        elif ch == "4":
            if not group["auxilia"]: ui.info("Нет ауксилий.", "GRAY"); ui.pause(); continue
            for i, uid in enumerate(group["auxilia"], 1):
                unit = _aux(player, uid); print(f"  {i}. {unit.get('name') if unit else uid}")
            p = ui.choice("  Отряд: ", [str(i) for i in range(1, len(group["auxilia"]) + 1)] + ["Q"])
            if p != "Q": group["auxilia"].pop(int(p) - 1)
        elif ch == "5":
            available = [(k, v) for k, v in free["artillery"].items() if v > 0]
            if not available: ui.info("Свободной артиллерии нет.", "GRAY"); ui.pause(); continue
            for i, (key, qty) in enumerate(available, 1): print(f"  {i}. {key} — доступно {qty}")
            p = ui.choice("  Тип: ", [str(i) for i in range(1, len(available) + 1)] + ["Q"])
            if p != "Q":
                key, _qty = available[int(p) - 1]
                group["artillery"][key] = group["artillery"].get(key, 0) + 1
        elif ch == "6":
            if not free["squadrons"]: ui.info("Свободных эскадр нет.", "GRAY"); ui.pause(); continue
            for i, name in enumerate(free["squadrons"], 1): print(f"  {i}. {name}")
            p = ui.choice("  Эскадра: ", [str(i) for i in range(1, len(free["squadrons"]) + 1)] + ["Q"])
            if p != "Q": group["fleet_squadrons"].append(free["squadrons"][int(p) - 1])
        elif ch == "7":
            if not group["fleet_squadrons"]: ui.info("Нет эскадр.", "GRAY"); ui.pause(); continue
            for i, name in enumerate(group["fleet_squadrons"], 1): print(f"  {i}. {name}")
            p = ui.choice("  Эскадра: ", [str(i) for i in range(1, len(group["fleet_squadrons"]) + 1)] + ["Q"])
            if p != "Q": group["fleet_squadrons"].pop(int(p) - 1)


def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx)
    ui = UI(ctx)
    state = ensure_state(player, ctx)
    while True:
        process_turn(player, ctx)
        ui.screen(); ui.header("EXERCITUS ROMANUS", "🦅", f"Оперативные армии, объединяющие легионы, ауксилии, артиллерию и флот — {MODULE_VERSION}")
        rows = _group_rows(player, state, ctx)
        if rows:
            ui.table("Армии Рима", ["#", "Армия", "Состав", "Позиция", "Доктрина", "Суша", "Море", "Гот."], rows, "RED")
        else:
            ui.info("Оперативных армий пока нет.", "GRAY")
        free = _unassigned(player, state, ctx)
        ui.info(f"Резерв: легионов {len(free['legions'])}, ауксилий {len(free['auxilia'])}, эскадр {len(free['squadrons'])}, артиллерии {sum(free['artillery'].values())}.", "CYAN")
        print("  1. Открыть досье армии")
        print("  2. Изменить состав армии")
        print("  3. Выбрать доктрину")
        print("  4. Изменить позицию и задачу")
        print("  5. Создать новую армию")
        print("  6. Автоматически реорганизовать все силы")
        print("  7. Старое управление отдельными легионами")
        print("  Q. Назад")
        ch = ui.choice("\n  Решение: ", ["1", "2", "3", "4", "5", "6", "7", "Q"])
        if ch == "Q": return
        if ch == "1":
            group = _select_group(ui, state)
            if group: _detail(ui, player, group, ctx)
        elif ch == "2":
            group = _select_group(ui, state)
            if group: _attachments_menu(ui, player, group, state, ctx)
        elif ch == "3":
            group = _select_group(ui, state)
            if not group: continue
            keys = list(DOCTRINES)
            for i, key in enumerate(keys, 1): print(f"  {i}. {DOCTRINES[key]['name']} — {DOCTRINES[key]['desc']}")
            p = ui.choice("  Доктрина: ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
            if p != "Q": group["doctrine"] = keys[int(p) - 1]
        elif ch == "4":
            group = _select_group(ui, state)
            if not group: continue
            raw = input("  Новая позиция (название города/провинции, пусто — без изменения): ").strip()
            if raw: group["location"] = raw
            stances = ["reserve", "defend", "intercept", "offensive", "siege", "refit"]
            for i, stance in enumerate(stances, 1): print(f"  {i}. {stance}")
            p = ui.choice("  Задача: ", [str(i) for i in range(1, len(stances) + 1)] + ["Q"])
            if p != "Q": group["stance"] = stances[int(p) - 1]
        elif ch == "5":
            name = input("  Название новой армии: ").strip() or None
            group = _new_group(state, name)
            group["created_turn"] = _i(getattr(player, "turn", 1), 1)
            state["groups"].append(group)
        elif ch == "6":
            confirm = ui.choice("  Полностью пересобрать все армии? (Y/N): ", ["Y", "N"])
            if confirm == "Y": auto_organize(player, ctx, force=True)
        elif ch == "7":
            legacy = ctx.get("legion_menu")
            if callable(legacy):
                legacy(player)
            else:
                ui.info("Старое меню легионов недоступно.", "RED"); ui.pause()
