#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Religio Provinciarum — расширенная религиозная система Roma Aeterna.

Модуль не импортирует основной файл игры. Все связи передаются через ``player``
и ``ctx`` (обычно globals() из roma_aeterna.py). Это сохраняет совместимость
с сохранениями и позволяет держать тяжёлую религиозную механику вне главного
файла.

Публичный контракт:
    ensure_state(player, ctx=None)
    effect(player, key, default=0, ctx=None)
    choose_religion(player, ctx=None)
    open_menu(player, ctx=None)
    process_turn(player, ctx=None, interactive=False)
    economy_modifiers(player, ctx=None)
    province_modifiers(player, province, ctx=None)
    maybe_event(player, ctx=None)
    maybe_spawn_sacred_figure(player, ctx=None)
"""

from __future__ import annotations

import copy
import math
import os
import random
import re
import textwrap
from typing import Any

MODULE_VERSION = "3.1.0-religio-interface"
SCHEMA_VERSION = 3
MAX_LOG = 180
MAX_DYNAMIC_HOLY_CITIES = 2
VALID_RELIGIONS = ("judaism", "christianity", "paganism")

POLICIES: dict[str, dict[str, Any]] = {
    "tolerance": {
        "name": "Толерантность",
        "desc": "Меньшинства защищены законом. Торговля и дипломатия растут, обращение идёт медленно.",
        "conversion_rate": 0.34,
        "minority_unrest": -0.25,
        "tax_mult": 0.96,
        "levy_mult": 0.92,
        "trade_mult": 1.10,
        "diplomacy": 8,
        "integrity": -1,
        "change_cost": 15,
    },
    "encouragement": {
        "name": "Мягкое поощрение",
        "desc": "Официальная вера получает храмы и льготы без прямого принуждения.",
        "conversion_rate": 0.72,
        "minority_unrest": 0.05,
        "tax_mult": 0.93,
        "levy_mult": 0.89,
        "trade_mult": 1.03,
        "diplomacy": 2,
        "integrity": 1,
        "change_cost": 20,
    },
    "persecution": {
        "name": "Гонения",
        "desc": "Чужие культы ограничены. Обращение ускоряется, но растут волнения и внешняя враждебность.",
        "conversion_rate": 1.28,
        "minority_unrest": 0.55,
        "tax_mult": 0.86,
        "levy_mult": 0.82,
        "trade_mult": 0.90,
        "diplomacy": -10,
        "integrity": -2,
        "change_cost": 30,
    },
    "mandatory_cult": {
        "name": "Обязательный культ",
        "desc": "Публичное исповедание официальной религии становится условием политической лояльности.",
        "conversion_rate": 1.72,
        "minority_unrest": 0.90,
        "tax_mult": 0.80,
        "levy_mult": 0.74,
        "trade_mult": 0.82,
        "diplomacy": -18,
        "integrity": -4,
        "change_cost": 45,
    },
}

CORE_PROVINCES = {"Latium", "Campania", "Etruria", "Umbria"}
DEFAULT_PROVINCE_RELIGION = {
    "Judaea": "judaism",
}
MINORITY_SPECIALS = {
    "judaism": {"trade_mult": 1.05, "tax_mult": 1.01, "label": "сети общин и грамотные сборщики"},
    "christianity": {"trade_mult": 1.02, "levy_mult": 0.98, "label": "благотворительные общины"},
    "paganism": {"trade_mult": 1.03, "levy_mult": 1.02, "label": "местные культы и праздники"},
}

FALLBACK_NAMES = {
    "judaism": ("✡", "Иудаизм", "Завет, Закон, мудрость и устойчивость."),
    "christianity": ("✝", "Христианство", "Милосердие, единство и прочность державы."),
    "paganism": ("🏛", "Язычество", "Боги Империи, армия, флот и экспансия."),
}

EFFECT_LABELS = {
    "faith_flat": "вера за ход",
    "faith_percent": "прирост веры",
    "gold_flat": "золото",
    "gold_percent": "доход",
    "grain_flat": "зерно",
    "glory_per_turn": "слава за ход",
    "population_growth_percent": "рост населения",
    "trade_income_percent": "торговый доход",
    "battle_attack": "атака",
    "battle_defense": "защита",
    "army_morale_percent": "мораль армии",
    "army_loss_reduction": "снижение потерь",
    "province_unrest_control": "контроль провинций",
    "unrest_reduction": "снижение волнений",
    "city_loyalty": "лояльность городов",
    "governor_loyalty_bonus": "лояльность наместников",
    "diplomacy_bonus": "дипломатия",
    "event_good_chance": "добрые события",
    "epidemic_resist": "сопротивление эпидемиям",
    "religion_institute_discount": "скидка институтов",
    "religion_institute_power": "сила институтов",
    "science_flat": "наука",
    "people_rep_flat": "народ",
    "senate_rep_flat": "Сенат",
    "conversion_pressure": "давление обращения",
    "integrity_flat": "целостность",
    "holy_city_power": "сила святых городов",
    "heresy_resistance": "сопротивление ересям",
    "heresy_risk": "риск ереси",
    "minority_trade_bonus": "бонус терпимости",
    "levy_percent": "набор ополчения",
    "relic_security": "защита реликвий",
    "tolerance_bonus": "эффект толерантности",
    "naval_power_percent": "сила флота",
    "health_bonus": "здоровье",
    "upkeep_percent": "содержание",
    "sacred_general_chance_bonus": "шанс священной фигуры",
    "heresy": "риск ереси",
    "holy_city": "святое место",
}
PERCENT_KEYS = {
    key for key in EFFECT_LABELS
    if key.endswith("_percent") or key in {
        "event_good_chance", "epidemic_resist", "religion_institute_discount",
        "religion_institute_power", "conversion_pressure", "holy_city_power",
        "heresy_resistance", "heresy_risk", "minority_trade_bonus",
        "relic_security", "tolerance_bonus", "upkeep_percent",
        "sacred_general_chance_bonus", "heresy",
    }
}


def _i(value: Any, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    try:
        result = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        result = default
    if low is not None:
        result = max(low, result)
    if high is not None:
        result = min(high, result)
    return result


def _f(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _ctx(ctx: dict | None) -> dict:
    return ctx if isinstance(ctx, dict) else {}


def _clamp(value: Any, low: float = 0.0, high: float = 100.0, default: float = 0.0) -> float:
    return max(low, min(high, _f(value, default)))


def _religion_catalog(ctx: dict | None = None) -> dict[str, dict]:
    raw = _dict(_ctx(ctx).get("RELIGION_CHOICES"))
    result: dict[str, dict] = {}
    for key in VALID_RELIGIONS:
        row = raw.get(key)
        if isinstance(row, dict):
            result[key] = row
        else:
            icon, name, desc = FALLBACK_NAMES[key]
            result[key] = {"icon": icon, "name": name, "desc": desc}
    return result


def _content(player: Any, ctx: dict | None = None) -> dict:
    religion = str(getattr(player, "religion", "") or "")
    return _religion_catalog(ctx).get(religion, {})


def _tech_effect(player: Any, key: str, ctx: dict | None = None) -> float:
    fn = _ctx(ctx).get("tech_effect")
    if callable(fn):
        try:
            return _f(fn(player, key, 0), 0.0)
        except TypeError:
            try:
                return _f(fn(player, key), 0.0)
            except Exception:
                return 0.0
        except Exception:
            return 0.0
    return 0.0


def _log(player: Any, message: str, ctx: dict | None = None) -> None:
    state = _dict(getattr(player, "religion_system", {}))
    turn = _i(getattr(player, "turn", 0), 0)
    line = f"Ход {turn}: {message}"
    history = state.setdefault("log", [])
    history.append(line)
    del history[:-MAX_LOG]
    legacy = getattr(player, "religion_event_log", None)
    if isinstance(legacy, list):
        legacy.append(line)
        del legacy[:-40]
    callback = _ctx(ctx).get("log_event")
    if callable(callback):
        try:
            callback(player, message)
        except Exception:
            pass


def _notify(text: str, ctx: dict | None = None, color: str = "GOLD") -> None:
    context = _ctx(ctx)
    clr = context.get("clr")
    colors = context.get("C")
    if callable(clr) and colors is not None:
        try:
            print(clr("  " + text, getattr(colors, color, "")))
            return
        except Exception:
            pass
    print("  " + text)


def _screen(title: str, icon: str = "🕯", ctx: dict | None = None, subtitle: str = "") -> None:
    context = _ctx(ctx)
    start = context.get("rui_screen_start") or context.get("clear")
    if callable(start):
        try:
            start()
        except Exception:
            pass
    header = context.get("rui_header")
    colors = context.get("C")
    if callable(header) and colors is not None:
        try:
            header(title, icon, getattr(colors, "GOLD", ""), subtitle)
            return
        except TypeError:
            try:
                header(title, icon, getattr(colors, "GOLD", ""))
                if subtitle:
                    _info(subtitle, ctx, "GRAY")
                return
            except Exception:
                pass
    print(f"\n{'═' * 72}\n  {icon} {title}\n{'═' * 72}")
    if subtitle:
        print("  " + subtitle)


def _info(text: Any, ctx: dict | None = None, color: str = "WHITE") -> None:
    context = _ctx(ctx)
    fn = context.get("rui_info")
    colors = context.get("C")
    if callable(fn) and colors is not None:
        try:
            fn(str(text), getattr(colors, color, ""))
            return
        except Exception:
            pass
    print("  " + str(text))


def _pause(ctx: dict | None = None) -> None:
    fn = _ctx(ctx).get("rui_pause") or _ctx(ctx).get("pause")
    if callable(fn):
        try:
            fn()
            return
        except Exception:
            pass
    input("\n  Нажмите Enter, чтобы продолжить...")


def _choice(prompt: str, valid: list[str], ctx: dict | None = None) -> str:
    valid = [str(x).upper() for x in valid]
    fn = _ctx(ctx).get("read_choice")
    if callable(fn):
        try:
            return str(fn(prompt, valid)).upper()
        except Exception:
            pass
    while True:
        value = input(prompt).strip().upper()
        if value in valid:
            return value
        print("  Допустимо: " + ", ".join(valid))


# ─── АДАПТИВНЫЙ ИНТЕРФЕЙС RELIGIO IMPERII ──────────────────────────────────

def _ui_width() -> int:
    """Безопасная ширина экрана для Termux и обычного терминала."""
    try:
        columns = int(os.get_terminal_size().columns)
    except (OSError, AttributeError, ValueError):
        columns = 80
    return max(48, min(92, columns - 2))


def _ui_wrap(text: Any, width: int | None = None) -> list[str]:
    width = max(24, (width or _ui_width()) - 6)
    value = str(text or "").strip()
    if not value:
        return [""]
    return textwrap.wrap(
        value,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
        replace_whitespace=True,
    ) or [""]


def _ui_rule(ctx: dict | None = None, char: str = "─", color: str = "GRAY") -> None:
    _info(char * _ui_width(), ctx, color)


def _ui_section(title: str, icon: str = "◆", ctx: dict | None = None, color: str = "GOLD") -> None:
    width = _ui_width()
    label = f" {icon} {title.strip()} "
    tail = "─" * max(1, width - len(label))
    _info(label + tail, ctx, color)


def _ui_bar(value: Any, maximum: Any = 100, width: int = 18) -> str:
    maximum_f = max(1.0, _f(maximum, 100.0))
    ratio = max(0.0, min(1.0, _f(value, 0.0) / maximum_f))
    filled = int(round(width * ratio))
    return "█" * filled + "░" * (width - filled)


def _ui_card(
    title: str,
    lines: list[Any],
    ctx: dict | None = None,
    *,
    color: str = "WHITE",
    title_color: str | None = None,
    badge: str = "",
) -> None:
    """Простая карточка, которая не требует Rich и не ломает узкий экран."""
    width = _ui_width()
    heading = f" {title.strip()} "
    if badge:
        heading += f"[{badge}] "
    top = "┌─" + heading + "─" * max(1, width - len(heading) - 2)
    _info(top[:width], ctx, title_color or color)
    for raw in lines:
        for line in _ui_wrap(raw, width):
            _info(("│ " + line)[:width], ctx, color)
    _info("└" + "─" * (width - 1), ctx, color)


def _ui_menu_item(key: str, title: str, note: str, ctx: dict | None = None, color: str = "WHITE") -> None:
    width = _ui_width()
    left = f"[{key}] {title}"
    dots = "·" * max(2, width - len(left) - len(note) - 5)
    _info(f"{left} {dots} {note}"[:width], ctx, color)


def _ui_religion_label(key: str, ctx: dict | None = None) -> str:
    info = religion_info(key, ctx)
    return f"{info['icon']} {info['name']}"


def _ui_branch_name(player: Any, branch_id: str, ctx: dict | None = None) -> str:
    for row in doctrine_branches(player, ctx):
        if row.get("id") == branch_id:
            return str(row.get("name", branch_id))
    return str(branch_id or "общая")


def _ui_relic_status(value: str) -> str:
    return {
        "owned": "в державе",
        "hidden": "не обнаружена",
        "lost": "утрачена",
        "foreign": "у чужеземцев",
    }.get(str(value), str(value or "неизвестно"))


def _ui_heresy_status(value: str) -> str:
    return {
        "dormant": "дремлет",
        "active": "активна",
        "suppressed": "подавлена",
        "negotiated": "договор",
        "accepted": "принята",
    }.get(str(value), str(value or "неизвестно"))


def _ui_active_heresies(player: Any) -> list[tuple[str, dict]]:
    state = _dict(getattr(player, "religion_system", {}))
    return [
        (str(hid), _dict(entry))
        for hid, entry in _dict(state.get("heresies")).items()
        if _dict(entry).get("status") == "active"
    ]


def _ui_religion_counts(player: Any, ctx: dict | None = None) -> dict[str, int]:
    state = ensure_state(player, ctx)
    return {
        "holy": len(_controlled_holy_city_rows(player, ctx)),
        "relics": len(_owned_relic_rows(player, ctx)),
        "heresies": len(_ui_active_heresies(player)),
        "figures": len(_list(getattr(player, "sacred_generals", []))),
        "institutes": len(_list(getattr(player, "religious_institutes", []))),
        "doctrines": len(_dict(state.get("doctrines"))),
    }


def _ui_confirm(prompt: str, ctx: dict | None = None) -> bool:
    return _choice(f"\n  {prompt} [Y/N]: ", ["Y", "N"], ctx) == "Y"


def _ui_institute_cost(player: Any, row: dict, ctx: dict | None = None) -> int:
    discount = min(0.65, max(-0.25, effect(player, "religion_institute_discount", 0, ctx)))
    raw_cost = max(1, int(round(_i(row.get("cost", 1), 1) * (1.0 - discount))))
    price_fn = _ctx(ctx).get("game_price")
    if callable(price_fn):
        try:
            return max(1, _i(price_fn(player, raw_cost, market=True), raw_cost))
        except Exception:
            return raw_cost
    return raw_cost


def _ui_institute_detail(player: Any, row: dict, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    owned = str(row.get("id")) in set(_list(getattr(player, "religious_institutes", [])))
    selected = set(_dict(state.get("doctrines")).values())
    ok, reason = _institute_requirement(row, selected)
    status = "ОТКРЫТ" if owned else "ДОСТУПЕН" if ok else "ЗАКРЫТ"
    lines = [
        f"Ветвь: {_ui_branch_name(player, str(row.get('branch', '')), ctx)}",
        f"Сила: {row.get('strength', 0)} • Стоимость: {_ui_institute_cost(player, row, ctx)} веры",
        "Эффект: " + effects_text(row.get("effects", {})),
    ]
    if row.get("risks"):
        lines.append("Риск: " + effects_text(row.get("risks", {})))
    if not ok:
        lines.append("Условие: " + reason)
    if row.get("requires_tech"):
        lines.append("Технология: " + str(row.get("requires_tech")))
    if row.get("quote"):
        lines.append(f"❝ {row.get('quote')} ❞")
    if row.get("source"):
        lines.append("— " + str(row.get("source")))
    if row.get("capstone"):
        lines.append("★ Завершающий институт ветви")
    _ui_card(
        f"{_i(row.get('order'), 0):02d}. {row.get('name', 'Институт')}",
        lines,
        ctx,
        color="GREEN" if owned else "WHITE" if ok else "GRAY",
        title_color="GOLD",
        badge=status,
    )


def _ui_doctrine_detail(
    player: Any,
    row: dict,
    current_id: str,
    ctx: dict | None = None,
) -> None:
    ok, reason = _doctrine_requirement_met(player, row, ctx)
    active = str(row.get("id")) == str(current_id)
    lines = [
        f"Стоимость: {row.get('cost', 0)} веры",
        "Бонусы: " + effects_text(row.get("effects", {})),
        "Компромисс: " + effects_text(row.get("debuffs", {})),
    ]
    if not ok:
        lines.append("Условие: " + reason)
    _ui_card(
        str(row.get("name", "Доктрина")),
        lines,
        ctx,
        color="GREEN" if active else "WHITE" if ok else "GRAY",
        title_color="GOLD",
        badge="ДЕЙСТВУЕТ" if active else "ДОСТУПНА" if ok else "ЗАКРЫТА",
    )

def effects_text(effects: dict) -> str:
    parts: list[str] = []
    for key, raw in _dict(effects).items():
        if not isinstance(raw, (int, float)) or raw == 0:
            continue
        label = EFFECT_LABELS.get(str(key), str(key))
        value = _f(raw)
        if key in PERCENT_KEYS:
            parts.append(f"{label}: {value:+.0%}")
        else:
            parts.append(f"{label}: {value:+g}")
    return "; ".join(parts) if parts else "особый эффект"


def _initial_pressure(religion: str) -> dict[str, float]:
    base = {key: 8.0 for key in VALID_RELIGIONS}
    if religion == "judaism":
        base.update({"judaism": 78.0, "paganism": 15.0, "christianity": 7.0})
    elif religion == "christianity":
        base.update({"christianity": 62.0, "paganism": 28.0, "judaism": 10.0})
    else:
        base.update({"paganism": 82.0, "judaism": 10.0, "christianity": 8.0})
    return base


def _province_default_religion(province: dict) -> str:
    current = str(province.get("religion", "") or "")
    if current in VALID_RELIGIONS:
        return current
    return DEFAULT_PROVINCE_RELIGION.get(str(province.get("name", "")), "paganism")


def _ensure_province(province: dict, official: str | None = None) -> dict:
    religion = _province_default_religion(province)
    province["religion"] = religion
    pressure = _dict(province.get("religion_pressure"))
    if not pressure:
        pressure = _initial_pressure(religion)
    for key in VALID_RELIGIONS:
        pressure[key] = round(_clamp(pressure.get(key, 0.0), 0.0, 200.0), 3)
    province["religion_pressure"] = pressure
    province["conversion_progress"] = round(_clamp(province.get("conversion_progress", 0.0), 0.0, 100.0), 3)
    province["religious_integrity"] = round(_clamp(province.get("religious_integrity", 50.0), 0.0, 100.0, 50.0), 3)
    province["religion_tax_mult"] = _f(province.get("religion_tax_mult", 1.0), 1.0)
    province["religion_levy_mult"] = _f(province.get("religion_levy_mult", 1.0), 1.0)
    province["religion_trade_mult"] = _f(province.get("religion_trade_mult", 1.0), 1.0)
    if official in VALID_RELIGIONS and str(province.get("name")) == "Latium":
        pressure[official] = max(pressure.get(official, 0.0), 90.0)
    return province


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    if not hasattr(player, "religion"):
        player.religion = None
    if str(getattr(player, "religion", "") or "") not in VALID_RELIGIONS:
        player.religion = None
    if not hasattr(player, "faith"):
        player.faith = 0
    player.faith = max(0, _i(getattr(player, "faith", 0), 0))
    if not isinstance(getattr(player, "religious_institutes", None), list):
        player.religious_institutes = []
    if not isinstance(getattr(player, "religion_event_log", None), list):
        player.religion_event_log = []
    if not isinstance(getattr(player, "sacred_generals", None), list):
        player.sacred_generals = []

    state = getattr(player, "religion_system", None)
    if not isinstance(state, dict):
        state = {}
    state.setdefault("schema", SCHEMA_VERSION)
    state.setdefault("version", MODULE_VERSION)
    state.setdefault("official_religion", player.religion)
    state.setdefault("policy", "encouragement")
    if state.get("policy") not in POLICIES:
        state["policy"] = "encouragement"
    state.setdefault("policy_changed_turn", 0)
    state.setdefault("doctrines", {})
    state.setdefault("doctrine_changed_turn", {})
    state.setdefault("integrity", 50.0)
    state.setdefault("holy_cities", {})
    state.setdefault("dynamic_holy_cities", [])
    state.setdefault("relics", {})
    state.setdefault("heresies", {})
    state.setdefault("accepted_branch", None)
    state.setdefault("capstones", [])
    state.setdefault("pending", [])
    state.setdefault("log", [])
    state.setdefault("last_turn_processed", 0)
    state.setdefault("last_event_turn", 0)
    state.setdefault("last_figure_turn", 0)
    state["doctrines"] = {
        str(k): str(v) for k, v in _dict(state.get("doctrines")).items()
        if str(k) and str(v)
    }
    state["doctrine_changed_turn"] = {
        str(k): _i(v, 0, 0) for k, v in _dict(state.get("doctrine_changed_turn")).items()
    }
    state["dynamic_holy_cities"] = [
        x for x in _list(state.get("dynamic_holy_cities")) if isinstance(x, dict)
    ][-MAX_DYNAMIC_HOLY_CITIES:]
    state["pending"] = [x for x in _list(state.get("pending")) if isinstance(x, dict)][-12:]
    state["log"] = [str(x) for x in _list(state.get("log"))][-MAX_LOG:]
    state["capstones"] = list(dict.fromkeys(str(x) for x in _list(state.get("capstones")) if str(x)))
    state["official_religion"] = player.religion
    state["schema"] = SCHEMA_VERSION
    state["version"] = MODULE_VERSION
    player.religion_system = state

    official = player.religion
    for province in _list(getattr(player, "provinces", [])):
        if isinstance(province, dict):
            _ensure_province(province, official)
    _sync_content_state(player, ctx)
    return state


def _sync_content_state(player: Any, ctx: dict | None = None) -> None:
    state = _dict(getattr(player, "religion_system", {}))
    content = _content(player, ctx)
    valid_institutes = {str(row.get("id") or f"{player.religion}_{i:02d}") for i, row in enumerate(_list(content.get("institutes")), 1) if isinstance(row, dict)}
    if valid_institutes:
        player.religious_institutes = [x for x in player.religious_institutes if x in valid_institutes]
    figures = [str(x) for x in _list(content.get("sacred_figures"))]
    if figures:
        player.sacred_generals = [x for x in player.sacred_generals if x in figures]

    relic_state = _dict(state.get("relics"))
    for row in _list(content.get("relics")):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        rid = str(row["id"])
        entry = relic_state.setdefault(rid, {})
        entry.setdefault("status", "hidden")
        entry.setdefault("location", None)
        entry.setdefault("holder", None)
        entry.setdefault("last_moved_turn", 0)
    state["relics"] = relic_state

    heresy_state = _dict(state.get("heresies"))
    for row in _list(content.get("heresies")):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        hid = str(row["id"])
        entry = heresy_state.setdefault(hid, {})
        entry.setdefault("status", "dormant")
        entry.setdefault("strength", 0)
        entry.setdefault("province", None)
        entry.setdefault("last_action_turn", 0)
    state["heresies"] = heresy_state


def religion_info(key: str, ctx: dict | None = None) -> dict:
    row = _religion_catalog(ctx).get(key, {})
    icon, name, desc = FALLBACK_NAMES.get(key, ("🕯", key, ""))
    return {
        "icon": str(row.get("icon", icon)),
        "name": str(row.get("name", name)),
        "desc": str(row.get("desc", desc)),
    }


def institute_catalog(player: Any, ctx: dict | None = None) -> list[dict]:
    content = _content(player, ctx)
    result: list[dict] = []
    for index, raw in enumerate(_list(content.get("institutes")), 1):
        if not isinstance(raw, dict):
            continue
        row = copy.deepcopy(raw)
        row["id"] = str(row.get("id") or f"{player.religion}_{index:02d}")
        row["order"] = _i(row.get("order", index), index, 1, 30)
        row["cost"] = _i(row.get("cost", 45 + index * 15), 45 + index * 15, 1)
        row["strength"] = _i(row.get("strength", min(125, 10 + index * 4)), min(125, 10 + index * 4), 1, 200)
        row["branch"] = str(row.get("branch", "general"))
        row["effects"] = _dict(row.get("effects"))
        result.append(row)
    result.sort(key=lambda x: x["order"])
    return result


def doctrine_catalog(player: Any, ctx: dict | None = None) -> list[dict]:
    result: list[dict] = []
    for raw in _list(_content(player, ctx).get("doctrines")):
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("branch"):
            continue
        row = copy.deepcopy(raw)
        row["id"] = str(row["id"])
        row["branch"] = str(row["branch"])
        row["cost"] = _i(row.get("cost", 100), 100, 1)
        row["effects"] = _dict(row.get("effects"))
        row["debuffs"] = _dict(row.get("debuffs"))
        result.append(row)
    return result


def doctrine_branches(player: Any, ctx: dict | None = None) -> list[dict]:
    rows = []
    for raw in _list(_content(player, ctx).get("doctrine_branches")):
        if isinstance(raw, dict) and raw.get("id"):
            rows.append({"id": str(raw["id"]), "name": str(raw.get("name", raw["id"]))})
    if rows:
        return rows
    seen = []
    for doc in doctrine_catalog(player, ctx):
        if doc["branch"] not in seen:
            seen.append(doc["branch"])
    return [{"id": key, "name": key} for key in seen]


def unlocked_doctrine_slots(player: Any, ctx: dict | None = None) -> int:
    content = _content(player, ctx)
    maximum = _i(content.get("doctrine_slots", 4), 4, 1, 4)
    base = 2
    tech = _i(_tech_effect(player, "doctrine_slots", ctx), 0, 0, 4)
    institute_bonus = _i(_raw_effect(player, "doctrine_slot_bonus", ctx, include_power=False), 0, 0, 2)
    return min(maximum, base + tech + institute_bonus)


def _selected_doctrine_rows(player: Any, ctx: dict | None = None) -> list[dict]:
    state = ensure_state(player, ctx)
    selected = set(_dict(state.get("doctrines")).values())
    return [row for row in doctrine_catalog(player, ctx) if row["id"] in selected]


def _owned_institute_rows(player: Any, ctx: dict | None = None) -> list[dict]:
    owned = set(str(x) for x in _list(getattr(player, "religious_institutes", [])))
    return [row for row in institute_catalog(player, ctx) if row["id"] in owned]


def _accepted_heresy_row(player: Any, ctx: dict | None = None) -> dict | None:
    state = ensure_state(player, ctx)
    accepted = str(state.get("accepted_branch") or "")
    if not accepted:
        return None
    for row in _list(_content(player, ctx).get("heresies")):
        if isinstance(row, dict) and str(row.get("id")) == accepted:
            return row
    return None


def _controlled_holy_city_rows(player: Any, ctx: dict | None = None) -> list[dict]:
    state = ensure_state(player, ctx)
    controlled = _dict(state.get("holy_cities"))
    rows = []
    for raw in _list(_content(player, ctx).get("holy_cities")):
        if isinstance(raw, dict) and raw.get("id") and _dict(controlled.get(str(raw["id"]))).get("controlled"):
            rows.append(raw)
    rows.extend(_list(state.get("dynamic_holy_cities")))
    return [x for x in rows if isinstance(x, dict)]


def _owned_relic_rows(player: Any, ctx: dict | None = None) -> list[dict]:
    state = ensure_state(player, ctx)
    statuses = _dict(state.get("relics"))
    rows = []
    for raw in _list(_content(player, ctx).get("relics")):
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        if _dict(statuses.get(str(raw["id"]))).get("status") == "owned":
            rows.append(raw)
    return rows


def _raw_effect(player: Any, effect_key: str, ctx: dict | None = None, *, include_power: bool = True) -> float:
    if not getattr(player, "religion", None):
        return 0.0
    content = _content(player, ctx)
    total = 0.0

    for tenet in _list(content.get("tenets")):
        if isinstance(tenet, dict):
            total += _f(_dict(tenet.get("effects")).get(effect_key, 0.0))

    institute_rows = _owned_institute_rows(player, ctx)
    institute_power = 1.0
    if include_power:
        for row in institute_rows:
            institute_power += _f(_dict(row.get("effects")).get("religion_institute_power", 0.0))
        institute_power = min(1.75, max(0.50, institute_power))
    for row in institute_rows:
        value = _f(_dict(row.get("effects")).get(effect_key, 0.0))
        if effect_key != "religion_institute_power":
            value *= institute_power
        total += value

    for row in _selected_doctrine_rows(player, ctx):
        total += _f(_dict(row.get("effects")).get(effect_key, 0.0))
        total += _f(_dict(row.get("debuffs")).get(effect_key, 0.0))

    accepted = _accepted_heresy_row(player, ctx)
    if isinstance(accepted, dict):
        total += _f(_dict(accepted.get("effects")).get(effect_key, 0.0))

    for row in _controlled_holy_city_rows(player, ctx):
        total += _f(_dict(row.get("effects")).get(effect_key, 0.0))

    for row in _owned_relic_rows(player, ctx):
        total += _f(_dict(row.get("effects")).get(effect_key, 0.0))

    figure_effects = _dict(content.get("sacred_effects"))
    total += len(_list(getattr(player, "sacred_generals", []))) * _f(figure_effects.get(effect_key, 0.0))

    policy = POLICIES.get(_dict(getattr(player, "religion_system", {})).get("policy"), POLICIES["encouragement"])
    if effect_key == "diplomacy_bonus":
        total += _f(policy.get("diplomacy", 0.0))
    return total


def effect(player: Any, effect_key: str, default: Any = 0, ctx: dict | None = None) -> Any:
    ensure_state(player, ctx)
    total = _f(default, 0.0) + _raw_effect(player, effect_key, ctx)
    integer_keys = {
        "faith_flat", "gold_flat", "grain_flat", "glory_per_turn", "battle_attack",
        "battle_defense", "province_unrest_control", "unrest_reduction",
        "city_loyalty", "governor_loyalty_bonus", "diplomacy_bonus",
        "science_flat", "people_rep_flat", "senate_rep_flat", "integrity_flat",
        "doctrine_slot_bonus",
    }
    if effect_key in integer_keys:
        return int(round(total))
    return total


def choose_religion(player: Any, ctx: dict | None = None) -> None:
    ensure_state(player, ctx)
    if player.religion:
        _notify("Государственная религия уже выбрана.", ctx, "RED")
        _pause(ctx)
        return
    catalog = _religion_catalog(ctx)
    _screen("ВЫБОР ГОСУДАРСТВЕННОЙ РЕЛИГИИ", "🕯", ctx)
    keys = list(VALID_RELIGIONS)
    for index, key in enumerate(keys, 1):
        info = religion_info(key, ctx)
        _info(f"{index}. {info['icon']} {info['name']} — {info['desc']}", ctx, "CYAN")
        tenets = [str(x.get("name")) for x in _list(catalog.get(key, {}).get("tenets")) if isinstance(x, dict)]
        if tenets:
            _info("   Догматы: " + ", ".join(tenets), ctx, "GRAY")
    value = _choice("\n  Выбор религии: ", [str(i) for i in range(1, 4)] + ["Q"], ctx)
    if value == "Q":
        return
    key = keys[int(value) - 1]
    player.religion = key
    player.faith = max(0, _i(getattr(player, "faith", 0))) + 80
    player.religious_institutes = []
    player.sacred_generals = []
    player.religion_event_log = []
    player.religion_system = {}
    state = ensure_state(player, ctx)
    state["official_religion"] = key
    state["integrity"] = 58.0

    for province in _list(getattr(player, "provinces", [])):
        if not isinstance(province, dict):
            continue
        _ensure_province(province, key)
        pname = str(province.get("name", ""))
        pressure = _dict(province["religion_pressure"])
        if pname == "Latium":
            province["religion"] = key
            pressure[key] = 110.0
            province["conversion_progress"] = 0.0
        elif pname in CORE_PROVINCES:
            pressure[key] = max(pressure.get(key, 0.0), 45.0)
    info = religion_info(key, ctx)
    _log(player, f"Государственной религией принята: {info['name']}", ctx)
    _screen(f"ПРИНЯТА РЕЛИГИЯ: {info['name'].upper()}", info["icon"], ctx)
    _info(info["desc"], ctx, "CYAN")
    _info("Пять догматов уже действуют. Получено 80 веры; доступны два из четырёх слотов доктрин.", ctx, "GREEN")
    xp = _ctx(ctx).get("add_battlepass_xp")
    if callable(xp):
        try:
            xp(player, 10)
        except Exception:
            pass
    _pause(ctx)


def _doctrine_by_id(player: Any, doctrine_id: str, ctx: dict | None = None) -> dict | None:
    for row in doctrine_catalog(player, ctx):
        if row["id"] == doctrine_id:
            return row
    return None


def _doctrine_requirement_met(player: Any, doctrine: dict, ctx: dict | None = None) -> tuple[bool, str]:
    owned_orders = {row["order"] for row in _owned_institute_rows(player, ctx)}
    minimum = _i(doctrine.get("requires_institute_order", 0), 0)
    if minimum and not any(order >= minimum for order in owned_orders):
        return False, f"нужен институт не ниже №{minimum}"
    required = str(doctrine.get("requires_institute") or "")
    if required and required not in set(getattr(player, "religious_institutes", [])):
        return False, f"нужен институт {required}"
    return True, ""


def choose_doctrine(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    if not player.religion:
        choose_religion(player, ctx)
        return

    while True:
        branches = doctrine_branches(player, ctx)
        selected = _dict(state.get("doctrines"))
        slots = unlocked_doctrine_slots(player, ctx)
        _screen("ДОКТРИНЫ", religion_info(player.religion, ctx)["icon"], ctx, "Выбор направления веры")
        _info(
            f"Слоты: {_ui_bar(len(selected), slots, 14)} {len(selected)}/{slots} • "
            "в каждой ветви действует только одна доктрина.",
            ctx,
            "GOLD",
        )
        _ui_section("ВЕТВИ", "📜", ctx)
        for index, branch in enumerate(branches, 1):
            current = _doctrine_by_id(player, str(selected.get(branch["id"], "")), ctx)
            current_name = str(current.get("name")) if current else "не выбрана"
            color = "GREEN" if current else "WHITE"
            _ui_menu_item(str(index), str(branch["name"]), current_name, ctx, color)
        _ui_menu_item("Q", "Назад", "к религии", ctx, "GRAY")

        value = _choice(
            "\n  Выберите ветвь: ",
            [str(i) for i in range(1, len(branches) + 1)] + ["Q"],
            ctx,
        )
        if value == "Q":
            return

        branch = branches[int(value) - 1]
        choices = [x for x in doctrine_catalog(player, ctx) if x["branch"] == branch["id"]]
        current_id = str(selected.get(branch["id"], "") or "")
        _screen(str(branch["name"]).upper(), "📜", ctx, "Взаимоисключающие доктрины")
        for index, row in enumerate(choices, 1):
            _info(f"[{index}]", ctx, "GOLD")
            _ui_doctrine_detail(player, row, current_id, ctx)
        _ui_menu_item("Q", "Назад", "к ветвям", ctx, "GRAY")

        value = _choice(
            "\n  Выберите доктрину: ",
            [str(i) for i in range(1, len(choices) + 1)] + ["Q"],
            ctx,
        )
        if value == "Q":
            continue

        row = choices[int(value) - 1]
        if str(row.get("id")) == current_id:
            _notify("Эта доктрина уже действует.", ctx, "GOLD")
            _pause(ctx)
            continue

        ok, reason = _doctrine_requirement_met(player, row, ctx)
        if not ok:
            _notify(reason, ctx, "RED")
            _pause(ctx)
            continue

        replacing = bool(current_id)
        if not current_id and len(selected) >= slots:
            _notify("Все доступные слоты заняты. Нужна технология или институт, открывающий новый слот.", ctx, "RED")
            _pause(ctx)
            continue

        turn = _i(getattr(player, "turn", 0), 0)
        changed_turn = _i(_dict(state.get("doctrine_changed_turn")).get(branch["id"], 0), 0)
        cooldown = max(0, 8 - (turn - changed_turn))
        if replacing and cooldown > 0:
            _notify(f"Доктрину этой ветви можно сменить через {cooldown} ход(а).", ctx, "RED")
            _pause(ctx)
            continue

        cost = _i(row["cost"] * (1.5 if replacing else 1.0), row["cost"], 1)
        if _i(getattr(player, "faith", 0), 0) < cost:
            _notify(f"Недостаточно веры: нужно {cost}, есть {getattr(player, 'faith', 0)}.", ctx, "RED")
            _pause(ctx)
            continue

        action = "Сменить" if replacing else "Принять"
        if not _ui_confirm(f"{action} «{row.get('name')}» за {cost} веры?", ctx):
            continue

        player.faith -= cost
        selected[branch["id"]] = row["id"]
        state["doctrines"] = selected
        state.setdefault("doctrine_changed_turn", {})[branch["id"]] = turn
        if replacing:
            state["integrity"] = _clamp(state.get("integrity", 50) - 7, 0, 100)
        _log(player, f"Принята доктрина «{row.get('name')}» ({branch['name']})", ctx)
        _notify(f"Доктрина принята: {row.get('name')}.", ctx, "GREEN")
        _pause(ctx)



def _institute_requirement(inst: dict, selected_doctrines: set[str]) -> tuple[bool, str]:
    required = inst.get("requires_doctrine")
    if isinstance(required, str) and required and required not in selected_doctrines:
        return False, f"нужна доктрина {required}"
    if isinstance(required, list):
        options = {str(x) for x in required}
        if options and not options.intersection(selected_doctrines):
            return False, "сначала выберите доктрину этой ветви"
    return True, ""


def next_institute(player: Any, ctx: dict | None = None) -> dict | None:
    owned = set(str(x) for x in _list(getattr(player, "religious_institutes", [])))
    for row in institute_catalog(player, ctx):
        if row["id"] not in owned:
            return row
    return None


def unlock_next_institute(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    if not player.religion:
        choose_religion(player, ctx)
        return

    row = next_institute(player, ctx)
    if not row:
        _screen("ИНСТИТУТЫ ЗАВЕРШЕНЫ", religion_info(player.religion, ctx)["icon"], ctx)
        _info("Все 30 религиозных институтов уже открыты.", ctx, "GOLD")
        _pause(ctx)
        return

    selected = set(_dict(state.get("doctrines")).values())
    ok, reason = _institute_requirement(row, selected)
    required_tech = str(row.get("requires_tech") or "")
    tech_ok = not required_tech or required_tech in set(_list(getattr(player, "tech_researched", [])))
    cost = _ui_institute_cost(player, row, ctx)

    _screen("СЛЕДУЮЩИЙ ИНСТИТУТ", religion_info(player.religion, ctx)["icon"], ctx)
    _ui_institute_detail(player, row, ctx)
    _info(f"В казне веры: {getattr(player, 'faith', 0)}", ctx, "GOLD")

    if not ok:
        _notify(f"Институт пока закрыт: {reason}.", ctx, "RED")
        _pause(ctx)
        return
    if not tech_ok:
        _notify(f"Требуется технология: {required_tech}.", ctx, "RED")
        _pause(ctx)
        return
    if _i(getattr(player, "faith", 0), 0) < cost:
        _notify(f"Недостаточно веры: нужно {cost}, есть {getattr(player, 'faith', 0)}.", ctx, "RED")
        _pause(ctx)
        return
    if not _ui_confirm(f"Открыть «{row.get('name')}» за {cost} веры?", ctx):
        return

    player.faith -= cost
    player.religious_institutes.append(row["id"])
    player.religious_institutes = list(dict.fromkeys(player.religious_institutes))
    state["integrity"] = _clamp(state.get("integrity", 50) + max(1, row["strength"] / 30), 0, 100)
    _apply_capstone(player, row, ctx)
    _log(player, f"Открыт институт {row['order']:02d}/30 «{row.get('name')}»", ctx)

    _screen(f"ИНСТИТУТ ОТКРЫТ", religion_info(player.religion, ctx)["icon"], ctx)
    _ui_card(
        f"{row['order']:02d}/30 • {row.get('name')}",
        [
            f"Ветвь: {_ui_branch_name(player, str(row.get('branch')), ctx)} • сила: {row.get('strength')}",
            "Эффект: " + effects_text(row.get("effects", {})),
            f"Осталось веры: {getattr(player, 'faith', 0)}",
        ],
        ctx,
        color="GREEN",
        title_color="GOLD",
        badge="ОТКРЫТ",
    )
    if row.get("quote"):
        _info(f"❝ {row.get('quote')} ❞", ctx, "WHITE")
    if row.get("source"):
        _info(f"— {row.get('source')}", ctx, "GRAY")
    xp = _ctx(ctx).get("add_battlepass_xp")
    if callable(xp):
        try:
            xp(player, 6)
        except Exception:
            pass
    _pause(ctx)



def _apply_capstone(player: Any, institute: dict, ctx: dict | None = None) -> None:
    unique = _dict(institute.get("unique_effect"))
    if not institute.get("capstone") and not unique:
        return
    state = ensure_state(player, ctx)
    key = str(unique.get("id") or institute.get("id"))
    if key in state["capstones"]:
        return
    state["capstones"].append(key)
    wave = _f(unique.get("conversion_wave", 0.0), 0.0)
    core_pressure = _f(unique.get("core_pressure", 0.0), 0.0)
    unrest_reduction = _i(unique.get("unrest_reduction", 0), 0)
    for province in _list(getattr(player, "provinces", [])):
        if not isinstance(province, dict):
            continue
        if wave and province.get("religion") != player.religion:
            province["conversion_progress"] = _clamp(province.get("conversion_progress", 0) + wave, 0, 100)
        if core_pressure and str(province.get("name")) in CORE_PROVINCES:
            pressure = _dict(province.get("religion_pressure"))
            pressure[player.religion] = pressure.get(player.religion, 0.0) + core_pressure
        if unrest_reduction:
            province["unrest"] = max(0, _i(province.get("unrest", 0), 0) - max(1, unrest_reduction // 4))
    if unrest_reduction and hasattr(player, "unrest"):
        player.unrest = max(0, _i(getattr(player, "unrest", 0), 0) - unrest_reduction)
    event_name = str(unique.get("event") or "Религиозное преображение державы")
    state["integrity"] = _clamp(state.get("integrity", 50) + 15, 0, 100)
    state["pending"].append({"type": "capstone", "title": event_name, "text": f"Капстоун «{institute.get('name')}» изменил религиозный порядок империи."})


def show_tenets(player: Any, ctx: dict | None = None) -> None:
    ensure_state(player, ctx)
    info = religion_info(player.religion, ctx)
    rows = [row for row in _list(_content(player, ctx).get("tenets")) if isinstance(row, dict)]
    _screen("ДОГМАТЫ ВЕРЫ", info["icon"], ctx, info["name"])
    _info("Пять постоянных оснований государственной религии. Они действуют с момента её принятия.", ctx, "CYAN")
    _ui_rule(ctx)
    for index, row in enumerate(rows, 1):
        _ui_card(
            f"{index}. {row.get('name', 'Догмат')}",
            [
                row.get("desc", ""),
                "Постоянный эффект: " + effects_text(row.get("effects", {})),
            ],
            ctx,
            color="WHITE",
            title_color="GOLD",
            badge="ДЕЙСТВУЕТ",
        )
    _pause(ctx)



def show_institutes(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    rows = institute_catalog(player, ctx)
    owned = set(_list(getattr(player, "religious_institutes", [])))
    selected = set(_dict(state.get("doctrines")).values())
    page_size = 6
    page = 0
    pages = max(1, math.ceil(len(rows) / page_size))

    while True:
        page = max(0, min(pages - 1, page))
        start = page * page_size
        visible = rows[start:start + page_size]
        _screen(
            "РЕЛИГИОЗНЫЕ ИНСТИТУТЫ",
            religion_info(player.religion, ctx)["icon"],
            ctx,
            f"Страница {page + 1}/{pages}",
        )
        _info(
            f"Прогресс: {_ui_bar(len(owned), 30, 24)} {len(owned)}/30 • "
            "✓ открыт  → следующий  ◆ доступен  × закрыт",
            ctx,
            "GOLD",
        )
        next_row = next_institute(player, ctx)
        next_id = str(next_row.get("id")) if isinstance(next_row, dict) else ""

        for local_index, row in enumerate(visible, 1):
            have = str(row["id"]) in owned
            ok, reason = _institute_requirement(row, selected)
            mark = "✓" if have else "→" if str(row["id"]) == next_id and ok else "◆" if ok else "×"
            color = "GREEN" if have else "GOLD" if mark == "→" else "WHITE" if ok else "GRAY"
            branch = _ui_branch_name(player, str(row.get("branch")), ctx)
            cost = _ui_institute_cost(player, row, ctx)
            _info(
                f"[{local_index}] {mark} {row['order']:02d}. {row.get('name')} "
                f"• {branch} • сила {row.get('strength')} • {cost} веры",
                ctx,
                color,
            )
            _info("    " + effects_text(row.get("effects", {})), ctx, "GREEN" if have else "CYAN")
            if not have and not ok:
                _info("    Закрыто: " + reason, ctx, "RED")

        _ui_rule(ctx)
        commands = [str(i) for i in range(1, len(visible) + 1)] + ["Q"]
        if page < pages - 1:
            _ui_menu_item("N", "Следующая страница", f"{page + 2}/{pages}", ctx, "CYAN")
            commands.append("N")
        if page > 0:
            _ui_menu_item("P", "Предыдущая страница", f"{page}/{pages}", ctx, "CYAN")
            commands.append("P")
        _ui_menu_item("Q", "Назад", "к религии", ctx, "GRAY")
        value = _choice("\n  Номер института или команда: ", commands, ctx)
        if value == "Q":
            return
        if value == "N":
            page += 1
            continue
        if value == "P":
            page -= 1
            continue
        row = visible[int(value) - 1]
        _screen("ИНСТИТУТ", religion_info(player.religion, ctx)["icon"], ctx)
        _ui_institute_detail(player, row, ctx)
        _pause(ctx)



def set_policy_menu(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 0), 0)
    current = str(state.get("policy", "encouragement"))
    changed_turn = _i(state.get("policy_changed_turn", 0), 0)
    cooldown = max(0, 5 - (turn - changed_turn))
    keys = list(POLICIES)

    _screen("ПОЛИТИКА ВЕРОИСПОВЕДАНИЯ", "⚖", ctx, POLICIES[current]["name"])
    _info(
        f"Вера: {getattr(player, 'faith', 0)} • "
        + ("смена доступна" if cooldown == 0 else f"смена через {cooldown} ход(а)"),
        ctx,
        "GOLD" if cooldown == 0 else "RED",
    )

    for index, key in enumerate(keys, 1):
        row = POLICIES[key]
        active = key == current
        lines = [
            row["desc"],
            f"Обращение ×{row['conversion_rate']:.2f} • налог ×{row['tax_mult']:.2f} • "
            f"набор ×{row['levy_mult']:.2f} • торговля ×{row['trade_mult']:.2f}",
            f"Дипломатия {row['diplomacy']:+} • изменение целостности {row['integrity']:+} • "
            f"стоимость смены {row['change_cost']} веры",
        ]
        _info(f"[{index}]", ctx, "GOLD")
        _ui_card(
            row["name"],
            lines,
            ctx,
            color="GREEN" if active else "WHITE",
            title_color="GOLD",
            badge="ДЕЙСТВУЕТ" if active else "ВАРИАНТ",
        )

    value = _choice(
        "\n  Новая политика или Q: ",
        [str(i) for i in range(1, len(keys) + 1)] + ["Q"],
        ctx,
    )
    if value == "Q":
        return
    key = keys[int(value) - 1]
    if key == current:
        _notify("Эта политика уже действует.", ctx, "GOLD")
        _pause(ctx)
        return
    if cooldown > 0:
        _notify(f"Политику можно сменить через {cooldown} ход(а).", ctx, "RED")
        _pause(ctx)
        return
    cost = _i(POLICIES[key].get("change_cost", 20), 20)
    if player.faith < cost:
        _notify(f"Нужно {cost} веры, есть {player.faith}.", ctx, "RED")
        _pause(ctx)
        return
    if not _ui_confirm(f"Установить «{POLICIES[key]['name']}» за {cost} веры?", ctx):
        return

    player.faith -= cost
    state["policy"] = key
    state["policy_changed_turn"] = turn
    state["integrity"] = _clamp(
        state.get("integrity", 50) - (5 if key in {"persecution", "mandatory_cult"} else 1),
        0,
        100,
    )
    _log(player, f"Установлена политика «{POLICIES[key]['name']}»", ctx)
    _notify(f"Новая политика: {POLICIES[key]['name']}.", ctx, "GREEN")
    _pause(ctx)



def province_modifiers(player: Any, province: dict, ctx: dict | None = None) -> dict[str, Any]:
    ensure_state(player, ctx)
    official = str(getattr(player, "religion", "") or "")
    local = str(province.get("religion", "") or "")
    policy = POLICIES.get(player.religion_system.get("policy"), POLICIES["encouragement"])
    if not official or local == official:
        return {
            "tax_multiplier": 1.02,
            "levy_multiplier": 1.03,
            "trade_multiplier": 1.00,
            "unrest_per_turn": -0.05,
            "minority": False,
            "label": "официальная религия",
        }
    result = {
        "tax_multiplier": _f(policy["tax_mult"], 1.0),
        "levy_multiplier": _f(policy["levy_mult"], 1.0),
        "trade_multiplier": _f(policy["trade_mult"], 1.0),
        "unrest_per_turn": _f(policy["minority_unrest"], 0.0),
        "minority": True,
        "label": "религиозное меньшинство",
    }
    if player.religion_system.get("policy") == "tolerance":
        special = MINORITY_SPECIALS.get(local, {})
        result["tax_multiplier"] *= _f(special.get("tax_mult", 1.0), 1.0)
        result["levy_multiplier"] *= _f(special.get("levy_mult", 1.0), 1.0)
        result["trade_multiplier"] *= _f(special.get("trade_mult", 1.0), 1.0)
        result["label"] = str(special.get("label", result["label"]))
        tolerance = max(0.0, effect(player, "tolerance_bonus", 0, ctx))
        result["trade_multiplier"] *= 1.0 + min(0.25, tolerance)
    return result


def economy_modifiers(player: Any, ctx: dict | None = None) -> dict[str, Any]:
    ensure_state(player, ctx)
    provinces = [p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)]
    if not provinces or not player.religion:
        return {
            "tax_multiplier": 1.0, "levy_multiplier": 1.0, "trade_multiplier": 1.0,
            "minority_provinces": 0, "details": [],
        }
    weights = []
    rows = []
    for province in provinces:
        weight = max(1.0, _f(province.get("wealth", 1), 1.0))
        mod = province_modifiers(player, province, ctx)
        weights.append(weight)
        rows.append((province, mod, weight))
        province["religion_tax_mult"] = round(mod["tax_multiplier"], 4)
        province["religion_levy_mult"] = round(mod["levy_multiplier"], 4)
        province["religion_trade_mult"] = round(mod["trade_multiplier"], 4)
    total_weight = sum(weights)
    avg = lambda key: sum(row[1][key] * row[2] for row in rows) / max(1.0, total_weight)
    tolerance_trade = 0.0
    if player.religion_system.get("policy") == "tolerance":
        tolerance_trade = max(0.0, _tech_effect(player, "tolerance_trade_bonus", ctx))
    return {
        "tax_multiplier": max(0.55, min(1.25, avg("tax_multiplier"))),
        "levy_multiplier": max(0.50, min(1.25, avg("levy_multiplier") + effect(player, "levy_percent", 0, ctx))),
        "trade_multiplier": max(0.55, min(1.35, avg("trade_multiplier") + max(-0.30, effect(player, "minority_trade_bonus", 0, ctx)) + tolerance_trade)),
        "minority_provinces": sum(1 for _, mod, _ in rows if mod["minority"]),
        "details": [
            {
                "province": str(province.get("name", "")),
                "religion": str(province.get("religion", "")),
                "tax": round(mod["tax_multiplier"], 4),
                "levy": round(mod["levy_multiplier"], 4),
                "trade": round(mod["trade_multiplier"], 4),
                "label": mod["label"],
            }
            for province, mod, _ in rows
        ],
    }


def _building_snapshot(player: Any, ctx: dict | None = None) -> dict:
    city_events = _ctx(ctx).get("CITY_EVENTS")
    if city_events is not None and hasattr(city_events, "building_economy_snapshot"):
        try:
            return _dict(city_events.building_economy_snapshot(player, _ctx(ctx)))
        except Exception:
            return {}
    return {}


def _province_definition_map(ctx: dict | None = None) -> dict[str, dict]:
    return {
        str(row.get("name")): row
        for row in _list(_ctx(ctx).get("PROVINCES_DATA"))
        if isinstance(row, dict) and row.get("name")
    }


def _owned_city_names(player: Any) -> set[str]:
    result: set[str] = set()
    for province in _list(getattr(player, "provinces", [])):
        if not isinstance(province, dict):
            continue
        for city in _list(province.get("cities")):
            if isinstance(city, dict) and city.get("name"):
                result.add(str(city["name"]))
    state = _dict(getattr(player, "city_system", {}))
    for city in _dict(state.get("cities")).values():
        if isinstance(city, dict) and city.get("active") and city.get("name"):
            result.add(str(city["name"]))
    return result


def _update_holy_cities(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    owned_provinces = {str(p.get("name")) for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)}
    owned_cities = _owned_city_names(player)
    records = _dict(state.get("holy_cities"))
    for row in _list(_content(player, ctx).get("holy_cities")):
        if not isinstance(row, dict) or not row.get("id"):
            continue
        hid = str(row["id"])
        controlled = str(row.get("province")) in owned_provinces and str(row.get("city")) in owned_cities
        entry = records.setdefault(hid, {})
        old = bool(entry.get("controlled"))
        entry["controlled"] = controlled
        entry["province"] = row.get("province")
        entry["city"] = row.get("city")
        if controlled != old:
            verb = "установлен контроль над" if controlled else "утрачен контроль над"
            _log(player, f"{verb} святым городом {row.get('city')}", ctx)
            if controlled:
                _discover_origin_relic(player, str(row.get("city")), ctx)
    state["holy_cities"] = records


def _discover_origin_relic(player: Any, city: str, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    for row in _list(_content(player, ctx).get("relics")):
        if not isinstance(row, dict) or str(row.get("origin_city")) != city:
            continue
        rid = str(row.get("id"))
        entry = _dict(state["relics"].get(rid))
        if entry.get("status") in {"owned", "lost"}:
            continue
        entry.update({"status": "owned", "holder": "player", "location": city})
        state["relics"][rid] = entry
        _log(player, f"обретена реликвия «{row.get('name')}» в городе {city}", ctx)
        state["pending"].append({"type": "relic", "title": "Обретение реликвии", "text": f"В городе {city} найдена реликвия «{row.get('name')}»."})
        break


def _update_integrity(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    provinces = [p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)]
    official = str(getattr(player, "religion", "") or "")
    same = sum(1 for p in provinces if p.get("religion") == official)
    minority = max(0, len(provinces) - same)
    holy_bonus = sum(_f(row.get("integrity", 0), 0.0) for row in _controlled_holy_city_rows(player, ctx))
    active_heresies = sum(1 for entry in _dict(state.get("heresies")).values() if _dict(entry).get("status") == "active")
    building = _building_snapshot(player, ctx)
    building_integrity = sum(_f(v) for v in _dict(building.get("religion_integrity")).values())
    policy = POLICIES.get(state.get("policy"), POLICIES["encouragement"])
    target = (
        42.0 + min(20.0, same * 1.4) - min(18.0, minority * 1.1)
        + min(28.0, holy_bonus)
        + min(16.0, building_integrity * 0.22)
        + effect(player, "integrity_flat", 0, ctx)
        - active_heresies * 11
        + _f(policy.get("integrity", 0.0))
        + _tech_effect(player, "holy_city_integrity_bonus", ctx)
    )
    current = _f(state.get("integrity", 50.0), 50.0)
    state["integrity"] = round(_clamp(current + max(-3.0, min(3.0, (target-current)*0.12)), 0.0, 100.0), 3)
    for province in provinces:
        local_target = state["integrity"] + (8 if province.get("religion") == official else -8)
        province["religious_integrity"] = round(
            _clamp(_f(province.get("religious_integrity", 50.0)) + max(-2.0, min(2.0, (local_target - _f(province.get("religious_integrity", 50.0))) * 0.10)), 0, 100),
            3,
        )


def _update_provinces(player: Any, ctx: dict | None = None) -> list[str]:
    state = ensure_state(player, ctx)
    official = str(getattr(player, "religion", "") or "")
    if not official:
        return []
    policy_key = str(state.get("policy", "encouragement"))
    policy = POLICIES.get(policy_key, POLICIES["encouragement"])
    building = _building_snapshot(player, ctx)
    building_pressure = _dict(building.get("religion_pressure"))
    definitions = _province_definition_map(ctx)
    owned = {str(p.get("name")): p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)}
    messages: list[str] = []
    conversion_bonus = effect(player, "conversion_pressure", 0, ctx)
    holy_power = max(
        0.0,
        effect(player, "holy_city_power", 0, ctx)
        + _tech_effect(player, "holy_city_power", ctx),
    )
    tech_pressure = _tech_effect(player, "religion_pressure_bonus", ctx)

    for pname, province in owned.items():
        _ensure_province(province, official)
        pressure = _dict(province.get("religion_pressure"))
        # Старая пропаганда выветривается, но локальная традиция сохраняет инерцию.
        for key in VALID_RELIGIONS:
            pressure[key] = max(0.0, pressure.get(key, 0.0) * 0.975)
        local = str(province.get("religion"))
        pressure[local] = pressure.get(local, 0.0) + 2.2
        official_gain = 2.2
        if pname == "Latium":
            official_gain += 9.0
        elif pname in CORE_PROVINCES:
            official_gain += 4.0
        official_gain += max(-1.0, conversion_bonus * 10.0)
        official_gain += max(0.0, holy_power * 4.0)
        official_gain += max(0.0, tech_pressure * 10.0)

        pbuild = _dict(building_pressure.get(pname))
        official_gain += _f(pbuild.get("official", 0.0), 0.0)
        for religion in VALID_RELIGIONS:
            pressure[religion] = pressure.get(religion, 0.0) + _f(pbuild.get(religion, 0.0), 0.0)

        definition = definitions.get(pname, province)
        for neighbor in _list(_dict(definition).get("neighbors")):
            other = owned.get(str(neighbor))
            if isinstance(other, dict) and other.get("religion") == official:
                official_gain += 0.8

        pressure[official] = pressure.get(official, 0.0) + max(0.2, official_gain)
        province["religion_pressure"] = {key: round(value, 3) for key, value in pressure.items()}

        mod = province_modifiers(player, province, ctx)
        unrest_float = _f(province.get("_religion_unrest_accumulator", 0.0)) + _f(mod.get("unrest_per_turn", 0.0))
        if unrest_float >= 1.0:
            delta = int(unrest_float)
            province["unrest"] = min(10, _i(province.get("unrest", 0), 0) + delta)
            unrest_float -= delta
        elif unrest_float <= -1.0:
            delta = int(abs(unrest_float))
            province["unrest"] = max(0, _i(province.get("unrest", 0), 0) - delta)
            unrest_float += delta
        province["_religion_unrest_accumulator"] = round(unrest_float, 3)

        if local == official:
            province["conversion_progress"] = max(0.0, _f(province.get("conversion_progress", 0.0)) - 2.0)
            continue

        total = sum(max(0.0, value) for value in pressure.values())
        share = pressure.get(official, 0.0) / max(1.0, total)
        resistance = pressure.get(local, 0.0) / max(1.0, total)
        rate = policy["conversion_rate"] * max(0.08, share - resistance * 0.28)
        rate *= 1.0 + max(-0.45, min(0.75, conversion_bonus))
        rate *= 1.0 + max(0.0, tech_pressure)
        if policy_key == "tolerance":
            rate *= 0.70
        progress = _f(province.get("conversion_progress", 0.0)) + max(0.05, rate * 4.5)
        province["conversion_progress"] = round(_clamp(progress, 0, 100), 3)
        if progress >= 100.0:
            old = local
            province["religion"] = official
            province["conversion_progress"] = 8.0
            pressure[official] = max(pressure.get(official, 0.0), 75.0)
            pressure[old] = max(10.0, pressure.get(old, 0.0) * 0.45)
            province["unrest"] = min(10, _i(province.get("unrest", 0), 0) + (1 if policy_key in {"persecution", "mandatory_cult"} else 0))
            message = f"{pname} приняла официальную религию"
            messages.append(message)
            _log(player, message, ctx)
    return messages


def _heresy_risk(player: Any, ctx: dict | None = None) -> float:
    state = ensure_state(player, ctx)
    risk = 0.008
    risk += max(0.0, 55.0 - _f(state.get("integrity", 50.0))) * 0.0011
    risk += max(0.0, effect(player, "heresy_risk", 0, ctx))
    risk -= max(0.0, effect(player, "heresy_resistance", 0, ctx))
    if state.get("policy") in {"persecution", "mandatory_cult"}:
        risk += 0.015
    # Городские события могут временно раскачать проповедников и расколы.
    risk += max(0.0, _f(state.get("event_heresy_pressure", 0.0), 0.0))
    for row in _owned_institute_rows(player, ctx):
        risk += max(0.0, _f(_dict(row.get("risks")).get("heresy", 0.0)))
    return max(0.0, min(0.22, risk))


def _spawn_heresy(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    if any(_dict(x).get("status") == "active" for x in _dict(state.get("heresies")).values()):
        return
    if random.random() >= _heresy_risk(player, ctx):
        return
    candidates = [
        row for row in _list(_content(player, ctx).get("heresies"))
        if isinstance(row, dict)
        and _dict(state["heresies"].get(str(row.get("id")))).get("status") == "dormant"
    ]
    if not candidates:
        return
    row = random.choice(candidates)
    provinces = [p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)]
    hint = str(row.get("province_hint") or "")
    target = next((p for p in provinces if str(p.get("name")) == hint), None)
    if not target and provinces:
        target = max(provinces, key=lambda p: (_i(p.get("unrest", 0)), -_f(p.get("religious_integrity", 50))))
    hid = str(row.get("id"))
    entry = state["heresies"].setdefault(hid, {})
    entry.update({
        "status": "active",
        "strength": random.randint(18, 32),
        "province": target.get("name") if isinstance(target, dict) else None,
        "last_action_turn": _i(getattr(player, "turn", 0), 0),
    })
    if isinstance(target, dict):
        target["unrest"] = min(10, _i(target.get("unrest", 0), 0) + 1)
    state["integrity"] = _clamp(state.get("integrity", 50) - 8, 0, 100)
    _log(player, f"возникло течение «{row.get('name')}» в {entry.get('province') or 'империи'}", ctx)
    state["pending"].append({"type": "heresy", "title": "Религиозный раскол", "text": f"Течение «{row.get('name')}» стало открытой силой."})


def _update_active_heresies(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    catalog = {str(x.get("id")): x for x in _list(_content(player, ctx).get("heresies")) if isinstance(x, dict)}
    provinces = {str(p.get("name")): p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)}
    for hid, entry in _dict(state.get("heresies")).items():
        entry = _dict(entry)
        if entry.get("status") != "active":
            continue
        strength = _i(entry.get("strength", 20), 20, 1, 100)
        drift = random.choice([-1, 0, 0, 1, 1, 2])
        if state.get("policy") == "tolerance":
            drift -= 1
        if state.get("policy") == "mandatory_cult":
            drift += 2
        strength = max(1, min(100, strength + drift))
        entry["strength"] = strength
        province = provinces.get(str(entry.get("province")))
        if isinstance(province, dict) and strength >= 45 and random.random() < 0.12:
            province["unrest"] = min(10, _i(province.get("unrest", 0), 0) + 1)
        if strength >= 75:
            state["pending"].append({
                "type": "heresy_crisis",
                "title": "Кризис вероисповедания",
                "text": f"Течение «{_dict(catalog.get(hid)).get('name', hid)}» стало массовым и угрожает единству державы.",
            })
            entry["strength"] = 62


def heresy_menu(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    catalog = {
        str(x.get("id")): x
        for x in _list(_content(player, ctx).get("heresies"))
        if isinstance(x, dict)
    }

    while True:
        active = [
            (hid, _dict(entry))
            for hid, entry in _dict(state.get("heresies")).items()
            if _dict(entry).get("status") == "active"
        ]
        accepted = str(state.get("accepted_branch") or "")
        _screen("ЕРЕСИ И ТЕЧЕНИЯ", "⚡", ctx, f"Активных: {len(active)}")

        if accepted:
            row = _dict(catalog.get(accepted))
            _ui_card(
                "Официально принятая ветвь",
                [
                    row.get("name", accepted),
                    row.get("desc", ""),
                    "Эффект: " + effects_text(row.get("effects", {})),
                ],
                ctx,
                color="CYAN",
                title_color="GOLD",
                badge="ПРИНЯТА",
            )

        _ui_section("СОСТОЯНИЕ ТЕЧЕНИЙ", "⚠", ctx)
        indexed: list[tuple[str, dict]] = []
        for hid, row in catalog.items():
            entry = _dict(_dict(state.get("heresies")).get(hid))
            status = str(entry.get("status", "dormant"))
            strength = _i(entry.get("strength", 0), 0, 0, 100)
            color = "RED" if status == "active" else "GREEN" if status in {"suppressed", "negotiated"} else "CYAN" if status == "accepted" else "GRAY"
            mark = "⚡" if status == "active" else "✓" if status in {"suppressed", "negotiated"} else "◆" if status == "accepted" else "·"
            _info(
                f"{mark} {row.get('name', hid)} — {_ui_heresy_status(status)} "
                f"{_ui_bar(strength, 100, 12)} {strength:3d}/100",
                ctx,
                color,
            )
            if status == "active":
                indexed.append((hid, entry))
                _info(f"    Центр: {entry.get('province') or 'неизвестно'} • {row.get('desc', '')}", ctx, "CYAN")

        if not indexed:
            _info("\nОткрытых кризисов нет. Дремлющие течения могут возникнуть при низкой целостности и религиозном напряжении.", ctx, "GREEN")
            _pause(ctx)
            return

        _ui_rule(ctx)
        for index, (hid, entry) in enumerate(indexed, 1):
            _ui_menu_item(str(index), str(_dict(catalog.get(hid)).get("name", hid)), f"сила {entry.get('strength', 0)}", ctx, "RED")
        _ui_menu_item("Q", "Назад", "к религии", ctx, "GRAY")
        value = _choice(
            "\n  Выберите активное течение: ",
            [str(i) for i in range(1, len(indexed) + 1)] + ["Q"],
            ctx,
        )
        if value == "Q":
            return

        hid, entry = indexed[int(value) - 1]
        row = _dict(catalog.get(hid))
        strength = _i(entry.get("strength", 20), 20, 0, 100)
        suppress_cost = 45 + strength
        negotiate_gold = 80 + strength * 2
        negotiate_faith = 25

        _screen(str(row.get("name", hid)).upper(), "⚡", ctx, f"Сила {strength}/100")
        _ui_card(
            str(row.get("name", hid)),
            [
                row.get("desc", ""),
                f"Центр: {entry.get('province') or 'неизвестно'}",
                "Возможный эффект при принятии: " + effects_text(row.get("effects", {})),
            ],
            ctx,
            color="RED",
            title_color="GOLD",
            badge="КРИЗИС",
        )
        _ui_menu_item("1", "Подавить", f"{suppress_cost} веры; волнения", ctx, "RED")
        _ui_menu_item("2", "Договориться", f"{negotiate_gold} золота + {negotiate_faith} веры", ctx, "GOLD")
        _ui_menu_item("3", "Принять ветвь", "40 веры; −10 целостности", ctx, "CYAN")
        _ui_menu_item("Q", "Назад", "к списку", ctx, "GRAY")
        action = _choice("\n  Решение: ", ["1", "2", "3", "Q"], ctx)
        if action == "Q":
            continue

        turn = _i(getattr(player, "turn", 0), 0)
        if action == "1":
            if player.faith < suppress_cost:
                _notify(f"Нужно {suppress_cost} веры.", ctx, "RED")
                _pause(ctx)
                continue
            if not _ui_confirm(f"Начать подавление за {suppress_cost} веры?", ctx):
                continue
            player.faith -= suppress_cost
            entry["strength"] = max(0, strength - random.randint(28, 45))
            if entry["strength"] <= 5:
                entry["status"] = "suppressed"
            province = next(
                (
                    p for p in _list(getattr(player, "provinces", []))
                    if isinstance(p, dict) and p.get("name") == entry.get("province")
                ),
                None,
            )
            if isinstance(province, dict):
                province["unrest"] = min(10, _i(province.get("unrest", 0), 0) + 2)
            state["integrity"] = _clamp(state.get("integrity", 50) + 4, 0, 100)
            _log(player, f"подавление течения «{row.get('name')}»", ctx)

        elif action == "2":
            if _i(getattr(player, "gold", 0), 0) < negotiate_gold or player.faith < negotiate_faith:
                _notify(f"Нужно {negotiate_gold} золота и {negotiate_faith} веры.", ctx, "RED")
                _pause(ctx)
                continue
            if not _ui_confirm("Заключить соглашение с течением?", ctx):
                continue
            player.gold -= negotiate_gold
            player.faith -= negotiate_faith
            entry["status"] = "negotiated"
            entry["strength"] = max(10, strength // 2)
            state["integrity"] = _clamp(state.get("integrity", 50) + 2, 0, 100)
            _log(player, f"соглашение с течением «{row.get('name')}»", ctx)

        else:
            if state.get("accepted_branch") and state.get("accepted_branch") != hid:
                _notify("Уже принята другая религиозная ветвь.", ctx, "RED")
                _pause(ctx)
                continue
            if player.faith < 40:
                _notify("Нужно 40 веры.", ctx, "RED")
                _pause(ctx)
                continue
            if not _ui_confirm(f"Принять «{row.get('name')}» как официальную ветвь?", ctx):
                continue
            player.faith -= 40
            entry["status"] = "accepted"
            state["accepted_branch"] = hid
            state["integrity"] = _clamp(state.get("integrity", 50) - 10, 0, 100)
            _log(player, f"официально принята ветвь «{row.get('name')}»", ctx)

        entry["last_action_turn"] = turn
        state["heresies"][hid] = entry
        _notify("Решение исполнено.", ctx, "GREEN")
        _pause(ctx)



def show_provinces(player: Any, ctx: dict | None = None) -> None:
    ensure_state(player, ctx)
    provinces = [p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)]
    mods = economy_modifiers(player, ctx)
    page_size = 7
    page = 0
    pages = max(1, math.ceil(len(provinces) / page_size))

    while True:
        official = str(getattr(player, "religion", "") or "")
        counts = {key: 0 for key in VALID_RELIGIONS}
        for province in provinces:
            local = str(province.get("religion", ""))
            if local in counts:
                counts[local] += 1
        minority = sum(v for k, v in counts.items() if k != official)
        low_integrity = sum(1 for p in provinces if _f(p.get("religious_integrity", 50)) < 35)
        high_conversion = sum(
            1 for p in provinces
            if p.get("religion") != official and _f(p.get("conversion_progress", 0)) >= 70
        )

        _screen("РЕЛИГИОЗНАЯ КАРТА", "🗺", ctx, f"Страница {page + 1}/{pages}")
        _ui_section("СВОДКА ИМПЕРИИ", "◈", ctx)
        total = max(1, len(provinces))
        for key in VALID_RELIGIONS:
            value = counts.get(key, 0)
            _info(
                f"{_ui_religion_label(key, ctx):<18} {_ui_bar(value, total, 18)} "
                f"{value}/{len(provinces)}",
                ctx,
                "GREEN" if key == official else "CYAN",
            )
        _info(
            f"Меньшинства: {minority} • низкая целостность: {low_integrity} • "
            f"обращение ≥70%: {high_conversion}",
            ctx,
            "RED" if low_integrity else "GOLD",
        )
        _info(
            f"Экономика: налоги ×{mods['tax_multiplier']:.3f} • набор ×{mods['levy_multiplier']:.3f} • "
            f"торговля ×{mods['trade_multiplier']:.3f}",
            ctx,
            "CYAN",
        )

        _ui_section("ПРОВИНЦИИ", "⌖", ctx)
        start = page * page_size
        visible = provinces[start:start + page_size]
        for index, province in enumerate(visible, 1):
            pressure = _dict(province.get("religion_pressure"))
            total_pressure = sum(max(0.0, _f(v)) for v in pressure.values()) or 1.0
            official_share = 100.0 * max(0.0, _f(pressure.get(official, 0))) / total_pressure
            local = str(province.get("religion", "") or "—")
            local_label = _ui_religion_label(local, ctx) if local in VALID_RELIGIONS else local
            integrity = _f(province.get("religious_integrity", 50), 50)
            conversion = _f(province.get("conversion_progress", 0), 0)
            warning = " ⚠" if integrity < 35 else ""
            color = "GREEN" if local == official else "GOLD"
            _info(
                f"[{index}] {province.get('name')} — {local_label}{warning}",
                ctx,
                color,
            )
            _info(
                f"    Официальная вера: {_ui_bar(official_share, 100, 14)} {official_share:5.1f}% • "
                f"обращение {conversion:5.1f}% • целостность {integrity:5.1f}",
                ctx,
                "RED" if integrity < 35 else "CYAN",
            )

        commands = [str(i) for i in range(1, len(visible) + 1)] + ["Q"]
        if page < pages - 1:
            commands.append("N")
            _ui_menu_item("N", "Следующая страница", f"{page + 2}/{pages}", ctx, "CYAN")
        if page > 0:
            commands.append("P")
            _ui_menu_item("P", "Предыдущая страница", f"{page}/{pages}", ctx, "CYAN")
        _ui_menu_item("Q", "Назад", "к религии", ctx, "GRAY")

        value = _choice("\n  Провинция или команда: ", commands, ctx)
        if value == "Q":
            return
        if value == "N":
            page += 1
            continue
        if value == "P":
            page -= 1
            continue

        province = visible[int(value) - 1]
        pressure = _dict(province.get("religion_pressure"))
        _screen(str(province.get("name", "ПРОВИНЦИЯ")).upper(), "⌖", ctx)
        local = str(province.get("religion", "") or "—")
        _ui_card(
            "Религиозное состояние",
            [
                f"Господствующая вера: {_ui_religion_label(local, ctx) if local in VALID_RELIGIONS else local}",
                f"Прогресс обращения: {_f(province.get('conversion_progress', 0)):.1f}%",
                f"Религиозная целостность: {_f(province.get('religious_integrity', 50)):.1f}/100",
                f"Волнения: {_i(province.get('unrest', 0), 0)}",
            ],
            ctx,
            color="WHITE",
            title_color="GOLD",
        )
        _ui_section("ДАВЛЕНИЕ ВЕР", "◌", ctx)
        total_pressure = sum(max(0.0, _f(v)) for v in pressure.values()) or 1.0
        for key in VALID_RELIGIONS:
            share = 100.0 * max(0.0, _f(pressure.get(key, 0))) / total_pressure
            _info(
                f"{_ui_religion_label(key, ctx):<18} {_ui_bar(share, 100, 20)} {share:5.1f}%",
                ctx,
                "GREEN" if key == player.religion else "CYAN",
            )
        pmods = province_modifiers(player, province, ctx)
        _ui_section("МОДИФИКАТОРЫ", "¤", ctx)
        _info(
            f"Налоги ×{pmods['tax_multiplier']:.3f} • набор ×{pmods['levy_multiplier']:.3f} • "
            f"торговля ×{pmods['trade_multiplier']:.3f}",
            ctx,
            "GOLD",
        )
        _pause(ctx)



def _holy_city_row_by_id(player: Any, hid: str, ctx: dict | None = None) -> dict:
    for row in _list(_content(player, ctx).get("holy_cities")):
        if isinstance(row, dict) and str(row.get("id")) == hid:
            return row
    return {}


def _ui_show_holy_cities(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    _update_holy_cities(player, ctx)
    rows = [x for x in _list(_content(player, ctx).get("holy_cities")) if isinstance(x, dict)]
    controlled_count = 0
    _screen("СВЯТЫЕ ГОРОДА", "🏛", ctx)
    for row in rows:
        status = _dict(state["holy_cities"].get(str(row.get("id"))))
        controlled = bool(status.get("controlled"))
        controlled_count += int(controlled)
        _ui_card(
            f"{row.get('city')} • {row.get('province')}",
            [
                row.get("title", ""),
                f"Целостность: +{row.get('integrity', 0)}",
                "Эффект: " + effects_text(row.get("effects", {})),
            ],
            ctx,
            color="GREEN" if controlled else "GRAY",
            title_color="GOLD",
            badge="ПОД КОНТРОЛЕМ" if controlled else "НЕ КОНТРОЛИРУЕТСЯ",
        )
    for row in _list(state.get("dynamic_holy_cities")):
        if isinstance(row, dict):
            _ui_card(
                f"{row.get('city')} • {row.get('province')}",
                [
                    row.get("title", "Освящённый центр державы"),
                    "Эффект: " + effects_text(row.get("effects", {})),
                ],
                ctx,
                color="CYAN",
                title_color="GOLD",
                badge="ОСВЯЩЕНО",
            )
    _info(
        f"Под контролем: {controlled_count}/{len(rows)} • динамических мест: "
        f"{len(_list(state.get('dynamic_holy_cities')))}/{MAX_DYNAMIC_HOLY_CITIES}",
        ctx,
        "GOLD",
    )
    _pause(ctx)


def _ui_show_relics(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    rows = [x for x in _list(_content(player, ctx).get("relics")) if isinstance(x, dict)]
    _screen("РЕЛИКВИИ", "✦", ctx, f"В державе: {len(_owned_relic_rows(player, ctx))}")
    for row in rows:
        entry = _dict(state["relics"].get(str(row.get("id"))))
        status = str(entry.get("status", "hidden"))
        location = entry.get("location") or "неизвестно"
        _ui_card(
            str(row.get("name", "Реликвия")),
            [
                f"Состояние: {_ui_relic_status(status)}",
                f"Место: {location}",
                "Эффект: " + effects_text(row.get("effects", {})),
            ],
            ctx,
            color="GREEN" if status == "owned" else "GRAY",
            title_color="GOLD",
            badge=status.upper(),
        )
    _pause(ctx)


def _ui_move_relic(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    relic_rows = [x for x in _list(_content(player, ctx).get("relics")) if isinstance(x, dict)]
    owned = [
        row for row in relic_rows
        if _dict(state["relics"].get(str(row.get("id")))).get("status") == "owned"
    ]
    if not owned:
        _notify("У вас нет переносимых реликвий.", ctx, "RED")
        _pause(ctx)
        return
    _screen("ПЕРЕНОС РЕЛИКВИИ", "✦", ctx, "Стоимость: 20 веры")
    for index, row in enumerate(owned, 1):
        entry = _dict(state["relics"].get(str(row.get("id"))))
        _ui_menu_item(str(index), str(row.get("name")), str(entry.get("location") or "неизвестно"), ctx, "GOLD")
    value = _choice(
        "\n  Реликвия: ",
        [str(i) for i in range(1, len(owned) + 1)] + ["Q"],
        ctx,
    )
    if value == "Q":
        return
    row = owned[int(value) - 1]
    provinces = [p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)]
    _screen(str(row.get("name", "РЕЛИКВИЯ")).upper(), "✦", ctx, "Выберите новое место")
    for index, province in enumerate(provinces, 1):
        _ui_menu_item(
            str(index),
            str(province.get("name")),
            f"целостность {_f(province.get('religious_integrity', 50)):.0f}",
            ctx,
            "CYAN",
        )
    value = _choice(
        "\n  Провинция: ",
        [str(i) for i in range(1, len(provinces) + 1)] + ["Q"],
        ctx,
    )
    if value == "Q":
        return
    if player.faith < 20:
        _notify("Перенос требует 20 веры.", ctx, "RED")
        _pause(ctx)
        return
    province = provinces[int(value) - 1]
    if not _ui_confirm(f"Перенести реликвию в {province.get('name')} за 20 веры?", ctx):
        return
    player.faith -= 20
    entry = state["relics"][str(row.get("id"))]
    entry["location"] = str(province.get("name"))
    entry["last_moved_turn"] = _i(getattr(player, "turn", 0), 0)
    _log(player, f"реликвия «{row.get('name')}» перенесена в {province.get('name')}", ctx)
    _notify("Реликвия перенесена.", ctx, "GREEN")
    _pause(ctx)


def holy_relic_menu(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    while True:
        _update_holy_cities(player, ctx)
        holy_total = len([x for x in _list(_content(player, ctx).get("holy_cities")) if isinstance(x, dict)])
        holy_owned = len(_controlled_holy_city_rows(player, ctx))
        relic_total = len([x for x in _list(_content(player, ctx).get("relics")) if isinstance(x, dict)])
        relic_owned = len(_owned_relic_rows(player, ctx))
        dynamic_count = len(_list(state.get("dynamic_holy_cities")))

        _screen("СВЯТЫЕ МЕСТА И РЕЛИКВИИ", "🏛", ctx)
        _info(
            f"Святые города: {_ui_bar(holy_owned, max(1, holy_total), 14)} {holy_owned}/{holy_total} • "
            f"реликвии: {_ui_bar(relic_owned, max(1, relic_total), 14)} {relic_owned}/{relic_total}",
            ctx,
            "GOLD",
        )
        _info(f"Освящённые центры державы: {dynamic_count}/{MAX_DYNAMIC_HOLY_CITIES}", ctx, "CYAN")
        _ui_section("ДЕЙСТВИЯ", "✦", ctx)
        _ui_menu_item("1", "Святые города", "контроль и эффекты", ctx, "GREEN")
        _ui_menu_item("2", "Реликвии", "состояние и местонахождение", ctx, "GOLD")
        _ui_menu_item("3", "Перенести реликвию", "20 веры", ctx, "CYAN")
        _ui_menu_item("4", "Освятить новый центр", "150 веры", ctx, "PURPLE")
        _ui_menu_item("Q", "Назад", "к религии", ctx, "GRAY")
        value = _choice("\n  Выбор: ", ["1", "2", "3", "4", "Q"], ctx)
        if value == "Q":
            return
        if value == "1":
            _ui_show_holy_cities(player, ctx)
        elif value == "2":
            _ui_show_relics(player, ctx)
        elif value == "3":
            _ui_move_relic(player, ctx)
        else:
            _consecrate_dynamic_holy_city(player, ctx)



def _consecrate_dynamic_holy_city(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    if len(_list(state.get("dynamic_holy_cities"))) >= MAX_DYNAMIC_HOLY_CITIES:
        _notify("Достигнут предел динамических святых мест.", ctx, "RED"); _pause(ctx); return
    candidates = [
        p for p in _list(getattr(player, "provinces", []))
        if isinstance(p, dict)
        and p.get("religion") == player.religion
        and _f(p.get("religious_integrity", 0)) >= 70
        and str(p.get("name")) not in {str(x.get("province")) for x in _list(state.get("dynamic_holy_cities")) if isinstance(x, dict)}
    ]
    if not candidates:
        _notify("Нужна провинция официальной веры с целостностью не ниже 70.", ctx, "RED"); _pause(ctx); return
    for index, province in enumerate(candidates, 1):
        _info(f"{index}. {province.get('name')} — целостность {province.get('religious_integrity'):.0f}", ctx, "CYAN")
    value = _choice("\n  Освятить: ", [str(i) for i in range(1, len(candidates)+1)] + ["Q"], ctx)
    if value == "Q":
        return
    if player.faith < 150:
        _notify("Освящение стоит 150 веры.", ctx, "RED"); _pause(ctx); return
    player.faith -= 150
    province = candidates[int(value)-1]
    cities = [x for x in _list(province.get("cities")) if isinstance(x, dict)]
    city = str(cities[0].get("name")) if cities else str(province.get("name"))
    row = {
        "id": f"dynamic_{re.sub(r'[^a-z0-9]+','_',str(province.get('name')).lower())}_{_i(getattr(player,'turn',0),0)}",
        "city": city,
        "province": province.get("name"),
        "title": "Освящённый центр державы",
        "integrity": 6,
        "effects": {"faith_flat": 3, "conversion_pressure": 0.03},
        "dynamic": True,
    }
    state["dynamic_holy_cities"].append(row)
    _log(player, f"{city} освящён как новое святое место", ctx)
    _pause(ctx)


def _relic_risk(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    security = max(
        0.0,
        effect(player, "relic_security", 0, ctx)
        + _f(state.get("event_relic_security", 0.0), 0.0),
    )
    province_map = {str(p.get("name")): p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)}
    relic_catalog = {str(x.get("id")): x for x in _list(_content(player, ctx).get("relics")) if isinstance(x, dict)}
    for rid, entry in _dict(state.get("relics")).items():
        entry = _dict(entry)
        if entry.get("status") != "owned":
            continue
        location = str(entry.get("location") or "")
        province = province_map.get(location)
        if province is None and location not in _owned_city_names(player):
            entry["status"] = "lost"
            entry["holder"] = "unknown"
            _log(player, f"утрачена реликвия «{_dict(relic_catalog.get(rid)).get('name',rid)}»", ctx)
            continue
        unrest = _i(province.get("unrest", 0), 0) if isinstance(province, dict) else 0
        chance = max(0.0, (unrest - 6) * 0.012 - security)
        if chance > 0 and random.random() < chance:
            entry["status"] = "lost"
            entry["holder"] = "thieves"
            _log(player, f"похищена реликвия «{_dict(relic_catalog.get(rid)).get('name',rid)}»", ctx)
            state["pending"].append({"type": "relic_lost", "title": "Похищение реликвии", "text": f"Реликвия «{_dict(relic_catalog.get(rid)).get('name',rid)}» исчезла во время беспорядков."})


def maybe_event(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    if not player.religion:
        return
    if state["pending"]:
        event = state["pending"].pop(0)
        _screen(str(event.get("title", "РЕЛИГИОЗНОЕ СОБЫТИЕ")).upper(), religion_info(player.religion, ctx)["icon"], ctx)
        _info(event.get("text", ""), ctx, "CYAN")
        _pause(ctx)
        return
    turn = _i(getattr(player, "turn", 0), 0)
    if turn == _i(state.get("last_event_turn", 0), 0):
        return
    base = _f(_ctx(ctx).get("SETTINGS", {}).get("religion_event_chance", 0.08), 0.08)
    chance = min(0.30, max(0.0, base + max(0.0, effect(player, "event_good_chance", 0, ctx))))
    if random.random() >= chance:
        return
    state["last_event_turn"] = turn
    legacy_events = _dict(_ctx(ctx).get("RELIGIOUS_EVENTS")).get(player.religion)
    if isinstance(legacy_events, list) and legacy_events:
        title, quote, reward = random.choice(legacy_events)
        apply_reward(player, _dict(reward), ctx)
        _screen("РЕЛИГИОЗНОЕ СОБЫТИЕ", religion_info(player.religion, ctx)["icon"], ctx)
        _info(title, ctx, "GOLD")
        _info(f"❝ {quote} ❞", ctx, "WHITE")
        _info("Итог: " + reward_text(reward), ctx, "GREEN")
        _log(player, f"{title}: {quote}", ctx)
        xp = _ctx(ctx).get("add_battlepass_xp")
        if callable(xp):
            try:
                xp(player, 4)
            except Exception:
                pass


def apply_reward(player: Any, reward: dict, ctx: dict | None = None) -> None:
    for key, attr in (("gold", "gold"), ("grain", "grain"), ("faith", "faith"), ("glory", "glory")):
        if key in reward:
            setattr(player, attr, max(0, _i(getattr(player, attr, 0), 0) + _i(reward.get(key), 0)))
    for key, attr in (("people", "people_rep"), ("senate", "senate_rep"), ("morale", "morale")):
        if key in reward:
            setattr(player, attr, max(0, min(100, _i(getattr(player, attr, 0), 0) + _i(reward.get(key), 0))))
    if reward.get("unrest"):
        player.unrest = max(0, min(100, _i(getattr(player, "unrest", 0), 0) + _i(reward.get("unrest"), 0)))
    if reward.get("metals_iron") and isinstance(getattr(player, "metals", None), dict):
        player.metals["iron"] = _i(player.metals.get("iron", 0), 0) + _i(reward.get("metals_iron"), 0)


def reward_text(reward: dict) -> str:
    return ", ".join(f"{key} {value:+}" for key, value in _dict(reward).items()) or "особое последствие"


def maybe_spawn_sacred_figure(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    if not player.religion:
        return
    turn = _i(getattr(player, "turn", 0), 0)
    if turn == _i(state.get("last_figure_turn", 0), 0):
        return
    figures = [str(x) for x in _list(_content(player, ctx).get("sacred_figures"))]
    available = [x for x in figures if x not in player.sacred_generals]
    if not available:
        return
    chance = _f(_ctx(ctx).get("SETTINGS", {}).get("sacred_general_chance", 0.06), 0.06)
    chance += max(0.0, effect(player, "sacred_general_chance_bonus", 0, ctx))
    if random.random() >= min(0.22, chance):
        return
    state["last_figure_turn"] = turn
    name = random.choice(available)
    player.sacred_generals.append(name)
    _screen("СВЯЩЕННАЯ ФИГУРА", religion_info(player.religion, ctx)["icon"], ctx)
    _info(name, ctx, "GOLD")
    _info("Постоянный эффект: " + effects_text(_content(player, ctx).get("sacred_effects", {})), ctx, "GREEN")
    _log(player, f"к державе присоединилась священная фигура: {name}", ctx)
    xp = _ctx(ctx).get("add_battlepass_xp")
    if callable(xp):
        try:
            xp(player, 12)
        except Exception:
            pass
    _pause(ctx)


def show_figures(player: Any, ctx: dict | None = None) -> None:
    ensure_state(player, ctx)
    rows = [str(x) for x in _list(_content(player, ctx).get("sacred_figures"))]
    owned = set(_list(getattr(player, "sacred_generals", [])))
    _screen("СВЯЩЕННЫЕ ФИГУРЫ", religion_info(player.religion, ctx)["icon"], ctx)
    _info(
        f"Получено: {_ui_bar(len(owned), max(1, len(rows)), 22)} {len(owned)}/{len(rows)}",
        ctx,
        "GOLD",
    )
    _ui_card(
        "Постоянный эффект каждой фигуры",
        [effects_text(_content(player, ctx).get("sacred_effects", {}))],
        ctx,
        color="CYAN",
        title_color="GOLD",
    )
    _ui_section("ЛИЧНОСТИ", "✦", ctx)
    for name in rows:
        _info(
            f"{'✓' if name in owned else '·'} {name}",
            ctx,
            "GREEN" if name in owned else "GRAY",
        )
    _pause(ctx)



def show_log(player: Any, ctx: dict | None = None) -> None:
    state = ensure_state(player, ctx)
    rows = _list(state.get("log")) or ["Событий ещё не было."]
    page_size = 12
    pages = max(1, math.ceil(len(rows) / page_size))
    page = pages - 1

    while True:
        page = max(0, min(pages - 1, page))
        start = page * page_size
        visible = rows[start:start + page_size]
        _screen("ЛЕТОПИСЬ ВЕРЫ", "📜", ctx, f"Страница {page + 1}/{pages}")
        for line in visible:
            _info("• " + str(line), ctx, "CYAN")
        commands = ["Q"]
        if page < pages - 1:
            commands.append("N")
            _ui_menu_item("N", "Более новые записи", f"{page + 2}/{pages}", ctx, "CYAN")
        if page > 0:
            commands.append("P")
            _ui_menu_item("P", "Более старые записи", f"{page}/{pages}", ctx, "CYAN")
        _ui_menu_item("Q", "Назад", "к религии", ctx, "GRAY")
        value = _choice("\n  Команда: ", commands, ctx)
        if value == "Q":
            return
        if value == "N":
            page += 1
        elif value == "P":
            page -= 1



def open_menu(player: Any, ctx: dict | None = None) -> None:
    ensure_state(player, ctx)
    while True:
        if not player.religion:
            _screen("RELIGIO IMPERII", "🕯", ctx, "Государственная вера")
            _ui_card(
                "Религия ещё не принята",
                [
                    "Выбор определит постоянные догматы, доктрины, институты, святые места, реликвии и возможные ереси.",
                    "После принятия государственной веры изменить её обычным решением нельзя.",
                ],
                ctx,
                color="CYAN",
                title_color="GOLD",
            )
            _ui_menu_item("1", "Выбрать религию", "начать религиозный путь", ctx, "GOLD")
            _ui_menu_item("Q", "Назад", "к управлению державой", ctx, "GRAY")
            value = _choice("\n  Выбор: ", ["1", "Q"], ctx)
            if value == "1":
                choose_religion(player, ctx)
            else:
                return
            continue

        state = ensure_state(player, ctx)
        info = religion_info(player.religion, ctx)
        counts = _ui_religion_counts(player, ctx)
        next_row = next_institute(player, ctx)
        mods = economy_modifiers(player, ctx)
        integrity = _f(state.get("integrity", 50), 50)
        slots = unlocked_doctrine_slots(player, ctx)
        policy_key = str(state.get("policy", "encouragement"))
        policy_name = POLICIES.get(policy_key, POLICIES["encouragement"])["name"]
        accepted = _accepted_heresy_row(player, ctx)

        _screen("RELIGIO IMPERII", info["icon"], ctx, info["name"])
        _ui_section("СОСТОЯНИЕ ВЕРЫ", "◈", ctx)
        _info(
            f"Вера: {getattr(player, 'faith', 0):,} • "
            f"Целостность: {_ui_bar(integrity, 100, 20)} {integrity:5.1f}/100",
            ctx,
            "GOLD" if integrity >= 50 else "RED",
        )
        _info(
            f"Политика: {policy_name} • доктрины {counts['doctrines']}/{slots} • "
            f"институты {counts['institutes']}/30",
            ctx,
            "CYAN",
        )
        _info(
            f"Святые города {counts['holy']} • реликвии {counts['relics']} • "
            f"священные фигуры {counts['figures']} • активные ереси {counts['heresies']}",
            ctx,
            "RED" if counts["heresies"] else "GREEN",
        )
        if isinstance(accepted, dict):
            _info(f"Принятая ветвь: {accepted.get('name', state.get('accepted_branch'))}", ctx, "PURPLE")

        _ui_section("ВЛИЯНИЕ НА ДЕРЖАВУ", "¤", ctx)
        _info(
            f"Налоги ×{mods['tax_multiplier']:.3f} • набор ×{mods['levy_multiplier']:.3f} • "
            f"торговля ×{mods['trade_multiplier']:.3f} • меньшинства {mods['minority_provinces']}",
            ctx,
            "CYAN",
        )

        if next_row:
            selected = set(_dict(state.get("doctrines")).values())
            ok, reason = _institute_requirement(next_row, selected)
            cost = _ui_institute_cost(player, next_row, ctx)
            _ui_section("СЛЕДУЮЩИЙ ШАГ", "→", ctx)
            _info(
                f"{next_row.get('order'):02d}/30 {next_row.get('name')} • {cost} веры"
                + ("" if ok else f" • закрыто: {reason}"),
                ctx,
                "GREEN" if ok and getattr(player, "faith", 0) >= cost else "RED",
            )

        if integrity < 35 or counts["heresies"]:
            _ui_section("ПРЕДУПРЕЖДЕНИЯ", "⚠", ctx, "RED")
            if integrity < 35:
                _info("Низкая религиозная целостность повышает риск раскола.", ctx, "RED")
            if counts["heresies"]:
                _info(f"В державе действует еретических течений: {counts['heresies']}.", ctx, "RED")

        _ui_section("УЧЕНИЕ И ИНСТИТУТЫ", "📜", ctx)
        _ui_menu_item("1", "Пять догматов", "постоянные основы", ctx, "GOLD")
        _ui_menu_item("2", "Доктрины", f"{counts['doctrines']}/{slots} слотов", ctx, "CYAN")
        _ui_menu_item("3", "Институты", f"{counts['institutes']}/30 открыто", ctx, "WHITE")
        _ui_menu_item("4", "Открыть следующий институт", "проверка и подтверждение", ctx, "GREEN")

        _ui_section("ИМПЕРИЯ И ВЕРА", "🏛", ctx)
        _ui_menu_item("5", "Религиозная карта", f"{mods['minority_provinces']} провинций меньшинств", ctx, "CYAN")
        _ui_menu_item("6", "Политика вероисповедания", policy_name, ctx, "GOLD")
        _ui_menu_item("7", "Святые места и реликвии", f"{counts['holy']} / {counts['relics']}", ctx, "PURPLE")
        _ui_menu_item("8", "Ереси и течения", f"{counts['heresies']} активных", ctx, "RED" if counts["heresies"] else "GREEN")

        _ui_section("ЛИЧНОСТИ И ПАМЯТЬ", "✦", ctx)
        _ui_menu_item("9", "Священные фигуры", str(counts["figures"]), ctx, "GOLD")
        _ui_menu_item("0", "Летопись веры", f"{len(_list(state.get('log')))} записей", ctx, "CYAN")
        _ui_menu_item("Q", "Назад", "к управлению державой", ctx, "GRAY")

        value = _choice(
            "\n  Выбор: ",
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "Q"],
            ctx,
        )
        if value == "Q":
            return
        {
            "1": show_tenets,
            "2": choose_doctrine,
            "3": show_institutes,
            "4": unlock_next_institute,
            "5": show_provinces,
            "6": set_policy_menu,
            "7": holy_relic_menu,
            "8": heresy_menu,
            "9": show_figures,
            "0": show_log,
        }[value](player, ctx)



def process_turn(player: Any, ctx: dict | None = None, interactive: bool = False) -> dict[str, Any]:
    state = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 0), 0)
    if not player.religion:
        return {"processed": False, "reason": "no_religion"}
    if turn <= _i(state.get("last_turn_processed", 0), 0):
        return {"processed": False, "reason": "already_processed"}

    _update_holy_cities(player, ctx)
    conversions = _update_provinces(player, ctx)
    _update_integrity(player, ctx)
    _spawn_heresy(player, ctx)
    _update_active_heresies(player, ctx)
    _relic_risk(player, ctx)
    mods = economy_modifiers(player, ctx)
    # Модификаторы от городских событий краткосрочны и постепенно затухают.
    state["event_heresy_pressure"] = round(max(0.0, _f(state.get("event_heresy_pressure", 0.0)) * 0.50), 4)
    state["event_relic_security"] = round(max(0.0, _f(state.get("event_relic_security", 0.0)) * 0.65), 4)
    state["last_turn_processed"] = turn

    # Базовый доход веры уже начисляет основное ядро. Здесь добавляется только
    # плоский доход новой религиозной системы, чтобы не удваивать старую формулу.
    faith_gain = max(0, effect(player, "faith_flat", 0, ctx))
    faith_gain = int(round(faith_gain))
    player.faith = max(0, _i(getattr(player, "faith", 0), 0) + faith_gain)

    if hasattr(player, "unrest"):
        reduction = max(0, effect(player, "unrest_reduction", 0, ctx))
        if reduction and turn % 3 == 0:
            player.unrest = max(0, _i(getattr(player, "unrest", 0), 0) - max(1, reduction // 6))
    if hasattr(player, "people_rep"):
        player.people_rep = max(0, min(100, _i(getattr(player, "people_rep", 50), 50) + effect(player, "people_rep_flat", 0, ctx) // 10))
    if hasattr(player, "senate_rep"):
        player.senate_rep = max(0, min(100, _i(getattr(player, "senate_rep", 50), 50) + effect(player, "senate_rep_flat", 0, ctx) // 10))

    if conversions:
        state["pending"].append({
            "type": "conversion",
            "title": "Обращение провинции",
            "text": "; ".join(conversions),
        })
    if interactive and state["pending"]:
        maybe_event(player, ctx)
    return {
        "processed": True,
        "faith_gain": faith_gain,
        "integrity": state["integrity"],
        "conversions": conversions,
        "economy": mods,
        "pending": len(state["pending"]),
    }


def audit_content(ctx: dict | None = None) -> list[str]:
    errors: list[str] = []
    catalog = _religion_catalog(ctx)
    for key in VALID_RELIGIONS:
        row = _dict(catalog.get(key))
        tenets = _list(row.get("tenets"))
        institutes = _list(row.get("institutes"))
        doctrines = _list(row.get("doctrines"))
        heresies = _list(row.get("heresies"))
        if len(tenets) != 5:
            errors.append(f"{key}: ожидалось 5 догматов, получено {len(tenets)}")
        if len(institutes) != 30:
            errors.append(f"{key}: ожидалось 30 институтов, получено {len(institutes)}")
        declared_branches = _list(row.get("doctrine_branches"))
        if len(declared_branches) != 4:
            errors.append(f"{key}: ожидалось 4 описания ветвей доктрин, получено {len(declared_branches)}")
        branches = {str(x.get("branch")) for x in doctrines if isinstance(x, dict)}
        if len(branches) != 4:
            errors.append(f"{key}: ожидалось 4 ветви доктрин, получено {len(branches)}")
        for branch in branches:
            count = sum(1 for x in doctrines if isinstance(x, dict) and str(x.get("branch")) == branch)
            if count not in {2, 3}:
                errors.append(f"{key}/{branch}: ожидалось 2–3 доктрины, получено {count}")
        if len(heresies) != 5:
            errors.append(f"{key}: ожидалось 5 ересей, получено {len(heresies)}")
        if not _list(row.get("holy_cities")):
            errors.append(f"{key}: нет святых городов")
        if not _list(row.get("relics")):
            errors.append(f"{key}: нет реликвий")
    return errors
