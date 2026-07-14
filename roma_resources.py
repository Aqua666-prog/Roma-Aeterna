#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Opes Imperii — автоматическая ресурсная экономика Roma Aeterna.

Модуль не импортирует основной файл игры. Он работает через ``player`` и
словарь ``context``. Игрок не нажимает кнопку добычи каждый ход: провинции
производят ресурсы автоматически, хозяйство автоматически расходует их,
нехватка по возможности закрывается закупками, а раз в несколько ходов
появляются только стратегические решения — вложения и торговые предложения.

Денежные и товарные величины абстрактны и предназначены для игрового баланса,
а не для буквального пересчёта античных тонн или денариев.
"""

from __future__ import annotations

import hashlib
import math
import random
from typing import Any

RESOURCE_ECONOMY_VERSION = 3

CATEGORY_ORDER = (
    "food",
    "materials",
    "metals",
    "military",
    "craft",
    "luxury",
    "special",
)

CATEGORY_LABELS = {
    "food": "Продовольствие",
    "materials": "Сырьё и строительство",
    "metals": "Металлы",
    "military": "Военные ресурсы",
    "craft": "Ремесленное сырьё",
    "luxury": "Роскошь",
    "special": "Особые товары",
}

# base_price — ориентир для автоматической закупки и торговых предложений;
# reserve — желательный запас в условных единицах; sector — связь с Roma Economica.
RESOURCE_CATALOG: dict[str, dict[str, Any]] = {
    "wheat":       {"name": "Пшеница",       "icon": "🌾", "category": "food",      "base_price": 8,  "reserve": 35, "sector": "agriculture"},
    "wine":        {"name": "Вино",          "icon": "🍷", "category": "food",      "base_price": 12, "reserve": 16, "sector": "agriculture"},
    "fish":        {"name": "Рыба",          "icon": "🐟", "category": "food",      "base_price": 9,  "reserve": 16, "sector": "agriculture"},
    "livestock":   {"name": "Скот",          "icon": "🐂", "category": "food",      "base_price": 13, "reserve": 18, "sector": "agriculture"},
    "olive_oil":   {"name": "Оливковое масло","icon": "🫒", "category": "food",      "base_price": 14, "reserve": 14, "sector": "agriculture"},

    "timber":      {"name": "Древесина",     "icon": "🪵", "category": "materials", "base_price": 10, "reserve": 30, "sector": "mining"},
    "stone":       {"name": "Камень",        "icon": "🪨", "category": "materials", "base_price": 9,  "reserve": 30, "sector": "mining"},
    "marble":      {"name": "Мрамор",        "icon": "🏛", "category": "materials", "base_price": 20, "reserve": 12, "sector": "mining"},
    "salt":        {"name": "Соль",          "icon": "🧂", "category": "materials", "base_price": 11, "reserve": 18, "sector": "mining"},

    "iron":        {"name": "Железо",        "icon": "⚒", "category": "metals",    "base_price": 18, "reserve": 28, "sector": "mining"},
    "steel":       {"name": "Сталь",         "icon": "🗡", "category": "metals",    "base_price": 30, "reserve": 18, "sector": "manufacturing", "derived": True},
    "copper":      {"name": "Медь",          "icon": "🔶", "category": "metals",    "base_price": 17, "reserve": 20, "sector": "mining"},
    "bronze":      {"name": "Бронза",        "icon": "🛡", "category": "metals",    "base_price": 27, "reserve": 14, "sector": "manufacturing", "derived": True},
    "tin":         {"name": "Олово",         "icon": "◻", "category": "metals",    "base_price": 19, "reserve": 12, "sector": "mining"},
    "lead":        {"name": "Свинец",        "icon": "⚫", "category": "metals",    "base_price": 15, "reserve": 12, "sector": "mining"},
    "silver":      {"name": "Серебро",       "icon": "🥈", "category": "metals",    "base_price": 42, "reserve": 8,  "sector": "mining"},
    "gold":        {"name": "Золото",        "icon": "🥇", "category": "metals",    "base_price": 65, "reserve": 5,  "sector": "mining"},

    "horses":      {"name": "Лошади",        "icon": "🐎", "category": "military",  "base_price": 24, "reserve": 18, "sector": "agriculture"},

    "wool":        {"name": "Шерсть",        "icon": "🧶", "category": "craft",     "base_price": 12, "reserve": 16, "sector": "agriculture"},
    "linen":       {"name": "Лён",           "icon": "🧵", "category": "craft",     "base_price": 14, "reserve": 14, "sector": "agriculture"},
    "leather":     {"name": "Кожа",          "icon": "🥾", "category": "craft",     "base_price": 18, "reserve": 18, "sector": "manufacturing", "derived": True},

    "purple":      {"name": "Пурпур",        "icon": "💜", "category": "luxury",    "base_price": 85,  "reserve": 3, "sector": "manufacturing"},
    "incense":     {"name": "Благовония",    "icon": "🌿", "category": "luxury",    "base_price": 52,  "reserve": 5, "sector": "commerce"},
    "spices":      {"name": "Специи",        "icon": "🌶", "category": "luxury",    "base_price": 58,  "reserve": 5, "sector": "commerce"},
    "amber":       {"name": "Янтарь",        "icon": "🟠", "category": "luxury",    "base_price": 48,  "reserve": 4, "sector": "commerce"},
    "pearls":      {"name": "Жемчуг",        "icon": "⚪", "category": "luxury",    "base_price": 72,  "reserve": 3, "sector": "commerce"},
    "diamonds":    {"name": "Алмазы",        "icon": "💎", "category": "luxury",    "base_price": 125, "reserve": 2, "sector": "commerce"},
    "rubies":      {"name": "Рубины",        "icon": "🔴", "category": "luxury",    "base_price": 105, "reserve": 2, "sector": "commerce"},
    "sapphires":   {"name": "Сапфиры",       "icon": "🔵", "category": "luxury",    "base_price": 100, "reserve": 2, "sector": "commerce"},
    "emeralds":    {"name": "Изумруды",      "icon": "🟢", "category": "luxury",    "base_price": 110, "reserve": 2, "sector": "commerce"},

    "papyrus":     {"name": "Папирус",       "icon": "📜", "category": "special",   "base_price": 24, "reserve": 12, "sector": "manufacturing"},
}

# Фиксированный доход за владение одной единицей редкого ресурса.
# Он начисляется напрямую в казну после ресурсного тика и не зависит от
# инфляции, налоговой ставки или бюджетного сглаживания Roma Economica.
# Поэтому 5 рубинов всегда дают ровно 5 × 20 = 100 золота за ход.
RARE_RESOURCE_GOLD_PER_TURN: dict[str, int] = {
    "silver": 4,
    "gold": 8,
    "purple": 18,
    "incense": 10,
    "spices": 12,
    "amber": 8,
    "pearls": 15,
    "diamonds": 25,
    "rubies": 20,
    "sapphires": 18,
    "emeralds": 20,
}

for _rare_key, _rare_income in RARE_RESOURCE_GOLD_PER_TURN.items():
    if _rare_key in RESOURCE_CATALOG:
        RESOURCE_CATALOG[_rare_key]["gold_per_turn"] = _rare_income


# Базовый выпуск провинции в условных единицах за ход. Значения намеренно
# небольшие: богатство создаётся комбинацией многих провинций и инвестиций.
PROVINCE_DEPOSITS: dict[str, dict[str, float]] = {
    "Latium": {"wheat": 2.2, "wine": 1.2, "stone": 0.8, "salt": 0.6},
    "Campania": {"wheat": 2.5, "wine": 2.0, "olive_oil": 1.4, "fish": 0.8},
    "Etruria": {"copper": 1.5, "iron": 0.9, "wine": 1.0, "clay": 0.0},
    "Umbria": {"wheat": 1.3, "livestock": 1.3, "timber": 0.9},
    "Samnium": {"iron": 1.2, "livestock": 1.1, "wool": 0.8},
    "Apulia": {"wheat": 1.8, "olive_oil": 1.2, "wool": 1.0},
    "Bruttium": {"timber": 1.6, "fish": 1.1, "gold": 0.18},
    "Liguria": {"timber": 1.5, "marble": 0.7, "fish": 0.8},
    "Gallia": {"wheat": 1.5, "wine": 1.7, "iron": 1.1, "timber": 1.3},
    "Gallia Narbonensis": {"wine": 2.0, "wheat": 1.3, "salt": 0.9, "fish": 0.7},
    "Aquitania": {"wine": 1.5, "livestock": 1.5, "timber": 1.0},
    "Belgica": {"wheat": 1.4, "iron": 1.0, "livestock": 1.2},
    "Germania Inferior": {"timber": 1.8, "iron": 1.1, "amber": 0.25},
    "Germania Superior": {"timber": 1.6, "iron": 1.4, "salt": 0.8},
    "Magna Germania": {"timber": 2.0, "amber": 0.45, "livestock": 1.4, "horses": 0.8},
    "Hispania": {"silver": 0.9, "iron": 1.5, "copper": 1.1, "gold": 0.28},
    "Lusitania": {"gold": 0.32, "tin": 0.8, "livestock": 1.0},
    "Baetica": {"silver": 0.7, "olive_oil": 2.0, "wine": 1.5, "wheat": 1.2},
    "Britannia": {"tin": 1.7, "lead": 1.4, "iron": 0.8, "wool": 1.2},
    "Caledonia": {"tin": 0.8, "lead": 0.8, "wool": 1.0, "fish": 1.0},
    "Hibernia": {"livestock": 1.5, "wool": 1.3, "fish": 1.0},
    "Sicilia": {"wheat": 3.2, "wine": 1.0, "fish": 1.0, "salt": 0.7},
    "Sardinia et Corsica": {"silver": 0.45, "lead": 0.9, "salt": 1.0, "fish": 0.9},
    "Carthago": {"wheat": 2.4, "olive_oil": 2.0, "purple": 0.28, "fish": 0.8},
    "Numidia": {"wheat": 1.2, "livestock": 1.7, "horses": 1.5, "salt": 0.7},
    "Mauretania": {"horses": 1.6, "livestock": 1.4, "purple": 0.18, "fish": 0.8},
    "Cyrenaica": {"wheat": 1.5, "olive_oil": 1.2, "horses": 0.8, "incense": 0.16},
    "Aegyptus": {"wheat": 4.0, "papyrus": 2.2, "linen": 1.7, "gold": 0.22},
    "Macedonia": {"iron": 1.5, "gold": 0.16, "timber": 1.1, "horses": 0.8},
    "Achaea": {"marble": 1.8, "olive_oil": 1.2, "wine": 1.2, "silver": 0.25},
    "Epirus": {"horses": 1.2, "timber": 1.2, "livestock": 1.0},
    "Illyricum": {"timber": 1.7, "iron": 1.3, "silver": 0.32},
    "Thracia": {"wheat": 1.6, "horses": 1.5, "gold": 0.14, "wine": 0.8},
    "Dacia": {"gold": 0.75, "silver": 0.45, "iron": 1.4, "timber": 1.2},
    "Asia Minor": {"silver": 0.7, "marble": 1.5, "wine": 1.2, "sapphires": 0.08},
    "Bithynia": {"timber": 1.5, "marble": 0.9, "wheat": 1.1},
    "Galatia": {"livestock": 1.6, "wool": 1.4, "horses": 1.0},
    "Cappadocia": {"horses": 1.3, "iron": 0.8, "silver": 0.25, "salt": 0.7},
    "Pontus": {"wheat": 1.4, "fish": 1.5, "timber": 1.2, "iron": 0.8},
    "Cilicia": {"timber": 1.1, "purple": 0.25, "spices": 0.18, "fish": 1.0},
    "Syria": {"wheat": 1.2, "wine": 0.9, "spices": 0.42, "incense": 0.34},
    "Judaea": {"olive_oil": 1.2, "wine": 0.8, "incense": 0.28, "salt": 0.9},
    "Armenia": {"horses": 1.5, "copper": 1.2, "iron": 1.0, "rubies": 0.07},
    "Mesopotamia": {"wheat": 2.2, "linen": 1.1, "spices": 0.22, "pearls": 0.08},
}

# Специализации внешних партнёров. Ключи проверяются как подстроки имени/ID.
PARTNER_SPECIALIZATIONS: dict[str, list[str]] = {
    "egypt": ["wheat", "papyrus", "linen"],
    "aegypt": ["wheat", "papyrus", "linen"],
    "carth": ["olive_oil", "purple", "wheat"],
    "phoen": ["purple", "timber", "pearls"],
    "syria": ["spices", "incense", "wine"],
    "parth": ["horses", "spices", "rubies"],
    "armenia": ["horses", "copper", "rubies"],
    "greece": ["marble", "wine", "olive_oil"],
    "maced": ["iron", "timber", "horses"],
    "hisp": ["silver", "iron", "gold"],
    "brit": ["tin", "lead", "wool"],
    "arab": ["incense", "spices", "pearls"],
    "india": ["spices", "diamonds", "rubies", "sapphires", "emeralds"],
    "gaul": ["iron", "wine", "livestock"],
    "germ": ["timber", "amber", "livestock"],
    "daci": ["gold", "silver", "iron"],
    "getae": ["copper", "horses", "livestock"],
    "sarmat": ["horses", "livestock", "leather"],
    "suebi": ["iron", "timber", "amber"],
    "pict": ["wool", "fish", "lead"],
    "iceni": ["tin", "horses", "wool"],
    "arverni": ["iron", "wine", "livestock"],
    "aedui": ["wine", "wheat", "iron"],
    "belgae": ["iron", "livestock", "wool"],
    "marcomanni": ["horses", "timber", "amber"],
}

LEGACY_METAL_MAP = {
    "iron": "iron",
    "copper": "copper",
    "silver": "silver",
    "gold_ore": "gold",
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _stable_seed(player: Any, purpose: str, turn: int | None = None) -> int:
    token = "|".join((
        str(getattr(player, "name", "Roma")),
        str(getattr(player, "faction", "")),
        str(turn if turn is not None else getattr(player, "turn", 1)),
        str(purpose),
        str(RESOURCE_ECONOMY_VERSION),
    ))
    return int.from_bytes(hashlib.sha256(token.encode("utf-8")).digest()[:8], "big")


def _rng(player: Any, purpose: str, turn: int | None = None) -> random.Random:
    return random.Random(_stable_seed(player, purpose, turn))


def _blank_stockpiles() -> dict[str, float]:
    return {key: 0.0 for key in RESOURCE_CATALOG}


def _initial_stockpiles(context: dict[str, Any]) -> dict[str, float]:
    stock = _blank_stockpiles()
    stock.update({
        "wheat": 18.0,
        "wine": 5.0,
        "fish": 4.0,
        "livestock": 5.0,
        "olive_oil": 4.0,
        "timber": 10.0,
        "stone": 10.0,
        "iron": 5.0,
        "copper": 3.0,
        "steel": 2.0,
        "bronze": 2.0,
        "horses": 3.0,
        "wool": 4.0,
        "linen": 3.0,
        "leather": 4.0,
        "papyrus": 3.0,
    })
    for province in context.get("provinces", []) if isinstance(context.get("provinces"), list) else []:
        if not isinstance(province, dict):
            continue
        for resource, base in PROVINCE_DEPOSITS.get(str(province.get("name", "")), {}).items():
            if resource in stock:
                stock[resource] += max(0.0, base) * 1.5
    return stock


def ensure_state(player: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context if isinstance(context, dict) else {}
    state = getattr(player, "resource_economy", None)
    if not isinstance(state, dict):
        state = {}
        setattr(player, "resource_economy", state)

    defaults: dict[str, Any] = {
        "version": RESOURCE_ECONOMY_VERSION,
        "stockpiles": _initial_stockpiles(context),
        "production_levels": {key: 1.0 for key in RESOURCE_CATALOG},
        "invested_gold": {key: 0.0 for key in RESOURCE_CATALOG},
        "market_prices": {key: float(spec["base_price"]) for key, spec in RESOURCE_CATALOG.items()},
        "reserve_targets": {key: float(spec["reserve"]) for key, spec in RESOURCE_CATALOG.items()},
        "auto_buy_shortages": True,
        "auto_purchase_budget_share": 0.08,
        "auto_process_materials": True,
        "pending_investment_offer": None,
        "pending_trade_offer": None,
        "next_investment_turn": max(4, int(getattr(player, "turn", 1)) + 3),
        "next_trade_turn": max(3, int(getattr(player, "turn", 1)) + 2),
        "last_flow": {},
        "history": [],
        "offer_history": [],
        "total_auto_purchase_cost": 0.0,
        "total_trade_gold": 0.0,
        "total_investment": 0.0,
        "last_rare_resource_income": 0,
        "total_rare_resource_income": 0.0,
        "last_processed_turn": 0,
    }
    for key, value in defaults.items():
        if key not in state or state[key] is None:
            state[key] = value

    stock = state.get("stockpiles") if isinstance(state.get("stockpiles"), dict) else {}
    levels = state.get("production_levels") if isinstance(state.get("production_levels"), dict) else {}
    invested = state.get("invested_gold") if isinstance(state.get("invested_gold"), dict) else {}
    prices = state.get("market_prices") if isinstance(state.get("market_prices"), dict) else {}
    reserves = state.get("reserve_targets") if isinstance(state.get("reserve_targets"), dict) else {}
    for key, spec in RESOURCE_CATALOG.items():
        stock[key] = clamp(finite(stock.get(key, defaults["stockpiles"].get(key, 0.0))), 0.0, 10_000_000.0)
        levels[key] = clamp(finite(levels.get(key, 1.0), 1.0), 0.25, 25.0)
        invested[key] = clamp(finite(invested.get(key, 0.0)), 0.0, 1_000_000_000.0)
        prices[key] = clamp(finite(prices.get(key, spec["base_price"]), spec["base_price"]), spec["base_price"] * 0.35, spec["base_price"] * 6.0)
        reserves[key] = clamp(finite(reserves.get(key, spec["reserve"]), spec["reserve"]), 0.0, 100_000.0)
    state["stockpiles"] = stock
    state["production_levels"] = levels
    state["invested_gold"] = invested
    state["market_prices"] = prices
    state["reserve_targets"] = reserves
    state["version"] = RESOURCE_ECONOMY_VERSION
    state["auto_buy_shortages"] = bool(state.get("auto_buy_shortages", True))
    state["auto_purchase_budget_share"] = clamp(finite(state.get("auto_purchase_budget_share", 0.08), 0.08), 0.0, 0.35)
    state["auto_process_materials"] = bool(state.get("auto_process_materials", True))
    if not isinstance(state.get("history"), list):
        state["history"] = []
    if not isinstance(state.get("offer_history"), list):
        state["offer_history"] = []
    if not isinstance(state.get("last_flow"), dict):
        state["last_flow"] = {}

    _pull_legacy_metals(player, state)
    _push_legacy_metals(player, state)
    return state


def _pull_legacy_metals(player: Any, state: dict[str, Any]) -> None:
    metals = getattr(player, "metals", None)
    if not isinstance(metals, dict):
        return
    stock = state["stockpiles"]
    # Между ресурсными тиками старые меню могут списывать или начислять металл.
    # Поэтому текущее значение legacy-кошелька считается источником истины.
    for old_key, new_key in LEGACY_METAL_MAP.items():
        if old_key in metals:
            stock[new_key] = clamp(finite(metals.get(old_key, stock[new_key])), 0.0, 10_000_000.0)


def _push_legacy_metals(player: Any, state: dict[str, Any]) -> None:
    metals = getattr(player, "metals", None)
    if not isinstance(metals, dict):
        metals = {}
        setattr(player, "metals", metals)
    stock = state["stockpiles"]
    for old_key, new_key in LEGACY_METAL_MAP.items():
        metals[old_key] = max(0, int(round(stock.get(new_key, 0.0))))


def _province_efficiency(province: dict[str, Any], context: dict[str, Any]) -> float:
    wealth = clamp(finite(province.get("wealth", 2.0), 2.0), 0.0, 99.0)
    romanization = clamp(finite(province.get("romanization", 35.0), 35.0), 0.0, 100.0)
    unrest = clamp(finite(province.get("unrest", 2.0), 2.0), 0.0, 10.0)
    war_damage = clamp(finite(province.get("war_damage", 0.0), 0.0), 0.0, 1.0)
    occupation = clamp(finite(province.get("occupation_progress", 1.0), 1.0), 0.0, 1.0)
    infrastructure = clamp(finite(context.get("infrastructure", 35.0), 35.0), 0.0, 500.0)
    efficiency = 0.62 + 0.020 * wealth + 0.0020 * romanization + 0.0012 * infrastructure
    efficiency *= clamp(1.0 - 0.055 * unrest, 0.35, 1.0)
    efficiency *= clamp(1.0 - 0.70 * war_damage, 0.20, 1.0)
    efficiency *= 0.55 + 0.45 * occupation
    return clamp(efficiency, 0.18, 2.4)


def _sector_factor(resource: str, context: dict[str, Any]) -> float:
    spec = RESOURCE_CATALOG[resource]
    sector = spec.get("sector", "commerce")
    productivity = context.get("sectoral_productivity", {}) if isinstance(context.get("sectoral_productivity"), dict) else {}
    output = context.get("sectoral_output", {}) if isinstance(context.get("sectoral_output"), dict) else {}
    prod = clamp(finite(productivity.get(sector, 1.0), 1.0), 0.25, 8.0)
    output_factor = 1.0 + 0.025 * math.log1p(max(0.0, finite(output.get(sector, 0.0))))
    return clamp((0.72 + 0.28 * prod) * output_factor, 0.45, 2.2)


def _primary_production(player: Any, context: dict[str, Any], state: dict[str, Any]) -> dict[str, float]:
    production = {key: 0.0 for key in RESOURCE_CATALOG}
    rng = _rng(player, "production")
    global_unrest = clamp(finite(context.get("effective_unrest", 0.0)), 0.0, 100.0)
    confidence = clamp(finite(context.get("confidence", 0.70), 0.70), 0.02, 0.99)
    global_factor = clamp(1.10 - 0.0050 * global_unrest + 0.18 * confidence, 0.40, 1.25)

    provinces = context.get("provinces", []) if isinstance(context.get("provinces"), list) else []
    for province in provinces:
        if not isinstance(province, dict):
            continue
        deposits = PROVINCE_DEPOSITS.get(str(province.get("name", "")), {})
        if not deposits:
            continue
        efficiency = _province_efficiency(province, context) * global_factor
        local_variation = 0.94 + 0.12 * rng.random()
        for resource, base in deposits.items():
            if resource not in RESOURCE_CATALOG or RESOURCE_CATALOG[resource].get("derived"):
                continue
            level = state["production_levels"].get(resource, 1.0)
            investment_factor = 1.0 + 0.16 * math.log1p(max(0.0, level - 1.0))
            yield_amount = base * efficiency * local_variation * investment_factor * _sector_factor(resource, context)
            production[resource] += max(0.0, yield_amount)

    # Opera Publica: permanent municipal buildings contribute directly to the
    # empire-wide resource flow.  The context is assembled by roma_aeterna, so
    # this module remains independent from the city module.
    building_output = context.get("building_resource_output", {})
    if isinstance(building_output, dict):
        for resource, amount in building_output.items():
            if resource in production:
                production[resource] += max(0.0, finite(amount))
    return production


def _demand_snapshot(context: dict[str, Any]) -> dict[str, float]:
    population = max(80.0, finite(context.get("population", 500.0), 500.0))
    pop = clamp(population / 500.0, 0.3, 40.0)
    legions = max(0, int(context.get("legion_count", 0)))
    aux = max(0, int(context.get("aux_count", 0)))
    fleet = max(0, int(context.get("fleet_size", 0)))
    wonders = max(0, int(context.get("wonder_count", 0)))
    construction = max(0.0, finite((context.get("sectoral_output") or {}).get("construction", 0.0) if isinstance(context.get("sectoral_output"), dict) else 0.0))
    manufacturing = max(0.0, finite((context.get("sectoral_output") or {}).get("manufacturing", 0.0) if isinstance(context.get("sectoral_output"), dict) else 0.0))
    science = max(0.0, finite(context.get("science_points", 0.0)))
    senate = clamp(finite(context.get("senate_rep", 50.0), 50.0), 0.0, 100.0)
    wealth = max(0.0, finite(context.get("average_wealth", 2.0), 2.0))

    demand = {key: 0.0 for key in RESOURCE_CATALOG}
    demand.update({
        "wheat": 2.5 * pop + 0.75 * legions + 0.20 * aux,
        "wine": 0.42 * pop + 0.08 * senate / 10.0,
        "fish": 0.48 * pop,
        "livestock": 0.36 * pop + 0.08 * legions,
        "olive_oil": 0.44 * pop,
        "salt": 0.32 * pop + 0.05 * legions,
        "timber": 0.34 * fleet + 0.0030 * construction + 0.08 * legions,
        "stone": 0.0038 * construction + 0.10 * wonders,
        "marble": 0.0017 * construction + 0.12 * wonders,
        "iron": 0.22 * legions + 0.08 * aux + 0.14 * fleet + 0.0010 * manufacturing,
        "steel": 0.30 * legions + 0.06 * aux + 0.10 * fleet,
        "copper": 0.08 * legions + 0.09 * fleet,
        "bronze": 0.11 * legions + 0.12 * fleet,
        "tin": 0.03 * fleet + 0.02 * legions,
        "lead": 0.06 * construction + 0.04 * fleet,
        "silver": 0.04 * pop + 0.015 * senate,
        "gold": 0.012 * senate + 0.02 * wonders,
        "horses": 0.12 * legions + 0.18 * aux,
        "wool": 0.24 * pop + 0.08 * legions,
        "linen": 0.18 * pop + 0.07 * fleet + 0.03 * legions,
        "leather": 0.18 * legions + 0.08 * aux + 0.08 * pop,
        "papyrus": 0.12 * pop + 0.0015 * science + 0.015 * senate,
    })
    luxury_scale = clamp(0.025 * pop + 0.010 * wealth + 0.002 * senate, 0.02, 3.0)
    for key in ("purple", "incense", "spices", "amber", "pearls", "diamonds", "rubies", "sapphires", "emeralds"):
        demand[key] = luxury_scale * (0.22 if key in {"purple", "incense", "spices"} else 0.08)

    # Workshops, mints, shipyards and other buildings can consume inputs every
    # turn.  Their demand is settled by the same stockpile/auto-buy machinery
    # as military and civilian demand, therefore shortages remain visible.
    building_input = context.get("building_resource_input", {})
    if isinstance(building_input, dict):
        for resource, amount in building_input.items():
            if resource in demand:
                demand[resource] += max(0.0, finite(amount))
    return {key: max(0.0, value) for key, value in demand.items()}


def _process_derived_goods(context: dict[str, Any], state: dict[str, Any], demand: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    if not state.get("auto_process_materials", True):
        return {}, {}
    stock = state["stockpiles"]
    produced: dict[str, float] = {}
    used: dict[str, float] = {}
    manufacturing_factor = _sector_factor("steel", context)

    def convert(output: str, inputs: dict[str, float], capacity: float) -> None:
        target = max(0.0, demand.get(output, 0.0) * 2.0 + state["reserve_targets"].get(output, 0.0) - stock.get(output, 0.0))
        amount = min(max(0.0, capacity), target)
        for resource, ratio in inputs.items():
            amount = min(amount, stock.get(resource, 0.0) / max(1e-9, ratio))
        if amount <= 1e-6:
            return
        for resource, ratio in inputs.items():
            consumed = amount * ratio
            stock[resource] = max(0.0, stock.get(resource, 0.0) - consumed)
            used[resource] = used.get(resource, 0.0) + consumed
        stock[output] = stock.get(output, 0.0) + amount
        produced[output] = produced.get(output, 0.0) + amount

    capacity = 1.5 + 0.055 * max(0.0, finite((context.get("sectoral_output") or {}).get("manufacturing", 0.0) if isinstance(context.get("sectoral_output"), dict) else 0.0))
    capacity *= manufacturing_factor
    convert("steel", {"iron": 0.78, "timber": 0.18}, capacity * 0.48)
    convert("bronze", {"copper": 0.76, "tin": 0.24}, capacity * 0.30)
    convert("leather", {"livestock": 0.55, "salt": 0.08}, capacity * 0.35)
    return produced, used


def _update_market_prices(player: Any, state: dict[str, Any], demand: dict[str, float], production: dict[str, float]) -> None:
    rng = _rng(player, "prices")
    for key, spec in RESOURCE_CATALOG.items():
        stock = state["stockpiles"].get(key, 0.0)
        reserve = max(1.0, state["reserve_targets"].get(key, spec["reserve"]))
        pressure = demand.get(key, 0.0) / max(0.35, production.get(key, 0.0) + 0.12 * stock)
        scarcity = clamp(0.72 + 0.42 * math.sqrt(max(0.0, pressure)) + max(0.0, reserve - stock) / reserve * 0.18, 0.55, 3.6)
        target = spec["base_price"] * scarcity
        drift = 0.985 + 0.030 * rng.random()
        old = state["market_prices"].get(key, spec["base_price"])
        state["market_prices"][key] = clamp(0.78 * old + 0.22 * target * drift, spec["base_price"] * 0.35, spec["base_price"] * 6.0)


def _consume_and_autobuy(player: Any, context: dict[str, Any], state: dict[str, Any], demand: dict[str, float]) -> tuple[dict[str, float], dict[str, float], float]:
    stock = state["stockpiles"]
    consumed: dict[str, float] = {}
    shortages: dict[str, float] = {}
    purchase_cost = 0.0
    price_level = clamp(finite(context.get("price_level", 1.0), 1.0), 0.20, 100.0)
    game_multiplier = clamp(finite(context.get("price_multiplier", 1.0), 1.0), 0.20, 20.0)

    essential_auto_buy = {"salt", "timber", "iron", "steel", "leather", "horses", "papyrus"}
    initial_gold = max(0.0, finite(getattr(player, "gold", 0.0)))
    purchase_budget = min(
        initial_gold * state.get("auto_purchase_budget_share", 0.08),
        (85.0 + 12.0 * max(0, int(context.get("legion_count", 0)))) * game_multiplier,
    )

    # Сначала жизненно важные позиции, затем всё остальное без автоматической закупки.
    ordered_keys = sorted(demand, key=lambda k: (k not in essential_auto_buy, -demand.get(k, 0.0)))
    for key in ordered_keys:
        required = max(0.0, demand.get(key, 0.0))
        available = max(0.0, stock.get(key, 0.0))
        direct = min(available, required)
        stock[key] = available - direct
        consumed[key] = direct
        missing = required - direct
        if missing <= 1e-6:
            continue
        if state.get("auto_buy_shortages", True) and key in essential_auto_buy and purchase_cost < purchase_budget:
            unit_price = state["market_prices"].get(key, RESOURCE_CATALOG[key]["base_price"])
            # Оптовая закупка дешевле розницы, но ограничена годовым бюджетом снабжения.
            unit_price *= price_level * game_multiplier * 0.42
            budget_left = max(0.0, purchase_budget - purchase_cost)
            affordable = min(
                max(0.0, finite(getattr(player, "gold", 0.0))) / max(0.01, unit_price),
                budget_left / max(0.01, unit_price),
            )
            bought = min(missing, affordable)
            if bought > 1e-6:
                cost = bought * unit_price
                player.gold = max(0, int(round(finite(getattr(player, "gold", 0.0)) - cost)))
                purchase_cost += cost
                consumed[key] += bought
                missing -= bought
        if missing > 1e-6:
            shortages[key] = missing
    state["total_auto_purchase_cost"] = finite(state.get("total_auto_purchase_cost", 0.0)) + purchase_cost
    return consumed, shortages, purchase_cost


def _apply_shortage_effects(player: Any, shortages: dict[str, float], demand: dict[str, float]) -> list[str]:
    if not shortages:
        return []
    # Пшеница и соль — действительно жизненно важные позиции. Рыба, мясо,
    # масло и предметы роскоши улучшают рацион, но их отсутствие не должно
    # автоматически превращать каждый ход в восстание.
    food_keys = {"salt"}
    military_keys = {"iron", "steel", "bronze", "leather", "horses", "timber"}
    admin_keys = {"papyrus"}

    def severity(keys: set[str]) -> float:
        ratios = [shortages[k] / max(0.1, demand.get(k, 0.1)) for k in keys if k in shortages]
        return clamp(sum(ratios), 0.0, 3.0)

    notes: list[str] = []
    food = severity(food_keys)
    military = severity(military_keys)
    admin = severity(admin_keys)
    if food > 0.15:
        delta = max(1, int(round(1.6 * food)))
        if hasattr(player, "unrest"):
            player.unrest = min(100, int(getattr(player, "unrest", 0)) + delta)
        if hasattr(player, "people_rep") and food > 0.7:
            player.people_rep = max(0, int(getattr(player, "people_rep", 50)) - 1)
        notes.append(f"нехватка продовольственных товаров: волнения +{delta}")
    if military > 1.15:
        delta = max(1, int(round(0.75 * military)))
        if hasattr(player, "morale"):
            player.morale = max(0, int(getattr(player, "morale", 70)) - delta)
        notes.append(f"системный дефицит военных материалов: боевой дух -{delta}")
    if admin > 0 and isinstance(getattr(player, "economy", None), dict):
        player.economy["tax_capacity"] = clamp(finite(player.economy.get("tax_capacity", 0.48)) - 0.002 * admin, 0.05, 0.98)
        notes.append("нехватка папируса затрудняет управление")
    return notes


def _resource_score_for_investment(key: str, state: dict[str, Any], demand: dict[str, float], production: dict[str, float], context: dict[str, Any]) -> float:
    stock = state["stockpiles"].get(key, 0.0)
    reserve = max(1.0, state["reserve_targets"].get(key, RESOURCE_CATALOG[key]["reserve"]))
    scarcity = max(0.0, reserve - stock) / reserve
    demand_pressure = demand.get(key, 0.0) / max(0.25, production.get(key, 0.0) + 0.15)
    deposit_capacity = 0.0
    for province in context.get("provinces", []) if isinstance(context.get("provinces"), list) else []:
        if isinstance(province, dict):
            deposit_capacity += PROVINCE_DEPOSITS.get(str(province.get("name", "")), {}).get(key, 0.0)
    if deposit_capacity <= 0 and not RESOURCE_CATALOG[key].get("derived"):
        return -100.0
    level_penalty = 0.22 * max(0.0, state["production_levels"].get(key, 1.0) - 1.0)
    return 1.5 * scarcity + 0.35 * min(5.0, demand_pressure) + 0.10 * deposit_capacity - level_penalty


def _maybe_create_investment_offer(player: Any, context: dict[str, Any], state: dict[str, Any], demand: dict[str, float], production: dict[str, float]) -> None:
    turn = int(getattr(player, "turn", 1))
    if state.get("pending_investment_offer") or turn < int(state.get("next_investment_turn", turn + 3)):
        return
    candidates = sorted(
        RESOURCE_CATALOG,
        key=lambda key: _resource_score_for_investment(key, state, demand, production, context),
        reverse=True,
    )
    resource = next((key for key in candidates if _resource_score_for_investment(key, state, demand, production, context) > -10), None)
    if not resource:
        state["next_investment_turn"] = turn + 5
        return
    spec = RESOURCE_CATALOG[resource]
    price_multiplier = clamp(finite(context.get("price_multiplier", 1.0), 1.0), 0.2, 20.0)
    current_level = state["production_levels"].get(resource, 1.0)
    base = spec["base_price"] * (18.0 + 5.0 * current_level) * price_multiplier
    tiers = [
        {"key": "1", "label": "Ограниченное расширение", "cost": max(80, int(round(base * 0.55))), "level_gain": 0.45, "yield_bonus": 7},
        {"key": "2", "label": "Провинциальная программа", "cost": max(180, int(round(base * 1.35))), "level_gain": 1.05, "yield_bonus": 16},
        {"key": "3", "label": "Имперская модернизация", "cost": max(400, int(round(base * 3.10))), "level_gain": 2.10, "yield_bonus": 31},
    ]
    state["pending_investment_offer"] = {
        "id": f"investment:{turn}:{resource}",
        "turn": turn,
        "resource": resource,
        "name": spec["name"],
        "icon": spec["icon"],
        "current_level": round(current_level, 2),
        "production": round(production.get(resource, 0.0), 2),
        "demand": round(demand.get(resource, 0.0), 2),
        "tiers": tiers,
    }
    rng = _rng(player, "next-investment", turn)
    state["next_investment_turn"] = turn + rng.randint(4, 7)


def resolve_investment_offer(player: Any, choice: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    state = ensure_state(player, context or {})
    offer = state.get("pending_investment_offer")
    if not isinstance(offer, dict):
        return {"ok": False, "message": "Нет действующего инвестиционного предложения."}
    if str(choice).upper() in {"Q", "N", "0", "DECLINE"}:
        state["pending_investment_offer"] = None
        state["offer_history"].append({"turn": int(getattr(player, "turn", 1)), "kind": "investment", "result": "declined", "resource": offer.get("resource")})
        state["offer_history"] = state["offer_history"][-80:]
        return {"ok": True, "message": f"Расширение производства: {offer.get('name', 'ресурс')} — отложено."}
    tier = next((row for row in offer.get("tiers", []) if str(row.get("key")) == str(choice)), None)
    if not isinstance(tier, dict):
        return {"ok": False, "message": "Неизвестный вариант вложения."}
    cost = max(0, int(tier.get("cost", 0)))
    if int(getattr(player, "gold", 0)) < cost:
        return {"ok": False, "message": f"Недостаточно золота: требуется {cost}."}
    resource = str(offer.get("resource"))
    player.gold -= cost
    state["production_levels"][resource] = clamp(state["production_levels"].get(resource, 1.0) + finite(tier.get("level_gain", 0.0)), 0.25, 25.0)
    state["invested_gold"][resource] = finite(state["invested_gold"].get(resource, 0.0)) + cost
    state["total_investment"] = finite(state.get("total_investment", 0.0)) + cost
    if isinstance(getattr(player, "economy", None), dict):
        sector = RESOURCE_CATALOG[resource].get("sector")
        capital = player.economy.get("sectoral_capital")
        if sector and isinstance(capital, dict):
            capital[sector] = max(1.0, finite(capital.get(sector, 1.0)) + 0.35 * math.log1p(cost))
    state["pending_investment_offer"] = None
    state["offer_history"].append({"turn": int(getattr(player, "turn", 1)), "kind": "investment", "result": "accepted", "resource": resource, "cost": cost})
    state["offer_history"] = state["offer_history"][-80:]
    return {
        "ok": True,
        "message": f"{offer.get('icon', '')} {offer.get('name', resource)}: вложено {cost} золота; производственная мощность выросла примерно на {tier.get('yield_bonus', 0)}%.",
    }


def _partner_specialties(identifier: str) -> list[str]:
    lowered = str(identifier).lower()
    result: list[str] = []
    for marker, goods in PARTNER_SPECIALIZATIONS.items():
        if marker in lowered:
            result.extend(goods)
    return [key for key in dict.fromkeys(result) if key in RESOURCE_CATALOG] or ["wheat", "iron", "wine", "horses"]


def _trade_partners(context: dict[str, Any]) -> list[dict[str, Any]]:
    partners: list[dict[str, Any]] = []
    for row in context.get("diplomatic_partners", []) if isinstance(context.get("diplomatic_partners"), list) else []:
        if not isinstance(row, dict):
            continue
        partners.append({
            "type": "state",
            "key": str(row.get("key") or row.get("name") or "state"),
            "name": str(row.get("name") or row.get("key") or "Иностранная держава"),
            "relation": clamp(finite(row.get("relation", row.get("disposition", 50))), 0.0, 100.0),
            "specialties": _partner_specialties(f"{row.get('key','')} {row.get('name','')}"),
        })
    for row in context.get("barbarian_partners", []) if isinstance(context.get("barbarian_partners"), list) else []:
        if not isinstance(row, dict):
            continue
        partners.append({
            "type": "barbarian",
            "key": str(row.get("key") or row.get("name") or "tribe"),
            "name": str(row.get("name") or row.get("key") or "Варварское племя"),
            "relation": clamp(finite(row.get("relation", 40)), 0.0, 100.0),
            "specialties": _partner_specialties(f"{row.get('key','')} {row.get('name','')}"),
        })
    return partners


def _maybe_create_trade_offer(player: Any, context: dict[str, Any], state: dict[str, Any]) -> None:
    turn = int(getattr(player, "turn", 1))
    if state.get("pending_trade_offer") or turn < int(state.get("next_trade_turn", turn + 2)):
        return
    partners = _trade_partners(context)
    if not partners:
        state["next_trade_turn"] = turn + 4
        return
    rng = _rng(player, "trade-offer", turn)
    partner = rng.choice(partners)
    relation = partner["relation"]
    stock = state["stockpiles"]
    reserves = state["reserve_targets"]
    prices = state["market_prices"]

    import_candidates = [key for key in partner["specialties"] if key in RESOURCE_CATALOG]
    export_candidates = [key for key in RESOURCE_CATALOG if stock.get(key, 0.0) > reserves.get(key, 0.0) * 1.25]
    kind_roll = rng.random()
    if export_candidates and kind_roll < 0.34:
        kind = "export"
        resource = rng.choice(export_candidates)
        surplus = max(1.0, stock[resource] - reserves[resource])
        amount = max(1, min(12, int(round(surplus * rng.uniform(0.25, 0.55)))))
        price = prices[resource] * amount * (0.78 + relation / 250.0)
        receive_gold = max(10, int(round(price)))
        offer = {
            "kind": kind,
            "resource": resource,
            "amount": amount,
            "receive_gold": receive_gold,
        }
    elif export_candidates and import_candidates and kind_roll < 0.60:
        kind = "barter"
        give = rng.choice(export_candidates)
        receive = rng.choice(import_candidates)
        give_amount = max(1, min(10, int(round((stock[give] - reserves[give]) * rng.uniform(0.20, 0.45)))))
        give_value = give_amount * prices[give]
        receive_amount = max(1, int(round(give_value / max(1.0, prices[receive]) * (0.82 + relation / 300.0))))
        offer = {
            "kind": kind,
            "give_resource": give,
            "give_amount": give_amount,
            "receive_resource": receive,
            "receive_amount": receive_amount,
        }
    else:
        kind = "import"
        resource = rng.choice(import_candidates)
        reserve_gap = max(1.0, reserves.get(resource, 5.0) - stock.get(resource, 0.0))
        amount = max(1, min(14, int(round(reserve_gap + rng.uniform(1.0, 5.0)))))
        price = prices[resource] * amount * (1.16 - relation / 350.0)
        pay_gold = max(10, int(round(price)))
        offer = {
            "kind": kind,
            "resource": resource,
            "amount": amount,
            "pay_gold": pay_gold,
        }
    offer.update({
        "id": f"trade:{turn}:{partner['type']}:{partner['key']}",
        "turn": turn,
        "expires_turn": turn + 2,
        "partner_type": partner["type"],
        "partner_key": partner["key"],
        "partner_name": partner["name"],
        "relation": relation,
    })
    state["pending_trade_offer"] = offer
    state["next_trade_turn"] = turn + rng.randint(3, 6)


def trade_offer_text(offer: dict[str, Any]) -> str:
    if not isinstance(offer, dict):
        return "Нет предложения."
    partner = offer.get("partner_name", "Торговый партнёр")
    kind = offer.get("kind")
    if kind == "import":
        spec = RESOURCE_CATALOG.get(str(offer.get("resource")), {"name": offer.get("resource"), "icon": "•"})
        return f"{partner} предлагает {spec['icon']} {spec['name']} ×{offer.get('amount', 0)} за {offer.get('pay_gold', 0)} золота."
    if kind == "export":
        spec = RESOURCE_CATALOG.get(str(offer.get("resource")), {"name": offer.get("resource"), "icon": "•"})
        return f"{partner} желает купить {spec['icon']} {spec['name']} ×{offer.get('amount', 0)} за {offer.get('receive_gold', 0)} золота."
    if kind == "barter":
        give = RESOURCE_CATALOG.get(str(offer.get("give_resource")), {"name": offer.get("give_resource"), "icon": "•"})
        receive = RESOURCE_CATALOG.get(str(offer.get("receive_resource")), {"name": offer.get("receive_resource"), "icon": "•"})
        return f"{partner} предлагает обмен: ваши {give['icon']} {give['name']} ×{offer.get('give_amount', 0)} на {receive['icon']} {receive['name']} ×{offer.get('receive_amount', 0)}."
    return f"{partner} прислал торговое предложение."


def resolve_trade_offer(player: Any, accept: bool, context: dict[str, Any] | None = None) -> dict[str, Any]:
    state = ensure_state(player, context or {})
    offer = state.get("pending_trade_offer")
    if not isinstance(offer, dict):
        return {"ok": False, "message": "Нет действующего торгового предложения."}
    if not accept:
        state["pending_trade_offer"] = None
        state["offer_history"].append({"turn": int(getattr(player, "turn", 1)), "kind": "trade", "result": "declined", "partner": offer.get("partner_name")})
        state["offer_history"] = state["offer_history"][-80:]
        return {"ok": True, "message": f"Предложение от {offer.get('partner_name', 'партнёра')} отклонено."}

    stock = state["stockpiles"]
    kind = offer.get("kind")
    if kind == "import":
        cost = max(0, int(offer.get("pay_gold", 0)))
        if int(getattr(player, "gold", 0)) < cost:
            return {"ok": False, "message": f"Недостаточно золота: требуется {cost}."}
        resource = str(offer.get("resource"))
        amount = max(0.0, finite(offer.get("amount", 0.0)))
        player.gold -= cost
        stock[resource] = stock.get(resource, 0.0) + amount
        gold_delta = -cost
    elif kind == "export":
        resource = str(offer.get("resource"))
        amount = max(0.0, finite(offer.get("amount", 0.0)))
        if stock.get(resource, 0.0) + 1e-6 < amount:
            return {"ok": False, "message": f"Недостаточно товара: {RESOURCE_CATALOG.get(resource, {}).get('name', resource)}."}
        revenue = max(0, int(offer.get("receive_gold", 0)))
        stock[resource] -= amount
        player.gold = int(getattr(player, "gold", 0)) + revenue
        gold_delta = revenue
    elif kind == "barter":
        give = str(offer.get("give_resource"))
        receive = str(offer.get("receive_resource"))
        give_amount = max(0.0, finite(offer.get("give_amount", 0.0)))
        receive_amount = max(0.0, finite(offer.get("receive_amount", 0.0)))
        if stock.get(give, 0.0) + 1e-6 < give_amount:
            return {"ok": False, "message": f"Недостаточно товара: {RESOURCE_CATALOG.get(give, {}).get('name', give)}."}
        stock[give] -= give_amount
        stock[receive] = stock.get(receive, 0.0) + receive_amount
        gold_delta = 0
    else:
        return {"ok": False, "message": "Неизвестный тип торгового предложения."}

    state["total_trade_gold"] = finite(state.get("total_trade_gold", 0.0)) + gold_delta
    state["pending_trade_offer"] = None
    state["offer_history"].append({"turn": int(getattr(player, "turn", 1)), "kind": "trade", "result": "accepted", "partner": offer.get("partner_name"), "gold_delta": gold_delta})
    state["offer_history"] = state["offer_history"][-80:]
    _push_legacy_metals(player, state)
    return {"ok": True, "message": "Сделка заключена: " + trade_offer_text(offer)}


def rare_resource_income_breakdown(
    player: Any,
    context: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Возвращает точный доход от текущих запасов редких ресурсов."""
    state = state if isinstance(state, dict) else ensure_state(player, context or {})
    stock = state.get("stockpiles") if isinstance(state.get("stockpiles"), dict) else {}
    rows: list[dict[str, Any]] = []
    for key, rate in RARE_RESOURCE_GOLD_PER_TURN.items():
        units = max(0.0, finite(stock.get(key, 0.0)))
        income = int(round(units * rate))
        if income <= 0:
            continue
        spec = RESOURCE_CATALOG.get(key, {})
        rows.append({
            "key": key,
            "name": spec.get("name", key),
            "icon": spec.get("icon", "•"),
            "units": round(units, 3),
            "rate": int(rate),
            "income": income,
        })
    return rows


