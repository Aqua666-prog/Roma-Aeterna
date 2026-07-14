#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data-driven microformula library for Roma Aeterna.

The main economy engine supplies aggregate state.  This module turns that state
into hundreds of tiny, independently visible gold-per-turn contributions.
Nothing here mutates the player or the economy state.
"""

from __future__ import annotations

import math
from typing import Any

MICROFORMULA_VERSION = 2
MICROFORMULA_TARGET_COUNT = 306
MICROFORMULA_PRECISION = 3
# A tiny circulation dividend ensures that a neutral indicator still moves the
# treasury by a visible micro-amount. Strong negative signals remain negative.
MICROFORMULA_BASELINE_SIGNAL = 0.018


def finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, finite(value)))


def _safe_map(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _share(value: float, total: float) -> float:
    return finite(value) / max(1e-9, finite(total, 1.0))


def _fmt_percent(value: float) -> str:
    return f"{finite(value):.2%}"


def _fmt_number(value: float, digits: int = 2) -> float:
    return round(finite(value), digits)


def _signal_positive(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return clamp((finite(value) - low) / (high - low), -1.0, 1.0)


def _signal_inverse(value: float, good: float, bad: float) -> float:
    if bad <= good:
        return 0.0
    return clamp(1.0 - 2.0 * (finite(value) - good) / (bad - good), -1.0, 1.0)


def _signal_optimal(value: float, target: float, tolerance: float) -> float:
    return clamp(1.0 - abs(finite(value) - target) / max(1e-9, tolerance), -1.0, 1.0)


# Every group contains six named concepts.  The concepts share a measurable
# driver but receive slightly different weights, so the report looks like the
# layered accounting machinery of a large empire instead of one blunt bonus.
GROUPS: tuple[dict[str, Any], ...] = (
    {"key":"gdp_scale","category":"Национальные счета","weight":1.35,"terms":["Валовой внутренний продукт","Номинальный масштаб экономики","Реальный масштаб экономики","Совокупный выпуск","Валовой продукт провинций","Макроэкономическая база"]},
    {"key":"gdp_per_capita","category":"Национальные счета","weight":0.95,"terms":["Душевой валовой продукт","Средний продукт жителя","Подушевой выпуск","Реальный доход на душу","Экономическая обеспеченность","Подушевая налоговая способность"]},
    {"key":"value_added","category":"Национальные счета","weight":0.90,"terms":["Совокупная добавленная стоимость","Чистая добавленная стоимость","Отраслевая добавленная стоимость","Производственный доход","Факторный доход","Внутреннее создание стоимости"]},
    {"key":"capital_turnover","category":"Капитал и инвестиции","weight":0.85,"terms":["Капиталоотдача","Оборот основного капитала","Предельный продукт капитала","Фондоотдача","Коэффициент загрузки капитала","Эффективность капитальных фондов"]},
    {"key":"labor_productivity","category":"Производство","weight":0.95,"terms":["Продуктивность занятых","Средний продукт труда","Предельный продукт труда","Трудовая отдача","Эффективность рабочей силы","Выпуск на занятого"]},
    {"key":"infrastructure","category":"Инфраструктура","weight":1.10,"terms":["Инфраструктурная рента","Логистическая связность","Плотность дорожной сети","Пропускная способность путей","Транспортный мультипликатор","Сетевой эффект инфраструктуры"]},
    {"key":"human_capital","category":"Производство","weight":0.80,"terms":["Запас человеческого капитала","Квалификационная премия","Накопление знаний","Ремесленная компетенция","Административная грамотность","Технологическая восприимчивость"]},
    {"key":"tax_capacity","category":"Фиск","weight":1.05,"terms":["Ёмкость податной системы","Налоговая мощность","Административная собираемость","Охват налогового кадастра","Доходность ценза","Фискальная глубина"]},
    {"key":"laffer_alignment","category":"Фиск","weight":1.00,"terms":["Кривая Лаффера","Оптимум Лаффера","Предельная налоговая ставка","Эластичность налоговой базы","Избыточное налоговое бремя","Доходный максимум налогообложения"]},
    {"key":"tax_compliance","category":"Фиск","weight":1.10,"terms":["Полнота налоговых сборов","Добровольное налоговое соответствие","Фискальная дисциплина","Коэффициент уплаты","Налоговая лояльность","Эффективная ставка взыскания"]},
    {"key":"corruption_control","category":"Институты","weight":1.00,"terms":["Контроль коррупции","Утечка доходов","Рентный поиск","Фискальное расхищение","Агентские издержки","Административные потери"]},
    {"key":"confidence","category":"Финансы","weight":0.85,"terms":["Премия доверия","Деловые ожидания","Инвестиционная уверенность","Доверие вкладчиков","Ожидаемая устойчивость","Коэффициент уверенности"]},
    {"key":"fiscal_balance","category":"Фиск","weight":0.95,"terms":["Структурное сальдо казны","Циклически скорректированный баланс","Первичное сальдо казны","Фискальная брешь","Бюджетная позиция","Казначейское равновесие"]},
    {"key":"debt_sustainability","category":"Долг","weight":0.95,"terms":["Долговая устойчивость","Коэффициент долга к ВВП","Фискальное пространство","Платёжеспособность казны","Межвременное бюджетное ограничение","Риск суверенного долга"]},
    {"key":"price_stability","category":"Деньги","weight":0.80,"terms":["Ценовая стабильность","Инфляционный разрыв","Инерция дефлятора","Реальная покупательная способность","Индекс цен","Стабильность счётной единицы"]},
    {"key":"money_velocity","category":"Деньги","weight":0.75,"terms":["Циркуляция монеты","Оборотность денежной массы","Транзакционная интенсивность","Денежный оборот","Кассовая активность","Коэффициент обращения монеты"]},
    {"key":"monetization","category":"Деньги","weight":0.75,"terms":["Монетизация экономики","Коэффициент деньги к ВВП","Насыщенность монетой","Денежная глубина","Монетарная обеспеченность","Доля денежных расчётов"]},
    {"key":"coin_quality","category":"Деньги","weight":0.70,"terms":["Чистота чеканки","Металлическое содержание","Доверие к чеканке","Монетный стандарт","Качество денежного обращения","Монетарная репутация"]},
    {"key":"banking_health","category":"Кредит","weight":0.90,"terms":["Прочность банковских домов","Капитализация банков","Устойчивость argentarii","Платёжеспособность менял","Надёжность депозитов","Финансовая устойчивость посредников"]},
    {"key":"liquidity","category":"Кредит","weight":0.80,"terms":["Ликвидный запас","Коэффициент ликвидного покрытия","Вкладная база","Резервная обеспеченность","Кассовый резерв","Денежная доступность"]},
    {"key":"credit_depth","category":"Кредит","weight":0.80,"terms":["Кредитная глубина","Мультипликация ссуд","Глубина частного кредита","Финансовое посредничество","Доступность ссуд","Кредитная экспансия"]},
    {"key":"interest_affordability","category":"Кредит","weight":0.75,"terms":["Доступность процента","Реальная процентная ставка","Стоимость капитала","Процентное бремя","Цена кредита","Ставка дисконтирования"]},
    {"key":"leverage_stability","category":"Кредит","weight":0.65,"terms":["Финансовый рычаг","Кредитное плечо","Долговой мультипликатор","Коэффициент заёмного капитала","Балансовый риск","Устойчивость кредитного плеча"]},
    {"key":"trade_margin","category":"Торговля","weight":1.05,"terms":["Маржа негоциаторов","Валовая маржа торговли","Чистая торговая маржа","Спред купца","Наценка посредника","Рентабельность обмена"]},
    {"key":"trade_balance","category":"Торговля","weight":1.05,"terms":["Внешнеторговое сальдо","Чистый экспорт","Экспортный излишек","Товарное сальдо","Баланс внешней торговли","Нетто-поступления торговли"]},
    {"key":"current_account","category":"Торговля","weight":0.80,"terms":["Текущее внешнее сальдо","Баланс текущих операций","Внешнее финансовое сальдо","Чистые внешние поступления","Текущий платёжный баланс","Международная доходная позиция"]},
    {"key":"terms_of_trade","category":"Торговля","weight":0.85,"terms":["Соотношение цен обмена","Индекс экспортных цен","Индекс импортных цен","Меновая пропорция","Покупательная сила экспорта","Ценовое преимущество торговли"]},
    {"key":"trade_openness","category":"Торговля","weight":0.75,"terms":["Внешнеторговая открытость","Внешнеторговая квота","Интенсивность обмена","Интеграция рынков","Доля внешнего оборота","Торговая проницаемость"]},
    {"key":"import_resilience","category":"Торговля","weight":0.70,"terms":["Импортная устойчивость","Импортозамещение","Коэффициент самообеспечения","Внешняя зависимость","Стратегическая автономия снабжения","Устойчивость к эмбарго"]},
    {"key":"route_network","category":"Торговля","weight":0.95,"terms":["Рента торговых маршрутов","Плотность караванных путей","Морская связность","Сетевой эффект маршрутов","Транзитная рента","Доходность торговой сети"]},
    {"key":"trade_pacts","category":"Торговля","weight":0.75,"terms":["Договорная торговая премия","Преференциальный доступ","Торговая конвенция","Договорный мультипликатор","Союзный рынок","Дипломатическая торговая рента"]},
    {"key":"urbanization","category":"Население","weight":0.80,"terms":["Урбанизационная агломерация","Городская плотность","Агломерационный эффект","Концентрация спроса","Городская специализация","Рынок городского труда"]},
    {"key":"employment","category":"Население","weight":0.80,"terms":["Полная занятость","Коэффициент занятости","Естественная безработица","Циклическая безработица","Резерв рабочей силы","Использование труда"]},
    {"key":"labor_participation","category":"Население","weight":0.65,"terms":["Вовлечённость в рабочую силу","Экономическая активность населения","Коэффициент участия","Трудовая мобилизация","Доля занятых домохозяйств","Предложение труда"]},
    {"key":"agriculture_share","category":"Сельское хозяйство","weight":1.00,"terms":["Аграрная добавленная стоимость","Земельная рента","Урожайная производительность","Сельскохозяйственная специализация","Аграрный излишек","Рента пашни"]},
    {"key":"grain_security","category":"Сельское хозяйство","weight":1.05,"terms":["Зерновая безопасность","Покрытие анноны","Стратегический запас зерна","Продовольственная обеспеченность","Коэффициент хлебного покрытия","Устойчивость зернового баланса"]},
    {"key":"domain_income","category":"Римская экономика","weight":0.90,"terms":["Доход ager publicus","Рента государственных владений","Доходы императорских доменов","Поступления с saltus","Казённая земельная рента","Доход patrimonium"]},
    {"key":"romanization","category":"Римская экономика","weight":0.95,"terms":["Romanitas fiscalis","Романизационная налоговая премия","Правовая унификация","Латинская контрактная среда","Интеграция провинциального рынка","Муниципальная романизация"]},
    {"key":"municipal_density","category":"Римская экономика","weight":0.85,"terms":["Муниципальная плотность","Доход civitates","Фискальная сеть municipia","Городская кадастровая база","Муниципальный мультипликатор","Плотность местных рынков"]},
    {"key":"legitimacy","category":"Институты","weight":0.85,"terms":["Мандат правления","Доверие сената","Поддержка народа","Институциональная устойчивость","Согласие управляемых","Легитимационная премия"]},
    {"key":"innovation","category":"Технологии","weight":0.80,"terms":["Диффузия знаний","Технологический spillover","Инновационная рента","Распространение ремесленных техник","Накопление изобретений","Технологическая конвергенция"]},
    {"key":"mining_share","category":"Производство","weight":0.70,"terms":["Горная рента","Рудная добавленная стоимость","Доходность каменоломен","Металлургическая база","Экстрактивная специализация","Рента недр"]},
    {"key":"manufacturing_share","category":"Производство","weight":0.80,"terms":["Ремесленная добавленная стоимость","Мануфактурная маржа","Глубина переработки","Промышленная специализация","Доходность мастерских","Цепочка переделов"]},
    {"key":"construction_share","category":"Производство","weight":0.70,"terms":["Строительный мультипликатор","Выпуск общественных работ","Капитальное строительство","Инвестиционный спрос на стройку","Строительная добавленная стоимость","Мощность строительных артелей"]},
    {"key":"commerce_share","category":"Производство","weight":0.85,"terms":["Коммерческая добавленная стоимость","Доходность услуг","Рыночная специализация","Оборот форумов","Посредническая рента","Торгово-сервисный выпуск"]},
    {"key":"foreign_confidence","category":"Торговля","weight":0.70,"terms":["Доверие внешних рынков","Суверенная торговая репутация","Доверие иностранных купцов","Страновой риск","Премия международного расчёта","Внешняя кредитоспособность"]},
    {"key":"exchange_stability","category":"Деньги","weight":0.65,"terms":["Стабильность валютного курса","Курсовая волатильность","Паритетное выравнивание цен","Обменный паритет","Курсовая премия","Стабильность международной монеты"]},
    {"key":"public_works","category":"Инфраструктура","weight":0.75,"terms":["Мультипликатор общественных работ","Инвестиционный импульс","Спрос на капитальные работы","Эффект crowding-in","Инфраструктурный акселератор","Казённый строительный заказ"]},
    {"key":"annona_efficiency","category":"Римская экономика","weight":0.75,"terms":["Annona civica","Эффективность frumentatio","Хлебная логистика","Распределение зернового пайка","Складская ротация horrea","Фискальная устойчивость анноны"]},
    {"key":"military_burden","category":"Фиск","weight":0.85,"terms":["Военно-фискальная нагрузка","Доля военных расходов","Содержание легионов","Военное вытеснение инвестиций","Бремя stipendium","Фискальная цена безопасности"]},
    {"key":"provincial_stability","category":"Римская экономика","weight":0.85,"terms":["Провинциальная стабильность","Мирная рента провинций","Снижение сборных издержек","Безопасность налоговых путей","Устойчивость cursus publicus","Премия pax Romana"]},
)


def modifier_count() -> int:
    return sum(len(group["terms"]) for group in GROUPS)


def _build_metrics(
    context: dict[str, Any],
    state: dict[str, Any],
    macro: dict[str, Any],
    sectors: dict[str, Any],
    finance: dict[str, Any],
    trade: dict[str, Any],
    revenues: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    revenues = _safe_map(revenues)
    outputs = _safe_map(sectors.get("output"))
    total_output = max(1.0, sum(max(0.0, finite(v)) for v in outputs.values()))
    nominal = max(1.0, finite(macro.get("nominal_output", 1.0)))
    real = max(1.0, finite(macro.get("real_output", nominal)))
    population = max(1.0, finite(macro.get("population", state.get("population", 1.0))))
    capital = max(1.0, finite(macro.get("capital_stock", sum(_safe_map(sectors.get("capital")).values()) or state.get("capital_stock", 1.0))))
    infrastructure = max(0.0, finite(macro.get("infrastructure", state.get("infrastructure", 0.0))))
    human_capital = max(0.0, finite(macro.get("human_capital", state.get("human_capital", 0.0))))
    tax_capacity = clamp(finite(macro.get("tax_capacity", state.get("tax_capacity", 0.48))), 0.0, 1.0)
    corruption = clamp(finite(macro.get("corruption", state.get("corruption", 0.12))), 0.0, 1.0)
    confidence = clamp(finite(macro.get("confidence", state.get("confidence", 0.72))), 0.0, 1.0)
    inflation = finite(macro.get("inflation", state.get("inflation", 0.0)))
    price_level = max(0.01, finite(macro.get("price_level", state.get("price_level", 1.0)), 1.0))
    velocity = finite(macro.get("velocity", state.get("velocity", 1.75)), 1.75)
    money_supply = max(1.0, finite(macro.get("money_supply", state.get("money_supply", nominal))))
    banking = clamp(finite(macro.get("banking_health", finance.get("banking_health", 0.78))), 0.0, 1.0)
    deposits = max(0.0, finite(finance.get("deposit_base", _safe_map(state.get("financial")).get("deposit_base", 0.0))))
    credit_ratio = max(0.0, finite(macro.get("credit_to_gdp", finance.get("credit_to_gdp", 0.0))))
    market_rate = max(0.0, finite(macro.get("market_rate", finance.get("market_rate", 0.05))))
    leverage = max(0.0, finite(finance.get("leverage", _safe_map(state.get("financial")).get("leverage", 0.0))))
    commerce_profit = finite(_safe_map(sectors.get("profitability")).get("commerce", 1.0), 1.0)
    trade_balance = finite(trade.get("trade_balance", 0.0))
    current_account = finite(trade.get("current_account", trade_balance))
    terms = clamp(finite(trade.get("terms_of_trade", 1.0), 1.0), 0.25, 4.0)
    openness = clamp(finite(trade.get("trade_openness", 0.0)), 0.0, 2.0)
    import_dependency = clamp(finite(trade.get("import_dependency", 0.0)), 0.0, 2.0)
    foreign_confidence = clamp(finite(trade.get("foreign_confidence", 0.5)), 0.0, 1.0)
    exchange_rate = clamp(finite(trade.get("exchange_rate", 1.0), 1.0), 0.05, 20.0)
    urbanization = clamp(finite(macro.get("urbanization", _safe_map(state.get("demographics")).get("urbanization_rate", 0.2))), 0.0, 1.0)
    unemployment = clamp(finite(macro.get("unemployment", state.get("unemployment", 0.08))), 0.0, 1.0)
    labor_participation = clamp(finite(macro.get("labor_participation", 0.46)), 0.0, 1.0)
    romanization = clamp(finite(context.get("avg_romanization", 0.0)), 0.0, 100.0)
    route_value = max(0.0, finite(context.get("trade_route_value", 0.0)))
    trade_pacts = max(0.0, finite(context.get("trade_pacts", 0.0)))
    building_count = max(0.0, finite(context.get("municipal_building_count", 0.0)))
    province_count = max(1.0, finite(context.get("province_count", macro.get("province_count", 1.0)), 1.0))
    legitimacy = clamp(finite(macro.get("political_legitimacy", 0.5)), 0.0, 1.0)
    innovation = max(0.0, finite(_safe_map(state.get("innovation")).get("diffusion", 0.0)))
    debt_ratio = max(0.0, finite(macro.get("debt_ratio", finite(state.get("debt", 0.0)) / nominal)))
    state_domain_income = max(0.0, finite(context.get("state_domain_income", 0.0)))
    avg_unrest = clamp(finite(context.get("avg_province_unrest", context.get("effective_unrest", 0.0))) / 10.0, 0.0, 1.0)
    force_limit = max(1.0, finite(context.get("legion_force_limit", 1.0)))
    legion_count = max(0.0, finite(context.get("legion_count", 0.0)))
    military_burden = legion_count / force_limit
    grain_supply = max(0.0, finite(_safe_map(trade.get("supply")).get("grain", 0.0)) + finite(context.get("special_grain_income", 0.0)))
    grain_demand = max(1.0, finite(_safe_map(trade.get("demand")).get("grain", population * 0.5)))
    grain_cover = grain_supply / grain_demand
    public_works = max(0.0, finite(context.get("public_works_demand", 0.0))) / nominal
    tax_rate = clamp(finite(state.get("tax_rate", 0.22)), 0.0, 0.80)
    tariff_rate = clamp(finite(state.get("tariff_rate", 0.08)), 0.0, 0.80)
    compliance = clamp(finite(revenues.get("compliance", (0.50 + 0.50 * tax_capacity) * (1.0 - 0.72 * corruption))), 0.0, 1.0)
    ordinary_revenue = sum(max(0.0, finite(revenues.get(k, 0.0))) for k in ("direct_tax", "customs", "domains", "tribute", "commerce", "base_revenue"))
    last_balance = finite(_safe_map(state.get("fiscal")).get("last_balance", ordinary_revenue * 0.10))
    fiscal_ratio = last_balance / max(1.0, ordinary_revenue)
    coin_standard = str(state.get("coin_standard", "managed"))
    coin_signal = {"sound": 1.0, "managed": 0.35, "debased": -0.75}.get(coin_standard, 0.0)

    metrics: dict[str, dict[str, Any]] = {}
    def put(key: str, value: Any, signal: float) -> None:
        metrics[key] = {"value": value, "signal": clamp(signal, -1.0, 1.0)}

    put("gdp_scale", _fmt_number(nominal), _signal_positive(math.log1p(nominal), math.log1p(60), math.log1p(3000)))
    put("gdp_per_capita", _fmt_number(real / population, 3), _signal_positive(real / population, 0.20, 2.20))
    put("value_added", _fmt_number(nominal), _signal_positive(nominal / province_count, 25.0, 300.0))
    # Высокая капиталоотдача (капитал дефицитен, каждый асс работает) — не
    # провал, а нормальное состояние ранней экономики; штрафуем только
    # простаивающий капитал (низкий Y/K), а избыток отдачи насыщаем сверху.
    capital_turnover = real / capital
    put("capital_turnover", _fmt_number(capital_turnover, 3), _signal_positive(min(capital_turnover, 1.0), 0.15, 0.90))
    put("labor_productivity", _fmt_number(real / max(1.0, finite(macro.get("labor", population * 0.46))), 3), _signal_positive(real / max(1.0, finite(macro.get("labor", population * 0.46))), 0.25, 2.50))
    put("infrastructure", _fmt_number(infrastructure, 1), _signal_positive(infrastructure, 20.0, 150.0))
    put("human_capital", _fmt_number(human_capital, 1), _signal_positive(human_capital, 15.0, 100.0))
    put("tax_capacity", _fmt_percent(tax_capacity), _signal_positive(tax_capacity, 0.20, 0.95))
    put("laffer_alignment", _fmt_percent(tax_rate), _signal_optimal(tax_rate, 0.24 + 0.10 * tax_capacity, 0.28))
    put("tax_compliance", _fmt_percent(compliance), _signal_positive(compliance, 0.30, 0.95))
    put("corruption_control", _fmt_percent(corruption), _signal_inverse(corruption, 0.04, 0.55))
    put("confidence", _fmt_percent(confidence), _signal_positive(confidence, 0.25, 0.95))
    put("fiscal_balance", _fmt_percent(fiscal_ratio), clamp(fiscal_ratio / 0.35, -1.0, 1.0))
    put("debt_sustainability", _fmt_percent(debt_ratio), _signal_inverse(debt_ratio, 0.10, 1.60))
    put("price_stability", _fmt_percent(inflation), _signal_optimal(inflation, 0.015, 0.18))
    put("money_velocity", _fmt_number(velocity, 3), _signal_optimal(velocity, 1.75, 1.15))
    put("monetization", _fmt_number(money_supply / nominal, 3), _signal_optimal(money_supply / nominal, 1.80, 1.80))
    put("coin_quality", coin_standard, coin_signal)
    put("banking_health", _fmt_percent(banking), _signal_positive(banking, 0.25, 0.95))
    put("liquidity", _fmt_number(deposits / nominal, 3), _signal_optimal(deposits / nominal, 0.70, 0.85))
    put("credit_depth", _fmt_percent(credit_ratio), _signal_optimal(credit_ratio, 0.55, 0.85))
    put("interest_affordability", _fmt_percent(market_rate), _signal_inverse(market_rate, 0.03, 0.45))
    put("leverage_stability", _fmt_number(leverage, 3), _signal_optimal(leverage, 0.85, 1.15))
    put("trade_margin", _fmt_number(commerce_profit, 3), _signal_positive(commerce_profit, 0.65, 1.50))
    put("trade_balance", _fmt_number(trade_balance, 2), clamp(trade_balance / max(10.0, nominal * 0.20), -1.0, 1.0))
    put("current_account", _fmt_number(current_account, 2), clamp(current_account / max(10.0, nominal * 0.25), -1.0, 1.0))
    put("terms_of_trade", _fmt_number(terms, 3), clamp((terms - 1.0) / 0.85, -1.0, 1.0))
    put("trade_openness", _fmt_percent(openness), _signal_optimal(openness, 0.55, 0.65))
    put("import_resilience", _fmt_percent(import_dependency), _signal_inverse(import_dependency, 0.08, 0.75))
    put("route_network", _fmt_number(route_value, 1), _signal_positive(route_value / province_count, 0.0, 120.0))
    put("trade_pacts", int(trade_pacts), _signal_positive(trade_pacts, 0.0, 8.0))
    put("urbanization", _fmt_percent(urbanization), _signal_optimal(urbanization, 0.42, 0.45))
    put("employment", _fmt_percent(1.0 - unemployment), _signal_inverse(unemployment, 0.03, 0.38))
    put("labor_participation", _fmt_percent(labor_participation), _signal_optimal(labor_participation, 0.50, 0.28))
    put("agriculture_share", _fmt_percent(_share(outputs.get("agriculture", 0.0), total_output)), _signal_optimal(_share(outputs.get("agriculture", 0.0), total_output), 0.32, 0.30))
    put("grain_security", _fmt_number(grain_cover, 3), _signal_optimal(grain_cover, 1.20, 1.10))
    put("domain_income", _fmt_number(state_domain_income, 2), _signal_positive(state_domain_income / nominal, 0.0, 0.30))
    put("romanization", _fmt_percent(romanization / 100.0), _signal_positive(romanization, 10.0, 100.0))
    put("municipal_density", _fmt_number(building_count / province_count, 2), _signal_positive(building_count / province_count, 0.0, 10.0))
    put("legitimacy", _fmt_percent(legitimacy), _signal_positive(legitimacy, 0.25, 0.95))
    put("innovation", _fmt_number(innovation, 3), _signal_positive(innovation, 0.0, 2.5))
    put("mining_share", _fmt_percent(_share(outputs.get("mining", 0.0), total_output)), _signal_optimal(_share(outputs.get("mining", 0.0), total_output), 0.13, 0.16))
    put("manufacturing_share", _fmt_percent(_share(outputs.get("manufacturing", 0.0), total_output)), _signal_optimal(_share(outputs.get("manufacturing", 0.0), total_output), 0.22, 0.22))
    put("construction_share", _fmt_percent(_share(outputs.get("construction", 0.0), total_output)), _signal_optimal(_share(outputs.get("construction", 0.0), total_output), 0.13, 0.17))
    put("commerce_share", _fmt_percent(_share(outputs.get("commerce", 0.0), total_output)), _signal_optimal(_share(outputs.get("commerce", 0.0), total_output), 0.20, 0.22))
    put("foreign_confidence", _fmt_percent(foreign_confidence), _signal_positive(foreign_confidence, 0.20, 0.95))
    put("exchange_stability", _fmt_number(exchange_rate, 3), _signal_optimal(exchange_rate, 1.0, 1.25))
    put("public_works", _fmt_percent(public_works), _signal_optimal(public_works, 0.10, 0.30))
    put("annona_efficiency", _fmt_number(grain_cover, 3), _signal_optimal(grain_cover, 1.10, 0.95))
    put("military_burden", _fmt_percent(military_burden), _signal_inverse(military_burden, 0.30, 1.60))
    put("provincial_stability", _fmt_percent(1.0 - avg_unrest), _signal_inverse(avg_unrest, 0.05, 0.80))
    return metrics


def calculate_modifiers(
    context: dict[str, Any],
    state: dict[str, Any],
    macro: dict[str, Any],
    sectors: dict[str, Any],
    finance: dict[str, Any],
    trade: dict[str, Any],
    revenues: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return every microformula with a bounded, independently visible impact.

    The rows are *shares* of two fixed envelopes: a positive economic dividend
    and a stress-dependent loss envelope. Adding more vocabulary therefore never
    prints additional money. A tiny baseline circulation signal keeps neutral
    concepts visible without masking genuinely bad indicators.
    """
    metrics = _build_metrics(context, state, macro, sectors, finance, trade, revenues)
    nominal = max(1.0, finite(macro.get("nominal_output", 1.0)))
    provinces = max(1.0, finite(context.get("province_count", macro.get("province_count", 1.0)), 1.0))
    buildings = max(0.0, finite(context.get("municipal_building_count", 0.0)))

    # Use the completed macro snapshot rather than optional raw state keys. The
    # previous implementation silently treated unemployment as zero because the
    # canonical value lives in ``macro``.
    corruption = clamp(finite(macro.get("corruption", state.get("corruption", 0.0))), 0.0, 1.0)
    unemployment = clamp(finite(macro.get("unemployment", state.get("unemployment", 0.0))), 0.0, 1.0)
    inflation = abs(finite(macro.get("inflation", state.get("inflation", 0.0))))
    debt = max(0.0, finite(macro.get("debt", state.get("debt", 0.0))))
    banking_stress = 1.0 - clamp(
        finite(macro.get("banking_health", finance.get("banking_health", 1.0)), 1.0),
        0.0,
        1.0,
    )
    stress = clamp(
        0.27 * corruption
        + 0.20 * unemployment
        + 0.22 * clamp(inflation / 0.30, 0.0, 1.0)
        + 0.18 * clamp(debt / nominal, 0.0, 1.0)
        + 0.13 * banking_stress,
        0.0,
        1.0,
    )

    raw_rows: list[dict[str, Any]] = []
    for group_index, group in enumerate(GROUPS):
        key = str(group["key"])
        metric = metrics.get(key, {"value": 0.0, "signal": 0.0})
        signal = clamp(finite(metric.get("signal", 0.0)), -1.0, 1.0)
        weight = max(0.0, finite(group.get("weight", 1.0), 1.0))
        # The baseline fades towards both extremes and is largest at neutrality.
        baseline = MICROFORMULA_BASELINE_SIGNAL * (1.0 - abs(signal))
        effective_signal = clamp(signal + baseline, -1.0, 1.0)
        if abs(effective_signal) < 1e-12:
            effective_signal = MICROFORMULA_BASELINE_SIGNAL
        terms = tuple(group["terms"])
        for term_index, term in enumerate(terms):
            # Deterministic 0.72..1.08 dispersion prevents six exact duplicates.
            spread = 0.72 + ((group_index * 7 + term_index * 5) % 10) * 0.04
            raw_gold = effective_signal * weight * spread
            raw_rows.append({
                "key": f"{key}__{term_index + 1}",
                "driver": key,
                "label": str(term),
                "value": metric.get("value", 0.0),
                "signal": round(signal, 6),
                "baseline_signal": round(baseline, 6),
                "effective_signal": round(effective_signal, 6),
                "weight": round(weight, 6),
                "spread": round(spread, 6),
                "raw_gold": raw_gold,
                "category": str(group["category"]),
                "kind": "microformula",
                "included_in_micro_total": True,
            })

    positive_raw = sum(max(0.0, finite(row["raw_gold"])) for row in raw_rows)
    negative_raw = sum(max(0.0, -finite(row["raw_gold"])) for row in raw_rows)

    # Hundreds of rows share bounded envelopes. The square roots make growth
    # useful but sublinear; provinces matter, while raw vocabulary count does not.
    positive_budget = clamp(
        10.0 + math.sqrt(nominal) * 1.35 + provinces * 1.30 + math.sqrt(buildings) * 1.10,
        18.0,
        175.0,
    )
    positive_budget *= clamp(0.82 + 0.30 * (1.0 - stress), 0.75, 1.15)
    negative_budget = clamp(
        positive_budget * (0.10 + 0.42 * stress),
        2.0,
        positive_budget * 0.60,
    )
    positive_scale = positive_budget / positive_raw if positive_raw > 1e-12 else 0.0
    negative_scale = negative_budget / negative_raw if negative_raw > 1e-12 else 0.0

    result: list[dict[str, Any]] = []
    for row in raw_rows:
        raw = finite(row.pop("raw_gold"))
        scale = positive_scale if raw >= 0.0 else negative_scale
        gold = raw * scale
        rounded = round(gold, MICROFORMULA_PRECISION)
        if rounded == 0.0 and raw != 0.0:
            rounded = math.copysign(10 ** (-MICROFORMULA_PRECISION), raw)
        row["normalization_scale"] = round(scale, 8)
        row["gold_per_turn"] = rounded
        row["formula"] = (
            f"({row['signal']:+.4f} + {row['baseline_signal']:.4f}) × "
            f"{row['weight']:.2f} × {row['spread']:.2f} × {scale:.5f}"
        )
        result.append(row)

    # Rounding must not make the visible rows disagree with their envelopes.
    target_total = (positive_budget if positive_raw > 1e-12 else 0.0) - (
        negative_budget if negative_raw > 1e-12 else 0.0
    )
    visible_total = sum(finite(row.get("gold_per_turn", 0.0)) for row in result)
    residual = round(target_total - visible_total, MICROFORMULA_PRECISION)
    if residual and result:
        anchor = max(result, key=lambda row: abs(finite(row.get("gold_per_turn", 0.0))))
        anchor["gold_per_turn"] = round(
            finite(anchor.get("gold_per_turn", 0.0)) + residual,
            MICROFORMULA_PRECISION,
        )
        anchor["rounding_reconciliation"] = residual

    return result


