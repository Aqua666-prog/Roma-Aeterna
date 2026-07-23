#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Economica — расширенное экономическое ядро Roma Aeterna.

Версия 3 переводит агрегированную макромодель в связанную систему отраслей,
населения, банковского кредита, внешней торговли и национальных счетов.
Модуль не импортирует основной файл игры: связь идёт только через ``player``
и чистый словарь ``context``. Поэтому ядро можно тестировать изолированно.

Основные элементы модели:
- пять производственных секторов с матрицей промежуточного спроса;
- свободное и рабское, городское и сельское население;
- фрикционное перераспределение труда и капитала;
- частный кредит, банковское здоровье, вытеснение частных инвестиций долгом;
- внешний рынок шести товаров, платёжный баланс и импортная зависимость;
- воспроизводимые эпидемии, климатические, горные и валютные шоки;
- эндогенное накопление знаний и отраслевые технологические прорывы;
- политическая экономия бюджетных ассигнований и рентный поиск;
- ВВП по производству и расходам, sectoral balances и flow-of-funds;
- двойная бухгалтерская запись и миграция старых сохранений;
- военные трофеи, контрибуции, пленные и капитальные трансферты завоеваний.

Денежные величины выражены в игровых единицах золота, население — в тысячах
жителей, реальные агрегаты — в индексных единицах выпуска.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from typing import Any

try:
    import economy_modifiers as ECONOMY_MODIFIERS
except (ImportError, SyntaxError):
    ECONOMY_MODIFIERS = None

try:
    import economy_dictionary as ECONOMY_DICTIONARY
except (ImportError, SyntaxError):
    ECONOMY_DICTIONARY = None

ECONOMY_VERSION = 13

STARTING_BASE_REVENUE_MIN = 50
STARTING_BASE_REVENUE_DEFAULT = 80
STARTING_BASE_REVENUE_MAX = 100


@dataclass(frozen=True)
class EconomyConfig:
    """Калибровка модели. Все прежние magic numbers собраны здесь."""

    capital_alpha: float = 0.38
    output_scale: float = 1.76
    labor_participation: float = 0.46
    base_population_growth: float = 0.011
    base_mortality: float = 0.0095
    private_saving_base: float = 0.10
    private_saving_confidence: float = 0.16
    private_saving_tax_penalty: float = 0.10
    base_money_growth: float = 0.0015
    money_output_response: float = 0.52
    price_adjustment: float = 0.23
    labor_mobility_base: float = 0.022
    capital_mobility_base: float = 0.014
    shock_scale: float = 1.0
    max_active_shocks: int = 5
    ledger_limit: int = 800
    history_limit: int = 180
    shock_history_limit: int = 120
    default_reserve_turns: float = 4.0
    captured_slaves_per_province: float = 7.5


DEFAULT_CONFIG = EconomyConfig()

BUDGET_KEYS = (
    "administration",
    "military",
    "infrastructure",
    "welfare",
    "science",
    "religion",
)

BUDGET_LABELS = {
    "administration": "Управление и суд",
    "military": "Военное ведомство",
    "infrastructure": "Дороги и сооружения",
    "welfare": "Аннона и общественные расходы",
    "science": "Школы и мастерские",
    "religion": "Культы и храмы",
}

DEFAULT_BUDGET_SHARES = {
    "administration": 0.20,
    "military": 0.24,
    "infrastructure": 0.24,
    "welfare": 0.14,
    "science": 0.12,
    "religion": 0.06,
}

# Один процент бюджета стоит по-разному в разных ведомствах. Перенос средств
# в армию или великие стройки теперь меняет не только бонусы, но и общий баланс.
PROGRAMME_COST_MULTIPLIERS = {
    "administration": 0.95,
    "military": 1.20,
    "infrastructure": 1.30,
    "welfare": 1.05,
    "science": 1.15,
    "religion": 0.90,
}

FISCAL_STANCES = {
    "austerity": {"label": "Экономия", "investment_ratio": 0.55, "confidence": 0.02},
    "balanced": {"label": "Сбалансированный бюджет", "investment_ratio": 0.85, "confidence": 0.01},
    "development": {"label": "Развитие", "investment_ratio": 1.15, "confidence": 0.00},
    "war": {"label": "Военная мобилизация", "investment_ratio": 1.30, "confidence": -0.02},
}

COIN_STANDARDS = {
    "sound": {"label": "Полновесная монета", "velocity": -0.04, "confidence": 0.025, "foreign_trust": 0.06},
    "managed": {"label": "Управляемая чеканка", "velocity": 0.00, "confidence": 0.000, "foreign_trust": 0.00},
    "debased": {"label": "Пониженная проба", "velocity": 0.09, "confidence": -0.035, "foreign_trust": -0.12},
}

CREDIT_POLICIES = {
    "easy": {"label": "Дешёвый кредит", "rate": -0.025, "credit_growth": 0.18, "risk": 0.05},
    "neutral": {"label": "Нейтральная политика", "rate": 0.000, "credit_growth": 0.08, "risk": 0.00},
    "tight": {"label": "Ограничение кредита", "rate": 0.035, "credit_growth": -0.02, "risk": -0.04},
}

# Автономная «имперская машина». Игрок выбирает доктрину один раз, после чего
# экономика сама подрезает необязательные расходы и удерживает положительный
# денежный поток. Сложная макромодель при этом остаётся под капотом.
AUTOMATION_DOCTRINES = {
    "balanced": {
        "label": "Стабильный фиск",
        "minimum_balance": 15,
        "emergency_limit": 8,
        "tax_target": 0.24,
        "tariff_target": 0.08,
        "fiscal_stance": "balanced",
        "coin_standard": "managed",
        "credit_policy": "neutral",
        "sector_policy": "balanced",
        "grain_target": 4.0,
        "reserve_turns": 2.2,
        "budget": {"administration": .21, "military": .22, "infrastructure": .23, "welfare": .15, "science": .13, "religion": .06},
        "investment_rate": 0.08,
    },
    "treasury": {
        "label": "Приоритет казны",
        "minimum_balance": 35,
        "emergency_limit": 12,
        "tax_target": 0.29,
        "tariff_target": 0.11,
        "fiscal_stance": "austerity",
        "coin_standard": "sound",
        "credit_policy": "tight",
        "sector_policy": "balanced",
        "grain_target": 3.5,
        "reserve_turns": 3.2,
        "budget": {"administration": .25, "military": .20, "infrastructure": .18, "welfare": .13, "science": .09, "religion": .05},
        "investment_rate": 0.04,
    },
    "mercantile": {
        "label": "Средиземноморская торговля",
        "minimum_balance": 25,
        "emergency_limit": 10,
        "tax_target": 0.22,
        "tariff_target": 0.10,
        "fiscal_stance": "balanced",
        "coin_standard": "sound",
        "credit_policy": "easy",
        "sector_policy": "mercantile",
        "grain_target": 4.5,
        "reserve_turns": 2.5,
        "budget": {"administration": .20, "military": .18, "infrastructure": .25, "welfare": .13, "science": .17, "religion": .07},
        "investment_rate": 0.09,
    },
    "development": {
        "label": "Имперское развитие",
        "minimum_balance": 10,
        "emergency_limit": 6,
        "tax_target": 0.23,
        "tariff_target": 0.07,
        "fiscal_stance": "development",
        "coin_standard": "managed",
        "credit_policy": "easy",
        "sector_policy": "public_works",
        "grain_target": 5.0,
        "reserve_turns": 1.8,
        "budget": {"administration": .18, "military": .17, "infrastructure": .31, "welfare": .13, "science": .16, "religion": .05},
        "investment_rate": 0.13,
    },
    "war": {
        "label": "Военная экономика",
        "minimum_balance": 5,
        "emergency_limit": 15,
        "tax_target": 0.31,
        "tariff_target": 0.12,
        "fiscal_stance": "war",
        "coin_standard": "managed",
        "credit_policy": "tight",
        "sector_policy": "workshops",
        "grain_target": 6.0,
        "reserve_turns": 1.5,
        "budget": {"administration": .17, "military": .39, "infrastructure": .18, "welfare": .12, "science": .09, "religion": .05},
        "investment_rate": 0.07,
    },
}


REVENUE_KEYS = (
    "direct_tax", "customs", "domains", "tribute", "commerce",
    "trade_routes", "rare_resources", "caravans", "base_revenue",
    "micro_income", "doctrine_income", "automatic_stabilizer",
)

# Эти поступления уже выражены в фактическом золоте. Они не умножаются на
# инфляцию, сложность или религиозные коэффициенты и не срезаются сглаживанием:
# торговый путь +144 обязан дать казне ровно 144, а прибывший караван — свою
# полную заявленную выручку. При этом проводка всё равно проходит через единое
# ядро Roma Economica и попадает в общую ведомость/бухгалтерскую книгу.
GUARANTEED_REVENUE_KEYS = ("trade_routes", "rare_resources", "caravans")

SECTOR_KEYS = (
    "agriculture",
    "mining",
    "manufacturing",
    "construction",
    "commerce",
)

SECTOR_LABELS = {
    "agriculture": "Сельское хозяйство",
    "mining": "Горное дело",
    "manufacturing": "Ремесло и мануфактуры",
    "construction": "Строительство",
    "commerce": "Торговля и услуги",
}

DEFAULT_SECTOR_CAPITAL_SHARES = {
    "agriculture": 0.40,
    "mining": 0.12,
    "manufacturing": 0.18,
    "construction": 0.12,
    "commerce": 0.18,
}

DEFAULT_SECTOR_LABOR_SHARES = {
    "agriculture": 0.55,
    "mining": 0.08,
    "manufacturing": 0.14,
    "construction": 0.08,
    "commerce": 0.15,
}

DEFAULT_SECTOR_PRODUCTIVITY = {
    "agriculture": 1.00,
    "mining": 0.90,
    "manufacturing": 0.94,
    "construction": 0.88,
    "commerce": 1.02,
}

DEFAULT_SECTOR_DEPRECIATION = {
    "agriculture": 0.025,
    "mining": 0.050,
    "manufacturing": 0.045,
    "construction": 0.040,
    "commerce": 0.030,
}

# Доля выпуска поставщика, необходимая для единицы выпуска потребителя.
INPUT_OUTPUT = {
    "agriculture": {"manufacturing": 0.07, "commerce": 0.035},
    "mining": {"manufacturing": 0.06, "construction": 0.025, "commerce": 0.025},
    "manufacturing": {"agriculture": 0.035, "mining": 0.18, "commerce": 0.045},
    "construction": {"mining": 0.16, "manufacturing": 0.13, "commerce": 0.030},
    "commerce": {"construction": 0.025, "manufacturing": 0.020},
}

SLAVE_PRODUCTIVITY = {
    "agriculture": 0.92,
    "mining": 1.02,
    "manufacturing": 0.58,
    "construction": 0.72,
    "commerce": 0.28,
}

SECTOR_POLICIES = {
    "balanced": {"label": "Равновесное развитие", "weights": {key: 1.0 for key in SECTOR_KEYS}},
    "bread": {"label": "Хлеб и земля", "weights": {"agriculture": 1.50, "mining": 0.85, "manufacturing": 0.90, "construction": 1.00, "commerce": 0.90}},
    "extractive": {"label": "Рудники и каменоломни", "weights": {"agriculture": 0.90, "mining": 1.55, "manufacturing": 1.10, "construction": 1.10, "commerce": 0.85}},
    "workshops": {"label": "Ремесленная экспансия", "weights": {"agriculture": 0.90, "mining": 1.10, "manufacturing": 1.55, "construction": 1.05, "commerce": 1.00}},
    "public_works": {"label": "Великие стройки", "weights": {"agriculture": 0.90, "mining": 1.10, "manufacturing": 1.10, "construction": 1.60, "commerce": 0.90}},
    "mercantile": {"label": "Торговая республика", "weights": {"agriculture": 0.92, "mining": 0.90, "manufacturing": 1.15, "construction": 0.95, "commerce": 1.60}},
}

GOODS = {
    "grain": {"label": "Зерно", "world_price": 1.00, "import_elasticity": 0.70, "export_elasticity": 0.60},
    "metals": {"label": "Металлы", "world_price": 1.35, "import_elasticity": 0.58, "export_elasticity": 0.52},
    "wine_oil": {"label": "Вино и масло", "world_price": 1.20, "import_elasticity": 0.48, "export_elasticity": 0.60},
    "manufactures": {"label": "Ремесленные изделия", "world_price": 1.55, "import_elasticity": 0.55, "export_elasticity": 0.62},
    "luxury": {"label": "Предметы роскоши", "world_price": 2.20, "import_elasticity": 0.78, "export_elasticity": 0.75},
    "slaves": {"label": "Рабы", "world_price": 1.70, "import_elasticity": 0.35, "export_elasticity": 0.30},
}

INTEREST_GROUPS = ("elites", "plebs", "military", "merchants", "priests")
INTEREST_GROUP_LABELS = {
    "elites": "Землевладельцы и нобилитет",
    "plebs": "Городской плебс",
    "military": "Армия и ветераны",
    "merchants": "Всадники и купцы",
    "priests": "Жреческие коллегии",
}

