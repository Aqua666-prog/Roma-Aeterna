#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Presentation-only economic lexicon for Roma Aeterna.

The lexicon never mutates game state. Fiscal-flow rows describe real money that
has already been counted; indicator rows show an attributed influence; only rows
with ``kind == 'microformula'`` belong to the nano-economic total.
"""

from __future__ import annotations

import math
from typing import Any

LEXICON_VERSION = 2
DISPLAY_PRECISION = 3
VALID_KINDS = {"indicator", "fiscal_flow", "microformula"}


def finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _m(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _pct(value: Any) -> str:
    return f"{finite(value):.2%}"


def _num(value: Any, digits: int = 2) -> float:
    return round(finite(value), digits)


def build_glossary(
    statement: dict[str, Any],
    state: dict[str, Any],
    magic_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    macro = _m(statement.get("macro"))
    revenues = _m(statement.get("revenues"))
    expenditures = _m(statement.get("expenditures"))
    trade = _m(statement.get("trade"))
    finance = _m(statement.get("finance"))
    national = _m(statement.get("national_accounts"))
    production = _m(national.get("production"))
    expenditure_accounts = _m(national.get("expenditure"))
    income_accounts = _m(national.get("income"))
    flow = _m(statement.get("flow_of_funds"))
    grain = _m(statement.get("grain"))
    automation = _m(statement.get("automation"))
    demographics = _m(statement.get("demographics"))
    roman = _m(statement.get("roman_accounts"))
    financial_state = _m(state.get("financial"))

    magic_rows = [row for row in (magic_rows or []) if isinstance(row, dict)]
    driver_gold: dict[str, float] = {}
    driver_value: dict[str, Any] = {}
    for row in magic_rows:
        driver = str(row.get("driver", ""))
        gold = finite(row.get("gold_per_turn", 0.0))
        driver_gold[driver] = driver_gold.get(driver, 0.0) + gold
        driver_value.setdefault(driver, row.get("value", 0.0))

    def impact(driver: str, divisor: float = 1.0) -> float:
        return driver_gold.get(driver, 0.0) / max(1.0, finite(divisor, 1.0))

    rows: list[dict[str, Any]] = []
    row_index: dict[tuple[str, str], int] = {}

    def add(
        category: str,
        term: str,
        value: Any,
        gold: float = 0.0,
        kind: str = "indicator",
        source: str = "",
        note: str = "",
        included: bool = False,
        formula: str = "",
    ) -> None:
        marker = (str(category).strip(), str(term).strip())
        if not marker[0] or not marker[1] or marker in row_index:
            return
        row_index[marker] = len(rows)
        rows.append({
            "category": marker[0],
            "term": marker[1],
            "value": value,
            "gold_per_turn": round(finite(gold), DISPLAY_PRECISION),
            "kind": kind if kind in VALID_KINDS else "indicator",
            "source": str(source),
            "note": str(note),
            "formula": str(formula),
            "included_in_micro_total": bool(included),
        })

    overall = finite(statement.get("overall_balance", 0.0))
    structural = finite(statement.get("structural_balance", overall))
    primary = finite(statement.get("primary_balance", overall))
    revenue_total = finite(statement.get("revenue_total", 0.0))
    expense_total = finite(statement.get("expense_total", 0.0))
    nominal = max(1.0, finite(macro.get("nominal_output", production.get("gdp", 1.0)), 1.0))
    real = finite(macro.get("real_output", nominal))
    population = max(1.0, finite(macro.get("population", 1.0)))

    # National accounts. Their attributed effects explain the economy but are
    # not added again to the treasury.
    add("Национальные счета", "ВВП", _num(nominal), impact("gdp_scale", 3), source="gdp_scale")
    add("Национальные счета", "Реальный ВВП", _num(real), impact("gdp_scale", 3), source="gdp_scale")
    add("Национальные счета", "Номинальный ВВП", _num(nominal), impact("gdp_scale", 3), source="gdp_scale")
    add("Национальные счета", "ВВП на душу населения", _num(real / population, 3), impact("gdp_per_capita"), source="gdp_per_capita")
    add("Национальные счета", "Валовая добавленная стоимость", _num(production.get("gdp", nominal)), impact("value_added"), source="value_added")
    add("Национальные счета", "Частное потребление", _num(expenditure_accounts.get("consumption", 0.0)), impact("gdp_per_capita", 3), source="gdp_per_capita")
    add("Национальные счета", "Частные инвестиции", _num(expenditure_accounts.get("private_investment", 0.0)), impact("capital_turnover"), source="capital_turnover")
    add("Национальные счета", "Государственные инвестиции", _num(expenditure_accounts.get("public_investment", 0.0)), impact("public_works"), source="public_works")
    add("Национальные счета", "Государственные закупки", _num(expenditure_accounts.get("government", 0.0)), impact("public_works", 2), source="public_works")
    add("Национальные счета", "Чистый экспорт", _num(expenditure_accounts.get("net_exports", 0.0)), impact("trade_balance"), source="trade_balance")
    add("Национальные счета", "Оплата труда", _num(income_accounts.get("wages", 0.0)), impact("labor_productivity"), source="labor_productivity")
    add("Национальные счета", "Смешанный доход", _num(income_accounts.get("mixed_income", 0.0)), impact("value_added", 3), source="value_added")
    add("Национальные счета", "Валовая прибыль экономики", _num(income_accounts.get("operating_surplus", 0.0)), impact("trade_margin"), source="trade_margin")
    add("Национальные счета", "Статистическое расхождение", _num(expenditure_accounts.get("statistical_discrepancy", 0.0)), 0.0)

    # Real fiscal flows. These are accounting views, not extra sources of money.
    add("Фиск", "Aerarium", _num(revenue_total), overall, "fiscal_flow", "overall_balance")
    add("Фиск", "Fiscus", _num(roman.get("fiscus", revenues.get("domains", 0.0))), revenues.get("domains", 0.0), "fiscal_flow", "domains")
    add("Фиск", "Доходы государства", _num(revenue_total), revenue_total, "fiscal_flow", "revenue_total")
    add("Фиск", "Расходы государства", _num(expense_total), -expense_total, "fiscal_flow", "expense_total")
    add("Фиск", "Сальдо бюджета", _num(overall), overall, "fiscal_flow", "overall_balance")
    add("Фиск", "Структурный баланс", _num(structural), structural, "fiscal_flow", "structural_balance")
    add("Фиск", "Первичный баланс", _num(primary), primary, "fiscal_flow", "primary_balance")
    add("Фиск", "Профицит", _num(max(0.0, overall)), max(0.0, overall), "fiscal_flow", "overall_balance")
    add("Фиск", "Дефицит", _num(max(0.0, -structural)), min(0.0, structural), "fiscal_flow", "structural_balance")
    add("Фиск", "Фискальный разрыв", _num(max(0.0, -structural)), min(0.0, structural), "fiscal_flow", "structural_balance")
    add("Фиск", "Автоматический стабилизатор", _num(automation.get("stabilizer_income", 0.0)), automation.get("stabilizer_income", 0.0), "fiscal_flow", "automatic_stabilizer")
    add("Фиск", "Tributum", _num(roman.get("tributum", revenues.get("direct_tax", 0.0))), revenues.get("direct_tax", 0.0), "fiscal_flow", "direct_tax")
    add("Фиск", "Portorium", _num(roman.get("portorium", revenues.get("customs", 0.0))), revenues.get("customs", 0.0), "fiscal_flow", "customs")
    add("Фиск", "Vectigalia", _num(roman.get("vectigalia", finite(revenues.get("customs")) + finite(revenues.get("domains")))), roman.get("vectigalia", 0.0), "fiscal_flow", "customs+domains")
    add("Фиск", "Налоговая база", _num(nominal), impact("tax_capacity", 2), source="tax_capacity")
    add("Фиск", "Эффективная налоговая ставка", _pct(revenues.get("laffer_effective_rate", 0.0)), impact("laffer_alignment", 2), source="laffer_alignment")
    add("Фиск", "Линия Лаффера", _pct(revenues.get("laffer_effective_rate", 0.0)), impact("laffer_alignment", 2), source="laffer_alignment")
    add("Фиск", "Собираемость налогов", _pct(revenues.get("compliance", 0.0)), impact("tax_compliance"), source="tax_compliance")
    add("Фиск", "Фискальная ёмкость", _pct(macro.get("tax_capacity", state.get("tax_capacity", 0.0))), impact("tax_capacity", 2), source="tax_capacity")
    add("Фиск", "Налоговая нагрузка", _pct(state.get("tax_rate", 0.0)), impact("laffer_alignment", 3), source="laffer_alignment")
    add("Фиск", "Таможенная нагрузка", _pct(state.get("tariff_rate", 0.0)), impact("trade_openness", 3), source="trade_openness")
    add("Фиск", "Доход государственных владений", _num(revenues.get("domains", 0.0)), revenues.get("domains", 0.0), "fiscal_flow", "domains")
    add("Фиск", "Доход от дани", _num(revenues.get("tribute", 0.0)), revenues.get("tribute", 0.0), "fiscal_flow", "tribute")
    add("Фиск", "Казначейский доход", _num(revenues.get("base_revenue", 0.0)), revenues.get("base_revenue", 0.0), "fiscal_flow", "base_revenue")
    add("Фиск", "Доход доктрины", _num(revenues.get("doctrine_income", 0.0)), revenues.get("doctrine_income", 0.0), "fiscal_flow", "doctrine_income")
    add("Фиск", "Наноэкономический доход", _num(revenues.get("micro_income", 0.0)), revenues.get("micro_income", 0.0), "fiscal_flow", "micro_income")

    # Money and credit.
    add("Деньги", "Денежная масса", _num(macro.get("money_supply", state.get("money_supply", 0.0))), impact("monetization", 2), source="monetization")
    add("Деньги", "Скорость обращения денег", _num(macro.get("velocity", state.get("velocity", 0.0)), 3), impact("money_velocity"), source="money_velocity")
    add("Деньги", "Монетизация", _num(finite(macro.get("money_supply", state.get("money_supply", 0.0))) / nominal, 3), impact("monetization", 2), source="monetization")
    add("Деньги", "Инфляция", _pct(macro.get("inflation", state.get("inflation", 0.0))), impact("price_stability", 4), source="price_stability")
    add("Деньги", "Ожидаемая инфляция", _pct(state.get("expected_inflation", 0.0)), impact("price_stability", 4), source="price_stability")
    add("Деньги", "Дефлятор ВВП", _num(macro.get("price_level", state.get("price_level", 1.0)), 3), impact("price_stability", 4), source="price_stability")
    add("Деньги", "Покупательная способность", _num(1.0 / max(0.01, finite(macro.get("price_level", state.get("price_level", 1.0)), 1.0)), 3), impact("price_stability", 4), source="price_stability")
    add("Деньги", "Сеньораж", _num(state.get("pending_minting", 0.0)), state.get("pending_minting", 0.0), "fiscal_flow", "pending_minting")
    add("Деньги", "Порча монеты", str(state.get("coin_standard", "managed")), impact("coin_quality", 2), source="coin_quality")
    add("Деньги", "Проба монеты", str(state.get("coin_standard", "managed")), impact("coin_quality", 2), source="coin_quality")
    add("Деньги", "Валютный курс", _num(trade.get("exchange_rate", 1.0), 3), impact("exchange_stability", 2), source="exchange_stability")
    add("Деньги", "Паритет покупательной способности", _num(1.0 / max(0.01, finite(trade.get("exchange_rate", 1.0), 1.0)), 3), impact("exchange_stability", 2), source="exchange_stability")

    add("Кредит", "Государственный долг", _num(macro.get("debt", state.get("debt", 0.0))), impact("debt_sustainability", 2), source="debt_sustainability")
    add("Кредит", "Долг к ВВП", _pct(macro.get("debt_ratio", 0.0)), impact("debt_sustainability", 2), source="debt_sustainability")
    add("Кредит", "Процентная ставка", _pct(macro.get("interest_rate", finance.get("sovereign_rate", 0.0))), impact("interest_affordability", 2), source="interest_affordability")
    add("Кредит", "Рыночная процентная ставка", _pct(macro.get("market_rate", finance.get("market_rate", 0.0))), impact("interest_affordability", 2), source="interest_affordability")
    add("Кредит", "Процентные расходы", _num(expenditures.get("interest", 0.0)), -finite(expenditures.get("interest", 0.0)), "fiscal_flow", "interest")
    add("Кредит", "Частный кредит", _num(macro.get("private_credit", finance.get("desired_private_credit", 0.0))), impact("credit_depth", 3), source="credit_depth")
    add("Кредит", "Частный кредит к ВВП", _pct(macro.get("credit_to_gdp", finance.get("credit_to_gdp", 0.0))), impact("credit_depth", 3), source="credit_depth")
    add("Кредит", "Банковское здоровье", _pct(macro.get("banking_health", finance.get("banking_health", 0.0))), impact("banking_health"), source="banking_health")
    add("Кредит", "Ликвидность", _num(finance.get("deposit_base", financial_state.get("deposit_base", 0.0))), impact("liquidity", 2), source="liquidity")
    add("Кредит", "Депозитная база", _num(finance.get("deposit_base", financial_state.get("deposit_base", 0.0))), impact("liquidity", 2), source="liquidity")
    deposits = max(1.0, finite(finance.get("deposit_base", financial_state.get("deposit_base", 1.0)), 1.0))
    private_credit = finite(macro.get("private_credit", finance.get("desired_private_credit", 0.0)))
    add("Кредит", "Кредитный мультипликатор", _num(private_credit / deposits, 3), impact("credit_depth", 3), source="credit_depth")
    add("Кредит", "Leverage", _num(finance.get("leverage", financial_state.get("leverage", 0.0)), 3), impact("leverage_stability"), source="leverage_stability")
    add("Кредит", "Вытеснение частных инвестиций", _pct(finance.get("crowding_out", 0.0)), impact("interest_affordability", 3), source="interest_affordability")
    add("Кредит", "Кредитное рационирование", _pct(1.0 - finite(finance.get("rationing", 1.0), 1.0)), impact("credit_depth", 4), source="credit_depth")
    add("Кредит", "Чистое кредитование государства", _num(flow.get("government_net_lending", overall)), flow.get("government_net_lending", overall), "fiscal_flow", "government_net_lending")
    add("Кредит", "Чистое кредитование частного сектора", _num(flow.get("private_net_lending", 0.0)), impact("credit_depth", 4), source="credit_depth")
    add("Кредит", "Финансовый разрыв", _num(flow.get("financial_gap", 0.0)), impact("leverage_stability", 2), source="leverage_stability")

    # Trade, production, population and institutions.
    add("Торговля", "Торговый оборот", _num(revenues.get("trade_volume", finite(trade.get("export_value")) + finite(trade.get("import_value")))), impact("trade_openness", 2), source="trade_openness")
    add("Торговля", "Экспорт", _num(trade.get("export_value", 0.0)), max(0.0, impact("trade_balance", 3)), source="trade_balance")
    add("Торговля", "Импорт", _num(trade.get("import_value", 0.0)), min(0.0, impact("trade_balance", 3)), source="trade_balance")
    add("Торговля", "Сальдо торгового баланса", _num(trade.get("trade_balance", 0.0)), impact("trade_balance", 3), source="trade_balance")
    add("Торговля", "Сальдо текущего счёта", _num(trade.get("current_account", 0.0)), impact("current_account"), source="current_account")
    add("Торговля", "Торговая маржа", _num(_m(statement.get("sectors")).get("profitability", {}).get("commerce", 0.0), 3), impact("trade_margin"), source="trade_margin")
    add("Торговля", "Условия торговли", _num(trade.get("terms_of_trade", 1.0), 3), impact("terms_of_trade"), source="terms_of_trade")
    add("Торговля", "Импортозависимость", _pct(trade.get("import_dependency", 0.0)), impact("import_resilience"), source="import_resilience")
    add("Торговля", "Открытость торговли", _pct(trade.get("trade_openness", 0.0)), impact("trade_openness", 2), source="trade_openness")
    add("Торговля", "Внешнее доверие", _pct(trade.get("foreign_confidence", 0.0)), impact("foreign_confidence"), source="foreign_confidence")
    add("Торговля", "Таможенные сборы", _num(revenues.get("customs", 0.0)), revenues.get("customs", 0.0), "fiscal_flow", "customs")
    add("Торговля", "Коммерческий доход", _num(revenues.get("commerce", 0.0)), revenues.get("commerce", 0.0), "fiscal_flow", "commerce")

    add("Производство", "Основной капитал", _num(macro.get("capital_stock", state.get("capital_stock", 0.0))), impact("capital_turnover", 2), source="capital_turnover")
    add("Производство", "Амортизация", _num(sum(finite(v) for v in _m(state.get("sectoral_depreciation")).values()), 4), impact("capital_turnover", 4), source="capital_turnover")
    add("Производство", "Производительность труда", _num(real / max(1.0, finite(macro.get("labor", population * 0.46))), 3), impact("labor_productivity"), source="labor_productivity")
    add("Производство", "Человеческий капитал", _num(macro.get("human_capital", state.get("human_capital", 0.0))), impact("human_capital"), source="human_capital")
    add("Производство", "Инфраструктура", _num(macro.get("infrastructure", state.get("infrastructure", 0.0))), impact("infrastructure"), source="infrastructure")
    add("Производство", "Капиталоотдача", _num(real / max(1.0, finite(macro.get("capital_stock", state.get("capital_stock", 1.0)))), 3), impact("capital_turnover", 2), source="capital_turnover")

    add("Население", "Население", _num(population, 2), impact("gdp_per_capita", 4), source="gdp_per_capita")
    add("Население", "Урбанизация", _pct(macro.get("urbanization", demographics.get("urbanization_rate", 0.0))), impact("urbanization"), source="urbanization")
    add("Население", "Безработица", _pct(macro.get("unemployment", state.get("unemployment", 0.0))), impact("employment"), source="employment")
    add("Население", "Участие в рабочей силе", _pct(macro.get("labor_participation", 0.0)), impact("labor_participation"), source="labor_participation")
    add("Население", "Рабская доля", _pct(macro.get("slave_ratio", demographics.get("slave_ratio", 0.0))), impact("agriculture_share", 4), source="agriculture_share")
    add("Население", "Риск восстания рабов", _pct(macro.get("slave_revolt_risk", demographics.get("slave_revolt_risk", 0.0))), impact("provincial_stability", 4), source="provincial_stability")

    add("Институты", "Коррупция", _pct(macro.get("corruption", state.get("corruption", 0.0))), impact("corruption_control"), source="corruption_control")
    add("Институты", "Доверие", _pct(macro.get("confidence", state.get("confidence", 0.0))), impact("confidence"), source="confidence")
    add("Институты", "Неравенство", _pct(macro.get("inequality", state.get("inequality", 0.0))), impact("legitimacy", 3), source="legitimacy")
    add("Институты", "Политическая легитимность", _pct(macro.get("political_legitimacy", 0.0)), impact("legitimacy"), source="legitimacy")

    # Roman institutions use the dedicated decomposition published by v10.
    add("Римская экономика", "Annona", _num(roman.get("annona_cost", expenditures.get("grain_subsidy", 0.0))), impact("annona_efficiency", 2), source="annona_efficiency", note="Стоимость снабжения; не отдельный второй расход")
    add("Римская экономика", "Frumentatio", _num(roman.get("frumentatio_volume", grain.get("consumption", 0.0))), impact("annona_efficiency", 2), source="annona_efficiency")
    add("Римская экономика", "Horreum", _num(roman.get("horrea_cover", grain.get("stock_cover", 0.0)), 2), impact("grain_security"), source="grain_security")
    add("Римская экономика", "Publicani", _pct(roman.get("publicani_efficiency", revenues.get("compliance", 0.0))), impact("tax_compliance"), source="tax_compliance")
    add("Римская экономика", "Cursus Publicus", _num(roman.get("cursus_publicus_cost", 0.0)), impact("infrastructure"), source="infrastructure")
    add("Римская экономика", "Ager Publicus", _num(roman.get("ager_publicus", 0.0)), impact("domain_income", 3), source="domain_income")
    add("Римская экономика", "Patrimonium Caesaris", _num(roman.get("patrimonium_caesaris", 0.0)), impact("domain_income", 3), source="domain_income")
    add("Римская экономика", "Stipendium", _num(roman.get("stipendium", 0.0)), impact("military_burden", 2), source="military_burden")
    add("Римская экономика", "Castra et Logistica", _num(roman.get("castra_logistics", 0.0)), impact("military_burden", 2), source="military_burden")
    add("Римская экономика", "Tributum Soli", _num(roman.get("tributum_soli", 0.0)), impact("tax_capacity", 2), source="tax_capacity")
    add("Римская экономика", "Tributum Capitis", _num(roman.get("tributum_capitis", 0.0)), impact("tax_compliance", 2), source="tax_compliance")
    add("Римская экономика", "Decuma", _num(roman.get("decuma_volume", 0.0)), impact("agriculture_share"), source="agriculture_share")
    add("Римская экономика", "Scriptura", _num(roman.get("scriptura", 0.0)), impact("domain_income", 3), source="domain_income")
    add("Римская экономика", "Argentarii", _pct(roman.get("argentarii_health", macro.get("banking_health", 0.0))), impact("banking_health"), source="banking_health")
    add("Римская экономика", "Mensarii", _num(roman.get("mensarii_liquidity", finance.get("deposit_base", 0.0))), impact("liquidity"), source="liquidity")
    add("Римская экономика", "Nummularii", str(roman.get("nummularii_standard", state.get("coin_standard", "managed"))), impact("coin_quality"), source="coin_quality")
    add("Римская экономика", "Vectigal", _num(roman.get("vectigalia", 0.0)), impact("tax_capacity", 3), source="tax_capacity")
    add("Римская экономика", "Romanitas Fiscalis", _pct(roman.get("romanitas_fiscalis", 0.0)), impact("romanization"), source="romanization")
    add("Римская экономика", "Pax Romana", _pct(roman.get("pax_romana", 0.0)), impact("provincial_stability"), source="provincial_stability")

    # The complete active microformula library. These and only these rows sum to
    # ``revenues.micro_income``.
    for row in magic_rows:
        add(
            str(row.get("category", "Микроформулы")),
            str(row.get("label", row.get("key", "—"))),
            row.get("value", "—"),
            finite(row.get("gold_per_turn", 0.0)),
            "microformula",
            str(row.get("driver", "")),
            "",
            True,
            str(row.get("formula", "")),
        )
    return rows


def audit_glossary(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    micro_keys: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"Строка {index} не является словарём")
            continue
        marker = (str(row.get("category", "")).strip(), str(row.get("term", "")).strip())
        if not marker[0] or not marker[1]:
            errors.append(f"Строка {index} не имеет категории или термина")
        if marker in seen:
            errors.append(f"Повтор термина: {marker[0]} / {marker[1]}")
        seen.add(marker)
        kind = str(row.get("kind", "indicator"))
        if kind not in VALID_KINDS:
            errors.append(f"Неизвестный тип строки {kind!r}: {marker[0]} / {marker[1]}")
        gold = finite(row.get("gold_per_turn", float("nan")), float("nan"))
        if not math.isfinite(gold):
            errors.append(f"Нечисловой вклад: {marker[0]} / {marker[1]}")
        included = bool(row.get("included_in_micro_total", False))
        if included != (kind == "microformula"):
            errors.append(f"Неверный флаг micro-total: {marker[0]} / {marker[1]}")
        if kind == "microformula":
            if marker in micro_keys:
                errors.append(f"Повтор микроформулы: {marker[0]} / {marker[1]}")
            micro_keys.add(marker)
    return errors
