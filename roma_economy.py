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

ECONOMY_VERSION = 4


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
    real_output = max(20.0, sectors["total_output"])
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
    base_revenue = max(0.0, finite(context.get("base_revenue", 10.0))) * nominal_scale
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
    military_technology = clamp(finite(state["innovation"].get("military_technology", 1.0)), 0.5, 10.0)
    price = state["price_level"]

    military = legion_count * (8.0 + 2.0 * quality_index) * price / (military_technology ** 0.12)
    military += over_limit * (10.0 + 5.0 * over_limit) * price
    fleet = max(0.0, finite(context.get("fleet_upkeep", 0.0))) * price
    administration = (4.0 + 2.8 * (province_count ** 1.18)) * price
    administration *= 1.0 + 0.35 * state["corruption"]
    tribute_paid = max(0.0, finite(context.get("tribute_paid", 0.0)))

    sovereign_rate = finance["sovereign_rate"]
    interest = state["debt"] * sovereign_rate
    revenue_total = sum(revenues[key] for key in ("direct_tax", "customs", "domains", "tribute", "commerce", "base_revenue"))
    treasury_cash = max(0.0, finite(context.get("treasury_cash", 0.0)))
    reserve_target = max(180.0, revenue_total * 4.0)
    excess_cash = max(0.0, treasury_cash - reserve_target)
    treasury_management = min(revenue_total * 0.20, excess_cash * 0.003)
    stance = FISCAL_STANCES[state["fiscal_stance"]]
    investment_envelope = max(0.0, revenue_total * 0.34 * stance["investment_ratio"])
    shares = normalize_budget_shares(state["budget_shares"])
    programmes = {key: investment_envelope * shares[key] for key in BUDGET_KEYS}

    grain_subsidy = 0.0
    if state.get("grain_subsidy", True) and grain["price"] > 1.35:
        grain_subsidy = min(revenue_total * 0.18, (grain["price"] - 1.0) * macro["population"] * 0.025)
        programmes["welfare"] += grain_subsidy

    strategic_reserve = min(revenue_total * 0.25, max(0.0, grain["reserve_procurement_cost"]))
    mandatory = administration + military + fleet + tribute_paid + interest + treasury_management + strategic_reserve
    programme_total = sum(programmes.values())
    total = mandatory + programme_total
    return {
        "administration": administration,
        "military_upkeep": military,
        "fleet_upkeep": fleet,
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
    government_purchases = (
        expenditures["administration"]
        + expenditures["military_upkeep"]
        + expenditures["fleet_upkeep"]
        + expenditures["programme_total"]
        + expenditures["strategic_reserve"]
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


def build_statement(player: Any, context: dict[str, Any], mutate: bool = False) -> dict[str, Any]:
    state = ensure_economy_state(player, context)
    sectors = _sectoral_snapshot(player, context, state)
    macro = _macro_snapshot(player, context, state, sectors)
    finance = _financial_market(player, context, state, macro, sectors)
    trade = _external_trade(player, context, state, macro, sectors)
    revenues = _tax_revenue(context, state, macro, trade)
    grain = _grain_market(player, context, state, macro, trade)
    expenditures = _expenditures(context, state, macro, revenues, grain, finance)
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

    revenue_total = sum(revenues[key] for key in ("direct_tax", "customs", "domains", "tribute", "commerce", "base_revenue"))
    primary_balance = revenue_total - (expenditures["total"] - expenditures["interest"])
    overall_balance = revenue_total - expenditures["total"]
    debt_ratio = state["debt"] / max(1.0, macro["nominal_output"])
    national_accounts = _national_accounts(state, macro, sectors, trade, finance, expenditures)
    flow_of_funds = _flow_of_funds(state, macro, trade, finance, revenue_total, expenditures)
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

    rows = [
        {"key": "direct_tax", "label": "Прямые налоги", "amount": money(revenues["direct_tax"]), "note": f"ставка {state['tax_rate']:.0%}; эффективная {revenues['laffer_effective_rate']:.1%}"},
        {"key": "customs", "label": "Пошлины и портовые сборы", "amount": money(revenues["customs"]), "note": f"тариф {state['tariff_rate']:.0%}"},
        {"key": "domains", "label": "Доходы государственных владений", "amount": money(revenues["domains"]), "note": "рудники, города, земля и монополии"},
        {"key": "tribute", "label": "Дань и союзные платежи", "amount": money(revenues["tribute"]), "note": "внешние поступления"},
        {"key": "commerce", "label": "Торговля и морские пути", "amount": money(revenues["commerce"]), "note": "рынки, караваны, ресурсы"},
        {"key": "base_revenue", "label": "Доход столицы и казённых служб", "amount": money(revenues["base_revenue"]), "note": "устойчивая налоговая база"},
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
        "turn": int(getattr(player, "turn", 1)),
        "rows": rows,
        "raw_gold": money(revenue_total),
        "difficulty_mult": finite(context.get("income_mult", 1.0), 1.0),
        "after_difficulty": money(revenue_total),
        "tech_percent": finite(context.get("tech_productivity", 0.0)),
        "percent_mult": 1.0 + finite(context.get("tech_productivity", 0.0)),
        "final_gold": money(revenue_total),
        "final_grain": money(grain["total_supply"]),
        "grain_consumption": money(grain["consumption"]),
        "revenues": {
            key: money(value) if key not in ("laffer_effective_rate", "compliance", "trade_volume") else value
            for key, value in revenues.items()
        },
        "expenditures": {
            "administration": money(expenditures["administration"]),
            "military_upkeep": money(expenditures["military_upkeep"]),
            "fleet_upkeep": money(expenditures["fleet_upkeep"]),
            "tribute_paid": money(expenditures["tribute_paid"]),
            "interest": money(expenditures["interest"]),
            "treasury_management": money(expenditures["treasury_management"]),
            "strategic_reserve": money(expenditures["strategic_reserve"]),
            "programmes": {key: money(value) for key, value in expenditures["programmes"].items()},
            "grain_subsidy": money(expenditures["grain_subsidy"]),
            "mandatory_total": money(expenditures["mandatory_total"]),
            "programme_total": money(expenditures["programme_total"]),
            "total": money(expenditures["total"]),
        },
        "macro": macro_payload,
        "sectors": {
            "output": {key: round(value, 4) for key, value in sectors["output"].items()},
            "capital": {key: round(value, 4) for key, value in sectors["capital"].items()},
            "labor": {key: round(value, 4) for key, value in sectors["labor"].items()},
            "labor_shares": {key: round(value, 6) for key, value in sectors["labor_shares"].items()},
            "capital_shares": {key: round(value, 6) for key, value in sectors["capital_shares"].items()},
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
        "national_accounts": national_accounts,
        "flow_of_funds": flow_of_funds,
        "sectoral_balances": {key: round(value, 4) for key, value in sectoral_balances.items()},
        "revenue_total": money(revenue_total),
        "expense_total": money(expenditures["total"]),
        "primary_balance": money(primary_balance),
        "overall_balance": money(overall_balance),
        "upkeep_gold": money(expenditures["total"]),
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
        "base_revenue": "Доходы: столица",
    }
    for key, account in revenue_accounts.items():
        _ledger_post(state, turn, "Казна", account, statement["revenues"].get(key, 0), account)
    expense_accounts = {
        "administration": "Расходы: управление",
        "military_upkeep": "Расходы: армия",
        "fleet_upkeep": "Расходы: флот",
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
    shock_messages = apply_economic_shocks(player, context, state)
    state["unemployment"] = clamp(finite(statement["macro"]["unemployment"]), 0.0, 0.75)

    warning_parts: list[str] = []
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
    except Exception as exc:
        errors.append(f"построение национальных счетов упало: {type(exc).__name__}: {exc}")
    return errors
