#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROMA AETERNA — BARBARICUM
Отдельная система живого варварского мира.

Контракт с основной игрой намеренно мал:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None, interactive=True)
    open_menu(player, ctx=None)
    legacy_tick_hook(player, ctx=None)
    legacy_gift_hook(player, ctx=None)

Модуль не импортирует roma_aeterna.py и поэтому не создаёт циклических импортов.
Основной файл передаёт своё globals() как ctx; при отсутствии Rich/Textual модуль
работает на обычных print/input.
"""
from __future__ import annotations

import copy
import random
import re
import time
from typing import Any

MODULE_VERSION = "1.2.0-annales-bridge"
WORLD_SCHEMA = 2


def _i(value: Any, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _clamp(value: Any, low: int = 0, high: int = 100, default: int = 0) -> int:
    return _i(value, default, low, high)


def _ctx(ctx: dict | None) -> dict:
    return ctx if isinstance(ctx, dict) else {}


class UI:
    def __init__(self, ctx: dict | None = None):
        self.ctx = _ctx(ctx)
        self.C = self.ctx.get("C")

    def color(self, text: str, color_name: str = "WHITE", bold: bool = False) -> str:
        clr = self.ctx.get("clr")
        if callable(clr) and self.C is not None:
            color = getattr(self.C, color_name, "")
            if bold:
                color = getattr(self.C, "BOLD", "") + color
            try:
                return clr(str(text), color)
            except Exception:
                pass
        return str(text)

    def screen(self) -> None:
        fn = self.ctx.get("rui_screen_start") or self.ctx.get("clear")
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def header(self, title: str, icon: str = "🐺", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try:
                fn(title, icon, getattr(self.C, "RED", ""), subtitle)
                return
            except TypeError:
                try:
                    fn(title, icon, getattr(self.C, "RED", ""))
                    if subtitle:
                        self.wrap(subtitle, "GRAY")
                    return
                except Exception:
                    pass
            except Exception:
                pass
        print(self.color(f"\n{'═' * 68}\n  {icon} {title}\n{'═' * 68}", "RED", True))
        if subtitle:
            print(self.color("  " + subtitle, "GRAY"))

    def section(self, title: str, color: str = "CYAN") -> None:
        fn = self.ctx.get("rui_section")
        if callable(fn) and self.C is not None:
            try:
                fn(title, getattr(self.C, color, ""))
                return
            except Exception:
                pass
        print(self.color(f"\n  ── {title} ──", color, True))

    def info(self, text: str, color: str = "WHITE") -> None:
        fn = self.ctx.get("rui_info")
        if callable(fn) and self.C is not None:
            try:
                fn(text, getattr(self.C, color, ""))
                return
            except Exception:
                pass
        print(self.color("  " + str(text), color))

    def wrap(self, text: str, color: str = "WHITE") -> None:
        fn = self.ctx.get("ui_wrap")
        if callable(fn) and self.C is not None:
            try:
                fn(text, color=getattr(self.C, color, ""))
                return
            except Exception:
                pass
        import textwrap
        for line in textwrap.wrap(str(text), width=74, break_long_words=False):
            print(self.color("  " + line, color))

    def table(self, title: str, headers: list[str], rows: list[tuple], color: str = "RED") -> None:
        fn = self.ctx.get("rui_table")
        if callable(fn) and self.C is not None:
            try:
                fn(title, headers, rows, color=getattr(self.C, color, ""))
                return
            except Exception:
                pass
        self.section(title, color)
        widths = [len(str(h)) for h in headers]
        for row in rows:
            for j, value in enumerate(row):
                if j < len(widths):
                    widths[j] = min(28, max(widths[j], len(_strip_markup(str(value)))))
        print("  " + " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
        print("  " + "-+-".join("-" * w for w in widths))
        for row in rows:
            clean = [_strip_markup(str(v)) for v in row]
            print("  " + " | ".join(clean[i][:widths[i]].ljust(widths[i]) for i in range(len(headers))))

    def menu(self, entries: list[tuple[str, str, str, str]], title: str = "Действия") -> None:
        fn = self.ctx.get("rui_menu")
        if callable(fn):
            try:
                fn(entries, title=title)
                return
            except TypeError:
                try:
                    fn(entries)
                    return
                except Exception:
                    pass
            except Exception:
                pass
        self.section(title, "GOLD")
        for key, name, hint, icon in entries:
            suffix = f" — {hint}" if hint else ""
            print(f"  {self.color(key, 'GOLD', True)}  {icon} {name}{self.color(suffix, 'GRAY')}")

    def choice(self, prompt: str, valid: list[str]) -> str:
        valid = [str(v).upper() for v in valid]
        fn = self.ctx.get("read_choice")
        if callable(fn):
            try:
                return str(fn(self.color(prompt, "CYAN"), valid)).upper()
            except Exception:
                pass
        while True:
            value = input(prompt).strip().upper()
            if value in valid:
                return value
            print("  Допустимо: " + ", ".join(valid))

    def pause(self, text: str = "Нажмите Enter, чтобы продолжить...") -> None:
        fn = self.ctx.get("rui_pause") or self.ctx.get("pause")
        if callable(fn):
            try:
                fn(text)
                return
            except TypeError:
                try:
                    fn()
                    return
                except Exception:
                    pass
            except Exception:
                pass
        input("\n  " + text)


def _strip_markup(text: str) -> str:
    text = re.sub(r"\[[^\]]+\]", "", text)
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


FRONTIERS = {
    "gaul": {
        "name": "Галльский фронтир",
        "latin": "Limes Gallicus",
        "provinces": ["Gallia Narbonensis", "Gallia", "Aquitania", "Belgica", "Liguria"],
        "terrain": "леса и холмы",
        "season_risk": 1,
    },
    "rhine": {
        "name": "Рейнский фронтир",
        "latin": "Limes Rhenanus",
        "provinces": ["Germania Inferior", "Germania Superior", "Belgica", "Gallia"],
        "terrain": "реки и чащи",
        "season_risk": 2,
    },
    "danube": {
        "name": "Дунайский фронтир",
        "latin": "Limes Danubianus",
        "provinces": ["Illyricum", "Dacia", "Thracia", "Macedonia"],
        "terrain": "горы и переправы",
        "season_risk": 2,
    },
    "steppe": {
        "name": "Понтийская степь",
        "latin": "Campi Pontici",
        "provinces": ["Dacia", "Thracia", "Cappadocia", "Armenia"],
        "terrain": "степь",
        "season_risk": 3,
    },
    "britannia": {
        "name": "Британский предел",
        "latin": "Finis Britannicus",
        "provinces": ["Britannia", "Caledonia"],
        "terrain": "болота и нагорья",
        "season_risk": 2,
    },
}


TRIBE_TEMPLATES = {
    "arverni": {
        "name": "Арверны", "culture": "галлы", "region": "gaul", "homeland": "Центральная Галлия",
        "chief": "Верцингеторикс", "trait": "собиратель племён", "tactic": "коалиционная пехота",
        "population": 53000, "warriors": 6200, "wealth": 58, "cohesion": 66, "aggression": 61,
        "mobility": 48, "relation": 35, "trust": 24, "fear": 18, "gift": "gold",
    },
    "aedui": {
        "name": "Эдуи", "culture": "галлы", "region": "gaul", "homeland": "Долина Арара",
        "chief": "Дивициак", "trait": "дипломат друидов", "tactic": "союзные контингенты",
        "population": 41000, "warriors": 4200, "wealth": 64, "cohesion": 54, "aggression": 34,
        "mobility": 42, "relation": 55, "trust": 46, "fear": 20, "gift": "tech",
    },
    "belgae": {
        "name": "Белги", "culture": "бельги", "region": "rhine", "homeland": "Северная Галлия",
        "chief": "Гальба", "trait": "вождь пограничья", "tactic": "яростный натиск",
        "population": 47000, "warriors": 5600, "wealth": 46, "cohesion": 62, "aggression": 68,
        "mobility": 55, "relation": 30, "trust": 18, "fear": 22, "gift": "unit",
    },
    "suebi": {
        "name": "Свевы", "culture": "германцы", "region": "rhine", "homeland": "За Рейном",
        "chief": "Ариовист", "trait": "король переселенцев", "tactic": "лесная засада",
        "population": 68000, "warriors": 8300, "wealth": 38, "cohesion": 73, "aggression": 82,
        "mobility": 69, "relation": 20, "trust": 10, "fear": 14, "gift": "iron",
    },
    "marcomanni": {
        "name": "Маркоманы", "culture": "германцы", "region": "danube", "homeland": "Богемские земли",
        "chief": "Маробод", "trait": "строитель королевства", "tactic": "укреплённый лагерь",
        "population": 61000, "warriors": 7000, "wealth": 51, "cohesion": 78, "aggression": 58,
        "mobility": 52, "relation": 25, "trust": 16, "fear": 24, "gift": "unit",
    },
    "daci": {
        "name": "Даки", "culture": "даки", "region": "danube", "homeland": "Карпатские крепости",
        "chief": "Буребиста", "trait": "царь горных крепостей", "tactic": "фальксы и укрепления",
        "population": 72000, "warriors": 8500, "wealth": 72, "cohesion": 76, "aggression": 64,
        "mobility": 43, "relation": 30, "trust": 20, "fear": 18, "gift": "silver",
    },
    "getae": {
        "name": "Геты", "culture": "фракийцы", "region": "danube", "homeland": "Нижний Дунай",
        "chief": "Дромихет", "trait": "хранитель переправ", "tactic": "конные застрельщики",
        "population": 44000, "warriors": 5100, "wealth": 48, "cohesion": 57, "aggression": 46,
        "mobility": 61, "relation": 40, "trust": 31, "fear": 21, "gift": "copper",
    },
    "sarmatians": {
        "name": "Сарматы", "culture": "степняки", "region": "steppe", "homeland": "Понтийская степь",
        "chief": "Саурмаг", "trait": "владыка конных родов", "tactic": "конные лучники",
        "population": 49000, "warriors": 6400, "wealth": 44, "cohesion": 60, "aggression": 67,
        "mobility": 88, "relation": 35, "trust": 22, "fear": 16, "gift": "unit",
    },
    "picts": {
        "name": "Пикты", "culture": "каледонцы", "region": "britannia", "homeland": "Каледонские нагорья",
        "chief": "Калгак", "trait": "голос горных кланов", "tactic": "засады в нагорьях",
        "population": 36000, "warriors": 4300, "wealth": 29, "cohesion": 52, "aggression": 69,
        "mobility": 63, "relation": 20, "trust": 11, "fear": 12, "gift": "gold",
    },
    "iceni": {
        "name": "Ицены", "culture": "бритты", "region": "britannia", "homeland": "Восточная Британия",
        "chief": "Прасутаг", "trait": "богатый клиентский царь", "tactic": "боевые колесницы",
        "population": 39000, "warriors": 3900, "wealth": 59, "cohesion": 49, "aggression": 41,
        "mobility": 58, "relation": 45, "trust": 38, "fear": 17, "gift": "tech",
    },
}

RIVALRIES = [
    ("arverni", "aedui"), ("belgae", "suebi"), ("daci", "getae"),
    ("suebi", "marcomanni"), ("picts", "iceni"), ("getae", "sarmatians"),
]

LEADER_NAMES = {
    "галлы": ["Катуалд", "Эпоредориг", "Коммий", "Луктерий"],
    "бельги": ["Бодуогнат", "Амбиорикс", "Катуволк", "Индутомар"],
    "германцы": ["Хариомер", "Сегимер", "Ингвиомер", "Балломар"],
    "даки": ["Децебал", "Котисон", "Комосик", "Ролес"],
    "фракийцы": ["Реметалк", "Зибельмий", "Ситалк", "Севт"],
    "степняки": ["Фарзой", "Инисмей", "Амага", "Медосакк"],
    "каледонцы": ["Калед", "Аргетококс", "Талорк", "Калпурн"],
    "бритты": ["Тогодумн", "Каратак", "Мандубракий", "Аддедомар"],
}

LEADER_TRAITS = [
    ("великий воитель", 10, 8), ("хитрый дипломат", -4, 10),
    ("собиратель племён", 5, 14), ("грабитель границ", 14, -3),
    ("осторожный хранитель", -8, 8), ("прорицатель войны", 7, 5),
]

INCIDENT_LABELS = {
    "raid": "Набег",
    "migration": "Переселение",
    "embassy": "Посольство",
    "mercenaries": "Предложение наёмников",
    "tribute": "Требование дани",
    "feud": "Межплеменная война",
    "hostages": "Обмен заложниками",
    "confederation": "Племенная конфедерация",
}


def _new_tribe(key: str, template: dict) -> dict:
    t = copy.deepcopy(template)
    t.update({
        "key": key,
        "status": "independent",
        "pact": False,
        "federate": False,
        "tribute": 0,
        "hostages": False,
        "intelligence": 15,
        "pressure": max(10, t["aggression"] // 3),
        "hunger": random.randint(5, 22),
        "prestige": random.randint(20, 45),
        "victories": 0,
        "defeats": 0,
        "leader_age": random.randint(28, 52),
        "last_action_turn": 0,
        "cooldowns": {},
        "grievance": 0,
    })
    return t


def _new_world(player: Any) -> dict:
    tribes = {k: _new_tribe(k, v) for k, v in TRIBE_TEMPLATES.items()}
    frontiers = {
        key: {
            "key": key,
            "name": data["name"],
            "pressure": 10,
            "intel": 15,
            "fortification": 0,
            "patrols": 0,
            "settlement_capacity": 2,
            "last_crisis_turn": 0,
        }
        for key, data in FRONTIERS.items()
    }
    return {
        "schema": WORLD_SCHEMA,
        "module_version": MODULE_VERSION,
        "turn_processed": 0,
        "tribes": tribes,
        "frontiers": frontiers,
        "camps": [],
        "migrations": [],
        "incidents": [],
        "federates": [],
        "confederations": [],
        "chronicle": [],
        "next_id": 1,
        "great_migration_level": 0,
        "last_great_migration_turn": 0,
        "last_world_report": [],
        "legacy_snapshot": {},
        "settings": {
            "auto_crisis": True,
            "max_open_incidents": 8,
            "simulation_intensity": 1.25,
            "briefing_mode": "important",
        },
        "first_contact_done": False,
        "quiet_turns": 0,
        "last_briefing_turn": 0,
        "last_turn_new_incidents": [],
        "last_turn_frontier_changes": [],
    }


def _chronicle(world: dict, player: Any, text: str, tone: str = "info") -> None:
    entry = {
        "turn": _i(getattr(player, "turn", 0), 0),
        "year": _i(getattr(player, "year", 0), 0),
        "text": str(text),
        "tone": tone,
    }
    world["chronicle"].append(entry)
    world["chronicle"] = world["chronicle"][-120:]
    world.setdefault("last_world_report", []).append(str(text))
    world["last_world_report"] = world["last_world_report"][-10:]


def _annals(player: Any, ctx: dict | None, text: str, *, source: str) -> None:
    """Передаёт Barbaricum в летопись с явной категорией и значимостью."""
    fn = _ctx(ctx).get("annals_record_event")
    if not callable(fn):
        return
    low = str(text).lower()
    severity = 1
    if any(word in low for word in ("набег", "миграц", "осад", "самовольное поселение", "великий поход")):
        severity = 3
    if any(word in low for word in ("уничтож", "провинция потеряна", "roma", "столица")):
        severity = 4
    try:
        fn(player, str(text), category="barbaricum", severity=severity, source=source)
    except Exception:
        pass


def _log(player: Any, ctx: dict | None, text: str) -> None:
    _annals(player, ctx, text, source="barbaricum")
    fn = _ctx(ctx).get("log_event")
    if callable(fn):
        try:
            fn(player, text)
        except Exception:
            pass


def _summary(player: Any, ctx: dict | None, text: str) -> None:
    _annals(player, ctx, text, source="barbaricum_summary")
    fn = _ctx(ctx).get("turn_summary_add")
    if callable(fn):
        try:
            fn(player, text)
            return
        except Exception:
            pass
    _log(player, ctx, text)


def _owned_names(player: Any) -> set[str]:
    result = set()
    for p in _list(getattr(player, "provinces", [])):
        if isinstance(p, dict) and p.get("name"):
            result.add(str(p["name"]))
    return result


def _owned_province(player: Any, preferred: list[str]) -> dict | None:
    provinces = [p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)]
    by_name = {str(p.get("name")): p for p in provinces if p.get("name")}
    for name in preferred:
        if name in by_name:
            return by_name[name]
    candidates = [p for p in provinces if p.get("name") != "Latium"]
    return random.choice(candidates) if candidates else (provinces[0] if provinces else None)


def _legacy_strength(tribe: dict) -> int:
    return max(0, min(15, round(_i(tribe.get("warriors"), 0) / 900)))


def _sync_legacy(player: Any, world: dict, import_changes: bool = True) -> None:
    if not isinstance(getattr(player, "barbarian_tribes", None), dict):
        player.barbarian_tribes = {}
    legacy = player.barbarian_tribes
    snapshots = world.setdefault("legacy_snapshot", {})

    for key, tribe in world["tribes"].items():
        old = legacy.get(key)
        snap = snapshots.get(key, {})
        if import_changes and isinstance(old, dict) and snap:
            old_strength = _i(old.get("strength"), _legacy_strength(tribe))
            old_relation = _i(old.get("relation"), tribe["relation"])
            if old_strength != _i(snap.get("strength"), old_strength):
                delta = old_strength - _i(snap.get("strength"), old_strength)
                tribe["warriors"] = max(0, tribe["warriors"] + delta * 900)
                if delta < 0:
                    tribe["defeats"] += abs(delta)
            if old_relation != _i(snap.get("relation"), old_relation):
                tribe["relation"] = _clamp(old_relation, 0, 100, tribe["relation"])
            if bool(old.get("pact")) != bool(snap.get("pact")):
                tribe["pact"] = bool(old.get("pact"))

        record = {
            "name": tribe["name"],
            "chief": tribe["chief"],
            "strength": _legacy_strength(tribe),
            "relation": _clamp(tribe["relation"]),
            "gift": tribe.get("gift", "gold"),
            "pact": bool(tribe.get("pact") or tribe.get("federate")),
        }
        legacy[key] = record
        snapshots[key] = copy.deepcopy(record)


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    world = getattr(player, "barbarian_world", None)
    if not isinstance(world, dict):
        world = _new_world(player)
        setattr(player, "barbarian_world", world)

    world.setdefault("schema", WORLD_SCHEMA)
    world.setdefault("module_version", MODULE_VERSION)
    world.setdefault("turn_processed", 0)
    world.setdefault("tribes", {})
    world.setdefault("frontiers", {})
    world.setdefault("camps", [])
    world.setdefault("migrations", [])
    world.setdefault("incidents", [])
    world.setdefault("federates", [])
    world.setdefault("confederations", [])
    world.setdefault("chronicle", [])
    world.setdefault("next_id", 1)
    world.setdefault("great_migration_level", 0)
    world.setdefault("last_great_migration_turn", 0)
    world.setdefault("last_world_report", [])
    world.setdefault("legacy_snapshot", {})
    world.setdefault("settings", {})
    world.setdefault("first_contact_done", False)
    world.setdefault("quiet_turns", 0)
    world.setdefault("last_briefing_turn", 0)
    world.setdefault("last_turn_new_incidents", [])
    world.setdefault("last_turn_frontier_changes", [])
    world["settings"].setdefault("auto_crisis", True)
    world["settings"].setdefault("max_open_incidents", 8)
    world["settings"].setdefault("simulation_intensity", 1.25)
    world["settings"].setdefault("briefing_mode", "important")

    for key, template in TRIBE_TEMPLATES.items():
        if key not in world["tribes"] or not isinstance(world["tribes"][key], dict):
            world["tribes"][key] = _new_tribe(key, template)
        tribe = world["tribes"][key]
        # Нормализация не должна расходовать глобальный RNG: открытие меню или
        # загрузка сейва не меняют будущие броски боя и событий.
        defaults = copy.deepcopy(template)
        defaults.update({
            "key": key, "status": "independent", "pact": False, "federate": False,
            "tribute": 0, "hostages": False, "intelligence": 15,
            "pressure": max(10, template["aggression"] // 3), "hunger": 12,
            "prestige": 30, "victories": 0, "defeats": 0, "leader_age": 40,
            "last_action_turn": 0, "cooldowns": {}, "grievance": 0,
        })
        for field, value in defaults.items():
            tribe.setdefault(field, copy.deepcopy(value))
        tribe["relation"] = _clamp(tribe.get("relation"), 0, 100, template["relation"])
        tribe["trust"] = _clamp(tribe.get("trust"), 0, 100, 20)
        tribe["fear"] = _clamp(tribe.get("fear"), 0, 100, 20)
        tribe["cohesion"] = _clamp(tribe.get("cohesion"), 1, 100, 50)
        tribe["aggression"] = _clamp(tribe.get("aggression"), 0, 100, 50)
        tribe["pressure"] = _clamp(tribe.get("pressure"), 0, 100, 20)
        tribe["hunger"] = _clamp(tribe.get("hunger"), 0, 100, 10)
        tribe["population"] = _i(tribe.get("population"), template["population"], 1000, 500000)
        tribe["warriors"] = _i(tribe.get("warriors"), template["warriors"], 0, 100000)
        tribe["wealth"] = _i(tribe.get("wealth"), template["wealth"], 0, 500)
        tribe["prestige"] = _i(tribe.get("prestige"), 25, 0, 300)
        tribe["leader_age"] = _i(tribe.get("leader_age"), 40, 16, 95)
        if not isinstance(tribe.get("cooldowns"), dict):
            tribe["cooldowns"] = {}

    for key, data in FRONTIERS.items():
        frontier = world["frontiers"].setdefault(key, {})
        frontier.setdefault("key", key)
        frontier.setdefault("name", data["name"])
        frontier.setdefault("pressure", 10)
        frontier.setdefault("intel", 15)
        frontier.setdefault("fortification", 0)
        frontier.setdefault("patrols", 0)
        frontier.setdefault("settlement_capacity", 2)
        frontier.setdefault("last_crisis_turn", 0)
        for fld in ("pressure", "intel", "fortification", "patrols"):
            frontier[fld] = _clamp(frontier.get(fld), 0, 100, 0)

    world["camps"] = [x for x in world["camps"] if isinstance(x, dict)][-20:]
    world["migrations"] = [x for x in world["migrations"] if isinstance(x, dict)][-12:]
    world["incidents"] = [x for x in world["incidents"] if isinstance(x, dict)][-20:]
    world["federates"] = [x for x in world["federates"] if isinstance(x, dict)][-12:]
    world["confederations"] = [x for x in world["confederations"] if isinstance(x, dict)][-8:]
    world["chronicle"] = [x for x in world["chronicle"] if isinstance(x, dict)][-120:]

    _sync_legacy(player, world, import_changes=True)
    return world


def _next_id(world: dict, prefix: str) -> str:
    n = _i(world.get("next_id"), 1, 1)
    world["next_id"] = n + 1
    return f"{prefix}-{n:04d}"


def _add_incident(world: dict, player: Any, kind: str, tribe_key: str, frontier_key: str,
                  severity: int, title: str, text: str, payload: dict | None = None) -> dict:
    existing = [
        x for x in world["incidents"]
        if not x.get("resolved") and x.get("kind") == kind and x.get("tribe_key") == tribe_key
    ]
    if existing:
        existing[0]["severity"] = max(_i(existing[0].get("severity"), 1), severity)
        existing[0]["text"] = text
        return existing[0]
    item = {
        "id": _next_id(world, "INC"),
        "kind": kind,
        "tribe_key": tribe_key,
        "frontier": frontier_key,
        "severity": _clamp(severity, 1, 5, 1),
        "title": title,
        "text": text,
        "created_turn": _i(getattr(player, "turn", 0), 0),
        "expires_turn": _i(getattr(player, "turn", 0), 0) + 3 + severity,
        "resolved": False,
        "payload": payload or {},
    }
    world["incidents"].append(item)
    max_open = _i(world["settings"].get("max_open_incidents"), 8, 3, 20)
    unresolved = [x for x in world["incidents"] if not x.get("resolved")]
    if len(unresolved) > max_open:
        for old in unresolved[:-max_open]:
            old["resolved"] = True
            old["resolution"] = "просрочено"
    return item


def _new_camp(world: dict, player: Any, tribe: dict) -> dict:
    camp = {
        "id": _next_id(world, "CAMP"),
        "tribe_key": tribe["key"],
        "frontier": tribe["region"],
        "stage": 1,
        "strength": max(12, tribe["warriors"] // 350),
        "supplies": random.randint(30, 60),
        "readiness": random.randint(10, 30),
        "concealment": random.randint(25, 70),
        "created_turn": _i(getattr(player, "turn", 0), 0),
    }
    world["camps"].append(camp)
    _chronicle(world, player, f"{tribe['name']} разбили пограничный лагерь на рубеже {FRONTIERS[tribe['region']]['name']}.", "warning")
    return camp


def _new_migration(world: dict, player: Any, tribe: dict) -> dict:
    people = max(4000, min(42000, tribe["population"] // random.randint(3, 7)))
    warriors = max(500, min(9000, tribe["warriors"] // random.randint(2, 4)))
    migration = {
        "id": _next_id(world, "MIG"),
        "tribe_key": tribe["key"],
        "frontier": tribe["region"],
        "people": people,
        "warriors": warriors,
        "wagons": max(80, people // 55),
        "hunger": tribe["hunger"],
        "stage": "approaching",
        "turns": 0,
        "created_turn": _i(getattr(player, "turn", 0), 0),
    }
    tribe["population"] = max(1000, tribe["population"] - people)
    tribe["warriors"] = max(0, tribe["warriors"] - warriors)
    tribe["pressure"] = max(0, tribe["pressure"] - 25)
    world["migrations"].append(migration)
    _chronicle(world, player, f"Часть народа {tribe['name']} снялась с мест: {people} человек и {warriors} воинов движутся к границе.", "danger")
    return migration


def _roman_power(player: Any) -> int:
    legions = _list(getattr(player, "legions", []))
    aux = _list(getattr(player, "aux_units", []))
    morale = _i(getattr(player, "morale", 70), 70)
    glory = _i(getattr(player, "glory", 0), 0)
    return min(100, len(legions) * 9 + len(aux) * 3 + morale // 5 + glory // 150)


def _tick_leader(world: dict, player: Any, tribe: dict) -> None:
    tribe["leader_age"] += 1 if random.random() < 0.08 else 0
    mortality = 0.002 + max(0, tribe["leader_age"] - 55) * 0.0012
    mortality += 0.01 if tribe["defeats"] > tribe["victories"] + 2 else 0
    if random.random() >= mortality:
        return
    old = tribe["chief"]
    names = LEADER_NAMES.get(tribe["culture"], ["Новый вождь"])
    tribe["chief"] = random.choice([n for n in names if n != old] or names)
    trait, aggr_delta, cohesion_delta = random.choice(LEADER_TRAITS)
    tribe["trait"] = trait
    tribe["leader_age"] = random.randint(24, 43)
    tribe["aggression"] = _clamp(tribe["aggression"] + aggr_delta)
    tribe["cohesion"] = _clamp(tribe["cohesion"] + cohesion_delta)
    tribe["prestige"] = max(10, tribe["prestige"] // 2)
    _chronicle(world, player, f"У {tribe['name']} умер вождь {old}; власть принял {tribe['chief']} — {trait}.", "info")


def _tick_tribe(world: dict, player: Any, tribe: dict, roman_power: int) -> None:
    if tribe.get("status") == "destroyed":
        return
    for key in list(tribe["cooldowns"]):
        tribe["cooldowns"][key] = max(0, _i(tribe["cooldowns"][key]) - 1)
        if not tribe["cooldowns"][key]:
            tribe["cooldowns"].pop(key, None)

    _tick_leader(world, player, tribe)
    harvest = random.randint(-8, 8) + (2 if tribe["wealth"] > 60 else 0)
    if harvest < -3:
        tribe["hunger"] = _clamp(tribe["hunger"] + abs(harvest) + random.randint(2, 7))
    else:
        tribe["hunger"] = _clamp(tribe["hunger"] - random.randint(1, 5))

    growth = max(-500, int(tribe["population"] * random.uniform(-0.002, 0.006)))
    if tribe["hunger"] > 70:
        growth -= random.randint(200, 900)
    tribe["population"] = max(1000, tribe["population"] + growth)

    recruit = max(0, growth // 8) + random.randint(0, max(20, tribe["population"] // 5000))
    if tribe["hunger"] > 75:
        recruit //= 2
    tribe["warriors"] = max(0, min(tribe["population"] // 4, tribe["warriors"] + recruit))
    tribe["wealth"] = max(0, tribe["wealth"] + random.randint(-3, 4) - tribe["warriors"] // 12000)

    fear_target = min(100, roman_power + tribe["defeats"] * 3 - tribe["victories"] * 2)
    tribe["fear"] = _clamp(tribe["fear"] + (1 if fear_target > tribe["fear"] else -1 if fear_target < tribe["fear"] else 0))

    drift = random.randint(-2, 2)
    if tribe.get("pact") or tribe.get("federate"):
        drift += 1
    if tribe["grievance"] > 40:
        drift -= 2
    tribe["relation"] = _clamp(tribe["relation"] + drift)
    tribe["trust"] = _clamp(tribe["trust"] + (1 if tribe.get("pact") else -1 if tribe["relation"] < 25 else 0))

    pressure_change = (
        (tribe["aggression"] - 45) // 12
        + tribe["hunger"] // 18
        + tribe["population"] // 50000
        + tribe["prestige"] // 70
        - tribe["fear"] // 25
        - tribe["relation"] // 35
    )
    if tribe.get("federate"):
        pressure_change -= 5
    tribe["pressure"] = _clamp(tribe["pressure"] + pressure_change + random.randint(-2, 3))
    tribe["prestige"] = max(0, tribe["prestige"] + tribe["victories"] - tribe["defeats"] // 2 + random.randint(-1, 2))
    tribe["grievance"] = max(0, tribe["grievance"] - 1)

    intensity = max(0.6, min(2.0, _f(world.get("settings", {}).get("simulation_intensity"), 1.25)))
    camp_threshold = max(38, 48 - int((intensity - 1.0) * 12))
    if tribe["pressure"] >= camp_threshold and not any(c.get("tribe_key") == tribe["key"] for c in world["camps"]):
        camp_chance = min(0.78, (0.16 + tribe["pressure"] / 165) * intensity)
        if random.random() < camp_chance:
            _new_camp(world, player, tribe)

    has_migration = any(m.get("tribe_key") == tribe["key"] and m.get("stage") != "resolved" for m in world["migrations"])
    if not has_migration and (tribe["hunger"] >= 68 or tribe["pressure"] >= 84 or tribe["population"] >= 90000):
        if random.random() < min(0.75, (0.24 + tribe["hunger"] / 360) * intensity):
            mig = _new_migration(world, player, tribe)
            _add_incident(
                world, player, "migration", tribe["key"], tribe["region"],
                3 if mig["people"] < 18000 else 4,
                f"Переселение: {tribe['name']}",
                f"К {FRONTIERS[tribe['region']]['name']} движутся {mig['people']} переселенцев, среди них {mig['warriors']} вооружённых людей.",
                {"migration_id": mig["id"]},
            )


def _tick_rivalries(world: dict, player: Any) -> None:
    intensity = max(0.6, min(2.0, _f(world.get("settings", {}).get("simulation_intensity"), 1.25)))
    if random.random() >= min(0.55, 0.30 * intensity):
        return
    a_key, b_key = random.choice(RIVALRIES)
    a = world["tribes"].get(a_key)
    b = world["tribes"].get(b_key)
    if not a or not b or a.get("status") == "destroyed" or b.get("status") == "destroyed":
        return
    if a.get("federate") and b.get("federate"):
        return
    a_power = a["warriors"] // 120 + a["cohesion"] + random.randint(1, 60)
    b_power = b["warriors"] // 120 + b["cohesion"] + random.randint(1, 60)
    winner, loser = (a, b) if a_power >= b_power else (b, a)
    loss = random.randint(180, 900)
    loser["warriors"] = max(0, loser["warriors"] - loss)
    loser["population"] = max(1000, loser["population"] - random.randint(50, 500))
    loser["defeats"] += 1
    loser["hunger"] = _clamp(loser["hunger"] + random.randint(2, 8))
    winner["victories"] += 1
    winner["prestige"] += random.randint(3, 9)
    winner["wealth"] += random.randint(1, 5)
    _chronicle(world, player, f"{winner['name']} разбили отряд племени {loser['name']}; потерпевшие отступили, оставив добычу.", "info")
    if loser["warriors"] < 900:
        loser["cohesion"] = max(5, loser["cohesion"] - 15)


def _tick_camps(world: dict, player: Any) -> None:
    active = []
    for camp in world["camps"]:
        tribe = world["tribes"].get(camp.get("tribe_key"))
        if not tribe or tribe.get("status") == "destroyed" or camp.get("strength", 0) <= 0:
            continue
        camp["supplies"] = _clamp(camp.get("supplies", 40) + random.randint(-3, 8), 0, 120, 40)
        camp["readiness"] = _clamp(camp.get("readiness", 20) + random.randint(2, 8) + tribe["aggression"] // 30, 0, 100, 20)
        camp["strength"] = max(5, _i(camp.get("strength"), 15) + random.randint(0, max(1, tribe["warriors"] // 3500)))
        new_stage = 3 if camp["strength"] >= 45 or camp["readiness"] >= 82 else 2 if camp["strength"] >= 25 else 1
        if new_stage > camp.get("stage", 1):
            camp["stage"] = new_stage
            label = {2: "укреплённый лагерь", 3: "сборное войско"}[new_stage]
            _chronicle(world, player, f"Лагерь племени {tribe['name']} вырос: теперь это {label}.", "warning")
        if camp["readiness"] >= 70 and not tribe["cooldowns"].get("raid"):
            sev = 1 + camp["stage"]
            _add_incident(
                world, player, "raid", tribe["key"], tribe["region"], sev,
                f"Набег: {tribe['name']}",
                f"Из лагеря {tribe['name']} вышла дружина. Разведка оценивает угрозу как {camp['strength']} условной силы.",
                {"camp_id": camp["id"], "enemy_strength": camp["strength"] * 3 + 15},
            )
            camp["readiness"] = max(15, camp["readiness"] - 55)
            tribe["cooldowns"]["raid"] = 2
        active.append(camp)
    world["camps"] = active[-20:]


def _tick_migrations(world: dict, player: Any) -> None:
    for migration in world["migrations"]:
        if migration.get("stage") == "resolved":
            continue
        migration["turns"] = _i(migration.get("turns"), 0) + 1
        if migration["turns"] >= 2:
            migration["stage"] = "at_border"
        if migration["turns"] >= 5:
            tribe = world["tribes"].get(migration.get("tribe_key"), {})
            incident = next((x for x in world["incidents"] if x.get("payload", {}).get("migration_id") == migration["id"] and not x.get("resolved")), None)
            if not incident:
                incident = _add_incident(
                    world, player, "migration", migration["tribe_key"], migration["frontier"], 5,
                    f"Переселенцы пересекают границу",
                    f"Колонна {tribe.get('name', 'переселенцев')} больше не ждёт решения Рима и начинает переход границы.",
                    {"migration_id": migration["id"], "forced": True},
                )
            incident["severity"] = 5


def _tick_frontiers(world: dict, player: Any) -> None:
    owned = _owned_names(player)
    for key, frontier in world["frontiers"].items():
        tribes = [t for t in world["tribes"].values() if t.get("region") == key and t.get("status") != "destroyed"]
        raw = sum(t["pressure"] * max(1, t["warriors"] // 2500) for t in tribes) // max(1, len(tribes) * 2)
        camps = sum(_i(c.get("strength"), 0) for c in world["camps"] if c.get("frontier") == key)
        migrations = sum(_i(m.get("warriors"), 0) // 500 for m in world["migrations"] if m.get("frontier") == key and m.get("stage") != "resolved")
        exposed = any(name in owned for name in FRONTIERS[key]["provinces"])
        target = raw + camps // 2 + migrations - frontier["fortification"] // 2 - frontier["patrols"] // 3
        if not exposed:
            target //= 2
        drift = max(-8, min(8, target - frontier["pressure"]))
        frontier["pressure"] = _clamp(frontier["pressure"] + drift + random.randint(-2, 2))
        frontier["patrols"] = max(0, frontier["patrols"] - 4)
        frontier["fortification"] = max(0, frontier["fortification"] - (1 if random.random() < 0.15 else 0))
        frontier["intel"] = max(0, frontier["intel"] - (1 if random.random() < 0.25 else 0))


def _maybe_confederation(world: dict, player: Any) -> None:
    if random.random() >= 0.12:
        return
    regions = list(FRONTIERS)
    random.shuffle(regions)
    for region in regions:
        candidates = [
            t for t in world["tribes"].values()
            if t["region"] == region and t["cohesion"] >= 55 and t["pressure"] >= 55
            and t.get("status") == "independent" and not t.get("federate")
        ]
        if len(candidates) < 2:
            continue
        candidates.sort(key=lambda t: t["prestige"] + t["warriors"] // 200, reverse=True)
        leader = candidates[0]
        members = candidates[:min(3, len(candidates))]
        conf = {
            "id": _next_id(world, "CONF"),
            "name": f"Союз под властью {leader['chief']}",
            "leader": leader["key"],
            "members": [t["key"] for t in members],
            "region": region,
            "cohesion": min(95, sum(t["cohesion"] for t in members) // len(members) + 8),
            "warriors": sum(t["warriors"] for t in members),
            "created_turn": _i(getattr(player, "turn", 0), 0),
        }
        for t in members:
            t["status"] = "confederate"
            t["pressure"] = _clamp(t["pressure"] + 12)
            t["prestige"] += 8
        world["confederations"].append(conf)
        _add_incident(
            world, player, "confederation", leader["key"], region, 4,
            "Возникла племенная конфедерация",
            f"{leader['chief']} объединил племена: {', '.join(t['name'] for t in members)}. Под его знамёнами около {conf['warriors']} воинов.",
            {"confederation_id": conf["id"]},
        )
        _chronicle(world, player, f"{leader['chief']} создал конфедерацию племён на рубеже {FRONTIERS[region]['name']}.", "danger")
        break



def _tick_confederations(world: dict, player: Any) -> None:
    """Конфедерации не вечны: они усиливаются победами и распадаются от вражды."""
    active = []
    for conf in world["confederations"]:
        members = [world["tribes"].get(k) for k in _list(conf.get("members"))]
        members = [t for t in members if isinstance(t, dict) and t.get("status") != "destroyed"]
        if len(members) < 2:
            for t in members:
                t["status"] = "independent"
            continue
        leader = world["tribes"].get(conf.get("leader")) or members[0]
        rivalry = max(t.get("grievance", 0) for t in members) // 12
        prestige = leader.get("prestige", 0) // 35
        drift = prestige - rivalry + random.randint(-4, 4)
        conf["cohesion"] = _clamp(conf.get("cohesion", 55) + drift, 0, 100, 55)
        conf["warriors"] = sum(_i(t.get("warriors"), 0) for t in members)
        if conf["cohesion"] <= 18:
            for t in members:
                t["status"] = "independent"
                t["pressure"] = max(0, t["pressure"] - 8)
            _chronicle(world, player, f"Конфедерация «{conf.get('name', 'союз племён')}» распалась в междоусобице.", "info")
            continue
        # Очень прочный союз сам организует большой поход, но не чаще раза в 4 хода.
        last = _i(conf.get("last_campaign_turn"), 0)
        turn = _i(getattr(player, "turn", 0), 0)
        if conf["cohesion"] >= 78 and turn - last >= 4 and random.random() < 0.16:
            conf["last_campaign_turn"] = turn
            _add_incident(
                world, player, "raid", leader["key"], conf["region"], 5,
                f"Поход конфедерации: {leader['chief']}",
                f"Объединённое войско {', '.join(t['name'] for t in members)} движется к римскому лимесу. Разведка насчитывает около {conf['warriors']} воинов.",
                {"enemy_strength": max(55, conf["warriors"] // 65), "confederation_id": conf["id"]},
            )
            _chronicle(world, player, f"Конфедерация под властью {leader['chief']} начала великий поход против Рима.", "danger")
        active.append(conf)
    world["confederations"] = active[-8:]


def _maybe_great_migration(world: dict, player: Any) -> None:
    """При высоком системном давлении запускает не рейд, а народную волну."""
    level = _i(world.get("great_migration_level"), 0)
    turn = _i(getattr(player, "turn", 0), 0)
    if level < 82 or turn - _i(world.get("last_great_migration_turn"), 0) < 10:
        return
    if any(not x.get("resolved") and x.get("kind") == "migration" and _i(x.get("severity"), 1) >= 5 for x in world["incidents"]):
        return
    candidates = [
        t for t in world["tribes"].values()
        if t.get("status") != "destroyed" and not t.get("federate") and t["population"] >= 18000
    ]
    if not candidates:
        return
    candidates.sort(key=lambda t: t["pressure"] + t["hunger"] + t["population"] // 4000, reverse=True)
    tribe = candidates[0]
    migration = _new_migration(world, player, tribe)
    # Великая волна крупнее обычной миграции.
    bonus_people = min(30000, tribe["population"] // 4)
    bonus_warriors = min(6000, tribe["warriors"] // 3)
    migration["people"] += bonus_people
    migration["warriors"] += bonus_warriors
    tribe["population"] = max(1000, tribe["population"] - bonus_people)
    tribe["warriors"] = max(0, tribe["warriors"] - bonus_warriors)
    world["last_great_migration_turn"] = turn
    world["great_migration_level"] = max(35, level - 35)
    _add_incident(
        world, player, "migration", tribe["key"], tribe["region"], 5,
        "Великая волна переселения",
        f"Не одна дружина, но целый народ {tribe['name']} — {migration['people']} человек, повозки, скот и {migration['warriors']} воинов — идёт к владениям Рима.",
        {"migration_id": migration["id"], "great_migration": True},
    )
    _chronicle(world, player, f"Началась великая волна переселения народа {tribe['name']}.", "danger")


def _maybe_peaceful_contact(world: dict, player: Any) -> None:
    intensity = max(0.6, min(2.0, _f(world.get("settings", {}).get("simulation_intensity"), 1.25)))
    if random.random() >= min(0.60, 0.28 * intensity):
        return
    candidates = [t for t in world["tribes"].values() if not t["cooldowns"].get("contact") and t.get("status") != "destroyed"]
    if not candidates:
        return
    tribe = random.choice(candidates)
    if tribe["relation"] >= 55:
        kind = random.choice(["embassy", "mercenaries", "hostages"])
        if kind == "embassy":
            text = f"Послы {tribe['name']} прибыли с дарами и предложением подтвердить мир на границе."
        elif kind == "mercenaries":
            text = f"Вождь {tribe['chief']} предлагает Риму {max(400, tribe['warriors']//8)} воинов за плату."
        else:
            text = f"{tribe['name']} предлагают обмен знатными заложниками как залог мира."
        _add_incident(world, player, kind, tribe["key"], tribe["region"], 1, INCIDENT_LABELS[kind], text)
    elif tribe["relation"] <= 22 and tribe["fear"] < 45:
        _add_incident(
            world, player, "tribute", tribe["key"], tribe["region"], 2,
            f"Требование {tribe['name']}",
            f"Посланцы {tribe['chief']} требуют золото за спокойствие на рубеже.",
        )
    tribe["cooldowns"]["contact"] = 3


def _exposed_frontier_keys(player: Any) -> list[str]:
    owned = _owned_names(player)
    exposed = [
        key for key, data in FRONTIERS.items()
        if any(name in owned for name in data.get("provinces", []))
    ]
    return exposed or ["gaul", "rhine", "danube"]


def _ensure_first_contact(world: dict, player: Any) -> None:
    """Гарантирует, что новый модуль не проходит для игрока незаметно.

    На первом обработанном ходу появляется осмысленное пограничное дело. Это
    не читерский набег: характер контакта зависит от отношений и давления.
    """
    if world.get("first_contact_done"):
        return
    if any(not x.get("resolved") for x in world.get("incidents", [])):
        world["first_contact_done"] = True
        return
    exposed = set(_exposed_frontier_keys(player))
    candidates = [
        t for t in world["tribes"].values()
        if t.get("region") in exposed and t.get("status") != "destroyed"
    ] or [t for t in world["tribes"].values() if t.get("status") != "destroyed"]
    candidates.sort(key=lambda t: t.get("pressure", 0) + t.get("prestige", 0) // 2, reverse=True)
    tribe = candidates[0]
    if tribe.get("relation", 0) >= 45:
        kind, severity = "embassy", 2
        title = f"Первое посольство: {tribe['name']}"
        text = (f"Вождь {tribe['chief']} прислал людей к римскому рубежу. Они предлагают "
                "обмен дарами, сведения о соседях и клятву временного мира.")
    elif tribe.get("pressure", 0) >= 48 or tribe.get("aggression", 0) >= 65:
        kind, severity = "raid", 2
        title = f"Первые тревожные вести: {tribe['name']}"
        text = (f"Разведчики заметили дружину народа {tribe['name']}. Пока это разведка боем, "
                "но без ответа Рима за ней последует крупный лагерь.")
    else:
        kind, severity = "mercenaries", 1
        title = f"Предложение вождя {tribe['chief']}"
        text = f"{tribe['name']} предлагают Риму нанять пограничную дружину и открыть постоянный контакт."
    incident = _add_incident(world, player, kind, tribe["key"], tribe["region"], severity, title, text)
    incident["first_contact"] = True
    world["first_contact_done"] = True
    _chronicle(world, player, f"Рим впервые получил прямое донесение о народе {tribe['name']}.", "warning")


def _force_contact_after_quiet_turns(world: dict, player: Any) -> None:
    """Не даёт симуляции надолго уйти в невидимый фоновый режим."""
    if _i(world.get("quiet_turns"), 0) < 2:
        return
    if any(not x.get("resolved") for x in world.get("incidents", [])):
        return
    tribes = [t for t in world["tribes"].values() if t.get("status") != "destroyed" and not t.get("federate")]
    if not tribes:
        return
    tribe = max(tribes, key=lambda t: t.get("pressure", 0) + t.get("hunger", 0) + t.get("aggression", 0) // 2)
    if tribe.get("pressure", 0) >= 55:
        _add_incident(
            world, player, "raid", tribe["key"], tribe["region"], 2,
            f"Пограничная тревога: {tribe['name']}",
            f"После нескольких тихих лет дружины {tribe['name']} снова испытывают римский рубеж на прочность.",
            {"enemy_strength": max(30, tribe.get("warriors", 0) // 80)},
        )
    else:
        _add_incident(
            world, player, "embassy", tribe["key"], tribe["region"], 1,
            f"Послы из-за лимеса: {tribe['name']}",
            f"Люди вождя {tribe['chief']} прибыли узнать намерения Рима и предложить обмен дарами.",
        )
    world["quiet_turns"] = 0


def _frontier_changes(before: dict[str, int], world: dict) -> list[str]:
    changes = []
    for key, frontier in world["frontiers"].items():
        old = _i(before.get(key), frontier.get("pressure", 0))
        new = _i(frontier.get("pressure"), old)
        delta = new - old
        if abs(delta) >= 7 or (old < 50 <= new) or (old < 70 <= new):
            direction = "выросло" if delta > 0 else "снизилось"
            changes.append(f"{frontier['name']}: давление {direction} до {new}/100 ({delta:+}).")
    return changes


def _incident_priority(item: dict) -> tuple[int, int]:
    kind_weight = {"migration": 6, "confederation": 5, "raid": 4, "tribute": 3, "mercenaries": 2, "hostages": 2, "embassy": 1}
    return (_i(item.get("severity"), 1) * 10 + kind_weight.get(str(item.get("kind")), 1), -_i(item.get("created_turn"), 0))


def show_turn_briefing(player: Any, ctx: dict | None = None, force: bool = False) -> None:
    """Единый Совет пограничных легатов после завершения остальных событий."""
    world = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 0), 0)
    if _i(world.get("last_briefing_turn"), 0) == turn and not force:
        return
    mode = str(world.get("settings", {}).get("briefing_mode", "important"))
    new_ids = set(_list(world.get("last_turn_new_incidents")))
    new_items = [x for x in world["incidents"] if x.get("id") in new_ids and not x.get("resolved")]
    open_items = [x for x in world["incidents"] if not x.get("resolved")]
    report = list(world.get("last_world_report", []))
    changes = list(world.get("last_turn_frontier_changes", []))
    max_frontier = max(world["frontiers"].values(), key=lambda f: _i(f.get("pressure"), 0))
    substantive_report = any("крупных перемещений не отмечено" not in str(line) for line in report)
    important = bool(new_items or changes or substantive_report or _i(max_frontier.get("pressure"), 0) >= 55)
    if mode == "silent" and not force:
        return
    if mode == "important" and not important and turn - _i(world.get("last_briefing_turn"), 0) < 3 and not force:
        return

    world["last_briefing_turn"] = turn
    ui = UI(ctx)
    ui.screen()
    ui.header("СОВЕТ ПОГРАНИЧНЫХ ЛЕГАТОВ", "🐺", "донесения после завершения гражданских, военных и дипломатических дел")
    ui.info(
        f"Главный риск: {max_frontier['name']} — {_i(max_frontier.get('pressure'), 0)}/100. "
        f"Открытых дел: {len(open_items)}; лагерей: {len(world['camps'])}; переселений: "
        f"{len([m for m in world['migrations'] if m.get('stage') != 'resolved'])}.",
        "GOLD",
    )
    news = []
    for line in changes[-3:] + report[-5:]:
        if line not in news:
            news.append(line)
    if not news:
        news.append("Разведчики не отмечают крупных передвижений, но наблюдение за лимесом продолжается.")
    ui.section("Донесения", "CYAN")
    for line in news[-6:]:
        ui.wrap("• " + line, "WHITE")

    if new_items:
        rows = []
        for item in sorted(new_items, key=_incident_priority, reverse=True)[:5]:
            tribe = world["tribes"].get(item.get("tribe_key"), {})
            rows.append((item.get("title", "Событие"), tribe.get("name", "?"), str(item.get("severity", 1)), FRONTIERS.get(item.get("frontier"), {}).get("name", "?")))
        ui.table("Новые пограничные дела", ["Событие", "Народ", "Угр.", "Рубеж"], rows, "RED")

    if open_items and world.get("settings", {}).get("auto_crisis", True):
        urgent = max(open_items, key=_incident_priority)
        ui.menu([
            ("1", "Рассмотреть главное дело", urgent.get("title", "пограничный кризис"), "🔥"),
            ("2", "Открыть весь Barbaricum", "карта, племена, лагеря и летопись", "🗺"),
            ("3", "Продолжить", "оставить остальные дела в очереди", "↩"),
        ], "Решение легата")
        ch = ui.choice("  Приказ: ", ["1", "2", "3"])
        if ch == "1":
            resolve_incident_menu(player, urgent["id"], ctx, automatic=True)
        elif ch == "2":
            open_menu(player, ctx)
    else:
        if open_items:
            ui.info("Автоматическое рассмотрение отключено: дела сохранены в меню Barbaricum.", "GOLD")
        ui.pause()


def _expire_incidents(world: dict, player: Any, ctx: dict | None) -> None:
    turn = _i(getattr(player, "turn", 0), 0)
    for incident in world["incidents"]:
        if incident.get("resolved") or turn <= _i(incident.get("expires_turn"), turn + 1):
            continue
        incident["resolved"] = True
        incident["resolution"] = "Рим не ответил"
        tribe = world["tribes"].get(incident.get("tribe_key"), {})
        kind = incident.get("kind")
        if kind == "raid":
            _apply_raid_damage(player, tribe, incident, ctx, ignored=True)
        elif kind == "migration":
            _apply_forced_settlement(player, tribe, incident, world, ctx)
        elif kind in ("embassy", "hostages"):
            tribe["relation"] = _clamp(tribe.get("relation", 50) - 7)
            tribe["trust"] = _clamp(tribe.get("trust", 30) - 10)
        elif kind == "tribute":
            tribe["pressure"] = _clamp(tribe.get("pressure", 30) + 12)
        _chronicle(world, player, f"Рим не ответил на событие «{incident.get('title')}». Последствия наступили сами.", "warning")


def _federate_tick(world: dict, player: Any, ctx: dict | None) -> None:
    active = []
    for fed in world["federates"]:
        tribe = world["tribes"].get(fed.get("tribe_key"))
        if not tribe:
            continue
        pay = _i(fed.get("pay"), 12)
        grain = _i(fed.get("grain"), 8)
        if _i(getattr(player, "gold", 0), 0) >= pay and _i(getattr(player, "grain", 0), 0) >= grain:
            player.gold -= pay
            player.grain -= grain
            fed["loyalty"] = _clamp(fed.get("loyalty", 50) + random.randint(0, 3))
            tribe["relation"] = _clamp(tribe["relation"] + 1)
            tribe["trust"] = _clamp(tribe["trust"] + 1)
        else:
            fed["loyalty"] = _clamp(fed.get("loyalty", 50) - random.randint(6, 14))
            tribe["grievance"] = _clamp(tribe["grievance"] + 10)
        if fed["loyalty"] <= 18:
            tribe["federate"] = False
            tribe["pact"] = False
            tribe["pressure"] = _clamp(tribe["pressure"] + 25)
            _add_incident(
                world, player, "raid", tribe["key"], tribe["region"], 4,
                "Мятеж федератов",
                f"Не получив платы, федераты {tribe['name']} покинули службу и грабят приграничные земли.",
                {"enemy_strength": max(35, fed.get("warriors", 1000) // 25)},
            )
            _chronicle(world, player, f"Федераты {tribe['name']} восстали из-за невыплаты содержания.", "danger")
            continue
        active.append(fed)
    world["federates"] = active


def process_turn(player: Any, ctx: dict | None = None, interactive: bool = True) -> list[str]:
    world = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 0), 0)
    if _i(world.get("turn_processed"), 0) == turn:
        if interactive:
            show_turn_briefing(player, ctx)
        return []
    world["turn_processed"] = turn
    world["last_world_report"] = []

    before_incidents = {x.get("id") for x in world["incidents"] if isinstance(x, dict)}
    before_frontiers = {key: _i(value.get("pressure"), 0) for key, value in world["frontiers"].items()}

    _federate_tick(world, player, ctx)
    roman_power = _roman_power(player)
    for tribe in world["tribes"].values():
        _tick_tribe(world, player, tribe, roman_power)
    _tick_rivalries(world, player)
    _tick_camps(world, player)
    _tick_migrations(world, player)
    _tick_frontiers(world, player)
    _tick_confederations(world, player)
    _maybe_confederation(world, player)
    _maybe_peaceful_contact(world, player)
    _ensure_first_contact(world, player)
    _expire_incidents(world, player, ctx)

    average_pressure = sum(f["pressure"] for f in world["frontiers"].values()) // max(1, len(world["frontiers"]))
    world["great_migration_level"] = _clamp(
        world.get("great_migration_level", 0)
        + (2 if average_pressure >= 70 else 1 if average_pressure >= 50 else -1)
        + len([m for m in world["migrations"] if m.get("stage") != "resolved"]),
        0, 100, 0,
    )
    _maybe_great_migration(world, player)

    current_ids = {x.get("id") for x in world["incidents"] if isinstance(x, dict)}
    new_ids = [x for x in current_ids - before_incidents if x]
    if new_ids:
        world["quiet_turns"] = 0
    else:
        world["quiet_turns"] = _i(world.get("quiet_turns"), 0) + 1
        _force_contact_after_quiet_turns(world, player)
        current_ids = {x.get("id") for x in world["incidents"] if isinstance(x, dict)}
        new_ids = [x for x in current_ids - before_incidents if x]

    world["last_turn_new_incidents"] = new_ids
    world["last_turn_frontier_changes"] = _frontier_changes(before_frontiers, world)

    _sync_legacy(player, world, import_changes=False)
    report = list(world.get("last_world_report", []))
    if not report:
        top = max(world["frontiers"].values(), key=lambda f: _i(f.get("pressure"), 0))
        report = [f"{top['name']}: давление {_i(top.get('pressure'), 0)}/100; крупных перемещений не отмечено."]
        world["last_world_report"] = list(report)
    if report:
        _summary(player, ctx, f"Barbaricum: {report[-1]}")
        for line in report[-4:]:
            _log(player, ctx, "Barbaricum: " + line)

    if interactive:
        show_turn_briefing(player, ctx)
    return report


def legacy_tick_hook(player: Any, ctx: dict | None = None) -> None:
    """Старая barbarian_ai_tick отключена: новый мир считается один раз после хода."""
    ensure_state(player, ctx)
    return None


def legacy_gift_hook(player: Any, ctx: dict | None = None) -> None:
    """Старые случайные подарки отключены; контакты идут через события Barbaricum."""
    ensure_state(player, ctx)
    return None


def _incident(world: dict, incident_id: str) -> dict | None:
    return next((x for x in world["incidents"] if x.get("id") == incident_id), None)


def _migration(world: dict, migration_id: str | None) -> dict | None:
    return next((x for x in world["migrations"] if x.get("id") == migration_id), None)


def _camp(world: dict, camp_id: str | None) -> dict | None:
    return next((x for x in world["camps"] if x.get("id") == camp_id), None)


def _resolve(incident: dict, resolution: str) -> None:
    incident["resolved"] = True
    incident["resolution"] = resolution


def _apply_raid_damage(player: Any, tribe: dict, incident: dict, ctx: dict | None, ignored: bool = False) -> None:
    severity = _i(incident.get("severity"), 1, 1, 5)
    frontier = FRONTIERS.get(incident.get("frontier"), {})
    target = _owned_province(player, frontier.get("provinces", []))
    gold_loss = random.randint(8, 18) * severity
    grain_loss = random.randint(5, 14) * severity
    if ignored:
        gold_loss = int(gold_loss * 1.25)
        grain_loss = int(grain_loss * 1.25)
    player.gold = max(0, _i(getattr(player, "gold", 0), 0) - gold_loss)
    player.grain = max(0, _i(getattr(player, "grain", 0), 0) - grain_loss)
    if target is not None:
        target["unrest"] = min(10, _i(target.get("unrest"), 0) + max(1, severity // 2))
    tribe["wealth"] += max(1, gold_loss // 12)
    tribe["prestige"] += severity * 2
    tribe["victories"] += 1
    tribe["pressure"] = _clamp(tribe["pressure"] + 5)
    province_name = target.get("name") if target else "пограничье"
    _log(player, ctx, f"Набег {tribe.get('name')}: {province_name}, -{gold_loss} золота, -{grain_loss} зерна")


def _apply_forced_settlement(player: Any, tribe: dict, incident: dict, world: dict, ctx: dict | None) -> None:
    migration = _migration(world, _dict(incident.get("payload")).get("migration_id"))
    if not migration:
        return
    target = _owned_province(player, FRONTIERS.get(migration["frontier"], {}).get("provinces", []))
    if target:
        target["unrest"] = min(10, _i(target.get("unrest"), 0) + 3)
    player.grain = max(0, _i(getattr(player, "grain", 0), 0) - max(20, migration["people"] // 500))
    migration["stage"] = "resolved"
    migration["resolution"] = "самовольное поселение"
    tribe["relation"] = _clamp(tribe["relation"] - 10)
    _log(player, ctx, f"Самовольное поселение {tribe.get('name')} вызвало беспорядки")


def _battle_response(player: Any, tribe: dict, incident: dict, world: dict, ctx: dict | None) -> bool | None:
    strength = _i(_dict(incident.get("payload")).get("enemy_strength"), 0)
    if strength <= 0:
        strength = max(24, tribe["warriors"] // 45 + incident["severity"] * 7)
    enemy = {
        "name": f"{tribe['name']}: {INCIDENT_LABELS.get(incident['kind'], incident['kind'])}",
        "strength": strength,
        "battle_mod": max(0, tribe["cohesion"] // 20 + incident["severity"]),
        "terrain_penalty": 2 if tribe["tactic"] in ("лесная засада", "засады в нагорьях") else 0,
    }
    fn = _ctx(ctx).get("barbarian_event_counterattack")
    if callable(fn):
        frontier = FRONTIERS.get(incident.get("frontier"), {})
        target = _owned_province(player, frontier.get("provinces", []))
        try:
            return fn(
                player, enemy, incident.get("title", "варварская угроза"),
                province_name=target.get("name") if target else None,
                tribe_key=tribe["key"],
                reward_glory=6 + incident["severity"] * 3,
            )
        except Exception:
            pass

    roman = _roman_power(player) + random.randint(1, 30)
    barbarian = strength // 3 + tribe["cohesion"] // 5 + random.randint(1, 30)
    if roman >= barbarian:
        player.glory = _i(getattr(player, "glory", 0), 0) + incident["severity"] * 5
        return True
    player.morale = max(0, _i(getattr(player, "morale", 70), 70) - incident["severity"] * 2)
    return False


def _settle_as_federates(player: Any, tribe: dict, incident: dict, world: dict, ctx: dict | None) -> bool:
    migration = _migration(world, _dict(incident.get("payload")).get("migration_id"))
    if not migration:
        return False
    gold = max(45, migration["people"] // 220)
    grain = max(60, migration["people"] // 170)
    if _i(getattr(player, "gold", 0), 0) < gold or _i(getattr(player, "grain", 0), 0) < grain:
        return False
    player.gold -= gold
    player.grain -= grain
    fed = {
        "id": _next_id(world, "FOED"),
        "tribe_key": tribe["key"],
        "people": migration["people"],
        "warriors": migration["warriors"],
        "loyalty": max(35, tribe["trust"]),
        "pay": max(8, migration["warriors"] // 500),
        "grain": max(5, migration["people"] // 2500),
        "frontier": migration["frontier"],
    }
    world["federates"].append(fed)
    tribe["federate"] = True
    tribe["pact"] = True
    tribe["relation"] = _clamp(tribe["relation"] + 18)
    tribe["trust"] = _clamp(tribe["trust"] + 15)
    tribe["pressure"] = max(0, tribe["pressure"] - 30)
    migration["stage"] = "resolved"
    migration["resolution"] = "федераты"
    player.morale = min(100, _i(getattr(player, "morale", 70), 70) + 2)
    # Первое федератское подразделение немедленно поступает на службу.
    unit_defs = _ctx(ctx).get("BARBARIAN_UNITS", [])
    add_fn = _ctx(ctx).get("add_aux_unit")
    if callable(add_fn) and unit_defs:
        try:
            add_fn(player, random.choice(unit_defs), free=True)
        except Exception:
            pass
    _log(player, ctx, f"{tribe['name']} поселены как федераты: {migration['warriors']} воинов")
    return True


def _hire_mercenaries(player: Any, tribe: dict, world: dict, ctx: dict | None) -> bool:
    cost = max(45, tribe["warriors"] // 90)
    if _i(getattr(player, "gold", 0), 0) < cost:
        return False
    player.gold -= cost
    unit_defs = _ctx(ctx).get("BARBARIAN_UNITS", [])
    add_fn = _ctx(ctx).get("add_aux_unit")
    if callable(add_fn) and unit_defs:
        try:
            unit = random.choice(unit_defs)
            add_fn(player, unit, free=True)
        except Exception:
            pass
    else:
        player.morale = min(100, _i(getattr(player, "morale", 70), 70) + 3)
    tribe["warriors"] = max(0, tribe["warriors"] - random.randint(300, 700))
    tribe["wealth"] += cost // 12
    tribe["relation"] = _clamp(tribe["relation"] + 6)
    tribe["trust"] = _clamp(tribe["trust"] + 4)
    _log(player, ctx, f"Нанят варварский отряд у {tribe['name']}")
    return True


def resolve_incident_menu(player: Any, incident_id: str, ctx: dict | None = None, automatic: bool = False) -> None:
    world = ensure_state(player, ctx)
    incident = _incident(world, incident_id)
    if not incident or incident.get("resolved"):
        return
    tribe = world["tribes"].get(incident.get("tribe_key"))
    if not tribe:
        _resolve(incident, "племя исчезло")
        return
    ui = UI(ctx)
    ui.screen()
    ui.header(incident["title"], "🐺", f"{tribe['name']} • {FRONTIERS[incident['frontier']]['name']} • угроза {incident['severity']}/5")
    ui.wrap(incident["text"], "WHITE")
    ui.info(f"Вождь: {tribe['chief']} ({tribe['trait']}); отношения {tribe['relation']}, доверие {tribe['trust']}, страх {tribe['fear']}", "GRAY")
    kind = incident["kind"]

    if kind == "raid":
        entries = [
            ("1", "Встретить боем", "легион, ауксилия или артиллерия", "⚔"),
            ("2", "Заплатить и выиграть время", f"{25 + incident['severity']*12} золота", "💰"),
            ("3", "Отправить послов", "шанс рассеять дружину без боя", "🤝"),
            ("4", "Оставить провинции самим себе", "набег нанесёт полный ущерб", "…"),
        ]
        ui.menu(entries, "Ответ Рима")
        ch = ui.choice("  Решение: ", [e[0] for e in entries])
        if ch == "1":
            won = _battle_response(player, tribe, incident, world, ctx)
            if won is True:
                loss = random.randint(300, 900) * incident["severity"]
                tribe["warriors"] = max(0, tribe["warriors"] - loss)
                tribe["defeats"] += 1
                tribe["fear"] = _clamp(tribe["fear"] + 12)
                tribe["pressure"] = max(0, tribe["pressure"] - 18)
                camp = _camp(world, _dict(incident.get("payload")).get("camp_id"))
                if camp:
                    camp["strength"] = max(0, camp["strength"] - incident["severity"] * 10)
                _resolve(incident, "разгромлено")
                ui.info("Римские силы рассеяли набег.", "GREEN")
            elif won is False:
                _apply_raid_damage(player, tribe, incident, ctx)
                _resolve(incident, "Рим проиграл бой")
                ui.info("Набег прорвался через заслон.", "RED")
            else:
                ui.info("Боевой приказ не отдан; событие остаётся открытым.", "GOLD")
        elif ch == "2":
            cost = 25 + incident["severity"] * 12
            if _i(getattr(player, "gold", 0), 0) >= cost:
                player.gold -= cost
                tribe["wealth"] += cost // 10
                tribe["relation"] = _clamp(tribe["relation"] + 3)
                tribe["pressure"] = _clamp(tribe["pressure"] + 7)
                _resolve(incident, "откуп")
                ui.info("Дружина взяла золото и ушла. Она запомнит слабость Рима.", "GOLD")
            else:
                ui.info("В казне недостаточно золота.", "RED")
        elif ch == "3":
            chance = 32 + tribe["relation"] // 3 + tribe["fear"] // 4 - tribe["aggression"] // 5
            if random.randint(1, 100) <= chance:
                tribe["relation"] = _clamp(tribe["relation"] + 5)
                tribe["trust"] = _clamp(tribe["trust"] + 3)
                tribe["pressure"] = max(0, tribe["pressure"] - 8)
                _resolve(incident, "улажено послами")
                ui.info("Вождь отозвал дружину.", "GREEN")
            else:
                tribe["relation"] = _clamp(tribe["relation"] - 5)
                ui.info("Переговоры провалились; событие остаётся открытым.", "RED")
        else:
            _apply_raid_damage(player, tribe, incident, ctx, ignored=True)
            _resolve(incident, "проигнорировано")
            ui.info("Пограничные общины заплатили за бездействие Рима.", "RED")

    elif kind == "migration":
        migration = _migration(world, _dict(incident.get("payload")).get("migration_id"))
        entries = [
            ("1", "Поселить как федератов", "земля и содержание в обмен на военную службу", "🛡"),
            ("2", "Допустить мирное расселение", "зерно и временные волнения", "🏘"),
            ("3", "Перенаправить к соседям", "дипломатия и риск конфликта", "🧭"),
            ("4", "Закрыть границу силой", "вероятен тяжёлый бой", "⚔"),
        ]
        ui.menu(entries, "Судьба переселенцев")
        ch = ui.choice("  Решение: ", [e[0] for e in entries])
        if ch == "1":
            if _settle_as_federates(player, tribe, incident, world, ctx):
                _resolve(incident, "приняты федератами")
                ui.info("Переселенцы получили землю и приняли воинскую присягу.", "GREEN")
            else:
                ui.info("Не хватает золота и зерна для расселения.", "RED")
        elif ch == "2" and migration:
            grain = max(35, migration["people"] // 260)
            if _i(getattr(player, "grain", 0), 0) >= grain:
                player.grain -= grain
                target = _owned_province(player, FRONTIERS[migration["frontier"]]["provinces"])
                if target:
                    target["unrest"] = min(10, _i(target.get("unrest"), 0) + 2)
                tribe["relation"] = _clamp(tribe["relation"] + 12)
                tribe["trust"] = _clamp(tribe["trust"] + 8)
                migration["stage"] = "resolved"
                migration["resolution"] = "мирное расселение"
                _resolve(incident, "мирное расселение")
                ui.info(f"Рим выделил {grain} зерна и земли для поселения.", "GREEN")
            else:
                ui.info("Не хватает зерна.", "RED")
        elif ch == "3" and migration:
            chance = 45 + tribe["trust"] // 3 + world["frontiers"][migration["frontier"]]["intel"] // 4
            if random.randint(1, 100) <= chance:
                migration["stage"] = "resolved"
                migration["resolution"] = "перенаправлены"
                tribe["relation"] = _clamp(tribe["relation"] - 3)
                tribe["pressure"] = max(0, tribe["pressure"] - 10)
                _resolve(incident, "перенаправлены")
                ui.info("Колонна повернула в земли другого народа.", "GREEN")
            else:
                tribe["relation"] = _clamp(tribe["relation"] - 8)
                ui.info("Переселенцы отказались менять путь.", "RED")
        elif ch == "4":
            incident.setdefault("payload", {})["enemy_strength"] = max(35, (migration or {}).get("warriors", 1500) // 30)
            won = _battle_response(player, tribe, incident, world, ctx)
            if won is True:
                if migration:
                    migration["stage"] = "resolved"
                    migration["resolution"] = "отброшены силой"
                tribe["relation"] = 0
                tribe["grievance"] = _clamp(tribe["grievance"] + 40)
                tribe["fear"] = _clamp(tribe["fear"] + 18)
                _resolve(incident, "граница закрыта силой")
                ui.info("Колонна отброшена, но кровная вражда останется надолго.", "GOLD")
            elif won is False:
                _apply_forced_settlement(player, tribe, incident, world, ctx)
                _resolve(incident, "граница прорвана")
                ui.info("Переселенцы прорвали границу.", "RED")

    elif kind in ("embassy", "hostages"):
        entries = [
            ("1", "Принять с почестями", "35 золота; растут отношения и доверие", "🎁"),
            ("2", "Заключить пограничный пакт", "нужны отношения 55 и доверие 35", "📜"),
            ("3", "Отпустить без обязательств", "малый эффект", "↩"),
        ]
        ui.menu(entries, "Приём посольства")
        ch = ui.choice("  Решение: ", [e[0] for e in entries])
        if ch == "1" and _i(getattr(player, "gold", 0), 0) >= 35:
            player.gold -= 35
            tribe["relation"] = _clamp(tribe["relation"] + 12)
            tribe["trust"] = _clamp(tribe["trust"] + 10)
            tribe["hostages"] = kind == "hostages" or tribe.get("hostages")
            _resolve(incident, "принято с почестями")
            ui.info("Послы уезжают довольными.", "GREEN")
        elif ch == "2":
            if tribe["relation"] >= 55 and tribe["trust"] >= 35:
                tribe["pact"] = True
                tribe["pressure"] = max(0, tribe["pressure"] - 18)
                tribe["relation"] = _clamp(tribe["relation"] + 5)
                _resolve(incident, "пограничный пакт")
                ui.info("Граница закреплена клятвами и обменом заложниками.", "GREEN")
            else:
                ui.info("Доверия пока недостаточно.", "RED")
        else:
            tribe["relation"] = _clamp(tribe["relation"] + 1)
            _resolve(incident, "без обязательств")

    elif kind == "mercenaries":
        ui.menu([
            ("1", "Нанять дружину", "получить варварскую ауксилию", "🪓"),
            ("2", "Отказать", "без расходов", "↩"),
        ], "Предложение вождя")
        ch = ui.choice("  Решение: ", ["1", "2"])
        if ch == "1" and _hire_mercenaries(player, tribe, world, ctx):
            _resolve(incident, "наняты")
            ui.info("Дружина поступила на римскую службу.", "GREEN")
        elif ch == "1":
            ui.info("Недостаточно золота.", "RED")
        else:
            _resolve(incident, "отказ")

    elif kind == "tribute":
        cost = 30 + incident["severity"] * 15
        ui.menu([
            ("1", "Заплатить", f"{cost} золота", "💰"),
            ("2", "Отвергнуть требование", "отношения ухудшатся, давление вырастет", "✋"),
            ("3", "Арестовать послов", "casus belli племени против Рима", "⛓"),
        ], "Ответ на требование")
        ch = ui.choice("  Решение: ", ["1", "2", "3"])
        if ch == "1" and _i(getattr(player, "gold", 0), 0) >= cost:
            player.gold -= cost
            tribe["wealth"] += cost // 10
            tribe["pressure"] = max(0, tribe["pressure"] - 8)
            _resolve(incident, "дань уплачена")
        elif ch == "1":
            ui.info("Недостаточно золота.", "RED")
        elif ch == "2":
            tribe["relation"] = _clamp(tribe["relation"] - 8)
            tribe["pressure"] = _clamp(tribe["pressure"] + 12)
            _resolve(incident, "требование отвергнуто")
        else:
            tribe["relation"] = 0
            tribe["grievance"] = _clamp(tribe["grievance"] + 35)
            tribe["pressure"] = _clamp(tribe["pressure"] + 20)
            _resolve(incident, "послы арестованы")

    elif kind == "confederation":
        ui.menu([
            ("1", "Послать щедрые дары", "попытаться расколоть союз", "🎁"),
            ("2", "Подкупить младших вождей", "тайная операция", "🗡"),
            ("3", "Готовить границу к войне", "+укрепления и патрули", "🧱"),
        ], "Римская стратегия")
        ch = ui.choice("  Решение: ", ["1", "2", "3"])
        conf = next((c for c in world["confederations"] if c.get("id") == _dict(incident.get("payload")).get("confederation_id")), None)
        if ch == "1" and _i(getattr(player, "gold", 0), 0) >= 90:
            player.gold -= 90
            tribe["relation"] = _clamp(tribe["relation"] + 8)
            if conf:
                conf["cohesion"] = max(10, conf["cohesion"] - random.randint(8, 18))
            _resolve(incident, "дары отправлены")
        elif ch == "2" and _i(getattr(player, "gold", 0), 0) >= 70:
            player.gold -= 70
            chance = 45 + world["frontiers"][incident["frontier"]]["intel"] // 3
            if random.randint(1, 100) <= chance and conf:
                conf["cohesion"] = max(0, conf["cohesion"] - random.randint(20, 40))
                tribe["trust"] = _clamp(tribe["trust"] - 5)
                ui.info("Младшие вожди приняли золото; союз трещит.", "GREEN")
            else:
                tribe["grievance"] = _clamp(tribe["grievance"] + 12)
                ui.info("Заговор раскрыт.", "RED")
            _resolve(incident, "тайная операция")
        elif ch == "3":
            frontier = world["frontiers"][incident["frontier"]]
            frontier["fortification"] = _clamp(frontier["fortification"] + 18)
            frontier["patrols"] = _clamp(frontier["patrols"] + 15)
            _resolve(incident, "граница укреплена")
        else:
            ui.info("Недостаточно средств.", "RED")

    _sync_legacy(player, world, import_changes=False)
    if incident.get("resolved"):
        _chronicle(world, player, f"Событие «{incident['title']}»: {incident.get('resolution', 'решено')}.", "info")
    if not automatic or incident.get("resolved"):
        ui.pause()


def _tribe_status(tribe: dict) -> str:
    if tribe.get("federate"):
        return "федераты"
    if tribe.get("status") == "confederate":
        return "в конфедерации"
    if tribe.get("pact"):
        return "пакт"
    if tribe.get("status") == "destroyed":
        return "рассеяны"
    return "независимы"


def show_world_overview(player: Any, ctx: dict | None = None) -> None:
    world = ensure_state(player, ctx)
    ui = UI(ctx)
    ui.screen()
    ui.header("BARBARICUM: МИР ЗА ЛИМЕСОМ", "🐺", "племена, миграции, лагеря, конфедерации и федераты")
    rows = []
    for key, frontier in world["frontiers"].items():
        tribes = [t for t in world["tribes"].values() if t["region"] == key and t.get("status") != "destroyed"]
        camps = len([c for c in world["camps"] if c.get("frontier") == key])
        migrations = len([m for m in world["migrations"] if m.get("frontier") == key and m.get("stage") != "resolved"])
        rows.append((frontier["name"], str(frontier["pressure"]), str(frontier["intel"]), str(frontier["fortification"]), str(camps), str(migrations), ", ".join(t["name"] for t in tribes)))
    ui.table("Рубежи", ["Фронтир", "Давл.", "Разв.", "Укр.", "Лаг.", "Мигр.", "Народы"], rows, "RED")
    unresolved = len([x for x in world["incidents"] if not x.get("resolved")])
    ui.info(f"Открытые события: {unresolved} | лагеря: {len(world['camps'])} | активные переселения: {len([m for m in world['migrations'] if m.get('stage') != 'resolved'])} | федераты: {len(world['federates'])}", "GOLD")
    ui.info(f"Индекс Великого переселения: {world['great_migration_level']}/100", "PURPLE")
    ui.pause()


def tribe_detail_menu(player: Any, tribe_key: str, ctx: dict | None = None) -> None:
    world = ensure_state(player, ctx)
    tribe = world["tribes"].get(tribe_key)
    if not tribe:
        return
    ui = UI(ctx)
    while True:
        ui.screen()
        ui.header(tribe["name"], "🪓", f"{tribe['culture']} • {tribe['homeland']} • {_tribe_status(tribe)}")
        intel = max(tribe["intelligence"], world["frontiers"][tribe["region"]]["intel"])
        ui.info(f"Вождь: {tribe['chief']} — {tribe['trait']}; тактика: {tribe['tactic']}", "CYAN")
        if intel >= 25:
            ui.info(f"Население ~{tribe['population']} | воинов ~{tribe['warriors']} | богатство {tribe['wealth']} | сплочённость {tribe['cohesion']}", "WHITE")
        else:
            ui.info("Точные сведения о населении и войске отсутствуют.", "GRAY")
        ui.info(f"Отношения {tribe['relation']} | доверие {tribe['trust']} | страх {tribe['fear']} | агрессивность {tribe['aggression']} | давление {tribe['pressure']} | голод {tribe['hunger']}", "GOLD")
        ui.menu([
            ("1", "Отправить дары", "40 золота: отношения и доверие", "🎁"),
            ("2", "Послать разведчиков", "30 золота: разведка фронтира и племени", "👁"),
            ("3", "Предложить пограничный пакт", "отношения 55, доверие 35", "📜"),
            ("4", "Нанять дружину", "варварская ауксилия", "🪓"),
            ("5", "Потребовать заложников", "страх 45 или хорошие отношения", "⛓"),
            ("Q", "Назад", "", "↩"),
        ])
        ch = ui.choice("  Решение: ", ["1", "2", "3", "4", "5", "Q"])
        if ch == "Q":
            return
        if ch == "1":
            if _i(getattr(player, "gold", 0), 0) >= 40:
                player.gold -= 40
                tribe["relation"] = _clamp(tribe["relation"] + random.randint(7, 13))
                tribe["trust"] = _clamp(tribe["trust"] + random.randint(3, 8))
                tribe["wealth"] += 3
                _chronicle(world, player, f"Рим отправил дары племени {tribe['name']}.")
            else:
                ui.info("Недостаточно золота.", "RED")
        elif ch == "2":
            if _i(getattr(player, "gold", 0), 0) >= 30:
                player.gold -= 30
                gain = random.randint(12, 25)
                tribe["intelligence"] = _clamp(tribe["intelligence"] + gain)
                frontier = world["frontiers"][tribe["region"]]
                frontier["intel"] = _clamp(frontier["intel"] + gain // 2)
                ui.info(f"Разведывательное покрытие выросло на {gain}.", "GREEN")
            else:
                ui.info("Недостаточно золота.", "RED")
        elif ch == "3":
            if tribe["relation"] >= 55 and tribe["trust"] >= 35:
                tribe["pact"] = True
                tribe["pressure"] = max(0, tribe["pressure"] - 15)
                tribe["relation"] = _clamp(tribe["relation"] + 4)
                _chronicle(world, player, f"Заключён пограничный пакт с {tribe['name']}.", "good")
            else:
                ui.info("Племя пока не доверяет Риму.", "RED")
        elif ch == "4":
            if not _hire_mercenaries(player, tribe, world, ctx):
                ui.info("Не хватает золота.", "RED")
        elif ch == "5":
            chance = 25 + tribe["fear"] // 2 + tribe["relation"] // 4 - tribe["prestige"] // 8
            if random.randint(1, 100) <= chance:
                tribe["hostages"] = True
                tribe["trust"] = _clamp(tribe["trust"] + 5)
                tribe["pressure"] = max(0, tribe["pressure"] - 8)
                ui.info("Знатные семьи прислали заложников.", "GREEN")
            else:
                tribe["relation"] = _clamp(tribe["relation"] - 9)
                tribe["grievance"] = _clamp(tribe["grievance"] + 8)
                ui.info("Требование сочли оскорблением.", "RED")
        _sync_legacy(player, world, import_changes=False)
        ui.pause()


def tribes_menu(player: Any, ctx: dict | None = None) -> None:
    world = ensure_state(player, ctx)
    ui = UI(ctx)
    while True:
        ui.screen()
        ui.header("ПЛЕМЕНА И ВОЖДИ", "🪓", "не просто армии, а народы со своими интересами")
        keys = list(world["tribes"])
        rows = []
        for i, key in enumerate(keys, 1):
            t = world["tribes"][key]
            rows.append((str(i), t["name"], t["chief"], FRONTIERS[t["region"]]["name"], str(_legacy_strength(t)), str(t["relation"]), str(t["pressure"]), _tribe_status(t)))
        ui.table("Народы", ["#", "Племя", "Вождь", "Рубеж", "Сила", "Отн.", "Давл.", "Статус"], rows, "RED")
        valid = [str(i) for i in range(1, len(keys) + 1)] + ["Q"]
        ch = ui.choice("  Племя (Q — назад): ", valid)
        if ch == "Q":
            return
        tribe_detail_menu(player, keys[int(ch) - 1], ctx)


def incidents_menu(player: Any, ctx: dict | None = None) -> None:
    world = ensure_state(player, ctx)
    ui = UI(ctx)
    while True:
        open_items = [x for x in world["incidents"] if not x.get("resolved")]
        ui.screen()
        ui.header("ПОГРАНИЧНЫЕ СОБЫТИЯ", "🔥", "события живут несколько ходов и имеют последствия")
        if not open_items:
            ui.info("Нерешённых событий нет.", "GREEN")
            ui.pause()
            return
        rows = []
        for i, item in enumerate(open_items, 1):
            tribe = world["tribes"].get(item["tribe_key"], {})
            rows.append((str(i), item["title"], tribe.get("name", "?"), FRONTIERS[item["frontier"]]["name"], str(item["severity"]), str(max(0, item["expires_turn"] - _i(getattr(player, "turn", 0), 0)))))
        ui.table("Открытые дела", ["#", "Событие", "Племя", "Рубеж", "Угр.", "Ходов"], rows, "RED")
        ch = ui.choice("  Открыть событие (Q — назад): ", [str(i) for i in range(1, len(open_items) + 1)] + ["Q"])
        if ch == "Q":
            return
        resolve_incident_menu(player, open_items[int(ch) - 1]["id"], ctx)


def camps_menu(player: Any, ctx: dict | None = None) -> None:
    world = ensure_state(player, ctx)
    ui = UI(ctx)
    while True:
        ui.screen()
        ui.header("ЛАГЕРЯ И ПЕРЕСЕЛЕНИЯ", "⛺", "лагерь растёт, если его игнорировать")
        rows = []
        for i, camp in enumerate(world["camps"], 1):
            tribe = world["tribes"].get(camp["tribe_key"], {})
            rows.append((f"C{i}", tribe.get("name", "?"), FRONTIERS[camp["frontier"]]["name"], str(camp["stage"]), str(camp["strength"]), str(camp["readiness"]), str(camp["concealment"])))
        for i, mig in enumerate([m for m in world["migrations"] if m.get("stage") != "resolved"], 1):
            tribe = world["tribes"].get(mig["tribe_key"], {})
            rows.append((f"M{i}", tribe.get("name", "?"), FRONTIERS[mig["frontier"]]["name"], "миграция", str(mig["warriors"]), mig["stage"], str(mig["people"])))
        if rows:
            ui.table("Объекты за лимесом", ["#", "Племя", "Рубеж", "Стадия", "Сила", "Готовн.", "Люди/скр."], rows, "GOLD")
        else:
            ui.info("Разведка не видит крупных лагерей или переселений.", "GREEN")
        ui.menu([
            ("1", "Усилить патрули выбранного рубежа", "35 золота", "👁"),
            ("2", "Возвести пограничные укрепления", "70 золота", "🧱"),
            ("3", "Атаковать обнаруженный лагерь", "ручной бой доступными силами", "⚔"),
            ("Q", "Назад", "", "↩"),
        ])
        ch = ui.choice("  Решение: ", ["1", "2", "3", "Q"])
        if ch == "Q":
            return
        if ch == "3":
            camps = [c for c in world["camps"] if _i(c.get("strength"), 0) > 0]
            if not camps:
                ui.info("Нет обнаруженных лагерей для атаки.", "GRAY")
                ui.pause()
                continue
            for i, camp in enumerate(camps, 1):
                tribe = world["tribes"].get(camp["tribe_key"], {})
                print(f"  {i}. {tribe.get('name', '?')} — сила {camp['strength']}, готовность {camp['readiness']}, {FRONTIERS[camp['frontier']]['name']}")
            pick = ui.choice("  Лагерь: ", [str(i) for i in range(1, len(camps) + 1)] + ["Q"])
            if pick == "Q":
                continue
            camp = camps[int(pick) - 1]
            tribe = world["tribes"][camp["tribe_key"]]
            temp = {
                "id": _next_id(world, "ASSAULT"), "kind": "raid", "tribe_key": tribe["key"],
                "frontier": camp["frontier"], "severity": max(2, camp["stage"] + 1),
                "title": f"Штурм лагеря {tribe['name']}", "text": "Римская колонна идёт уничтожить лагерь до начала нового набега.",
                "payload": {"camp_id": camp["id"], "enemy_strength": camp["strength"] * 3 + 10},
                "resolved": False, "created_turn": _i(getattr(player, "turn", 0), 0),
                "expires_turn": _i(getattr(player, "turn", 0), 0) + 1,
            }
            won = _battle_response(player, tribe, temp, world, ctx)
            if won is True:
                camp["strength"] = 0
                tribe["warriors"] = max(0, tribe["warriors"] - random.randint(500, 1400))
                tribe["fear"] = _clamp(tribe["fear"] + 14)
                tribe["pressure"] = max(0, tribe["pressure"] - 20)
                player.glory = _i(getattr(player, "glory", 0), 0) + 10
                _chronicle(world, player, f"Рим уничтожил лагерь племени {tribe['name']}.", "good")
                ui.info("Лагерь уничтожен.", "GREEN")
            elif won is False:
                camp["readiness"] = _clamp(camp["readiness"] + 18)
                tribe["prestige"] += 8
                ui.info("Штурм отбит; лагерь воодушевлён победой.", "RED")
            ui.pause()
            continue
        keys = list(FRONTIERS)
        for i, key in enumerate(keys, 1):
            f = world["frontiers"][key]
            print(f"  {i}. {f['name']} — давление {f['pressure']}, разведка {f['intel']}, укрепления {f['fortification']}")
        pick = ui.choice("  Рубеж: ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
        if pick == "Q":
            continue
        frontier = world["frontiers"][keys[int(pick) - 1]]
        cost = 35 if ch == "1" else 70
        if _i(getattr(player, "gold", 0), 0) < cost:
            ui.info("Недостаточно золота.", "RED")
        else:
            player.gold -= cost
            if ch == "1":
                frontier["patrols"] = _clamp(frontier["patrols"] + 25)
                frontier["intel"] = _clamp(frontier["intel"] + 15)
            else:
                frontier["fortification"] = _clamp(frontier["fortification"] + 22)
                frontier["pressure"] = max(0, frontier["pressure"] - 8)
            ui.info("Приказ исполнен.", "GREEN")
        ui.pause()


def federates_menu(player: Any, ctx: dict | None = None) -> None:
    world = ensure_state(player, ctx)
    ui = UI(ctx)
    ui.screen()
    ui.header("FOEDERATI", "🛡", "переселенцы на римской земле в обмен на военную службу")
    if not world["federates"]:
        ui.info("Федератов пока нет.", "GRAY")
    else:
        rows = []
        for fed in world["federates"]:
            tribe = world["tribes"].get(fed["tribe_key"], {})
            rows.append((tribe.get("name", "?"), str(fed["people"]), str(fed["warriors"]), str(fed["loyalty"]), f"{fed['pay']} зол. + {fed['grain']} зерна", FRONTIERS[fed["frontier"]]["name"]))
        ui.table("Договорные народы", ["Народ", "Люди", "Воины", "Лоял.", "Содержание", "Рубеж"], rows, "GREEN")
        ui.info("При невыплате содержания лояльность падает; бывшие федераты могут восстать.", "GOLD")
    ui.pause()


def chronicle_menu(player: Any, ctx: dict | None = None) -> None:
    world = ensure_state(player, ctx)
    ui = UI(ctx)
    ui.screen()
    ui.header("ЛЕТОПИСЬ ВАРВАРСКОГО МИРА", "📜", "войны племён, смерти вождей, миграции и союзы")
    if not world["chronicle"]:
        ui.info("Летопись пока пуста.", "GRAY")
    for entry in world["chronicle"][-30:]:
        color = "RED" if entry.get("tone") == "danger" else "GOLD" if entry.get("tone") == "warning" else "WHITE"
        ui.wrap(f"Ход {entry.get('turn')} ({entry.get('year')} AUC): {entry.get('text')}", color)
    ui.pause()


def settings_menu(player: Any, ctx: dict | None = None) -> None:
    world = ensure_state(player, ctx)
    ui = UI(ctx)
    while True:
        ui.screen()
        ui.header("НАСТРОЙКИ BARBARICUM", "⚙")
        auto = "включены" if world["settings"].get("auto_crisis", True) else "выключены"
        mode_names = {"important": "только важные", "every_turn": "каждый ход", "silent": "без экранов"}
        mode = str(world["settings"].get("briefing_mode", "important"))
        intensity = _f(world["settings"].get("simulation_intensity"), 1.25)
        ui.info(f"Автоматические срочные кризисы: {auto}", "CYAN")
        ui.info(f"Совет легатов: {mode_names.get(mode, mode)} | интенсивность мира: ×{intensity:.2f}", "GOLD")
        ui.menu([
            ("1", "Переключить автоматические кризисы", "", "🔥"),
            ("2", "Режим Совета легатов", "важные / каждый ход / без экранов", "📜"),
            ("3", "Интенсивность симуляции", "×0.80 / ×1.00 / ×1.25 / ×1.50", "🐺"),
            ("4", "Показать Совет сейчас", "проверка подключения и текущих угроз", "👁"),
            ("Q", "Назад", "", "↩"),
        ])
        ch = ui.choice("  Решение: ", ["1", "2", "3", "4", "Q"])
        if ch == "Q":
            return
        if ch == "1":
            world["settings"]["auto_crisis"] = not world["settings"].get("auto_crisis", True)
        elif ch == "2":
            order = ["important", "every_turn", "silent"]
            current = order.index(mode) if mode in order else 0
            world["settings"]["briefing_mode"] = order[(current + 1) % len(order)]
        elif ch == "3":
            levels = [0.80, 1.00, 1.25, 1.50]
            current = min(range(len(levels)), key=lambda i: abs(levels[i] - intensity))
            world["settings"]["simulation_intensity"] = levels[(current + 1) % len(levels)]
        elif ch == "4":
            world["last_briefing_turn"] = 0
            show_turn_briefing(player, ctx, force=True)


def open_menu(player: Any, ctx: dict | None = None) -> None:
    world = ensure_state(player, ctx)
    ui = UI(ctx)
    while True:
        unresolved = len([x for x in world["incidents"] if not x.get("resolved")])
        max_pressure = max((f["pressure"] for f in world["frontiers"].values()), default=0)
        ui.screen()
        ui.header("BARBARICUM", "🐺", "живой мир народов за римским лимесом")
        ui.info(f"Модуль {MODULE_VERSION} подключён • открытые кризисы: {unresolved} • максимальное давление: {max_pressure}/100", "GOLD")
        ui.info(f"Индекс Великого переселения: {world['great_migration_level']}/100 • тихих ходов подряд: {world.get('quiet_turns', 0)}", "PURPLE")
        ui.menu([
            ("1", "Карта варварского мира", "давление, разведка, лагеря и миграции", "🗺"),
            ("2", "Племена и вожди", "отношения, разведка, пакты, наём", "🪓"),
            ("3", "Пограничные события", f"нерешённых: {unresolved}", "🔥"),
            ("4", "Лагеря и переселения", "рост угрозы и оборона рубежей", "⛺"),
            ("5", "Федераты", "служба, содержание и лояльность", "🛡"),
            ("6", "Летопись", "мир действует и без Рима", "📜"),
            ("7", "Настройки", "автоматические кризисы", "⚙"),
            ("Q", "Назад", "", "↩"),
        ], "Consilium de Barbaris")
        ch = ui.choice("  Приказ: ", ["1", "2", "3", "4", "5", "6", "7", "Q"])
        if ch == "Q":
            _sync_legacy(player, world, import_changes=False)
            return
        if ch == "1":
            show_world_overview(player, ctx)
        elif ch == "2":
            tribes_menu(player, ctx)
        elif ch == "3":
            incidents_menu(player, ctx)
        elif ch == "4":
            camps_menu(player, ctx)
        elif ch == "5":
            federates_menu(player, ctx)
        elif ch == "6":
            chronicle_menu(player, ctx)
        elif ch == "7":
            settings_menu(player, ctx)



def install(namespace: dict[str, Any]) -> bool:
    """Подключает Barbaricum к уже загруженному основному файлу.

    Основная игра вызывает только ``roma_barbarians.install(globals())``.
    Все обёртки живут здесь, поэтому roma_aeterna.py не знает внутренностей
    системы и остаётся пригодным для дальнейшего обновления.
    """
    if not isinstance(namespace, dict):
        raise TypeError("Barbaricum.install ожидает globals() основного модуля")
    if namespace.get("_BARBARICUM_INSTALLED"):
        return True

    required = ["ensure_all_states", "barbarian_menu", "end_turn"]
    missing = [name for name in required if not callable(namespace.get(name))]
    if missing:
        raise RuntimeError("Barbaricum: отсутствуют точки интеграции: " + ", ".join(missing))

    old_ensure = namespace["ensure_all_states"]
    old_menu = namespace["barbarian_menu"]
    old_end_turn = namespace["end_turn"]
    old_ai_tick = namespace.get("barbarian_ai_tick")
    old_gift = namespace.get("maybe_barbarian_gifts")
    old_alert_add = namespace.get("barbarian_alert_add")
    old_alert_process = namespace.get("_process_barbarian_alerts")

    def debug(message: str, *args, level_name: str = "WARNING", exc_info: bool = False) -> None:
        fn = namespace.get("debug_log")
        logging_mod = namespace.get("logging")
        if callable(fn):
            level = getattr(logging_mod, level_name, 30) if logging_mod is not None else 30
            try:
                fn(message, *args, exc_info=exc_info, level=level)
            except Exception:
                pass

    def integrated_ensure(player):
        player = old_ensure(player)
        if player is not None:
            try:
                ensure_state(player, namespace)
            except Exception as exc:
                debug("BARBARICUM state migration failed: %s", exc, exc_info=True)
        return player

    def integrated_menu(player):
        try:
            return open_menu(player, namespace)
        except Exception as exc:
            debug("BARBARICUM menu failed: %s", exc, level_name="ERROR", exc_info=True)
            clr = namespace.get("clr")
            C = namespace.get("C")
            if callable(clr) and C is not None:
                print(clr(f"  Barbaricum недоступен: {type(exc).__name__}: {exc}", getattr(C, "RED", "")))
                pause_fn = namespace.get("pause")
                if callable(pause_fn):
                    pause_fn()
            return old_menu(player)

    def integrated_ai_tick(player):
        return legacy_tick_hook(player, namespace)

    def integrated_gift_tick(player):
        return legacy_gift_hook(player, namespace)

    def integrated_alert_add(player, text: str, *, severity: int = 1, source: str = "summary"):
        # Эвристический сборщик старой системы реагировал на любое слово
        # «враг». Типизированные события Barbaricum не нуждаются в нём.
        return None

    def integrated_alert_process(player, alerts):
        return None

    def integrated_end_turn(player):
        # Сначала основной файл полностью завершает экономику, гражданскую
        # войну, сводку и международный совет. Лишь затем открывается отдельный
        # Совет пограничных легатов — экраны больше не вклиниваются друг в друга.
        result = old_end_turn(player)
        try:
            process_turn(player, namespace, interactive=False)
            show_turn_briefing(player, namespace)
            save_fn = namespace.get("save_game")
            if callable(save_fn):
                save_fn(player)
        except Exception as exc:
            debug("BARBARICUM turn processing failed: %s", exc, level_name="ERROR", exc_info=True)
            clr = namespace.get("clr")
            C = namespace.get("C")
            if callable(clr) and C is not None:
                print(clr(f"\n  ⚠ Barbaricum: ошибка тика ({type(exc).__name__}: {exc}).", getattr(C, "RED", "")))
                print(clr("  Партия продолжена; подробности записаны в roma_debug.log.", getattr(C, "GOLD", "")))
        return result

    namespace["_BARBARICUM_LEGACY_ENSURE"] = old_ensure
    namespace["_BARBARICUM_LEGACY_MENU"] = old_menu
    namespace["_BARBARICUM_LEGACY_END_TURN"] = old_end_turn
    namespace["_BARBARICUM_LEGACY_AI_TICK"] = old_ai_tick
    namespace["_BARBARICUM_LEGACY_GIFT_TICK"] = old_gift
    namespace["_BARBARICUM_LEGACY_ALERT_ADD"] = old_alert_add
    namespace["_BARBARICUM_LEGACY_ALERT_PROCESS"] = old_alert_process

    namespace["ensure_all_states"] = integrated_ensure
    namespace["barbarian_menu"] = integrated_menu
    namespace["end_turn"] = integrated_end_turn
    if callable(old_ai_tick):
        namespace["barbarian_ai_tick"] = integrated_ai_tick
    if callable(old_gift):
        namespace["maybe_barbarian_gifts"] = integrated_gift_tick
    if callable(old_alert_add):
        namespace["barbarian_alert_add"] = integrated_alert_add
    if callable(old_alert_process):
        namespace["_process_barbarian_alerts"] = integrated_alert_process

    namespace["_BARBARICUM_INSTALLED"] = True
    namespace["BARBARICUM_VERSION"] = MODULE_VERSION
    return True


def self_test() -> tuple[bool, list[str]]:
    class Dummy:
        def __init__(self):
            self.turn = 1
            self.year = 700
            self.gold = 500
            self.grain = 500
            self.glory = 0
            self.morale = 70
            self.provinces = [{"name": "Gallia", "unrest": 0}, {"name": "Dacia", "unrest": 0}]
            self.legions = []
            self.aux_units = []
            self.barbarian_tribes = {}

    errors = []
    p = Dummy()
    w = ensure_state(p)
    if len(w.get("tribes", {})) != len(TRIBE_TEMPLATES):
        errors.append("не созданы все племена")
    if len(w.get("frontiers", {})) != len(FRONTIERS):
        errors.append("не созданы все фронтиры")
    random.seed(7)
    process_turn(p, interactive=False)
    if w.get("turn_processed") != 1:
        errors.append("ход не обработан")
    if not isinstance(getattr(p, "barbarian_tribes", None), dict):
        errors.append("не создан слой совместимости")
    p.turn = 2
    process_turn(p, interactive=False)
    return not errors, errors


if __name__ == "__main__":
    ok, errors = self_test()
    print("BARBARICUM SELF-TEST:", "OK" if ok else "FAIL")
    for error in errors:
        print(" -", error)
    raise SystemExit(0 if ok else 1)