SHOCK_LABELS = {
    "epidemic": "Эпидемия",
    "drought": "Засуха",
    "flood": "Наводнение",
    "locusts": "Нашествие саранчи",
    "mine_discovery": "Открытие нового месторождения",
    "mine_depletion": "Истощение рудника",
    "currency_crisis": "Валютный кризис",
    "banking_panic": "Банковская паника",
    "slave_revolt": "Восстание рабов",
    "trade_boom": "Торговый подъём",
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def money(value: float) -> int:
    return int(round(finite(value)))


def sigmoid(x: float) -> float:
    x = clamp(finite(x), -60.0, 60.0)
    return 1.0 / (1.0 + math.exp(-x))


def _deepcopy(value: Any) -> Any:
    return copy.deepcopy(value)


def _normalize_map(raw: Any, keys: tuple[str, ...], defaults: dict[str, float]) -> dict[str, float]:
    source = raw if isinstance(raw, dict) else {}
    cleaned = {key: max(0.0, finite(source.get(key, defaults[key]))) for key in keys}
    total = sum(cleaned.values())
    if total <= 0:
        return dict(defaults)
    return {key: cleaned[key] / total for key in keys}


def normalize_budget_shares(shares: Any) -> dict[str, float]:
    return _normalize_map(shares, BUDGET_KEYS, DEFAULT_BUDGET_SHARES)


def normalize_sector_shares(shares: Any, defaults: dict[str, float]) -> dict[str, float]:
    return _normalize_map(shares, SECTOR_KEYS, defaults)


def _stable_seed(*parts: Any) -> int:
    payload = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big", signed=False)


def _rng_for(player: Any, state: dict[str, Any], channel: str) -> random.Random:
    return random.Random(_stable_seed(
        channel,
        int(getattr(player, "turn", 0)),
        str(getattr(player, "name", "Roma")),
        round(finite(state.get("population", 0)), 3),
        round(finite(state.get("capital_stock", 0)), 3),
        round(finite(state.get("debt", 0)), 2),
        int(state.get("version", ECONOMY_VERSION)),
    ))


def _config(context: dict[str, Any] | None = None) -> EconomyConfig:
    raw = (context or {}).get("economy_config")
    if isinstance(raw, EconomyConfig):
        return raw
    if isinstance(raw, dict):
        allowed = asdict(DEFAULT_CONFIG)
        allowed.update({k: v for k, v in raw.items() if k in allowed})
        try:
            return EconomyConfig(**allowed)
        except (TypeError, ValueError):
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def _province_population(context: dict[str, Any]) -> float:
    profiles = context.get("provinces", []) if isinstance(context.get("provinces", []), list) else []
    city_population = sum(max(0.0, finite(p.get("city_population", 0))) for p in profiles if isinstance(p, dict))
    rural_population = sum(20.0 + 3.0 * max(0.0, finite(p.get("wealth", 0))) for p in profiles if isinstance(p, dict))
    return max(80.0, city_population + rural_population)


def _province_capital(context: dict[str, Any]) -> float:
    profiles = context.get("provinces", []) if isinstance(context.get("provinces", []), list) else []
    total = 0.0
    for p in profiles:
        if not isinstance(p, dict):
            continue
        wealth = max(0.0, finite(p.get("wealth", 0)))
        cities = max(0.0, finite(p.get("city_count", 0)))
        romanization = clamp(finite(p.get("romanization", 0)), 0.0, 100.0)
        total += 18.0 + wealth * 3.2 + cities * 1.5 + romanization * 0.08
    return max(100.0, total)


def _province_carrying_capacity(context: dict[str, Any]) -> float:
    profiles = context.get("provinces", []) if isinstance(context.get("provinces", []), list) else []
    capacity = 90.0
    for p in profiles:
        if not isinstance(p, dict):
            continue
        wealth = max(0.0, finite(p.get("wealth", 0)))
        city_population = max(0.0, finite(p.get("city_population", 0)))
        agricultural = clamp(finite(p.get("agriculture", 0.5)), 0.0, 2.5)
        capacity += 35.0 + city_population * 1.35 + wealth * 4.0 * agricultural
    return max(160.0, capacity)


def _sector_endowments(context: dict[str, Any]) -> dict[str, float]:
    profiles = context.get("provinces", []) if isinstance(context.get("provinces", []), list) else []
    result = {key: 1.0 for key in SECTOR_KEYS}
    if not profiles:
        return result
    for p in profiles:
        if not isinstance(p, dict):
            continue
        wealth = max(0.0, finite(p.get("wealth", 0)))
        cities = max(0.0, finite(p.get("city_count", 0)))
        result["agriculture"] += max(0.0, finite(p.get("agriculture", 0.5))) * 0.22
        result["mining"] += max(0.0, finite(p.get("mining", 0.25))) * 0.30
        result["manufacturing"] += max(0.0, finite(p.get("manufacturing", 0.25))) * 0.24 + cities * 0.03
        result["construction"] += max(0.0, finite(p.get("construction", 0.20))) * 0.20 + wealth * 0.015
        result["commerce"] += max(0.0, finite(p.get("commerce", 0.30))) * 0.26 + cities * 0.04
    scale = max(1.0, len(profiles) * 0.60)
    return {key: clamp(value / scale, 0.55, 2.25) for key, value in result.items()}


def _ledger_post(state: dict[str, Any], turn: int, debit: str, credit: str, amount: float, memo: str) -> None:
    amount = round(max(0.0, finite(amount)), 2)
    if amount <= 0:
        return
    entry = {"turn": int(turn), "debit": str(debit), "credit": str(credit), "amount": amount, "memo": str(memo)}
    ledger = state.setdefault("ledger", [])
    if not isinstance(ledger, list):
        ledger = []
        state["ledger"] = ledger
    ledger.append(entry)
    del ledger[:-_config().ledger_limit]


def trial_balance(player: Any) -> dict[str, Any]:
    state = ensure_economy_state(player)
    debit: dict[str, float] = {}
    credit: dict[str, float] = {}
    for row in state.get("ledger", []):
        if not isinstance(row, dict):
            continue
        amount = max(0.0, finite(row.get("amount", 0)))
        debit_name = str(row.get("debit", "Неизвестный счёт"))
        credit_name = str(row.get("credit", "Неизвестный счёт"))
        debit[debit_name] = debit.get(debit_name, 0.0) + amount
        credit[credit_name] = credit.get(credit_name, 0.0) + amount
    debit_total = round(sum(debit.values()), 2)
    credit_total = round(sum(credit.values()), 2)
    return {
        "debit": debit,
        "credit": credit,
        "debit_total": debit_total,
        "credit_total": credit_total,
        "balanced": abs(debit_total - credit_total) < 0.01,
    }


def _initial_demographics(population: float, context: dict[str, Any]) -> dict[str, float]:
    urban_hint = 0.24 + 0.015 * max(0, int(context.get("province_count", 0)))
    urban_ratio = clamp(finite(context.get("urbanization_hint", urban_hint)), 0.12, 0.62)
    slave_ratio = clamp(finite(context.get("slave_ratio_hint", 0.16)), 0.04, 0.42)
    slave_population = population * slave_ratio
    free_population = population - slave_population
    urban_population = population * urban_ratio
    rural_population = population - urban_population
    return {
        "free_population": free_population,
        "slave_population": slave_population,
        "urban_population": urban_population,
        "rural_population": rural_population,
        "birth_rate": 0.018,
        "death_rate": 0.010,
        "urbanization_rate": urban_ratio,
        "slave_ratio": slave_ratio,
        "slave_revolt_risk": 0.02,
        "last_province_count": float(max(1, int(context.get("province_count", 1)))),
        "captives_last_turn": 0.0,
        "manumissions_last_turn": 0.0,
    }


def _initial_financial_state(initial_output: float, initial_money: float) -> dict[str, float | str | bool]:
    return {
        "private_credit": initial_output * 0.24,
        "deposit_base": initial_money * 0.42,
        "banking_health": 0.78,
        "credit_to_gdp": 0.24,
        "market_rate": 0.085,
        "loan_demand": initial_output * 0.10,
        "loan_supply": initial_output * 0.09,
        "leverage": 0.55,
        "usury_cap": 0.12,
        "temple_banking": 0.20,
        "policy": "neutral",
        "last_crisis_turn": -999,
        "credit_growth": 0.0,
        "crowding_out": 0.0,
        "private_investment": initial_output * 0.08,
    }


def _initial_trade_state() -> dict[str, Any]:
    world_prices = {key: finite(spec["world_price"], 1.0) for key, spec in GOODS.items()}
    return {
        "world_prices": world_prices,
        "domestic_prices": dict(world_prices),
        "exports": {key: 0.0 for key in GOODS},
        "imports": {key: 0.0 for key in GOODS},
        "trade_balance": 0.0,
        "current_account": 0.0,
        "import_dependency": 0.0,
        "terms_of_trade": 1.0,
        "exchange_rate": 1.0,
        "foreign_confidence": 0.72,
        "embargo_exposure": 0.0,
        "trade_openness": 0.35,
    }


def _initial_innovation_state() -> dict[str, Any]:
    return {
        "research_stock": 0.0,
        "cumulative_science_spending": 0.0,
        "diffusion": 0.18,
        "breakthroughs": 0,
        "sector_technology": {key: 1.0 for key in SECTOR_KEYS},
        "last_breakthrough_turn": -999,
        "military_technology": 1.0,
    }


def _initial_interest_groups() -> dict[str, dict[str, float]]:
    return {
        "elites": {"influence": 0.31, "satisfaction": 0.58, "rents": 0.0},
        "plebs": {"influence": 0.24, "satisfaction": 0.56, "rents": 0.0},
        "military": {"influence": 0.20, "satisfaction": 0.60, "rents": 0.0},
        "merchants": {"influence": 0.17, "satisfaction": 0.59, "rents": 0.0},
        "priests": {"influence": 0.08, "satisfaction": 0.62, "rents": 0.0},
    }


def _initial_state(player: Any, context: dict[str, Any]) -> dict[str, Any]:
    population = _province_population(context)
    capital = _province_capital(context)
    initial_output = max(80.0, 1.9 * (capital ** DEFAULT_CONFIG.capital_alpha) * ((population * 0.43) ** (1.0 - DEFAULT_CONFIG.capital_alpha)))
    initial_money = max(600.0, finite(getattr(player, "gold", 200), 200) * 2.5 + initial_output * 2.2)
    initial_velocity = 1.75
    sectoral_capital = {key: capital * share for key, share in DEFAULT_SECTOR_CAPITAL_SHARES.items()}
    return {
        "version": ECONOMY_VERSION,
        "population": population,
        "carrying_capacity": _province_carrying_capacity(context),
        "capital_stock": capital,
        "infrastructure": 28.0 + 5.0 * max(0, int(context.get("province_count", 0))),
        "human_capital": 22.0,
        "productivity": 1.0,
        "money_supply": initial_money,
        "price_level": 1.0,
        "velocity": initial_velocity,
        "monetary_anchor": initial_money * initial_velocity / initial_output,
        "inflation": 0.0,
        "expected_inflation": 0.0,
        "grain_price": 1.0,
        "wage_index": 1.0,
        "unemployment": 0.08,
        "tax_rate": 0.22,
        "tariff_rate": 0.08,
        "tax_capacity": 0.48,
        "corruption": 0.12,
        "confidence": 0.72,
        "inequality": 0.35,
        "debt": 0.0,
        "interest_rate": 0.045,
        "arrears": 0.0,
        "fiscal_stance": "balanced",
        "coin_standard": "managed",
        "budget_shares": dict(DEFAULT_BUDGET_SHARES),
        "automatic_debt_repayment": True,
        "grain_subsidy": True,
        "strategic_grain_target": DEFAULT_CONFIG.default_reserve_turns,
        "sector_policy": "balanced",
        "automation": {
            "enabled": True,
            "doctrine": "balanced",
            "last_reconfigured_turn": 0,
            "stabilizer_uses": 0,
            "last_stabilizer_income": 0.0,
        },
        "sectoral_capital": sectoral_capital,
        "sectoral_labor_share": dict(DEFAULT_SECTOR_LABOR_SHARES),
        "sectoral_productivity": dict(DEFAULT_SECTOR_PRODUCTIVITY),
        "sectoral_depreciation": dict(DEFAULT_SECTOR_DEPRECIATION),
        "sectoral_output": {key: initial_output * DEFAULT_SECTOR_LABOR_SHARES[key] for key in SECTOR_KEYS},
        "sectoral_profitability": {key: 1.0 for key in SECTOR_KEYS},
        "demographics": _initial_demographics(population, context),
        "financial": _initial_financial_state(initial_output, initial_money),
        "trade": _initial_trade_state(),
        "innovation": _initial_innovation_state(),
        "interest_groups": _initial_interest_groups(),
        "conquest": {
            "city_spoils": 0.0,
            "province_indemnities": 0.0,
            "grain_requisitions": 0.0,
            "captives": 0.0,
            "capital_transfers": 0.0,
            "history": [],
        },
        "soil_fertility": 1.0,
        "resource_depletion": 0.04,
        "active_shocks": [],
        "shock_history": [],
        "last_shock_turn": -1,
        "last_statement": {},
        "history": [],
        "ledger": [],
        "flow_of_funds_history": [],
        "last_turn_processed": 0,
        "pending_minting": 0.0,
        "pending_bond_issue": 0.0,
        "pending_debt_repayment": 0.0,
        "last_real_output": initial_output,
        "fiscal": {
            "last_realized_revenue": 0.0,
            "last_realized_stabilizable_revenue": 0.0,
            "last_realized_expense": 0.0,
            "last_realized_balance": 0.0,
            "last_candidate_revenue": 0.0,
            "last_policy_signature": "",
            "last_province_count": int(context.get("province_count", 0)),
            "history": [],
        },
    }


def _merge_defaults(target: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key, value in defaults.items():
        if key not in target or target[key] is None:
            target[key] = _deepcopy(value)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge_defaults(target[key], value)
    return target


def migrate_economy_state(player: Any, state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Мигрирует сохранения v1/v2 без потери старых макропоказателей."""
    defaults = _initial_state(player, context)
    old_version = int(finite(state.get("version", 0), 0))
    _merge_defaults(state, defaults)

    # v1 хранила только агрегированный капитал и население.
    if old_version < 2:
        capital = max(20.0, finite(state.get("capital_stock", defaults["capital_stock"])))
        state["sectoral_capital"] = {
            key: capital * DEFAULT_SECTOR_CAPITAL_SHARES[key] for key in SECTOR_KEYS
        }
        population = max(20.0, finite(state.get("population", defaults["population"])))
        state["demographics"] = _initial_demographics(population, context)

    # v2 могла иметь сектора, но ещё не имела финансового рынка и платёжного баланса.
    if old_version < 3:
        initial_output = max(20.0, finite(state.get("last_real_output", defaults["last_real_output"])))
        initial_money = max(10.0, finite(state.get("money_supply", defaults["money_supply"])))
        _merge_defaults(state.setdefault("financial", {}), _initial_financial_state(initial_output, initial_money))
        _merge_defaults(state.setdefault("trade", {}), _initial_trade_state())
        _merge_defaults(state.setdefault("innovation", {}), _initial_innovation_state())
        _merge_defaults(state.setdefault("interest_groups", {}), _initial_interest_groups())

    # v4 добавляет отдельный счёт военных трофеев и капитальных трансфертов.
    if old_version < 4:
        _merge_defaults(state.setdefault("conquest", {}), defaults["conquest"])

    # v5 вводит единый фискальный мост между макромоделью и игровой казной.
    # Последняя реально применённая ведомость становится якорем прогноза, чтобы
    # показатель «золото за ход» не прыгал на тысячи без понятной причины.
    if old_version < 5:
        fiscal = state.setdefault("fiscal", {})
        _merge_defaults(fiscal, defaults["fiscal"])
        last = state.get("last_statement") if isinstance(state.get("last_statement"), dict) else {}
        if finite(fiscal.get("last_realized_revenue", 0.0)) <= 0:
            fiscal["last_realized_revenue"] = max(0.0, finite(last.get("revenue_total", 0.0)))
        if finite(fiscal.get("last_realized_expense", 0.0)) <= 0:
            fiscal["last_realized_expense"] = max(0.0, finite(last.get("expense_total", 0.0)))
        if not finite(fiscal.get("last_realized_balance", 0.0)) and last:
            fiscal["last_realized_balance"] = finite(last.get("overall_balance", 0.0))

    state["version"] = ECONOMY_VERSION
    return state


def ensure_economy_state(player: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
    context = context if isinstance(context, dict) else {}
    state = getattr(player, "economy", None)
    if not isinstance(state, dict):
        state = {}
        setattr(player, "economy", state)
    migrate_economy_state(player, state, context)

    state["budget_shares"] = normalize_budget_shares(state.get("budget_shares"))
    state["sectoral_labor_share"] = normalize_sector_shares(state.get("sectoral_labor_share"), DEFAULT_SECTOR_LABOR_SHARES)
    state["fiscal_stance"] = state.get("fiscal_stance") if state.get("fiscal_stance") in FISCAL_STANCES else "balanced"
    state["coin_standard"] = state.get("coin_standard") if state.get("coin_standard") in COIN_STANDARDS else "managed"
    state["sector_policy"] = state.get("sector_policy") if state.get("sector_policy") in SECTOR_POLICIES else "balanced"

    numeric_limits = {
        "population": (20.0, 100_000.0),
        "carrying_capacity": (50.0, 150_000.0),
        "capital_stock": (20.0, 100_000_000.0),
        "infrastructure": (0.0, 1_000.0),
        "human_capital": (0.0, 1_000.0),
        "productivity": (0.10, 50.0),
        "money_supply": (10.0, 10_000_000_000.0),
        "price_level": (0.05, 1_000.0),
        "velocity": (0.10, 15.0),
        "monetary_anchor": (0.0001, 10_000_000.0),
        "inflation": (-0.80, 25.0),
        "expected_inflation": (-0.50, 15.0),
        "grain_price": (0.05, 500.0),
        "wage_index": (0.05, 500.0),
        "unemployment": (0.0, 0.75),
        "tax_rate": (0.0, 0.65),
        "tariff_rate": (0.0, 0.45),
        "tax_capacity": (0.03, 0.99),
        "corruption": (0.005, 0.95),
        "confidence": (0.01, 0.995),
        "inequality": (0.03, 0.95),
        "debt": (0.0, 10_000_000_000.0),
        "interest_rate": (0.0, 5.0),
        "arrears": (0.0, 10_000_000_000.0),
        "soil_fertility": (0.25, 1.35),
        "resource_depletion": (0.0, 0.95),
        "strategic_grain_target": (0.0, 20.0),
    }
    for key, (low, high) in numeric_limits.items():
        state[key] = clamp(finite(state.get(key, low)), low, high)

    for key in SECTOR_KEYS:
        state["sectoral_capital"][key] = clamp(finite(state["sectoral_capital"].get(key, 1.0)), 1.0, 100_000_000.0)
        state["sectoral_productivity"][key] = clamp(finite(state["sectoral_productivity"].get(key, 1.0)), 0.10, 25.0)
        state["sectoral_depreciation"][key] = clamp(finite(state["sectoral_depreciation"].get(key, DEFAULT_SECTOR_DEPRECIATION[key])), 0.005, 0.25)
        state["sectoral_output"][key] = max(0.0, finite(state["sectoral_output"].get(key, 0.0)))
        state["sectoral_profitability"][key] = clamp(finite(state["sectoral_profitability"].get(key, 1.0)), 0.01, 100.0)

    demo = state["demographics"]
    for key in ("free_population", "slave_population", "urban_population", "rural_population"):
        demo[key] = max(0.0, finite(demo.get(key, 0.0)))
    total = demo["free_population"] + demo["slave_population"]
    if total <= 0:
        demo.update(_initial_demographics(state["population"], context))
        total = demo["free_population"] + demo["slave_population"]
    state["population"] = clamp(total, 20.0, 100_000.0)
    urban_total = demo["urban_population"] + demo["rural_population"]
    if urban_total <= 0:
        demo["urban_population"] = state["population"] * 0.25
        demo["rural_population"] = state["population"] - demo["urban_population"]
    else:
        scale = state["population"] / urban_total
        demo["urban_population"] *= scale
        demo["rural_population"] *= scale
    demo["slave_ratio"] = clamp(demo["slave_population"] / max(1.0, state["population"]), 0.0, 0.85)
    demo["urbanization_rate"] = clamp(demo["urban_population"] / max(1.0, state["population"]), 0.02, 0.95)
    demo["slave_revolt_risk"] = clamp(finite(demo.get("slave_revolt_risk", 0.02)), 0.0, 0.95)

    financial = state["financial"]
    financial["policy"] = financial.get("policy") if financial.get("policy") in CREDIT_POLICIES else "neutral"
    for key, low, high in (
        ("private_credit", 0.0, 10_000_000_000.0),
        ("deposit_base", 1.0, 10_000_000_000.0),
        ("banking_health", 0.01, 0.99),
        ("credit_to_gdp", 0.0, 20.0),
        ("market_rate", 0.0, 3.0),
        ("loan_demand", 0.0, 10_000_000_000.0),
        ("loan_supply", 0.0, 10_000_000_000.0),
        ("leverage", 0.0, 20.0),
        ("usury_cap", 0.03, 0.50),
        ("temple_banking", 0.0, 1.0),
        ("credit_growth", -0.95, 5.0),
        ("crowding_out", 0.0, 1.0),
        ("private_investment", 0.0, 10_000_000_000.0),
    ):
        financial[key] = clamp(finite(financial.get(key, low)), low, high)

    trade = state["trade"]
    for map_key in ("world_prices", "domestic_prices", "exports", "imports"):
        if not isinstance(trade.get(map_key), dict):
            trade[map_key] = {}
        for good, spec in GOODS.items():
            default = spec["world_price"] if "prices" in map_key else 0.0
            trade[map_key][good] = max(0.0, finite(trade[map_key].get(good, default)))

    innovation = state["innovation"]
    if not isinstance(innovation.get("sector_technology"), dict):
        innovation["sector_technology"] = {}
    for key in SECTOR_KEYS:
        innovation["sector_technology"][key] = clamp(finite(innovation["sector_technology"].get(key, 1.0)), 0.5, 20.0)

    for key in ("history", "ledger", "active_shocks", "shock_history", "flow_of_funds_history"):
        if not isinstance(state.get(key), list):
            state[key] = []
    if not isinstance(state.get("last_statement"), dict):
        state["last_statement"] = {}
    conquest = state.setdefault("conquest", {})
    _merge_defaults(conquest, _initial_state(player, context)["conquest"])
    if not isinstance(conquest.get("history"), list):
        conquest["history"] = []
    conquest["history"] = [row for row in conquest["history"] if isinstance(row, dict)][-240:]
    for key in ("city_spoils", "province_indemnities", "grain_requisitions", "captives", "capital_transfers"):
        conquest[key] = max(0.0, finite(conquest.get(key, 0.0)))

    fiscal = state.setdefault("fiscal", {})
    _merge_defaults(fiscal, _initial_state(player, context)["fiscal"])
    for key in (
        "last_realized_revenue", "last_realized_expense",
        "last_candidate_revenue",
    ):
        fiscal[key] = max(0.0, finite(fiscal.get(key, 0.0)))
    fiscal["last_realized_balance"] = finite(fiscal.get("last_realized_balance", 0.0))
    fiscal["last_policy_signature"] = str(fiscal.get("last_policy_signature", ""))
    fiscal["last_province_count"] = max(
        0,
        int(finite(fiscal.get("last_province_count", context.get("province_count", 0)), 0)),
    )
    if not isinstance(fiscal.get("history"), list):
        fiscal["history"] = []
    fiscal["history"] = [row for row in fiscal["history"] if isinstance(row, dict)][-120:]
    return state


def _active_shock_modifiers(state: dict[str, Any]) -> dict[str, Any]:
    sector = {key: 1.0 for key in SECTOR_KEYS}
    result: dict[str, Any] = {
        "sector": sector,
        "mortality": 0.0,
        "fertility": 0.0,
        "confidence": 0.0,
        "banking": 0.0,
        "trade": 0.0,
        "price": 0.0,
        "slave_revolt": 0.0,
    }
    for shock in state.get("active_shocks", []):
        if not isinstance(shock, dict) or int(finite(shock.get("remaining", 0))) <= 0:
            continue
        kind = str(shock.get("kind", ""))
        magnitude = clamp(finite(shock.get("magnitude", 0.1)), 0.01, 0.90)
        if kind == "epidemic":
            result["mortality"] += 0.012 + 0.035 * magnitude
            sector["commerce"] *= 1.0 - 0.28 * magnitude
            sector["manufacturing"] *= 1.0 - 0.18 * magnitude
        elif kind in {"drought", "flood", "locusts"}:
            sector["agriculture"] *= 1.0 - (0.35 if kind == "drought" else 0.28 if kind == "flood" else 0.42) * magnitude
        elif kind == "mine_discovery":
            sector["mining"] *= 1.0 + 0.32 * magnitude
        elif kind == "mine_depletion":
            sector["mining"] *= 1.0 - 0.34 * magnitude
        elif kind == "currency_crisis":
            result["confidence"] -= 0.18 * magnitude
            result["price"] += 0.55 * magnitude
            result["trade"] -= 0.16 * magnitude
        elif kind == "banking_panic":
            result["banking"] -= 0.42 * magnitude
            sector["construction"] *= 1.0 - 0.24 * magnitude
            sector["manufacturing"] *= 1.0 - 0.18 * magnitude
        elif kind == "slave_revolt":
            result["slave_revolt"] += magnitude
            sector["agriculture"] *= 1.0 - 0.35 * magnitude
            sector["mining"] *= 1.0 - 0.42 * magnitude
        elif kind == "trade_boom":
            result["trade"] += 0.26 * magnitude
            sector["commerce"] *= 1.0 + 0.24 * magnitude
            sector["manufacturing"] *= 1.0 + 0.10 * magnitude
    return result


def _demographic_labor_supply(state: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    demo = state["demographics"]
    effective_unrest = clamp(finite(context.get("effective_unrest", getattr(context, "unrest", 0))), 0.0, 100.0)
    morale = clamp(finite(context.get("morale", 70)), 0.0, 100.0)
    free_population = max(1.0, finite(demo["free_population"]))
    slave_population = max(0.0, finite(demo["slave_population"]))
    participation = clamp(
        _config(context).labor_participation
        - 0.0015 * effective_unrest
        + 0.00045 * morale
        + 0.018 * state["confidence"],
        0.18,
        0.59,
    )
    free_labor = free_population * participation * (1.0 - state["unemployment"])
    slave_labor = slave_population * clamp(0.72 - 0.20 * demo["slave_revolt_risk"], 0.30, 0.78)
    shares = normalize_sector_shares(state["sectoral_labor_share"], DEFAULT_SECTOR_LABOR_SHARES)
    sector_labor: dict[str, float] = {}
    free_sector: dict[str, float] = {}
    slave_sector: dict[str, float] = {}
    slave_weights = normalize_sector_shares(
        {
            "agriculture": shares["agriculture"] * 1.45,
            "mining": shares["mining"] * 1.80,
            "manufacturing": shares["manufacturing"] * 0.70,
            "construction": shares["construction"] * 1.00,
            "commerce": shares["commerce"] * 0.25,
        },
        DEFAULT_SECTOR_LABOR_SHARES,
    )
    for key in SECTOR_KEYS:
        free_sector[key] = free_labor * shares[key]
        slave_sector[key] = slave_labor * slave_weights[key]
        sector_labor[key] = free_sector[key] + slave_sector[key] * SLAVE_PRODUCTIVITY[key]
    return {
        "participation": participation,
        "free_labor": free_labor,
        "slave_labor": slave_labor,
        "total_effective_labor": sum(sector_labor.values()),
        "sector_labor": sector_labor,
        "free_sector_labor": free_sector,
        "slave_sector_labor": slave_sector,
        "labor_shares": shares,
    }


def allocate_labor_and_capital(
    player: Any,
    context: dict[str, Any],
    state: dict[str, Any] | None = None,
    mutate: bool = False,
) -> dict[str, Any]:
    """Фрикционно перераспределяет труд и капитал к более доходным секторам."""
    state = ensure_economy_state(player, context) if state is None else state
    policy = SECTOR_POLICIES[state["sector_policy"]]["weights"]
    endowments = _sector_endowments(context)
    previous_output = state["sectoral_output"]
    previous_labor = normalize_sector_shares(state["sectoral_labor_share"], DEFAULT_SECTOR_LABOR_SHARES)
    total_capital = sum(max(1.0, finite(v)) for v in state["sectoral_capital"].values())
    capital_shares = normalize_sector_shares(state["sectoral_capital"], DEFAULT_SECTOR_CAPITAL_SHARES)

    desired_scores: dict[str, float] = {}
    for key in SECTOR_KEYS:
        output = max(1.0, finite(previous_output.get(key, 1.0)))
        capital = max(1.0, finite(state["sectoral_capital"].get(key, 1.0)))
        labor_share = max(0.01, previous_labor[key])
        marginal_return = output / (capital ** 0.45 * labor_share ** 0.35)
        desired_scores[key] = max(0.05, marginal_return * policy[key] * endowments[key])
    desired_labor = normalize_sector_shares(desired_scores, DEFAULT_SECTOR_LABOR_SHARES)
    desired_capital = normalize_sector_shares(
        {key: desired_scores[key] / max(0.01, state["sectoral_depreciation"][key]) ** 0.25 for key in SECTOR_KEYS},
        DEFAULT_SECTOR_CAPITAL_SHARES,
    )

    unrest = clamp(finite(context.get("effective_unrest", 0)), 0.0, 100.0)
    infrastructure = state["infrastructure"]
    human = state["human_capital"]
    labor_mobility = clamp(
        _config(context).labor_mobility_base + infrastructure / 1800.0 + human / 3000.0 - unrest / 1700.0,
        0.008,
        0.16,
    )
    capital_mobility = clamp(
        _config(context).capital_mobility_base + state["financial"]["banking_health"] / 90.0 + infrastructure / 4000.0 - unrest / 2600.0,
        0.004,
        0.095,
    )
    projected_labor = normalize_sector_shares(
        {key: previous_labor[key] + labor_mobility * (desired_labor[key] - previous_labor[key]) for key in SECTOR_KEYS},
        DEFAULT_SECTOR_LABOR_SHARES,
    )
    projected_capital_share = normalize_sector_shares(
        {key: capital_shares[key] + capital_mobility * (desired_capital[key] - capital_shares[key]) for key in SECTOR_KEYS},
        DEFAULT_SECTOR_CAPITAL_SHARES,
    )
    projected_capital = {key: total_capital * projected_capital_share[key] for key in SECTOR_KEYS}
    if mutate:
        state["sectoral_labor_share"] = projected_labor
        state["sectoral_capital"] = projected_capital
        state["capital_stock"] = sum(projected_capital.values())
    return {
        "labor_shares": projected_labor,
        "capital_shares": projected_capital_share,
        "capital": projected_capital,
        "desired_labor_shares": desired_labor,
        "desired_capital_shares": desired_capital,
        "labor_mobility": labor_mobility,
        "capital_mobility": capital_mobility,
    }


def _sectoral_snapshot(player: Any, context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    allocation = allocate_labor_and_capital(player, context, state, mutate=False)
    labor_data = _demographic_labor_supply(state, context)
    shock_mods = _active_shock_modifiers(state)
    endowments = _sector_endowments(context)
    innovation = state["innovation"]["sector_technology"]
    alpha = _config(context).capital_alpha
    unrest = clamp(finite(context.get("effective_unrest", 0)), 0.0, 100.0)
    morale = clamp(finite(context.get("morale", 70)), 0.0, 100.0)
    romanization = clamp(finite(context.get("avg_romanization", 35.0)), 0.0, 100.0)
    infrastructure_factor = 0.62 + 0.46 * math.tanh(state["infrastructure"] / 110.0)
    institution_factor = clamp(0.55 + 0.58 * state["tax_capacity"] * (1.0 - state["corruption"]), 0.28, 1.12)
    security_factor = clamp(1.08 - 0.0062 * unrest + 0.0007 * morale, 0.30, 1.14)
    integration_factor = 0.68 + 0.32 * romanization / 100.0
    soil = state["soil_fertility"]
    depletion = state["resource_depletion"]

    labor_shares = allocation["labor_shares"]
    total_effective_labor = max(10.0, labor_data["total_effective_labor"])
    sector_labor = {key: max(1.0, total_effective_labor * labor_shares[key]) for key in SECTOR_KEYS}
    base_output: dict[str, float] = {}
    for key in SECTOR_KEYS:
        capital = max(1.0, allocation["capital"][key])
        labor = sector_labor[key]
        productivity = (
            state["productivity"]
            * state["sectoral_productivity"][key]
            * innovation[key]
            * endowments[key]
            * shock_mods["sector"][key]
        )
        if key == "agriculture":
            productivity *= soil
        elif key == "mining":
            productivity *= 1.0 - 0.55 * depletion
        elif key == "commerce":
            productivity *= clamp(0.72 + 0.44 * state["confidence"] + shock_mods["trade"], 0.35, 1.35)
        elif key == "construction":
            productivity *= 0.78 + 0.35 * infrastructure_factor
        base_output[key] = max(
            1.0,
            _config(context).output_scale
            * productivity
            * capital ** alpha
            * labor ** (1.0 - alpha)
            * infrastructure_factor
            * institution_factor
            * security_factor
            * integration_factor,
        )

    # Два шага fixed-point приближения матрицы input-output.
    output = dict(base_output)
    bottlenecks = {key: 1.0 for key in SECTOR_KEYS}
    for _ in range(2):
        new_output: dict[str, float] = {}
        for consumer in SECTOR_KEYS:
            availability_scores: list[float] = []
            for supplier, coefficient in INPUT_OUTPUT[consumer].items():
                required = max(0.01, base_output[consumer] * coefficient)
                available = max(0.01, output[supplier] * 0.34)
                availability_scores.append(clamp(available / required, 0.25, 1.15))
            supply_chain = min(availability_scores) if availability_scores else 1.0
            bottlenecks[consumer] = supply_chain
            new_output[consumer] = base_output[consumer] * (0.52 + 0.48 * supply_chain)
        output = new_output

    military_demand = max(0, int(context.get("legion_count", 0))) * 0.012
    output["manufacturing"] *= 1.0 + min(0.28, military_demand)
    output["construction"] *= 1.0 + min(0.24, finite(context.get("public_works_demand", 0.0)) / 1000.0)
    output["commerce"] *= 1.0 + 0.025 * max(0, int(context.get("trade_pacts", 0)))
    total_output = sum(output.values())
    profitability = {
        key: output[key] / max(1.0, allocation["capital"][key] * 0.55 + sector_labor[key] * 0.45)
        for key in SECTOR_KEYS
    }
    return {
        "output": output,
        "base_output": base_output,
        "total_output": total_output,
        "capital": allocation["capital"],
        "capital_shares": allocation["capital_shares"],
        "labor": sector_labor,
        "labor_shares": labor_shares,
        "profitability": profitability,
        "bottlenecks": bottlenecks,
        "labor_mobility": allocation["labor_mobility"],
        "capital_mobility": allocation["capital_mobility"],
        "free_labor": labor_data["free_labor"],
        "slave_labor": labor_data["slave_labor"],
        "participation": labor_data["participation"],
        "security_factor": security_factor,
        "institution_factor": institution_factor,
        "infrastructure_factor": infrastructure_factor,
    }


def _macro_snapshot(player: Any, context: dict[str, Any], state: dict[str, Any], sectors: dict[str, Any]) -> dict[str, float]:
    province_count = max(1, int(context.get("province_count", 1)))
    effective_unrest = clamp(finite(context.get("effective_unrest", getattr(player, "unrest", 0))), 0.0, 100.0)
    senate = clamp(finite(context.get("senate_rep", getattr(player, "senate_rep", 50))), 0.0, 100.0)
    people = clamp(finite(context.get("people_rep", getattr(player, "people_rep", 50))), 0.0, 100.0)
    population = state["population"]
    unemployment_target = clamp(
        0.045 + 0.0026 * effective_unrest
        - 0.075 * state["confidence"]
        - 0.00035 * state["infrastructure"]
        + 0.025 * max(0.0, sectors["bottlenecks"]["manufacturing"] < 0.70),
        0.02,
        0.55,
    )
    unemployment = clamp(0.72 * state["unemployment"] + 0.28 * unemployment_target, 0.0, 0.75)
    # Реальный ВВП должен точно совпадать с суммой отраслевого выпуска.
    # Старый искусственный минимум 20 создавал бухгалтерское расхождение
    # в тяжёлом кризисе, когда пять секторов вместе производили меньше 20.
    real_output = max(1.0, sum(finite(value) for value in sectors["output"].values()))
    nominal_output = real_output * state["price_level"]
    per_capita = real_output / max(1.0, population)
    political_legitimacy = (senate + people) / 200.0
    return {
        "population": population,
        "labor": sum(sectors["labor"].values()),
        "labor_participation": sectors["participation"],
        "unemployment": unemployment,
        "real_output": real_output,
        "nominal_output": nominal_output,
        "per_capita_output": per_capita,
        "security_factor": sectors["security_factor"],
        "institution_factor": sectors["institution_factor"],
        "trade_factor": 1.0 + 0.025 * max(0, int(context.get("trade_pacts", 0))) + 0.015 * math.log1p(max(0.0, finite(context.get("trade_route_value", 0)))),
        "political_legitimacy": political_legitimacy,
        "province_count": float(province_count),
    }


def _financial_market(
    player: Any,
    context: dict[str, Any],
    state: dict[str, Any],
    macro: dict[str, float],
    sectors: dict[str, Any],
) -> dict[str, float]:
    financial = state["financial"]
    policy = CREDIT_POLICIES[financial["policy"]]
    shock_mods = _active_shock_modifiers(state)
    banking_health = clamp(financial["banking_health"] + shock_mods["banking"], 0.01, 0.99)
    nominal_output = max(1.0, macro["nominal_output"])
    private_savings_rate = clamp(
        _config(context).private_saving_base
        + _config(context).private_saving_confidence * state["confidence"]
        - _config(context).private_saving_tax_penalty * state["tax_rate"]
        - 0.06 * max(0.0, state["inflation"]),
        0.025,
        0.32,
    )
    private_savings = nominal_output * private_savings_rate
    deposit_base = max(1.0, financial["deposit_base"])
    temple_liquidity = deposit_base * (0.10 + 0.35 * financial["temple_banking"])
    loan_supply = (private_savings + temple_liquidity) * banking_health

    replacement_demand = sum(
        sectors["capital"][key] * state["sectoral_depreciation"][key]
        for key in SECTOR_KEYS
    ) * state["price_level"]
    expansion_demand = nominal_output * clamp(0.07 + 0.14 * state["confidence"], 0.03, 0.22)
    loan_demand = replacement_demand + expansion_demand

    debt_ratio = state["debt"] / nominal_output
    sovereign_absorption = clamp(0.06 + 0.22 * debt_ratio, 0.0, 0.72)
    crowding_out = clamp(sovereign_absorption * (0.55 + 0.45 * (1.0 - banking_health)), 0.0, 0.85)
    effective_supply = max(1.0, loan_supply * (1.0 - crowding_out))
    scarcity = loan_demand / effective_supply
    expected_inflation = max(-0.15, state["expected_inflation"])
    risk = (
        0.018
        + 0.085 * (1.0 - state["confidence"])
        + 0.075 * (1.0 - banking_health)
        + 0.060 * max(0.0, financial["leverage"] - 1.0)
    )
    market_rate = clamp(
        0.025 + 0.42 * expected_inflation + 0.055 * math.log(max(0.20, scarcity)) + risk + policy["rate"],
        0.015,
        0.80,
    )
    rationing = 1.0
    if market_rate > financial["usury_cap"]:
        rationing = clamp(financial["usury_cap"] / max(0.001, market_rate), 0.18, 1.0)
    available_credit = min(effective_supply, loan_demand) * rationing
    target_credit_ratio = clamp(
        0.16 + 0.62 * banking_health * state["confidence"]
        + 0.55 * policy["credit_growth"]
        - 0.35 * crowding_out,
        0.04,
        1.60,
    )
    desired_credit = max(0.0, nominal_output * target_credit_ratio)
    credit_change = desired_credit - financial["private_credit"]
    private_investment = max(0.0, min(loan_demand, private_savings * 0.70 + max(0.0, credit_change)))
    credit_to_gdp = desired_credit / nominal_output
    leverage = desired_credit / max(1.0, deposit_base + private_savings)
    sovereign_rate = clamp(
        market_rate + 0.018 + 0.105 * sigmoid((debt_ratio - 0.85) * 3.2) + 0.055 * state["arrears"] / nominal_output,
        0.02,
        1.20,
    )
    return {
        "private_savings_rate": private_savings_rate,
        "private_savings": private_savings,
        "deposit_base": deposit_base,
        "banking_health": banking_health,
        "loan_supply": loan_supply,
        "effective_loan_supply": effective_supply,
        "loan_demand": loan_demand,
        "market_rate": market_rate,
        "sovereign_rate": sovereign_rate,
        "crowding_out": crowding_out,
        "rationing": rationing,
        "available_credit": available_credit,
        "desired_private_credit": desired_credit,
        "credit_change": credit_change,
        "private_investment": private_investment,
        "credit_to_gdp": credit_to_gdp,
        "leverage": leverage,
    }


def _interest_rate(state: dict[str, Any], macro: dict[str, float]) -> float:
    """Совместимый wrapper для старого API; новая ставка берётся из рынка кредита."""
    debt_ratio = state["debt"] / max(1.0, macro["nominal_output"])
    inflation = max(0.0, state["expected_inflation"])
    financial = state.get("financial", {})
    market = finite(financial.get("market_rate", 0.08), 0.08)
    return clamp(
        market + 0.012 + 0.095 * sigmoid((debt_ratio - 0.90) * 3.0) + 0.045 * inflation,
        0.02,
        1.20,
    )


def _world_price(good: str, turn: int, state: dict[str, Any]) -> float:
    base = finite(GOODS[good]["world_price"], 1.0)
    phase = (_stable_seed("world-price", good) % 6283) / 1000.0
    cycle = 1.0 + 0.08 * math.sin(turn / (9.0 + len(good)) + phase)
    trend = 1.0 + 0.0005 * max(0, turn)
    shock = 1.0
    for item in state.get("active_shocks", []):
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        magnitude = clamp(finite(item.get("magnitude", 0.1)), 0.0, 0.9)
        if good == "grain" and kind in {"drought", "flood", "locusts"}:
            shock *= 1.0 + 0.35 * magnitude
        elif good == "metals" and kind == "mine_depletion":
            shock *= 1.0 + 0.22 * magnitude
        elif good == "metals" and kind == "mine_discovery":
            shock *= 1.0 - 0.18 * magnitude
        elif kind == "trade_boom":
            shock *= 1.0 + 0.05 * magnitude
    return max(0.10, base * cycle * trend * shock)


def _external_trade(
    player: Any,
    context: dict[str, Any],
    state: dict[str, Any],
    macro: dict[str, float],
    sectors: dict[str, Any],
) -> dict[str, Any]:
    trade_state = state["trade"]
    turn = int(getattr(player, "turn", 1))
    population = max(1.0, state["population"])
    legion_count = max(0, int(context.get("legion_count", 0)))
    openness = clamp(
        0.22
        + 0.045 * max(0, int(context.get("trade_pacts", 0)))
        + 0.018 * math.log1p(max(0.0, finite(context.get("trade_route_value", 0))))
        + 0.20 * state["confidence"]
        - 0.55 * clamp(finite(context.get("embargo_level", 0.0)), 0.0, 1.0)
        + _active_shock_modifiers(state)["trade"],
        0.03,
        0.92,
    )
    standard = COIN_STANDARDS[state["coin_standard"]]
    foreign_confidence = clamp(
        0.40 + 0.48 * state["confidence"] + standard["foreign_trust"] - 0.16 * max(0.0, state["inflation"] - 0.10),
        0.05,
        0.98,
    )
    exchange_rate = clamp(
        state["price_level"] * (1.15 - 0.50 * foreign_confidence) * (1.0 + 0.45 * max(0.0, state["inflation"])),
        0.20,
        25.0,
    )
    output = sectors["output"]
    demo = state["demographics"]
    supply = {
        "grain": output["agriculture"] * 0.72 + max(0.0, finite(context.get("special_grain_income", 0.0))),
        "metals": output["mining"] * 0.70 + max(0.0, finite(context.get("metal_output_bonus", 0.0))),
        "wine_oil": output["agriculture"] * 0.18,
        "manufactures": output["manufacturing"] * 0.66,
        "luxury": output["manufacturing"] * 0.11 + output["commerce"] * 0.10,
        "slaves": max(0.0, demo["slave_population"] * 0.012 + demo.get("captives_last_turn", 0.0) * 0.20),
    }
    demand = {
        "grain": 8.0 + population * 0.038 + legion_count * 5.0,
        "metals": 3.0 + output["construction"] * 0.16 + output["manufacturing"] * 0.19 + legion_count * 1.9,
        "wine_oil": 2.0 + population * (0.010 + 0.010 * state["confidence"]),
        "manufactures": 5.0 + population * 0.012 + output["construction"] * 0.12 + legion_count * 2.1,
        "luxury": 1.0 + population * 0.003 * (0.55 + state["inequality"] + state["confidence"]),
        "slaves": 0.6 + output["agriculture"] * 0.012 + output["mining"] * 0.018,
    }
    exports: dict[str, float] = {}
    imports: dict[str, float] = {}
    world_prices: dict[str, float] = {}
    domestic_prices: dict[str, float] = {}
    export_value = import_value = 0.0
    weighted_export_price = weighted_import_price = 0.0
    weighted_export_qty = weighted_import_qty = 0.0
    for good, spec in GOODS.items():
        world = _world_price(good, turn, state)
        scarcity = demand[good] / max(0.01, supply[good])
        domestic = clamp(world * (scarcity ** 0.34) * exchange_rate ** 0.22, world * 0.35, world * 6.0)
        surplus = max(0.0, supply[good] - demand[good])
        deficit = max(0.0, demand[good] - supply[good])
        export_qty = surplus * openness * finite(spec["export_elasticity"], 0.5) * foreign_confidence
        import_qty = deficit * openness * finite(spec["import_elasticity"], 0.5) / max(0.45, exchange_rate ** 0.18)
        if good == "slaves":
            export_qty = min(export_qty, demo["slave_population"] * 0.003)
            import_qty = min(import_qty, max(0.0, population * 0.004))
        exports[good] = export_qty
        imports[good] = import_qty
        world_prices[good] = world
        domestic_prices[good] = domestic
        export_value += export_qty * world / max(0.30, exchange_rate)
        import_value += import_qty * world * exchange_rate
        weighted_export_price += export_qty * world
        weighted_import_price += import_qty * world
        weighted_export_qty += export_qty
        weighted_import_qty += import_qty
    trade_balance = export_value - import_value
    current_account = trade_balance + max(0.0, finite(context.get("tribute_income", 0.0))) - max(0.0, finite(context.get("tribute_paid", 0.0)))
    total_demand = sum(demand.values())
    import_dependency = sum(imports.values()) / max(1.0, total_demand)
    export_price_index = weighted_export_price / max(0.01, weighted_export_qty)
    import_price_index = weighted_import_price / max(0.01, weighted_import_qty)
    terms_of_trade = clamp(export_price_index / max(0.01, import_price_index), 0.25, 4.0)
    return {
        "supply": supply,
        "demand": demand,
        "exports": exports,
        "imports": imports,
        "world_prices": world_prices,
        "domestic_prices": domestic_prices,
        "export_value": export_value,
        "import_value": import_value,
        "trade_balance": trade_balance,
        "current_account": current_account,
        "import_dependency": import_dependency,
        "terms_of_trade": terms_of_trade,
        "exchange_rate": exchange_rate,
        "foreign_confidence": foreign_confidence,
        "trade_openness": openness,
        "embargo_exposure": clamp(finite(context.get("embargo_level", 0.0)), 0.0, 1.0),
    }



def _automation_spec(state: dict[str, Any]) -> dict[str, Any]:
    automation = state.get("automation") if isinstance(state.get("automation"), dict) else {}
    doctrine = str(automation.get("doctrine", "balanced"))
    return AUTOMATION_DOCTRINES.get(doctrine, AUTOMATION_DOCTRINES["balanced"])


def _legacy_economic_magic_modifiers(
    context: dict[str, Any],
    state: dict[str, Any],
    macro: dict[str, float],
    sectors: dict[str, Any],
    finance: dict[str, float],
    trade: dict[str, Any],
) -> list[dict[str, Any]]:
    """Много мелких финансовых шестерёнок, каждая даёт или отнимает копеечку."""
    nominal = max(1.0, finite(macro.get("nominal_output", 0.0)))
    population = max(1.0, finite(macro.get("population", state.get("population", 1.0))))
    rows: list[dict[str, Any]] = []

    def add(key: str, label: str, value: Any, gold: float, category: str) -> None:
        rows.append({
            "key": key,
            "label": label,
            "value": value,
            "gold_per_turn": round(finite(gold), 2),
            "category": category,
        })

    commerce_profit = finite(sectors.get("profitability", {}).get("commerce", 1.0), 1.0)
    capital = max(0.0, finite(macro.get("capital_stock", state.get("capital_stock", 0.0))))
    infrastructure = max(0.0, finite(macro.get("infrastructure", state.get("infrastructure", 0.0))))
    human_capital = max(0.0, finite(macro.get("human_capital", state.get("human_capital", 0.0))))
    velocity = finite(macro.get("velocity", state.get("velocity", 1.0)), 1.0)
    banking = clamp(finite(macro.get("banking_health", finance.get("banking_health", 0.5))), 0.0, 1.0)
    confidence = clamp(finite(macro.get("confidence", state.get("confidence", 0.5))), 0.0, 1.0)
    urbanization = clamp(finite(macro.get("urbanization", state.get("demographics", {}).get("urbanization_rate", 0.2))), 0.0, 1.0)
    tax_capacity = clamp(finite(macro.get("tax_capacity", state.get("tax_capacity", 0.4))), 0.0, 1.0)
    terms = clamp(finite(trade.get("terms_of_trade", 1.0)), 0.25, 4.0)
    trade_balance = finite(trade.get("trade_balance", 0.0))
    money_supply = max(1.0, finite(macro.get("money_supply", state.get("money_supply", 1.0))))
    deposits = max(0.0, finite(state.get("financial", {}).get("deposit_base", 0.0)))
    credit_ratio = clamp(finite(macro.get("credit_to_gdp", finance.get("credit_to_gdp", 0.0))), 0.0, 5.0)
    romanization = clamp(finite(context.get("avg_romanization", 0.0)), 0.0, 100.0)
    route_value = max(0.0, finite(context.get("trade_route_value", 0.0)))
    trade_pacts = max(0, int(finite(context.get("trade_pacts", 0))))
    building_count = max(0, int(finite(context.get("municipal_building_count", 0))))

    add("gdp_dividend", "Дивиденд валового продукта", round(nominal, 1), nominal * 0.008, "Макроэкономика")
    add("capital_turnover", "Оборот основного капитала", round(capital, 1), capital * 0.010, "Капитал")
    add("money_velocity", "Скорость обращения денег", round(velocity, 3), clamp((velocity - 1.40) * nominal * 0.012, -8.0, 15.0), "Деньги")
    add("monetization", "Монетизация хозяйства", round(money_supply / nominal, 3), clamp(math.log1p(money_supply / nominal) * 2.2, 0.0, 10.0), "Деньги")
    add("banking_health", "Банковское здоровье", f"{banking:.1%}", clamp((banking - 0.45) * nominal * 0.015, -8.0, 16.0), "Финансы")
    add("liquidity", "Ликвидность вкладов", round(deposits / nominal, 3), clamp(deposits / nominal * 3.2, 0.0, 12.0), "Финансы")
    add("credit_multiplier", "Кредитный мультипликатор", round(credit_ratio, 3), clamp(credit_ratio * 6.0, 0.0, 18.0), "Финансы")
    add("trade_margin", "Торговая маржа", round(commerce_profit, 3), clamp((commerce_profit - 0.82) * nominal * 0.025, -8.0, 22.0), "Торговля")
    add("trade_balance", "Сальдо торгового баланса", round(trade_balance, 2), clamp(trade_balance * 0.15, -15.0, 25.0), "Торговля")
    add("terms_of_trade", "Условия торговли", round(terms, 3), clamp((terms - 1.0) * nominal * 0.010, -10.0, 18.0), "Торговля")
    add("infrastructure_rent", "Инфраструктурная рента", round(infrastructure, 1), infrastructure * 0.12, "Инфраструктура")
    add("human_capital", "Премия человеческого капитала", round(human_capital, 1), human_capital * 0.08, "Труд")
    add("agglomeration", "Урбанизационная агломерация", f"{urbanization:.1%}", population * urbanization * 0.020, "Труд")
    add("fiscal_capacity", "Фискальная ёмкость", f"{tax_capacity:.1%}", nominal * max(0.0, tax_capacity - 0.30) * 0.010, "Налоги")
    add("confidence_premium", "Премия доверия", f"{confidence:.1%}", nominal * max(-0.20, confidence - 0.45) * 0.006, "Финансы")
    add("romanization", "Романизационная налоговая премия", f"{romanization:.0f}%", romanization * 0.06, "Римская экономика")
    add("route_network", "Рента торговых маршрутов", round(route_value, 1), clamp(route_value * 0.020, 0.0, 20.0), "Торговля")
    add("trade_pacts", "Договорная торговая премия", trade_pacts, trade_pacts * 2.0, "Торговля")
    add("municipal_density", "Муниципальная плотность", building_count, building_count * 0.35, "Римская экономика")
    add("research_diffusion", "Диффузия знаний", round(finite(state.get("innovation", {}).get("diffusion", 0.0)), 3), finite(state.get("innovation", {}).get("diffusion", 0.0)) * 5.0, "Технологии")
    return rows


def _economic_magic_modifiers(
    context: dict[str, Any],
    state: dict[str, Any],
    macro: dict[str, float],
    sectors: dict[str, Any],
    finance: dict[str, float],
    trade: dict[str, Any],
    revenues: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Hundreds of data-driven microformulae, with a safe legacy fallback."""
    if ECONOMY_MODIFIERS is not None:
        try:
            return ECONOMY_MODIFIERS.calculate_modifiers(
                context, state, macro, sectors, finance, trade, revenues
            )
        except (AttributeError, KeyError, TypeError, ValueError, ArithmeticError):
            pass
    return _legacy_economic_magic_modifiers(context, state, macro, sectors, finance, trade)


def microformula_count() -> int:
    if ECONOMY_MODIFIERS is None:
        return 20
    try:
        return int(ECONOMY_MODIFIERS.modifier_count())
    except (AttributeError, TypeError, ValueError):
        return 20


def microformula_library_audit() -> list[str]:
    if ECONOMY_MODIFIERS is None:
        return ["economy_modifiers.py не импортирован"]
    try:
        return list(ECONOMY_MODIFIERS.audit_library())
    except (AttributeError, TypeError, ValueError) as exc:
        return [f"Ошибка проверки библиотеки микроформул: {type(exc).__name__}: {exc}"]



def _realize_magic_rows(
    rows: list[dict[str, Any]],
    realization_factor: float,
) -> list[dict[str, Any]]:
    """Scale visible microformulae by the same collection factor as revenue.

    Before v10, stabilized revenue was scaled while the 306 visible rows kept
    their candidate values. After a few turns the lexicon could therefore claim
    a different micro-income than the treasury actually received.
    """
    factor = max(0.0, finite(realization_factor, 1.0))
    precision = int(getattr(ECONOMY_MODIFIERS, "MICROFORMULA_PRECISION", 3)) if ECONOMY_MODIFIERS is not None else 3
    precision = max(2, min(6, precision))
    realized: list[dict[str, Any]] = []
    raw_total = 0.0
    for source in rows:
        if not isinstance(source, dict):
            continue
        row = dict(source)
        raw = finite(row.get("gold_per_turn", 0.0))
        raw_total += raw
        row["candidate_gold_per_turn"] = round(raw, precision)
        row["realization_factor"] = round(factor, 8)
        row["gold_per_turn"] = round(raw * factor, precision)
        row.setdefault("kind", "microformula")
        row["included_in_micro_total"] = True
        realized.append(row)

    target = round(raw_total * factor, precision)
    visible = round(sum(finite(row.get("gold_per_turn", 0.0)) for row in realized), precision)
    residual = round(target - visible, precision)
    if residual and realized:
        anchor_row = max(realized, key=lambda row: abs(finite(row.get("gold_per_turn", 0.0))))
        anchor_row["gold_per_turn"] = round(
            finite(anchor_row.get("gold_per_turn", 0.0)) + residual,
            precision,
        )
        anchor_row["realization_rounding_reconciliation"] = residual
    return realized


def _magic_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if ECONOMY_MODIFIERS is not None and hasattr(ECONOMY_MODIFIERS, "modifier_summary"):
        try:
            return dict(ECONOMY_MODIFIERS.modifier_summary(rows))
        except (AttributeError, TypeError, ValueError, ArithmeticError):
            pass
    clean = [row for row in rows if isinstance(row, dict)]
    positive = sum(max(0.0, finite(row.get("gold_per_turn", 0.0))) for row in clean)
    negative = sum(min(0.0, finite(row.get("gold_per_turn", 0.0))) for row in clean)
    return {
        "count": len(clean),
        "positive": round(positive, 3),
        "negative": round(negative, 3),
        "net": round(positive + negative, 3),
        "zero_rows": sum(1 for row in clean if finite(row.get("gold_per_turn", 0.0)) == 0.0),
    }

def _doctrine_income(state: dict[str, Any], revenues: dict[str, float]) -> float:
    automation = state.get("automation") if isinstance(state.get("automation"), dict) else {}
    if not bool(automation.get("enabled", True)):
        return 0.0
    spec = _automation_spec(state)
    ordinary = sum(max(0.0, finite(revenues.get(k, 0.0))) for k in ("direct_tax", "domains", "tribute", "base_revenue"))
    return max(0.0,
        ordinary * (finite(spec.get("revenue_mult", 1.0), 1.0) - 1.0)
        + max(0.0, finite(revenues.get("customs", 0.0))) * (finite(spec.get("customs_mult", 1.0), 1.0) - 1.0)
        + max(0.0, finite(revenues.get("commerce", 0.0))) * (finite(spec.get("commerce_mult", 1.0), 1.0) - 1.0)
    )


def _apply_automatic_spending(state: dict[str, Any], expenditures: dict[str, Any]) -> None:
    """Recompute totals after the autopilot changed real budget shares.

    Older builds multiplied whole expenditure blocks invisibly.  The new
    autopilot changes the same public levers as the player (budget shares,
    fiscal stance, taxes, credit, coin and sector policy), so no hidden blanket
    multiplier is required here.
    """
    automation = state.get("automation") if isinstance(state.get("automation"), dict) else {}
    if not bool(automation.get("enabled", True)):
        return
    expenditures["programme_total"] = sum(
        max(0.0, finite(value)) for value in expenditures.get("programmes", {}).values()
    )
    expenditures["mandatory_total"] = sum(max(0.0, finite(expenditures.get(key, 0.0))) for key in (
        "administration", "military_upkeep", "fleet_upkeep", "auxiliary_upkeep",
        "artillery_upkeep", "garrison_upkeep", "municipal_building_upkeep",
        "tribute_paid", "interest", "treasury_management", "strategic_reserve",
    ))
    expenditures["total"] = expenditures["mandatory_total"] + expenditures["programme_total"]


def set_economy_automation(player: Any, enabled: bool) -> bool:
    state = ensure_economy_state(player)
    state.setdefault("automation", {})["enabled"] = bool(enabled)
    state["automation"]["last_reconfigured_turn"] = int(getattr(player, "turn", 1))
    return state["automation"]["enabled"]


def set_automation_doctrine(player: Any, doctrine: str) -> str:
    if doctrine not in AUTOMATION_DOCTRINES:
        raise ValueError(f"Неизвестная автоматическая доктрина: {doctrine}")
    state = ensure_economy_state(player)
    state.setdefault("automation", {})["doctrine"] = doctrine
    state["automation"]["last_reconfigured_turn"] = int(getattr(player, "turn", 1))
    return doctrine


def _blend_map(current: dict[str, float], target: dict[str, float], speed: float) -> dict[str, float]:
    speed = clamp(finite(speed), 0.0, 1.0)
    return {key: finite(current.get(key, target[key])) * (1.0 - speed) + target[key] * speed for key in target}


def _autopilot_action(actions: list[str], label: str, old: Any, new: Any, *, percent: bool = False) -> None:
    if isinstance(old, (int, float)) and isinstance(new, (int, float)):
        if abs(finite(new) - finite(old)) < (0.002 if percent else 0.01):
            return
        if percent:
            actions.append(f"{label}: {finite(old):.1%} → {finite(new):.1%}")
        else:
            actions.append(f"{label}: {finite(old):.2f} → {finite(new):.2f}")
    elif old != new:
        actions.append(f"{label}: {old} → {new}")


def run_economy_autopilot(player: Any, context: dict[str, Any] | None = None, *, force: bool = False) -> list[str]:
    """Adapt every controllable economic lever to the selected doctrine.

    The routine uses only public state variables also exposed in Consilium
    Oeconomicum.  It does not change conquests or manufacture favourable shocks;
    instead it changes the fiscal, monetary, sectoral, credit, grain and social
    response to those circumstances.
    """
    context = context or {}
    state = ensure_economy_state(player, context)
    automation = state.setdefault("automation", {})
    if not bool(automation.get("enabled", True)):
        return []
    turn = int(getattr(player, "turn", 1))
    if not force and int(automation.get("last_policy_turn", -1)) == turn:
        return list(automation.get("last_actions", []))

    doctrine = str(automation.get("doctrine", "balanced"))
    spec = AUTOMATION_DOCTRINES.get(doctrine, AUTOMATION_DOCTRINES["balanced"])
    report = preview_turn(player, context)
    macro = report.get("macro", {})
    grain = report.get("grain", {})
    finance = report.get("finance", {})
    trade = report.get("trade", {})
    actions: list[str] = []

    nominal = max(1.0, finite(macro.get("nominal_output", 1.0)))
    debt_ratio = finite(state.get("debt", 0.0)) / nominal
    inflation = finite(state.get("inflation", 0.0))
    confidence = clamp(finite(state.get("confidence", 0.5)), 0.0, 1.0)
    banking = clamp(finite(finance.get("banking_health", state.get("financial", {}).get("banking_health", 0.5))), 0.0, 1.0)
    import_dependency = clamp(finite(trade.get("import_dependency", 0.0)), 0.0, 2.0)
    trade_balance = finite(trade.get("trade_balance", 0.0))
    grain_cover = finite(grain.get("reserve_turns", grain.get("coverage_turns", 0.0)))
    if grain_cover <= 0:
        grain_cover = finite(getattr(player, "grain", 0.0)) / max(1.0, finite(report.get("upkeep_grain", 1.0)))
    unrest = clamp(finite(getattr(player, "unrest", 0.0)) / 100.0, 0.0, 1.0)
    corruption = clamp(finite(state.get("corruption", 0.12)), 0.0, 1.0)

    # 1–2. Tax and customs: move gradually, respecting Laffer capacity and trade stress.
    elasticity = 2.40 + 1.80 * (1.0 - clamp(finite(state.get("tax_capacity", .48)), 0.0, 1.0)) + 0.65 * corruption
    laffer_peak = clamp(1.0 / max(1.0, elasticity), 0.16, 0.38)
    tax_target = 0.55 * finite(spec.get("tax_target", .24)) + 0.45 * laffer_peak
    if debt_ratio > 0.90: tax_target += 0.025
    if unrest > 0.55 or confidence < 0.35: tax_target -= 0.025
    tax_target = clamp(tax_target, 0.08, 0.46)
    old = state["tax_rate"]; state["tax_rate"] = clamp(old + clamp(tax_target-old, -.025, .025), 0.0, .65)
    _autopilot_action(actions, "Налог", old, state["tax_rate"], percent=True)

    tariff_target = finite(spec.get("tariff_target", .08))
    if import_dependency > .45: tariff_target += .025
    if trade_balance < -nominal * .08: tariff_target += .015
    if trade_balance > nominal * .10 or doctrine == "mercantile": tariff_target -= .015
    if state.get("trade", {}).get("embargo_turns", 0): tariff_target = max(tariff_target, .14)
    tariff_target = clamp(tariff_target, .02, .24)
    old = state["tariff_rate"]; state["tariff_rate"] = clamp(old + clamp(tariff_target-old, -.02, .02), 0.0, .45)
    _autopilot_action(actions, "Тариф", old, state["tariff_rate"], percent=True)

    # 3–4. Budget and stance react to grain, unrest, corruption, war and shocks.
    target_budget = dict(spec.get("budget", DEFAULT_BUDGET_SHARES))
    active_kinds = {str(x.get("kind", "")) for x in state.get("active_shocks", []) if isinstance(x, dict)}
    if grain_cover < 2.0 or active_kinds & {"drought", "locusts", "flood"}:
        target_budget["welfare"] += .07; target_budget["infrastructure"] += .02
    if unrest > .45 or "slave_revolt" in active_kinds:
        target_budget["welfare"] += .05; target_budget["administration"] += .03
    if corruption > .28:
        target_budget["administration"] += .05
    if "epidemic" in active_kinds:
        target_budget["welfare"] += .06; target_budget["science"] += .02
    if "currency_crisis" in active_kinds or "banking_panic" in active_kinds:
        target_budget["administration"] += .04
    if doctrine == "war" or finite(context.get("legion_count", 0)) > finite(context.get("legion_force_limit", 1)) * .85:
        target_budget["military"] += .05
    target_budget = normalize_budget_shares(target_budget)
    old_budget = dict(state["budget_shares"])
    state["budget_shares"] = normalize_budget_shares(_blend_map(old_budget, target_budget, .45))
    if any(abs(state["budget_shares"][k]-old_budget.get(k,0)) >= .004 for k in BUDGET_KEYS):
        actions.append("Бюджет перераспределён: " + ", ".join(f"{BUDGET_LABELS[k]} {state['budget_shares'][k]:.0%}" for k in BUDGET_KEYS))

    stance = str(spec.get("fiscal_stance", "balanced"))
    if debt_ratio > 1.20 and doctrine != "war": stance = "austerity"
    elif report.get("structural_balance", 0) > spec.get("minimum_balance", 0) + 25 and doctrine in {"balanced","development"}: stance = "development"
    old = state["fiscal_stance"]; state["fiscal_stance"] = stance
    _autopilot_action(actions, "Бюджетная позиция", FISCAL_STANCES.get(old,{}).get("label",old), FISCAL_STANCES.get(stance,{}).get("label",stance))

    # 5, 8. Coin standard and minting. Minting is emergency-only and recorded.
    standard = str(spec.get("coin_standard", "managed"))
    if inflation > .10 or confidence < .38: standard = "sound"
    elif doctrine == "war" and inflation < .035 and debt_ratio > 1.0: standard = "debased"
    old = state["coin_standard"]; state["coin_standard"] = standard
    _autopilot_action(actions, "Монета", COIN_STANDARDS.get(old,{}).get("label",old), COIN_STANDARDS.get(standard,{}).get("label",standard))

    # 9/A. Capital investment and sector/labour allocation.
    sector_policy = str(spec.get("sector_policy", "balanced"))
    bottlenecks = report.get("sectors", {}).get("bottlenecks", {})
    if grain_cover < 1.5: sector_policy = "bread"
    elif bottlenecks and min(bottlenecks, key=lambda k: finite(bottlenecks[k], 1.0)) == "mining": sector_policy = "extractive"
    old = state["sector_policy"]; state["sector_policy"] = sector_policy
    _autopilot_action(actions, "Отраслевая политика", SECTOR_POLICIES.get(old,{}).get("label",old), SECTOR_POLICIES.get(sector_policy,{}).get("label",sector_policy))
    weights = SECTOR_POLICIES[sector_policy]["weights"]
    profit = report.get("sectors", {}).get("profitability", {})
    desired_labor = normalize_sector_shares({k: DEFAULT_SECTOR_LABOR_SHARES[k] * weights[k] * max(.45, finite(profit.get(k,1.0))) for k in SECTOR_KEYS}, DEFAULT_SECTOR_LABOR_SHARES)
    state["sectoral_labor_share"] = normalize_sector_shares(_blend_map(state["sectoral_labor_share"], desired_labor, .18), DEFAULT_SECTOR_LABOR_SHARES)

    # C. Credit market.
    credit = str(spec.get("credit_policy", "neutral"))
    if inflation > .09 or banking < .38: credit = "tight"
    elif confidence > .68 and inflation < .04 and doctrine in {"development","mercantile"}: credit = "easy"
    old = state["financial"]["policy"]; state["financial"]["policy"] = credit
    _autopilot_action(actions, "Кредит", CREDIT_POLICIES.get(old,{}).get("label",old), CREDIT_POLICIES.get(credit,{}).get("label",credit))
    old_cap = finite(state["financial"].get("usury_cap", .12))
    target_cap = .10 if credit == "easy" else (.18 if credit == "tight" else .12)
    state["financial"]["usury_cap"] = clamp(old_cap + clamp(target_cap-old_cap, -.015, .015), .03, .50)
    _autopilot_action(actions, "Предел процента", old_cap, state["financial"]["usury_cap"], percent=True)

    # G/D/J/K/T. Grain, demography, groups, shocks and trade are managed through real levers.
    old_target = finite(state.get("strategic_grain_target", 4.0))
    target_grain = finite(spec.get("grain_target", 4.0)) + (1.5 if grain_cover < 2.0 else 0.0)
    state["strategic_grain_target"] = clamp(old_target + clamp(target_grain-old_target, -.75, .75), 0.0, 20.0)
    state["grain_subsidy"] = bool(grain_cover < state["strategic_grain_target"] or unrest > .40)
    _autopilot_action(actions, "Зерновой резерв", old_target, state["strategic_grain_target"])

    # 6–7 and capital investments: preserve a treasury reserve, borrow only for a real gap,
    # repay excess debt and invest genuine surplus rather than printing a magic balance.
    reserve = max(100.0, finite(report.get("expense_total", 0.0)) * finite(spec.get("reserve_turns", 2.0)))
    gold = max(0.0, finite(getattr(player, "gold", 0.0)))
    structural = finite(report.get("structural_balance", report.get("overall_balance", 0.0)))
    state["automatic_debt_repayment"] = doctrine != "development" or debt_ratio > .65
    if gold < reserve * .45 and structural < 0 and debt_ratio < 1.75:
        issue = min(reserve * .35 - gold, nominal * .08)
        if issue > 1:
            state["pending_bond_issue"] = max(finite(state.get("pending_bond_issue", 0.0)), money(issue))
            actions.append(f"Облигации запланированы: +{money(issue)} золота")
    elif gold > reserve * 1.35 and state["debt"] > 0:
        repay = min(state["debt"], (gold-reserve) * .30)
        state["pending_debt_repayment"] = max(finite(state.get("pending_debt_repayment", 0.0)), money(repay))
        if repay > 1: actions.append(f"Погашение долга запланировано: {money(repay)}")

    if gold > reserve * 1.15 and structural >= 0:
        amount = min((gold-reserve) * finite(spec.get("investment_rate", .08)), nominal * .025)
        if amount >= 5:
            target = "infrastructure"
            if corruption > .25: target = "administration"
            elif banking < .45: target = "banking"
            elif doctrine == "development": target = "human_capital"
            elif grain_cover < 2.0: target = "agriculture"
            invested = direct_investment(player, target, amount)
            if invested: actions.append(f"Капитальные вложения: {target}, {invested} золота")

    if gold < 20 and structural < -max(20.0, nominal*.08) and debt_ratio >= 1.65 and inflation < .07:
        minted = mint_currency(player, min(25.0, nominal*.015))
        if minted: actions.append(f"Чрезвычайная чеканка: {minted} золота")

    automation["last_policy_turn"] = turn
    automation["last_reconfigured_turn"] = turn
    automation["last_actions"] = actions[-16:]
    automation["last_plan"] = {
        "tax_rate": state["tax_rate"], "tariff_rate": state["tariff_rate"],
        "fiscal_stance": state["fiscal_stance"], "coin_standard": state["coin_standard"],
        "credit_policy": state["financial"]["policy"], "sector_policy": state["sector_policy"],
        "grain_target": state["strategic_grain_target"], "budget_shares": dict(state["budget_shares"]),
        "reserve_gold": money(reserve), "debt_ratio": round(debt_ratio, 4),
    }
    return list(actions)


def _tax_revenue(
    context: dict[str, Any],
    state: dict[str, Any],
    macro: dict[str, float],
    trade: dict[str, Any],
) -> dict[str, float]:
    rate = state["tax_rate"]
    capacity = state["tax_capacity"]
    corruption = state["corruption"]
    legitimacy = macro["political_legitimacy"]
    elasticity = 2.40 + 1.80 * (1.0 - capacity) + 0.65 * corruption
    laffer_rate = rate * math.exp(-elasticity * rate)
    compliance = clamp((0.50 + 0.50 * capacity) * (1.0 - 0.72 * corruption) * (0.72 + 0.28 * legitimacy), 0.10, 0.97)
    direct_tax = macro["nominal_output"] * laffer_rate * compliance

    tariff = state["tariff_rate"]
    trade_volume = trade["export_value"] + trade["import_value"]
    tariff_yield = tariff * math.exp(-2.70 * tariff)
    customs_efficiency = clamp(0.45 + 0.50 * capacity - 0.45 * corruption, 0.10, 0.95)
    customs = trade["import_value"] * tariff_yield * customs_efficiency

    nominal_scale = max(0.20, state["price_level"])
    domains = max(0.0, finite(context.get("state_domain_income", 0.0))) * nominal_scale
    tribute = max(0.0, finite(context.get("tribute_income", 0.0))) * nominal_scale
    commerce = max(0.0, finite(context.get("special_gold_income", 0.0))) * nominal_scale
    # Фактические денежные потоки приходят уже в игровых единицах золота.
    # Их нельзя повторно индексировать уровнем цен или множителем сложности.
    trade_routes = max(0.0, finite(context.get("trade_route_income", 0.0)))
    rare_resources = max(0.0, finite(context.get("rare_resource_income", 0.0)))
    caravans = max(0.0, finite(context.get("caravan_income", 0.0)))
    base_revenue = max(0.0, finite(context.get("base_revenue", STARTING_BASE_REVENUE_DEFAULT))) * nominal_scale
    difficulty = clamp(finite(context.get("income_mult", 1.0), 1.0), 0.20, 3.0)
    direct_tax *= difficulty
    customs *= difficulty
    domains *= difficulty
    commerce *= difficulty
    base_revenue *= difficulty
    return {
        "direct_tax": direct_tax,
        "customs": customs,
        "domains": domains,
        "tribute": tribute,
        "commerce": commerce,
        "trade_routes": trade_routes,
        "rare_resources": rare_resources,
        "caravans": caravans,
        "base_revenue": base_revenue,
        "laffer_effective_rate": laffer_rate,
        "compliance": compliance,
        "trade_volume": trade_volume,
    }


def _grain_market(
    player: Any,
    context: dict[str, Any],
    state: dict[str, Any],
    macro: dict[str, float],
    trade: dict[str, Any],
) -> dict[str, float]:
    inventory = max(0.0, finite(getattr(player, "grain", 0.0)))
    production = max(0.0, finite(trade["supply"]["grain"]))
    consumption = max(1.0, finite(trade["demand"]["grain"]))
    commercial_imports = max(0.0, finite(trade["imports"]["grain"]))
    commercial_exports = max(0.0, finite(trade["exports"]["grain"]))
    inventory_loss = inventory * 0.006 + max(0.0, inventory - 1000.0) * 0.025
    consumption += inventory_loss
    stock_cover = inventory / max(1.0, consumption)
    target_cover = clamp(state.get("strategic_grain_target", _config(context).default_reserve_turns), 0.0, 20.0)
    desired_stock = consumption * target_cover
    reserve_gap = max(0.0, desired_stock - inventory)
    reserve_purchase = min(reserve_gap * 0.18, consumption * 0.75)
    world_price = max(0.10, finite(trade["world_prices"]["grain"], 1.0))
    reserve_procurement_cost = reserve_purchase * world_price * trade["exchange_rate"]
    total_supply = production + commercial_imports + reserve_purchase - commercial_exports
    scarcity = consumption / max(1.0, total_supply + 0.22 * inventory)
    target_price = clamp(
        trade["domestic_prices"]["grain"] * (scarcity ** 0.45) * (1.0 + max(0.0, 0.75 - stock_cover) * 0.20),
        0.20,
        50.0,
    )
    grain_price = clamp(0.66 * state["grain_price"] + 0.34 * target_price, 0.10, 100.0)
    return {
        "production": production,
        "consumption": consumption,
        "commercial_imports": commercial_imports,
        "commercial_exports": commercial_exports,
        "reserve_purchase": reserve_purchase,
        "reserve_procurement_cost": reserve_procurement_cost,
        "total_supply": total_supply,
        "net": total_supply - consumption,
        "price": grain_price,
        "stock_cover": stock_cover,
        "target_stock_cover": target_cover,
        "scarcity": scarcity,
        "inventory_loss": inventory_loss,
    }


def _political_economy(
    player: Any,
    context: dict[str, Any],
    state: dict[str, Any],
    programmes: dict[str, float],
) -> dict[str, Any]:
    senate = clamp(finite(context.get("senate_rep", getattr(player, "senate_rep", 50))), 0.0, 100.0)
    people = clamp(finite(context.get("people_rep", getattr(player, "people_rep", 50))), 0.0, 100.0)
    morale = clamp(finite(context.get("morale", getattr(player, "morale", 70))), 0.0, 100.0)
    corruption = state["corruption"]
    efficiencies = {
        "administration": clamp(0.55 + 0.55 * state["tax_capacity"] - 0.35 * corruption, 0.25, 1.20),
        "military": clamp(0.58 + 0.30 * senate / 100.0 + 0.24 * morale / 100.0 - 0.20 * corruption, 0.25, 1.20),
        "infrastructure": clamp(0.62 + 0.24 * senate / 100.0 + 0.22 * state["confidence"] - 0.35 * corruption, 0.20, 1.18),
        "welfare": clamp(0.56 + 0.42 * people / 100.0 + 0.12 * state["confidence"] - 0.20 * corruption, 0.25, 1.25),
        "science": clamp(0.55 + 0.30 * state["human_capital"] / 100.0 + 0.20 * state["confidence"] - 0.22 * corruption, 0.25, 1.30),
        "religion": clamp(0.62 + 0.20 * people / 100.0 + 0.18 * senate / 100.0 - 0.18 * corruption, 0.30, 1.22),
    }
    programme_total = sum(max(0.0, finite(v)) for v in programmes.values())
    rents = programme_total * corruption * (0.18 + 0.22 * state["inequality"])
    group_rents = {
        "elites": rents * 0.40,
        "plebs": rents * 0.04,
        "military": rents * 0.18,
        "merchants": rents * 0.30,
        "priests": rents * 0.08,
    }
    satisfaction_targets = {
        "elites": clamp(0.35 + 0.34 * senate / 100.0 + 0.16 * programmes.get("infrastructure", 0) / max(1.0, programme_total) - 0.25 * state["tax_rate"], 0.02, 0.98),
        "plebs": clamp(0.25 + 0.38 * people / 100.0 + 0.40 * programmes.get("welfare", 0) / max(1.0, programme_total) - 0.18 * state["inequality"], 0.02, 0.98),
        "military": clamp(0.30 + 0.35 * morale / 100.0 + 0.42 * programmes.get("military", 0) / max(1.0, programme_total), 0.02, 0.98),
        "merchants": clamp(0.32 + 0.35 * state["confidence"] + 0.22 * programmes.get("infrastructure", 0) / max(1.0, programme_total) - 0.25 * state["tariff_rate"], 0.02, 0.98),
        "priests": clamp(0.36 + 0.45 * programmes.get("religion", 0) / max(1.0, programme_total) + 0.12 * people / 100.0, 0.02, 0.98),
    }
    return {
        "programme_efficiency": efficiencies,
        "rent_seeking": rents,
        "group_rents": group_rents,
        "satisfaction_targets": satisfaction_targets,
    }


def _fiscal_policy_signature(state: dict[str, Any], context: dict[str, Any]) -> str:
    """Короткая подпись решений, способных изменить бюджетный поток."""
    payload = {
        "tax": round(finite(state.get("tax_rate", 0.0)), 4),
        "tariff": round(finite(state.get("tariff_rate", 0.0)), 4),
        "stance": str(state.get("fiscal_stance", "balanced")),
        "coin": str(state.get("coin_standard", "managed")),
        "credit": str(state.get("financial", {}).get("policy", "neutral")),
        "budget": {
            key: round(finite(state.get("budget_shares", {}).get(key, 0.0)), 4)
            for key in BUDGET_KEYS
        },
        "reserve": round(finite(state.get("strategic_grain_target", 0.0)), 2),
        "provinces": int(context.get("province_count", 0)),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def _stabilized_revenue(
    state: dict[str, Any],
    context: dict[str, Any],
    candidate: float,
) -> tuple[float, dict[str, Any]]:
    """Превращает волатильную макрооценку в реально собираемый доход казны."""
    candidate = max(0.0, finite(candidate))
    fiscal = state.setdefault("fiscal", {})
    previous = max(
        0.0,
        finite(
            fiscal.get(
                "last_realized_stabilizable_revenue",
                fiscal.get("last_realized_revenue", 0.0),
            )
        ),
    )
    signature = _fiscal_policy_signature(state, context)
    previous_signature = str(fiscal.get("last_policy_signature", ""))
    current_provinces = max(0, int(context.get("province_count", 0)))
    previous_provinces = max(
        0,
        int(finite(fiscal.get("last_province_count", current_provinces), current_provinces)),
    )

    if previous <= 0.0:
        return candidate, {
            "candidate": candidate,
            "realized": candidate,
            "previous": previous,
            "lower_bound": 0.0,
            "upper_bound": candidate,
            "policy_changed": bool(previous_signature and previous_signature != signature),
            "province_delta": current_provinces - previous_provinces,
            "stabilized": False,
            "policy_signature": signature,
        }

    policy_changed = bool(previous_signature and previous_signature != signature)
    province_delta = current_provinces - previous_provinces
    shock_active = any(
        isinstance(row, dict) and int(finite(row.get("remaining", 0))) > 0
        for row in state.get("active_shocks", [])
    )

    rise_rate = 0.28
    fall_rate = 0.34
    if policy_changed:
        rise_rate += 0.12
        fall_rate += 0.10
    if province_delta:
        expansion = min(0.30, abs(province_delta) * 0.055)
        rise_rate += expansion
        fall_rate += expansion * 0.55
    if shock_active:
        rise_rate += 0.16
        fall_rate += 0.22

    upper = previous + max(35.0, previous * rise_rate)
    lower = max(0.0, previous - max(35.0, previous * fall_rate))
    realized = clamp(candidate, lower, upper)
    return realized, {
        "candidate": candidate,
        "realized": realized,
        "previous": previous,
        "lower_bound": lower,
        "upper_bound": upper,
        "policy_changed": policy_changed,
        "province_delta": province_delta,
        "stabilized": abs(realized - candidate) > 0.5,
        "policy_signature": signature,
    }


def _expenditures(
    context: dict[str, Any],
    state: dict[str, Any],
    macro: dict[str, float],
    revenues: dict[str, float],
    grain: dict[str, float],
    finance: dict[str, float],
) -> dict[str, Any]:
    province_count = max(1, int(context.get("province_count", 1)))
    legion_count = max(0, int(context.get("legion_count", 0)))
    force_limit = max(1, int(context.get("legion_force_limit", 2)))
    over_limit = max(0, legion_count - force_limit)
    quality_index = clamp(finite(context.get("legion_quality_index", 1.0), 1.0), 0.50, 3.0)
    military_technology = clamp(
        finite(state["innovation"].get("military_technology", 1.0)),
        0.5,
        10.0,
    )
    price = state["price_level"]
    corruption = state["corruption"]
    local_unrest = clamp(finite(context.get("avg_province_unrest", 0.0)), 0.0, 10.0)

    # Профессиональная армия и большая территория должны ощущаться в казне.
    military = (
        legion_count
        * (24.0 + 7.0 * quality_index)
        * price
        / (military_technology ** 0.12)
    )
    military += over_limit * (18.0 + 8.0 * over_limit) * price

    fleet = max(0.0, finite(context.get("fleet_upkeep", 0.0))) * price
    auxiliaries = max(0.0, finite(context.get("auxiliary_upkeep", 0.0))) * price
    artillery = max(0.0, finite(context.get("artillery_upkeep", 0.0))) * price
    provincial_garrisons = max(0.0, finite(context.get("garrison_upkeep", 0.0))) * price
    municipal_buildings = max(0.0, finite(context.get("municipal_building_upkeep", 0.0))) * price

    # Степень 1.55 создаёт настоящий late-game administrative burden:
    # маленькая республика дешева, мировая империя требует большого аппарата.
    administration = (6.0 + 1.55 * (province_count ** 1.55)) * price
    administration *= 1.0 + 0.42 * corruption + 0.018 * local_unrest

    tribute_paid = max(0.0, finite(context.get("tribute_paid", 0.0)))
    sovereign_rate = finance["sovereign_rate"]
    interest = state["debt"] * sovereign_rate
    revenue_total = sum(finite(revenues.get(key, 0.0)) for key in REVENUE_KEYS)

    # Крупная бездействующая казна требует охраны, перевозки, чеканки и
    # создаёт утечки. Это мягкий late-game sink, а не конфискация накоплений.
    treasury_cash = max(0.0, finite(context.get("treasury_cash", 0.0)))
    reserve_target = max(300.0, revenue_total * 3.0)
    excess_cash = max(0.0, treasury_cash - reserve_target)
    treasury_management = min(
        revenue_total * 0.30,
        excess_cash * 0.006 + math.sqrt(excess_cash) * 0.12,
    )

    stance = FISCAL_STANCES[state["fiscal_stance"]]
    investment_envelope = max(
        0.0,
        revenue_total * 0.34 * stance["investment_ratio"],
    )
    shares = normalize_budget_shares(state["budget_shares"])
    programmes = {
        key: investment_envelope
        * shares[key]
        * PROGRAMME_COST_MULTIPLIERS.get(key, 1.0)
        for key in BUDGET_KEYS
    }

    grain_subsidy = 0.0
    if state.get("grain_subsidy", True) and grain["price"] > 1.35:
        grain_subsidy = min(
            revenue_total * 0.18,
            (grain["price"] - 1.0) * macro["population"] * 0.025,
        )
        programmes["welfare"] += grain_subsidy

    strategic_reserve = min(
        revenue_total * 0.25,
        max(0.0, grain["reserve_procurement_cost"]),
    )
    mandatory = (
        administration
        + military
        + fleet
        + auxiliaries
        + artillery
        + provincial_garrisons
        + municipal_buildings
        + tribute_paid
        + interest
        + treasury_management
        + strategic_reserve
    )
    programme_total = sum(programmes.values())
    total = mandatory + programme_total
    return {
        "administration": administration,
        "military_upkeep": military,
        "fleet_upkeep": fleet,
        "auxiliary_upkeep": auxiliaries,
        "artillery_upkeep": artillery,
        "garrison_upkeep": provincial_garrisons,
        "municipal_building_upkeep": municipal_buildings,
        "tribute_paid": tribute_paid,
        "interest": interest,
        "treasury_management": treasury_management,
        "strategic_reserve": strategic_reserve,
        "programmes": programmes,
        "grain_subsidy": grain_subsidy,
        "mandatory_total": mandatory,
        "programme_total": programme_total,
        "total": total,
        "investment_envelope": investment_envelope,
    }


def _national_accounts(
    state: dict[str, Any],
    macro: dict[str, float],
    sectors: dict[str, Any],
    trade: dict[str, Any],
    finance: dict[str, float],
    expenditures: dict[str, Any],
) -> dict[str, Any]:
    nominal_gdp = max(1.0, macro["nominal_output"])
    government_purchases = max(0.0,
        expenditures["mandatory_total"]
        - expenditures["interest"]
        - expenditures["treasury_management"]
        + expenditures["programme_total"]
    )
    public_investment = (
        expenditures["programmes"].get("infrastructure", 0.0)
        + 0.35 * expenditures["programmes"].get("science", 0.0)
        + 0.20 * expenditures["programmes"].get("military", 0.0)
    )
    private_investment = max(0.0, finance["private_investment"])
    investment = private_investment + public_investment
    net_exports = trade["trade_balance"]
    consumption = max(0.0, nominal_gdp - investment - government_purchases - net_exports)
    expenditure_sum = consumption + investment + government_purchases + net_exports
    statistical_discrepancy = nominal_gdp - expenditure_sum

    wages = nominal_gdp * clamp(0.42 + 0.12 * (1.0 - state["inequality"]), 0.32, 0.58)
    mixed_income = nominal_gdp * 0.18
    operating_surplus = max(0.0, nominal_gdp - wages - mixed_income)

    sector_nominal = {
        key: sectors["output"][key] * state["price_level"]
        for key in SECTOR_KEYS
    }
    return {
        "production": {
            "sectoral_value_added": sector_nominal,
            "gdp": nominal_gdp,
        },
        "expenditure": {
            "consumption": consumption,
            "private_investment": private_investment,
            "public_investment": public_investment,
            "investment": investment,
            "government": government_purchases,
            "net_exports": net_exports,
            "statistical_discrepancy": statistical_discrepancy,
            "gdp": nominal_gdp,
        },
        "income": {
            "wages": wages,
            "mixed_income": mixed_income,
            "operating_surplus": operating_surplus,
            "gdp": nominal_gdp,
        },
    }


def _flow_of_funds(
    state: dict[str, Any],
    macro: dict[str, float],
    trade: dict[str, Any],
    finance: dict[str, float],
    revenue_total: float,
    expenditures: dict[str, Any],
) -> dict[str, float]:
    government_net_lending = revenue_total - expenditures["total"]
    household_saving = finance["private_savings"]
    private_investment = finance["private_investment"]
    private_net_lending = household_saving - private_investment
    external_balance = -trade["current_account"]
    financial_gap = -(government_net_lending + private_net_lending + external_balance)
    credit_change = finance["credit_change"]
    discrepancy = financial_gap - credit_change
    return {
        "government_net_lending": government_net_lending,
        "private_saving": household_saving,
        "private_investment": private_investment,
        "private_net_lending": private_net_lending,
        "external_balance": external_balance,
        "credit_change": credit_change,
        "financial_gap": financial_gap,
        "discrepancy": discrepancy,
    }




def _integer_revenue_payload(revenues: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Round fiscal receipts once and reconcile components to their total."""
    payload: dict[str, Any] = {}
    for key, value in revenues.items():
        if key in ("laffer_effective_rate", "compliance", "trade_volume"):
            payload[key] = value
        else:
            payload[key] = money(value)
    for key in REVENUE_KEYS:
        payload.setdefault(key, 0)
    target = money(sum(finite(revenues.get(key, 0.0)) for key in REVENUE_KEYS))
    component_total = sum(int(payload.get(key, 0)) for key in REVENUE_KEYS)
    residual = target - component_total
    if residual:
        anchors = ("automatic_stabilizer", "base_revenue", "micro_income", "direct_tax")
        anchor_key = next((key for key in anchors if int(payload.get(key, 0)) != 0), "base_revenue")
        payload[anchor_key] = int(payload.get(anchor_key, 0)) + residual
    return payload, target


def _integer_expenditure_payload(expenditures: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Build an integer expenditure statement whose subtotals always add up."""
    mandatory_keys = (
        "administration", "military_upkeep", "fleet_upkeep", "auxiliary_upkeep",
        "artillery_upkeep", "garrison_upkeep", "municipal_building_upkeep",
        "tribute_paid", "interest", "treasury_management", "strategic_reserve",
    )
    payload = {key: money(expenditures.get(key, 0.0)) for key in mandatory_keys}
    programmes_raw = expenditures.get("programmes") if isinstance(expenditures.get("programmes"), dict) else {}
    programmes = {key: money(programmes_raw.get(key, 0.0)) for key in BUDGET_KEYS}
    payload["programmes"] = programmes
    payload["grain_subsidy"] = money(expenditures.get("grain_subsidy", 0.0))
    payload["mandatory_total"] = sum(int(payload[key]) for key in mandatory_keys)
    payload["programme_total"] = sum(int(programmes[key]) for key in BUDGET_KEYS)
    payload["total"] = int(payload["mandatory_total"]) + int(payload["programme_total"])
    return payload, int(payload["total"])

def _roman_fiscal_accounts(
    context: dict[str, Any],
    state: dict[str, Any],
    macro: dict[str, float],
    sectors: dict[str, Any],
    revenues: dict[str, float],
    expenditures: dict[str, Any],
    grain: dict[str, float],
    finance: dict[str, float],
    revenue_total: float,
) -> dict[str, Any]:
    """Read-only Roman decomposition of the already calculated budget.

    These figures do not create a second stream of money. They partition direct
    taxes, public-domain income and military expenditure into historically
    legible Roman institutions for the lexicon and audits.
    """
    nominal = max(1.0, finite(macro.get("nominal_output", 1.0)))
    output = sectors.get("output") if isinstance(sectors.get("output"), dict) else {}
    total_output = max(1e-9, sum(max(0.0, finite(value)) for value in output.values()))
    agriculture_share = clamp(finite(output.get("agriculture", 0.0)) / total_output, 0.0, 1.0)
    urbanization = clamp(
        finite(state.get("demographics", {}).get("urbanization_rate", macro.get("urbanization", 0.0))),
        0.0,
        1.0,
    )

    direct_tax = max(0.0, finite(revenues.get("direct_tax", 0.0)))
    land_tax_share = clamp(0.50 + 0.34 * agriculture_share - 0.18 * urbanization, 0.34, 0.78)
    tributum_soli = direct_tax * land_tax_share
    tributum_capitis = direct_tax - tributum_soli

    domains = max(0.0, finite(revenues.get("domains", 0.0)))
    ager_share = clamp(0.56 + 0.30 * agriculture_share - 0.12 * urbanization, 0.35, 0.82)
    ager_publicus = domains * ager_share
    patrimonium_caesaris = domains - ager_publicus
    scriptura = ager_publicus * clamp(0.10 + 0.24 * agriculture_share, 0.08, 0.30)

    military_total = max(0.0, finite(expenditures.get("military_upkeep", 0.0)))
    stipendium = military_total * 0.64
    castra_logistics = military_total - stipendium

    programmes = expenditures.get("programmes") if isinstance(expenditures.get("programmes"), dict) else {}
    cursus_publicus_cost = (
        max(0.0, finite(expenditures.get("administration", 0.0))) * 0.22
        + max(0.0, finite(programmes.get("infrastructure", 0.0))) * 0.18
    )
    annona_cost = max(0.0, finite(expenditures.get("grain_subsidy", 0.0))) + max(
        0.0, finite(expenditures.get("strategic_reserve", 0.0))
    )
    frumentatio_volume = max(0.0, finite(grain.get("consumption", 0.0))) * clamp(
        0.14 + 0.34 * urbanization,
        0.12,
        0.42,
    )
    decuma_volume = max(0.0, finite(grain.get("production", 0.0))) * 0.10

    avg_unrest = clamp(finite(context.get("avg_province_unrest", 0.0)) / 10.0, 0.0, 1.0)
    romanization = clamp(finite(context.get("avg_romanization", 0.0)) / 100.0, 0.0, 1.0)
    publicani_efficiency = clamp(finite(revenues.get("compliance", 0.0)), 0.0, 1.0)

    return {
        "aerarium": round(max(0.0, finite(revenue_total)), 6),
        "fiscus": round(domains + max(0.0, finite(revenues.get("doctrine_income", 0.0))), 6),
        "tributum": round(direct_tax, 6),
        "tributum_soli": round(tributum_soli, 6),
        "tributum_capitis": round(tributum_capitis, 6),
        "portorium": round(max(0.0, finite(revenues.get("customs", 0.0))), 6),
        "vectigalia": round(max(0.0, finite(revenues.get("customs", 0.0))) + domains, 6),
        "ager_publicus": round(ager_publicus, 6),
        "patrimonium_caesaris": round(patrimonium_caesaris, 6),
        "scriptura": round(scriptura, 6),
        "decuma_volume": round(decuma_volume, 6),
        "annona_cost": round(annona_cost, 6),
        "frumentatio_volume": round(frumentatio_volume, 6),
        "horrea_cover": round(max(0.0, finite(grain.get("stock_cover", 0.0))), 6),
        "cursus_publicus_cost": round(cursus_publicus_cost, 6),
        "stipendium": round(stipendium, 6),
        "castra_logistics": round(castra_logistics, 6),
        "publicani_efficiency": round(publicani_efficiency, 6),
        "argentarii_health": round(clamp(finite(finance.get("banking_health", 0.0)), 0.0, 1.0), 6),
        "mensarii_liquidity": round(max(0.0, finite(finance.get("deposit_base", 0.0))), 6),
        "nummularii_standard": str(state.get("coin_standard", "managed")),
        "romanitas_fiscalis": round(romanization, 6),
        "pax_romana": round(1.0 - avg_unrest, 6),
        "agriculture_share": round(agriculture_share, 6),
        "urbanization": round(urbanization, 6),
        "nominal_basis": round(nominal, 6),
        "accounting_note": "decomposition_only_no_double_counting",
    }

def build_statement(player: Any, context: dict[str, Any], mutate: bool = False) -> dict[str, Any]:
    state = ensure_economy_state(player, context)
    sectors = _sectoral_snapshot(player, context, state)
    macro = _macro_snapshot(player, context, state, sectors)
    finance = _financial_market(player, context, state, macro, sectors)
    trade = _external_trade(player, context, state, macro, sectors)
    revenues = _tax_revenue(context, state, macro, trade)

    # Провинциальная религия изменяет реальные налоговые, торговые и мобилизационные
    # возможности державы. Модуль опционален: старые сохранения и автономные тесты
    # экономики продолжают работать без него.
    religion_economy = {
        "tax_multiplier": 1.0,
        "levy_multiplier": 1.0,
        "trade_multiplier": 1.0,
        "minority_provinces": 0,
        "details": [],
    }
    religion_engine = context.get("RELIGION_SYSTEM")
    if religion_engine is not None and hasattr(religion_engine, "economy_modifiers"):
        try:
            candidate = religion_engine.economy_modifiers(player, context)
            if isinstance(candidate, dict):
                religion_economy.update(candidate)
        except Exception:
            pass
    religion_tax = clamp(finite(religion_economy.get("tax_multiplier", 1.0), 1.0), 0.55, 1.25)
    religion_trade = clamp(finite(religion_economy.get("trade_multiplier", 1.0), 1.0), 0.55, 1.35)
    revenues["direct_tax"] = finite(revenues.get("direct_tax", 0.0)) * religion_tax
    revenues["domains"] = finite(revenues.get("domains", 0.0)) * (0.65 + 0.35 * religion_tax)
    revenues["commerce"] = finite(revenues.get("commerce", 0.0)) * religion_trade

    magic_rows = _economic_magic_modifiers(context, state, macro, sectors, finance, trade, revenues)
    candidate_micro_income = sum(finite(row.get("gold_per_turn", 0.0)) for row in magic_rows)
    revenues["micro_income"] = candidate_micro_income
    revenues["doctrine_income"] = _doctrine_income(state, revenues)
    revenues["automatic_stabilizer"] = 0.0

    candidate_revenue_total = sum(finite(revenues.get(key, 0.0)) for key in REVENUE_KEYS)
    guaranteed_revenue_total = sum(
        max(0.0, finite(revenues.get(key, 0.0))) for key in GUARANTEED_REVENUE_KEYS
    )
    stabilizable_candidate = max(0.0, candidate_revenue_total - guaranteed_revenue_total)
    realized_stabilizable, fiscal_stabilization = _stabilized_revenue(
        state,
        context,
        stabilizable_candidate,
    )
    if stabilizable_candidate > 0:
        realization_factor = realized_stabilizable / stabilizable_candidate
        for key in REVENUE_KEYS:
            if key not in GUARANTEED_REVENUE_KEYS and key != "automatic_stabilizer":
                revenues[key] = finite(revenues.get(key, 0.0)) * realization_factor
    else:
        realization_factor = 1.0
    fiscal_stabilization["guaranteed"] = guaranteed_revenue_total
    fiscal_stabilization["candidate_total"] = candidate_revenue_total
    fiscal_stabilization["realized_total"] = realized_stabilizable + guaranteed_revenue_total

    # Keep the 306 visible rows and the realized treasury flow in exact accord.
    magic_rows = _realize_magic_rows(magic_rows, realization_factor)
    revenues["micro_income"] = sum(
        finite(row.get("gold_per_turn", 0.0)) for row in magic_rows
    )
    realized_revenue_total = sum(
        finite(revenues.get(key, 0.0)) for key in REVENUE_KEYS
    )
    fiscal_stabilization["realized"] = realized_revenue_total
    microformula_summary = _magic_summary(magic_rows)

    grain = _grain_market(player, context, state, macro, trade)
    expenditures = _expenditures(context, state, macro, revenues, grain, finance)
    _apply_automatic_spending(state, expenditures)
    if grain["reserve_procurement_cost"] > 0:
        funding_ratio = clamp(expenditures["strategic_reserve"] / grain["reserve_procurement_cost"], 0.0, 1.0)
        funded_purchase = grain["reserve_purchase"] * funding_ratio
        grain["funded_reserve_purchase"] = funded_purchase
        grain["reserve_purchase"] = funded_purchase
        grain["reserve_procurement_cost"] = expenditures["strategic_reserve"]
        grain["total_supply"] = grain["production"] + grain["commercial_imports"] + funded_purchase - grain["commercial_exports"]
        grain["net"] = grain["total_supply"] - grain["consumption"]
    else:
        grain["funded_reserve_purchase"] = 0.0
    politics = _political_economy(player, context, state, expenditures["programmes"])

    revenue_total_before_stabilizer = sum(finite(revenues.get(key, 0.0)) for key in REVENUE_KEYS if key != "automatic_stabilizer")
    structural_balance = revenue_total_before_stabilizer - expenditures["total"]
    automation = state.get("automation") if isinstance(state.get("automation"), dict) else {}
    doctrine_key = str(automation.get("doctrine", "balanced"))
    doctrine_spec = AUTOMATION_DOCTRINES.get(doctrine_key, AUTOMATION_DOCTRINES["balanced"])
    target_floor = int(finite(doctrine_spec.get("minimum_balance", 0))) if bool(automation.get("enabled", True)) else -10**9
    emergency_limit = max(0.0, finite(doctrine_spec.get("emergency_limit", 0.0)))
    stabilizer_income = min(
        emergency_limit,
        max(0.0, target_floor - structural_balance),
    ) if bool(automation.get("enabled", True)) else 0.0
    revenues["automatic_stabilizer"] = stabilizer_income
    revenue_total = revenue_total_before_stabilizer + stabilizer_income
    primary_balance = revenue_total - (expenditures["total"] - expenditures["interest"])
    overall_balance = revenue_total - expenditures["total"]
    debt_ratio = state["debt"] / max(1.0, macro["nominal_output"])
    national_accounts = _national_accounts(state, macro, sectors, trade, finance, expenditures)
    flow_of_funds = _flow_of_funds(state, macro, trade, finance, revenue_total, expenditures)
    roman_accounts = _roman_fiscal_accounts(
        context, state, macro, sectors, revenues, expenditures, grain, finance, revenue_total
    )
    total_private_investment = max(0.0, national_accounts["expenditure"]["private_investment"])
    total_public_investment = max(0.0, national_accounts["expenditure"]["public_investment"])
    sectoral_balances = {}
    for key in SECTOR_KEYS:
        value_added = sectors["output"][key] * state["price_level"]
        investment_use = (total_private_investment + total_public_investment) * sectors["capital_shares"][key]
        intermediate_use = sum(
            sectors["output"][consumer] * state["price_level"] * INPUT_OUTPUT[consumer].get(key, 0.0)
            for consumer in SECTOR_KEYS
        )
        sectoral_balances[key] = value_added - investment_use - intermediate_use

    revenue_payload, revenue_total_game = _integer_revenue_payload(revenues)
    expenditure_payload, expense_total_game = _integer_expenditure_payload(expenditures)
    # Integer rounding must not defeat the selected automatic floor.
    if bool(automation.get("enabled", True)) and target_floor > -10**8:
        floor_gap = max(0, target_floor - (revenue_total_game - expense_total_game))
        if floor_gap:
            revenue_payload["automatic_stabilizer"] = int(
                revenue_payload.get("automatic_stabilizer", 0)
            ) + floor_gap
            revenue_total_game += floor_gap
    overall_balance_game = revenue_total_game - expense_total_game
    structural_balance_game = (
        revenue_total_game - int(revenue_payload.get("automatic_stabilizer", 0)) - expense_total_game
    )
    primary_balance_game = revenue_total_game - (
        expense_total_game - int(expenditure_payload.get("interest", 0))
    )
    roman_accounts["aerarium"] = revenue_total_game

    rows = [
        {"key": "direct_tax", "label": "Прямые налоги", "amount": int(revenue_payload["direct_tax"]), "note": f"ставка {state['tax_rate']:.0%}; эффективная {revenues['laffer_effective_rate']:.1%}"},
        {"key": "customs", "label": "Пошлины и портовые сборы", "amount": int(revenue_payload["customs"]), "note": f"тариф {state['tariff_rate']:.0%}"},
        {"key": "domains", "label": "Доходы государственных владений", "amount": int(revenue_payload["domains"]), "note": "рудники, города, земля и монополии"},
        {"key": "tribute", "label": "Дань и союзные платежи", "amount": int(revenue_payload["tribute"]), "note": "внешние поступления"},
        {"key": "commerce", "label": "Торговля и рынки", "amount": int(revenue_payload["commerce"]), "note": "внутренняя торговля и городские рынки"},
        {"key": "trade_routes", "label": "Торговые пути", "amount": int(revenue_payload.get("trade_routes", 0)), "note": "полная заявленная прибыль действующих маршрутов"},
        {"key": "rare_resources", "label": "Редкие ресурсы", "amount": int(revenue_payload.get("rare_resources", 0)), "note": "серебро, золото, пурпур, специи и драгоценности"},
        {"key": "caravans", "label": "Прибывшие караваны", "amount": int(revenue_payload.get("caravans", 0)), "note": "разовое поступление этого хода"},
        {"key": "base_revenue", "label": "Доход столицы и казённых служб", "amount": int(revenue_payload["base_revenue"]), "note": "устойчивая налоговая база"},
        {"key": "micro_income", "label": "Наноэкономические модификаторы", "amount": int(revenue_payload.get("micro_income", 0)), "note": "ВВП, маржа, ликвидность, дороги и ещё много непонятной магии"},
        {"key": "doctrine_income", "label": "Доход экономической доктрины", "amount": int(revenue_payload.get("doctrine_income", 0)), "note": doctrine_spec.get("label", doctrine_key)},
        {"key": "automatic_stabilizer", "label": "Автоматическая фискальная стабилизация", "amount": int(revenue_payload.get("automatic_stabilizer", 0)), "note": "ограниченный чрезвычайный резерв после реальной перенастройки политики"},
    ]
    rows = [row for row in rows if row["amount"]]

    macro_payload = {
        **{key: round(value, 6) for key, value in macro.items()},
        "price_level": round(state["price_level"], 6),
        "inflation": round(state["inflation"], 8),
        "expected_inflation": round(state["expected_inflation"], 8),
        "money_supply": round(state["money_supply"], 2),
        "velocity": round(state["velocity"], 6),
        "capital_stock": round(sum(sectors["capital"].values()), 2),
        "infrastructure": round(state["infrastructure"], 2),
        "human_capital": round(state["human_capital"], 2),
        "tax_capacity": round(state["tax_capacity"], 6),
        "corruption": round(state["corruption"], 6),
        "confidence": round(state["confidence"], 6),
        "inequality": round(state["inequality"], 6),
        "debt": round(state["debt"], 2),
        "debt_ratio": round(debt_ratio, 6),
        # Выпуск на занятого: раньше ключ не публиковался вовсе, и легаси-отчёт
        # честно показывал macro.get("labor_productivity", 0.0) == 0.
        "labor_productivity": round(
            finite(macro.get("real_output", 0.0)) / max(1.0, finite(macro.get("labor", 1.0))), 6
        ),
        "interest_rate": round(finance["sovereign_rate"], 8),
        "trade_balance": round(trade["trade_balance"], 4),
        "current_account": round(trade["current_account"], 4),
        "import_dependency": round(trade["import_dependency"], 6),
        "terms_of_trade": round(trade["terms_of_trade"], 6),
        "exchange_rate": round(trade["exchange_rate"], 6),
        "private_credit": round(finance["desired_private_credit"], 2),
        "credit_to_gdp": round(finance["credit_to_gdp"], 6),
        "banking_health": round(finance["banking_health"], 6),
        "market_rate": round(finance["market_rate"], 8),
        "slave_ratio": round(state["demographics"]["slave_ratio"], 6),
        "urbanization": round(state["demographics"]["urbanization_rate"], 6),
        "slave_revolt_risk": round(state["demographics"]["slave_revolt_risk"], 6),
    }

    statement = {
        "version": ECONOMY_VERSION,
        "microformula_version": int(getattr(ECONOMY_MODIFIERS, "MICROFORMULA_VERSION", 0)) if ECONOMY_MODIFIERS is not None else 0,
        "microformula_count": len(magic_rows),
        "microformula_summary": microformula_summary,
        "micro_income_candidate": round(candidate_micro_income, 6),
        "micro_income_realized": round(
            sum(finite(row.get("gold_per_turn", 0.0)) for row in magic_rows), 6
        ),
        "turn": int(getattr(player, "turn", 1)),
        "rows": rows,
        "raw_gold": money(candidate_revenue_total),
        "difficulty_mult": finite(context.get("income_mult", 1.0), 1.0),
        "after_difficulty": money(candidate_revenue_total),
        "tech_percent": finite(context.get("tech_productivity", 0.0)),
        "percent_mult": 1.0 + finite(context.get("tech_productivity", 0.0)),
        "final_gold": revenue_total_game,
        "final_grain": money(grain["total_supply"]),
        "grain_consumption": money(grain["consumption"]),
        "revenues": revenue_payload,
        "religion_economy": {
            "tax_multiplier": round(religion_tax, 6),
            "levy_multiplier": round(clamp(finite(religion_economy.get("levy_multiplier", 1.0), 1.0), 0.50, 1.25), 6),
            "trade_multiplier": round(religion_trade, 6),
            "minority_provinces": int(finite(religion_economy.get("minority_provinces", 0), 0)),
            "details": religion_economy.get("details", []) if isinstance(religion_economy.get("details", []), list) else [],
        },
        "expenditures": expenditure_payload,
        "macro": macro_payload,
        "sectors": {
            "output": {key: round(value, 4) for key, value in sectors["output"].items()},
            "capital": {key: round(value, 4) for key, value in sectors["capital"].items()},
            "labor": {key: round(value, 4) for key, value in sectors["labor"].items()},
            "labor_shares": {key: round(value, 9) for key, value in sectors["labor_shares"].items()},
            "capital_shares": {key: round(value, 9) for key, value in sectors["capital_shares"].items()},
            "profitability": {key: round(value, 6) for key, value in sectors["profitability"].items()},
            "bottlenecks": {key: round(value, 6) for key, value in sectors["bottlenecks"].items()},
            "labor_mobility": round(sectors["labor_mobility"], 6),
            "capital_mobility": round(sectors["capital_mobility"], 6),
        },
        "demographics": {
            **{key: round(finite(value), 6) for key, value in state["demographics"].items() if isinstance(value, (int, float))},
            "free_labor": round(sectors["free_labor"], 4),
            "slave_labor": round(sectors["slave_labor"], 4),
            "slave_maintenance_cost": round(state["demographics"]["slave_population"] * state["grain_price"] * state["price_level"] * 0.040, 4),
        },
        "finance": {key: round(value, 6) for key, value in finance.items()},
        "trade": {
            **{key: round(value, 6) for key, value in trade.items() if isinstance(value, (int, float))},
            "supply": {key: round(value, 4) for key, value in trade["supply"].items()},
            "demand": {key: round(value, 4) for key, value in trade["demand"].items()},
            "exports": {key: round(value, 4) for key, value in trade["exports"].items()},
            "imports": {key: round(value, 4) for key, value in trade["imports"].items()},
            "world_prices": {key: round(value, 4) for key, value in trade["world_prices"].items()},
            "domestic_prices": {key: round(value, 4) for key, value in trade["domestic_prices"].items()},
        },
        "grain": {key: round(value, 6) for key, value in grain.items()},
        "political_economy": politics,
        "magic_modifiers": magic_rows,
        "automation": {
            "enabled": bool(automation.get("enabled", True)),
            "doctrine": doctrine_key,
            "doctrine_label": doctrine_spec.get("label", doctrine_key),
            "target_floor": target_floor if target_floor > -10**8 else None,
            "structural_balance": structural_balance_game,
            "stabilizer_income": int(revenue_payload.get("automatic_stabilizer", 0)),
        },
        "national_accounts": national_accounts,
        "roman_accounts": roman_accounts,
        "flow_of_funds": flow_of_funds,
        "sectoral_balances": {key: round(value, 4) for key, value in sectoral_balances.items()},
        "fiscal_stabilization": {
            **fiscal_stabilization,
            "candidate": money(fiscal_stabilization["candidate"]),
            "realized": money(fiscal_stabilization["realized"]),
            "previous": money(fiscal_stabilization["previous"]),
            "lower_bound": money(fiscal_stabilization["lower_bound"]),
            "upper_bound": money(fiscal_stabilization["upper_bound"]),
            "realization_factor": round(realization_factor, 6),
        },
        "candidate_revenue_total": money(candidate_revenue_total),
        "guaranteed_revenue_total": money(guaranteed_revenue_total),
        "revenue_total": revenue_total_game,
        "expense_total": expense_total_game,
        "primary_balance": primary_balance_game,
        "structural_balance": structural_balance_game,
        "overall_balance": overall_balance_game,
        "upkeep_gold": expense_total_game,
        "upkeep_grain": money(grain["consumption"]),
        "mutated": bool(mutate),
    }
    return statement


def preview_turn(player: Any, context: dict[str, Any]) -> dict[str, Any]:
    return build_statement(player, context, mutate=False)


def _apply_programmes(player: Any, state: dict[str, Any], statement: dict[str, Any]) -> None:
    programmes = statement["expenditures"]["programmes"]
    efficiency = statement["political_economy"]["programme_efficiency"]
    effective = {
        key: max(0.0, finite(programmes.get(key, 0))) * clamp(finite(efficiency.get(key, 1.0)), 0.1, 1.5)
        for key in BUDGET_KEYS
    }
    infrastructure = effective["infrastructure"]
    administration = effective["administration"]
    military = effective["military"]
    welfare = effective["welfare"]
    science = effective["science"]
    religion = effective["religion"]

    state["infrastructure"] += 0.22 * math.log1p(infrastructure) / (1.0 + state["infrastructure"] / 90.0)
    state["tax_capacity"] = clamp(state["tax_capacity"] + 0.0007 * math.log1p(administration), 0.03, 0.99)
    state["human_capital"] += 0.12 * math.log1p(science) / (1.0 + state["human_capital"] / 100.0)
    state["innovation"]["cumulative_science_spending"] += science
    state["innovation"]["research_stock"] += math.sqrt(science) * (0.45 + 0.55 * state["confidence"])

    if hasattr(player, "science_points"):
        player.science_points = max(0, int(getattr(player, "science_points", 0)) + money(science * 0.20))
    if hasattr(player, "faith"):
        player.faith = max(0, int(getattr(player, "faith", 0)) + money(religion * 0.18))
    if hasattr(player, "morale"):
        player.morale = int(clamp(finite(getattr(player, "morale", 70)) + min(3.0, math.log1p(military) * 0.38), 0.0, 100.0))
    if hasattr(player, "unrest"):
        relief = min(4.5, math.log1p(welfare) * 0.52)
        player.unrest = int(clamp(finite(getattr(player, "unrest", 0)) - relief, 0.0, 100.0))
    if hasattr(player, "people_rep") and welfare > 0:
        player.people_rep = int(clamp(finite(getattr(player, "people_rep", 50)) + min(2.2, math.log1p(welfare) * 0.18), 0.0, 100.0))

    # Политический перекос: военные расходы без сенатской легитимности раздражают общество.
    senate = finite(getattr(player, "senate_rep", 50), 50)
    total = max(1.0, sum(programmes.values()))
    military_share = programmes.get("military", 0.0) / total
    if military_share > 0.42 and senate < 35 and hasattr(player, "unrest"):
        player.unrest = int(clamp(finite(getattr(player, "unrest", 0)) + 1.0 + 3.0 * (military_share - 0.42), 0.0, 100.0))


def _update_sectoral_economy(
    player: Any,
    context: dict[str, Any],
    state: dict[str, Any],
    statement: dict[str, Any],
) -> None:
    allocation = allocate_labor_and_capital(player, context, state, mutate=True)
    sectors = statement["sectors"]
    finance = statement["finance"]
    programmes = statement["expenditures"]["programmes"]
    policy_weights = SECTOR_POLICIES[state["sector_policy"]]["weights"]

    private_investment_real = max(0.0, finite(finance["private_investment"])) / max(0.10, state["price_level"])
    public_investment_real = (
        max(0.0, finite(programmes.get("infrastructure", 0)))
        + 0.30 * max(0.0, finite(programmes.get("science", 0)))
        + 0.18 * max(0.0, finite(programmes.get("military", 0)))
    ) / max(0.10, state["price_level"])
    profitability = {key: max(0.01, finite(sectors["profitability"].get(key, 1.0))) for key in SECTOR_KEYS}
    private_weights = normalize_sector_shares(
        {key: profitability[key] * policy_weights[key] for key in SECTOR_KEYS},
        DEFAULT_SECTOR_CAPITAL_SHARES,
    )
    public_weights = normalize_sector_shares(
        {
            "agriculture": 0.16 + programmes.get("welfare", 0) * 0.0002,
            "mining": 0.13 + programmes.get("military", 0) * 0.0002,
            "manufacturing": 0.21 + programmes.get("military", 0) * 0.0003,
            "construction": 0.34 + programmes.get("infrastructure", 0) * 0.0004,
            "commerce": 0.16 + programmes.get("administration", 0) * 0.0002,
        },
        DEFAULT_SECTOR_CAPITAL_SHARES,
    )
    for key in SECTOR_KEYS:
        capital = max(1.0, state["sectoral_capital"][key])
        depreciation = state["sectoral_depreciation"][key]
        investment = private_investment_real * private_weights[key] + public_investment_real * public_weights[key]
        diminishing = 1.0 / (1.0 + capital / 800.0)
        state["sectoral_capital"][key] = max(1.0, capital * (1.0 - depreciation) + investment * (0.11 + 0.14 * diminishing))
        state["sectoral_output"][key] = max(0.0, finite(sectors["output"].get(key, 0.0)))
        state["sectoral_profitability"][key] = profitability[key]
    state["capital_stock"] = sum(state["sectoral_capital"].values())

    # Интенсивное земледелие истощает почвы; инфраструктура и знания частично восстанавливают.
    agri_intensity = state["sectoral_labor_share"]["agriculture"] + state["sectoral_capital"]["agriculture"] / max(1.0, state["capital_stock"])
    fertility_loss = max(0.0, agri_intensity - 0.72) * 0.0015
    fertility_recovery = 0.00025 + state["human_capital"] / 2_000_000.0 + programmes.get("infrastructure", 0) / 5_000_000.0
    state["soil_fertility"] = clamp(state["soil_fertility"] - fertility_loss + fertility_recovery, 0.25, 1.35)
    mining_intensity = state["sectoral_output"]["mining"] / max(1.0, state["sectoral_capital"]["mining"])
    state["resource_depletion"] = clamp(state["resource_depletion"] + 0.00035 * mining_intensity - 0.00008, 0.0, 0.95)


def _update_demography(
    player: Any,
    context: dict[str, Any],
    state: dict[str, Any],
    statement: dict[str, Any],
) -> None:
    demo = state["demographics"]
    grain = statement["grain"]
    programmes = statement["expenditures"]["programmes"]
    welfare = max(0.0, finite(programmes.get("welfare", 0)))
    shock_mods = _active_shock_modifiers(state)
    total = max(20.0, demo["free_population"] + demo["slave_population"])
    carrying = max(total + 1.0, state["carrying_capacity"])
    food_ratio = finite(grain["total_supply"]) / max(1.0, finite(grain["consumption"]))
    density = total / carrying
    urban_ratio = demo["urban_population"] / max(1.0, total)
    price_pressure = max(0.0, grain["price"] / max(0.20, state["wage_index"]) - 1.0)
    birth_rate = clamp(
        0.0175
        + 0.0035 * min(1.0, food_ratio)
        + 0.00018 * math.log1p(welfare)
        - 0.0060 * density
        - 0.0030 * urban_ratio,
        0.002,
        0.035,
    )
    death_rate = clamp(
        _config(context).base_mortality
        + 0.010 * max(0.0, 1.0 - food_ratio)
        + 0.0045 * price_pressure
        + 0.0035 * urban_ratio
        - 0.00022 * math.log1p(welfare)
        + shock_mods["mortality"],
        0.003,
        0.12,
    )
    free_growth = demo["free_population"] * (birth_rate - death_rate) * (1.0 - density)
    slave_growth = demo["slave_population"] * (0.70 * birth_rate - 1.12 * death_rate)

    province_count = max(1, int(context.get("province_count", 1)))
    last_province_count = int(finite(demo.get("last_province_count", province_count), province_count))
    new_provinces = max(0, province_count - last_province_count)
    captives = (
        new_provinces * _config(context).captured_slaves_per_province
        + max(0.0, finite(context.get("captured_slaves", 0.0)))
        + max(0.0, finite(context.get("recent_battle_captives", 0.0)))
    )
    manumission_rate = clamp(
        0.0015 + 0.000015 * state["human_capital"] + 0.00010 * math.log1p(welfare),
        0.001,
        0.025,
    )
    manumissions = demo["slave_population"] * manumission_rate
    demo["slave_population"] = max(0.0, demo["slave_population"] + slave_growth + captives - manumissions)
    demo["free_population"] = max(1.0, demo["free_population"] + free_growth + manumissions)

    total_after = demo["free_population"] + demo["slave_population"]
    wage_pull = statement["sectors"]["profitability"]["manufacturing"] + statement["sectors"]["profitability"]["commerce"]
    rural_push = statement["grain"]["price"] + max(0.0, 1.0 - state["soil_fertility"])
    migration_rate = clamp(
        0.002
        + 0.00004 * state["infrastructure"]
        + 0.00003 * state["human_capital"]
        + 0.0015 * math.tanh(wage_pull - rural_push)
        - 0.00005 * finite(context.get("effective_unrest", 0.0)),
        -0.012,
        0.025,
    )
    urban_change = demo["rural_population"] * max(0.0, migration_rate) - demo["urban_population"] * max(0.0, -migration_rate)
    current_geo_total = max(1.0, demo["urban_population"] + demo["rural_population"])
    population_scale = total_after / current_geo_total
    demo["urban_population"] = max(1.0, demo["urban_population"] * population_scale + urban_change)
    demo["rural_population"] = max(1.0, total_after - demo["urban_population"])
    if demo["urban_population"] > total_after - 1.0:
        demo["urban_population"] = total_after - 1.0
        demo["rural_population"] = 1.0

    demo["birth_rate"] = birth_rate
    demo["death_rate"] = death_rate
    demo["urbanization_rate"] = clamp(demo["urban_population"] / max(1.0, total_after), 0.02, 0.95)
    demo["slave_ratio"] = clamp(demo["slave_population"] / max(1.0, total_after), 0.0, 0.85)
    demo["captives_last_turn"] = captives
    demo["manumissions_last_turn"] = manumissions
    demo["last_province_count"] = float(province_count)
    welfare_relief = min(0.22, math.log1p(welfare) / 30.0)
    demo["slave_revolt_risk"] = clamp(
        sigmoid(
            (demo["slave_ratio"] - 0.22) * 8.5
            + state["inequality"] * 2.6
            + state["corruption"] * 2.0
            + finite(context.get("effective_unrest", 0.0)) / 28.0
            - welfare_relief * 4.0
            - 2.3
        ),
        0.0,
        0.95,
    )
    state["population"] = clamp(total_after, 20.0, 100_000.0)
    capacity_map = _province_carrying_capacity(context)
    state["carrying_capacity"] = clamp(
        0.82 * state["carrying_capacity"] + 0.18 * (capacity_map + 0.60 * state["infrastructure"]),
        50.0,
        150_000.0,
    )


def _update_institutions(player: Any, context: dict[str, Any], state: dict[str, Any], statement: dict[str, Any]) -> None:
    province_count = max(1, int(context.get("province_count", 1)))
    admin_spend = finite(statement["expenditures"]["programmes"].get("administration", 0))
    debt_ratio = finite(statement["macro"]["debt_ratio"])
    rent_seeking = finite(statement["political_economy"]["rent_seeking"])
    structural_corruption = 0.06 + 0.54 * sigmoid((province_count - 5.0 - 14.0 * state["tax_capacity"]) / 3.8)
    structural_corruption += 0.08 * debt_ratio + 0.10 * state["tax_rate"]
    anti_corruption = 0.016 * math.log1p(admin_spend)
    rent_pressure = min(0.08, rent_seeking / max(1.0, statement["revenue_total"]) * 0.10)
    state["corruption"] = clamp(0.84 * state["corruption"] + 0.16 * structural_corruption - anti_corruption + rent_pressure, 0.005, 0.95)

    legitimacy = finite(statement["macro"]["political_legitimacy"])
    stance_effect = FISCAL_STANCES[state["fiscal_stance"]]["confidence"]
    standard_effect = COIN_STANDARDS[state["coin_standard"]]["confidence"]
    balance_ratio = statement["overall_balance"] / max(1.0, statement["revenue_total"])
    confidence_target = 0.34 + 0.40 * legitimacy + 0.18 * clamp(balance_ratio + 0.5, 0.0, 1.0)
    confidence_target -= 0.22 * max(0.0, state["inflation"] - 0.08)
    confidence_target -= 0.18 * clamp(debt_ratio - 0.8, 0.0, 2.0)
    confidence_target -= 0.12 * statement["macro"]["import_dependency"]
    confidence_target += stance_effect + standard_effect + _active_shock_modifiers(state)["confidence"]
    state["confidence"] = clamp(0.78 * state["confidence"] + 0.22 * confidence_target, 0.01, 0.995)

    welfare = finite(statement["expenditures"]["programmes"].get("welfare", 0))
    inequality_target = clamp(
        0.25 + 0.35 * state["tax_rate"] + 0.28 * state["corruption"] + 0.16 * state["demographics"]["slave_ratio"] - 0.002 * welfare,
        0.06,
        0.90,
    )
    state["inequality"] = clamp(0.88 * state["inequality"] + 0.12 * inequality_target, 0.03, 0.95)

    for key in INTEREST_GROUPS:
        group = state["interest_groups"][key]
        target = finite(statement["political_economy"]["satisfaction_targets"].get(key, 0.5), 0.5)
        group["satisfaction"] = clamp(0.80 * finite(group.get("satisfaction", 0.5)) + 0.20 * target, 0.01, 0.99)
        group["rents"] = finite(statement["political_economy"]["group_rents"].get(key, 0.0))
    influence_raw = {
        key: max(0.01, finite(state["interest_groups"][key].get("influence", 0.2)) * (0.98 + 0.04 * state["interest_groups"][key]["satisfaction"]))
        for key in INTEREST_GROUPS
    }
    total_influence = sum(influence_raw.values())
    for key in INTEREST_GROUPS:
        state["interest_groups"][key]["influence"] = influence_raw[key] / total_influence


def _update_financial_market(state: dict[str, Any], statement: dict[str, Any]) -> None:
    financial = state["financial"]
    finance = statement["finance"]
    old_credit = max(0.0, financial["private_credit"])
    desired = max(0.0, finite(finance["desired_private_credit"]))
    adjustment = 0.22 * CREDIT_POLICIES[financial["policy"]]["credit_growth"] + 0.18
    new_credit = max(0.0, old_credit + clamp(adjustment, 0.05, 0.36) * (desired - old_credit))
    credit_growth = new_credit / max(1.0, old_credit) - 1.0
    deposit_target = max(1.0, finance["private_savings"] * 2.2 + new_credit * 0.42)
    financial["deposit_base"] = max(1.0, 0.84 * financial["deposit_base"] + 0.16 * deposit_target)
    financial["private_credit"] = new_credit
    financial["credit_growth"] = clamp(credit_growth, -0.95, 5.0)
    financial["market_rate"] = clamp(finite(finance["market_rate"]), 0.0, 3.0)
    state["interest_rate"] = clamp(finite(finance["sovereign_rate"]), 0.0, 5.0)
    financial["loan_demand"] = max(0.0, finite(finance["loan_demand"]))
    financial["loan_supply"] = max(0.0, finite(finance["loan_supply"]))
    financial["credit_to_gdp"] = clamp(finite(finance["credit_to_gdp"]), 0.0, 20.0)
    financial["leverage"] = clamp(finite(finance["leverage"]), 0.0, 20.0)
    financial["crowding_out"] = clamp(finite(finance["crowding_out"]), 0.0, 1.0)
    financial["private_investment"] = max(0.0, finite(finance["private_investment"]))
    policy_risk = CREDIT_POLICIES[financial["policy"]]["risk"]
    health_target = (
        0.78
        + 0.18 * state["confidence"]
        - 0.22 * max(0.0, financial["leverage"] - 1.0)
        - 0.16 * max(0.0, state["inflation"] - 0.12)
        - policy_risk
    )
    financial["banking_health"] = clamp(0.86 * financial["banking_health"] + 0.14 * health_target, 0.01, 0.99)


def _update_trade_state(state: dict[str, Any], statement: dict[str, Any]) -> None:
    trade = state["trade"]
    current = statement["trade"]
    for key in ("world_prices", "domestic_prices", "exports", "imports"):
        trade[key] = {good: max(0.0, finite(value)) for good, value in current[key].items()}
    for key in ("trade_balance", "current_account", "import_dependency", "terms_of_trade", "exchange_rate", "foreign_confidence", "trade_openness", "embargo_exposure"):
        trade[key] = finite(current[key])
    # Ограниченный реальный приток/отток рабов через рынок.
    imported_slaves = current["imports"].get("slaves", 0.0)
    exported_slaves = current["exports"].get("slaves", 0.0)
    demo = state["demographics"]
    demo["slave_population"] = max(0.0, demo["slave_population"] + 0.25 * (imported_slaves - exported_slaves))
    new_total = max(20.0, demo["free_population"] + demo["slave_population"])
    geographic_total = max(1.0, demo["urban_population"] + demo["rural_population"])
    scale = new_total / geographic_total
    demo["urban_population"] *= scale
    demo["rural_population"] *= scale
    demo["slave_ratio"] = clamp(demo["slave_population"] / new_total, 0.0, 0.85)
    demo["urbanization_rate"] = clamp(demo["urban_population"] / new_total, 0.02, 0.95)
    state["population"] = new_total


def _update_innovation(player: Any, context: dict[str, Any], state: dict[str, Any], statement: dict[str, Any]) -> list[str]:
    innovation = state["innovation"]
    romanization = clamp(finite(context.get("avg_romanization", 35.0)), 0.0, 100.0)
    human = state["human_capital"]
    science = max(0.0, finite(statement["expenditures"]["programmes"].get("science", 0)))
    diffusion = clamp(0.08 + romanization / 280.0 + human / 1200.0, 0.08, 0.62)
    innovation["diffusion"] = diffusion
    tech_context = max(-0.25, finite(context.get("tech_productivity", 0.0)))
    for key in SECTOR_KEYS:
        frontier = 1.0 + 0.85 * max(0.0, tech_context) + 0.002 * human
        current = innovation["sector_technology"][key]
        innovation["sector_technology"][key] = clamp(current + diffusion * 0.0012 * max(0.0, frontier - current), 0.5, 20.0)

    messages: list[str] = []
    turn = int(getattr(player, "turn", 1))
    if turn != int(innovation.get("last_breakthrough_turn", -999)):
        stock = max(0.0, innovation["research_stock"])
        chance = clamp(0.002 + 0.00008 * math.sqrt(stock) + 0.000012 * human + 0.000008 * romanization + science / 2_000_000.0, 0.0, 0.12)
        rng = _rng_for(player, state, "innovation")
        if rng.random() < chance:
            weights = {
                key: 1.0 / max(0.25, innovation["sector_technology"][key])
                * (1.0 + statement["sectors"]["profitability"][key])
                for key in SECTOR_KEYS
            }
            keys = list(SECTOR_KEYS)
            chosen = rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]
            gain = 0.025 + rng.random() * 0.045
            innovation["sector_technology"][chosen] = clamp(innovation["sector_technology"][chosen] * (1.0 + gain), 0.5, 20.0)
            innovation["research_stock"] *= 0.72
            innovation["breakthroughs"] = int(innovation.get("breakthroughs", 0)) + 1
            innovation["last_breakthrough_turn"] = turn
            messages.append(f"научный прорыв в отрасли «{SECTOR_LABELS[chosen]}» (+{gain:.1%} технологии)")
    military_spend = max(0.0, finite(statement["expenditures"]["programmes"].get("military", 0)))
    innovation["military_technology"] = clamp(
        innovation["military_technology"] + 0.00012 * math.log1p(military_spend) + 0.00008 * max(0.0, tech_context),
        0.5,
        10.0,
    )
    return messages


def _update_money(state: dict[str, Any], statement: dict[str, Any], context: dict[str, Any]) -> None:
    macro = statement["macro"]
    real_output = max(1.0, finite(macro["real_output"]))
    pending_mint = max(0.0, finite(state.get("pending_minting", 0.0)))
    state["money_supply"] = max(10.0, state["money_supply"] + pending_mint)
    state["pending_minting"] = 0.0

    previous_output = max(1.0, finite(state.get("last_real_output", real_output), real_output))
    output_growth = clamp(real_output / previous_output - 1.0, -0.20, 0.20)
    endogenous_money_growth = clamp(
        _config(context).base_money_growth + _config(context).money_output_response * output_growth,
        -0.03,
        0.06,
    )
    state["money_supply"] = max(10.0, state["money_supply"] * (1.0 + endogenous_money_growth))
    state["last_real_output"] = real_output

    standard = COIN_STANDARDS[state["coin_standard"]]
    velocity_target = 1.15 + 1.15 * state["confidence"] + standard["velocity"]
    velocity_target += 0.75 * max(0.0, state["expected_inflation"])
    velocity_target += 0.10 * state["financial"]["credit_growth"]
    state["velocity"] = clamp(0.78 * state["velocity"] + 0.22 * velocity_target, 0.10, 15.0)

    anchor = max(0.0001, state["monetary_anchor"])
    shock_price = 1.0 + _active_shock_modifiers(state)["price"]
    target_price = clamp(state["money_supply"] * state["velocity"] / (anchor * real_output) * shock_price, 0.05, 1000.0)
    old_price = state["price_level"]
    gap = target_price / max(0.01, old_price) - 1.0
    adjustment_speed = _config(context).price_adjustment + 0.10 * min(1.0, abs(gap))
    new_price = clamp(old_price * (1.0 + adjustment_speed * gap), 0.05, 1000.0)
    inflation = clamp(new_price / max(0.01, old_price) - 1.0, -0.80, 25.0)
    state["price_level"] = new_price
    state["inflation"] = inflation
    state["expected_inflation"] = clamp(0.70 * state["expected_inflation"] + 0.30 * inflation, -0.50, 15.0)
    state["wage_index"] = clamp(state["wage_index"] * (1.0 + 0.55 * inflation), 0.05, 500.0)


def _post_statement_ledger(player: Any, state: dict[str, Any], statement: dict[str, Any]) -> None:
    turn = int(getattr(player, "turn", 1))
    revenue_accounts = {
        "direct_tax": "Доходы: прямые налоги",
        "customs": "Доходы: таможня",
        "domains": "Доходы: государственные владения",
        "tribute": "Доходы: дань",
        "commerce": "Доходы: торговля",
        "trade_routes": "Доходы: торговые пути",
        "rare_resources": "Доходы: редкие ресурсы",
        "caravans": "Доходы: караваны",
        "base_revenue": "Доходы: столица",
        "micro_income": "Доходы: наноэкономические модификаторы",
        "doctrine_income": "Доходы: экономическая доктрина",
        "automatic_stabilizer": "Доходы: автоматическая стабилизация",
    }
    for key, account in revenue_accounts.items():
        _ledger_post(state, turn, "Казна", account, statement["revenues"].get(key, 0), account)
    expense_accounts = {
        "administration": "Расходы: управление",
        "military_upkeep": "Расходы: армия",
        "fleet_upkeep": "Расходы: флот",
        "auxiliary_upkeep": "Расходы: ауксилии",
        "artillery_upkeep": "Расходы: артиллерия",
        "garrison_upkeep": "Расходы: провинциальные гарнизоны",
        "municipal_building_upkeep": "Расходы: содержание городских сооружений",
        "tribute_paid": "Расходы: внешние платежи",
        "interest": "Расходы: проценты",
        "treasury_management": "Расходы: хранение и управление казной",
        "strategic_reserve": "Активы: стратегический зерновой резерв",
    }
    for key, account in expense_accounts.items():
        _ledger_post(state, turn, account, "Казна", statement["expenditures"].get(key, 0), account)
    for key, amount in statement["expenditures"]["programmes"].items():
        _ledger_post(state, turn, f"Расходы: {BUDGET_LABELS.get(key, key)}", "Казна", amount, "Бюджетное ассигнование")

    # Flow-of-funds: кредит создаёт одновременно актив банков и обязательство частного сектора.
    credit_change = finite(statement["flow_of_funds"].get("credit_change", 0.0))
    if credit_change > 0:
        _ledger_post(state, turn, "Активы банков: частные ссуды", "Обязательства частного сектора", credit_change, "Расширение частного кредита")
    elif credit_change < 0:
        _ledger_post(state, turn, "Обязательства частного сектора", "Активы банков: частные ссуды", -credit_change, "Сокращение частного кредита")
    for key in SECTOR_KEYS:
        investment_share = statement["sectors"]["capital_shares"][key]
        amount = statement["national_accounts"]["expenditure"]["private_investment"] * investment_share
        _ledger_post(state, turn, f"Капитал: {SECTOR_LABELS[key]}", "Сбережения частного сектора", amount, "Частное накопление капитала")


def _new_shock(kind: str, magnitude: float, duration: int, turn: int, detail: str = "") -> dict[str, Any]:
    return {
        "kind": kind,
        "title": SHOCK_LABELS.get(kind, kind),
        "magnitude": clamp(magnitude, 0.01, 0.90),
        "remaining": max(1, int(duration)),
        "started": int(turn),
        "detail": str(detail),
    }


def apply_economic_shocks(player: Any, context: dict[str, Any], state: dict[str, Any]) -> list[str]:
    """Обновляет длительные шоки и создаёт новые воспроизводимым RNG."""
    turn = int(getattr(player, "turn", 1))
    if int(state.get("last_shock_turn", -1)) == turn:
        return []
    state["last_shock_turn"] = turn
    active: list[dict[str, Any]] = []
    for item in state.get("active_shocks", []):
        if not isinstance(item, dict):
            continue
        remaining = int(finite(item.get("remaining", 0))) - 1
        if remaining > 0:
            item = dict(item)
            item["remaining"] = remaining
            active.append(item)
    state["active_shocks"] = active

    rng = _rng_for(player, state, "economic-shocks")
    cfg = _config(context)
    demo = state["demographics"]
    finance = state["financial"]
    messages: list[str] = []
    candidates: list[tuple[str, float, float, int, str]] = []

    urbanization = demo["urbanization_rate"]
    welfare_hint = normalize_budget_shares(state["budget_shares"])["welfare"]
    epidemic_prob = cfg.shock_scale * clamp(0.0025 + 0.012 * urbanization + 0.008 * max(0.0, 0.12 - welfare_hint), 0.0, 0.035)
    candidates.append(("epidemic", epidemic_prob, 0.30 + 0.40 * rng.random(), rng.randint(3, 8), "города и военные дороги ускорили распространение болезни"))

    climate_prob = cfg.shock_scale * 0.017
    climate_kind = rng.choice(["drought", "flood", "locusts"])
    candidates.append((climate_kind, climate_prob, 0.25 + 0.55 * rng.random(), rng.randint(2, 6), "урожай и цены на хлеб оказались под ударом"))

    mine_prob = cfg.shock_scale * 0.006
    mine_kind = "mine_depletion" if state["resource_depletion"] > 0.40 and rng.random() < 0.68 else "mine_discovery"
    candidates.append((mine_kind, mine_prob, 0.22 + 0.48 * rng.random(), rng.randint(4, 10), "геологи и арендаторы сообщили о перемене в добыче"))

    currency_prob = cfg.shock_scale * clamp(0.002 + 0.055 * max(0.0, state["inflation"] - 0.18) + 0.018 * max(0.0, 0.40 - state["confidence"]), 0.0, 0.18)
    candidates.append(("currency_crisis", currency_prob, 0.28 + 0.50 * rng.random(), rng.randint(3, 7), "монете перестали доверять на внешних и внутренних рынках"))

    panic_prob = cfg.shock_scale * clamp(
        0.001 + 0.055 * max(0.0, finance["leverage"] - 1.05) + 0.045 * max(0.0, 0.48 - state["confidence"]) + 0.035 * max(0.0, 0.55 - finance["banking_health"]),
        0.0,
        0.16,
    )
    candidates.append(("banking_panic", panic_prob, 0.30 + 0.48 * rng.random(), rng.randint(3, 8), "вкладчики требуют серебро, argentarii сокращают ссуды"))

    slave_prob = cfg.shock_scale * clamp(0.001 + 0.085 * demo["slave_revolt_risk"], 0.0, 0.11)
    candidates.append(("slave_revolt", slave_prob, 0.30 + 0.55 * rng.random(), rng.randint(2, 6), "латифундии и рудники охвачены мятежом"))

    boom_prob = cfg.shock_scale * clamp(0.003 + 0.012 * state["confidence"] * state["trade"]["trade_openness"], 0.0, 0.025)
    candidates.append(("trade_boom", boom_prob, 0.20 + 0.35 * rng.random(), rng.randint(3, 7), "купеческие сети расширили оборот и морские перевозки"))

    existing_kinds = {item.get("kind") for item in active}
    if len(active) < cfg.max_active_shocks:
        rng.shuffle(candidates)
        for kind, probability, magnitude, duration, detail in candidates:
            if kind in existing_kinds:
                continue
            if rng.random() < probability:
                shock = _new_shock(kind, magnitude, duration, turn, detail)
                active.append(shock)
                existing_kinds.add(kind)
                messages.append(f"{shock['title']}: {detail}")
                # Обычно не более одного нового крупного шока за ход.
                break

    # Немедленные последствия.
    for message in messages:
        kind = active[-1]["kind"] if active else ""
        magnitude = active[-1]["magnitude"] if active else 0.0
        if kind == "epidemic":
            loss = state["population"] * (0.004 + 0.012 * magnitude)
            free_share = state["demographics"]["free_population"] / max(1.0, state["population"])
            state["demographics"]["free_population"] = max(1.0, state["demographics"]["free_population"] - loss * free_share)
            state["demographics"]["slave_population"] = max(0.0, state["demographics"]["slave_population"] - loss * (1.0 - free_share))
            state["population"] = state["demographics"]["free_population"] + state["demographics"]["slave_population"]
            if hasattr(player, "unrest"):
                player.unrest = int(clamp(finite(getattr(player, "unrest", 0)) + 4 + 8 * magnitude, 0.0, 100.0))
        elif kind == "mine_discovery":
            state["resource_depletion"] = clamp(state["resource_depletion"] - 0.08 * magnitude, 0.0, 0.95)
            state["sectoral_capital"]["mining"] += 4.0 + 10.0 * magnitude
        elif kind == "mine_depletion":
            state["resource_depletion"] = clamp(state["resource_depletion"] + 0.06 * magnitude, 0.0, 0.95)
        elif kind == "currency_crisis":
            state["confidence"] = clamp(state["confidence"] - 0.08 * magnitude, 0.01, 0.995)
            state["expected_inflation"] = clamp(state["expected_inflation"] + 0.18 * magnitude, -0.50, 15.0)
        elif kind == "banking_panic":
            state["financial"]["banking_health"] = clamp(state["financial"]["banking_health"] - 0.18 * magnitude, 0.01, 0.99)
            state["financial"]["last_crisis_turn"] = turn
        elif kind == "slave_revolt":
            if hasattr(player, "unrest"):
                player.unrest = int(clamp(finite(getattr(player, "unrest", 0)) + 6 + 10 * magnitude, 0.0, 100.0))
        elif kind == "trade_boom":
            state["confidence"] = clamp(state["confidence"] + 0.025 * magnitude, 0.01, 0.995)

    history = state.setdefault("shock_history", [])
    for message in messages:
        history.append({"turn": turn, "message": message, "shock": dict(active[-1]) if active else {}})
    del history[:-cfg.shock_history_limit]
    state["active_shocks"] = active
    return messages


def apply_turn(player: Any, context: dict[str, Any]) -> str | None:
    state = ensure_economy_state(player, context)
    run_economy_autopilot(player, context)
    statement = build_statement(player, context, mutate=True)
    _post_statement_ledger(player, state, statement)

    old_gold = finite(getattr(player, "gold", 0.0))
    old_grain = finite(getattr(player, "grain", 0.0))
    cash_after = old_gold + statement["overall_balance"]
    grain_after = old_grain + statement["grain"]["total_supply"] - statement["grain"]["consumption"]

    pending_bonds = max(0.0, finite(state.get("pending_bond_issue", 0.0)))
    if pending_bonds:
        state["debt"] += pending_bonds
        cash_after += pending_bonds
        _ledger_post(state, int(getattr(player, "turn", 1)), "Казна", "Обязательства: государственный долг", pending_bonds, "Размещение облигаций")
        state["pending_bond_issue"] = 0.0

    pending_repayment = min(state["debt"], max(0.0, finite(state.get("pending_debt_repayment", 0.0))), max(0.0, cash_after))
    if pending_repayment:
        state["debt"] -= pending_repayment
        cash_after -= pending_repayment
        _ledger_post(state, int(getattr(player, "turn", 1)), "Обязательства: государственный долг", "Казна", pending_repayment, "Погашение долга")
        state["pending_debt_repayment"] = 0.0

    automatic_issue = 0.0
    unfunded_gap = 0.0
    nominal_output = max(1.0, finite(statement["macro"]["nominal_output"]))
    banking_factor = clamp(statement["macro"]["banking_health"], 0.05, 1.0)
    credit_limit = nominal_output * (1.15 + 2.30 * state["confidence"] + 0.55 * banking_factor)
    if cash_after < 0:
        shortfall = -cash_after
        available_credit = max(0.0, credit_limit - state["debt"])
        automatic_issue = min(shortfall, available_credit)
        unfunded_gap = max(0.0, shortfall - automatic_issue)
        state["debt"] += automatic_issue
        state["arrears"] += unfunded_gap
        cash_after = 0.0
        _ledger_post(state, int(getattr(player, "turn", 1)), "Казна", "Обязательства: государственный долг", automatic_issue, "Автоматическое покрытие кассового разрыва")
        _ledger_post(state, int(getattr(player, "turn", 1)), "Расходы: просроченные обязательства", "Обязательства: задолженность поставщикам", unfunded_gap, "Непрофинансированный дефицит")

    if cash_after > 0 and state["arrears"] > 0:
        arrears_payment = min(state["arrears"], max(0.0, cash_after - 100.0) * 0.45)
        if arrears_payment > 0:
            state["arrears"] -= arrears_payment
            cash_after -= arrears_payment
            _ledger_post(state, int(getattr(player, "turn", 1)), "Обязательства: задолженность поставщикам", "Казна", arrears_payment, "Погашение бюджетной просрочки")

    if state.get("automatic_debt_repayment", True) and cash_after > 0 and state["debt"] > 0:
        repayment = min(state["debt"], max(0.0, cash_after - max(100.0, statement["expense_total"] * 1.5)) * 0.35)
        if repayment > 0:
            state["debt"] -= repayment
            cash_after -= repayment
            _ledger_post(state, int(getattr(player, "turn", 1)), "Обязательства: государственный долг", "Казна", repayment, "Автоматическое досрочное погашение")

    debt_ratio_after = state["debt"] / nominal_output
    restructured = 0.0
    if debt_ratio_after > 4.0 or state["arrears"] > nominal_output * 1.5:
        old_debt = state["debt"]
        state["debt"] *= 0.48
        state["arrears"] *= 0.30
        restructured = old_debt - state["debt"]
        state["confidence"] = clamp(state["confidence"] - 0.24, 0.01, 0.995)
        state["financial"]["banking_health"] = clamp(state["financial"]["banking_health"] - 0.16, 0.01, 0.99)
        if hasattr(player, "unrest"):
            player.unrest = int(clamp(finite(getattr(player, "unrest", 0)) + 14, 0.0, 100.0))
        if hasattr(player, "senate_rep"):
            player.senate_rep = int(clamp(finite(getattr(player, "senate_rep", 50)) - 10, 0.0, 100.0))
        if hasattr(player, "people_rep"):
            player.people_rep = int(clamp(finite(getattr(player, "people_rep", 50)) - 8, 0.0, 100.0))
        _ledger_post(state, int(getattr(player, "turn", 1)), "Обязательства: государственный долг", "Доходы: реструктуризация", restructured, "Принудительная конверсия долга")

    setattr(player, "gold", max(0, money(cash_after)))
    setattr(player, "grain", max(0, money(grain_after)))
    state["grain_price"] = finite(statement["grain"]["price"], 1.0)

    _apply_programmes(player, state, statement)
    _update_sectoral_economy(player, context, state, statement)
    _update_demography(player, context, state, statement)
    _update_institutions(player, context, state, statement)
    _update_financial_market(state, statement)
    _update_trade_state(state, statement)
    innovation_messages = _update_innovation(player, context, state, statement)
    _update_money(state, statement, context)
    automatic_support = max(0.0, finite(statement.get("automation", {}).get("stabilizer_income", 0.0)))
    if automatic_support > 0:
        pressure = automatic_support / max(1.0, nominal_output)
        state["corruption"] = clamp(state["corruption"] + min(0.012, pressure * 0.004), 0.005, 0.95)
        state["inflation"] = clamp(state["inflation"] + min(0.018, pressure * 0.005), -0.25, 5.0)
        state["confidence"] = clamp(state["confidence"] - min(0.015, pressure * 0.004), 0.01, 0.995)
        auto_state = state.setdefault("automation", {})
        auto_state["stabilizer_uses"] = int(finite(auto_state.get("stabilizer_uses", 0))) + 1
        auto_state["last_stabilizer_income"] = automatic_support
    shock_messages = apply_economic_shocks(player, context, state)
    state["unemployment"] = clamp(finite(statement["macro"]["unemployment"]), 0.0, 0.75)

    warning_parts: list[str] = []
    if automatic_support > 0:
        warning_parts.append(f"автоматическая фискальная стабилизация: +{money(automatic_support)} золота")
    if grain_after < 0:
        shortage = -grain_after
        severity = min(20, max(4, money(shortage / max(1.0, statement["upkeep_grain"]) * 25)))
        if hasattr(player, "unrest"):
            player.unrest = int(clamp(finite(getattr(player, "unrest", 0)) + severity, 0.0, 100.0))
        warning_parts.append(f"нехватка зерна; волнения +{severity}")
    debt_ratio = state["debt"] / max(1.0, nominal_output)
    if debt_ratio > 1.50:
        if hasattr(player, "senate_rep"):
            player.senate_rep = int(clamp(finite(getattr(player, "senate_rep", 50)) - 2, 0.0, 100.0))
        warning_parts.append("долг превышает 150% годового выпуска")
    if state["inflation"] > 0.18:
        if hasattr(player, "people_rep"):
            player.people_rep = int(clamp(finite(getattr(player, "people_rep", 50)) - 2, 0.0, 100.0))
        if hasattr(player, "unrest"):
            player.unrest = int(clamp(finite(getattr(player, "unrest", 0)) + 2, 0.0, 100.0))
        warning_parts.append(f"инфляция {state['inflation']:.1%}")
    if state["financial"]["banking_health"] < 0.35:
        warning_parts.append("банковская система близка к панике")
    if state["trade"]["import_dependency"] > 0.45:
        warning_parts.append("критическая импортная зависимость")
    if state["demographics"]["slave_revolt_risk"] > 0.55:
        warning_parts.append("высокий риск восстания рабов")
    if automatic_issue > 0:
        warning_parts.append(f"кассовый дефицит покрыт долгом: +{money(automatic_issue)}")
    if unfunded_gap > 0:
        warning_parts.append(f"не оплачено обязательств: {money(unfunded_gap)}")
    if restructured > 0:
        warning_parts.append(f"реструктуризация списала {money(restructured)} долга, но ударила по доверию")
    warning_parts.extend(innovation_messages)
    warning_parts.extend(shock_messages)

    statement["cash_change_after_financing"] = money(
        finite(getattr(player, "gold", 0.0)) - old_gold
    )
    fiscal = state.setdefault("fiscal", {})
    fiscal["last_realized_revenue"] = max(0.0, finite(statement["revenue_total"]) - finite(statement.get("automation", {}).get("stabilizer_income", 0.0)))
    fiscal["last_realized_stabilizable_revenue"] = max(
        0.0,
        fiscal["last_realized_revenue"] - finite(statement.get("guaranteed_revenue_total", 0.0)),
    )
    fiscal["last_realized_expense"] = max(0.0, finite(statement["expense_total"]))
    fiscal["last_realized_balance"] = finite(statement.get("structural_balance", statement["overall_balance"]))
    fiscal["last_candidate_revenue"] = max(
        0.0,
        finite(statement.get("candidate_revenue_total", statement["revenue_total"])),
    )
    fiscal["last_policy_signature"] = str(
        statement.get("fiscal_stabilization", {}).get(
            "policy_signature",
            _fiscal_policy_signature(state, context),
        )
    )
    fiscal["last_province_count"] = max(0, int(context.get("province_count", 0)))
    fiscal_history = fiscal.setdefault("history", [])
    fiscal_history.append({
        "turn": int(getattr(player, "turn", 1)),
        "candidate_revenue": int(
            statement.get("candidate_revenue_total", statement["revenue_total"])
        ),
        "revenue": int(statement["revenue_total"]),
        "expense": int(statement["expense_total"]),
        "balance": int(statement["overall_balance"]),
        "cash_change": int(statement["cash_change_after_financing"]),
    })
    del fiscal_history[:-120]

    setattr(player, "gold_income_last_turn", int(statement["revenue_total"]))
    setattr(player, "gold_expense_last_turn", int(statement["expense_total"]))
    setattr(player, "gold_per_turn", int(statement["overall_balance"]))

    state["last_statement"] = statement
    history = state.setdefault("history", [])
    history.append({
        "turn": int(getattr(player, "turn", 1)),
        "output": money(statement["macro"]["real_output"]),
        "revenue": statement["revenue_total"],
        "expense": statement["expense_total"],
        "balance": statement["overall_balance"],
        "gold": int(getattr(player, "gold", 0)),
        "debt": money(state["debt"]),
        "inflation": round(state["inflation"], 5),
        "price_level": round(state["price_level"], 4),
        "population": round(state["population"], 2),
        "corruption": round(state["corruption"], 4),
        "banking_health": round(state["financial"]["banking_health"], 4),
        "trade_balance": round(state["trade"]["trade_balance"], 2),
        "slave_ratio": round(state["demographics"]["slave_ratio"], 4),
        "sector_output": {key: round(state["sectoral_output"][key], 2) for key in SECTOR_KEYS},
    })
    del history[:-_config(context).history_limit]
    f_history = state.setdefault("flow_of_funds_history", [])
    f_history.append({"turn": int(getattr(player, "turn", 1)), **statement["flow_of_funds"]})
    del f_history[:-_config(context).history_limit]
    state["last_turn_processed"] = int(getattr(player, "turn", 1))
    return "⚠ " + "; ".join(warning_parts) + "." if warning_parts else None


def income_tuple(player: Any, context: dict[str, Any]) -> tuple[int, int]:
    statement = preview_turn(player, context)
    return int(statement["final_gold"]), int(statement["final_grain"])


def upkeep_tuple(player: Any, context: dict[str, Any]) -> tuple[int, int]:
    statement = preview_turn(player, context)
    return int(statement["upkeep_gold"]), int(statement["upkeep_grain"])


def price_multiplier(player: Any) -> float:
    state = ensure_economy_state(player)
    return clamp(state["price_level"], 0.35, 12.0)


def set_tax_rate(player: Any, rate: float) -> float:
    state = ensure_economy_state(player)
    state["tax_rate"] = clamp(finite(rate), 0.0, 0.65)
    return state["tax_rate"]


def set_tariff_rate(player: Any, rate: float) -> float:
    state = ensure_economy_state(player)
    state["tariff_rate"] = clamp(finite(rate), 0.0, 0.45)
    return state["tariff_rate"]


def set_fiscal_stance(player: Any, stance: str) -> str:
    state = ensure_economy_state(player)
    if stance not in FISCAL_STANCES:
        raise ValueError(f"Неизвестная бюджетная позиция: {stance}")
    state["fiscal_stance"] = stance
    return stance


def set_coin_standard(player: Any, standard: str) -> str:
    state = ensure_economy_state(player)
    if standard not in COIN_STANDARDS:
        raise ValueError(f"Неизвестный монетный стандарт: {standard}")
    state["coin_standard"] = standard
    return standard


def set_budget_shares(player: Any, shares: dict[str, float]) -> dict[str, float]:
    state = ensure_economy_state(player)
    state["budget_shares"] = normalize_budget_shares(shares)
    return dict(state["budget_shares"])


def set_sector_policy(player: Any, policy: str) -> str:
    state = ensure_economy_state(player)
    if policy not in SECTOR_POLICIES:
        raise ValueError(f"Неизвестная отраслевая политика: {policy}")
    state["sector_policy"] = policy
    return policy


def set_credit_policy(player: Any, policy: str) -> str:
    state = ensure_economy_state(player)
    if policy not in CREDIT_POLICIES:
        raise ValueError(f"Неизвестная кредитная политика: {policy}")
    state["financial"]["policy"] = policy
    return policy


def set_usury_cap(player: Any, rate: float) -> float:
    state = ensure_economy_state(player)
    state["financial"]["usury_cap"] = clamp(finite(rate), 0.03, 0.50)
    return state["financial"]["usury_cap"]


def set_strategic_grain_target(player: Any, turns: float) -> float:
    state = ensure_economy_state(player)
    state["strategic_grain_target"] = clamp(finite(turns), 0.0, 20.0)
    return state["strategic_grain_target"]


def issue_bonds(player: Any, amount: float) -> int:
    state = ensure_economy_state(player)
    amount = max(0, money(amount))
    if amount <= 0:
        return 0
    state["debt"] += amount
    player.gold = max(0, int(getattr(player, "gold", 0))) + amount
    state["confidence"] = clamp(
        state["confidence"] - min(0.08, amount / max(1.0, state["money_supply"] + state["debt"]) * 0.15),
        0.01,
        0.995,
    )
    _ledger_post(state, int(getattr(player, "turn", 1)), "Казна", "Обязательства: государственный долг", amount, "Размещение облигаций")
    return amount


def repay_debt(player: Any, amount: float) -> int:
    state = ensure_economy_state(player)
    amount = min(max(0, money(amount)), money(state["debt"]), max(0, int(getattr(player, "gold", 0))))
    if amount <= 0:
        return 0
    state["debt"] -= amount
    player.gold -= amount
    _ledger_post(state, int(getattr(player, "turn", 1)), "Обязательства: государственный долг", "Казна", amount, "Внеочередное погашение долга")
    return amount


def mint_currency(player: Any, amount: float) -> int:
    state = ensure_economy_state(player)
    amount = max(0, money(amount))
    if amount <= 0:
        return 0
    player.gold = max(0, int(getattr(player, "gold", 0))) + amount
    state["money_supply"] += amount
    state["confidence"] = clamp(state["confidence"] - min(0.18, amount / max(1.0, state["money_supply"]) * 0.75), 0.01, 0.995)
    _ledger_post(state, int(getattr(player, "turn", 1)), "Казна", "Доходы: сеньораж", amount, "Чеканка монеты")
    return amount


def direct_investment(player: Any, target: str, amount: float) -> int:
    state = ensure_economy_state(player)
    amount = min(max(0, money(amount)), max(0, int(getattr(player, "gold", 0))))
    if amount <= 0:
        return 0
    player.gold -= amount
    real_amount = amount / max(0.10, state["price_level"])
    if target == "infrastructure":
        state["infrastructure"] += 2.4 * math.log1p(real_amount) / (1.0 + state["infrastructure"] / 100.0)
        state["sectoral_capital"]["construction"] += 1.8 * math.log1p(real_amount)
        state["sectoral_capital"]["commerce"] += 0.8 * math.log1p(real_amount)
    elif target == "administration":
        state["tax_capacity"] = clamp(state["tax_capacity"] + 0.010 * math.log1p(real_amount), 0.03, 0.99)
        state["corruption"] = clamp(state["corruption"] - 0.006 * math.log1p(real_amount), 0.005, 0.95)
    elif target == "human_capital":
        state["human_capital"] += 1.7 * math.log1p(real_amount) / (1.0 + state["human_capital"] / 100.0)
        state["innovation"]["research_stock"] += 1.4 * math.sqrt(real_amount)
        if hasattr(player, "science_points"):
            player.science_points += money(real_amount * 0.25)
    elif target == "welfare":
        if hasattr(player, "unrest"):
            player.unrest = int(clamp(finite(getattr(player, "unrest", 0)) - min(10.0, math.log1p(real_amount) * 1.2), 0.0, 100.0))
        if hasattr(player, "people_rep"):
            player.people_rep = int(clamp(finite(getattr(player, "people_rep", 50)) + min(6.0, math.log1p(real_amount) * 0.65), 0.0, 100.0))
    elif target in SECTOR_KEYS:
        state["sectoral_capital"][target] += 2.1 * math.log1p(real_amount) / (1.0 + state["sectoral_capital"][target] / 500.0)
        state["capital_stock"] = sum(state["sectoral_capital"].values())
    elif target == "banking":
        state["financial"]["banking_health"] = clamp(state["financial"]["banking_health"] + 0.018 * math.log1p(real_amount), 0.01, 0.99)
        state["financial"]["deposit_base"] += real_amount * 0.35
    else:
        raise ValueError(f"Неизвестное направление инвестиций: {target}")
    _ledger_post(state, int(getattr(player, "turn", 1)), f"Капитальные вложения: {target}", "Казна", amount, "Прямое казённое вложение")
    return amount



def _conquest_record(state: dict[str, Any], row: dict[str, Any]) -> None:
    conquest = state.setdefault("conquest", {})
    history = conquest.setdefault("history", [])
    if not isinstance(history, list):
        history = []
        conquest["history"] = history
    history.append(row)
    del history[:-240]


def register_conquest_windfall(
    player: Any,
    *,
    gold: float,
    grain: float = 0.0,
    slaves: float = 0.0,
    province: str = "",
    city: str = "",
    capital_gain: float = 0.0,
    sector: str = "commerce",
    source: str = "assault",
) -> dict[str, Any]:
    """Регистрирует городские трофеи как внешний трансферт, а не как ВВП."""
    state = ensure_economy_state(player)
    gold_i = max(0, money(gold))
    grain_i = max(0, money(grain))
    slaves_f = max(0.0, finite(slaves))
    capital_f = max(0.0, finite(capital_gain))
    sector = sector if sector in SECTOR_KEYS else "commerce"

    player.gold = max(0, int(getattr(player, "gold", 0))) + gold_i
    player.grain = max(0, int(getattr(player, "grain", 0))) + grain_i
    state["money_supply"] += gold_i * 0.62
    state["sectoral_capital"][sector] += capital_f
    state["capital_stock"] = sum(state["sectoral_capital"].values())
    demo = state["demographics"]
    demo["slave_population"] += slaves_f
    demo["captives_last_turn"] = slaves_f
    state["population"] = demo["free_population"] + demo["slave_population"]
    demo["slave_ratio"] = clamp(demo["slave_population"] / max(1.0, state["population"]), 0.0, 0.85)
    state["inequality"] = clamp(state["inequality"] + min(0.015, slaves_f / max(1.0, state["population"]) * 0.20), 0.05, 0.95)
    state["confidence"] = clamp(state["confidence"] + min(0.012, gold_i / max(1.0, state["money_supply"]) * 0.08), 0.01, 0.995)

    conquest = state["conquest"]
    if source == "annexation":
        conquest["province_indemnities"] += gold_i
    else:
        conquest["city_spoils"] += gold_i
    conquest["grain_requisitions"] += grain_i
    conquest["captives"] += slaves_f
    conquest["capital_transfers"] += capital_f
    turn = int(getattr(player, "turn", 1))
    revenue_account = "Военные трофеи: провинциальная контрибуция" if source == "annexation" else "Военные трофеи: города"
    _ledger_post(state, turn, "Казна", revenue_account, gold_i, f"Трофеи {city}, {province}")
    if grain_i:
        _ledger_post(state, turn, "Запасы зерна", "Военные реквизиции", grain_i, f"Реквизиция {city}, {province}")
    if capital_f:
        _ledger_post(state, turn, f"Капитал: {SECTOR_LABELS[sector]}", "Капитальные трансферты завоеваний", capital_f, f"Захваченные активы {city}")
    if source != "annexation":
        _conquest_record(state, {"turn": turn, "kind": "city", "province": str(province), "city": str(city), "gold": gold_i, "grain": grain_i, "slaves": round(slaves_f, 3), "capital": round(capital_f, 3), "sector": sector, "source": source})
    return {"gold": gold_i, "grain": grain_i, "slaves": slaves_f, "capital": capital_f, "sector": sector}


def register_province_annexation(
    player: Any,
    context: dict[str, Any],
    *,
    province: str,
    gold: float,
    grain: float = 0.0,
    slaves: float = 0.0,
    local_population: float = 0.0,
    capital_transfer: float = 0.0,
    sector: str = "construction",
    policy: str = "integration",
) -> dict[str, Any]:
    """Включает новую провинцию в демографию, капитал и счета Республики."""
    state = ensure_economy_state(player, context)
    sector = sector if sector in SECTOR_KEYS else "construction"
    result = register_conquest_windfall(
        player,
        gold=gold,
        grain=grain,
        slaves=slaves,
        province=province,
        city="provincia tota",
        capital_gain=capital_transfer,
        sector=sector,
        source="annexation",
    )
    demo = state["demographics"]
    local_pop = max(0.0, finite(local_population))
    # Население городских roster хранится в тысячах; большая его часть становится
    # свободными провинциалами, а пленные уже учтены отдельно.
    incorporated_free = local_pop * 0.72
    incorporated_urban = local_pop * (0.42 if sector in {"commerce", "manufacturing"} else 0.28)
    demo["free_population"] += incorporated_free
    demo["urban_population"] += incorporated_urban
    demo["rural_population"] += max(0.0, incorporated_free + max(0.0, finite(slaves)) - incorporated_urban)
    state["population"] = demo["free_population"] + demo["slave_population"]
    demo["slave_ratio"] = clamp(demo["slave_population"] / max(1.0, state["population"]), 0.0, 0.85)
    demo["urbanization_rate"] = clamp(demo["urban_population"] / max(1.0, state["population"]), 0.05, 0.92)
    demo["last_province_count"] = float(max(1, int(context.get("province_count", 1))))
    state["carrying_capacity"] += local_pop * 0.95
    turn = int(getattr(player, "turn", 1))
    _ledger_post(state, turn, "Активы: провинциальная налоговая база", "Капитальные трансферты завоеваний", max(0.0, local_pop), f"Аннексия {province}")
    _conquest_record(state, {"turn": turn, "kind": "province", "province": str(province), "gold": max(0, money(gold)), "grain": max(0, money(grain)), "slaves": round(max(0.0, finite(slaves)), 3), "population": round(local_pop, 3), "capital": round(max(0.0, finite(capital_transfer)), 3), "sector": sector, "policy": str(policy)})
    return result


def conquest_report(player: Any) -> dict[str, Any]:
    state = ensure_economy_state(player)
    return copy.deepcopy(state.get("conquest", {}))


def grain_buy_price(player: Any) -> int:
    state = ensure_economy_state(player)
    return max(1, money(12.0 * state["grain_price"] * state["price_level"]))


def grain_sell_price(player: Any) -> int:
    return max(1, money(grain_buy_price(player) * 0.72))


def apply_cash_transaction(
    player: Any,
    amount: int | float,
    label: str,
    context: dict[str, Any] | None = None,
    *,
    category: str = "external",
) -> dict[str, Any]:
    """Единственная публичная дверь для внеходовых изменений казны.

    Ресурсный модуль возвращает только ``gold_delta``; фактическую проводку,
    проверку достаточности средств и запись в бухгалтерскую книгу выполняет
    Roma Economica. Пассивный показатель ``gold_per_turn`` эта операция не
    меняет, поскольку покупка/продажа является разовой транзакцией.
    """
    state = ensure_economy_state(player, context or {})
    delta = money(amount)
    before = max(0, int(getattr(player, "gold", 0)))
    if delta < 0 and before < abs(delta):
        return {
            "ok": False,
            "requested": delta,
            "applied": 0,
            "before": before,
            "after": before,
            "message": f"Недостаточно золота: требуется {abs(delta)}.",
        }
    after = max(0, before + delta)
    setattr(player, "gold", after)
    turn = int(getattr(player, "turn", 1))
    account = f"Разовые операции: {category}"
    if delta >= 0:
        _ledger_post(state, turn, "Казна", account, delta, str(label))
    else:
        _ledger_post(state, turn, account, "Казна", abs(delta), str(label))
    history = state.setdefault("cash_transactions", [])
    history.append({
        "turn": turn,
        "category": str(category),
        "label": str(label),
        "delta": delta,
        "before": before,
        "after": after,
    })
    del history[:-160]
    return {
        "ok": True,
        "requested": delta,
        "applied": delta,
        "before": before,
        "after": after,
        "message": str(label),
    }


def buy_grain(player: Any, units: int = 50) -> tuple[int, int]:
    units = max(1, int(units))
    lots = max(1, math.ceil(units / 50))
    cost = grain_buy_price(player) * lots
    if int(getattr(player, "gold", 0)) < cost:
        return 0, cost
    player.gold -= cost
    player.grain = max(0, int(getattr(player, "grain", 0))) + 50 * lots
    state = ensure_economy_state(player)
    state["grain_price"] = clamp(state["grain_price"] * (1.0 + 0.012 * lots), 0.10, 100.0)
    _ledger_post(state, int(getattr(player, "turn", 1)), "Запасы зерна", "Казна", cost, "Закупка зерна")
    return 50 * lots, cost


def sell_grain(player: Any, units: int = 50) -> tuple[int, int]:
    units = max(1, int(units))
    lots = max(1, math.ceil(units / 50))
    amount = 50 * lots
    if int(getattr(player, "grain", 0)) < amount:
        return 0, 0
    revenue = grain_sell_price(player) * lots
    player.grain -= amount
    player.gold = max(0, int(getattr(player, "gold", 0))) + revenue
    state = ensure_economy_state(player)
    state["grain_price"] = clamp(state["grain_price"] * max(0.85, 1.0 - 0.010 * lots), 0.10, 100.0)
    _ledger_post(state, int(getattr(player, "turn", 1)), "Казна", "Доходы: продажа зерна", revenue, "Продажа зерна")
    return amount, revenue



def _legacy_economic_glossary(player: Any, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Термины справки с текущим числом и прямым вкладом в золото/ход."""
    statement = preview_turn(player, context)
    macro = statement["macro"]
    revenues = statement["revenues"]
    trade = statement["trade"]
    finance = statement["finance"]
    national = statement["national_accounts"]
    automation = statement.get("automation", {})
    magic = {str(row.get("key")): row for row in statement.get("magic_modifiers", []) if isinstance(row, dict)}

    def mg(key: str) -> float:
        return finite(magic.get(key, {}).get("gold_per_turn", 0.0))

    rows: list[dict[str, Any]] = []
    def add(category: str, term: str, value: Any, gold: float = 0.0) -> None:
        rows.append({"category": category, "term": term, "value": value, "gold_per_turn": round(finite(gold), 2)})

    add("Национальные счета", "ВВП", round(macro.get("nominal_output", 0.0), 2), mg("gdp_dividend"))
    add("Национальные счета", "Валовой выпуск", round(macro.get("real_output", 0.0), 2), 0)
    add("Национальные счета", "Валовая добавленная стоимость", round(national["production"]["gdp"], 2), mg("gdp_dividend"))
    add("Национальные счета", "Частное потребление", round(national["expenditure"]["consumption"], 2), 0)
    add("Национальные счета", "Частные инвестиции", round(national["expenditure"]["private_investment"], 2), 0)
    add("Национальные счета", "Государственные закупки", round(national["expenditure"]["government"], 2), 0)  # отток казны показан в «Фиске»
    add("Фиск", "Aerarium", statement["revenue_total"], statement["overall_balance"])
    add("Фиск", "Fiscus", revenues.get("domains", 0), revenues.get("domains", 0))
    add("Фиск", "Tributum", f"{ensure_economy_state(player).get('tax_rate', 0):.1%}", revenues.get("direct_tax", 0))
    add("Фиск", "Portorium", f"{ensure_economy_state(player).get('tariff_rate', 0):.1%}", revenues.get("customs", 0))
    add("Фиск", "Vectigalia", revenues.get("customs", 0) + revenues.get("domains", 0), revenues.get("customs", 0) + revenues.get("domains", 0))
    add("Фиск", "Налоговая база", round(macro.get("nominal_output", 0), 2), revenues.get("direct_tax", 0))
    add("Фиск", "Кривая Лаффера", f"{revenues.get('laffer_effective_rate', 0):.2%}", revenues.get("direct_tax", 0))
    add("Фиск", "Собираемость налогов", f"{revenues.get('compliance', 0):.2%}", revenues.get("direct_tax", 0))
    add("Фиск", "Первичный баланс", statement["primary_balance"], statement["primary_balance"])
    add("Фиск", "Структурный баланс", statement.get("structural_balance", 0), statement.get("structural_balance", 0))
    add("Фиск", "Сальдо бюджета", statement["overall_balance"], statement["overall_balance"])
    add("Фиск", "Профицит", max(0, statement["overall_balance"]), max(0, statement["overall_balance"]))
    add("Фиск", "Дефицит", max(0, -statement.get("structural_balance", 0)), min(0, statement.get("structural_balance", 0)))
    add("Фиск", "Автоматический стабилизатор", automation.get("stabilizer_income", 0), automation.get("stabilizer_income", 0))
    add("Деньги", "Денежная масса", round(macro.get("money_supply", 0), 2), mg("monetization"))
    add("Деньги", "Скорость обращения денег", round(macro.get("velocity", 0), 3), mg("money_velocity"))
    add("Деньги", "Инфляция", f"{macro.get('inflation', 0):.2%}", 0)
    add("Деньги", "Дефлятор ВВП", round(macro.get("price_level", 1), 3), 0)
    add("Деньги", "Покупательная способность", round(1 / max(0.01, macro.get("price_level", 1)), 3), 0)
    add("Деньги", "Сеньораж", round(ensure_economy_state(player).get("pending_minting", 0), 2), 0)
    add("Кредит", "Государственный долг", round(macro.get("debt", 0), 2), -statement["expenditures"].get("interest", 0))
    add("Кредит", "Долговая нагрузка", f"{macro.get('debt_ratio', 0):.2%}", -statement["expenditures"].get("interest", 0))
    add("Кредит", "Процентная ставка", f"{macro.get('interest_rate', 0):.2%}", -statement["expenditures"].get("interest", 0))
    add("Кредит", "Банковское здоровье", f"{macro.get('banking_health', 0):.2%}", mg("banking_health"))
    add("Кредит", "Ликвидность", round(finance.get("deposit_base", ensure_economy_state(player).get("financial", {}).get("deposit_base", 0)), 2), mg("liquidity"))
    add("Кредит", "Кредитный мультипликатор", round(finite(macro.get("private_credit", 0)) / max(1.0, finite(finance.get("deposit_base", ensure_economy_state(player).get("financial", {}).get("deposit_base", 1.0)), 1.0)), 3), mg("credit_multiplier"))
    add("Кредит", "Leverage", round(ensure_economy_state(player).get("financial", {}).get("leverage", 0), 3), 0)
    add("Торговля", "Торговый оборот", round(revenues.get("trade_volume", 0), 2), revenues.get("commerce", 0) + revenues.get("customs", 0))
    add("Торговля", "Маржа", round(magic.get("trade_margin", {}).get("value", 0), 3), mg("trade_margin"))
    add("Торговля", "Экспорт", round(trade.get("export_value", 0), 2), max(0, mg("trade_balance")))
    add("Торговля", "Импорт", round(trade.get("import_value", 0), 2), min(0, mg("trade_balance")))
    add("Торговля", "Сальдо торгового баланса", round(trade.get("trade_balance", 0), 2), mg("trade_balance"))
    add("Торговля", "Сальдо текущего счёта", round(trade.get("current_account", 0), 2), 0)
    add("Торговля", "Условия торговли", round(trade.get("terms_of_trade", 1), 3), mg("terms_of_trade"))
    add("Торговля", "Валютный курс", round(trade.get("exchange_rate", 1), 3), 0)
    add("Торговля", "Импортозависимость", f"{trade.get('import_dependency', 0):.2%}", 0)
    add("Производство", "Основной капитал", round(macro.get("capital_stock", 0), 2), mg("capital_turnover"))
    add("Производство", "Амортизация", round(sum(ensure_economy_state(player).get("sectoral_depreciation", {}).values()), 3), 0)
    add("Производство", "Производительность труда", round(macro.get("labor_productivity", 0), 3), 0)
    add("Производство", "Человеческий капитал", round(macro.get("human_capital", 0), 2), mg("human_capital"))
    add("Производство", "Инфраструктурная рента", round(macro.get("infrastructure", 0), 2), mg("infrastructure_rent"))
    add("Население", "Урбанизация", f"{macro.get('urbanization', 0):.2%}", mg("agglomeration"))
    add("Население", "Безработица", f"{macro.get('unemployment', 0):.2%}", 0)
    add("Население", "Рабская доля", f"{macro.get('slave_ratio', 0):.2%}", 0)
    add("Институты", "Коррупция", f"{macro.get('corruption', 0):.2%}", 0)
    add("Институты", "Доверие", f"{macro.get('confidence', 0):.2%}", mg("confidence_premium"))
    add("Институты", "Неравенство", f"{macro.get('inequality', 0):.2%}", 0)
    add("Римская экономика", "Annona", round(statement["expenditures"].get("grain_subsidy", 0), 2), -statement["expenditures"].get("grain_subsidy", 0))
    add("Римская экономика", "Publicani", f"{revenues.get('compliance', 0):.2%}", revenues.get("direct_tax", 0))
    add("Римская экономика", "Cursus Publicus", round(macro.get("infrastructure", 0), 2), mg("infrastructure_rent"))
    add("Римская экономика", "Romanitas fiscalis", magic.get("romanization", {}).get("value", 0), mg("romanization"))
    return rows


def economic_glossary(player: Any, context: dict[str, Any]) -> list[dict[str, Any]]:
    """Complete accounting lexicon plus every active microformula."""
    statement = preview_turn(player, context)
    state = ensure_economy_state(player, context)
    magic_rows = [row for row in statement.get("magic_modifiers", []) if isinstance(row, dict)]
    if ECONOMY_DICTIONARY is not None:
        try:
            return ECONOMY_DICTIONARY.build_glossary(statement, state, magic_rows)
        except (AttributeError, KeyError, TypeError, ValueError, ArithmeticError):
            pass
    return _legacy_economic_glossary(player, context)


def glossary_audit(player: Any, context: dict[str, Any]) -> list[str]:
    rows = economic_glossary(player, context)
    if ECONOMY_DICTIONARY is None:
        return ["economy_dictionary.py не импортирован"]
    try:
        return list(ECONOMY_DICTIONARY.audit_glossary(rows))
    except (AttributeError, TypeError, ValueError) as exc:
        return [f"Ошибка проверки справочника: {type(exc).__name__}: {exc}"]


def sector_report(player: Any, context: dict[str, Any]) -> list[dict[str, Any]]:
    statement = preview_turn(player, context)
    rows: list[dict[str, Any]] = []
    for key in SECTOR_KEYS:
        rows.append({
            "key": key,
            "label": SECTOR_LABELS[key],
            "output": statement["sectors"]["output"][key],
            "capital": statement["sectors"]["capital"][key],
            "labor": statement["sectors"]["labor"][key],
            "labor_share": statement["sectors"]["labor_shares"][key],
            "profitability": statement["sectors"]["profitability"][key],
            "bottleneck": statement["sectors"]["bottlenecks"][key],
            "technology": ensure_economy_state(player, context)["innovation"]["sector_technology"][key],
        })
    return rows


def economic_shock_log(player: Any) -> list[dict[str, Any]]:
    state = ensure_economy_state(player)
    return [dict(item) for item in state.get("shock_history", []) if isinstance(item, dict)]


def audit_invariants(player: Any, context: dict[str, Any] | None = None) -> list[str]:
    context = context or {}
    state = ensure_economy_state(player, context)
    errors: list[str] = []

    for key in ("population", "capital_stock", "money_supply", "price_level", "grain_price", "carrying_capacity"):
        value = finite(state.get(key), float("nan"))
        if not math.isfinite(value) or value <= 0:
            errors.append(f"{key}: недопустимое значение {state.get(key)!r}")
    if not 0 <= state["tax_rate"] <= 0.65:
        errors.append("налоговая ставка вне диапазона")
    if not 0 <= state["tariff_rate"] <= 0.45:
        errors.append("тарифная ставка вне диапазона")
    if abs(sum(normalize_budget_shares(state["budget_shares"]).values()) - 1.0) > 1e-9:
        errors.append("доли бюджета не суммируются в 100%")
    if abs(sum(normalize_sector_shares(state["sectoral_labor_share"], DEFAULT_SECTOR_LABOR_SHARES).values()) - 1.0) > 1e-9:
        errors.append("доли труда по секторам не суммируются в 100%")
    if abs(state["population"] - (state["demographics"]["free_population"] + state["demographics"]["slave_population"])) > max(0.01, state["population"] * 1e-6):
        errors.append("население не равно сумме свободных и рабов")
    if abs(state["population"] - (state["demographics"]["urban_population"] + state["demographics"]["rural_population"])) > max(0.01, state["population"] * 1e-6):
        errors.append("население не равно сумме городских и сельских жителей")
    if any(finite(state["sectoral_capital"].get(key, 0)) <= 0 for key in SECTOR_KEYS):
        errors.append("один из секторов имеет неположительный капитал")
    if state["financial"]["banking_health"] <= 0 or state["financial"]["banking_health"] > 1:
        errors.append("banking_health вне диапазона (0, 1]")
    if state["trade"]["import_dependency"] < 0:
        errors.append("импортная зависимость отрицательна")
    conquest = state.get("conquest", {})
    if any(finite(conquest.get(key, 0.0)) < 0 for key in ("city_spoils", "province_indemnities", "grain_requisitions", "captives", "capital_transfers")):
        errors.append("счета завоеваний содержат отрицательные накопления")
    tb = trial_balance(player)
    if not tb["balanced"]:
        errors.append("двойная запись не сбалансирована")

    try:
        statement = preview_turn(player, context)
        production_gdp = statement["national_accounts"]["production"]["gdp"]
        expenditure = statement["national_accounts"]["expenditure"]
        exp_gdp = (
            expenditure["consumption"]
            + expenditure["investment"]
            + expenditure["government"]
            + expenditure["net_exports"]
            + expenditure["statistical_discrepancy"]
        )
        if abs(production_gdp - exp_gdp) > max(0.01, abs(production_gdp) * 1e-7):
            errors.append("тождество ВВП C+I+G+NX не выполняется")
        if abs(sum(statement["sectors"]["output"].values()) - statement["macro"]["real_output"]) > max(0.05, statement["macro"]["real_output"] * 1e-5):
            errors.append("сумма отраслевого выпуска не равна реальному ВВП")
        flow = statement["flow_of_funds"]
        if not all(math.isfinite(finite(flow.get(key))) for key in flow):
            errors.append("flow-of-funds содержит нечисловые значения")

        magic_rows = [row for row in statement.get("magic_modifiers", []) if isinstance(row, dict)]
        if len(magic_rows) != microformula_count():
            errors.append(
                f"число активных микроформул {len(magic_rows)} не равно библиотеке {microformula_count()}"
            )
        magic_total = sum(finite(row.get("gold_per_turn", 0.0)) for row in magic_rows)
        precise_total = finite(statement.get("micro_income_realized", magic_total))
        if abs(magic_total - precise_total) > 0.002:
            errors.append("видимые микроформулы не сходятся с точным микродоходом")
        summary = statement.get("microformula_summary", {})
        if isinstance(summary, dict):
            if int(finite(summary.get("count", -1))) != len(magic_rows):
                errors.append("сводка микроформул содержит неверное число строк")
            if abs(finite(summary.get("net", 0.0)) - magic_total) > 0.002:
                errors.append("сводка микроформул не сходится с суммой строк")
            if int(finite(summary.get("zero_rows", 0))) != 0:
                errors.append("часть микроформул округлилась до нулевого вклада")
        if any(not math.isfinite(finite(row.get("gold_per_turn"), float("nan"))) for row in magic_rows):
            errors.append("микроформулы содержат NaN или бесконечность")

        if statement["overall_balance"] != statement["revenue_total"] - statement["expense_total"]:
            errors.append("итоговый баланс не равен доходам минус расходы")
        stabilizer = finite(statement.get("revenues", {}).get("automatic_stabilizer", 0.0))
        expected_structural = statement["revenue_total"] - stabilizer - statement["expense_total"]
        if abs(statement["structural_balance"] - expected_structural) > 1.0:
            errors.append("структурный баланс не согласован со стабилизатором")

        roman = statement.get("roman_accounts", {})
        if not isinstance(roman, dict):
            errors.append("римские счета отсутствуют")
        else:
            if abs(
                finite(roman.get("tributum", 0.0))
                - finite(roman.get("tributum_soli", 0.0))
                - finite(roman.get("tributum_capitis", 0.0))
            ) > 0.002:
                errors.append("Tributum не равен сумме tributum soli и tributum capitis")
            if abs(
                finite(statement.get("revenues", {}).get("domains", 0.0))
                - finite(roman.get("ager_publicus", 0.0))
                - finite(roman.get("patrimonium_caesaris", 0.0))
            ) > 1.1:
                errors.append("доходы доменов не разделены между ager publicus и patrimonium")
            if abs(
                finite(statement.get("expenditures", {}).get("military_upkeep", 0.0))
                - finite(roman.get("stipendium", 0.0))
                - finite(roman.get("castra_logistics", 0.0))
            ) > 1.1:
                errors.append("военное содержание не разделено между stipendium и логистикой")
            if str(roman.get("accounting_note", "")) != "decomposition_only_no_double_counting":
                errors.append("римские счета не помечены как декомпозиция без двойного счёта")
    except Exception as exc:
        errors.append(f"построение национальных счетов упало: {type(exc).__name__}: {exc}")
    return errors