def rare_resource_income(player: Any, context: dict[str, Any] | None = None) -> int:
    return sum(row["income"] for row in rare_resource_income_breakdown(player, context))


def apply_turn(player: Any, context: dict[str, Any]) -> dict[str, Any]:
    """Выполняет один автоматический ресурсный ход.

    Повторный вызов на том же ходу безопасен: состояние не начисляется дважды.
    """
    state = ensure_state(player, context)
    turn = int(getattr(player, "turn", 1))
    if int(state.get("last_processed_turn", 0)) == turn:
        return dict(state.get("last_flow", {}))

    _pull_legacy_metals(player, state)
    production = _primary_production(player, context, state)
    for key, amount in production.items():
        state["stockpiles"][key] = state["stockpiles"].get(key, 0.0) + amount

    demand = _demand_snapshot(context)
    processed, processing_inputs = _process_derived_goods(context, state, demand)
    for key, amount in processed.items():
        production[key] = production.get(key, 0.0) + amount

    _update_market_prices(player, state, demand, production)
    consumed, shortages, purchase_cost = _consume_and_autobuy(player, context, state, demand)
    shortage_notes = _apply_shortage_effects(player, shortages, demand)

    rare_income_rows = rare_resource_income_breakdown(player, context, state)
    rare_income = sum(row["income"] for row in rare_income_rows)
    if rare_income:
        player.gold = max(0, int(getattr(player, "gold", 0))) + rare_income
        # Roma Economica уже записала обычный бюджетный итог раньше в этом ходе.
        # Добавляем прямой ресурсный доход к итоговым показателям, не подменяя их.
        player.gold_income_last_turn = int(getattr(player, "gold_income_last_turn", 0)) + rare_income
        player.gold_per_turn = int(getattr(player, "gold_per_turn", 0)) + rare_income
    player.rare_resource_income_last_turn = rare_income
    state["last_rare_resource_income"] = rare_income
    state["total_rare_resource_income"] = finite(state.get("total_rare_resource_income", 0.0)) + rare_income

    _maybe_create_investment_offer(player, context, state, demand, production)
    _maybe_create_trade_offer(player, context, state)
    _push_legacy_metals(player, state)

    produced_total = sum(production.values())
    consumed_total = sum(consumed.values())
    important = sorted(production.items(), key=lambda row: row[1], reverse=True)[:5]
    flow = {
        "turn": turn,
        "production": {key: round(value, 3) for key, value in production.items() if value > 1e-6},
        "processing_inputs": {key: round(value, 3) for key, value in processing_inputs.items() if value > 1e-6},
        "consumption": {key: round(value, 3) for key, value in consumed.items() if value > 1e-6},
        "demand": {key: round(value, 3) for key, value in demand.items() if value > 1e-6},
        "shortages": {key: round(value, 3) for key, value in shortages.items() if value > 1e-6},
        "auto_purchase_cost": int(round(purchase_cost)),
        "rare_resource_income": rare_income,
        "rare_resource_income_breakdown": rare_income_rows,
        "produced_total": round(produced_total, 2),
        "consumed_total": round(consumed_total, 2),
        "top_production": [(key, round(value, 2)) for key, value in important if value > 0.01],
        "notes": shortage_notes,
    }
    state["last_flow"] = flow
    state["history"].append({
        "turn": turn,
        "produced": round(produced_total, 2),
        "consumed": round(consumed_total, 2),
        "auto_purchase_cost": int(round(purchase_cost)),
        "rare_resource_income": rare_income,
        "shortages": len(shortages),
        "stock_value": round(stockpile_value(player, context), 2),
    })
    state["history"] = state["history"][-120:]
    state["last_processed_turn"] = turn
    return flow


