#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna 4.1 — EXERCITUS UNIVERSALIS.

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
    open_province_operations(player, province, ctx=None)
"""
from __future__ import annotations

import random
import re
import textwrap
import uuid
from typing import Any

MODULE_VERSION = "4.2.0-bellum-celer"
SCHEMA_VERSION = 2
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
        "desc": "Флот, конвои, абордажные команды и переброска обычной армии к вражескому берегу.",
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
        # Нормализуем объект на месте: меню и операции держат ссылку на группу.
        # Копирование здесь делало выбранную армию «устаревшей» после любого
        # вызова group_power()/ensure_state() и теряло последующие приказы.
        group = raw
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

# ─── ROMA 4.0: EXERCITUS UNIVERSALIS ────────────────────────────────────────
# Единый штаб групп армий. Этот слой намеренно оставляет публичный контракт
# версии 3.0 совместимым для Bellum Universale, но переносит в одно меню найм,
# состав, развитие, сухопутные, варварские, морские и десантные операции.

_ensure_state_v300 = ensure_state
_auto_organize_v300 = auto_organize
_group_power_v300 = group_power
_apply_battle_result_v300 = apply_battle_result
_process_turn_v300 = process_turn

GROUP_LEVEL_XP = 12
MAX_GROUP_LEVEL = 16
BASE_ARTILLERY_SLOTS = 8
BASE_FLEET_SLOTS = 4
MAX_OPERATION_HISTORY = 80

UPGRADE_BRANCHES = (
    ("command", "IMPERVM — командование", "PURPLE"),
    ("field", "ACIES — полевая армия", "RED"),
    ("siege", "OPPVGNATIO — осадное дело", "GOLD"),
    ("logistics", "ANNONA — снабжение", "GREEN"),
    ("naval", "CLASSIS — море и десант", "CYAN"),
)

UPGRADE_TREE: dict[str, dict[str, Any]] = {
    # Командование
    "staff_camp": {
        "branch": "command", "name": "Штаб лагеря", "cost": 1, "requires": [],
        "desc": "+1 приказ группы за ход; штабная дисциплина повышает готовность.",
        "effects": {"command_points": 1, "readiness_flat": 4},
    },
    "consular_staff": {
        "branch": "command", "name": "Консульский штаб", "cost": 1, "requires": ["staff_camp"],
        "desc": "+1 место легиона и +8% к общей мощи соединения.",
        "effects": {"legion_slots": 1, "land_pct": 0.08},
    },
    "unified_command": {
        "branch": "command", "name": "Единое командование", "cost": 2, "requires": ["consular_staff"],
        "desc": "+12% атаки и защиты; потери спаянности после поражения ниже.",
        "effects": {"attack_pct": 0.12, "defense_pct": 0.12, "cohesion_guard": 6},
    },

    # Полевая армия
    "manipular_drill": {
        "branch": "field", "name": "Манипулярная выучка", "cost": 1, "requires": [],
        "desc": "+10% атаки и +6 мобильности.",
        "effects": {"attack_pct": 0.10, "mobility_flat": 6},
    },
    "cohort_tactics": {
        "branch": "field", "name": "Когортная тактика", "cost": 1, "requires": ["manipular_drill"],
        "desc": "+12% защиты и +1 место ауксилии.",
        "effects": {"defense_pct": 0.12, "aux_slots": 1},
    },
    "triplex_acies": {
        "branch": "field", "name": "Triplex acies", "cost": 2, "requires": ["cohort_tactics"],
        "desc": "+15% полевой мощи и преимущество против варварских масс.",
        "effects": {"land_pct": 0.15, "barbarian_bonus": 10},
    },

    # Осадное дело
    "fabri_corps": {
        "branch": "siege", "name": "Корпус fabri", "cost": 1, "requires": [],
        "desc": "+18% осадной силы и +2 места артиллерии.",
        "effects": {"siege_pct": 0.18, "artillery_slots": 2},
    },
    "siege_train": {
        "branch": "siege", "name": "Осадный поезд", "cost": 1, "requires": ["fabri_corps"],
        "desc": "+15% осадной силы, меньше расход боезапаса.",
        "effects": {"siege_pct": 0.15, "artillery_supply_discount": 0.30},
    },
    "storm_columns": {
        "branch": "siege", "name": "Штурмовые колонны", "cost": 2, "requires": ["siege_train"],
        "desc": "+14% атаки у стен и дополнительный урон обороне города.",
        "effects": {"attack_pct": 0.14, "city_damage": 9},
    },

    # Логистика
    "road_columns": {
        "branch": "logistics", "name": "Маршевые колонны", "cost": 1, "requires": [],
        "desc": "+12 мобильности и -10% стоимости операций.",
        "effects": {"mobility_flat": 12, "operation_discount": 0.10},
    },
    "fortified_camps": {
        "branch": "logistics", "name": "Укреплённые лагеря", "cost": 1, "requires": ["road_columns"],
        "desc": "+8% защиты, ускоренное восстановление снабжения и спаянности.",
        "effects": {"defense_pct": 0.08, "supply_recovery": 5, "cohesion_recovery": 4},
    },
    "annona_militaris": {
        "branch": "logistics", "name": "Annona militaris", "cost": 2, "requires": ["fortified_camps"],
        "desc": "Ещё -15% стоимости операций, +10 готовности и +1 приказ за ход.",
        "effects": {"operation_discount": 0.15, "readiness_flat": 10, "command_points": 1},
    },

    # Флот
    "classis_staff": {
        "branch": "naval", "name": "Штаб classis", "cost": 1, "requires": [],
        "desc": "+15% морской мощи и +1 место эскадры.",
        "effects": {"naval_pct": 0.15, "fleet_slots": 1},
    },
    "corvus_school": {
        "branch": "naval", "name": "Школа corvus", "cost": 1, "requires": ["classis_staff"],
        "desc": "+12% морской мощи; абордажные команды эффективнее в ближнем морском бою.",
        "effects": {"naval_pct": 0.12, "marine_bonus": 10},
    },
    "amphibious_command": {
        "branch": "naval", "name": "Командование морской переброской", "cost": 2, "requires": ["corvus_school"],
        "desc": "+12 к высадке обычной армии с кораблей, +4 транспортной вместимости.",
        "effects": {"amphibious_bonus": 12, "transport_bonus": 4},
    },
}


def _upgrade_effects(group: dict) -> dict[str, float]:
    result: dict[str, float] = {}
    for key in _list(group.get("upgrades")):
        node = _dict(UPGRADE_TREE.get(str(key)))
        for effect, value in _dict(node.get("effects")).items():
            result[effect] = result.get(effect, 0.0) + _f(value, 0.0)
    return result


def group_capacity(group: dict, category: str) -> int:
    effects = _upgrade_effects(group)
    bases = {
        "legions": MAX_LEGIONS_PER_GROUP,
        "auxilia": MAX_AUXILIA_PER_GROUP,
        "artillery": BASE_ARTILLERY_SLOTS,
        "fleet_squadrons": BASE_FLEET_SLOTS,
    }
    effect_keys = {
        "legions": "legion_slots",
        "auxilia": "aux_slots",
        "artillery": "artillery_slots",
        "fleet_squadrons": "fleet_slots",
    }
    return max(1, bases.get(category, 1) + _i(effects.get(effect_keys.get(category, ""), 0), 0))


def _group_level_for_xp(experience: int) -> int:
    return min(MAX_GROUP_LEVEL, 1 + max(0, _i(experience, 0)) // GROUP_LEVEL_XP)


def _sync_group_level(group: dict) -> int:
    target = _group_level_for_xp(_i(group.get("experience", 0), 0))
    awarded = _i(group.get("level_awarded", group.get("level", 1)), 1, 1, MAX_GROUP_LEVEL)
    gained = max(0, target - awarded)
    if gained:
        group["upgrade_points"] = _i(group.get("upgrade_points", 0), 0, 0) + gained
    group["level"] = target
    group["level_awarded"] = max(awarded, target)
    return gained


def _max_command_points(group: dict) -> int:
    return 2 + _i(_upgrade_effects(group).get("command_points", 0), 0)


def _normalize_group_v4(group: dict) -> None:
    group.setdefault("upgrades", [])
    group["upgrades"] = list(dict.fromkeys(str(k) for k in _list(group.get("upgrades")) if str(k) in UPGRADE_TREE))
    group.setdefault("upgrade_points", 0)
    group["upgrade_points"] = _i(group.get("upgrade_points", 0), 0, 0, 99)
    group.setdefault("level", 1)
    group.setdefault("level_awarded", group.get("level", 1))
    group.setdefault("command_points", _max_command_points(group))
    group.setdefault("last_command_turn", 0)
    group.setdefault("naval_zone", None)
    group.setdefault("operation", None)
    group.setdefault("operation_history", [])
    group["operation_history"] = [x for x in _list(group.get("operation_history")) if isinstance(x, dict)][-MAX_OPERATION_HISTORY:]
    group["command_points"] = _i(group.get("command_points", _max_command_points(group)), _max_command_points(group), 0, 9)
    group["last_command_turn"] = _i(group.get("last_command_turn", 0), 0, 0)
    _sync_group_level(group)


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    state = _ensure_state_v300(player, ctx)
    state["schema"] = SCHEMA_VERSION
    state["version"] = MODULE_VERSION
    state.setdefault("last_command_turn", 0)
    state.setdefault("market_history", [])
    state["market_history"] = [x for x in _list(state.get("market_history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state.setdefault("province_intel", {})
    state["province_intel"] = {str(k): _clamp(v, 0, 100, 0) for k, v in _dict(state.get("province_intel")).items()}
    for group in state.get("groups", []):
        _normalize_group_v4(group)
    return state


def _group_with_room(state: dict, category: str, *, exclude: dict | None = None) -> dict | None:
    candidates = []
    for group in state.get("groups", []):
        if group is exclude:
            continue
        used = sum(_dict(group.get("artillery")).values()) if category == "artillery" else len(group.get(category, []))
        capacity = group_capacity(group, category)
        if used < capacity:
            candidates.append((used / max(1, capacity), used, group))
    return min(candidates, key=lambda row: (row[0], row[1]))[2] if candidates else None


def _new_balanced_group(state: dict, player: Any, *, maritime: bool = False) -> dict:
    name = "Exercitus Maritimus" if maritime else None
    group = _new_group(state, name)
    group["created_turn"] = _i(getattr(player, "turn", 1), 1)
    if maritime:
        group["doctrine"] = "maritime"
    _normalize_group_v4(group)
    state.setdefault("groups", []).append(group)
    return group


def auto_organize(player: Any, ctx: dict | None = None, force: bool = False) -> dict:
    """Собирает все части в группы и гарантирует соблюдение вместимости.

    Старый алгоритм миграции сохраняется, после чего излишки легионов,
    ауксилий, артиллерии и эскадр автоматически образуют новые штабы вместо
    скрытого штрафа за бесконечно перегруженную единственную армию.
    """
    ctx = _ctx(ctx)
    state = _auto_organize_v300(player, ctx, force=force)
    for group in state.get("groups", []):
        _normalize_group_v4(group)

    # Списочные категории: сохраняем первые части, излишки отправляем в штабы,
    # где есть свободные штатные места, либо создаём новый штаб.
    for category in ("legions", "auxilia", "fleet_squadrons"):
        for group in list(state.get("groups", [])):
            capacity = group_capacity(group, category)
            assigned = list(group.get(category, []))
            group[category] = assigned[:capacity]
            for item in assigned[capacity:]:
                target = _group_with_room(state, category, exclude=group)
                if target is None:
                    target = _new_balanced_group(state, player, maritime=(category == "fleet_squadrons"))
                target.setdefault(category, []).append(item)

    # Артиллерия хранится словарём количеств, поэтому временно разворачиваем её
    # в отдельные машины и распределяем поштучно.
    for group in list(state.get("groups", [])):
        flat = [key for key, qty in _dict(group.get("artillery")).items() for _ in range(max(0, _i(qty, 0)))]
        capacity = group_capacity(group, "artillery")
        kept = flat[:capacity]
        rebuilt: dict[str, int] = {}
        for key in kept:
            rebuilt[key] = rebuilt.get(key, 0) + 1
        group["artillery"] = rebuilt
        for key in flat[capacity:]:
            target = _group_with_room(state, "artillery", exclude=group)
            if target is None:
                target = _new_balanced_group(state, player)
            target.setdefault("artillery", {})[key] = _i(target.get("artillery", {}).get(key, 0), 0) + 1

    # Пустые штабы после полной пересборки не нужны; пользовательские пустые
    # группы при обычном авто-прикреплении, напротив, сохраняются.
    if force:
        state["groups"] = [
            group for group in state.get("groups", [])
            if group.get("legions") or group.get("auxilia") or group.get("fleet_squadrons") or group.get("artillery")
        ]
    for group in state.get("groups", []):
        _normalize_group_v4(group)
    _validate_assignments(player, state, ctx)
    return state


def group_power(player: Any, group_or_id: dict | str, ctx: dict | None = None) -> dict:
    """Returns strategic combat power for the fast-conquest war model.

    The old wrapper left even a complete army group feeling weaker than a city
    garrison.  Here unit quality and actual composition matter directly: veteran
    and elite legions become decisive, while auxilia can form a viable army of
    their own instead of serving as a tiny passive bonus.
    """
    ctx = _ctx(ctx)
    result = dict(_group_power_v300(player, group_or_id, ctx))
    group = get_group(player, group_or_id, ctx)
    if not group:
        return result

    effects = _upgrade_effects(group)
    legion_score = 0.0
    legion_count = 0
    for name in group.get("legions", []):
        legion = _legion(player, name)
        if legion is None:
            continue
        legion_count += 1
        strength = _i(getattr(legion, "strength", 0), 0, 0, 100)
        quality = _i(getattr(legion, "quality", 1), 1, 1, 10)
        morale = _i(getattr(legion, "morale", 70), 70, 0, 100)
        rank = 1.18 if bool(getattr(legion, "elite", False)) else 1.10 if bool(getattr(legion, "veterans", False)) else 1.0
        legion_score += (strength * 0.58 + quality * 5.0 + morale * 0.16) * rank

    aux_score = 0.0
    aux_count = 0
    aux_power_fn = ctx.get("aux_unit_power")
    for uid in group.get("auxilia", []):
        unit = _aux(player, uid)
        if not unit:
            continue
        aux_count += 1
        try:
            base = _i(aux_power_fn(unit), 0) if callable(aux_power_fn) else (
                _i(unit.get("strength", 0), 0) + _i(unit.get("attack", 0), 0) + _i(unit.get("defense", 0), 0)
            )
        except Exception:
            base = _i(unit.get("strength", 0), 0)
        rank = 1.16 if bool(unit.get("elite", False)) else 1.09 if bool(unit.get("veterans", False)) else 1.0
        aux_score += base * rank

    base_attack = _f(result.get("attack", 0), 0)
    base_defense = _f(result.get("defense", 0), 0)
    base_siege = _f(result.get("siege", 0), 0)
    base_land = _f(result.get("land", 0), 0)

    attack = base_attack * 1.28 + legion_score * 0.42 + aux_score * 0.32 + legion_count * 8 + aux_count * 5
    defense = base_defense * 1.24 + legion_score * 0.36 + aux_score * 0.34 + legion_count * 7 + aux_count * 6
    siege = base_siege * 1.35 + legion_score * 0.10 + aux_score * 0.07 + legion_count * 4 + aux_count * 2
    land = base_land * 1.18 + attack * 0.42 + defense * 0.28

    result["attack"] = max(0, int(round(attack * (1.0 + effects.get("attack_pct", 0.0)))))
    result["defense"] = max(0, int(round(defense * (1.0 + effects.get("defense_pct", 0.0)))))
    result["siege"] = max(0, int(round(siege * (1.0 + effects.get("siege_pct", 0.0)))))
    result["naval"] = max(0, int(round(result.get("naval", 0) * (1.0 + effects.get("naval_pct", 0.0)))))
    result["mobility"] = max(0, int(round(result.get("mobility", 0) + effects.get("mobility_flat", 0.0))))
    result["land"] = max(0, int(round(land * (1.0 + effects.get("land_pct", 0.0)))))

    # An auxilia-only group is a real field army. It is slightly less efficient
    # at organised siege work, but it can assault and occupy a city normally.
    if aux_count and not legion_count:
        result["attack"] = int(round(result["attack"] * 0.94))
        result["siege"] = int(round(result["siege"] * 0.88))
        result["land"] = int(round(result["land"] * 0.96))

    over = 0
    over += max(0, len(group.get("legions", [])) - group_capacity(group, "legions"))
    over += max(0, len(group.get("auxilia", [])) - group_capacity(group, "auxilia"))
    over += max(0, sum(_dict(group.get("artillery")).values()) - group_capacity(group, "artillery"))
    over += max(0, len(group.get("fleet_squadrons", [])) - group_capacity(group, "fleet_squadrons"))
    readiness = _i(result.get("readiness", 0), 0) + _i(effects.get("readiness_flat", 0), 0) - over * 7
    result["readiness"] = _clamp(readiness, 0, 100, 0)
    if over:
        penalty = max(0.55, 1.0 - 0.08 * over)
        result["land"] = int(result["land"] * penalty)
        result["naval"] = int(result["naval"] * penalty)
    result["level"] = _i(group.get("level", 1), 1)
    result["command_points"] = _i(group.get("command_points", 0), 0)
    result["max_command_points"] = _max_command_points(group)
    result["legion_count"] = legion_count
    result["auxilia_count"] = aux_count
    return result



def apply_battle_result(
    player: Any,
    group_or_id: dict | str,
    won: bool,
    margin: int,
    ctx: dict | None = None,
    naval: bool = False,
) -> dict:
    ctx = _ctx(ctx)
    group = get_group(player, group_or_id, ctx)
    old_level = _i(group.get("level", 1), 1) if group else 1
    result = _apply_battle_result_v300(player, group_or_id, won, margin, ctx, naval=naval)
    group = get_group(player, group_or_id, ctx)
    gained = _sync_group_level(group) if group else 0
    if group:
        guard = _i(_upgrade_effects(group).get("cohesion_guard", 0), 0)
        if not won and guard:
            group["cohesion"] = _clamp(group.get("cohesion", 0) + guard, 0, 100, 0)
        group.setdefault("operation_history", []).append({
            "turn": _i(getattr(player, "turn", 1), 1),
            "type": "naval_battle" if naval else "land_battle",
            "result": "victory" if won else "defeat",
            "margin": _i(margin, 0),
        })
        group["operation_history"] = group["operation_history"][-MAX_OPERATION_HISTORY:]
    result["level_before"] = old_level
    result["level_after"] = _i(group.get("level", old_level), old_level) if group else old_level
    result["upgrade_points_gained"] = gained
    return result


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    state = _process_turn_v300(player, ctx)
    turn = _i(getattr(player, "turn", 1), 1)
    if _i(state.get("last_command_turn", 0), 0) >= turn:
        return state
    state["last_command_turn"] = turn
    for group in state.get("groups", []):
        _normalize_group_v4(group)
        effects = _upgrade_effects(group)
        group["command_points"] = _max_command_points(group)
        group["last_command_turn"] = turn
        group["supply"] = _clamp(group.get("supply", 85) + _i(effects.get("supply_recovery", 0), 0), 0, 100, 85)
        group["cohesion"] = _clamp(group.get("cohesion", 75) + _i(effects.get("cohesion_recovery", 0), 0), 0, 100, 75)
        if group.get("stance") == "refit":
            for name in group.get("legions", []):
                legion = _legion(player, name)
                if legion is not None:
                    legion.strength = min(100, _i(getattr(legion, "strength", 0), 0) + 3)
                    legion.morale = min(100, _i(getattr(legion, "morale", 70), 70) + 2)
            for uid in group.get("auxilia", []):
                unit = _aux(player, uid)
                if unit:
                    maximum = _i(unit.get("max_strength", unit.get("strength", 0)), 0)
                    unit["strength"] = min(maximum, _i(unit.get("strength", 0), 0) + 2)
            for name in group.get("fleet_squadrons", []):
                sq = _squadron(player, name, ctx)
                if sq:
                    sq["damage"] = max(0, _i(sq.get("damage", 0), 0) - 3)
                    sq["morale"] = min(100, _i(sq.get("morale", 70), 70) + 2)
        zone = group.get("naval_zone")
        if zone:
            for name in group.get("fleet_squadrons", []):
                sq = _squadron(player, name, ctx)
                if sq:
                    sq["zone"] = str(zone)
    return state


def _grant_group_xp(group: dict, amount: int) -> int:
    group["experience"] = _i(group.get("experience", 0), 0, 0) + max(0, _i(amount, 0))
    return _sync_group_level(group)


def _operation_record(player: Any, state: dict, group: dict, kind: str, title: str, text: str, ctx: dict) -> None:
    item = {
        "turn": _i(getattr(player, "turn", 1), 1),
        "type": kind,
        "title": title,
        "text": text,
    }
    group.setdefault("operation_history", []).append(item)
    group["operation_history"] = group["operation_history"][-MAX_OPERATION_HISTORY:]
    group["operation"] = item
    _record(player, state, title, text, ctx)


def _roman_numeral(number: int) -> str:
    values = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
              (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
    number = max(1, _i(number, 1))
    result = []
    for value, glyph in values:
        while number >= value:
            result.append(glyph)
            number -= value
    return "".join(result)


def _price(player: Any, ctx: dict, base: int, *, upkeep: bool = False) -> int:
    fn = ctx.get("game_price")
    if callable(fn):
        try:
            return max(0, _i(fn(player, max(0, _i(base, 0)), market=True, upkeep=upkeep, minimum=0), base))
        except TypeError:
            try:
                return max(0, _i(fn(player, max(0, _i(base, 0)), market=True), base))
            except Exception:
                pass
        except Exception:
            pass
    return max(0, _i(base, 0))


def _operation_cost(player: Any, group: dict, ctx: dict, gold: int, grain: int) -> tuple[int, int]:
    discount = min(0.50, max(0.0, _upgrade_effects(group).get("operation_discount", 0.0)))
    gold_cost = _price(player, ctx, int(round(max(0, gold) * (1.0 - discount))))
    grain_cost = max(0, int(round(max(0, grain) * (1.0 - discount * 0.60))))
    return gold_cost, grain_cost


def _pay_operation(player: Any, group: dict, ctx: dict, gold: int, grain: int, ui: UI) -> tuple[bool, int, int]:
    gold_cost, grain_cost = _operation_cost(player, group, ctx, gold, grain)
    if _i(getattr(player, "gold", 0), 0) < gold_cost or _i(getattr(player, "grain", 0), 0) < grain_cost:
        ui.info(f"Недостаточно ресурсов: нужно {gold_cost} золота и {grain_cost} зерна.", "RED")
        return False, gold_cost, grain_cost
    player.gold -= gold_cost
    player.grain -= grain_cost
    return True, gold_cost, grain_cost


def _spend_command(group: dict, amount: int, ui: UI) -> bool:
    amount = max(1, _i(amount, 1))
    current = _i(group.get("command_points", 0), 0)
    if current < amount:
        ui.info(f"У группы недостаточно приказов: нужно {amount}, доступно {current}. Завершите ход.", "RED")
        return False
    group["command_points"] = current - amount
    return True


def _roll_duel(ctx: dict, roman: int, enemy: int) -> tuple[int, list[int], int, list[int], int]:
    fn = ctx.get("table_3d6_duel_totals")
    if callable(fn):
        try:
            rt, rd, et, ed, margin = fn(max(1, roman), max(1, enemy))
            return _i(rt, roman), list(rd), _i(et, enemy), list(ed), _i(margin, 0)
        except Exception:
            pass
    rd = [random.randint(1, 6) for _ in range(3)]
    ed = [random.randint(1, 6) for _ in range(3)]
    rt = max(1, roman) + sum(rd)
    et = max(1, enemy) + sum(ed)
    return rt, rd, et, ed, rt - et


def _dice_text(ctx: dict, dice: list[int]) -> str:
    fn = ctx.get("format_3d6")
    if callable(fn):
        try:
            return str(fn(dice))
        except Exception:
            pass
    return "+".join(str(x) for x in dice)


def _select_group_for_operation(ui: UI, player: Any, state: dict, ctx: dict, *, naval: bool = False, amphibious: bool = False) -> dict | None:
    candidates = []
    for group in state.get("groups", []):
        p = group_power(player, group, ctx)
        if p["readiness"] < 12 or _i(group.get("command_points", 0), 0) <= 0:
            continue
        if naval and not group.get("fleet_squadrons"):
            continue
        if amphibious and (not group.get("fleet_squadrons") or not (group.get("legions") or group.get("auxilia"))):
            continue
        if not naval and not (group.get("legions") or group.get("auxilia")):
            continue
        candidates.append((group, p))
    if not candidates:
        ui.info("Нет подходящей боеспособной группы армий с доступными приказами.", "RED")
        ui.pause()
        return None
    ui.table("Доступные группы", ["#", "Группа", "Позиция", "Суша", "Море", "Гот.", "Прик."], [
        (str(i), group.get("name"), group.get("location"), p["land"], p["naval"], p["readiness"], f"{group.get('command_points', 0)}/{p['max_command_points']}")
        for i, (group, p) in enumerate(candidates, 1)
    ], "RED" if not naval else "CYAN")
    pick = ui.choice("  Группа (Q — назад): ", [str(i) for i in range(1, len(candidates) + 1)] + ["Q"])
    return None if pick == "Q" else candidates[int(pick) - 1][0]


def _assigned_artillery_power(group: dict, ctx: dict, role: str) -> int:
    types = _dict(ctx.get("ARTILLERY_TYPES"))
    total = 0
    for key, qty in _dict(group.get("artillery")).items():
        total += _i(qty, 0) * _i(_dict(types.get(key)).get(role, 0), 0)
    return max(0, total)


def _assigned_artillery_count(group: dict) -> int:
    return sum(max(0, _i(v, 0)) for v in _dict(group.get("artillery")).values())


def _group_transport_capacity(player: Any, group: dict, ctx: dict) -> int:
    types = _dict(ctx.get("FLEET_SQUADRON_TYPES"))
    cargo = 0
    for name in group.get("fleet_squadrons", []):
        sq = _squadron(player, name, ctx)
        if sq:
            cargo += _i(_dict(types.get(sq.get("type"))).get("cargo", 0), 0)
    cargo += _i(_upgrade_effects(group).get("transport_bonus", 0), 0)
    return max(0, cargo)


def _group_marines(player: Any, group: dict, ctx: dict) -> int:
    types = _dict(ctx.get("FLEET_SQUADRON_TYPES"))
    marines = 0
    for name in group.get("fleet_squadrons", []):
        sq = _squadron(player, name, ctx)
        if sq:
            marines += _i(_dict(types.get(sq.get("type"))).get("marines", 0), 0)
    for uid in group.get("auxilia", []):
        unit = _aux(player, uid)
        if unit and "морск" in str(unit.get("type", "")).lower():
            marines += max(4, _i(unit.get("strength", 0), 0) // 2)
    marines += _i(_upgrade_effects(group).get("marine_bonus", 0), 0)
    return max(0, marines)


def _frontier_provinces(player: Any, ctx: dict) -> list[dict]:
    fn = ctx.get("frontier_provinces")
    if callable(fn):
        try:
            return [p for p in _list(fn(player)) if isinstance(p, dict)]
        except Exception:
            pass
    all_provinces = [p for p in _list(ctx.get("PROVINCES_DATA")) if isinstance(p, dict)]
    owned = {str(p.get("name")) for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)}
    frontier = set()
    by_name = {str(p.get("name")): p for p in all_provinces}
    for name in owned:
        frontier.update(str(x) for x in _list(_dict(by_name.get(name)).get("neighbors")))
    return [by_name[name] for name in frontier if name in by_name and name not in owned]


def _next_city(player: Any, province: dict, ctx: dict) -> dict | None:
    fn = ctx.get("next_city_to_attack")
    if callable(fn):
        try:
            city = fn(player, province)
            return city if isinstance(city, dict) else None
        except Exception:
            pass
    taken = set(_dict(getattr(player, "city_campaigns", {})).get(str(province.get("name")), []))
    return next((c for c in _list(province.get("cities")) if isinstance(c, dict) and c.get("name") not in taken), None)


def _capture_city(player: Any, province: dict, city: dict, source: str, ctx: dict, ui: UI) -> tuple[bool, str]:
    ensure = ctx.get("ensure_city_campaigns")
    if callable(ensure):
        try:
            ensure(player)
        except Exception:
            pass
    if not hasattr(player, "city_campaigns") or not isinstance(player.city_campaigns, dict):
        player.city_campaigns = {}
    province_name = str(province.get("name"))
    city_name = str(city.get("name"))
    taken = player.city_campaigns.setdefault(province_name, [])
    if city_name not in taken:
        taken.append(city_name)
    clear = ctx.get("clear_city_siege_damage")
    if callable(clear):
        try:
            clear(player, province_name, city_name)
        except Exception:
            pass

    reward: dict = {}
    reward_fn = ctx.get("city_conquest_reward")
    if callable(reward_fn):
        try:
            reward = _dict(reward_fn(player, province, city, source=source, announce=False))
        except Exception:
            reward = {}
    reward_parts = []
    if _i(reward.get("gold", 0), 0):
        reward_parts.append(f"+{_i(reward.get('gold', 0), 0)} золота")
    if _i(reward.get("grain", 0), 0):
        reward_parts.append(f"+{_i(reward.get('grain', 0), 0)} зерна")
    resources = _dict(reward.get("resources"))
    if resources:
        resource_names = _dict(ctx.get("RESOURCE_CATALOG"))
        formatted = []
        for key, amount in resources.items():
            spec = _dict(resource_names.get(key))
            formatted.append(f"{spec.get('name', key)} +{_i(amount, 0)}")
        reward_parts.append("ресурсы: " + ", ".join(formatted))
    reward_text = (" Трофеи: " + "; ".join(reward_parts) + ".") if reward_parts else ""

    route_text = ""
    route_fn = ctx.get("offer_city_trade_route")
    if callable(route_fn):
        try:
            route = _dict(route_fn(player, province, city, interactive=True))
            if route.get("built"):
                route_text = f" Торговый путь построен: +{_i(route.get('income', 0), 0)} золота/ход."
        except Exception:
            pass

    progress_fn = ctx.get("city_campaign_progress")
    done = len(taken)
    total = len(_list(province.get("cities"))) or 1
    if callable(progress_fn):
        try:
            done, total = progress_fn(player, province_name)
        except Exception:
            pass
    if done >= total:
        annex = ctx.get("annex_province_after_campaign")
        if callable(annex):
            try:
                captured, unlocked = annex(player, province)
                extra = f" Открыты части: {', '.join(unlocked)}." if unlocked else ""
                return True, f"Провинция {captured.get('name', province_name)} присоединена.{reward_text}{route_text}{extra}"
            except Exception as exc:
                return True, f"Все города {province_name} взяты, но присоединение требует проверки: {exc}{reward_text}{route_text}"
    return False, f"Город {city_name} взят. Кампания {province_name}: {done}/{total}.{reward_text}{route_text}"



def _city_operation(player: Any, ctx: dict, ui: UI, state: dict) -> None:
    group = _select_group_for_operation(ui, player, state, ctx, naval=False)
    if not group:
        return
    if not group.get("legions") and not group.get("auxilia"):
        ui.info("Для штурма нужен хотя бы один легион или отряд ауксилии.", "RED")
        ui.pause(); return
    targets = _frontier_provinces(player, ctx)
    rows = []
    valid_targets = []
    damage_fn = ctx.get("city_siege_damage")
    progress_fn = ctx.get("city_campaign_progress")
    for province in targets:
        city = _next_city(player, province, ctx)
        if not city:
            continue
        damage = 0
        if callable(damage_fn):
            try: damage = _i(damage_fn(player, province.get("name"), city.get("name")), 0)
            except Exception: pass
        done, total = 0, len(_list(province.get("cities"))) or 1
        if callable(progress_fn):
            try: done, total = progress_fn(player, province.get("name"))
            except Exception: pass
        valid_targets.append((province, city, damage))
        rows.append((str(len(valid_targets)), province.get("name"), city.get("name"), f"{done}/{total}", city.get("difficulty", 3), f"{damage}%"))
    if not valid_targets:
        ui.info("На сухопутной границе нет доступных городов.", "GRAY"); ui.pause(); return
    ui.screen(); ui.header("ПОХОД НА ГОРОД", "🏰", f"Группа: {group.get('name')}")
    ui.table("Цели кампании", ["#", "Провинция", "Следующий город", "Взято", "Сложн.", "Урон"], rows, "GOLD")
    pick = ui.choice("  Цель (Q — назад): ", [str(i) for i in range(1, len(valid_targets) + 1)] + ["Q"])
    if pick == "Q": return
    province, city, current_damage = valid_targets[int(pick) - 1]
    p = group_power(player, group, ctx)
    difficulty = _i(city.get("difficulty", 3), 3, 1, 10)
    # Обычный штурм города не покупается за золото или зерно. Группа расходует
    # только приказ; артиллерия ниже по-прежнему использует собственный боезапас.
    if not _spend_command(group, 1, ui):
        ui.pause(); return

    artillery = _assigned_artillery_power(group, ctx, "siege")
    art_count = _assigned_artillery_count(group)
    art_supply = max(0, art_count * 2)
    supply_stock = _i(getattr(player, "artillery_supplies", 0), 0)
    if art_count and supply_stock >= art_supply:
        discount = min(0.70, _upgrade_effects(group).get("artillery_supply_discount", 0.0))
        spent = max(1, int(round(art_supply * (1.0 - discount))))
        player.artillery_supplies = max(0, supply_stock - spent)
    elif art_count:
        artillery = artillery // 3
        spent = 0
    else:
        spent = 0

    strength_fn = ctx.get("city_strength_for_attack")
    base_city = difficulty * 2 + _i(province.get("wealth", 2), 2) + 2
    if callable(strength_fn):
        try: base_city = _i(strength_fn(city, province, None, 1.0), base_city)
        except Exception: pass
    remaining = max(0, 100 - current_damage)
    roman = max(8, p["attack"] // 8 + p["land"] // 12 + p["siege"] // 6 + p["readiness"] // 10)
    enemy = max(8, base_city * 2 + remaining // 8 + difficulty * 2)
    rt, rd, et, ed, margin = _roll_duel(ctx, roman, enemy)
    won = margin >= 0
    ui.screen(); ui.header(f"ШТУРМ: {str(city.get('name')).upper()}", "⚔", f"{group.get('name')} — {province.get('name')}")
    ui.info(f"Рим: {_dice_text(ctx, rd)} + {roman} = {rt}", "GREEN")
    ui.info(f"Гарнизон: {_dice_text(ctx, ed)} + {enemy} = {et}", "RED")
    raw_damage = 5 + p["siege"] // 4 + p["attack"] // 16 + _i(_upgrade_effects(group).get("city_damage", 0), 0) + random.randint(0, 7)
    if not won:
        raw_damage = max(2, raw_damage // 3)
    apply_damage = ctx.get("apply_city_siege_damage")
    actual, total_damage, remaining_after = raw_damage, min(100, current_damage + raw_damage), max(0, 100 - current_damage - raw_damage)
    if callable(apply_damage):
        try:
            actual, total_damage, remaining_after = apply_damage(player, province.get("name"), city.get("name"), raw_damage)
        except Exception:
            pass
    apply_battle_result(player, group, won, abs(margin), ctx, naval=False)
    group["location"] = str(city.get("name"))
    group["target"] = str(city.get("name"))
    group["stance"] = "siege"
    group["last_action_turn"] = _i(getattr(player, "turn", 1), 1)
    ui.info(f"Оборона города получила {actual}% урона: всего {total_damage}%, осталось {remaining_after}%.", "GOLD")
    if art_count:
        ui.info(f"Осадные машины: сила {artillery}; боезапас -{spent}." if spent else "Боезапаса не хватило: артиллерия действовала с пониженной эффективностью.", "CYAN")
    title = f"Штурм {city.get('name')}"
    if won and total_damage >= 100:
        annexed, message = _capture_city(player, province, city, "army_group_assault", ctx, ui)
        gained = _grant_group_xp(group, 6 if annexed else 4)
        ui.wrap(message, "GREEN")
        text = message
        if gained: ui.info(f"Новый уровень группы: {group.get('level')}; очки развития +{gained}.", "PURPLE")
    elif won:
        text = f"Победа у стен; город повреждён на {total_damage}%, но ещё держится."
        ui.wrap(text, "GOLD")
    else:
        text = f"Штурм отбит; обороне всё же нанесено {actual}% урона."
        ui.wrap(text, "RED")
    _operation_record(player, state, group, "city", title, text, ctx)
    ui.pause()


def _barbarian_operation(player: Any, ctx: dict, ui: UI, state: dict) -> None:
    group = _select_group_for_operation(ui, player, state, ctx, naval=False)
    if not group: return
    tribes = [(key, row) for key, row in _dict(getattr(player, "barbarian_tribes", {})).items() if isinstance(row, dict) and _i(row.get("strength", 0), 0) > 0]
    if not tribes:
        ui.info("Активных варварских племён в совместимом реестре нет.", "GRAY"); ui.pause(); return
    ui.screen(); ui.header("ЭКСПЕДИЦИЯ НА ФРОНТИР", "🐺", f"Группа: {group.get('name')}")
    ui.table("Племена", ["#", "Племя", "Вождь", "Сила", "Отношение", "Пакт"], [
        (str(i), row.get("name", key), row.get("chief", "—"), row.get("strength", 0), row.get("relation", 0), "да" if row.get("pact") else "нет")
        for i, (key, row) in enumerate(tribes, 1)
    ], "RED")
    pick = ui.choice("  Цель (Q — назад): ", [str(i) for i in range(1, len(tribes) + 1)] + ["Q"])
    if pick == "Q": return
    key, tribe = tribes[int(pick) - 1]
    p = group_power(player, group, ctx)
    strength = _i(tribe.get("strength", 5), 5, 1)
    unit_count = len(group.get("legions", [])) + len(group.get("auxilia", []))
    ok, gold_cost, grain_cost = _pay_operation(player, group, ctx, 12 + strength * 4, 10 + unit_count * 4, ui)
    if not ok: ui.pause(); return
    if not _spend_command(group, 1, ui):
        player.gold += gold_cost; player.grain += grain_cost; ui.pause(); return
    artillery = _assigned_artillery_power(group, ctx, "anti_barbarian")
    roman = max(7, p["land"] // 12 + p["attack"] // 10 + p["mobility"] // 8 + p["readiness"] // 10 + artillery // 5 + _i(_upgrade_effects(group).get("barbarian_bonus", 0), 0))
    enemy = max(7, strength * 5 + random.randint(0, 8))
    rt, rd, et, ed, margin = _roll_duel(ctx, roman, enemy)
    won = margin >= 0
    ui.screen(); ui.header(f"СРАЖЕНИЕ С ПЛЕМЕНЕМ {str(tribe.get('name', key)).upper()}", "🪓", group.get("name"))
    ui.info(f"Рим: {_dice_text(ctx, rd)} + {roman} = {rt}", "GREEN")
    ui.info(f"Племя: {_dice_text(ctx, ed)} + {enemy} = {et}", "RED")
    apply_battle_result(player, group, won, abs(margin), ctx, naval=False)
    if won:
        damage = max(1, min(strength, 1 + abs(margin) // 8 + artillery // 30))
        tribe["strength"] = max(0, strength - damage)
        tribe["relation"] = max(0, _i(tribe.get("relation", 40), 40) - random.randint(8, 18))
        reward = _price(player, ctx, 18 + damage * 12)
        glory = 4 + damage * 3
        player.gold += reward
        player.glory = _i(getattr(player, "glory", 0), 0) + glory
        text = f"Племя потеряло {damage} силы; осталось {tribe['strength']}. Добыча +{reward} золота, слава +{glory}."
        ui.wrap(text, "GREEN")
        gained = _grant_group_xp(group, 3 if tribe["strength"] else 5)
        if gained: ui.info(f"Группа получила {gained} очк. развития.", "PURPLE")
    else:
        tribe["strength"] = min(30, strength + (1 if random.random() < 0.45 else 0))
        player.unrest = min(100, _i(getattr(player, "unrest", 0), 0) + 1)
        text = f"Экспедиция отбита. Племя сохраняет силу {tribe['strength']}; беспорядки в Риме +1."
        ui.wrap(text, "RED")
    group["location"] = f"Фронтир: {tribe.get('name', key)}"
    group["target"] = str(tribe.get("name", key))
    group["stance"] = "offensive" if won else "refit"
    group["last_action_turn"] = _i(getattr(player, "turn", 1), 1)
    _operation_record(player, state, group, "barbarian", f"Поход против {tribe.get('name', key)}", text, ctx)
    ui.pause()


def _set_group_zone(player: Any, group: dict, zone: str, ctx: dict) -> None:
    group["naval_zone"] = str(zone)
    group["location"] = str(_dict(_dict(ctx.get("SEA_ZONES")).get(zone)).get("name", zone))
    for name in group.get("fleet_squadrons", []):
        sq = _squadron(player, name, ctx)
        if sq:
            sq["zone"] = str(zone)


def _naval_operation(player: Any, ctx: dict, ui: UI, state: dict) -> None:
    group = _select_group_for_operation(ui, player, state, ctx, naval=True)
    if not group: return
    zones = list(_dict(ctx.get("SEA_ZONES")).keys())
    if not zones:
        ui.info("Справочник морских зон недоступен.", "RED"); ui.pause(); return
    fleet = _fleet(player, ctx)
    ui.screen(); ui.header("МОРСКАЯ ОПЕРАЦИЯ ГРУППЫ", "⚓", group.get("name"))
    ui.table("Морские зоны", ["#", "Зона", "Контроль", "Пираты", "Блокада", "Погода"], [
        (str(i), _dict(_dict(ctx.get("SEA_ZONES")).get(z)).get("name", z), _dict(fleet.get("sea_zone_control")).get(z, 0),
         _dict(fleet.get("zone_piracy")).get(z, 0), _dict(fleet.get("zone_blockade")).get(z, 0), _dict(fleet.get("zone_weather")).get(z, "calm"))
        for i, z in enumerate(zones, 1)
    ], "CYAN")
    zp = ui.choice("  Зона (Q — назад): ", [str(i) for i in range(1, len(zones) + 1)] + ["Q"])
    if zp == "Q": return
    zone = zones[int(zp) - 1]
    missions = [
        ("pirates", "Охота на пиратов", "снижает пиратство и приносит добычу"),
        ("blockade", "Блокада побережья", "повышает давление и контроль зоны"),
        ("patrol", "Боевой патруль", "повышает контроль и готовность конвоев"),
        ("landing", "Подготовка десанта", "создаёт плацдарм для высадки группы"),
    ]
    for i, (_, name, desc) in enumerate(missions, 1): print(f"  {i}. {name} — {desc}")
    mp = ui.choice("  Операция: ", [str(i) for i in range(1, len(missions) + 1)] + ["Q"])
    if mp == "Q": return
    mission, mission_name, _ = missions[int(mp) - 1]
    p = group_power(player, group, ctx)
    sq_count = len(group.get("fleet_squadrons", []))
    ok, gold_cost, grain_cost = _pay_operation(player, group, ctx, 14 + sq_count * 6, 8 + sq_count * 3, ui)
    if not ok: ui.pause(); return
    if not _spend_command(group, 1, ui):
        player.gold += gold_cost; player.grain += grain_cost; ui.pause(); return
    _set_group_zone(player, group, zone, ctx)
    zone_def = _dict(_dict(ctx.get("SEA_ZONES")).get(zone))
    piracy = _i(_dict(fleet.get("zone_piracy")).get(zone, zone_def.get("base_pirates", 20)), 20)
    blockade = _i(_dict(fleet.get("zone_blockade")).get(zone, 0), 0)
    weather = str(_dict(fleet.get("zone_weather")).get(zone, "calm"))
    mission_bonus = {"pirates": p["mobility"] // 5, "blockade": p["naval"] // 8, "patrol": p["mobility"] // 4, "landing": _group_marines(player, group, ctx) // 4}[mission]
    weather_penalty = 8 if weather == "storm" else 3 if weather == "windy" else 0
    roman = max(7, p["naval"] // 3 + p["mobility"] // 7 + p["readiness"] // 10 + mission_bonus - weather_penalty)
    enemy = max(7, _i(zone_def.get("difficulty", 20), 20) // 2 + piracy // 3 + blockade // 4 + random.randint(0, 7))
    rt, rd, et, ed, margin = _roll_duel(ctx, roman, enemy)
    won = margin >= 0
    ui.screen(); ui.header(f"{mission_name.upper()}: {str(zone_def.get('name', zone)).upper()}", "🌊", group.get("name"))
    ui.info(f"Рим: {_dice_text(ctx, rd)} + {roman} = {rt}", "GREEN")
    ui.info(f"Противник: {_dice_text(ctx, ed)} + {enemy} = {et}", "RED")
    apply_battle_result(player, group, won, abs(margin), ctx, naval=True)
    controls = fleet.setdefault("sea_zone_control", {})
    piracies = fleet.setdefault("zone_piracy", {})
    blockades = fleet.setdefault("zone_blockade", {})
    preparations = fleet.setdefault("landing_preparations", {})
    if won:
        gain = random.randint(5, 11) + min(8, abs(margin) // 7)
        controls[zone] = _clamp(_i(controls.get(zone, 0), 0) + gain, 0, 100, 0)
        if mission == "pirates": piracies[zone] = _clamp(_i(piracies.get(zone, piracy), piracy) - random.randint(9, 18), 0, 100, 0)
        elif mission == "blockade": blockades[zone] = _clamp(_i(blockades.get(zone, 0), 0) + random.randint(8, 16), 0, 100, 0)
        elif mission == "patrol":
            piracies[zone] = _clamp(_i(piracies.get(zone, piracy), piracy) - random.randint(4, 10), 0, 100, 0)
            fleet["convoy_readiness"] = _clamp(_i(fleet.get("convoy_readiness", 35), 35) + 6, 0, 100, 35)
        else:
            preparations[zone] = _clamp(_i(preparations.get(zone, 0), 0) + random.randint(12, 22), 0, 100, 0)
        reward = _price(player, ctx, 20 + _i(zone_def.get("trade_value", 10), 10) + gain * 2)
        player.gold += reward
        player.glory = _i(getattr(player, "glory", 0), 0) + 7
        fleet["naval_tradition"] = _i(fleet.get("naval_tradition", 0), 0) + 3
        text = f"Победа: контроль +{gain}, добыча +{reward} золота, морская традиция +3."
        ui.wrap(text, "GREEN")
        gained = _grant_group_xp(group, 3)
        if gained: ui.info(f"Очки развития группы +{gained}.", "PURPLE")
    else:
        controls[zone] = _clamp(_i(controls.get(zone, 0), 0) - random.randint(4, 9), 0, 100, 0)
        piracies[zone] = _clamp(_i(piracies.get(zone, piracy), piracy) + random.randint(3, 8), 0, 100, 0)
        text = "Поражение: контроль моря снизился, пиратство усилилось."
        ui.wrap(text, "RED")
    group["stance"] = "intercept" if mission in {"pirates", "patrol"} else "offensive"
    group["target"] = str(zone_def.get("name", zone))
    group["last_action_turn"] = _i(getattr(player, "turn", 1), 1)
    _operation_record(player, state, group, "naval", mission_name, text, ctx)
    ui.pause()


def _amphibious_operation(player: Any, ctx: dict, ui: UI, state: dict) -> None:
    group = _select_group_for_operation(ui, player, state, ctx, naval=True, amphibious=True)
    if not group: return
    transport = _group_transport_capacity(player, group, ctx)
    if transport < 4:
        ui.info(f"Недостаточно транспортной вместимости: {transport}/4. Нужны транспорты или десантное развитие.", "RED")
        ui.pause(); return
    targets_data = _dict(ctx.get("MARITIME_LANDING_TARGETS"))
    province_by_name = ctx.get("province_by_name")
    owned = {str(p.get("name")) for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)}
    targets = []
    for name, data in targets_data.items():
        if name in owned: continue
        province = None
        if callable(province_by_name):
            try: province = province_by_name(name)
            except Exception: pass
        if not isinstance(province, dict):
            province = next((p for p in _list(ctx.get("PROVINCES_DATA")) if isinstance(p, dict) and p.get("name") == name), None)
        city = _next_city(player, province, ctx) if isinstance(province, dict) else None
        if province and city:
            targets.append((province, city, _dict(data)))
    if not targets:
        ui.info("Нет доступных прибрежных целей.", "GRAY"); ui.pause(); return
    fleet = _fleet(player, ctx)
    zones = _dict(ctx.get("SEA_ZONES"))
    ui.screen(); ui.header("ДЕСАНТ ГРУППЫ АРМИЙ", "⚓", f"{group.get('name')} • вместимость {transport}")
    ui.table("Прибрежные цели", ["#", "Провинция", "Город", "Море", "Контр.", "Подгот.", "Сложн."], [
        (str(i), province.get("name"), city.get("name"), _dict(zones.get(data.get("zone"))).get("name", data.get("zone")),
         _dict(fleet.get("sea_zone_control")).get(data.get("zone"), 0), _dict(fleet.get("landing_preparations")).get(data.get("zone"), 0), data.get("difficulty", 40))
        for i, (province, city, data) in enumerate(targets, 1)
    ], "CYAN")
    pick = ui.choice("  Цель (Q — назад): ", [str(i) for i in range(1, len(targets) + 1)] + ["Q"])
    if pick == "Q": return
    province, city, data = targets[int(pick) - 1]
    zone = str(data.get("zone"))
    p = group_power(player, group, ctx)
    difficulty = _i(data.get("difficulty", 40), 40)
    # Морская переброска к городу также ведёт к обычному боевому штурму:
    # золото и зерно за нажатие кнопки не списываются.
    if not _spend_command(group, 2, ui):
        ui.pause(); return
    _set_group_zone(player, group, zone, ctx)
    control = _i(_dict(fleet.get("sea_zone_control")).get(zone, 0), 0)
    preparation = _i(_dict(fleet.get("landing_preparations")).get(zone, 0), 0)
    marines = _group_marines(player, group, ctx)
    city_damage = 0
    damage_fn = ctx.get("city_siege_damage")
    if callable(damage_fn):
        try: city_damage = _i(damage_fn(player, province.get("name"), city.get("name")), 0)
        except Exception: pass
    roman = max(8, p["naval"] // 5 + p["land"] // 15 + marines // 3 + transport * 2 + control // 8 + preparation // 5 + _i(_upgrade_effects(group).get("amphibious_bonus", 0), 0))
    enemy = max(8, difficulty // 2 + _i(city.get("difficulty", 3), 3) * 3 + max(0, 100 - city_damage) // 10)
    rt, rd, et, ed, margin = _roll_duel(ctx, roman, enemy)
    won = margin >= 0
    ui.screen(); ui.header(f"ДЕСАНТ НА {str(city.get('name')).upper()}", "⚓", f"{group.get('name')} • {province.get('name')}")
    ui.info(f"Рим: {_dice_text(ctx, rd)} + {roman} = {rt}", "GREEN")
    ui.info(f"Береговая оборона: {_dice_text(ctx, ed)} + {enemy} = {et}", "RED")
    apply_battle_result(player, group, won, abs(margin), ctx, naval=False)
    preparations = fleet.setdefault("landing_preparations", {})
    controls = fleet.setdefault("sea_zone_control", {})
    if won:
        preparations[zone] = max(0, preparation - 25)
        controls[zone] = _clamp(control + random.randint(3, 8), 0, 100, 0)
        annexed, message = _capture_city(player, province, city, "army_group_amphibious", ctx, ui)
        player.glory = _i(getattr(player, "glory", 0), 0) + 12
        gained = _grant_group_xp(group, 7 if annexed else 5)
        text = f"Десант удался. {message} Слава +12."
        ui.wrap(text, "GREEN")
        if gained: ui.info(f"Очки развития группы +{gained}.", "PURPLE")
    else:
        preparations[zone] = max(0, preparation - 18)
        controls[zone] = _clamp(control - random.randint(4, 9), 0, 100, 0)
        # Неудачная высадка дополнительно повреждает корабли группы.
        apply_battle_result(player, group, False, max(1, abs(margin) // 2), ctx, naval=True)
        text = "Высадка захлебнулась у берега; транспорты и десант понесли потери."
        ui.wrap(text, "RED")
    group["location"] = str(city.get("name")) if won else str(_dict(zones.get(zone)).get("name", zone))
    group["target"] = str(city.get("name"))
    group["stance"] = "siege" if won else "refit"
    group["last_action_turn"] = _i(getattr(player, "turn", 1), 1)
    _operation_record(player, state, group, "amphibious", f"Десант на {city.get('name')}", text, ctx)
    ui.pause()


# ─── ROMA 4.1: ЕДИНЫЙ ВОЕННЫЙ ШТАБ КОНКРЕТНОЙ ПРОВИНЦИИ ──────────────────
# Операции больше не выбирают цель внутри Exercitus Universalis. Карта передаёт
# сюда уже выбранную провинцию, а штаб назначает группу и способ вторжения.

TRIBE_PROVINCE_HINTS: dict[str, set[str]] = {
    "arverni": {"Gallia", "Gallia Narbonensis", "Aquitania"},
    "aedui": {"Gallia", "Gallia Narbonensis"},
    "belgae": {"Belgica", "Gallia"},
    "suebi": {"Germania Inferior", "Germania Superior", "Magna Germania"},
    "marcomanni": {"Germania Superior", "Magna Germania", "Dacia"},
    "daci": {"Dacia", "Thracia"},
    "getae": {"Dacia", "Thracia"},
    "sarmatians": {"Dacia", "Armenia", "Mesopotamia"},
    "picts": {"Caledonia", "Britannia"},
    "iceni": {"Britannia"},
}


def group_transport_need(group: dict) -> int:
    """Сколько грузовых единиц занимает обычная армия при морской переброске."""
    return max(
        0,
        len(_list(group.get("legions"))) * 3
        + len(_list(group.get("auxilia")))
        + sum(max(0, _i(v, 0)) for v in _dict(group.get("artillery")).values()),
    )


def province_operation_snapshot(player: Any, province: dict | str, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    if not isinstance(province, dict):
        fn = ctx.get("province_by_name")
        province = fn(str(province)) if callable(fn) else None
    province = province if isinstance(province, dict) else {}
    name = str(province.get("name", ""))
    routes_fn = ctx.get("province_attack_routes")
    if callable(routes_fn):
        try:
            routes = [str(x) for x in _list(routes_fn(player, province))]
        except Exception:
            routes = []
    else:
        routes = []
        if bool(province.get("land_access", True)):
            routes.append("land")
        if bool(province.get("sea_access", False)):
            routes.append("sea")
    intel = _clamp(_dict(state.get("province_intel")).get(name, 0), 0, 100, 0)
    city = _next_city(player, province, ctx) if province else None
    return {
        "province": province,
        "name": name,
        "routes": routes,
        "intel": intel,
        "city": city,
        "sea_zone": province.get("sea_zone"),
        "landing_difficulty": _i(province.get("landing_difficulty", 40), 40, 0, 100),
    }


def _province_group_candidates(player: Any, state: dict, ctx: dict, route: str, *, fleet_only: bool = False) -> list[tuple[dict, dict, int, int]]:
    rows: list[tuple[dict, dict, int, int]] = []
    for group in state.get("groups", []):
        power = group_power(player, group, ctx)
        if power.get("readiness", 0) < 12 or _i(group.get("command_points", 0), 0) <= 0:
            continue
        if fleet_only:
            if not group.get("fleet_squadrons") or power.get("naval", 0) <= 0:
                continue
        else:
            # Both legions and auxilia are independent fighting formations.
            if (not group.get("legions") and not group.get("auxilia")) or power.get("land", 0) <= 0:
                continue
        transport = _group_transport_capacity(player, group, ctx)
        need = group_transport_need(group)
        if route == "sea" and not fleet_only:
            if not group.get("fleet_squadrons") or transport < need:
                continue
        rows.append((group, power, transport, need))
    return rows



def _select_group_for_province(ui: UI, player: Any, state: dict, ctx: dict, route: str, *, fleet_only: bool = False) -> dict | None:
    candidates = _province_group_candidates(player, state, ctx, route, fleet_only=fleet_only)
    if not candidates:
        if route == "sea" and not fleet_only:
            ui.info("Нет сухопутной группы (легионы или ауксилии) с прикреплённым флотом и достаточной транспортной вместимостью.", "RED")
        elif fleet_only:
            ui.info("Нет боеспособной группы с прикреплёнными эскадрами.", "RED")
        else:
            ui.info("Нет боеспособной группы с легионами или ауксилиями и доступными приказами.", "RED")
        ui.pause()
        return None
    ui.table(
        "Группы, способные выполнить приказ",
        ["#", "Группа", "Позиция", "Суша", "Осада", "Море", "Гот.", "ОД", "Транспорт"],
        [
            (
                str(i), group.get("name"), group.get("location"), power.get("land", 0), power.get("siege", 0),
                power.get("naval", 0), power.get("readiness", 0), group.get("command_points", 0),
                f"{transport}/{need}" if route == "sea" else "—",
            )
            for i, (group, power, transport, need) in enumerate(candidates, 1)
        ],
        "CYAN" if route == "sea" or fleet_only else "RED",
    )
    pick = ui.choice("  Назначить группу (Q — назад): ", [str(i) for i in range(1, len(candidates) + 1)] + ["Q"])
    return None if pick == "Q" else candidates[int(pick) - 1][0]


def _province_city_defense(player: Any, province: dict, city: dict, ctx: dict) -> tuple[int, int, int]:
    damage_fn = ctx.get("city_siege_damage")
    damage = 0
    if callable(damage_fn):
        try:
            damage = _i(damage_fn(player, province.get("name"), city.get("name")), 0, 0, 100)
        except Exception:
            pass
    difficulty = _i(city.get("difficulty", 3), 3, 1, 10)
    base = difficulty * 2 + _i(province.get("wealth", 2), 2) + 2
    strength_fn = ctx.get("city_strength_for_attack")
    if callable(strength_fn):
        try:
            enemy_def = next(
                (e for e in _list(ctx.get("ENEMY_FACTIONS")) if isinstance(e, dict) and e.get("region") == province.get("name")),
                None,
            )
            diff_fn = getattr(player, "diff", None)
            mult = 1.0
            if callable(diff_fn):
                mult = _f(_dict(diff_fn()).get("enemy_strength_mult", 1.0), 1.0)
            base = _i(strength_fn(city, province, enemy_def, mult), base)
        except Exception:
            pass
    return damage, difficulty, max(1, base)


def _province_artillery_support(player: Any, group: dict, ctx: dict) -> tuple[int, int]:
    artillery = _assigned_artillery_power(group, ctx, "siege")
    count = _assigned_artillery_count(group)
    if count <= 0:
        return 0, 0
    stock = _i(getattr(player, "artillery_supplies", 0), 0)
    raw_cost = max(1, count * 2)
    discount = min(0.70, _upgrade_effects(group).get("artillery_supply_discount", 0.0))
    cost = max(1, int(round(raw_cost * (1.0 - discount))))
    if stock < cost:
        return artillery // 3, 0
    player.artillery_supplies = max(0, stock - cost)
    return artillery, cost


def _execute_province_city_assault(player: Any, province: dict, route: str, ctx: dict, ui: UI, state: dict) -> None:
    """Fast strategic assault: a city falls in one strong or two normal victories."""
    city = _next_city(player, province, ctx)
    if not city:
        ui.info("В провинции не осталось непокорённых городов.", "GREEN")
        annex = ctx.get("annex_province_after_campaign")
        if callable(annex):
            try:
                captured, unlocked = annex(player, province)
                ui.info(f"Провинция {captured.get('name', province.get('name'))} присоединена.", "GREEN")
                if unlocked:
                    ui.info("Открыты части: " + ", ".join(unlocked), "CYAN")
            except Exception as exc:
                ui.info(f"Присоединение не завершено: {exc}", "RED")
        ui.pause()
        return

    group = _select_group_for_province(ui, player, state, ctx, route)
    if not group:
        return
    power = group_power(player, group, ctx)
    damage, difficulty, base_city = _province_city_defense(player, province, city, ctx)
    remaining = max(0, 100 - damage)
    intel = _clamp(_dict(state.get("province_intel")).get(str(province.get("name")), 0), 0, 100, 0)
    if route == "sea":
        transport = _group_transport_capacity(player, group, ctx)
        need = group_transport_need(group)
        if transport < need:
            ui.info(f"Транспортная вместимость {transport}/{need}: переброска невозможна.", "RED"); ui.pause(); return
        landing = _i(province.get("landing_difficulty", 40), 40, 0, 100)
        command_cost = 2
    else:
        landing = 0
        command_cost = 1
    if not _spend_command(group, command_cost, ui):
        ui.pause(); return

    artillery, art_spent = _province_artillery_support(player, group, ctx)
    upgrade = _upgrade_effects(group)
    fleet = _fleet(player, ctx)
    zone = str(province.get("sea_zone") or "")
    control = _i(_dict(fleet.get("sea_zone_control")).get(zone, 0), 0)
    preparation = _i(_dict(fleet.get("landing_preparations")).get(zone, 0), 0)
    legion_count = len(group.get("legions", []))
    aux_count = len(group.get("auxilia", []))

    if route == "sea":
        _set_group_zone(player, group, zone, ctx)
        transport_margin = max(0, _group_transport_capacity(player, group, ctx) - group_transport_need(group))
        roman = max(10, power["attack"] // 5 + power["land"] // 9 + power["naval"] // 9 + power["siege"] // 6
                    + power["readiness"] // 8 + transport_margin * 2 + control // 8 + preparation // 6 + intel // 9
                    + _i(upgrade.get("amphibious_bonus", 0), 0))
        enemy = max(10, int(base_city * 1.45) + remaining // 11 + difficulty + landing // 7)
        header, icon = "МОРСКАЯ ПЕРЕБРОСКА И ШТУРМ", "⚓"
    else:
        roman = max(10, power["attack"] // 5 + power["land"] // 8 + power["siege"] // 5
                    + power["readiness"] // 8 + intel // 10)
        enemy = max(10, int(base_city * 1.40) + remaining // 12 + difficulty)
        header, icon = "СТРЕМИТЕЛЬНЫЙ ШТУРМ", "⚔"

    rt, rd, et, ed, margin = _roll_duel(ctx, roman, enemy)
    won = margin >= 0
    ui.screen()
    ui.header(f"{header}: {str(city.get('name')).upper()}", icon, f"{group.get('name')} • {province.get('name')}")
    ui.info(f"Рим: {_dice_text(ctx, rd)} + {roman} = {rt}", "GREEN")
    ui.info(f"Оборона: {_dice_text(ctx, ed)} + {enemy} = {et}", "RED")
    ui.info(f"Состав: легионы {legion_count}, ауксилии {aux_count}; мощь {power.get('land', 0)}.", "CYAN")
    if route == "sea":
        ui.info(f"Флот: контроль {control}, подготовка {preparation}, транспорт {_group_transport_capacity(player, group, ctx)}/{group_transport_need(group)}.", "CYAN")

    if won:
        strong_victory = margin >= 8 or roman >= int(enemy * 1.22)
        raw_damage = 100 - damage if strong_victory else max(55, 48 + margin * 2 + power["siege"] // 18 + artillery // 18)
        # A second victorious assault always finishes the city.
        if damage >= 45:
            raw_damage = 100 - damage
    else:
        raw_damage = max(10, 12 + power["siege"] // 35 + artillery // 30 + max(-6, margin) // 3)
    raw_damage = max(1, min(100 - damage, raw_damage))

    apply_damage = ctx.get("apply_city_siege_damage")
    actual, total_damage, remaining_after = raw_damage, min(100, damage + raw_damage), max(0, 100 - damage - raw_damage)
    if callable(apply_damage):
        try:
            actual, total_damage, remaining_after = apply_damage(player, province.get("name"), city.get("name"), raw_damage)
        except Exception:
            pass

    apply_battle_result(player, group, won, abs(margin), ctx, naval=False)
    if route == "sea" and not won:
        apply_battle_result(player, group, False, max(1, abs(margin) // 2), ctx, naval=True)
    group["target"] = str(city.get("name"))
    group["last_action_turn"] = _i(getattr(player, "turn", 1), 1)
    group["location"] = str(city.get("name")) if won else (str(_dict(_dict(ctx.get("SEA_ZONES")).get(zone)).get("name", zone)) if route == "sea" else str(province.get("name")))
    group["stance"] = "siege" if won and total_damage < 100 else "occupation" if won else "refit"
    if route == "sea":
        preparations = fleet.setdefault("landing_preparations", {})
        preparations[zone] = max(0, preparation - (22 if won else 14))

    state.setdefault("province_intel", {})[str(province.get("name"))] = max(0, intel - 12)
    ui.info(f"Оборона города: урон +{actual}%, всего {total_damage}%, осталось {remaining_after}%.", "GOLD")
    if _assigned_artillery_count(group):
        ui.info(f"Осадная поддержка {artillery}; боезапас -{art_spent}." if art_spent else "Боезапаса не хватило: артиллерия действовала с пониженной мощью.", "CYAN")

    title = f"{('Морская высадка' if route == 'sea' else 'Штурм')} {city.get('name')}"
    if won and total_damage >= 100:
        annexed, message = _capture_city(player, province, city, f"army_group_{route}_assault", ctx, ui)
        gained = _grant_group_xp(group, 9 if route == "sea" and annexed else 8 if annexed else 7)
        player.glory = _i(getattr(player, "glory", 0), 0) + (14 if route == "sea" else 10)
        text = message
        ui.wrap(message, "GREEN")
        if gained:
            ui.info(f"Новый уровень группы: {group.get('level')}; очки развития +{gained}.", "PURPLE")
    elif won:
        text = f"Первая атака прорвала оборону на {total_damage}%. Следующая победа возьмёт город."
        ui.wrap(text, "GOLD")
    else:
        text = f"Атака отбита, но укрепления потеряли {actual}% прочности."
        ui.wrap(text, "RED")
    _operation_record(player, state, group, f"province_{route}", title, text, ctx)
    ui.pause()



def _province_blockade_operation(player: Any, province: dict, ctx: dict, ui: UI, state: dict) -> None:
    zone = str(province.get("sea_zone") or "")
    if not zone:
        ui.info("У провинции нет морского театра.", "RED"); ui.pause(); return
    group = _select_group_for_province(ui, player, state, ctx, "sea", fleet_only=True)
    if not group:
        return
    power = group_power(player, group, ctx)
    fleet = _fleet(player, ctx)
    control = _i(_dict(fleet.get("sea_zone_control")).get(zone, 0), 0)
    piracy = _i(_dict(fleet.get("zone_piracy")).get(zone, 20), 20)
    difficulty = _i(_dict(_dict(ctx.get("SEA_ZONES")).get(zone)).get("difficulty", 35), 35)
    ok, gold_cost, grain_cost = _pay_operation(player, group, ctx, 16 + len(group.get("fleet_squadrons", [])) * 6, 8, ui)
    if not ok:
        ui.pause(); return
    if not _spend_command(group, 1, ui):
        player.gold += gold_cost; player.grain += grain_cost; ui.pause(); return
    _set_group_zone(player, group, zone, ctx)
    roman = max(8, power["naval"] // 6 + power["mobility"] // 8 + power["readiness"] // 10 + control // 10)
    enemy = max(8, difficulty // 2 + piracy // 5 + _i(province.get("landing_difficulty", 40), 40) // 8)
    rt, rd, et, ed, margin = _roll_duel(ctx, roman, enemy)
    won = margin >= 0
    ui.screen(); ui.header(f"БЛОКАДА: {str(province.get('name')).upper()}", "⚓", group.get("name"))
    ui.info(f"Римский флот: {_dice_text(ctx, rd)} + {roman} = {rt}", "GREEN")
    ui.info(f"Береговая оборона: {_dice_text(ctx, ed)} + {enemy} = {et}", "RED")
    apply_battle_result(player, group, won, abs(margin), ctx, naval=True)
    blockades = fleet.setdefault("zone_blockade", {})
    controls = fleet.setdefault("sea_zone_control", {})
    preparations = fleet.setdefault("landing_preparations", {})
    if won:
        gain = random.randint(8, 16) + max(0, margin // 10)
        blockades[zone] = _clamp(_i(blockades.get(zone, 0), 0) + gain, 0, 100, 0)
        controls[zone] = _clamp(control + random.randint(3, 8), 0, 100, 0)
        preparations[zone] = _clamp(_i(preparations.get(zone, 0), 0) + random.randint(5, 12), 0, 100, 0)
        text = f"Блокада установлена: давление +{gain}, контроль моря {controls[zone]}, подготовка переправы {preparations[zone]}."
        ui.wrap(text, "GREEN")
        _grant_group_xp(group, 3)
    else:
        controls[zone] = _clamp(control - random.randint(3, 8), 0, 100, 0)
        text = f"Блокадная линия прорвана; контроль моря снижен до {controls[zone]}."
        ui.wrap(text, "RED")
    group["target"] = str(province.get("name"))
    group["stance"] = "intercept" if won else "refit"
    group["last_action_turn"] = _i(getattr(player, "turn", 1), 1)
    _operation_record(player, state, group, "province_blockade", f"Блокада {province.get('name')}", text, ctx)
    ui.pause()


def _province_prepare_sea_operation(player: Any, province: dict, ctx: dict, ui: UI, state: dict) -> None:
    zone = str(province.get("sea_zone") or "")
    if not zone:
        ui.info("У провинции нет морского театра.", "RED"); ui.pause(); return
    group = _select_group_for_province(ui, player, state, ctx, "sea", fleet_only=True)
    if not group:
        return
    power = group_power(player, group, ctx)
    ok, gold_cost, grain_cost = _pay_operation(player, group, ctx, 10 + len(group.get("fleet_squadrons", [])) * 4, 6, ui)
    if not ok:
        ui.pause(); return
    if not _spend_command(group, 1, ui):
        player.gold += gold_cost; player.grain += grain_cost; ui.pause(); return
    _set_group_zone(player, group, zone, ctx)
    fleet = _fleet(player, ctx)
    preparations = fleet.setdefault("landing_preparations", {})
    old = _i(preparations.get(zone, 0), 0)
    gain = max(5, min(25, power["naval"] // 12 + _group_transport_capacity(player, group, ctx) + random.randint(2, 7)))
    preparations[zone] = _clamp(old + gain, 0, 100, 0)
    group["target"] = str(province.get("name"))
    group["stance"] = "intercept"
    group["last_action_turn"] = _i(getattr(player, "turn", 1), 1)
    text = f"Флот разведал побережье и подготовил переправу: готовность {old} → {preparations[zone]}."
    ui.wrap(text, "GREEN")
    _operation_record(player, state, group, "province_preparation", f"Подготовка переправы к {province.get('name')}", text, ctx)
    ui.pause()


def _province_recon_operation(player: Any, province: dict, ctx: dict, ui: UI, state: dict) -> None:
    routes = province_operation_snapshot(player, province, ctx)["routes"]
    route = "land" if "land" in routes else "sea"
    group = _select_group_for_province(ui, player, state, ctx, route, fleet_only=(route == "sea"))
    if not group:
        return
    power = group_power(player, group, ctx)
    ok, gold_cost, grain_cost = _pay_operation(player, group, ctx, 8, 4, ui)
    if not ok:
        ui.pause(); return
    if not _spend_command(group, 1, ui):
        player.gold += gold_cost; player.grain += grain_cost; ui.pause(); return
    if route == "sea" and province.get("sea_zone"):
        _set_group_zone(player, group, str(province.get("sea_zone")), ctx)
    difficulty = _i(province.get("landing_difficulty", 35), 35) if route == "sea" else 25 + _i(province.get("wealth", 2), 2) * 4
    roman = max(8, power["mobility"] // 5 + power["readiness"] // 8 + (power["naval"] // 10 if route == "sea" else power["land"] // 18))
    enemy = max(8, difficulty // 3 + random.randint(4, 12))
    rt, rd, et, ed, margin = _roll_duel(ctx, roman, enemy)
    won = margin >= 0
    current = _clamp(_dict(state.get("province_intel")).get(str(province.get("name")), 0), 0, 100, 0)
    gain = random.randint(18, 32) + max(0, margin // 4) if won else random.randint(4, 10)
    state.setdefault("province_intel", {})[str(province.get("name"))] = _clamp(current + gain, 0, 100, 0)
    ui.screen(); ui.header(f"РАЗВЕДКА: {str(province.get('name')).upper()}", "🔭", group.get("name"))
    ui.info(f"Рим: {_dice_text(ctx, rd)} + {roman} = {rt}", "GREEN")
    ui.info(f"Контрразведка: {_dice_text(ctx, ed)} + {enemy} = {et}", "RED")
    text = f"Разведданные {current} → {state['province_intel'][str(province.get('name'))]}%. Следующий штурм получит бонус и потратит часть сведений."
    ui.wrap(text, "GREEN" if won else "GOLD")
    group["target"] = str(province.get("name"))
    group["last_action_turn"] = _i(getattr(player, "turn", 1), 1)
    _operation_record(player, state, group, "province_recon", f"Разведка {province.get('name')}", text, ctx)
    ui.pause()


def _barbarian_keys_for_province(player: Any, province_name: str) -> list[str]:
    tribes = _dict(getattr(player, "barbarian_tribes", {}))
    return [
        key for key, tribe in tribes.items()
        if isinstance(tribe, dict) and _i(tribe.get("strength", 0), 0) > 0
        and province_name in TRIBE_PROVINCE_HINTS.get(str(key), set())
    ]


def _barbarian_operation_for_province(player: Any, province: dict, ctx: dict, ui: UI, state: dict) -> None:
    keys = _barbarian_keys_for_province(player, str(province.get("name")))
    if not keys:
        ui.info("На этом направлении нет племени из действующего реестра.", "GRAY"); ui.pause(); return
    group = _select_group_for_province(ui, player, state, ctx, "land")
    if not group:
        return
    tribes = _dict(getattr(player, "barbarian_tribes", {}))
    rows = [(str(i), tribes[key].get("name", key), tribes[key].get("chief", "—"), tribes[key].get("strength", 0), tribes[key].get("relation", 0)) for i, key in enumerate(keys, 1)]
    ui.table("Племена этого фронтира", ["#", "Племя", "Вождь", "Сила", "Отношение"], rows, "RED")
    pick = ui.choice("  Цель (Q — назад): ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
    if pick == "Q":
        return
    key = keys[int(pick) - 1]
    tribe = tribes[key]
    power = group_power(player, group, ctx)
    strength = _i(tribe.get("strength", 5), 5, 1)
    ok, gold_cost, grain_cost = _pay_operation(player, group, ctx, 12 + strength * 4, 10 + (len(group.get("legions", [])) + len(group.get("auxilia", []))) * 4, ui)
    if not ok:
        ui.pause(); return
    if not _spend_command(group, 1, ui):
        player.gold += gold_cost; player.grain += grain_cost; ui.pause(); return
    artillery = _assigned_artillery_power(group, ctx, "anti_barbarian")
    roman = max(7, power["land"] // 12 + power["attack"] // 10 + power["mobility"] // 8 + power["readiness"] // 10 + artillery // 5 + _i(_upgrade_effects(group).get("barbarian_bonus", 0), 0))
    enemy = max(7, strength * 5 + random.randint(0, 8))
    rt, rd, et, ed, margin = _roll_duel(ctx, roman, enemy)
    won = margin >= 0
    ui.screen(); ui.header(f"ФРОНТИР {str(province.get('name')).upper()}: {str(tribe.get('name', key)).upper()}", "🪓", group.get("name"))
    ui.info(f"Рим: {_dice_text(ctx, rd)} + {roman} = {rt}", "GREEN")
    ui.info(f"Племя: {_dice_text(ctx, ed)} + {enemy} = {et}", "RED")
    apply_battle_result(player, group, won, abs(margin), ctx, naval=False)
    if won:
        loss = max(1, min(strength, 1 + abs(margin) // 8 + artillery // 30))
        tribe["strength"] = max(0, strength - loss)
        reward = _price(player, ctx, 18 + loss * 12)
        player.gold += reward
        player.glory = _i(getattr(player, "glory", 0), 0) + 4 + loss * 3
        text = f"Племя потеряло {loss} силы; осталось {tribe['strength']}. Добыча +{reward} золота."
        ui.wrap(text, "GREEN")
        _grant_group_xp(group, 3 if tribe["strength"] else 5)
    else:
        text = "Экспедиция отбита; группа отходит к укреплённому лагерю."
        ui.wrap(text, "RED")
    group["location"] = str(province.get("name"))
    group["target"] = str(tribe.get("name", key))
    group["stance"] = "offensive" if won else "refit"
    group["last_action_turn"] = _i(getattr(player, "turn", 1), 1)
    _operation_record(player, state, group, "province_barbarian", f"Поход против {tribe.get('name', key)} в {province.get('name')}", text, ctx)
    ui.pause()


def open_province_operations(player: Any, province: dict | str, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx)
    ui = UI(ctx)
    state = ensure_state(player, ctx)
    if not isinstance(province, dict):
        fn = ctx.get("province_by_name")
        province = fn(str(province)) if callable(fn) else None
    if not isinstance(province, dict):
        ui.info("Провинция не найдена в карте.", "RED"); ui.pause(); return

    while True:
        state = ensure_state(player, ctx)
        snap = province_operation_snapshot(player, province, ctx)
        city = snap.get("city")
        if not city:
            ui.info("Все города провинции уже покорены.", "GREEN")
            annex = ctx.get("annex_province_after_campaign")
            if callable(annex):
                try:
                    annex(player, province)
                except Exception:
                    pass
            ui.pause(); return
        route_text = " / ".join("сухопутный поход" if route == "land" else "морская переброска" for route in snap["routes"])
        zone_name = _dict(_dict(ctx.get("SEA_ZONES")).get(snap.get("sea_zone"))).get("name", snap.get("sea_zone") or "—")
        damage_fn = ctx.get("city_siege_damage")
        damage = 0
        if callable(damage_fn):
            try:
                damage = _i(damage_fn(player, province.get("name"), city.get("name")), 0)
            except Exception:
                pass
        ui.screen(); ui.header(f"ШТАБ ПРОВИНЦИИ {str(province.get('name')).upper()}", "🦅", f"Цель: {city.get('name')} • разведданные {snap['intel']}%")
        ui.table("Оперативная обстановка", ["Показатель", "Значение"], [
            ("Доступные маршруты", route_text or "нет"),
            ("Следующий город", city.get("name")),
            ("Сложность", f"{city.get('difficulty', 3)}/10"),
            ("Оборона", f"{100-damage}%"),
            ("Морской театр", zone_name if snap.get("sea_zone") else "—"),
            ("Сложность морской переброски", snap.get("landing_difficulty") if "sea" in snap["routes"] else "—"),
        ], "RED")
        ui.info("Обычный штурм не требует золота или зерна. Расходуются приказы группы; осадные машины используют только свой боезапас.", "GREEN")

        options: list[str] = ["R", "Q"]
        print("  R. Разведать провинцию")
        if "land" in snap["routes"]:
            print("  1. Сухопутный поход и обычный штурм группой армий")
            options.append("1")
        else:
            print("  1. Сухопутный поход [нет сухопутного маршрута]")
        if "sea" in snap["routes"]:
            print("  2. Морская переброска группы армий и обычный штурм")
            print("  3. Блокада побережья")
            print("  4. Подготовить переправу и место высадки")
            options.extend(["2", "3", "4"])
        else:
            print("  2. Морская переброска [провинция недоступна с моря]")
        if _barbarian_keys_for_province(player, str(province.get("name"))):
            print("  B. Экспедиция против племён этого фронтира")
            options.append("B")
        print("  D. Вражеские кампании в этой провинции")
        print("  W. Войны держав и фронты")
        print("  Q. Назад")
        options.extend(["D", "W"])
        ch = ui.choice("\n  Приказ: ", options)
        if ch == "Q":
            return
        if ch == "1":
            _execute_province_city_assault(player, province, "land", ctx, ui, state)
        elif ch == "2":
            _execute_province_city_assault(player, province, "sea", ctx, ui, state)
        elif ch == "3":
            _province_blockade_operation(player, province, ctx, ui, state)
        elif ch == "4":
            _province_prepare_sea_operation(player, province, ctx, ui, state)
        elif ch == "R":
            _province_recon_operation(player, province, ctx, ui, state)
        elif ch == "B":
            _barbarian_operation_for_province(player, province, ctx, ui, state)
        elif ch == "D":
            module = ctx.get("WAR_DIRECTOR_3")
            if module is not None and hasattr(module, "open_province_menu"):
                module.open_province_menu(player, str(province.get("name")), ctx)
            elif module is not None and hasattr(module, "open_menu"):
                module.open_menu(player, ctx)
            else:
                ui.info("Bellum Universale недоступен.", "RED"); ui.pause()
        elif ch == "W":
            module = ctx.get("WARFARE_AI")
            if module is not None and hasattr(module, "open_province_menu"):
                module.open_province_menu(player, str(province.get("name")), ctx)
            elif module is not None and hasattr(module, "open_menu"):
                module.open_menu(player, ctx)
            else:
                ui.info("Модуль прямых войн недоступен.", "RED"); ui.pause()

def _operations_menu(ui: UI, player: Any, state: dict, ctx: dict) -> None:
    while True:
        ui.screen(); ui.header("ЦЕНТР ОПЕРАЦИЙ", "⚔", "Одна группа — один субъект войны на суше и на море")
        print("  1. Обычный штурм города")
        print("  2. Экспедиция против варваров")
        print("  3. Морская операция группы")
        print("  4. Морская переброска и обычный штурм города")
        print("  5. Активные вражеские кампании Bellum Universale")
        print("  6. Прямые войны держав и фронты")
        print("  7. Разведка вражеского штаба")
        print("  8. Варварский мир: племена, лагеря, миграции и федераты")
        print("  Q. Назад")
        ch = ui.choice("\n  Операция: ", ["1", "2", "3", "4", "5", "6", "7", "8", "Q"])
        if ch == "Q": return
        if ch == "1": _city_operation(player, ctx, ui, state)
        elif ch == "2": _barbarian_operation(player, ctx, ui, state)
        elif ch == "3": _naval_operation(player, ctx, ui, state)
        elif ch == "4": _amphibious_operation(player, ctx, ui, state)
        elif ch == "5":
            module = ctx.get("WAR_DIRECTOR_3")
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
            else: ui.info("Bellum Universale недоступен.", "RED"); ui.pause()
        elif ch == "6":
            module = ctx.get("WARFARE_AI")
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
            else: ui.info("Модуль прямых войн недоступен.", "RED"); ui.pause()
        elif ch == "7":
            fn = ctx.get("enemy_ai_headquarters_menu")
            if callable(fn): fn(player)
            else: ui.info("Вражеский штаб недоступен.", "RED"); ui.pause()
        elif ch == "8":
            fn = ctx.get("barbarian_menu")
            if callable(fn): fn(player)
            else:
                module = ctx.get("BARBARIAN_WORLD")
                if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
                else: ui.info("Полный варварский мир недоступен.", "RED"); ui.pause()


def _pick_assignment_group(ui: UI, player: Any, state: dict, ctx: dict, category: str) -> dict | None:
    candidates = []
    for group in state.get("groups", []):
        used = sum(_dict(group.get("artillery")).values()) if category == "artillery" else len(group.get(category, []))
        cap = group_capacity(group, category)
        if used < cap:
            candidates.append((group, used, cap))
    if not candidates:
        return None
    for i, (group, used, cap) in enumerate(candidates, 1): print(f"  {i}. {group.get('name')} — {used}/{cap}")
    pick = ui.choice("  Прикрепить к группе (Q — оставить в резерве): ", [str(i) for i in range(1, len(candidates) + 1)] + ["Q"])
    return None if pick == "Q" else candidates[int(pick) - 1][0]


def _shop_legion(ui: UI, player: Any, state: dict, ctx: dict) -> None:
    cost_fn = ctx.get("legion_recruitment_cost")
    base_cost = _i(cost_fn(player), 80) if callable(cost_fn) else _price(player, ctx, 80 + len(_list(getattr(player, "legions", []))) * 25)
    tiers = [
        ("1", "Новый легион", "качество 5, сила 50", 1.0, 5, 50, 80, 0, False, False),
        ("2", "Ветеранский легион", "качество 8, сила 90, ветераны", 3.0, 8, 90, 95, 5, True, False),
        ("3", "Элитный легион", "полная прокачка: 10/10, сила и мораль 100", 6.0, 10, 100, 100, 12, True, True),
    ]
    ui.screen(); ui.header("НАБОР ЛЕГИОНА", "🛡", "Можно сразу купить обученное и полностью боеспособное соединение")
    ui.info(f"Казна: {getattr(player, 'gold', 0)}", "GOLD")
    ui.table("Уровни подготовки", ["#", "Легион", "Состояние", "Цена"], [
        (key, name, desc, max(1, int(round(base_cost * mult)))) for key, name, desc, mult, *_ in tiers
    ], "GOLD")
    pick = ui.choice("  Уровень (Q — назад): ", ["1", "2", "3", "Q"])
    if pick == "Q": return
    row = next(t for t in tiers if t[0] == pick)
    _, tier_name, _, mult, quality, strength, morale, battles, veterans, elite = row
    cost = max(1, int(round(base_cost * mult)))
    if _i(getattr(player, "gold", 0), 0) < cost:
        ui.info(f"Недостаточно золота: нужно {cost}.", "RED"); ui.pause(); return
    cls = ctx.get("Legion")
    if cls is None:
        ui.info("Класс Legion недоступен в контексте.", "RED"); ui.pause(); return
    existing = {str(getattr(x, "name", "")) for x in _list(getattr(player, "legions", []))}
    number = 1
    while f"Legio {_roman_numeral(number)} Romana" in existing: number += 1
    name = f"Legio {_roman_numeral(number)} Romana"
    try:
        legion = cls(name, quality=quality, elite=elite)
    except TypeError:
        legion = cls(name)
    except Exception as exc:
        ui.info(f"Не удалось сформировать легион: {exc}", "RED"); ui.pause(); return
    legion.quality = quality
    legion.strength = strength
    legion.morale = morale
    legion.battles = battles
    legion.veterans = veterans
    legion.elite = elite
    legion.fatigue = 0
    player.gold -= cost
    player.legions.append(legion)
    target = _pick_assignment_group(ui, player, state, ctx, "legions")
    if target:
        target.setdefault("legions", []).append(name)
        target["location"] = str(getattr(legion, "location", "Roma"))
    _validate_assignments(player, state, ctx)
    text = f"Сформирован {tier_name.lower()} {name} за {cost} золота."
    _record(player, state, "Новый легион", text, ctx)
    ui.wrap(text + (f" Прикреплён к {target.get('name')}." if target else " Оставлен в резерве."), "GREEN")
    ui.pause()



def _paged_choice(ui: UI, title: str, rows: list[tuple], headers: list[str], page_size: int = 10, color: str = "GOLD") -> int | None:
    if not rows: return None
    page = 0
    while True:
        start = page * page_size
        chunk = rows[start:start + page_size]
        ui.screen(); ui.header(title, "🏛", f"Страница {page + 1}/{max(1, (len(rows) + page_size - 1) // page_size)}")
        ui.table(title, headers, [(str(i + 1),) + tuple(row[1:]) for i, row in enumerate(chunk)], color)
        valid = [str(i) for i in range(1, len(chunk) + 1)] + ["Q"]
        if start + page_size < len(rows): valid.append("N"); print("  N. Следующая страница")
        if page > 0: valid.append("P"); print("  P. Предыдущая страница")
        pick = ui.choice("  Выбор: ", valid)
        if pick == "Q": return None
        if pick == "N": page += 1; continue
        if pick == "P": page -= 1; continue
        return start + int(pick) - 1


def _shop_auxilia(ui: UI, player: Any, state: dict, ctx: dict) -> None:
    ensure = ctx.get("ensure_expansion_state")
    if callable(ensure):
        try: ensure(player)
        except Exception: pass
    defs_fn = ctx.get("all_aux_unit_defs")
    defs = _list(defs_fn()) if callable(defs_fn) else []
    unlocked = set(_list(getattr(player, "unlocked_aux_units", [])))
    defs = [u for u in defs if isinstance(u, dict) and u.get("key") in unlocked]
    if not defs:
        ui.info("Нет открытых ауксилий. Захватывайте провинции и исследуйте технологии.", "GRAY"); ui.pause(); return
    game_price = ctx.get("game_price")
    rows = []
    for i, unit in enumerate(defs):
        base = _i(unit.get("cost_gold", 0), 0)
        cost = _i(game_price(player, base, market=True), base) if callable(game_price) else base
        rows.append((str(i + 1), unit.get("name"), unit.get("type"), unit.get("province", "—"), unit.get("strength", 0), f"от {cost}з"))
    idx = _paged_choice(ui, "РЫНОК АУКСИЛИИ", rows, ["#", "Отряд", "Тип", "Провинция", "Сила", "Цена"], 10, "CYAN")
    if idx is None: return
    base_def = dict(defs[idx])
    tiers = [
        ("1", "Новобранцы", 1.0, 1.0, 70, 0, False, False),
        ("2", "Ветераны", 2.5, 1.45, 92, 12, True, False),
        ("3", "Элита", 4.5, 1.85, 100, 45, True, True),
    ]
    base_gold = _i(base_def.get("cost_gold", 0), 0)
    ui.screen(); ui.header(f"ПОДГОТОВКА: {base_def.get('name')}", "🏹", "Ауксилии могут самостоятельно штурмовать и занимать города")
    ui.table("Уровень отряда", ["#", "Ранг", "Боевые параметры", "Цена"], [
        (key, name, f"×{stat_mult:.2f} сила/атака/защита; мораль {morale}",
         f"{_i(game_price(player, int(round(base_gold * cost_mult)), market=True), int(round(base_gold * cost_mult))) if callable(game_price) else int(round(base_gold * cost_mult))}з")
        for key, name, cost_mult, stat_mult, morale, xp, veterans, elite in tiers
    ], "GOLD")
    pick = ui.choice("  Уровень (Q — назад): ", ["1", "2", "3", "Q"])
    if pick == "Q": return
    _, tier_name, cost_mult, stat_mult, morale, xp, veterans, elite = next(t for t in tiers if t[0] == pick)
    unit_def = dict(base_def)
    unit_def["cost_gold"] = max(0, int(round(_i(base_def.get("cost_gold", 0), 0) * cost_mult)))
    unit_def["cost_iron"] = max(0, int(round(_i(base_def.get("cost_iron", 0), 0) * (1.0 + (cost_mult - 1.0) * 0.35))))
    unit_def["cost_copper"] = max(0, int(round(_i(base_def.get("cost_copper", 0), 0) * (1.0 + (cost_mult - 1.0) * 0.35))))
    unit_def["strength"] = min(120, max(1, int(round(_i(base_def.get("strength", 10), 10) * stat_mult))))
    unit_def["attack"] = min(50, max(0, int(round(_i(base_def.get("attack", unit_def["strength"] // 3), 0) * stat_mult))))
    unit_def["defense"] = min(50, max(0, int(round(_i(base_def.get("defense", unit_def["strength"] // 4), 0) * stat_mult))))
    unit_def["morale"] = morale
    add = ctx.get("add_aux_unit")
    before = len(_list(getattr(player, "aux_units", [])))
    if not callable(add) or not add(player, unit_def, free=False):
        ui.info("Не хватает золота или металлов либо найм недоступен.", "RED"); ui.pause(); return
    _ensure_aux_ids(player)
    new_units = _list(getattr(player, "aux_units", []))[before:]
    unit = new_units[-1] if new_units else _list(getattr(player, "aux_units", []))[-1]
    unit["xp"] = xp
    unit["battles"] = 10 if elite else 4 if veterans else 0
    unit["veterans"] = veterans
    unit["elite"] = elite
    unit["morale"] = morale
    unit["strength"] = unit_def["strength"]
    unit["max_strength"] = unit_def["strength"]
    unit["attack"] = unit_def["attack"]
    unit["defense"] = unit_def["defense"]
    uid = str(unit.get("army_uid"))
    target = _pick_assignment_group(ui, player, state, ctx, "auxilia")
    if target: target.setdefault("auxilia", []).append(uid)
    _validate_assignments(player, state, ctx)
    text = f"Нанят отряд {base_def.get('name')} — {tier_name}." + (f" Прикреплён к {target.get('name')}." if target else " Оставлен в резерве.")
    _record(player, state, "Новая ауксилия", text, ctx)
    ui.wrap(text, "GREEN"); ui.pause()



def _shop_artillery(ui: UI, player: Any, state: dict, ctx: dict) -> None:
    ensure = ctx.get("ensure_artillery_state")
    if callable(ensure):
        try: ensure(player)
        except Exception: pass
    types = _dict(ctx.get("ARTILLERY_TYPES"))
    if not types:
        ui.info("Справочник артиллерии недоступен.", "RED"); ui.pause(); return
    unlock = ctx.get("artillery_unlock_reason")
    cost_fn = ctx.get("artillery_effective_cost")
    rows = []
    keys = list(types)
    for i, key in enumerate(keys):
        spec = _dict(types.get(key))
        ok, reason = (True, "доступно")
        if callable(unlock):
            try: ok, reason = unlock(player, spec)
            except Exception: pass
        cost = _i(cost_fn(player, key), spec.get("cost_gold", 0)) if callable(cost_fn) else _price(player, ctx, spec.get("cost_gold", 0))
        rows.append((str(i + 1), spec.get("name", key), f"{cost}з", f"ос.{spec.get('siege', 0)} вар.{spec.get('anti_barbarian', 0)} под.{spec.get('support', 0)}", "можно" if ok else reason))
    idx = _paged_choice(ui, "МАГАЗИН АРТИЛЛЕРИИ", rows, ["#", "Орудие", "Цена", "Параметры", "Доступ"], 10, "GOLD")
    if idx is None: return
    key = keys[idx]
    spec = _dict(types.get(key))
    if callable(unlock):
        try:
            ok, reason = unlock(player, spec)
            if not ok: ui.info(f"Закрыто: {reason}", "RED"); ui.pause(); return
        except Exception: pass
    cost = _i(cost_fn(player, key), spec.get("cost_gold", 0)) if callable(cost_fn) else _price(player, ctx, spec.get("cost_gold", 0))
    maximum = min(20, _i(getattr(player, "gold", 0), 0) // max(1, cost))
    if maximum <= 0:
        ui.info(f"Нужно минимум {cost} золота.", "RED"); ui.pause(); return
    raw = input(f"  Количество 1-{maximum} (Q — отмена): ").strip().upper()
    if raw == "Q": return
    qty = _i(raw, 1, 1, maximum)
    build = ctx.get("build_artillery")
    if not callable(build) or not build(player, key, qty):
        ui.info("Покупка не состоялась.", "RED"); ui.pause(); return
    remaining = qty
    while remaining > 0:
        target = _pick_assignment_group(ui, player, state, ctx, "artillery")
        if not target: break
        free_slots = group_capacity(target, "artillery") - sum(_dict(target.get("artillery")).values())
        attach = min(remaining, max(0, free_slots))
        if attach <= 0: break
        target.setdefault("artillery", {})[key] = _i(target.get("artillery", {}).get(key, 0), 0) + attach
        remaining -= attach
        if remaining <= 0: break
        if ui.choice(f"  Осталось {remaining} в резерве. Распределить ещё? (Y/N): ", ["Y", "N"]) != "Y": break
    _validate_assignments(player, state, ctx)
    text = f"Куплено {spec.get('name', key)} ×{qty}; в резерве осталось {remaining}."
    _record(player, state, "Новая артиллерия", text, ctx)
    ui.wrap(text, "GREEN"); ui.pause()


def _fleet_type_unlocked(player: Any, spec: dict) -> tuple[bool, str]:
    owned = {str(p.get("name")) for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)}
    researched = set(str(x) for x in _list(getattr(player, "tech_researched", [])))
    req_prov = spec.get("requires_province")
    req_tech = [str(x) for x in _list(spec.get("requires_tech"))]
    missing = [x for x in req_tech if x not in researched]
    if req_prov and req_prov not in owned:
        return False, f"нужна провинция {req_prov}"
    if missing:
        return False, "нужны технологии: " + ", ".join(missing)
    return True, "доступно"


def _shop_fleet(ui: UI, player: Any, state: dict, ctx: dict) -> None:
    types = _dict(ctx.get("FLEET_SQUADRON_TYPES"))
    if not types:
        ui.info("Справочник эскадр недоступен.", "RED"); ui.pause(); return
    fleet = _fleet(player, ctx)
    keys = list(types)
    rows = []
    for i, key in enumerate(keys):
        spec = _dict(types.get(key))
        ok, reason = _fleet_type_unlocked(player, spec)
        cost = _price(player, ctx, _i(spec.get("cost", 0), 0))
        rows.append((str(i + 1), spec.get("name", key), f"{cost}з", f"бой {spec.get('power', 0)} ман.{spec.get('maneuver', 0)} морп.{spec.get('marines', 0)} груз {spec.get('cargo', 0)}", "можно" if ok else reason))
    idx = _paged_choice(ui, "ВЕРФИ РЕСПУБЛИКИ", rows, ["#", "Эскадра", "Цена", "Параметры", "Доступ"], 9, "CYAN")
    if idx is None: return
    key = keys[idx]
    spec = _dict(types.get(key))
    ok, reason = _fleet_type_unlocked(player, spec)
    if not ok: ui.info(reason, "RED"); ui.pause(); return
    cost = _price(player, ctx, _i(spec.get("cost", 0), 0))
    if _i(getattr(player, "gold", 0), 0) < cost:
        ui.info(f"Недостаточно золота: нужно {cost}.", "RED"); ui.pause(); return
    player.gold -= cost
    constructor = ctx.get("_new_squadron_v25")
    number = len(_list(fleet.get("squadrons"))) + 1
    if callable(constructor):
        try: sq = constructor(key, number)
        except Exception: sq = None
    else: sq = None
    if not isinstance(sq, dict):
        sq = {"id": "SQ-" + uuid.uuid4().hex[:10], "type": key, "name": f"{spec.get('name', key)} {number}", "xp": 0, "damage": 0, "zone": "tyrrhenian", "order": "reserve", "morale": 70}
    fleet.setdefault("squadrons", []).append(sq)
    target = _pick_assignment_group(ui, player, state, ctx, "fleet_squadrons")
    if target: target.setdefault("fleet_squadrons", []).append(str(sq.get("name")))
    _validate_assignments(player, state, ctx)
    text = f"Построена {sq.get('name')}." + (f" Прикреплена к {target.get('name')}." if target else " Оставлена в резерве.")
    _record(player, state, "Новая эскадра", text, ctx)
    ui.wrap(text, "GREEN"); ui.pause()


def _unit_shop_menu(ui: UI, player: Any, state: dict, ctx: dict) -> None:
    while True:
        free = _unassigned(player, state, ctx)
        ui.screen(); ui.header("FORVM MILITARE", "🏛", "Единый магазин легионов, ауксилий, артиллерии, флота и боезапаса")
        ui.info(f"Казна {getattr(player, 'gold', 0)} • зерно {getattr(player, 'grain', 0)} • резерв: L{len(free['legions'])}/A{len(free['auxilia'])}/R{sum(free['artillery'].values())}/F{len(free['squadrons'])}", "CYAN")
        print("  1. Сформировать легион")
        print("  2. Нанять ауксилию")
        print("  3. Купить артиллерию")
        print("  4. Построить эскадру")
        print("  5. Купить артиллерийский боезапас")
        print("  Q. Назад")
        ch = ui.choice("  Раздел: ", ["1", "2", "3", "4", "5", "Q"])
        if ch == "Q": return
        if ch == "1": _shop_legion(ui, player, state, ctx)
        elif ch == "2": _shop_auxilia(ui, player, state, ctx)
        elif ch == "3": _shop_artillery(ui, player, state, ctx)
        elif ch == "4": _shop_fleet(ui, player, state, ctx)
        elif ch == "5":
            fn = ctx.get("buy_artillery_supplies")
            if callable(fn):
                raw = input("  Сколько обозов купить? 1-99, Q — отмена: ").strip().upper()
                if raw != "Q": fn(player, _i(raw, 1, 1, 99))
            else: ui.info("Закупка боезапаса недоступна.", "RED")
            ui.pause()


def _upgrade_tree_menu(ui: UI, player: Any, group: dict, ctx: dict) -> None:
    while True:
        _sync_group_level(group)
        ui.screen(); ui.header(f"CURSUS HONORUM: {group.get('name')}", "🌿", f"Уровень {group.get('level')}/{MAX_GROUP_LEVEL} • опыт {group.get('experience', 0)} • очки {group.get('upgrade_points', 0)}")
        rows = []
        keys = list(UPGRADE_TREE)
        for i, key in enumerate(keys, 1):
            node = UPGRADE_TREE[key]
            owned = key in group.get("upgrades", [])
            missing = [UPGRADE_TREE[r]["name"] for r in node.get("requires", []) if r not in group.get("upgrades", [])]
            status = "ИЗУЧЕНО" if owned else ("нужно: " + ", ".join(missing) if missing else f"цена {node['cost']}")
            branch_name = next((name for branch, name, _ in UPGRADE_BRANCHES if branch == node["branch"]), node["branch"])
            rows.append((str(i), branch_name.split(" — ")[0], node["name"], node["cost"], status, node["desc"]))
        ui.table("Дерево развития", ["#", "Ветвь", "Узел", "Цена", "Статус", "Эффект"], rows, "PURPLE")
        pick = ui.choice("  Изучить узел (Q — назад): ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
        if pick == "Q": return
        key = keys[int(pick) - 1]
        node = UPGRADE_TREE[key]
        if key in group.get("upgrades", []): ui.info("Этот узел уже изучен.", "GRAY"); ui.pause(); continue
        missing = [r for r in node.get("requires", []) if r not in group.get("upgrades", [])]
        if missing:
            ui.info("Сначала нужны: " + ", ".join(UPGRADE_TREE[r]["name"] for r in missing), "RED"); ui.pause(); continue
        if _i(group.get("upgrade_points", 0), 0) < _i(node.get("cost", 1), 1):
            ui.info("Недостаточно очков развития. Побеждайте и берите города.", "RED"); ui.pause(); continue
        group["upgrade_points"] -= _i(node.get("cost", 1), 1)
        group.setdefault("upgrades", []).append(key)
        group["command_points"] = min(_max_command_points(group), _i(group.get("command_points", 0), 0) + _i(_dict(node.get("effects")).get("command_points", 0), 0))
        ui.wrap(f"Изучено: {node['name']}. {node['desc']}", "GREEN")
        ui.pause()


def _group_refit_menu(ui: UI, player: Any, group: dict, state: dict, ctx: dict) -> None:
    while True:
        p = group_power(player, group, ctx)
        ui.screen(); ui.header(f"CASTRA: {group.get('name')}", "⛺", "Учения, пополнение, ремонт и снабжение")
        ui.info(f"Снабжение {group.get('supply')} • спаянность {group.get('cohesion')} • усталость {group.get('fatigue')} • готовность {p['readiness']}", "CYAN")
        print("  1. Общие учения группы")
        print("  2. Пополнить легионы и ауксилии")
        print("  3. Отремонтировать прикреплённые эскадры")
        print("  4. Тренировать один легион")
        print("  5. Тренировать одну ауксилию")
        print("  6. Купить артиллерийский боезапас")
        print("  7. Перевести группу в режим переоснащения")
        print("  Q. Назад")
        ch = ui.choice("  Решение: ", ["1", "2", "3", "4", "5", "6", "7", "Q"])
        if ch == "Q": return
        if ch == "1":
            units = len(group.get("legions", [])) + len(group.get("auxilia", [])) + len(group.get("fleet_squadrons", []))
            cost = _price(player, ctx, 25 + units * 12)
            grain = 8 + units * 4
            if _i(getattr(player, "gold", 0), 0) < cost or _i(getattr(player, "grain", 0), 0) < grain:
                ui.info(f"Нужно {cost} золота и {grain} зерна.", "RED"); ui.pause(); continue
            player.gold -= cost; player.grain -= grain
            group["cohesion"] = _clamp(group.get("cohesion", 75) + 12, 0, 100, 75)
            group["supply"] = _clamp(group.get("supply", 85) + 6, 0, 100, 85)
            group["fatigue"] = _clamp(group.get("fatigue", 0) + 8, 0, 100, 0)
            gained = _grant_group_xp(group, 4)
            for name in group.get("legions", []):
                legion = _legion(player, name)
                if legion: legion.morale = min(100, _i(getattr(legion, "morale", 70), 70) + 5)
            ui.info(f"Учения завершены. Опыт +4.{f' Очки развития +{gained}.' if gained else ''}", "GREEN"); ui.pause()
        elif ch == "2":
            missing = 0
            for name in group.get("legions", []):
                legion = _legion(player, name)
                if legion: missing += max(0, 100 - _i(getattr(legion, "strength", 0), 0))
            for uid in group.get("auxilia", []):
                unit = _aux(player, uid)
                if unit: missing += max(0, _i(unit.get("max_strength", unit.get("strength", 0)), 0) - _i(unit.get("strength", 0), 0))
            if missing <= 0: ui.info("Все сухопутные части укомплектованы.", "GREEN"); ui.pause(); continue
            cost = _price(player, ctx, max(12, missing * 2))
            grain = max(8, missing // 2)
            if _i(getattr(player, "gold", 0), 0) < cost or _i(getattr(player, "grain", 0), 0) < grain:
                ui.info(f"Нужно {cost} золота и {grain} зерна.", "RED"); ui.pause(); continue
            player.gold -= cost; player.grain -= grain
            for name in group.get("legions", []):
                legion = _legion(player, name)
                if legion: legion.strength = min(100, _i(getattr(legion, "strength", 0), 0) + 18)
            for uid in group.get("auxilia", []):
                unit = _aux(player, uid)
                if unit:
                    maximum = _i(unit.get("max_strength", unit.get("strength", 0)), 0)
                    unit["strength"] = min(maximum, _i(unit.get("strength", 0), 0) + 12)
            group["supply"] = _clamp(group.get("supply", 85) + 10, 0, 100, 85)
            ui.info("Пополнение прибыло.", "GREEN"); ui.pause()
        elif ch == "3":
            damaged = []
            total_damage = 0
            for name in group.get("fleet_squadrons", []):
                sq = _squadron(player, name, ctx)
                if sq and _i(sq.get("damage", 0), 0) > 0:
                    damaged.append(sq); total_damage += _i(sq.get("damage", 0), 0)
            if not damaged: ui.info("Прикреплённые эскадры не повреждены.", "GREEN"); ui.pause(); continue
            cost = _price(player, ctx, max(15, total_damage * 2))
            if _i(getattr(player, "gold", 0), 0) < cost:
                ui.info(f"Нужно {cost} золота.", "RED"); ui.pause(); continue
            player.gold -= cost
            for sq in damaged: sq["damage"] = 0; sq["morale"] = min(100, _i(sq.get("morale", 70), 70) + 6)
            ui.info(f"Эскадры отремонтированы за {cost} золота.", "GREEN"); ui.pause()
        elif ch == "4":
            if not group.get("legions"): ui.info("В группе нет легионов.", "GRAY"); ui.pause(); continue
            for i, name in enumerate(group.get("legions", []), 1):
                legion = _legion(player, name); print(f"  {i}. {name} — качество {getattr(legion, 'quality', 0)}/10")
            pick = ui.choice("  Легион (Q — назад): ", [str(i) for i in range(1, len(group["legions"]) + 1)] + ["Q"])
            if pick == "Q": continue
            legion = _legion(player, group["legions"][int(pick) - 1])
            fn = ctx.get("train_legion_multiple_levels")
            if legion is not None and callable(fn):
                levels = fn(player, legion, 1)
                ui.info("Легион прошёл учения." if levels else "Учения невозможны: максимум качества или нет золота.", "GREEN" if levels else "RED")
            else: ui.info("Тренировка легиона недоступна.", "RED")
            ui.pause()
        elif ch == "5":
            if not group.get("auxilia"): ui.info("В группе нет ауксилий.", "GRAY"); ui.pause(); continue
            for i, uid in enumerate(group.get("auxilia", []), 1):
                unit = _aux(player, uid); print(f"  {i}. {unit.get('name') if unit else uid}")
            pick = ui.choice("  Отряд (Q — назад): ", [str(i) for i in range(1, len(group["auxilia"]) + 1)] + ["Q"])
            if pick == "Q": continue
            unit = _aux(player, group["auxilia"][int(pick) - 1])
            fn = ctx.get("train_auxiliary_unit")
            if unit and callable(fn) and fn(player, unit): ui.info("Ауксилия прошла тренировку.", "GREEN")
            else: ui.info("Тренировка не состоялась.", "RED")
            ui.pause()
        elif ch == "6":
            fn = ctx.get("buy_artillery_supplies")
            if callable(fn):
                raw = input("  Обозов 1-99, Q — отмена: ").strip().upper()
                if raw != "Q": fn(player, _i(raw, 1, 1, 99))
            else: ui.info("Закупка боезапаса недоступна.", "RED")
            ui.pause()
        elif ch == "7":
            group["stance"] = "refit"; group["target"] = None
            ui.info("Группа переходит к ремонту и пополнению. На следующих ходах восстановление ускорится.", "GREEN"); ui.pause()


def _detail(ui: UI, player: Any, group: dict, ctx: dict) -> None:
    p = group_power(player, group, ctx)
    effects = _upgrade_effects(group)
    ui.screen(); ui.header(group.get("name", "EXERCITUS"), "🦅", f"Командующий: {group.get('commander') or 'не назначен'} • уровень {group.get('level', 1)}")
    ui.table("Оперативные показатели", ["Параметр", "Значение"], [
        ("Доктрина", DOCTRINES[group.get("doctrine", "balanced")]["name"]),
        ("Позиция / задача", f"{group.get('location')} / {group.get('stance')}"),
        ("Приказы", f"{group.get('command_points', 0)}/{p['max_command_points']}"),
        ("Полевая мощь", p["land"]), ("Атака / защита", f"{p['attack']} / {p['defense']}"),
        ("Осада", p["siege"]), ("Флот", p["naval"]), ("Мобильность", p["mobility"]),
        ("Снабжение / спаянность", f"{p['supply']} / {p['cohesion']}"),
        ("Готовность", p["readiness"]), ("Опыт / очки", f"{group.get('experience', 0)} / {group.get('upgrade_points', 0)}"),
        ("Бои / победы", f"{group.get('battles', 0)} / {group.get('victories', 0)}"),
    ], "GOLD")
    ui.section(f"Легионы {len(group.get('legions', []))}/{group_capacity(group, 'legions')}", "RED")
    for name in group.get("legions", []):
        legion = _legion(player, name)
        if legion: print(f"  • {name}: сила {getattr(legion, 'strength', 0)}, качество {getattr(legion, 'quality', 0)}, мораль {getattr(legion, 'morale', 0)}, усталость {getattr(legion, 'fatigue', 0)}")
    if not group.get("legions"): ui.info("Нет легионов.", "GRAY")
    ui.section(f"Ауксилии {len(group.get('auxilia', []))}/{group_capacity(group, 'auxilia')}", "CYAN")
    for uid in group.get("auxilia", []):
        unit = _aux(player, uid)
        if unit: print(f"  • {unit.get('name')}: {unit.get('type')}, сила {unit.get('strength')}/{unit.get('max_strength', unit.get('strength'))}, мораль {unit.get('morale')}")
    if not group.get("auxilia"): ui.info("Нет ауксилий.", "GRAY")
    ui.section(f"Артиллерия {sum(group.get('artillery', {}).values())}/{group_capacity(group, 'artillery')}", "GOLD")
    types = _dict(ctx.get("ARTILLERY_TYPES"))
    if group.get("artillery"):
        for key, qty in group.get("artillery", {}).items(): print(f"  • {_dict(types.get(key)).get('name', key)} ×{qty}")
    else: ui.info("Нет артиллерии.", "GRAY")
    ui.section(f"Эскадры {len(group.get('fleet_squadrons', []))}/{group_capacity(group, 'fleet_squadrons')}", "BLUE")
    for name in group.get("fleet_squadrons", []):
        sq = _squadron(player, name, ctx)
        if sq: print(f"  • {name}: зона {sq.get('zone')}, приказ {sq.get('order')}, повреждения {sq.get('damage', 0)}%")
    if not group.get("fleet_squadrons"): ui.info("Нет эскадр.", "GRAY")
    ui.section("Развитие", "PURPLE")
    ui.info(", ".join(UPGRADE_TREE[k]["name"] for k in group.get("upgrades", []) if k in UPGRADE_TREE) or "Улучшений пока нет.")
    if group.get("operation_history"):
        last = group["operation_history"][-1]
        ui.info(f"Последняя операция: ход {last.get('turn')} — {last.get('title', last.get('type'))}: {last.get('text', last.get('result', ''))}", "GRAY")
    ui.pause()


def _attachments_menu(ui: UI, player: Any, group: dict, state: dict, ctx: dict) -> None:
    while True:
        _validate_assignments(player, state, ctx)
        free = _unassigned(player, state, ctx)
        ui.screen(); ui.header(f"СОСТАВ: {group.get('name')}", "🛡", "Каждая часть принадлежит только одной группе либо резерву")
        ui.info(
            f"L {len(group['legions'])}/{group_capacity(group, 'legions')} • A {len(group['auxilia'])}/{group_capacity(group, 'auxilia')} • "
            f"R {sum(group['artillery'].values())}/{group_capacity(group, 'artillery')} • F {len(group['fleet_squadrons'])}/{group_capacity(group, 'fleet_squadrons')}", "CYAN")
        print("  1. Прикрепить легион")
        print("  2. Открепить легион")
        print("  3. Прикрепить ауксилию")
        print("  4. Открепить ауксилию")
        print("  5. Прикрепить артиллерию")
        print("  6. Открепить артиллерию")
        print("  7. Прикрепить эскадру")
        print("  8. Открепить эскадру")
        print("  9. Передать часть другой группе")
        print("  Q. Назад")
        ch = ui.choice("  Решение: ", ["1","2","3","4","5","6","7","8","9","Q"])
        if ch == "Q": return
        if ch == "1":
            if not free["legions"] or len(group["legions"]) >= group_capacity(group, "legions"):
                ui.info("Нет свободного места или легионов.", "RED"); ui.pause(); continue
            for i, name in enumerate(free["legions"], 1): print(f"  {i}. {name}")
            p = ui.choice("  Легион: ", [str(i) for i in range(1, len(free["legions"])+1)] + ["Q"])
            if p != "Q": group["legions"].append(free["legions"][int(p)-1])
        elif ch == "2":
            if not group["legions"]: ui.info("Нет легионов.", "GRAY"); ui.pause(); continue
            for i, name in enumerate(group["legions"], 1): print(f"  {i}. {name}")
            p = ui.choice("  Легион: ", [str(i) for i in range(1, len(group["legions"])+1)] + ["Q"])
            if p != "Q": group["legions"].pop(int(p)-1)
        elif ch == "3":
            if not free["auxilia"] or len(group["auxilia"]) >= group_capacity(group, "auxilia"):
                ui.info("Нет свободного места или ауксилий.", "RED"); ui.pause(); continue
            for i, uid in enumerate(free["auxilia"], 1):
                unit = _aux(player, uid); print(f"  {i}. {unit.get('name') if unit else uid}")
            p = ui.choice("  Отряд: ", [str(i) for i in range(1, len(free["auxilia"])+1)] + ["Q"])
            if p != "Q": group["auxilia"].append(free["auxilia"][int(p)-1])
        elif ch == "4":
            if not group["auxilia"]: ui.info("Нет ауксилий.", "GRAY"); ui.pause(); continue
            for i, uid in enumerate(group["auxilia"], 1):
                unit = _aux(player, uid); print(f"  {i}. {unit.get('name') if unit else uid}")
            p = ui.choice("  Отряд: ", [str(i) for i in range(1, len(group["auxilia"])+1)] + ["Q"])
            if p != "Q": group["auxilia"].pop(int(p)-1)
        elif ch == "5":
            available = [(k, v) for k, v in free["artillery"].items() if v > 0]
            slots = group_capacity(group, "artillery") - sum(group["artillery"].values())
            if not available or slots <= 0: ui.info("Нет свободной артиллерии или мест.", "GRAY"); ui.pause(); continue
            types = _dict(ctx.get("ARTILLERY_TYPES"))
            for i, (key, qty) in enumerate(available, 1): print(f"  {i}. {_dict(types.get(key)).get('name', key)} — резерв {qty}")
            p = ui.choice("  Тип: ", [str(i) for i in range(1, len(available)+1)] + ["Q"])
            if p != "Q":
                key, qty = available[int(p)-1]
                maximum = min(qty, slots)
                raw = input(f"  Количество 1-{maximum}: ").strip()
                add = _i(raw, 1, 1, maximum)
                group["artillery"][key] = group["artillery"].get(key, 0) + add
        elif ch == "6":
            available = [(k, v) for k, v in group["artillery"].items() if v > 0]
            if not available: ui.info("Нет артиллерии.", "GRAY"); ui.pause(); continue
            types = _dict(ctx.get("ARTILLERY_TYPES"))
            for i, (key, qty) in enumerate(available, 1): print(f"  {i}. {_dict(types.get(key)).get('name', key)} ×{qty}")
            p = ui.choice("  Тип: ", [str(i) for i in range(1, len(available)+1)] + ["Q"])
            if p != "Q":
                key, qty = available[int(p)-1]
                raw = input(f"  Открепить 1-{qty}: ").strip(); amount = _i(raw, 1, 1, qty)
                group["artillery"][key] -= amount
                if group["artillery"][key] <= 0: group["artillery"].pop(key, None)
        elif ch == "7":
            if not free["squadrons"] or len(group["fleet_squadrons"]) >= group_capacity(group, "fleet_squadrons"):
                ui.info("Нет свободного места или эскадр.", "RED"); ui.pause(); continue
            for i, name in enumerate(free["squadrons"], 1): print(f"  {i}. {name}")
            p = ui.choice("  Эскадра: ", [str(i) for i in range(1, len(free["squadrons"])+1)] + ["Q"])
            if p != "Q": group["fleet_squadrons"].append(free["squadrons"][int(p)-1])
        elif ch == "8":
            if not group["fleet_squadrons"]: ui.info("Нет эскадр.", "GRAY"); ui.pause(); continue
            for i, name in enumerate(group["fleet_squadrons"], 1): print(f"  {i}. {name}")
            p = ui.choice("  Эскадра: ", [str(i) for i in range(1, len(group["fleet_squadrons"])+1)] + ["Q"])
            if p != "Q": group["fleet_squadrons"].pop(int(p)-1)
        elif ch == "9":
            others = [g for g in state.get("groups", []) if g is not group]
            if not others: ui.info("Других групп нет.", "GRAY"); ui.pause(); continue
            print("  L. Легион   A. Ауксилия   R. Артиллерия   F. Эскадра")
            typ = ui.choice("  Тип части: ", ["L","A","R","F","Q"])
            if typ == "Q": continue
            for i, target in enumerate(others, 1): print(f"  {i}. {target.get('name')}")
            tp = ui.choice("  Получатель: ", [str(i) for i in range(1, len(others)+1)] + ["Q"])
            if tp == "Q": continue
            target = others[int(tp)-1]
            if typ == "L" and group["legions"] and len(target["legions"]) < group_capacity(target, "legions"):
                for i, name in enumerate(group["legions"], 1): print(f"  {i}. {name}")
                p = ui.choice("  Легион: ", [str(i) for i in range(1, len(group["legions"])+1)] + ["Q"])
                if p != "Q": target["legions"].append(group["legions"].pop(int(p)-1))
            elif typ == "A" and group["auxilia"] and len(target["auxilia"]) < group_capacity(target, "auxilia"):
                for i, uid in enumerate(group["auxilia"], 1):
                    unit = _aux(player, uid); print(f"  {i}. {unit.get('name') if unit else uid}")
                p = ui.choice("  Отряд: ", [str(i) for i in range(1, len(group["auxilia"])+1)] + ["Q"])
                if p != "Q": target["auxilia"].append(group["auxilia"].pop(int(p)-1))
            elif typ == "F" and group["fleet_squadrons"] and len(target["fleet_squadrons"]) < group_capacity(target, "fleet_squadrons"):
                for i, name in enumerate(group["fleet_squadrons"], 1): print(f"  {i}. {name}")
                p = ui.choice("  Эскадра: ", [str(i) for i in range(1, len(group["fleet_squadrons"])+1)] + ["Q"])
                if p != "Q": target["fleet_squadrons"].append(group["fleet_squadrons"].pop(int(p)-1))
            elif typ == "R" and group["artillery"]:
                free_slots = group_capacity(target, "artillery") - sum(target["artillery"].values())
                if free_slots <= 0: ui.info("У получателя нет мест.", "RED"); ui.pause(); continue
                available = list(group["artillery"].items())
                for i, (key, qty) in enumerate(available, 1): print(f"  {i}. {key} ×{qty}")
                p = ui.choice("  Тип: ", [str(i) for i in range(1, len(available)+1)] + ["Q"])
                if p != "Q":
                    key, qty = available[int(p)-1]; amount = min(qty, free_slots)
                    target["artillery"][key] = target["artillery"].get(key, 0) + amount
                    group["artillery"][key] -= amount
                    if group["artillery"][key] <= 0: group["artillery"].pop(key, None)
            else:
                ui.info("Передача невозможна: нет части или свободного места.", "RED"); ui.pause()
        _validate_assignments(player, state, ctx)


def _orders_menu(ui: UI, player: Any, group: dict, ctx: dict) -> None:
    ui.screen(); ui.header(f"ПРИКАЗЫ: {group.get('name')}", "📜", "Позиция группы синхронизирует входящие в неё легионы")
    raw = input("  Новая позиция (пусто — оставить): ").strip()
    if raw: group["location"] = raw
    stances = [
        ("reserve", "Резерв"), ("defend", "Оборона"), ("intercept", "Перехват"),
        ("offensive", "Наступление"), ("siege", "Осада"), ("refit", "Переоснащение"),
    ]
    for i, (_, name) in enumerate(stances, 1): print(f"  {i}. {name}")
    p = ui.choice("  Задача: ", [str(i) for i in range(1, len(stances)+1)] + ["Q"])
    if p != "Q": group["stance"] = stances[int(p)-1][0]
    if group.get("fleet_squadrons"):
        zones = list(_dict(ctx.get("SEA_ZONES")))
        if zones:
            print("\n  Морская зона группы:")
            for i, zone in enumerate(zones, 1): print(f"  {i}. {_dict(_dict(ctx.get('SEA_ZONES')).get(zone)).get('name', zone)}")
            zp = ui.choice("  Зона (Q — без изменения): ", [str(i) for i in range(1, len(zones)+1)] + ["Q"])
            if zp != "Q": _set_group_zone(player, group, zones[int(zp)-1], ctx)


def _group_management_menu(ui: UI, player: Any, state: dict, ctx: dict) -> None:
    group = _select_group(ui, state)
    if not group: return
    while True:
        p = group_power(player, group, ctx)
        ui.screen(); ui.header(f"ШТАБ: {group.get('name')}", "🦅", f"Ур. {group.get('level')} • готовность {p['readiness']} • приказы {group.get('command_points')}/{p['max_command_points']}")
        print("  1. Полное досье")
        print("  2. Состав и передача частей")
        print("  3. Доктрина")
        print("  4. Позиция и постоянная задача")
        print("  5. Дерево развития группы")
        print("  6. Учения, пополнение и ремонт")
        print("  7. Переименовать группу")
        print("  8. Расформировать пустую группу")
        print("  Q. Назад")
        ch = ui.choice("  Решение: ", ["1","2","3","4","5","6","7","8","Q"])
        if ch == "Q": return
        if ch == "1": _detail(ui, player, group, ctx)
        elif ch == "2": _attachments_menu(ui, player, group, state, ctx)
        elif ch == "3":
            keys = list(DOCTRINES)
            ui.screen(); ui.header("ВОЕННАЯ ДОКТРИНА", "📚", group.get("name"))
            for i, key in enumerate(keys, 1): print(f"  {i}. {DOCTRINES[key]['name']} — {DOCTRINES[key]['desc']}")
            pch = ui.choice("  Доктрина: ", [str(i) for i in range(1, len(keys)+1)] + ["Q"])
            if pch != "Q": group["doctrine"] = keys[int(pch)-1]
        elif ch == "4": _orders_menu(ui, player, group, ctx)
        elif ch == "5": _upgrade_tree_menu(ui, player, group, ctx)
        elif ch == "6": _group_refit_menu(ui, player, group, state, ctx)
        elif ch == "7":
            name = input("  Новое название: ").strip()
            if name: group["name"] = name
        elif ch == "8":
            empty = not group.get("legions") and not group.get("auxilia") and not group.get("fleet_squadrons") and not group.get("artillery")
            if not empty: ui.info("Сначала переведите все части в резерв или другие группы.", "RED"); ui.pause(); continue
            if ui.choice("  Расформировать группу? (Y/N): ", ["Y","N"]) == "Y":
                state["groups"].remove(group); return


def _naval_administration_menu(ui: UI, player: Any, ctx: dict) -> None:
    while True:
        ui.screen(); ui.header("ADMIRALITAS", "⚓", "Инфраструктура флота теперь подчинена единому штабу армий")
        print("  1. Приказы отдельным эскадрам")
        print("  2. Порты и верфи")
        print("  3. Морские торговые пути")
        print("  4. Ремонт эскадры")
        print("  5. Морская разведка")
        print("  Q. Назад")
        ui.info("Островные походы и атаки побережья запускаются только из меню «Провинции».", "GOLD")
        ch = ui.choice("  Раздел: ", ["1","2","3","4","5","Q"])
        if ch == "Q": return
        fn_name = {"1":"v25_orders_menu", "2":"v25_ports_menu", "3":"v25_routes_menu", "4":"v25_repair_menu", "5":"v25_intel_menu"}[ch]
        fn = ctx.get(fn_name)
        if callable(fn): fn(player)
        else: ui.info(f"Раздел {fn_name} недоступен.", "RED"); ui.pause()


def _archive_menu(ui: UI, player: Any, state: dict, ctx: dict) -> None:
    ui.screen(); ui.header("ACTA EXERCITVVM", "📜", "История групп, покупок и операций")
    if state.get("history"):
        ui.table("Последние записи", ["Ход", "Событие", "Содержание"], [
            (x.get("turn"), x.get("title"), x.get("text")) for x in reversed(state["history"][-60:])
        ], "CYAN")
    else: ui.info("Архив пока пуст.", "GRAY")
    ui.pause()


def _group_rows(player: Any, state: dict, ctx: dict) -> list[tuple]:
    """Компактная сводка для узкого экрана Termux/Android."""
    rows = []
    for i, group in enumerate(state["groups"], 1):
        p = group_power(player, group, ctx)
        composition = f"{len(group.get('legions', []))}/{len(group.get('auxilia', []))}/{sum(group.get('artillery', {}).values())}/{len(group.get('fleet_squadrons', []))}"
        rows.append((
            str(i), group.get("name"), group.get("level", 1), composition,
            f"{p['land']}/{p['naval']}", f"{p['readiness']}%",
            f"{group.get('command_points', 0)}/{p['max_command_points']}", group.get("location"),
        ))
    return rows


def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx)
    ui = UI(ctx)
    state = ensure_state(player, ctx)
    while True:
        process_turn(player, ctx)
        state = ensure_state(player, ctx)
        ui.screen(); ui.header("EXERCITUS UNIVERSALIS", "🦅", f"Единый штаб групп армий — {MODULE_VERSION}")
        rows = _group_rows(player, state, ctx)
        if rows:
            ui.table("Группы армий Рима", ["#", "Группа", "Ур.", "L/A/R/F", "Суша/море", "Гот.", "ОД", "Позиция"], rows, "RED")
        else:
            ui.info("Групп армий пока нет.", "GRAY")
        free = _unassigned(player, state, ctx)
        ui.info(f"Резерв: легионов {len(free['legions'])}, ауксилий {len(free['auxilia'])}, артиллерии {sum(free['artillery'].values())}, эскадр {len(free['squadrons'])}.", "CYAN")
        print("  1. Управление выбранной группой")
        print("  2. Единый военный магазин")
        print("  3. Создать новую группу армий")
        print("  4. Автоматически собрать силы в группы")
        print("  5. Адмиралтейство: порты, маршруты, приказы, ремонт")
        print("  6. Военный архив")
        print("  Q. Назад")
        ui.info("Боевые приказы отдаются только через меню «Провинции» после выбора территории.", "GOLD")
        ch = ui.choice("\n  Решение: ", ["1","2","3","4","5","6","Q"])
        if ch == "Q": return
        if ch == "1": _group_management_menu(ui, player, state, ctx)
        elif ch == "2": _unit_shop_menu(ui, player, state, ctx)
        elif ch == "3":
            name = input("  Название новой группы: ").strip() or None
            group = _new_group(state, name)
            group["created_turn"] = _i(getattr(player, "turn", 1), 1)
            _normalize_group_v4(group)
            state["groups"].append(group)
            ui.info(f"Создана группа {group.get('name')}.", "GREEN"); ui.pause()
        elif ch == "4":
            if ui.choice("  Полностью пересобрать группы? Все части сохранятся. (Y/N): ", ["Y","N"]) == "Y":
                auto_organize(player, ctx, force=True)
                state = ensure_state(player, ctx)
        elif ch == "5": _naval_administration_menu(ui, player, ctx)
        elif ch == "6": _archive_menu(ui, player, state, ctx)
