#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna 3.0 — CIVITATES ARTIFICIALES.

Цивилизационный ИИ иностранных держав. Каждая держава получает самостоятельную
экономику, казну, продовольствие, людские резервы, общую с Римом технологическую
систему, государственную религию, национальные армии, ауксилии, артиллерию и
флот. Модель намеренно легче Roma Economica, но замкнута: войска требуют денег
и зерна, исследования — науки, флот — верфей, а длительная война истощает
резервы.

Публичный контракт:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None)
    get_power_state(player, power_key, ctx=None)
    land_power(player, power_key, ctx=None, army_id=None)
    naval_power(player, power_key, ctx=None)
    choose_field_army(player, power_key, ctx=None, objective=None)
    apply_land_losses(player, power_key, army_id, severity, won, ctx=None)
    apply_naval_losses(player, power_key, severity, won, ctx=None)
    open_menu(player, ctx=None)
"""
from __future__ import annotations

import copy
import hashlib
import math
import random
import re
import textwrap
import uuid
from typing import Any

MODULE_VERSION = "3.0.0-civitates-artificiales"
SCHEMA_VERSION = 1
MAX_HISTORY = 360
MAX_ARMIES_PER_POWER = 8
MAX_UNITS_PER_ARMY = 7


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
        value = float(value)
        return value if math.isfinite(value) else default
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


def _stable_int(*parts: Any, modulo: int = 100) -> int:
    raw = ":".join(str(x) for x in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:12], 16) % max(1, modulo)


class UI:
    def __init__(self, ctx: dict | None = None):
        self.ctx = _ctx(ctx); self.C = self.ctx.get("C")
    def color(self, text: Any, color: str = "WHITE", bold: bool = False) -> str:
        fn = self.ctx.get("clr")
        if callable(fn) and self.C is not None:
            try:
                code = getattr(self.C, color, "")
                if bold: code = getattr(self.C, "BOLD", "") + code
                return fn(str(text), code)
            except Exception: pass
        return str(text)
    def screen(self) -> None:
        fn = self.ctx.get("rui_screen_start") or self.ctx.get("clear")
        if callable(fn):
            try: fn(); return
            except Exception: pass
    def header(self, title: str, icon: str = "🌍", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try: fn(title, icon, getattr(self.C, "CYAN", ""), subtitle); return
            except TypeError:
                try: fn(title, icon, getattr(self.C, "CYAN", "")); return
                except Exception: pass
            except Exception: pass
        print(self.color(f"\n{'═' * 76}\n  {icon} {title}\n{'═' * 76}", "CYAN", True))
        if subtitle: self.wrap(subtitle, "GRAY")
    def section(self, title: str, color: str = "GOLD") -> None:
        fn = self.ctx.get("rui_section")
        if callable(fn) and self.C is not None:
            try: fn(title, getattr(self.C, color, "")); return
            except Exception: pass
        print(self.color(f"\n  ── {title} ──", color, True))
    def info(self, text: Any, color: str = "WHITE") -> None:
        fn = self.ctx.get("rui_info")
        if callable(fn) and self.C is not None:
            try: fn(str(text), getattr(self.C, color, "")); return
            except Exception: pass
        print(self.color("  " + str(text), color))
    def wrap(self, text: Any, color: str = "WHITE") -> None:
        fn = self.ctx.get("ui_wrap")
        if callable(fn) and self.C is not None:
            try: fn(str(text), color=getattr(self.C, color, "")); return
            except Exception: pass
        for line in textwrap.wrap(str(text), width=76, break_long_words=False): print(self.color("  " + line, color))
    def table(self, title: str, headers: list[str], rows: list[tuple], color: str = "CYAN") -> None:
        fn = self.ctx.get("rui_table")
        if callable(fn) and self.C is not None:
            try: fn(title, headers, rows, color=getattr(self.C, color, "")); return
            except Exception: pass
        self.section(title, color)
        widths = [len(_plain(h)) for h in headers]; clean_rows = []
        for row in rows:
            clean = [_plain(v) for v in row]; clean_rows.append(clean)
            for i, value in enumerate(clean[:len(widths)]): widths[i] = min(30, max(widths[i], len(value)))
        print("  " + " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
        print("  " + "-+-".join("-" * w for w in widths))
        for row in clean_rows: print("  " + " | ".join(row[i][:widths[i]].ljust(widths[i]) for i in range(len(headers))))
    def choice(self, prompt: str, valid: list[str]) -> str:
        valid = [str(x).upper() for x in valid]
        fn = self.ctx.get("read_choice")
        if callable(fn):
            try: return str(fn(self.color(prompt, "CYAN"), valid)).upper()
            except Exception: pass
        while True:
            value = input(prompt).strip().upper()
            if value in valid: return value
            print("  Допустимо: " + ", ".join(valid))
    def pause(self, text: str = "Нажмите Enter, чтобы продолжить...") -> None:
        fn = self.ctx.get("rui_pause") or self.ctx.get("pause")
        if callable(fn):
            try: fn(text); return
            except TypeError:
                try: fn(); return
                except Exception: pass
            except Exception: pass
        input("\n  " + text)


AI_PROFILES: dict[str, dict[str, Any]] = {
    "carthage": {
        "wealth": 92, "population": 68, "naval": 100, "science": 72, "faith": 68,
        "tech": {"economic": 1.35, "military": 1.05, "civil": 0.85, "naval": 1.65},
        "budget": {"army": 0.25, "navy": 0.27, "science": 0.15, "faith": 0.07, "infrastructure": 0.26},
        "religion": "paganism", "army_prefix": "Exercitus Punicus", "fleet_name": "Classis Punica",
    },
    "numidia": {
        "wealth": 55, "population": 62, "naval": 12, "science": 42, "faith": 62,
        "tech": {"economic": 0.85, "military": 1.55, "civil": 0.60, "naval": 0.25},
        "budget": {"army": 0.39, "navy": 0.03, "science": 0.10, "faith": 0.13, "infrastructure": 0.35},
        "religion": "paganism", "army_prefix": "Agmen Regium", "fleet_name": "Classis Numidica",
    },
    "pergamon": {
        "wealth": 73, "population": 57, "naval": 38, "science": 100, "faith": 58,
        "tech": {"economic": 1.10, "military": 1.20, "civil": 1.55, "naval": 0.70},
        "budget": {"army": 0.22, "navy": 0.08, "science": 0.29, "faith": 0.07, "infrastructure": 0.34},
        "religion": "paganism", "army_prefix": "Stratos Attalidon", "fleet_name": "Nautikon Pergamenon",
    },
    "parthia": {
        "wealth": 74, "population": 77, "naval": 8, "science": 66, "faith": 82,
        "tech": {"economic": 1.05, "military": 1.60, "civil": 0.80, "naval": 0.15},
        "budget": {"army": 0.42, "navy": 0.01, "science": 0.13, "faith": 0.13, "infrastructure": 0.31},
        "religion": "paganism", "army_prefix": "Spah Arsakidan", "fleet_name": "Classis Arsacidarum",
    },
    "egypt": {
        "wealth": 90, "population": 96, "naval": 72, "science": 88, "faith": 95,
        "tech": {"economic": 1.35, "military": 0.95, "civil": 1.30, "naval": 1.10},
        "budget": {"army": 0.20, "navy": 0.14, "science": 0.22, "faith": 0.13, "infrastructure": 0.31},
        "religion": "paganism", "army_prefix": "Stratos Ptolemaikos", "fleet_name": "Basilikon Nautikon",
    },
    "gauls": {
        "wealth": 48, "population": 91, "naval": 10, "science": 38, "faith": 88,
        "tech": {"economic": 0.75, "military": 1.55, "civil": 0.70, "naval": 0.20},
        "budget": {"army": 0.44, "navy": 0.02, "science": 0.08, "faith": 0.16, "infrastructure": 0.30},
        "religion": "paganism", "army_prefix": "Slougos Galatikos", "fleet_name": "Classis Gallica",
    },
}

RELIGION_POLICIES = {
    "paganism": {"military": 1.08, "stability": 1.00, "trade": 1.00, "science": 0.98},
    "judaism": {"military": 0.98, "stability": 1.08, "trade": 1.03, "science": 1.07},
    "christianity": {"military": 0.96, "stability": 1.12, "trade": 1.00, "science": 1.02},
}


def _nation_module(ctx: dict) -> Any:
    return ctx.get("NATIONS")


def _nation(ctx: dict, key: str) -> dict:
    module = _nation_module(ctx)
    if module is not None and hasattr(module, "get_nation"):
        try: return module.get_nation(key)
        except Exception: pass
    return {"name": key, "capital": key, "units": [], "modifiers": {}, "war_doctrine": ""}


def _roster(ctx: dict, key: str) -> list[dict]:
    module = _nation_module(ctx)
    if module is not None and hasattr(module, "get_roster"):
        try: return module.get_roster(key)
        except Exception: pass
    return copy.deepcopy(_list(_nation(ctx, key).get("units")))


def _diplomacy_row(player: Any, key: str) -> dict:
    return _dict(_dict(getattr(player, "diplomacy", {})).get(key))


def _strategic_state(player: Any, key: str) -> dict:
    return _dict(_dict(_dict(getattr(player, "diplomatic_ai", {})).get("powers")).get(key))


def _record(player: Any, state: dict, key: str, title: str, text: str, ctx: dict, severity: int = 2, notify: bool = False) -> None:
    item = {"turn": _i(getattr(player, "turn", 1), 1), "power": key, "title": title, "text": text}
    state.setdefault("history", []).append(item); state["history"] = state["history"][-MAX_HISTORY:]
    power = _dict(state.get("powers", {}).get(key))
    power.setdefault("history", []).append(item); power["history"] = power["history"][-100:]
    log = ctx.get("log_event")
    if callable(log):
        try: log(player, f"{title}: {text}")
        except Exception: pass
    annales = ctx.get("ANNALES")
    if annales is not None and hasattr(annales, "record_event"):
        try:
            annales.record_event(player, category="diplomacy", title=title, text=text,
                                  reason="Самостоятельное развитие иностранной державы.", severity=severity,
                                  data={"power": key, "system": "civitates_artificiales"})
        except Exception: pass
    if notify:
        council = ctx.get("WORLD_COUNCIL")
        if council is not None and hasattr(council, "enqueue"):
            try:
                council.enqueue(player, "ai.development", title, text, power=key, severity=severity,
                                expires_in=6, dedupe=f"ai.development:{key}:{title}:{getattr(player, 'turn', 1)}", ctx=ctx)
            except Exception: pass


def _unit_class(unit: dict) -> str:
    return str(unit.get("class", "")).lower()


def _is_fleet(unit: dict) -> bool:
    return any(word in _unit_class(unit) for word in ("флот", "эскадр", "кораб", "naval"))


def _is_artillery(unit: dict) -> bool:
    return any(word in _unit_class(unit) for word in ("осад", "инженер", "артил", "машин"))


def _is_auxiliary(unit: dict) -> bool:
    cls = _unit_class(unit)
    return _i(unit.get("cost", 99), 99) <= 10 or any(word in cls for word in ("лёг", "развед", "гарнизон", "ополчен", "наём"))


def _new_unit(template: dict, turn: int, *, branch: str | None = None) -> dict:
    branch = branch or ("fleet" if _is_fleet(template) else "artillery" if _is_artillery(template) else "auxilia" if _is_auxiliary(template) else "line")
    return {
        "id": "AIU-" + uuid.uuid4().hex[:10],
        "template": str(template.get("id", "unit")),
        "name": str(template.get("name", "Национальный отряд")),
        "class": str(template.get("class", "войска")),
        "branch": branch,
        "attack": _i(template.get("attack", 10), 10, 0),
        "defense": _i(template.get("defense", 10), 10, 0),
        "mobility": _i(template.get("mobility", 8), 8, 0),
        "cost": _i(template.get("cost", 10), 10, 1),
        "trait": str(template.get("trait", "")),
        "strength": 100,
        "morale": 72,
        "experience": 0,
        "created_turn": turn,
        "location": "capital",
    }


def _new_army(power: dict, profile: dict, turn: int) -> dict:
    number = _i(power.get("next_army_number", 1), 1, 1)
    power["next_army_number"] = number + 1
    commanders = power.get("commanders") or ["Strategos", "Rex Bellator", "Dux"]
    return {
        "id": "AIA-" + uuid.uuid4().hex[:10],
        "name": f"{profile.get('army_prefix', 'Exercitus')} {number}",
        "commander": commanders[(number - 1) % len(commanders)],
        "units": [],
        "location": "capital",
        "objective": None,
        "stance": "reserve",
        "supply": 86,
        "cohesion": 76,
        "fatigue": 0,
        "experience": 0,
        "battles": 0,
        "victories": 0,
        "created_turn": turn,
        "available_turn": turn,
    }


def _default_commanders(key: str) -> list[str]:
    return {
        "carthage": ["Ганнон Баркид", "Магон Ганнонид", "Бомилькар"],
        "numidia": ["Мастанабал", "Гулусса", "Иарб"],
        "pergamon": ["Аттал Филетер", "Никандр", "Меноген"],
        "parthia": ["Сурена", "Карен", "Готарз"],
        "egypt": ["Диоскурид", "Сосибий", "Ахилла"],
        "gauls": ["Бренн", "Веркассивеллаун", "Луктерий"],
    }.get(key, ["Strategos", "Dux", "Rex"])


def _default_power(key: str, ctx: dict, turn: int) -> dict:
    profile = AI_PROFILES.get(key, {})
    nation = _nation(ctx, key)
    wealth = _i(profile.get("wealth", 60), 60)
    population = _i(profile.get("population", 60), 60)
    power = {
        "key": key, "name": nation.get("name", key), "capital": nation.get("capital", key),
        "treasury": 180 + wealth * 4, "grain": 170 + population * 3, "manpower": 55 + population * 4,
        "population": 150 + population * 8, "infrastructure": max(25, wealth // 2),
        "trade": max(20, wealth), "stability": 65, "war_exhaustion": 0, "inflation": 0.02,
        "debt": 0, "last_income": 0, "last_expenses": 0, "budget": copy.deepcopy(profile.get("budget", {})),
        "research_points": 0, "science_output": max(4, _i(profile.get("science", 50), 50) // 8),
        "current_research": None, "technologies": [], "research_history": [],
        "religion": profile.get("religion", "paganism"), "faith": 40 + _i(profile.get("faith", 60), 60),
        "religious_fervor": _i(profile.get("faith", 60), 60), "conversion_pressure": {},
        "units": [], "armies": [], "fleet": [], "artillery": [], "auxiliaries": [],
        "shipyards": max(0, _i(profile.get("naval", 0), 0) // 35), "arsenals": 1,
        "commanders": _default_commanders(key), "next_army_number": 1,
        "military_stockpile": 70, "naval_stockpile": 35, "last_build_turn": 0,
        "last_tick_turn": 0, "history": [], "milestones": [], "schema": SCHEMA_VERSION,
    }
    roster = _roster(ctx, key)
    line = [u for u in roster if not _is_fleet(u) and not _is_artillery(u) and not _is_auxiliary(u)]
    aux = [u for u in roster if _is_auxiliary(u) and not _is_fleet(u)]
    art = [u for u in roster if _is_artillery(u)]
    fleets = [u for u in roster if _is_fleet(u)]
    if not line:
        line = [u for u in roster if not _is_fleet(u)]
    # Стартовая армия не бесплатна по ходу игры, но необходима для существующего мира.
    army = _new_army(power, profile, turn)
    for template in (line[:2] + aux[:1] + art[:1]):
        unit = _new_unit(template, turn)
        power["units"].append(unit)
        army["units"].append(unit["id"])
        if unit["branch"] == "auxilia": power["auxiliaries"].append(unit["id"])
        if unit["branch"] == "artillery": power["artillery"].append(unit["id"])
    if army["units"]:
        power["armies"].append(army)
    for template in fleets[:2]:
        unit = _new_unit(template, turn, branch="fleet")
        power["units"].append(unit); power["fleet"].append(unit["id"])
    return power


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    state = getattr(player, "ai_civilizations", None)
    if not isinstance(state, dict): state = {}; player.ai_civilizations = state
    state.setdefault("schema", SCHEMA_VERSION); state.setdefault("version", MODULE_VERSION)
    state.setdefault("powers", {}); state.setdefault("history", []); state.setdefault("last_tick_turn", 0)
    turn = _i(getattr(player, "turn", 1), 1)
    keys = list(AI_PROFILES)
    nation_module = _nation_module(ctx)
    if nation_module is not None and hasattr(nation_module, "NATIONS"):
        try: keys = list(nation_module.NATIONS)
        except Exception: pass
    for key in keys:
        if key not in state["powers"] or not isinstance(state["powers"].get(key), dict):
            state["powers"][key] = _default_power(key, ctx, turn)
        p = state["powers"][key]
        defaults = _default_power(key, ctx, turn)
        for field, value in defaults.items():
            p.setdefault(field, copy.deepcopy(value))
        for field in ("treasury", "grain", "manpower", "population", "infrastructure", "trade", "debt", "research_points", "science_output", "faith", "military_stockpile", "naval_stockpile", "last_build_turn", "last_tick_turn", "next_army_number"):
            p[field] = _i(p.get(field, defaults[field]), defaults[field], 0)
        for field in ("stability", "war_exhaustion", "religious_fervor"):
            p[field] = _clamp(p.get(field, defaults[field]), 0, 100, defaults[field])
        p["inflation"] = max(0.0, min(1.0, _f(p.get("inflation", 0.02), 0.02)))
        p["technologies"] = list(dict.fromkeys(str(x) for x in _list(p.get("technologies"))))
        p["units"] = [u for u in _list(p.get("units")) if isinstance(u, dict)]
        p["armies"] = [a for a in _list(p.get("armies")) if isinstance(a, dict)]
        p["fleet"] = [str(x) for x in _list(p.get("fleet"))]
        p["artillery"] = [str(x) for x in _list(p.get("artillery"))]
        p["auxiliaries"] = [str(x) for x in _list(p.get("auxiliaries"))]
        p["history"] = [x for x in _list(p.get("history")) if isinstance(x, dict)][-100:]
        p["milestones"] = [str(x) for x in _list(p.get("milestones"))][-100:]
        unit_ids = {u.get("id") for u in p["units"]}
        p["fleet"] = [x for x in p["fleet"] if x in unit_ids]
        p["artillery"] = [x for x in p["artillery"] if x in unit_ids]
        p["auxiliaries"] = [x for x in p["auxiliaries"] if x in unit_ids]
        used: set[str] = set()
        fixed_armies = []
        for army in p["armies"][:MAX_ARMIES_PER_POWER]:
            army.setdefault("id", "AIA-" + uuid.uuid4().hex[:10]); army.setdefault("name", "Национальная армия")
            army.setdefault("commander", random.choice(p.get("commanders") or ["Strategos"])); army.setdefault("units", [])
            army.setdefault("location", "capital"); army.setdefault("objective", None); army.setdefault("stance", "reserve")
            army.setdefault("supply", 80); army.setdefault("cohesion", 75); army.setdefault("fatigue", 0)
            army.setdefault("experience", 0); army.setdefault("battles", 0); army.setdefault("victories", 0)
            army.setdefault("created_turn", turn); army.setdefault("available_turn", turn)
            army["units"] = [str(x) for x in _list(army.get("units")) if x in unit_ids and x not in used][:MAX_UNITS_PER_ARMY]
            used.update(army["units"])
            for metric in ("supply", "cohesion", "fatigue"):
                army[metric] = _clamp(army.get(metric, 75), 0, 100, 75)
            fixed_armies.append(army)
        p["armies"] = fixed_armies
        p["schema"] = SCHEMA_VERSION
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state["last_tick_turn"] = _i(state.get("last_tick_turn", 0), 0, 0)
    state["schema"] = SCHEMA_VERSION; state["version"] = MODULE_VERSION
    player.ai_civilizations = state
    return state


def get_power_state(player: Any, power_key: str, ctx: dict | None = None) -> dict:
    return _dict(ensure_state(player, ctx)["powers"].get(power_key))


def _unit(power: dict, unit_id: str) -> dict | None:
    return next((u for u in power.get("units", []) if u.get("id") == unit_id), None)


def _army(power: dict, army_id: str | None) -> dict | None:
    if army_id:
        return next((a for a in power.get("armies", []) if a.get("id") == army_id), None)
    return None


def _tech_effect(power: dict, ctx: dict, effect: str) -> float:
    tree = _dict(ctx.get("TECH_TREE")); total = 0.0
    for key in power.get("technologies", []):
        total += _f(_dict(_dict(tree.get(key)).get("effects")).get(effect, 0), 0)
    return total


def _available_techs(power: dict, ctx: dict) -> list[str]:
    tree = _dict(ctx.get("TECH_TREE")); known = set(power.get("technologies", [])); out = []
    for key, tech in tree.items():
        if key in known: continue
        prereq = [str(x) for x in _list(_dict(tech).get("prereq"))]
        if all(p in known for p in prereq): out.append(str(key))
    return out


def _tech_category(key: str, tech: dict) -> str:
    category = str(tech.get("category", "civil")).lower()
    effects = _dict(tech.get("effects"))
    if any(k in effects for k in ("navy_power", "naval_combat", "fleet_upkeep", "naval_supply")) or any(w in key for w in ("naval", "fleet", "mare", "admir")):
        return "naval"
    if category in {"military", "economic", "civil", "naval"}: return category
    return "civil"


def _choose_research(power: dict, key: str, ctx: dict, at_war: bool) -> str | None:
    available = _available_techs(power, ctx)
    if not available: return None
    profile = AI_PROFILES.get(key, {}); weights = _dict(profile.get("tech")); tree = _dict(ctx.get("TECH_TREE"))
    def score(tech_key: str) -> float:
        tech = _dict(tree.get(tech_key)); cat = _tech_category(tech_key, tech)
        value = weights.get(cat, 1.0) * 100
        effects = _dict(tech.get("effects"))
        if at_war and any(k in effects for k in ("battle_attack", "battle_defense", "battle_siege", "navy_power")): value += 55
        if power["treasury"] < 120 and any(k in effects for k in ("gold_flat", "gold_percent", "gold_per_province", "upkeep_percent")): value += 45
        if power["grain"] < 120 and any(k in effects for k in ("grain_flat", "grain_percent")): value += 40
        value -= _i(tech.get("cost", 50), 50) * 0.08
        value += _stable_int(key, tech_key, getattr(power, "turn", 0), modulo=17)
        return value
    return max(available, key=score)


def _research_tick(player: Any, state: dict, key: str, power: dict, ctx: dict, at_war: bool, science_budget: int) -> None:
    tree = _dict(ctx.get("TECH_TREE"))
    if not tree: return
    if power.get("current_research") not in tree or power.get("current_research") in power.get("technologies", []):
        power["current_research"] = _choose_research(power, key, ctx, at_war)
        power["research_points"] = max(0, _i(power.get("research_points", 0), 0))
    current = power.get("current_research")
    if not current: return
    religion = RELIGION_POLICIES.get(power.get("religion"), RELIGION_POLICIES["paganism"])
    gain = max(1, power["science_output"] + science_budget // 12 + power["infrastructure"] // 25)
    gain = int(round(gain * _f(religion.get("science", 1.0), 1.0)))
    power["research_points"] += gain
    cost = max(10, _i(_dict(tree.get(current)).get("cost", 60), 60))
    if power["research_points"] >= cost:
        power["research_points"] -= cost
        power["technologies"].append(current)
        power["research_history"].append({"turn": _i(getattr(player, "turn", 1), 1), "technology": current})
        tech_row = _dict(tree.get(current))
        tech_name = tech_row.get("name", current)
        effects = _dict(tech_row.get("effects"))
        completed = len(power["technologies"])
        major_effects = {
            "battle_attack", "battle_defense", "battle_siege", "navy_power",
            "morale_cap_bonus", "research_percent", "gold_percent",
            "grain_percent", "upkeep_percent", "trade_gold_flat",
        }
        milestone = completed in {3, 6, 10, 15, 20, 30}
        # Послеходовый Совет получает лишь действительно эпохальные открытия.
        # Обычные исследования всё равно сохраняются в летописи державы.
        major = milestone or (cost >= 150 and bool(major_effects.intersection(effects)))
        _record(
            player, state, key, f"{power['name']} завершает исследование",
            f"Освоена технология «{tech_name}». Иностранная держава теперь использует то же знание в собственной национальной форме.",
            ctx, 4 if major else 2, notify=major,
        )
        power["current_research"] = _choose_research(power, key, ctx, at_war)


def _religion_tick(player: Any, state: dict, key: str, power: dict, ctx: dict, faith_budget: int) -> None:
    choices = _dict(ctx.get("RELIGION_CHOICES"))
    if not choices: return
    power["faith"] += max(1, faith_budget // 14 + power["religious_fervor"] // 25)
    current = str(power.get("religion", "paganism"))
    if current not in choices: current = next(iter(choices)); power["religion"] = current
    pressures = power.setdefault("conversion_pressure", {})
    for religion in choices:
        pressures.setdefault(religion, 0)
    roman_religion = str(getattr(player, "religion", "") or "")
    row = _diplomacy_row(player, key)
    if roman_religion in choices and roman_religion != current:
        contact = (8 if row.get("trade_pact") else 0) + (12 if row.get("alliance") else 0) + (15 if row.get("married") else 0) + max(0, _i(row.get("disposition", 50), 50) - 55) // 4
        pressures[roman_religion] = _i(pressures.get(roman_religion, 0), 0) + contact
    # Внутренняя устойчивость родного культа.
    pressures[current] = max(0, _i(pressures.get(current, 0), 0) - 4 - power["religious_fervor"] // 30)
    for religion in list(pressures):
        if religion != roman_religion:
            pressures[religion] = max(0, _i(pressures.get(religion, 0), 0) - 1)
    candidate = max(pressures, key=lambda r: pressures[r], default=current)
    threshold = 160 + power["religious_fervor"]
    if candidate != current and pressures.get(candidate, 0) >= threshold and power["faith"] >= 90:
        old = current; power["religion"] = candidate; power["faith"] -= 70
        power["stability"] = _clamp(power["stability"] - 10, 0, 100, 65)
        power["religious_fervor"] = _clamp(55 + faith_budget // 10, 0, 100, 60)
        pressures[candidate] = 0
        old_name = _dict(choices.get(old)).get("name", old); new_name = _dict(choices.get(candidate)).get("name", candidate)
        _record(player, state, key, f"Религиозный перелом в державе {power['name']}", f"Государственный двор отходит от традиции «{old_name}» и принимает «{new_name}». Решение изменит стабильность, дипломатию и военную мораль.", ctx, 5, notify=True)


def _normalize_budget(profile: dict, at_war: bool, naval_need: bool, weak_economy: bool) -> dict[str, float]:
    budget = dict(profile.get("budget", {}))
    for key in ("army", "navy", "science", "faith", "infrastructure"): budget.setdefault(key, 0.1)
    if at_war:
        budget["army"] += 0.13; budget["infrastructure"] -= 0.06; budget["science"] -= 0.03; budget["faith"] += 0.01
        if naval_need: budget["navy"] += 0.08
    if weak_economy:
        budget["infrastructure"] += 0.12; budget["army"] -= 0.05; budget["navy"] -= 0.04; budget["science"] -= 0.02
    total = sum(max(0.0, x) for x in budget.values()) or 1.0
    return {k: max(0.0, v) / total for k, v in budget.items()}


def _economic_tick(player: Any, key: str, power: dict, ctx: dict, at_war: bool) -> dict[str, int]:
    profile = AI_PROFILES.get(key, {})
    row = _diplomacy_row(player, key)
    religion = RELIGION_POLICIES.get(power.get("religion"), RELIGION_POLICIES["paganism"])
    base_income = 10 + power["population"] // 35 + power["infrastructure"] // 4 + power["trade"] // 5
    if row.get("trade_pact"): base_income += 12
    if row.get("client"): base_income = int(base_income * 0.72)
    base_income = int(round(base_income * _f(religion.get("trade", 1.0), 1.0)))
    grain_income = 12 + power["population"] // 28 + (18 if key == "egypt" else 0)
    upkeep = sum(max(1, _i(u.get("cost", 10), 10) // 4) for u in power.get("units", []))
    war_cost = 10 + len(power.get("armies", [])) * 4 if at_war else 0
    interest = max(0, power["debt"] // 30)
    expenses = upkeep + war_cost + interest
    income = max(1, base_income + random.randint(-4, 6))
    power["treasury"] += income - expenses
    power["grain"] += grain_income - max(4, len(power.get("units", [])) * (2 if at_war else 1))
    power["manpower"] += max(1, power["population"] // 180) - (3 if at_war else 0)
    power["population"] += max(0, power["stability"] // 35 - (2 if at_war else 0))
    if power["treasury"] < 0:
        gap = -power["treasury"]; power["debt"] += gap; power["treasury"] = 0; power["inflation"] = min(0.50, power["inflation"] + 0.01)
    elif power["treasury"] > 300 and power["debt"] > 0:
        repay = min(power["debt"], max(5, power["treasury"] // 12)); power["treasury"] -= repay; power["debt"] -= repay
    if power["grain"] < 0:
        power["stability"] = _clamp(power["stability"] - 6, 0, 100, 65); power["manpower"] = max(0, power["manpower"] - 8); power["grain"] = 0
    if at_war:
        power["war_exhaustion"] = _clamp(power["war_exhaustion"] + 2 + expenses // 45, 0, 100, 0)
    else:
        power["war_exhaustion"] = _clamp(power["war_exhaustion"] - 4, 0, 100, 0)
    power["stability"] = _clamp(power["stability"] + (1 if not at_war and power["treasury"] > 100 else 0) - (1 if power["debt"] > 300 else 0), 0, 100, 65)
    power["last_income"] = income; power["last_expenses"] = expenses
    # ИИ не тратит казну до последнего асса: мирный резерв обеспечивает
    # восстановление и исследования, военный — снабжение следующей кампании.
    reserve = 45 if at_war else 90
    free_treasury = max(0, power["treasury"] - reserve)
    spendable = max(0, min(free_treasury, income + max(0, power["treasury"] // 12)))
    naval_need = _i(profile.get("naval", 0), 0) >= 50 or bool(row.get("at_war") and key in {"carthage", "egypt"})
    shares = _normalize_budget(profile, at_war, naval_need, power["debt"] > 250 or power["treasury"] < 60)
    allocation = {name: int(spendable * share) for name, share in shares.items()}
    total_spend = min(power["treasury"], sum(allocation.values()))
    power["treasury"] -= total_spend
    # Нераспределённая округлением сумма остаётся в казне.
    actual = sum(allocation.values()) or 1
    if total_spend < actual:
        scale = total_spend / actual
        allocation = {k: int(v * scale) for k, v in allocation.items()}
    power["infrastructure"] = _clamp(power["infrastructure"] + allocation.get("infrastructure", 0) // 45, 0, 100, power["infrastructure"])
    power["trade"] = _clamp(power["trade"] + allocation.get("infrastructure", 0) // 70, 0, 130, power["trade"])
    power["military_stockpile"] += allocation.get("army", 0)
    power["naval_stockpile"] += allocation.get("navy", 0)
    power["faith"] += allocation.get("faith", 0) // 5
    return allocation


def _generic_fleet_template(key: str) -> dict:
    return {"id": f"{key}_fleet", "name": "Национальная военная эскадра", "class": "флот", "attack": 12, "defense": 12, "mobility": 12, "cost": 15, "trait": "защита побережья"}


def _generic_artillery_template(key: str) -> dict:
    return {"id": f"{key}_siege_train", "name": "Национальный осадный парк", "class": "осадные части", "attack": 12, "defense": 9, "mobility": 4, "cost": 16, "trait": "разрушение стен"}


def _choose_unit_template(key: str, power: dict, ctx: dict, branch: str) -> dict | None:
    roster = _roster(ctx, key)
    if branch == "fleet":
        options = [u for u in roster if _is_fleet(u)]
        return copy.deepcopy(max(options, key=lambda u: u.get("attack", 0) + u.get("defense", 0), default=_generic_fleet_template(key)))
    if branch == "artillery":
        options = [u for u in roster if _is_artillery(u)]
        if options: return copy.deepcopy(max(options, key=lambda u: u.get("attack", 0) + u.get("defense", 0)))
        if "siege_engines" in power.get("technologies", []): return _generic_artillery_template(key)
        return None
    if branch == "auxilia":
        options = [u for u in roster if _is_auxiliary(u) and not _is_fleet(u) and not _is_artillery(u)]
    else:
        options = [u for u in roster if not _is_fleet(u) and not _is_artillery(u) and not _is_auxiliary(u)]
        if not options: options = [u for u in roster if not _is_fleet(u) and not _is_artillery(u)]
    if not options: return None
    war = branch == "line"
    return copy.deepcopy(max(options, key=lambda u: (u.get("attack", 0) * (1.25 if war else 0.9) + u.get("defense", 0) + u.get("mobility", 0) * 0.35) / max(1, u.get("cost", 1))))


def _attach_unit(power: dict, unit: dict, profile: dict, turn: int) -> None:
    if unit["branch"] == "fleet":
        power["fleet"].append(unit["id"]); return
    if unit["branch"] == "artillery": power["artillery"].append(unit["id"])
    if unit["branch"] == "auxilia": power["auxiliaries"].append(unit["id"])
    army = min((a for a in power["armies"] if len(a.get("units", [])) < MAX_UNITS_PER_ARMY), key=lambda a: len(a.get("units", [])), default=None)
    if army is None and len(power["armies"]) < MAX_ARMIES_PER_POWER:
        army = _new_army(power, profile, turn); power["armies"].append(army)
    if army is not None: army["units"].append(unit["id"])


def _production_tick(player: Any, state: dict, key: str, power: dict, ctx: dict, at_war: bool) -> None:
    turn = _i(getattr(player, "turn", 1), 1); profile = AI_PROFILES.get(key, {})
    if turn <= power.get("last_build_turn", 0): return
    desired_line = max(2, 2 + power["population"] // 280 + (2 if at_war else 0))
    line_count = sum(1 for u in power["units"] if u.get("branch") == "line")
    aux_count = sum(1 for u in power["units"] if u.get("branch") == "auxilia")
    artillery_count = sum(1 for u in power["units"] if u.get("branch") == "artillery")
    fleet_count = len(power["fleet"])
    naval_rating = _i(profile.get("naval", 0), 0)
    desired_fleet = max(0, naval_rating // 30 + (1 if at_war and naval_rating >= 45 else 0))
    branch = None
    if line_count < desired_line: branch = "line"
    elif at_war and aux_count < max(1, line_count // 2): branch = "auxilia"
    elif at_war and artillery_count < max(1, len(power["armies"]) // 2): branch = "artillery"
    elif fleet_count < desired_fleet: branch = "fleet"
    elif power["military_stockpile"] >= 95 and line_count < desired_line + 2: branch = "line"
    if branch is None: return
    template = _choose_unit_template(key, power, ctx, branch)
    if not template: return
    cost = max(18, _i(template.get("cost", 10), 10) * (5 if branch == "fleet" else 4))
    stock = "naval_stockpile" if branch == "fleet" else "military_stockpile"
    manpower_cost = 8 if branch == "fleet" else 14 if branch == "line" else 7
    grain_cost = 10 if branch == "fleet" else 15
    if power[stock] < cost or power["manpower"] < manpower_cost or power["grain"] < grain_cost: return
    if branch == "fleet" and power["shipyards"] <= 0:
        if power["infrastructure"] >= 55 and power["naval_stockpile"] >= cost + 30:
            power["naval_stockpile"] -= 30; power["shipyards"] += 1
        else: return
    power[stock] -= cost; power["manpower"] -= manpower_cost; power["grain"] -= grain_cost
    unit = _new_unit(template, turn, branch=branch); power["units"].append(unit); _attach_unit(power, unit, profile, turn)
    power["last_build_turn"] = turn
    if branch in {"fleet", "artillery"} or len(power["armies"]) == 1 and len(power["armies"][0]["units"]) == 1:
        _record(player, state, key, f"Военная модернизация державы {power['name']}", f"В строй введено соединение «{unit['name']}» ({unit['class']}).", ctx, 3, notify=branch == "fleet")


def _army_units(power: dict, army: dict) -> list[dict]:
    return [u for uid in army.get("units", []) if (u := _unit(power, uid)) is not None]


def _unit_power(unit: dict, attack_weight: float = 1.0, defense_weight: float = 1.0) -> float:
    strength = _clamp(unit.get("strength", 100), 0, 100, 100)
    morale = _clamp(unit.get("morale", 70), 0, 100, 70)
    experience = _i(unit.get("experience", 0), 0)
    base = _i(unit.get("attack", 10), 10) * attack_weight + _i(unit.get("defense", 10), 10) * defense_weight + _i(unit.get("mobility", 8), 8) * 0.35
    return base * max(0.05, strength / 100) * (0.72 + morale / 250) * (1.0 + min(0.30, experience / 250))


def land_power(player: Any, power_key: str, ctx: dict | None = None, army_id: str | None = None) -> int:
    ctx = _ctx(ctx); power = get_power_state(player, power_key, ctx)
    armies = [_army(power, army_id)] if army_id else power.get("armies", [])
    total = 0.0
    for army in [a for a in armies if a]:
        units = _army_units(power, army)
        raw = sum(_unit_power(u) for u in units if u.get("branch") != "fleet")
        supply = _clamp(army.get("supply", 80), 0, 100, 80); cohesion = _clamp(army.get("cohesion", 75), 0, 100, 75); fatigue = _clamp(army.get("fatigue", 0), 0, 100, 0)
        raw *= (0.55 + supply / 220) * (0.58 + cohesion / 235) * max(0.40, 1.0 - fatigue / 155)
        total += raw
    tech = _tech_effect(power, ctx, "battle_attack") + _tech_effect(power, ctx, "battle_defense")
    religion = RELIGION_POLICIES.get(power.get("religion"), RELIGION_POLICIES["paganism"])
    total = (total + tech * 5) * _f(religion.get("military", 1.0), 1.0)
    nation = _nation(ctx, power_key); modifiers = _dict(nation.get("modifiers"))
    total *= 1.0 + max(modifiers.get("cavalry_combat", 0), modifiers.get("forest_combat", 0), modifiers.get("siege", 0), 0) / 500
    return max(0, int(round(total)))


def naval_power(player: Any, power_key: str, ctx: dict | None = None) -> int:
    ctx = _ctx(ctx); power = get_power_state(player, power_key, ctx)
    raw = sum(_unit_power(u, 1.1, 1.0) for uid in power.get("fleet", []) if (u := _unit(power, uid)) is not None)
    raw += power.get("shipyards", 0) * 4 + _tech_effect(power, ctx, "navy_power") * 5
    nation = _nation(ctx, power_key); raw *= 1.0 + _i(_dict(nation.get("modifiers")).get("naval_combat", 0), 0) / 100
    return max(0, int(round(raw)))


def choose_field_army(player: Any, power_key: str, ctx: dict | None = None, objective: str | None = None) -> dict | None:
    ctx = _ctx(ctx); power = get_power_state(player, power_key, ctx); turn = _i(getattr(player, "turn", 1), 1)
    candidates = [a for a in power.get("armies", []) if a.get("units") and _i(a.get("available_turn", 0), 0) <= turn and a.get("stance") != "destroyed"]
    if not candidates: return None
    def score(army: dict) -> int:
        value = land_power(player, power_key, ctx, army.get("id"))
        value += _clamp(army.get("supply", 80), 0, 100, 80) + _clamp(army.get("cohesion", 75), 0, 100, 75)
        if objective and army.get("objective") == objective: value += 30
        if army.get("stance") == "reserve": value += 10
        return value
    return max(candidates, key=score)


def _remove_unit(power: dict, unit: dict) -> None:
    uid = unit.get("id")
    power["units"] = [u for u in power["units"] if u.get("id") != uid]
    power["fleet"] = [x for x in power["fleet"] if x != uid]
    power["artillery"] = [x for x in power["artillery"] if x != uid]
    power["auxiliaries"] = [x for x in power["auxiliaries"] if x != uid]
    for army in power["armies"]:
        army["units"] = [x for x in army.get("units", []) if x != uid]


def apply_land_losses(player: Any, power_key: str, army_id: str | None, severity: int, won: bool, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx); state = ensure_state(player, ctx); power = get_power_state(player, power_key, ctx); army = _army(power, army_id) or choose_field_army(player, power_key, ctx)
    if not army: return {"losses": 0, "destroyed": []}
    severity = _i(severity, 12, 1, 60); destroyed = []; total = 0
    for unit in list(_army_units(power, army)):
        if unit.get("branch") == "fleet": continue
        loss = random.randint(max(2, severity // 5), max(4, severity // 2 + 2))
        if won: loss = max(1, loss // 2)
        unit["strength"] = max(0, _i(unit.get("strength", 100), 100) - loss)
        unit["morale"] = _clamp(unit.get("morale", 72) + (5 if won else -14), 0, 100, 72)
        unit["experience"] = _i(unit.get("experience", 0), 0) + (3 if won else 1); total += loss
        if unit["strength"] <= 0:
            destroyed.append(unit.get("name", "отряд")); _remove_unit(power, unit)
    army["battles"] = _i(army.get("battles", 0), 0) + 1; army["experience"] = _i(army.get("experience", 0), 0) + (5 if won else 2)
    army["supply"] = _clamp(army.get("supply", 80) - (8 if won else 16), 0, 100, 80)
    army["cohesion"] = _clamp(army.get("cohesion", 75) + (4 if won else -16), 0, 100, 75)
    army["fatigue"] = _clamp(army.get("fatigue", 0) + (12 if won else 25), 0, 100, 0)
    if won: army["victories"] = _i(army.get("victories", 0), 0) + 1
    if not army.get("units"): army["stance"] = "destroyed"
    power["manpower"] = max(0, power["manpower"] - total // 2); power["war_exhaustion"] = _clamp(power["war_exhaustion"] + (2 if won else 7), 0, 100, 0)
    _record(player, state, power_key, f"Потери армии державы {power['name']}", f"{army.get('name')} теряет {total}% совокупной численности; уничтожено: {', '.join(destroyed) if destroyed else 'нет'}.", ctx, 2)
    return {"losses": total, "destroyed": destroyed, "army": army}


def apply_naval_losses(player: Any, power_key: str, severity: int, won: bool, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx); state = ensure_state(player, ctx); power = get_power_state(player, power_key, ctx)
    severity = _i(severity, 12, 1, 60); destroyed = []; total = 0
    for uid in list(power.get("fleet", [])):
        unit = _unit(power, uid)
        if not unit: continue
        loss = random.randint(max(2, severity // 4), max(5, severity // 2 + 4))
        if won: loss = max(1, loss // 2)
        unit["strength"] = max(0, _i(unit.get("strength", 100), 100) - loss)
        unit["morale"] = _clamp(unit.get("morale", 72) + (6 if won else -16), 0, 100, 72)
        unit["experience"] = _i(unit.get("experience", 0), 0) + (3 if won else 1); total += loss
        if unit["strength"] <= 0:
            destroyed.append(unit.get("name", "эскадра")); _remove_unit(power, unit)
    power["naval_stockpile"] = max(0, power["naval_stockpile"] - total // 2); power["war_exhaustion"] = _clamp(power["war_exhaustion"] + (1 if won else 6), 0, 100, 0)
    _record(player, state, power_key, f"Морские потери державы {power['name']}", f"Флот теряет {total}% совокупной боеспособности; потоплено: {', '.join(destroyed) if destroyed else 'нет'}.", ctx, 2)
    return {"losses": total, "destroyed": destroyed}


def _recover_armies(power: dict, at_war: bool, turn: int) -> None:
    for army in power.get("armies", []):
        if army.get("stance") == "destroyed": continue
        in_action = army.get("stance") in {"advance", "siege", "battle", "raid"}
        army["supply"] = _clamp(army.get("supply", 80) + (3 if in_action else 8), 0, 100, 80)
        army["cohesion"] = _clamp(army.get("cohesion", 75) + (2 if in_action else 6), 0, 100, 75)
        army["fatigue"] = _clamp(army.get("fatigue", 0) - (7 if in_action else 16), 0, 100, 0)
        if not at_war: army["stance"] = "reserve"; army["objective"] = None
        for unit in _army_units(power, army):
            if not in_action and power["manpower"] > 0 and unit.get("strength", 100) < 100:
                refill = min(4, 100 - _i(unit.get("strength", 100), 100), power["manpower"])
                unit["strength"] += refill; power["manpower"] -= refill
            unit["morale"] = _clamp(unit.get("morale", 72) + (1 if at_war else 3), 0, 100, 72)
    power["armies"] = [a for a in power["armies"] if a.get("stance") != "destroyed" or turn - _i(a.get("available_turn", turn), turn) < 4]


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx); state = ensure_state(player, ctx); turn = _i(getattr(player, "turn", 1), 1)
    if state.get("last_tick_turn", 0) >= turn: return state
    state["last_tick_turn"] = turn
    for key, power in state["powers"].items():
        if power.get("last_tick_turn", 0) >= turn: continue
        power["last_tick_turn"] = turn
        row = _diplomacy_row(player, key); at_war = bool(row.get("at_war"))
        strategic = _strategic_state(player, key)
        if strategic:
            # Мягкая синхронизация с Orbis Politicus, без двойной бухгалтерии.
            power["stability"] = _clamp((power["stability"] * 3 + _i(strategic.get("stability", power["stability"]), power["stability"])) // 4, 0, 100, power["stability"])
            power["war_exhaustion"] = max(power["war_exhaustion"], _i(strategic.get("war_weariness", 0), 0) // 2)
        allocation = _economic_tick(player, key, power, ctx, at_war)
        _research_tick(player, state, key, power, ctx, at_war, allocation.get("science", 0))
        _religion_tick(player, state, key, power, ctx, allocation.get("faith", 0))
        _production_tick(player, state, key, power, ctx, at_war)
        _recover_armies(power, at_war, turn)
        # Военная готовность передаётся старому стратегическому ИИ как наблюдаемый результат экономики.
        if strategic:
            strategic["treasury"] = max(_i(strategic.get("treasury", 0), 0), power["treasury"] // 5)
            strategic["manpower"] = _clamp(power["manpower"] // 5, 0, 100, 50)
            strategic["economic_power"] = _clamp((power["infrastructure"] + power["trade"]) // 2, 0, 100, 50)
            strategic["naval_power"] = _clamp(naval_power(player, key, ctx) // 2, 0, 100, 0)
            strategic["readiness"] = _clamp(land_power(player, key, ctx) // max(1, len(power["armies"]) * 2), 0, 100, 50)
    return state


def _power_detail(ui: UI, player: Any, key: str, power: dict, ctx: dict) -> None:
    choices = _dict(ctx.get("RELIGION_CHOICES")); tree = _dict(ctx.get("TECH_TREE")); nation = _nation(ctx, key)
    religion = _dict(choices.get(power.get("religion"))).get("name", power.get("religion"))
    current = _dict(tree.get(power.get("current_research"))).get("name", power.get("current_research") or "—")
    ui.screen(); ui.header(power.get("name", key), nation.get("icon", "🌍"), nation.get("identity", "Самостоятельная держава"))
    ui.table("Государственный баланс", ["Показатель", "Значение"], [
        ("Казна / долг", f"{power['treasury']} / {power['debt']}"), ("Доход / расходы", f"{power['last_income']} / {power['last_expenses']}"),
        ("Зерно / людские резервы", f"{power['grain']} / {power['manpower']}"), ("Население", power["population"]),
        ("Инфраструктура / торговля", f"{power['infrastructure']} / {power['trade']}"), ("Стабильность / усталость", f"{power['stability']} / {power['war_exhaustion']}"),
        ("Религия / вера", f"{religion} / {power['faith']}"), ("Технологии", len(power["technologies"])),
        ("Текущее исследование", f"{current} ({power['research_points']})"), ("Армии / флот", f"{len(power['armies'])} / {len(power['fleet'])}"),
        ("Сухопутная / морская мощь", f"{land_power(player, key, ctx)} / {naval_power(player, key, ctx)}"),
    ], "CYAN")
    if power["armies"]:
        rows = []
        for army in power["armies"]:
            rows.append((army.get("name"), army.get("commander"), len(army.get("units", [])), army.get("location"), army.get("stance"), land_power(player, key, ctx, army.get("id")), army.get("supply"), army.get("cohesion")))
        ui.table("Национальные армии", ["Армия", "Командир", "Части", "Позиция", "Приказ", "Мощь", "Снаб.", "Спаян."], rows, "RED")
    if power["fleet"]:
        ui.section("Флот", "BLUE")
        for uid in power["fleet"]:
            unit = _unit(power, uid)
            if unit: print(f"  • {unit['name']}: сила {unit['strength']}, мораль {unit['morale']}, опыт {unit['experience']}")
    ui.pause()


def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx); ui = UI(ctx); state = ensure_state(player, ctx)
    while True:
        process_turn(player, ctx)
        ui.screen(); ui.header("CIVITATES ARTIFICIALES", "🌍", f"Экономика, технологии, религия и вооружённые силы ИИ — {MODULE_VERSION}")
        rows = []
        keys = list(state["powers"])
        choices = _dict(ctx.get("RELIGION_CHOICES"))
        for i, key in enumerate(keys, 1):
            power = state["powers"][key]
            religion = _dict(choices.get(power.get("religion"))).get("name", power.get("religion"))
            rows.append((str(i), power["name"], power["treasury"], power["grain"], len(power["technologies"]), religion, len(power["armies"]), len(power["fleet"]), land_power(player, key, ctx), naval_power(player, key, ctx)))
        ui.table("Державы", ["#", "Держава", "Казна", "Зерно", "Наука", "Религия", "Арм.", "Флот", "Суша", "Море"], rows, "GOLD")
        print("  1-6. Подробное досье державы")
        print("  Q. Назад")
        valid = [str(i) for i in range(1, len(keys) + 1)] + ["Q"]
        ch = ui.choice("\n  Выбор: ", valid)
        if ch == "Q": return
        key = keys[int(ch) - 1]; _power_detail(ui, player, key, state["powers"][key], ctx)