def stockpile_value(player: Any, context: dict[str, Any] | None = None) -> float:
    state = ensure_state(player, context or {})
    return sum(state["stockpiles"].get(key, 0.0) * state["market_prices"].get(key, spec["base_price"]) for key, spec in RESOURCE_CATALOG.items())


def category_report(player: Any, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    state = ensure_state(player, context or {})
    flow = state.get("last_flow", {}) if isinstance(state.get("last_flow"), dict) else {}
    production = flow.get("production", {}) if isinstance(flow.get("production"), dict) else {}
    consumption = flow.get("consumption", {}) if isinstance(flow.get("consumption"), dict) else {}
    shortages = flow.get("shortages", {}) if isinstance(flow.get("shortages"), dict) else {}
    rows: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        for key, spec in RESOURCE_CATALOG.items():
            if spec["category"] != category:
                continue
            rows.append({
                "key": key,
                "category": category,
                "category_label": CATEGORY_LABELS[category],
                "name": spec["name"],
                "icon": spec["icon"],
                "stock": round(state["stockpiles"].get(key, 0.0), 1),
                "production": round(finite(production.get(key, 0.0)), 1),
                "consumption": round(finite(consumption.get(key, 0.0)), 1),
                "shortage": round(finite(shortages.get(key, 0.0)), 1),
                "level": round(state["production_levels"].get(key, 1.0), 2),
                "price": round(state["market_prices"].get(key, spec["base_price"]), 1),
            })
    return rows


def compact_summary(player: Any, context: dict[str, Any] | None = None) -> str:
    state = ensure_state(player, context or {})
    stock = state["stockpiles"]
    keys = ("wheat", "iron", "steel", "horses", "silver", "gold")
    return "  ".join(f"{RESOURCE_CATALOG[key]['icon']} {int(round(stock.get(key, 0.0)))}" for key in keys)


def pending_offers(player: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
    state = ensure_state(player, context or {})
    return {
        "investment": state.get("pending_investment_offer"),
        "trade": state.get("pending_trade_offer"),
    }


def set_auto_buy(player: Any, enabled: bool, context: dict[str, Any] | None = None) -> bool:
    state = ensure_state(player, context or {})
    state["auto_buy_shortages"] = bool(enabled)
    return state["auto_buy_shortages"]


def audit_invariants(player: Any, context: dict[str, Any] | None = None) -> list[str]:
    state = ensure_state(player, context or {})
    errors: list[str] = []
    stock = state.get("stockpiles")
    if not isinstance(stock, dict):
        errors.append("stockpiles не является словарём")
        return errors
    for key in RESOURCE_CATALOG:
        value = finite(stock.get(key, -1.0), -1.0)
        if value < 0 or not math.isfinite(value):
            errors.append(f"{key}: недопустимый запас {stock.get(key)!r}")
        level = finite(state["production_levels"].get(key, 0.0), 0.0)
        if not 0.25 <= level <= 25.0:
            errors.append(f"{key}: уровень добычи вне диапазона")
        price = finite(state["market_prices"].get(key, 0.0), 0.0)
        if price <= 0:
            errors.append(f"{key}: цена неположительна")
    if int(state.get("last_processed_turn", 0)) < 0:
        errors.append("last_processed_turn отрицателен")
    for key, spec in RESOURCE_CATALOG.items():
        if spec.get("category") == "luxury" and int(RARE_RESOURCE_GOLD_PER_TURN.get(key, 0)) <= 0:
            errors.append(f"{key}: редкий ресурс не даёт золото за ход")
    return errors



def imperial_turn_report(player: Any, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Returns the complete post-turn imperial resource statement.

    Each row contains gross production, consumption, net flow and current
    stock.  Rows with no production, consumption or stock are omitted so a new
    game remains readable while a developed empire still shows all active
    commodities.
    """
    state = ensure_state(player, context or {})
    flow = state.get("last_flow", {}) if isinstance(state.get("last_flow"), dict) else {}
    production = flow.get("production", {}) if isinstance(flow.get("production"), dict) else {}
    consumption = flow.get("consumption", {}) if isinstance(flow.get("consumption"), dict) else {}
    processing_inputs = flow.get("processing_inputs", {}) if isinstance(flow.get("processing_inputs"), dict) else {}
    shortages = flow.get("shortages", {}) if isinstance(flow.get("shortages"), dict) else {}
    rows: list[dict[str, Any]] = []
    for category in CATEGORY_ORDER:
        for key, spec in RESOURCE_CATALOG.items():
            if spec.get("category") != category:
                continue
            produced = finite(production.get(key, 0.0))
            used = finite(consumption.get(key, 0.0)) + finite(processing_inputs.get(key, 0.0))
            stock = finite(state.get("stockpiles", {}).get(key, 0.0))
            shortage = finite(shortages.get(key, 0.0))
            if max(abs(produced), abs(used), abs(stock), abs(shortage)) <= 1e-6:
                continue
            rows.append({
                "key": key,
                "category": category,
                "category_label": CATEGORY_LABELS.get(category, category),
                "name": spec.get("name", key),
                "icon": spec.get("icon", "•"),
                "produced": round(produced, 2),
                "consumed": round(used, 2),
                "net": round(produced - used, 2),
                "stock": round(stock, 2),
                "shortage": round(shortage, 2),
            })
    return rows
