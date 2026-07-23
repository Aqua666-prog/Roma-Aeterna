#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna — ORBIS POLITICUS.

Стратегический ИИ иностранных держав и координация внутриполитических фракций.
Модуль расширяет существующий Consilium Externum, не заменяя его договоры,
миссии и кризисы. Каждая держава получает собственную экономику, военную
готовность, характер, долгосрочную цель, планы, память и отношения с другими
державами.

Публичный контракт:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None)
    open_menu(player, ctx=None)
    strategic_assessment(player, ctx=None)
"""
from __future__ import annotations

import copy
import math
import random
import re
import textwrap
from typing import Any

MODULE_VERSION = "1.0.0-orbis-politicus"
SCHEMA_VERSION = 1
MAX_HISTORY = 240


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

    def header(self, title: str, icon: str = "🌍", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try:
                fn(title, icon, getattr(self.C, "CYAN", ""), subtitle); return
            except TypeError:
                try: fn(title, icon, getattr(self.C, "CYAN", ""))
                except Exception: pass
        print(self.color(f"\n{'═' * 74}\n  {icon} {title}\n{'═' * 74}", "CYAN", True))
        if subtitle: self.wrap(subtitle, "GRAY")

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
        clean_rows = []
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
            try: return str(fn(self.color(prompt, "CYAN"), valid)).upper()
            except Exception: pass
        while True:
            answer = input(prompt).strip().upper()
            if answer in valid: return answer
            print("  Допустимо: " + ", ".join(valid))

    def pause(self) -> None:
        fn = self.ctx.get("rui_pause") or self.ctx.get("pause")
        if callable(fn):
            try: fn(); return
            except Exception: pass
        input("\n  Нажмите Enter, чтобы продолжить...")


POWER_ARCHETYPES: dict[str, dict[str, Any]] = {
    "carthage": {
        "personality": "меркантильная морская олигархия", "doctrine": "талассократия",
        "aggression": 62, "opportunism": 82, "honor": 44, "risk": 58, "trade_drive": 92,
        "expansionism": 74, "naval": 92, "administration": 72, "preferred": ["trade_supremacy", "contain_rome", "prepare_war"],
        "province": "Sicilia", "enemy_reason": "punic_war",
    },
    "numidia": {
        "personality": "подвижная царская клиентела", "doctrine": "конная дипломатия",
        "aggression": 48, "opportunism": 76, "honor": 52, "risk": 60, "trade_drive": 54,
        "expansionism": 58, "naval": 20, "administration": 42, "preferred": ["seek_patron", "balance_neighbors", "raid_border"],
        "province": "Numidia", "enemy_reason": "numidian_intervention",
    },
    "pergamon": {
        "personality": "эллинистическая бюрократическая монархия", "doctrine": "культурное влияние",
        "aggression": 28, "opportunism": 48, "honor": 72, "risk": 35, "trade_drive": 78,
        "expansionism": 42, "naval": 45, "administration": 84, "preferred": ["ally_rome", "trade_supremacy", "cultural_influence"],
        "province": "Asia Minor", "enemy_reason": "hellenistic_war",
    },
    "parthia": {
        "personality": "аристократическая конная держава", "doctrine": "стратегическая глубина",
        "aggression": 72, "opportunism": 66, "honor": 64, "risk": 54, "trade_drive": 42,
        "expansionism": 82, "naval": 12, "administration": 56, "preferred": ["contain_rome", "prepare_war", "expand_region"],
        "province": "Syria", "enemy_reason": "parthian_war",
    },
    "egypt": {
        "personality": "богатая дворцовая монархия", "doctrine": "зерно и золото",
        "aggression": 36, "opportunism": 68, "honor": 48, "risk": 40, "trade_drive": 94,
        "expansionism": 46, "naval": 68, "administration": 88, "preferred": ["trade_supremacy", "balance_neighbors", "influence_rome"],
        "province": "Aegyptus", "enemy_reason": "egyptian_intervention",
    },
    "gauls": {
        "personality": "неустойчивая конфедерация вождей", "doctrine": "набеги и военная слава",
        "aggression": 82, "opportunism": 72, "honor": 50, "risk": 78, "trade_drive": 28,
        "expansionism": 65, "naval": 10, "administration": 28, "preferred": ["raid_border", "prepare_war", "unite_tribes"],
        "province": "Gallia", "enemy_reason": "gallic_war",
    },
}

PAIR_BIASES = {
    frozenset(("carthage", "numidia")): -18,
    frozenset(("carthage", "egypt")): 8,
    frozenset(("carthage", "pergamon")): 4,
    frozenset(("parthia", "pergamon")): -28,
    frozenset(("parthia", "egypt")): -18,
    frozenset(("egypt", "pergamon")): 14,
    frozenset(("gauls", "carthage")): 2,
    frozenset(("gauls", "numidia")): 0,
}

GOAL_LABELS = {
    "trade_supremacy": "торговое первенство", "contain_rome": "сдерживание Рима",
    "prepare_war": "подготовка войны", "ally_rome": "союз с Римом", "seek_patron": "поиск покровителя",
    "balance_neighbors": "равновесие соседей", "raid_border": "пограничное давление",
    "cultural_influence": "культурное влияние", "expand_region": "региональная экспансия",
    "influence_rome": "влияние на римскую политику", "unite_tribes": "объединение племён",
    "recover": "восстановление сил", "break_rome": "подрыв Рима",
}

PLAN_LABELS = {
    "commercial_offensive": "коммерческое наступление", "embassy": "дипломатическое сближение",
    "coalition": "формирование коалиции", "mobilization": "военная мобилизация",
    "ultimatum": "подготовка ультиматума", "espionage": "развёртывание агентуры",
    "border_raid": "подготовка пограничного рейда", "internal_reform": "внутреннее восстановление",
    "client_negotiation": "переговоры о покровительстве", "cultural_mission": "культурная миссия",
}


def _base_diplomacy(player: Any, ctx: dict) -> dict:
    fn = ctx.get("ensure_external_policy_state")
    if callable(fn):
        try: return fn(player)
        except Exception: pass
    diplomacy = getattr(player, "diplomacy", None)
    if not isinstance(diplomacy, dict):
        diplomacy = {}
        player.diplomacy = diplomacy
    return diplomacy


def _stable_jitter(key: str, salt: str, span: int) -> int:
    """Детерминированное стартовое различие без расходования общего RNG игры."""
    if span <= 0:
        return 0
    seed = sum((index + 1) * ord(ch) for index, ch in enumerate(f"{key}:{salt}"))
    return seed % (span * 2 + 1) - span


def _default_power_state(key: str, row: dict) -> dict:
    arch = POWER_ARCHETYPES.get(key, {})
    strength = _i(row.get("strength", 5), 5, 1, 20)
    wealth = _clamp(row.get("wealth", 50), 0, 100, 50)
    return {
        "key": key, "name": str(row.get("name", key)),
        "personality": arch.get("personality", "прагматичная держава"),
        "doctrine": arch.get("doctrine", "равновесие"),
        "treasury": max(40, wealth * 4 + _stable_jitter(key, "treasury", 35)),
        "manpower": _clamp(35 + strength * 6 + _stable_jitter(key, "manpower", 8), 10, 100, 55),
        "stability": _clamp(55 + arch.get("administration", 50) // 5 + _stable_jitter(key, "stability", 8), 20, 95, 60),
        "war_weariness": 0,
        "readiness": _clamp(35 + strength * 5 + arch.get("aggression", 50) // 7, 15, 95, 55),
        "economic_power": wealth,
        "naval_power": _clamp(arch.get("naval", 25), 0, 100, 25),
        "diplomatic_weight": _clamp(35 + wealth // 3 + arch.get("administration", 50) // 4, 10, 100, 55),
        "aggression": _clamp(arch.get("aggression", 50), 0, 100, 50),
        "opportunism": _clamp(arch.get("opportunism", 50), 0, 100, 50),
        "honor": _clamp(arch.get("honor", 50), 0, 100, 50),
        "risk": _clamp(arch.get("risk", 50), 0, 100, 50),
        "trade_drive": _clamp(arch.get("trade_drive", 50), 0, 100, 50),
        "expansionism": _clamp(arch.get("expansionism", 50), 0, 100, 50),
        "goal": None, "goal_selected_turn": 0, "goal_score": 0,
        "plan": None, "plan_progress": 0, "plan_required": 0, "plan_target": None,
        "last_action_turn": 0, "last_war_spawn_turn": 0, "cooldown": max(0, _stable_jitter(key, "cooldown", 2)),
        "threat_from_rome": 20, "opportunity_against_rome": 20,
        "known_rome_power": 0, "intel_confidence": _clamp(row.get("intel", 20), 0, 100, 20),
        "grievances": [], "favors": 0, "promises": [], "history": [],
    }


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    diplomacy = _base_diplomacy(player, ctx)
    state = getattr(player, "diplomatic_ai", None)
    if not isinstance(state, dict):
        state = {}
        player.diplomatic_ai = state
    state.setdefault("schema", SCHEMA_VERSION)
    state.setdefault("version", MODULE_VERSION)
    state.setdefault("powers", {})
    state.setdefault("relations", {})
    state.setdefault("coalitions", [])
    state.setdefault("history", [])
    state.setdefault("last_tick_turn", 0)
    state.setdefault("last_global_action_turn", 0)
    state.setdefault("domestic_relations", {})
    state.setdefault("domestic_last_action_turn", 0)

    powers = _dict(state.get("powers"))
    for key, row in diplomacy.items():
        if not isinstance(row, dict):
            continue
        pstate = powers.get(key) if isinstance(powers.get(key), dict) else _default_power_state(str(key), row)
        defaults = _default_power_state(str(key), row)
        for field, default in defaults.items():
            pstate.setdefault(field, copy.deepcopy(default))
        pstate["key"] = str(key)
        pstate["name"] = str(row.get("name", pstate.get("name", key)))
        for metric in ("manpower", "stability", "war_weariness", "readiness", "economic_power", "naval_power", "diplomatic_weight", "aggression", "opportunism", "honor", "risk", "trade_drive", "expansionism", "threat_from_rome", "opportunity_against_rome", "intel_confidence"):
            pstate[metric] = _clamp(pstate.get(metric, defaults.get(metric, 50)), 0, 100, defaults.get(metric, 50))
        pstate["treasury"] = _i(pstate.get("treasury", defaults["treasury"]), defaults["treasury"], 0, 100000)
        pstate["goal_selected_turn"] = _i(pstate.get("goal_selected_turn", 0), 0, 0)
        pstate["goal_score"] = _i(pstate.get("goal_score", 0), 0, -9999, 9999)
        pstate["plan_progress"] = _i(pstate.get("plan_progress", 0), 0, 0, 999)
        pstate["plan_required"] = _i(pstate.get("plan_required", 0), 0, 0, 999)
        pstate["last_action_turn"] = _i(pstate.get("last_action_turn", 0), 0, 0)
        pstate["last_war_spawn_turn"] = _i(pstate.get("last_war_spawn_turn", 0), 0, 0)
        pstate["cooldown"] = _i(pstate.get("cooldown", 0), 0, 0, 10)
        pstate["history"] = [x for x in _list(pstate.get("history")) if isinstance(x, dict)][-40:]
        pstate["grievances"] = [str(x) for x in _list(pstate.get("grievances"))][-12:]
        pstate["promises"] = [x for x in _list(pstate.get("promises")) if isinstance(x, dict)][-12:]
        powers[str(key)] = pstate
    state["powers"] = powers

    keys = sorted(powers)
    relations = _dict(state.get("relations"))
    for a in keys:
        relations.setdefault(a, {})
        for b in keys:
            if a == b:
                relations[a][b] = 100
                continue
            if b not in relations[a]:
                bias = PAIR_BIASES.get(frozenset((a, b)), 0)
                relations[a][b] = _clamp(48 + bias + _stable_jitter(f"{a}:{b}", "relation", 6), 0, 100, 48)
            else:
                relations[a][b] = _clamp(relations[a][b], 0, 100, 50)
    state["relations"] = relations

    factions = [f for f in _list(getattr(player, "ai_factions", [])) if getattr(f, "name", None)]
    domestic = _dict(state.get("domestic_relations"))
    for a in factions:
        domestic.setdefault(str(a.name), {})
        for b in factions:
            if a is b:
                domestic[str(a.name)][str(b.name)] = 100
            else:
                domestic[str(a.name)].setdefault(str(b.name), _clamp(42 + _stable_jitter(f"{a.name}:{b.name}", "domestic", 16), 0, 100, 42))
                domestic[str(a.name)][str(b.name)] = _clamp(domestic[str(a.name)][str(b.name)], 0, 100, 45)
    state["domestic_relations"] = domestic
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state["coalitions"] = [x for x in _list(state.get("coalitions")) if isinstance(x, dict)][-12:]
    state["last_tick_turn"] = _i(state.get("last_tick_turn", 0), 0, 0)
    state["last_global_action_turn"] = _i(state.get("last_global_action_turn", 0), 0, 0)
    state["domestic_last_action_turn"] = _i(state.get("domestic_last_action_turn", 0), 0, 0)
    state["schema"] = SCHEMA_VERSION
    state["version"] = MODULE_VERSION
    player.diplomatic_ai = state
    return state


def _rome_metrics(player: Any, ctx: dict) -> dict[str, float]:
    provinces = [p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)]
    legions = [l for l in _list(getattr(player, "legions", []))]
    city_metrics = {}
    city_module = ctx.get("CITY_EVENTS")
    if city_module is not None and hasattr(city_module, "empire_metrics"):
        try: city_metrics = city_module.empire_metrics(player, ctx)
        except Exception: city_metrics = {}
    military = sum(_i(getattr(l, "strength", 0), 0) + _i(getattr(l, "quality", 0), 0) * 4 for l in legions)
    provincial_unrest = sum(_i(p.get("unrest", 0), 0) for p in provinces) / max(1, len(provinces))
    power = (
        len(provinces) * 6 + len(legions) * 12 + military / 12 + _i(getattr(player, "gold", 0), 0) / 30
        + _i(getattr(player, "glory", 0), 0) / 18 + _f(city_metrics.get("prosperity", 0), 0) / 4
    )
    weakness = (
        _i(getattr(player, "unrest", 0), 0) * 0.35 + max(0, 50 - _i(getattr(player, "senate_rep", 50), 50)) * 0.25
        + max(0, 50 - _i(getattr(player, "people_rep", 50), 50)) * 0.20 + provincial_unrest * 5
        + (22 if not legions else 0) + max(0, 100 - _i(getattr(player, "gold", 0), 0)) / 8
        + _f(city_metrics.get("crisis_cities", 0), 0) * 4
    )
    return {
        "power": max(0.0, power), "weakness": max(0.0, weakness), "provinces": len(provinces),
        "legions": len(legions), "military": military, "provincial_unrest": provincial_unrest,
        "city_prosperity": _f(city_metrics.get("prosperity", 50), 50),
    }


def _record(player: Any, ctx: dict, power_key: str | None, title: str, text: str, tone: str = "info", severity: int = 2) -> None:
    state = ensure_state(player, ctx)
    record = {
        "turn": _i(getattr(player, "turn", 1), 1, 1), "year": _i(getattr(player, "year", 0), 0),
        "power": power_key, "title": str(title), "text": str(text), "tone": tone,
    }
    state["history"].append(record)
    state["history"] = state["history"][-MAX_HISTORY:]
    if power_key in state["powers"]:
        state["powers"][power_key]["history"].append(record)
        state["powers"][power_key]["history"] = state["powers"][power_key]["history"][-40:]
    dispatch = ctx.get("_foreign_dispatch")
    if callable(dispatch):
        try: dispatch(player, title, text, power_key, tone)
        except Exception: pass
    summary = ctx.get("turn_summary_add")
    if callable(summary):
        try: summary(player, f"{title}: {text}")
        except Exception: pass
    log_event = ctx.get("log_event")
    if callable(log_event):
        try: log_event(player, f"{title}: {text}")
        except Exception: pass
    annales = ctx.get("ANNALES")
    if annales is not None and hasattr(annales, "record_event"):
        try:
            annales.record_event(player, category="diplomacy", title=title, text=text,
                                 reason="Самостоятельное решение иностранной державы.", severity=severity,
                                 data={"power": power_key, "system": "orbis_politicus"})
        except Exception: pass


def _add_crisis(player: Any, ctx: dict, key: str, kind: str, title: str, text: str, expires: int = 4) -> bool:
    diplomacy = _base_diplomacy(player, ctx)
    fp = getattr(player, "foreign_policy", None)
    if not isinstance(fp, dict) or key not in diplomacy:
        return False
    crises = fp.setdefault("crises", [])
    if any(isinstance(c, dict) and c.get("target") == key for c in crises):
        return False
    turn = _i(getattr(player, "turn", 1), 1)
    crises.append({
        "kind": kind, "title": title, "text": text, "target": key,
        "created_turn": turn, "expires_turn": turn + max(2, expires), "source": "orbis_politicus",
    })
    fp["crises"] = crises[-8:]
    return True


def _goal_utilities(key: str, pstate: dict, row: dict, rome: dict, state: dict) -> dict[str, float]:
    arch = POWER_ARCHETYPES.get(key, {})
    relation = _clamp(row.get("disposition", 50), 0, 100, 50)
    trust = _clamp(row.get("trust", 40), 0, 100, 40)
    tension = _clamp(row.get("tension", 30), 0, 100, 30)
    fear = _clamp(row.get("fear", 10), 0, 100, 10)
    threat = pstate.get("threat_from_rome", 20)
    opportunity = pstate.get("opportunity_against_rome", 20)
    at_war = bool(row.get("at_war", False))
    utilities = {
        "trade_supremacy": pstate["trade_drive"] + row.get("trade_interest", 50) + pstate["economic_power"] * 0.4 - tension * 0.7 + (22 if row.get("trade_pact") else 0),
        "contain_rome": threat * 1.3 + pstate["expansionism"] * 0.35 + tension * 0.5 - relation * 0.35,
        "prepare_war": pstate["aggression"] + opportunity * 1.1 + tension * 0.8 + pstate["readiness"] * 0.45 - pstate["war_weariness"] - fear * 0.25,
        "ally_rome": relation + trust * 0.8 + threat * 0.25 + pstate["honor"] * 0.25 - tension,
        "seek_patron": max(0, 65 - pstate["stability"]) + max(0, 60 - pstate["readiness"]) + relation * 0.65 + fear * 0.4,
        "balance_neighbors": pstate["diplomatic_weight"] + pstate["honor"] * 0.4 + threat * 0.35,
        "raid_border": pstate["opportunism"] + opportunity + pstate["aggression"] * 0.45 - relation * 0.35 - fear * 0.2,
        "cultural_influence": pstate["diplomatic_weight"] + pstate["economic_power"] * 0.35 + relation * 0.35,
        "expand_region": pstate["expansionism"] + pstate["readiness"] * 0.5 + opportunity * 0.45,
        "influence_rome": pstate["opportunism"] + pstate["economic_power"] * 0.5 + max(0, 60 - trust) * 0.3,
        "unite_tribes": pstate["aggression"] * 0.7 + pstate["diplomatic_weight"] * 0.45 + threat * 0.45,
        "recover": max(0, 70 - pstate["stability"]) * 1.4 + max(0, 65 - pstate["manpower"]) + pstate["war_weariness"] * 1.2,
        "break_rome": opportunity * 1.3 + tension * 0.65 + pstate["opportunism"] * 0.45,
    }
    for preferred in arch.get("preferred", []):
        utilities[preferred] = utilities.get(preferred, 0) + 18
    if at_war:
        utilities["prepare_war"] += 35
        utilities["recover"] += pstate["war_weariness"]
        utilities["trade_supremacy"] -= 25
        utilities["ally_rome"] = -100
    if row.get("alliance"):
        utilities["ally_rome"] += 35
        utilities["prepare_war"] -= 80
        utilities["break_rome"] -= 60
    if row.get("client"):
        utilities["seek_patron"] += 40
        utilities["prepare_war"] -= 50
    if pstate["treasury"] < 50:
        utilities["recover"] += 30
        utilities["prepare_war"] -= 20
    return utilities


def _choose_goal(key: str, pstate: dict, row: dict, rome: dict, state: dict, turn: int) -> str:
    if pstate.get("goal") and turn - _i(pstate.get("goal_selected_turn", 0), 0) < 4:
        return str(pstate["goal"])
    utilities = _goal_utilities(key, pstate, row, rome, state)
    # Небольшой шум предотвращает одинаковые детерминированные партии.
    scored = {goal: score + random.uniform(-7, 7) for goal, score in utilities.items()}
    goal = max(scored, key=scored.get)
    pstate["goal"] = goal
    pstate["goal_score"] = int(round(scored[goal]))
    pstate["goal_selected_turn"] = turn
    return goal


def _plan_for_goal(goal: str, pstate: dict) -> tuple[str, int]:
    mapping = {
        "trade_supremacy": ("commercial_offensive", 55), "ally_rome": ("embassy", 48),
        "contain_rome": ("coalition", 68), "prepare_war": ("mobilization", 80),
        "seek_patron": ("client_negotiation", 50), "balance_neighbors": ("coalition", 58),
        "raid_border": ("border_raid", 50), "cultural_influence": ("cultural_mission", 52),
        "expand_region": ("mobilization", 72), "influence_rome": ("espionage", 58),
        "unite_tribes": ("coalition", 62), "recover": ("internal_reform", 48),
        "break_rome": ("espionage", 64),
    }
    plan, required = mapping.get(goal, ("embassy", 50))
    required += max(0, 55 - pstate.get("administration", POWER_ARCHETYPES.get(pstate.get("key"), {}).get("administration", 50))) // 3
    return plan, required


def _select_partner(key: str, state: dict, prefer_hostile_to_rome: bool = False, diplomacy: dict | None = None) -> str | None:
    candidates = [other for other in state["powers"] if other != key]
    if not candidates:
        return None
    def score(other: str) -> float:
        base = state["relations"].get(key, {}).get(other, 50)
        if prefer_hostile_to_rome and diplomacy:
            base += _i(diplomacy.get(other, {}).get("tension", 30), 30) * 0.5
            base += _i(diplomacy.get(other, {}).get("hostility", 50), 50) * 0.25
        return base + random.uniform(-8, 8)
    return max(candidates, key=score)


def _spawn_war_force(player: Any, ctx: dict, key: str, pstate: dict) -> None:
    turn = _i(getattr(player, "turn", 1), 1)
    if turn - _i(pstate.get("last_war_spawn_turn", 0), 0) < 4:
        return
    # Bella Regnorum является главным слоем межгосударственной войны. Если он
    # доступен, стратегический ИИ не создаёт параллельную безымянную армию в
    # старом пуле, а открывает полноценный фронт с национальным ростером.
    warfare = ctx.get("WARFARE_AI")
    if warfare is not None and hasattr(warfare, "declare_war"):
        try:
            war = warfare.declare_war(player, key, ctx, reason="orbis_politicus")
            if war is not None:
                pstate["last_war_spawn_turn"] = turn
                return
        except Exception:
            pass
    cap_fn = ctx.get("_enemy_armies_cap")
    try:
        cap = _i(cap_fn(player), 7, 1, 90) if callable(cap_fn) else 7
    except Exception:
        cap = 7
    if len(_list(getattr(player, "enemy_armies", []))) >= cap:
        return
    fn = ctx.get("spawn_enemy_army")
    if not callable(fn):
        return
    arch = POWER_ARCHETYPES.get(key, {})
    try:
        army = fn(player, province_name=arch.get("province"), reason=arch.get("enemy_reason", "foreign_war"))
    except TypeError:
        try: army = fn(player, arch.get("province"), arch.get("enemy_reason", "foreign_war"))
        except Exception: army = None
    except Exception:
        army = None
    if army is not None:
        try:
            army["owner"] = key
            army["name"] = f"{pstate.get('name', key)}: {army.get('name', 'экспедиционная армия')}"
            army["strength"] = min(150, _i(army.get("strength", 30), 30) + max(0, pstate.get("readiness", 50) - 50) // 5)
        except Exception:
            pass
        pstate["last_war_spawn_turn"] = turn


def _complete_plan(player: Any, ctx: dict, key: str, pstate: dict, row: dict, state: dict) -> None:
    plan = str(pstate.get("plan") or "")
    name = pstate.get("name", key)
    turn = _i(getattr(player, "turn", 1), 1)
    if plan == "commercial_offensive":
        row["trade_interest"] = _clamp(row.get("trade_interest", 50) + 8, 0, 100, 50)
        pstate["economic_power"] = _clamp(pstate["economic_power"] + 5, 0, 100, 50)
        pstate["treasury"] += 35
        if not row.get("trade_pact"):
            _add_crisis(player, ctx, key, "trade", "Инициатива об открытии рынков", f"{name} предлагает взаимные торговые привилегии и снижение пошлин.")
        _record(player, ctx, key, "Коммерческое наступление", f"{name} направляет купеческие делегации по всему Средиземноморью.", "good")
    elif plan == "embassy":
        row["disposition"] = _clamp(row.get("disposition", 50) + 7, 0, 100, 50)
        row["trust"] = _clamp(row.get("trust", 40) + 6, 0, 100, 40)
        row["tension"] = _clamp(row.get("tension", 30) - 6, 0, 100, 30)
        _record(player, ctx, key, "Иностранное посольство", f"{name} самостоятельно ищет сближения с Римом и предлагает продолжить переговоры.", "good")
    elif plan == "coalition":
        partner = _select_partner(key, state, True, getattr(player, "diplomacy", {}))
        if partner:
            relation = state["relations"][key].get(partner, 50)
            state["relations"][key][partner] = _clamp(relation + 12, 0, 100, 50)
            state["relations"][partner][key] = state["relations"][key][partner]
            coalition = {
                "members": sorted({key, partner}), "purpose": pstate.get("goal", "balance_neighbors"),
                "formed_turn": turn, "strength": _clamp((pstate["readiness"] + state["powers"][partner]["readiness"]) // 2, 0, 100, 50),
            }
            if not any(set(c.get("members", [])) == set(coalition["members"]) for c in state["coalitions"]):
                state["coalitions"].append(coalition)
            partner_name = state["powers"][partner]["name"]
            _record(player, ctx, key, "Переговоры чужих держав", f"{name} и {partner_name} согласуют совместную линию: {GOAL_LABELS.get(pstate.get('goal'), pstate.get('goal'))}.", "bad" if pstate.get("goal") == "contain_rome" else "info", 3)
    elif plan == "mobilization":
        pstate["readiness"] = _clamp(pstate["readiness"] + 16, 0, 100, 50)
        pstate["manpower"] = _clamp(pstate["manpower"] + 7, 0, 100, 50)
        row["strength"] = min(20, _i(row.get("strength", 5), 5) + 1)
        row["tension"] = _clamp(row.get("tension", 30) + 8, 0, 100, 30)
        should_war = (
            pstate.get("goal") in {"prepare_war", "expand_region"}
            and row.get("tension", 0) >= 68 and pstate["readiness"] >= 68
            and not row.get("alliance") and not row.get("client")
        )
        if should_war:
            row["at_war"] = True
            row["war_started_turn"] = turn
            row["alliance"] = False; row["non_aggression"] = False; row["trade_pact"] = False
            row["casus_belli"] = True; row["casus_belli_turn"] = turn
            _spawn_war_force(player, ctx, key, pstate)
            _record(player, ctx, key, "Объявление войны", f"{name} отвергает договорный порядок и начинает открытую войну против Рима.", "bad", 5)
        else:
            _record(player, ctx, key, "Иностранная мобилизация", f"{name} завершает военные сборы; готовность армии заметно выросла.", "bad", 3)
    elif plan == "ultimatum":
        row["tension"] = _clamp(row.get("tension", 30) + 10, 0, 100, 30)
        _add_crisis(player, ctx, key, "ultimatum", "Требования иностранного двора", f"{name} требует уступок, гарантий и признания собственной сферы влияния.", 3)
        _record(player, ctx, key, "Подготовлен ультиматум", f"{name} переходит от угроз к формальным требованиям.", "bad", 4)
    elif plan == "espionage":
        pstate["intel_confidence"] = _clamp(pstate["intel_confidence"] + 14, 0, 100, 30)
        row["intel"] = _clamp(row.get("intel", 20) + 8, 0, 100, 20)
        success = random.random() < (0.42 + pstate["opportunism"] / 250)
        if success:
            if pstate.get("goal") == "break_rome":
                loss = min(_i(getattr(player, "gold", 0), 0), random.randint(12, 32))
                player.gold = max(0, _i(getattr(player, "gold", 0), 0) - loss)
                player.unrest = _clamp(_i(getattr(player, "unrest", 0), 0) + 2, 0, 100, 0)
                _record(player, ctx, key, "Раскрыта иностранная агентура", f"Сеть, связанная с державой {name}, похитила {loss} золота и распространяла слухи.", "bad", 3)
            else:
                row["leverage"] = _clamp(row.get("leverage", 0) + 8, 0, 100, 0)
                _record(player, ctx, key, "Чужая агентура активизировалась", f"{name} расширяет сеть информаторов при римских рынках и дворах.", "bad", 2)
        else:
            row["trust"] = _clamp(row.get("trust", 40) - 5, 0, 100, 40)
            row["tension"] = _clamp(row.get("tension", 30) + 5, 0, 100, 30)
            _record(player, ctx, key, "Провал иностранной агентуры", f"Люди державы {name} были разоблачены до завершения операции.", "good", 2)
    elif plan == "border_raid":
        row["tension"] = _clamp(row.get("tension", 30) + 9, 0, 100, 30)
        target_provinces = [p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict) and p.get("name") != "Latium"]
        if target_provinces:
            target = max(target_provinces, key=lambda p: _i(p.get("unrest", 0), 0) + random.randint(0, 3))
            target["unrest"] = min(10, _i(target.get("unrest", 0), 0) + 1)
            loss = min(_i(getattr(player, "gold", 0), 0), random.randint(8, 22))
            player.gold = max(0, _i(getattr(player, "gold", 0), 0) - loss)
            _record(player, ctx, key, "Пограничный рейд", f"Отряды державы {name} разорили дороги провинции {target.get('name')}; казна потеряла {loss} золота.", "bad", 3)
        else:
            _add_crisis(player, ctx, key, "border", "Пограничный инцидент", f"Вооружённые люди державы {name} нарушили римскую границу.")
    elif plan == "internal_reform":
        spend = min(pstate["treasury"], random.randint(25, 55))
        pstate["treasury"] -= spend
        pstate["stability"] = _clamp(pstate["stability"] + 12, 0, 100, 50)
        pstate["economic_power"] = _clamp(pstate["economic_power"] + 5, 0, 100, 50)
        pstate["war_weariness"] = _clamp(pstate["war_weariness"] - 12, 0, 100, 0)
        _record(player, ctx, key, "Внутренние реформы", f"{name} временно отказывается от авантюр и укрепляет собственное государство.", "info")
    elif plan == "client_negotiation":
        if row.get("disposition", 50) >= 60 and row.get("fear", 0) >= 35:
            _add_crisis(player, ctx, key, "client", "Поиск римского покровительства", f"{name} готова обсуждать зависимый союз и римские гарантии.")
        else:
            row["disposition"] = _clamp(row.get("disposition", 50) + 5, 0, 100, 50)
            row["trust"] = _clamp(row.get("trust", 40) + 4, 0, 100, 40)
        _record(player, ctx, key, "Переговоры о покровительстве", f"{name} ищет сильного патрона и проверяет условия Рима.", "good")
    elif plan == "cultural_mission":
        row["disposition"] = _clamp(row.get("disposition", 50) + 5, 0, 100, 50)
        row["trust"] = _clamp(row.get("trust", 40) + 3, 0, 100, 40)
        player.science_points = max(0, _i(getattr(player, "science_points", 0), 0) + 5)
        _record(player, ctx, key, "Культурная миссия", f"{name} направляет учёных, переводчиков и дары библиотекам; Рим получает 5 науки.", "good")

    pstate["plan"] = None
    pstate["plan_progress"] = 0
    pstate["plan_required"] = 0
    pstate["last_action_turn"] = turn
    pstate["cooldown"] = random.randint(1, 3)


def _tick_power(player: Any, ctx: dict, key: str, pstate: dict, row: dict, state: dict, rome: dict) -> None:
    turn = _i(getattr(player, "turn", 1), 1)
    # Экономика и общество державы живут независимо от Рима.
    income = max(2, pstate["economic_power"] // 9 + (4 if row.get("trade_pact") else 0) + random.randint(-2, 4))
    upkeep = max(1, pstate["readiness"] // 16 + (5 if row.get("at_war") else 0))
    pstate["treasury"] = max(0, pstate["treasury"] + income - upkeep)
    if pstate["treasury"] <= 20:
        pstate["stability"] = _clamp(pstate["stability"] - 2, 0, 100, 50)
        pstate["readiness"] = _clamp(pstate["readiness"] - 2, 0, 100, 50)
    elif pstate["treasury"] >= 250:
        pstate["economic_power"] = _clamp(pstate["economic_power"] + (1 if random.random() < 0.35 else 0), 0, 100, 50)
    if row.get("at_war"):
        pstate["war_weariness"] = _clamp(pstate["war_weariness"] + random.randint(2, 5), 0, 100, 0)
        pstate["manpower"] = _clamp(pstate["manpower"] - random.randint(0, 2), 0, 100, 50)
        pstate["treasury"] = max(0, pstate["treasury"] - random.randint(3, 8))
        _spawn_war_force(player, ctx, key, pstate)
        if pstate["war_weariness"] >= 78 and (pstate["manpower"] <= 35 or pstate["treasury"] <= 35):
            row["at_war"] = False
            row["tension"] = _clamp(row.get("tension", 70) - 18, 0, 100, 50)
            row["trust"] = _clamp(row.get("trust", 30) - 3, 0, 100, 30)
            pstate["war_weariness"] = max(35, pstate["war_weariness"] - 25)
            _record(player, ctx, key, "Прекращение активной войны", f"{pstate['name']} истощена и прекращает крупные военные действия, не отказываясь от претензий.", "info", 4)
    else:
        pstate["war_weariness"] = _clamp(pstate["war_weariness"] - 2, 0, 100, 0)
        pstate["manpower"] = _clamp(pstate["manpower"] + (1 if random.random() < 0.55 else 0), 0, 100, 50)

    own_power = pstate["readiness"] * 0.8 + pstate["manpower"] * 0.55 + pstate["economic_power"] * 0.45 + _i(row.get("strength", 5), 5) * 5
    true_threat = _clamp((rome["power"] - own_power + 65) * 0.65 + _i(row.get("hostility", 50), 50) * 0.25, 0, 100, 30)
    true_opportunity = _clamp(rome["weakness"] * 0.85 + pstate["opportunism"] * 0.25 - _i(row.get("fear", 10), 10) * 0.2, 0, 100, 30)
    intel = _clamp(row.get("intel", 20), 0, 100, 20)
    noise = max(1, (100 - intel) // 10)
    pstate["threat_from_rome"] = _clamp(true_threat + random.randint(-noise, noise), 0, 100, 30)
    pstate["opportunity_against_rome"] = _clamp(true_opportunity + random.randint(-noise, noise), 0, 100, 30)
    pstate["known_rome_power"] = max(0, int(round(rome["power"] + random.uniform(-noise * 1.5, noise * 1.5))))
    pstate["intel_confidence"] = _clamp((pstate["intel_confidence"] * 3 + intel) // 4, 0, 100, 20)

    goal = _choose_goal(key, pstate, row, rome, state, turn)
    if not pstate.get("plan"):
        pstate["plan"], pstate["plan_required"] = _plan_for_goal(goal, pstate)
        pstate["plan_progress"] = 0
        pstate["plan_target"] = "rome"
    if pstate["cooldown"] > 0:
        pstate["cooldown"] -= 1
    plan_gain = max(4, pstate["diplomatic_weight"] // 12 + pstate["readiness"] // 18 + random.randint(0, 5))
    if pstate["stability"] < 35:
        plan_gain = max(2, plan_gain - 4)
    if pstate["treasury"] < 20:
        plan_gain = max(1, plan_gain - 3)
    pstate["plan_progress"] += plan_gain
    if (
        pstate["plan_progress"] >= max(1, pstate["plan_required"])
        and pstate["cooldown"] <= 0
        and _i(state.get("_actions_this_turn", 0), 0) < 2
    ):
        _complete_plan(player, ctx, key, pstate, row, state)
        state["_actions_this_turn"] = _i(state.get("_actions_this_turn", 0), 0) + 1


def _tick_world_relations(player: Any, ctx: dict, state: dict) -> None:
    diplomacy = getattr(player, "diplomacy", {})
    keys = sorted(state["powers"])
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            relation = _i(state["relations"][a].get(b, 50), 50)
            pa, pb = state["powers"][a], state["powers"][b]
            drift = random.choice([-1, 0, 0, 0, 1])
            if pa.get("goal") == pb.get("goal") == "contain_rome": drift += 2
            if pa.get("goal") == "expand_region" or pb.get("goal") == "expand_region": drift -= 1
            if diplomacy.get(a, {}).get("alliance") and diplomacy.get(b, {}).get("alliance"): drift += 1
            relation = _clamp(relation + drift, 0, 100, 50)
            state["relations"][a][b] = relation
            state["relations"][b][a] = relation

    # Коалиции стареют, но могут усиливаться при общей угрозе.
    coalitions = []
    turn = _i(getattr(player, "turn", 1), 1)
    for coalition in _list(state.get("coalitions")):
        if not isinstance(coalition, dict): continue
        members = [m for m in _list(coalition.get("members")) if m in state["powers"]]
        if len(members) < 2: continue
        avg_threat = sum(state["powers"][m]["threat_from_rome"] for m in members) / len(members)
        coalition["strength"] = _clamp(coalition.get("strength", 50) + (1 if avg_threat >= 55 else -1), 0, 100, 50)
        if coalition["strength"] > 18 and turn - _i(coalition.get("formed_turn", turn), turn) < 20:
            coalitions.append(coalition)
    state["coalitions"] = coalitions[-12:]


def _domestic_ai_tick(player: Any, ctx: dict, state: dict) -> None:
    factions = [f for f in _list(getattr(player, "ai_factions", [])) if not getattr(f, "defeated", False) and getattr(f, "name", None)]
    if len(factions) < 2:
        return
    turn = _i(getattr(player, "turn", 1), 1)
    domestic = state["domestic_relations"]
    for i, a in enumerate(factions):
        for b in factions[i + 1:]:
            relation = _i(domestic[str(a.name)].get(str(b.name), 45), 45)
            same_goal = getattr(a, "goal", None) and getattr(a, "goal", None) == getattr(b, "goal", None)
            drift = random.choice([-2, -1, 0, 0, 1]) + (3 if same_goal else 0)
            if getattr(a, "strategy", "") == getattr(b, "strategy", ""): drift += 1
            relation = _clamp(relation + drift, 0, 100, 45)
            domestic[str(a.name)][str(b.name)] = relation
            domestic[str(b.name)][str(a.name)] = relation

    if turn - _i(state.get("domestic_last_action_turn", 0), 0) < 4:
        return
    instability = _i(getattr(player, "unrest", 0), 0) + max(0, 55 - _i(getattr(player, "senate_rep", 50), 50)) + max(0, 55 - _i(getattr(player, "people_rep", 50), 50))
    pairs = []
    for i, a in enumerate(factions):
        for b in factions[i + 1:]:
            relation = domestic[str(a.name)].get(str(b.name), 0)
            capacity = _i(getattr(a, "resources", 0), 0) + _i(getattr(b, "resources", 0), 0)
            influence = _i(getattr(a, "influence", 0), 0) + _i(getattr(b, "influence", 0), 0)
            score = relation + capacity * 0.45 + influence * 0.35 + instability * 0.25
            pairs.append((score, a, b))
    if not pairs:
        return
    score, a, b = max(pairs, key=lambda x: x[0])
    chance = max(0.0, min(0.60, (score - 120) / 180))
    if random.random() >= chance:
        return
    # Совместная операция — редкое, но заметное следствие взаимодействия ИИ.
    operation = random.choices(
        ["senate_bloc", "street_network", "treasury_pressure", "provincial_clients"],
        weights=[28, 27, 22, 23], k=1,
    )[0]
    if operation == "senate_bloc":
        loss = random.randint(3, 6)
        player.senate_rep = max(0, _i(getattr(player, "senate_rep", 0), 0) - loss)
        text = f"{a.name} и {b.name} создали общий блок в Сенате; репутация власти -{loss}."
    elif operation == "street_network":
        loss = random.randint(2, 5)
        player.people_rep = max(0, _i(getattr(player, "people_rep", 0), 0) - loss)
        player.unrest = _clamp(_i(getattr(player, "unrest", 0), 0) + 2, 0, 100, 0)
        text = f"Сторонники {a.name} и {b.name} совместно организовали уличную агитацию; народная репутация -{loss}."
    elif operation == "treasury_pressure":
        loss = min(_i(getattr(player, "gold", 0), 0), random.randint(18, 42))
        player.gold = max(0, _i(getattr(player, "gold", 0), 0) - loss)
        text = f"Связанные с {a.name} и {b.name} откупщики сорвали платежи; казна потеряла {loss} золота."
    else:
        provinces = [p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict) and p.get("name") != "Latium"]
        if not provinces:
            return
        target = max(provinces, key=lambda p: _i(p.get("unrest", 0), 0) + random.randint(0, 3))
        target["unrest"] = min(10, _i(target.get("unrest", 0), 0) + 1)
        text = f"{a.name} и {b.name} укрепили клиентелу в провинции {target.get('name')}; волнения выросли."
    a.resources = max(0, _i(getattr(a, "resources", 0), 0) - 12)
    b.resources = max(0, _i(getattr(b, "resources", 0), 0) - 12)
    a.influence = min(100, _i(getattr(a, "influence", 0), 0) + 2)
    b.influence = min(100, _i(getattr(b, "influence", 0), 0) + 2)
    state["domestic_last_action_turn"] = turn
    _record(player, ctx, None, "Координация римских фракций", text, "bad", 3)


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 1), 1)
    if state.get("last_tick_turn") >= turn:
        return state
    state["last_tick_turn"] = turn
    diplomacy = _base_diplomacy(player, ctx)
    rome = _rome_metrics(player, ctx)
    state["_actions_this_turn"] = 0
    for key, pstate in state["powers"].items():
        row = diplomacy.get(key)
        if isinstance(row, dict):
            row.setdefault("at_war", False)
            row.setdefault("war_started_turn", 0)
            _tick_power(player, ctx, key, pstate, row, state, rome)
    _tick_world_relations(player, ctx, state)
    _domestic_ai_tick(player, ctx, state)
    state.pop("_actions_this_turn", None)
    return state


def strategic_assessment(player: Any, ctx: dict | None = None) -> list[dict]:
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    diplomacy = _base_diplomacy(player, ctx)
    result = []
    for key, pstate in state["powers"].items():
        row = diplomacy.get(key, {})
        danger = (
            pstate["readiness"] * 0.35 + pstate["aggression"] * 0.25 + pstate["opportunity_against_rome"] * 0.25
            + _i(row.get("tension", 0), 0) * 0.25 - _i(row.get("fear", 0), 0) * 0.1
            + (25 if row.get("at_war") else 0) - (20 if row.get("alliance") or row.get("client") else 0)
        )
        opportunity = (
            _i(row.get("disposition", 50), 50) * 0.3 + _i(row.get("trust", 40), 40) * 0.3
            + pstate["trade_drive"] * 0.25 + _i(row.get("trade_interest", 50), 50) * 0.2
            - _i(row.get("tension", 0), 0) * 0.25
        )
        result.append({
            "key": key, "name": pstate["name"], "danger": int(round(danger)), "opportunity": int(round(opportunity)),
            "goal": pstate.get("goal"), "plan": pstate.get("plan"), "war": bool(row.get("at_war")),
            "recommendation": (
                "немедленное сдерживание и разведка" if danger >= 70 else
                "подготовить гарантии и контрмеры" if danger >= 52 else
                "развивать торговлю и доверие" if opportunity >= 65 else
                "наблюдать и сохранять свободу действий"
            ),
        })
    return sorted(result, key=lambda x: (x["danger"], x["opportunity"]), reverse=True)


def _power_detail(ui: UI, player: Any, ctx: dict, key: str) -> None:
    state = ensure_state(player, ctx)
    pstate = state["powers"][key]
    row = _base_diplomacy(player, ctx).get(key, {})
    ui.screen(); ui.header(pstate["name"].upper(), "🦅", pstate["personality"])
    ui.table("Показатели", ["Параметр", "Значение"], [
        ("Отношение / доверие / напряжённость", f"{row.get('disposition', 0)} / {row.get('trust', 0)} / {row.get('tension', 0)}"),
        ("Страх / разведка / рычаги", f"{row.get('fear', 0)} / {row.get('intel', 0)} / {row.get('leverage', 0)}"),
        ("Казна / экономика", f"{pstate['treasury']} / {pstate['economic_power']}"),
        ("Людские ресурсы / готовность", f"{pstate['manpower']} / {pstate['readiness']}"),
        ("Стабильность / усталость от войны", f"{pstate['stability']} / {pstate['war_weariness']}"),
        ("Флот / дипломатический вес", f"{pstate['naval_power']} / {pstate['diplomatic_weight']}"),
        ("Характер", f"агрессия {pstate['aggression']}; оппортунизм {pstate['opportunism']}; честь {pstate['honor']}; риск {pstate['risk']}"),
        ("Доктрина", pstate["doctrine"]),
        ("Цель", GOAL_LABELS.get(pstate.get("goal"), pstate.get("goal") or "не определена")),
        ("Текущий план", PLAN_LABELS.get(pstate.get("plan"), pstate.get("plan") or "нет")),
        ("Прогресс плана", f"{pstate.get('plan_progress', 0)}/{max(1, pstate.get('plan_required', 0))}"),
        ("Оценка угрозы Рима", pstate["threat_from_rome"]),
        ("Оценка слабости Рима", pstate["opportunity_against_rome"]),
        ("Состояние войны", "ВОЙНА" if row.get("at_war") else "мир"),
    ], "CYAN")
    history = pstate.get("history", [])[-8:]
    if history:
        ui.table("Последние действия", ["Ход", "Событие", "Содержание"], [(h.get("turn"), h.get("title"), h.get("text")) for h in reversed(history)], "GOLD")
    ui.pause()


def _relations_matrix(ui: UI, state: dict) -> None:
    keys = sorted(state["powers"])
    headers = ["Держава"] + [state["powers"][k]["name"][:8] for k in keys]
    rows = []
    for a in keys:
        rows.append(tuple([state["powers"][a]["name"]] + [state["relations"][a].get(b, 0) for b in keys]))
    ui.table("Отношения между иностранными державами", headers, rows, "PURPLE")


def _counterintelligence_menu(ui: UI, player: Any, ctx: dict, state: dict) -> None:
    fp = getattr(player, "foreign_policy", {})
    capital = _i(_dict(fp).get("capital", 0), 0)
    ui.screen(); ui.header("КОНТРРАЗВЕДЫВАТЕЛЬНЫЕ МЕРЫ", "🕵")
    ui.info(f"Дипломатический капитал: {capital}; золото: {_i(getattr(player, 'gold', 0), 0)}", "CYAN")
    keys = sorted(state["powers"])
    for i, key in enumerate(keys, 1):
        p = state["powers"][key]
        print(f"  {i}. {p['name']} — разведка {p['intel_confidence']}; план: {PLAN_LABELS.get(p.get('plan'), 'неизвестно')}")
    print("  Q. Назад")
    answer = ui.choice("\n  Цель: ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
    if answer == "Q": return
    key = keys[int(answer) - 1]
    pstate = state["powers"][key]
    row = _base_diplomacy(player, ctx).get(key, {})
    cost_gold, cost_capital = 45, 1
    if capital < cost_capital or _i(getattr(player, "gold", 0), 0) < cost_gold:
        ui.info(f"Нужно {cost_capital} дипломатического капитала и {cost_gold} золота.", "RED"); ui.pause(); return
    player.gold -= cost_gold
    fp["capital"] = max(0, capital - cost_capital)
    success = random.random() < 0.55 + _i(row.get("intel", 20), 20) / 250
    if success:
        pstate["plan_progress"] = max(0, pstate["plan_progress"] - random.randint(12, 24))
        pstate["intel_confidence"] = _clamp(pstate["intel_confidence"] - 8, 0, 100, 20)
        row["intel"] = _clamp(row.get("intel", 20) + 8, 0, 100, 20)
        ui.info(f"Операция успешна. План раскрыт: {PLAN_LABELS.get(pstate.get('plan'), pstate.get('plan'))}; его подготовка задержана.", "GREEN")
        _record(player, ctx, key, "Римская контрразведка", f"Агентурная сеть державы {pstate['name']} частично раскрыта.", "good")
    else:
        row["tension"] = _clamp(row.get("tension", 30) + 4, 0, 100, 30)
        ui.info("Операция не дала результата; иностранный двор подозревает вмешательство Рима.", "RED")
    ui.pause()


def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx)
    ui = UI(ctx)
    state = ensure_state(player, ctx)
    while True:
        ui.screen(); ui.header("ORBIS POLITICUS", "🌍", f"Стратегический ИИ держав {MODULE_VERSION}")
        assessment = strategic_assessment(player, ctx)
        rows = []
        diplomacy = _base_diplomacy(player, ctx)
        for item in assessment:
            key = item["key"]; p = state["powers"][key]; d = diplomacy.get(key, {})
            rows.append((
                p["name"], d.get("disposition", 0), d.get("tension", 0), p["readiness"], p["economic_power"],
                GOAL_LABELS.get(p.get("goal"), p.get("goal")), PLAN_LABELS.get(p.get("plan"), p.get("plan")),
                "ВОЙНА" if d.get("at_war") else "мир",
            ))
        ui.table("Державы", ["Держава", "Отн.", "Напр.", "Готов.", "Экон.", "Цель", "План", "Статус"], rows, "CYAN")
        ui.section("Команды", "GOLD")
        print("  1. Подробное досье державы")
        print("  2. Матрица отношений между державами")
        print("  3. Стратегическая оценка угроз и возможностей")
        print("  4. Контрразведывательная операция")
        print("  5. Архив самостоятельных действий ИИ")
        print("  Q. Назад")
        answer = ui.choice("\n  Выбор: ", ["1", "2", "3", "4", "5", "Q"])
        if answer == "Q": return
        if answer == "1":
            keys = sorted(state["powers"])
            ui.screen(); ui.header("ДОСЬЕ ДЕРЖАВ", "📜")
            for i, key in enumerate(keys, 1): print(f"  {i}. {state['powers'][key]['name']}")
            selected = ui.choice("\n  Держава (или Q): ", [str(i) for i in range(1, len(keys)+1)] + ["Q"])
            if selected != "Q": _power_detail(ui, player, ctx, keys[int(selected)-1])
        elif answer == "2":
            ui.screen(); ui.header("СИСТЕМА ДЕРЖАВ", "🕸")
            _relations_matrix(ui, state)
            if state.get("coalitions"):
                ui.table("Коалиции", ["Участники", "Цель", "Сила", "Ход"], [
                    (", ".join(state["powers"].get(k, {}).get("name", k) for k in c.get("members", [])), GOAL_LABELS.get(c.get("purpose"), c.get("purpose")), c.get("strength"), c.get("formed_turn"))
                    for c in state["coalitions"]
                ], "RED")
            ui.pause()
        elif answer == "3":
            ui.screen(); ui.header("СТРАТЕГИЧЕСКАЯ ОЦЕНКА", "🦉")
            ui.table("Угрозы и возможности", ["Держава", "Угроза", "Возможность", "Рекомендация"], [
                (a["name"], a["danger"], a["opportunity"], a["recommendation"]) for a in assessment
            ], "GOLD")
            ui.pause()
        elif answer == "4":
            _counterintelligence_menu(ui, player, ctx, state)
        elif answer == "5":
            ui.screen(); ui.header("АРХИВ ORBIS POLITICUS", "📜")
            history = state.get("history", [])[-35:]
            if history:
                ui.table("Последние события", ["Ход", "Держава", "Событие", "Содержание"], [
                    (h.get("turn"), state["powers"].get(h.get("power"), {}).get("name", "Рим"), h.get("title"), h.get("text")) for h in reversed(history)
                ], "CYAN")
            else:
                ui.info("Архив пока пуст.", "GRAY")
            ui.pause()


# ─── RES PUBLICA ORBIS COMPATIBILITY ROUTE ────────────────────────────────
# Старые прямые входы оставлены для сторонних модов и старых горячих клавиш,
# но в актуальной сборке ведут в соответствующий раздел единого центра.
_legacy_open_menu_before_world_politics = open_menu

def open_menu(player: Any, ctx: dict | None = None) -> None:
    context = _ctx(ctx)
    facade = context.get("WORLD_POLITICS")
    if facade is not None and hasattr(facade, "open_menu"):
        facade.open_menu(player, context, start_section="intelligence")
        return
    return _legacy_open_menu_before_world_politics(player, context)