def modifier_summary(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    """Compact audit-friendly totals for a calculated modifier library."""
    clean = [row for row in rows if isinstance(row, dict)]
    positive = sum(max(0.0, finite(row.get("gold_per_turn", 0.0))) for row in clean)
    negative = sum(min(0.0, finite(row.get("gold_per_turn", 0.0))) for row in clean)
    return {
        "count": len(clean),
        "positive": round(positive, MICROFORMULA_PRECISION),
        "negative": round(negative, MICROFORMULA_PRECISION),
        "net": round(positive + negative, MICROFORMULA_PRECISION),
        "zero_rows": sum(1 for row in clean if finite(row.get("gold_per_turn", 0.0)) == 0.0),
    }

def audit_library() -> list[str]:
    errors: list[str] = []
    keys: set[str] = set()
    terms: set[str] = set()
    for group in GROUPS:
        key = str(group.get("key", "")).strip()
        category = str(group.get("category", "")).strip()
        weight = finite(group.get("weight", float("nan")), float("nan"))
        if not key:
            errors.append("Группа без ключа")
        elif key in keys:
            errors.append(f"Повтор ключа группы: {key}")
        keys.add(key)
        if not category:
            errors.append(f"Группа {key or '—'} не имеет категории")
        if not math.isfinite(weight) or weight <= 0.0:
            errors.append(f"Группа {key or '—'} имеет недопустимый вес {group.get('weight')!r}")
        group_terms = group.get("terms")
        if not isinstance(group_terms, (list, tuple)) or len(group_terms) != 6:
            errors.append(f"Группа {key} должна содержать ровно 6 терминов")
            continue
        for term in group_terms:
            label = str(term).strip()
            if not label:
                errors.append(f"Пустой термин в группе {key}")
            elif label in terms:
                errors.append(f"Повтор термина: {label}")
            terms.add(label)

    if modifier_count() != MICROFORMULA_TARGET_COUNT:
        errors.append(
            f"Ожидалось {MICROFORMULA_TARGET_COUNT} микроформул, найдено {modifier_count()}"
        )

    # Ensure every declared driver is actually produced by the metric builder.
    probe_metrics = _build_metrics(
        {"province_count": 1},
        {},
        {"nominal_output": 100.0, "real_output": 100.0, "population": 100.0},
        {"output": {}, "capital": {}, "profitability": {}},
        {},
        {},
        {},
    )
    missing = sorted(keys - set(probe_metrics))
    extra = sorted(set(probe_metrics) - keys)
    if missing:
        errors.append("Нет расчёта метрик для драйверов: " + ", ".join(missing))
    if extra:
        errors.append("Метрики без группы терминов: " + ", ".join(extra))
    return errors

