#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna — RES PUBLICA ORBIS.

Единый центр мировой политики. Модуль не создаёт вторую дипломатию и не
дублирует войны, торговлю, державы или династии: он объединяет их существующие
состояния и публичные контракты в один интерфейс и один порядок обработки хода.

Публичный контракт:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None)
    open_menu(player, ctx=None, start_section=None)
"""
from __future__ import annotations

import random
import re
import textwrap
from typing import Any

MODULE_VERSION = "1.0.0-res-publica-orbis"
SCHEMA_VERSION = 1
MAX_ARCHIVE_ROWS = 80


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


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _ctx(ctx: dict | None) -> dict:
    return ctx if isinstance(ctx, dict) else {}


def _plain(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r"\[[^\]]+\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _module(ctx: dict, name: str) -> Any:
    return ctx.get(name)


def _safe_call(fn: Any, *args: Any, default: Any = None, **kwargs: Any) -> Any:
    if not callable(fn):
        return default
    try:
        return fn(*args, **kwargs)
    except Exception:
        return default


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
                fn()
                return
            except Exception:
                pass

    def header(self, title: str, icon: str = "🌍", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try:
                fn(title, icon, getattr(self.C, "CYAN", ""), subtitle)
                return
            except TypeError:
                try:
                    fn(title, icon, getattr(self.C, "CYAN", ""))
                    if subtitle:
                        self.wrap(subtitle, "GRAY")
                    return
                except Exception:
                    pass
            except Exception:
                pass
        print(self.color(f"\n{'═' * 76}\n  {icon} {title}\n{'═' * 76}", "CYAN", True))
        if subtitle:
            self.wrap(subtitle, "GRAY")

    def section(self, title: str, color: str = "GOLD") -> None:
        fn = self.ctx.get("rui_section")
        if callable(fn) and self.C is not None:
            try:
                fn(title, getattr(self.C, color, ""))
                return
            except Exception:
                pass
        print(self.color(f"\n  ── {title} ──", color, True))

    def info(self, text: Any, color: str = "WHITE") -> None:
        fn = self.ctx.get("rui_info")
        if callable(fn) and self.C is not None:
            try:
                fn(str(text), getattr(self.C, color, ""))
                return
            except Exception:
                pass
        print(self.color("  " + str(text), color))

    def wrap(self, text: Any, color: str = "WHITE") -> None:
        fn = self.ctx.get("ui_wrap")
        if callable(fn) and self.C is not None:
            try:
                fn(str(text), color=getattr(self.C, color, ""))
                return
            except Exception:
                pass
        for line in textwrap.wrap(str(text), width=76, break_long_words=False):
            print(self.color("  " + line, color))

    def table(self, title: str, headers: list[str], rows: list[tuple], color: str = "CYAN") -> None:
        fn = self.ctx.get("rui_table")
        if callable(fn) and self.C is not None:
            try:
                fn(title, headers, rows, color=getattr(self.C, color, ""))
                return
            except Exception:
                pass
        self.section(title, color)
        if not rows:
            self.info("Нет данных.", "GRAY")
            return
        widths = [len(_plain(h)) for h in headers]
        clean_rows: list[list[str]] = []
        for row in rows:
            clean = [_plain(v) for v in row]
            clean_rows.append(clean)
            for index, value in enumerate(clean[:len(widths)]):
                widths[index] = min(28, max(widths[index], len(value)))
        print("  " + " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
        print("  " + "-+-".join("-" * width for width in widths))
        for row in clean_rows:
            print("  " + " | ".join(row[i][:widths[i]].ljust(widths[i]) for i in range(len(headers))))

    def menu(self, entries: list[tuple[str, str, str, str]], title: str = "Разделы") -> None:
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
            print(f"  {self.color(key, 'GOLD', True)}  {icon} {name}{suffix}")

    def choice(self, prompt: str, valid: list[str]) -> str:
        fn = self.ctx.get("read_choice")
        if callable(fn):
            try:
                return str(fn(prompt, valid)).upper()
            except Exception:
                pass
        allowed = {str(x).upper() for x in valid}
        while True:
            answer = input(prompt).strip().upper()
            if answer in allowed:
                return answer

    def pause(self, text: str = "Нажмите Enter...") -> None:
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


def _ensure_module(module: Any, player: Any, ctx: dict) -> dict:
    if module is not None and hasattr(module, "ensure_state"):
        try:
            result = module.ensure_state(player, ctx)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
    return {}


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    """Нормализует общий фасад, не создавая дубликатов дипломатических данных."""
    ctx = _ctx(ctx)
    foreign_ensure = ctx.get("ensure_external_policy_state")
    if callable(foreign_ensure):
        try:
            foreign_ensure(player)
        except Exception:
            pass

    state = getattr(player, "world_politics", None)
    if not isinstance(state, dict):
        state = {}
        player.world_politics = state
    state.setdefault("schema", SCHEMA_VERSION)
    state.setdefault("version", MODULE_VERSION)
    state.setdefault("last_open_turn", 0)
    state.setdefault("last_section", "dashboard")
    state.setdefault("history_filter", "all")

    for name in ("DIPLOMACY_AI", "NATIONS", "WARFARE_AI", "DIPLOMATIC_TRADE", "DYNASTIES", "WORLD_COUNCIL"):
        _ensure_module(_module(ctx, name), player, ctx)

    state["schema"] = SCHEMA_VERSION
    state["version"] = MODULE_VERSION
    player.world_politics = state
    return state


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    """Единый неинтерактивный порядок обновления мировой политики.

    Важен именно порядок: намерения держав → национальные бонусы → войны →
    торговля → династии. Срочные решения затем разбирает Consilium Orbis.
    """
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    errors: list[str] = []
    for name, label in (
        ("DIPLOMACY_AI", "стратегический ИИ"),
        ("NATIONS", "державы"),
        ("WARFARE_AI", "межгосударственные войны"),
        ("DIPLOMATIC_TRADE", "международная торговля"),
        ("DYNASTIES", "династии"),
    ):
        module = _module(ctx, name)
        if module is None or not hasattr(module, "process_turn"):
            continue
        try:
            module.process_turn(player, ctx)
        except Exception as exc:
            errors.append(f"{label}: {type(exc).__name__}: {exc}")
            debug = ctx.get("debug_log")
            if callable(debug):
                try:
                    debug("World politics turn failed (%s): %s", label, exc, exc_info=True)
                except Exception:
                    pass
    state["last_processed_turn"] = _i(getattr(player, "turn", 1), 1)
    state["last_errors"] = errors[-10:]
    return state


def _diplomacy(player: Any) -> dict:
    return _dict(getattr(player, "diplomacy", {}))


def _nation_catalog(ctx: dict) -> dict:
    module = _module(ctx, "NATIONS")
    catalog = getattr(module, "NATIONS", None) if module is not None else None
    return catalog if isinstance(catalog, dict) else {}


def _power_keys(player: Any, ctx: dict) -> list[str]:
    keys = set(_diplomacy(player))
    keys.update(_nation_catalog(ctx))
    ai = _dict(getattr(player, "diplomatic_ai", {}))
    keys.update(_dict(ai.get("powers")))
    return sorted(keys, key=lambda k: str(_dict(_diplomacy(player).get(k)).get("name", k)))


def _power_name(player: Any, ctx: dict, key: str) -> str:
    row = _dict(_diplomacy(player).get(key))
    if row.get("name"):
        return str(row["name"])
    nation = _dict(_nation_catalog(ctx).get(key))
    return str(nation.get("name", key))


def _goal_label(ctx: dict, value: Any) -> str:
    module = _module(ctx, "DIPLOMACY_AI")
    labels = getattr(module, "GOAL_LABELS", {}) if module is not None else {}
    return str(_dict(labels).get(value, value or "не определена"))


def _plan_label(ctx: dict, value: Any) -> str:
    module = _module(ctx, "DIPLOMACY_AI")
    labels = getattr(module, "PLAN_LABELS", {}) if module is not None else {}
    return str(_dict(labels).get(value, value or "нет"))


def _goods_label(ctx: dict, value: Any) -> str:
    module = _module(ctx, "DIPLOMATIC_TRADE")
    labels = getattr(module, "GOODS_LABELS", {}) if module is not None else {}
    return str(_dict(labels).get(value, value or "неизвестный товар"))


def _module_states(player: Any, ctx: dict) -> dict[str, dict]:
    return {
        "ai": _ensure_module(_module(ctx, "DIPLOMACY_AI"), player, ctx),
        "nations": _ensure_module(_module(ctx, "NATIONS"), player, ctx),
        "wars": _ensure_module(_module(ctx, "WARFARE_AI"), player, ctx),
        "trade": _ensure_module(_module(ctx, "DIPLOMATIC_TRADE"), player, ctx),
        "dynasties": _ensure_module(_module(ctx, "DYNASTIES"), player, ctx),
        "council": _ensure_module(_module(ctx, "WORLD_COUNCIL"), player, ctx),
    }


def _status_links(row: dict) -> str:
    links = []
    if row.get("at_war"):
        links.append("ВОЙНА")
    if row.get("client"):
        links.append("клиент")
    elif row.get("alliance"):
        links.append("союз")
    if row.get("married"):
        links.append("династия")
    if row.get("trade_pact"):
        links.append("торговля")
    if row.get("non_aggression"):
        links.append("ненападение")
    return ", ".join(links) or "нет договоров"


def _dashboard(ui: UI, player: Any, ctx: dict, states: dict[str, dict]) -> None:
    diplomacy = _diplomacy(player)
    fp = _dict(getattr(player, "foreign_policy", {}))
    wars = _dict(states["wars"].get("wars"))
    contracts = _list(states["trade"].get("contracts"))
    queue = _list(states["council"].get("queue"))
    missions = _list(fp.get("active_missions"))
    crises = _list(fp.get("crises"))

    alliances = sum(1 for row in diplomacy.values() if isinstance(row, dict) and row.get("alliance"))
    clients = sum(1 for row in diplomacy.values() if isinstance(row, dict) and row.get("client"))
    marriages = sum(1 for row in diplomacy.values() if isinstance(row, dict) and row.get("married"))
    trade_pacts = sum(1 for row in diplomacy.values() if isinstance(row, dict) and row.get("trade_pact"))

    ui.table("Положение Рима", ["Сфера", "Состояние"], [
        ("Внешнеполитический курс", fp.get("doctrine", "равновесие")),
        ("Дипломатический капитал", f"{_i(fp.get('capital', 0), 0)}/{_i(fp.get('capital_max', 0), 0) or '—'}"),
        ("Активные миссии / кризисы", f"{len(missions)} / {len(crises)}"),
        ("Мировая напряжённость", f"{_i(fp.get('global_tension', 0), 0)}/100"),
        ("Войны / срочные дела", f"{len(wars)} / {len(queue)}"),
        ("Торговые контракты", len(contracts)),
        ("Союзы / клиенты / браки", f"{alliances} / {clients} / {marriages}"),
        ("Торговые пакты", trade_pacts),
    ], "GOLD")

    ai_module = _module(ctx, "DIPLOMACY_AI")
    assessment = []
    if ai_module is not None and hasattr(ai_module, "strategic_assessment"):
        try:
            assessment = ai_module.strategic_assessment(player, ctx)
        except Exception:
            assessment = []
    if assessment:
        ui.table("Главные направления", ["Держава", "Угроза", "Возможность", "Рекомендация"], [
            (item.get("name"), item.get("danger"), item.get("opportunity"), item.get("recommendation"))
            for item in assessment[:4]
        ], "CYAN")

    recommendations = []
    if queue:
        recommendations.append(f"В Consilium Orbis ожидают решения {len(queue)} дел.")
    if wars:
        recommendations.append(f"Рим ведёт {len(wars)} войн; проверьте фронты и усталость.")
    if crises:
        recommendations.append(f"Нерешённых дипломатических кризисов: {len(crises)}.")
    if not contracts:
        recommendations.append("Нет долгосрочных торговых контрактов: можно направить торговое посольство.")
    if not recommendations:
        recommendations.append("Международное положение устойчиво; можно наращивать доверие и разведку.")
    ui.section("Заключение канцелярии", "PURPLE")
    for item in recommendations[:4]:
        ui.info("• " + item, "WHITE")


def _select_power(ui: UI, player: Any, ctx: dict, title: str = "ВЫБОР ДЕРЖАВЫ") -> str | None:
    keys = _power_keys(player, ctx)
    if not keys:
        ui.info("Иностранные державы ещё не инициализированы.", "RED")
        ui.pause()
        return None
    diplomacy = _diplomacy(player)
    ai_powers = _dict(_dict(getattr(player, "diplomatic_ai", {})).get("powers"))
    ui.screen(); ui.header(title, "🗺", "Единый реестр иностранных держав")
    rows = []
    for index, key in enumerate(keys, 1):
        row = _dict(diplomacy.get(key)); ai = _dict(ai_powers.get(key))
        plan = _plan_label(ctx, ai.get("plan"))
        rows.append((index, _power_name(player, ctx, key), row.get("disposition", 0), row.get("tension", 0), ai.get("readiness", "—"), plan, _status_links(row)))
    ui.table("Державы", ["#", "Держава", "Отн.", "Напр.", "Готов.", "План", "Связи"], rows, "CYAN")
    answer = ui.choice("\n  Держава (или Q): ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
    return None if answer == "Q" else keys[int(answer) - 1]


def _power_archive(ui: UI, player: Any, ctx: dict, key: str, states: dict[str, dict]) -> None:
    rows: list[tuple] = []
    sources = (
        ("ИИ", _list(_dict(_dict(states["ai"].get("powers")).get(key)).get("history"))),
        ("Держава", [h for h in _list(states["nations"].get("history")) if h.get("power") == key]),
        ("Война", [h for h in _list(states["wars"].get("history")) if h.get("power") == key]),
        ("Торговля", [h for h in _list(states["trade"].get("history")) if h.get("power") == key]),
        ("Совет", [h for h in _list(states["council"].get("history")) if h.get("power") == key]),
    )
    for source, items in sources:
        for item in items:
            rows.append((_i(item.get("turn", item.get("resolved_turn", 0)), 0), source, item.get("title", item.get("type", "событие")), item.get("text", item.get("summary", ""))))
    rows.sort(key=lambda row: row[0], reverse=True)
    ui.screen(); ui.header(f"АРХИВ: {_power_name(player, ctx, key).upper()}", "📜")
    if rows:
        ui.table("История отношений", ["Ход", "Источник", "Событие", "Содержание"], rows[:40], "GOLD")
    else:
        ui.info("Записей по этой державе пока нет.", "GRAY")
    ui.pause()


def _counterintelligence(ui: UI, player: Any, ctx: dict, key: str, states: dict[str, dict]) -> None:
    fp = _dict(getattr(player, "foreign_policy", {}))
    capital = _i(fp.get("capital", 0), 0)
    gold = _i(getattr(player, "gold", 0), 0)
    cost_gold, cost_capital = 45, 1
    pstate = _dict(_dict(states["ai"].get("powers")).get(key))
    row = _dict(_diplomacy(player).get(key))
    ui.screen(); ui.header("КОНТРРАЗВЕДЫВАТЕЛЬНАЯ ОПЕРАЦИЯ", "🕵", _power_name(player, ctx, key))
    ui.info(f"Цена: {cost_gold} золота и {cost_capital} дипломатический капитал. Казна: {gold}; ДК: {capital}.", "CYAN")
    ui.wrap("Агенты пытаются вскрыть текущий план державы и задержать его исполнение. Провал повышает напряжённость.", "GRAY")
    if ui.choice("\n  Начать операцию? (Y/N): ", ["Y", "N"]) == "N":
        return
    if gold < cost_gold or capital < cost_capital:
        ui.info("Недостаточно средств для операции.", "RED"); ui.pause(); return
    player.gold = gold - cost_gold
    fp["capital"] = capital - cost_capital
    chance = 0.55 + _i(row.get("intel", 20), 20) / 250
    if random.random() < chance:
        pstate["plan_progress"] = max(0, _i(pstate.get("plan_progress", 0), 0) - random.randint(12, 24))
        pstate["intel_confidence"] = max(0, _i(pstate.get("intel_confidence", 20), 20) - 8)
        row["intel"] = min(100, _i(row.get("intel", 20), 20) + 8)
        ui.info(f"Операция успешна. План раскрыт: {_plan_label(ctx, pstate.get('plan'))}; подготовка задержана.", "GREEN")
    else:
        row["tension"] = min(100, _i(row.get("tension", 30), 30) + 4)
        ui.info("Операция провалена. Иностранный двор подозревает вмешательство Рима.", "RED")
    ui.pause()


def _power_detail(ui: UI, player: Any, ctx: dict, key: str, states: dict[str, dict]) -> None:
    while True:
        diplomacy = _diplomacy(player)
        row = _dict(diplomacy.get(key))
        nation = _dict(_nation_catalog(ctx).get(key))
        ai = _dict(_dict(states["ai"].get("powers")).get(key))
        nation_state = _dict(_dict(states["nations"].get("powers")).get(key))
        war = _dict(_dict(states["wars"].get("wars")).get(key))
        contracts = [c for c in _list(states["trade"].get("contracts")) if c.get("power") == key]

        ui.screen(); ui.header(_power_name(player, ctx, key).upper(), nation.get("icon", "🦅"), nation.get("identity", ai.get("personality", "иностранная держава")))
        ui.table("Единое государственное досье", ["Параметр", "Содержание"], [
            ("Столица / устройство", f"{nation.get('capital', 'неизвестно')} / {nation.get('government', 'неизвестно')}"),
            ("Отношение / доверие / напряжение", f"{row.get('disposition', 0)} / {row.get('trust', 0)} / {row.get('tension', 0)}"),
            ("Страх / разведка / рычаги", f"{row.get('fear', 0)} / {row.get('intel', 0)} / {row.get('leverage', 0)}"),
            ("Связи с Римом", _status_links(row)),
            ("Казна / экономика / дипломатический вес", f"{ai.get('treasury', '—')} / {ai.get('economic_power', '—')} / {ai.get('diplomatic_weight', '—')}"),
            ("Людские ресурсы / готовность / флот", f"{ai.get('manpower', '—')} / {ai.get('readiness', '—')} / {ai.get('naval_power', '—')}"),
            ("Стабильность / усталость от войны", f"{ai.get('stability', '—')} / {ai.get('war_weariness', '—')}"),
            ("Характер", f"агрессия {ai.get('aggression', '—')}; риск {ai.get('risk', '—')}; честь {ai.get('honor', '—')}; торговля {ai.get('trade_drive', '—')}"),
            ("Цель / текущий план", f"{_goal_label(ctx, ai.get('goal'))} / {_plan_label(ctx, ai.get('plan'))} ({ai.get('plan_progress', 0)}/{max(1, _i(ai.get('plan_required', 0), 0))})"),
            ("Военное положение", f"фронт {war.get('front', '—')}; счёт {war.get('war_score', '—')}; {war.get('last_result', 'мир')}" if war else "мир"),
            ("Торговые контракты", len(contracts)),
            ("Открытые уникальные преимущества", ", ".join(_list(nation_state.get("unique_benefits_unlocked"))) or "нет"),
        ], "GOLD")
        if contracts:
            ui.table("Контракты", ["Товар", "Объём", "Цена", "Осталось", "Статус"], [
                (_goods_label(ctx, c.get("resource")), c.get("amount"), c.get("price"), c.get("remaining"), c.get("status")) for c in contracts
            ], "GREEN")
        roster = _list(nation.get("units"))
        if roster:
            ui.table("Национальные войска", ["Часть", "Класс", "Атака", "Защита", "Подвижность", "Особенность"], [
                (u.get("name"), u.get("class"), u.get("attack"), u.get("defense"), u.get("mobility"), u.get("trait")) for u in roster
            ], "CYAN")

        ui.menu([
            ("1", "Дипломатические действия", "миссия, договор, ультиматум или война", "🤝"),
            ("2", "Направить торговое посольство", "предложение попадёт в Consilium Orbis", "⚖"),
            ("3", "Контрразведывательная операция", "раскрыть и задержать план", "🕵"),
            ("4", "Архив отношений", "войны, торговля и решения", "📜"),
            ("Q", "Назад", "", "↩"),
        ], title="Приказы по державе")
        ch = ui.choice("\n  Приказ: ", ["1", "2", "3", "4", "Q"])
        if ch == "Q":
            return
        if ch == "1":
            action = ctx.get("external_power_actions")
            if callable(action):
                action(player, key, row)
            else:
                ui.info("Канцелярия дипломатических действий недоступна.", "RED"); ui.pause()
        elif ch == "2":
            trade = _module(ctx, "DIPLOMATIC_TRADE")
            if trade is not None and hasattr(trade, "propose_contract"):
                ok = bool(trade.propose_contract(player, key, ctx, forced=True))
                ui.info("Торговое посольство созвано; дело передано в Consilium Orbis." if ok else "Сейчас переговоры невозможны либо такое дело уже ожидает решения.", "GREEN" if ok else "RED")
            else:
                ui.info("Модуль международной торговли недоступен.", "RED")
            ui.pause()
        elif ch == "3":
            _counterintelligence(ui, player, ctx, key, states)
        elif ch == "4":
            _power_archive(ui, player, ctx, key, states)


def _dossiers_menu(ui: UI, player: Any, ctx: dict, states: dict[str, dict]) -> None:
    while True:
        key = _select_power(ui, player, ctx, "ДЕРЖАВЫ И ДИПЛОМАТИЯ")
        if key is None:
            return
        _power_detail(ui, player, ctx, key, states)


def _diplomatic_office(ui: UI, player: Any, ctx: dict) -> None:
    while True:
        ui.screen(); ui.header("КАНЦЕЛЯРИЯ ВНЕШНЕЙ ПОЛИТИКИ", "🏛", "Доктрина, миссии, кризисы и дипломатическая память")
        overview = ctx.get("external_policy_overview")
        if callable(overview):
            try:
                overview(player)
            except Exception:
                pass
        ui.menu([
            ("1", "Утвердить внешнеполитическую доктрину", "общий курс Рима", "🏛"),
            ("2", "Активные дипломатические миссии", "операции, сроки и шансы", "📜"),
            ("3", "Нерешённые кризисы", "ноты, требования и ультиматумы", "⚠"),
            ("4", "Дипломатические депеши", "история миссий и договоров", "📨"),
            ("5", "Справка", "капитал, разведка и договоры", "📚"),
            ("Q", "Назад", "", "↩"),
        ], title="Канцелярия")
        ch = ui.choice("\n  Приказ: ", ["1", "2", "3", "4", "5", "Q"])
        if ch == "Q": return
        fn_name = {"1": "choose_foreign_doctrine", "2": "show_active_foreign_missions", "3": "show_pending_foreign_crises", "4": "show_foreign_dispatches", "5": "show_foreign_policy_help"}.get(ch)
        fn = ctx.get(fn_name or "")
        if callable(fn):
            fn(player)
        else:
            ui.info("Раздел недоступен в этой сборке.", "RED"); ui.pause()


def _intelligence_menu(ui: UI, player: Any, ctx: dict, states: dict[str, dict]) -> None:
    ai_module = _module(ctx, "DIPLOMACY_AI")
    while True:
        assessment = []
        if ai_module is not None and hasattr(ai_module, "strategic_assessment"):
            try:
                assessment = ai_module.strategic_assessment(player, ctx)
            except Exception:
                assessment = []
        ui.screen(); ui.header("СТРАТЕГИЧЕСКАЯ РАЗВЕДКА", "🕸", "ИИ держав скрыт за разведывательными оценками, а не вынесен отдельной игровой кнопкой")
        if assessment:
            ui.table("Баланс угроз и возможностей", ["Держава", "Угроза", "Возможность", "Цель", "План", "Рекомендация"], [
                (a.get("name"), a.get("danger"), a.get("opportunity"), _goal_label(ctx, a.get("goal")), _plan_label(ctx, a.get("plan")), a.get("recommendation")) for a in assessment
            ], "CYAN")
        else:
            ui.info("Разведывательные оценки пока недоступны.", "GRAY")
        coalitions = _list(states["ai"].get("coalitions"))
        if coalitions:
            powers = _dict(states["ai"].get("powers"))
            ui.table("Коалиции", ["Участники", "Цель", "Сила", "Ход"], [
                (", ".join(_dict(powers.get(k)).get("name", k) for k in c.get("members", [])), c.get("purpose"), c.get("strength"), c.get("formed_turn")) for c in coalitions
            ], "RED")
        ui.menu([
            ("1", "Матрица отношений держав", "союзники и соперники вне Рима", "🕸"),
            ("2", "Подробное досье", "совмещённые сведения по одной державе", "🗺"),
            ("3", "Контрразведка", "сорвать подготовку иностранного плана", "🕵"),
            ("4", "Архив действий держав", "последние самостоятельные решения", "📜"),
            ("Q", "Назад", "", "↩"),
        ], title="Разведывательное управление")
        ch = ui.choice("\n  Выбор: ", ["1", "2", "3", "4", "Q"])
        if ch == "Q": return
        if ch == "1":
            relations = _dict(states["ai"].get("relations")); powers = _dict(states["ai"].get("powers")); keys = sorted(powers)
            ui.screen(); ui.header("МАТРИЦА ОТНОШЕНИЙ", "🕸")
            headers = ["Держава"] + [_dict(powers.get(k)).get("name", k)[:8] for k in keys]
            rows = [tuple([_dict(powers.get(a)).get("name", a)] + [_dict(relations.get(a)).get(b, 0) for b in keys]) for a in keys]
            ui.table("Отношения между державами", headers, rows, "PURPLE"); ui.pause()
        elif ch == "2":
            key = _select_power(ui, player, ctx)
            if key: _power_detail(ui, player, ctx, key, states)
        elif ch == "3":
            key = _select_power(ui, player, ctx, "ЦЕЛЬ КОНТРРАЗВЕДКИ")
            if key: _counterintelligence(ui, player, ctx, key, states)
        elif ch == "4":
            history = _list(states["ai"].get("history"))[-50:]
            ui.screen(); ui.header("АРХИВ СТРАТЕГИЧЕСКОЙ РАЗВЕДКИ", "📜")
            if history:
                powers = _dict(states["ai"].get("powers"))
                ui.table("Последние события", ["Ход", "Держава", "Событие", "Содержание"], [
                    (h.get("turn"), _dict(powers.get(h.get("power"))).get("name", "Рим"), h.get("title"), h.get("text")) for h in reversed(history)
                ], "GOLD")
            else: ui.info("Архив пуст.", "GRAY")
            ui.pause()


def _wars_menu(ui: UI, player: Any, ctx: dict, states: dict[str, dict]) -> None:
    while True:
        wars = _dict(states["wars"].get("wars"))
        ui.screen(); ui.header("ВОЙНЫ И КАМПАНИИ", "⚔", "Дипломатический статус, фронты и прямые операции сведены в один раздел")
        if wars:
            ui.table("Активные войны", ["Противник", "Фронт", "Счёт", "Усталость Рим/враг", "Армии", "Последний результат"], [
                (_power_name(player, ctx, key), war.get("front"), war.get("war_score"), f"{war.get('roman_weariness', 0)}/{war.get('enemy_weariness', 0)}", len(_list(war.get("enemy_armies"))), war.get("last_result"))
                for key, war in wars.items()
            ], "RED")
        else:
            ui.info("Рим не ведёт межгосударственных войн.", "GREEN")
        ui.menu([
            ("1", "Оперативный военный штаб", "кампании, армии, мирные предложения", "⚔"),
            ("2", "Досье противника", "политика, экономика и национальные войска", "🗺"),
            ("3", "Военный архив", "битвы, рейды и договоры", "📜"),
            ("Q", "Назад", "", "↩"),
        ], title="Военный совет")
        ch = ui.choice("\n  Выбор: ", ["1", "2", "3", "Q"])
        if ch == "Q": return
        if ch == "1":
            module = _module(ctx, "WARFARE_AI")
            if module is not None and hasattr(module, "open_menu"):
                module.open_menu(player, ctx)
            else:
                ui.info("Военный модуль недоступен.", "RED"); ui.pause()
            states["wars"] = _ensure_module(module, player, ctx)
        elif ch == "2":
            key = _select_power(ui, player, ctx)
            if key: _power_detail(ui, player, ctx, key, states)
        elif ch == "3":
            history = _list(states["wars"].get("history"))[-50:]
            ui.screen(); ui.header("ВОЕННЫЙ АРХИВ", "📜")
            if history:
                ui.table("Последние записи", ["Ход", "Держава", "Событие", "Содержание"], [
                    (h.get("turn"), _power_name(player, ctx, str(h.get("power") or "Рим")), h.get("title"), h.get("text")) for h in reversed(history)
                ], "RED")
            else: ui.info("Архив пуст.", "GRAY")
            ui.pause()


def _trade_menu(ui: UI, player: Any, ctx: dict, states: dict[str, dict]) -> None:
    trade = _module(ctx, "DIPLOMATIC_TRADE")
    while True:
        state = _ensure_module(trade, player, ctx)
        states["trade"] = state
        contracts = _list(state.get("contracts"))
        ui.screen(); ui.header("МЕЖДУНАРОДНАЯ ТОРГОВЛЯ", "⚖", "Контракты являются частью отношений с державой, а не отдельной мировой системой")
        if contracts:
            ui.table("Действующие контракты", ["Держава", "Товар", "Объём", "Цена", "Осталось", "Статус"], [
                (_power_name(player, ctx, str(c.get("power"))), _goods_label(ctx, c.get("resource")), c.get("amount"), c.get("price"), c.get("remaining"), c.get("status")) for c in contracts
            ], "GREEN")
        else:
            ui.info("Долгосрочных международных контрактов нет.", "GRAY")
        ui.menu([
            ("1", "Направить торговое посольство", "открыть переговоры с выбранной державой", "📨"),
            ("2", "Открыть досье торгового партнёра", "все связи и выгоды", "🗺"),
            ("3", "Архив торговли", "предложения, долги и расторжения", "📜"),
            ("Q", "Назад", "", "↩"),
        ], title="Торговая канцелярия")
        ch = ui.choice("\n  Выбор: ", ["1", "2", "3", "Q"])
        if ch == "Q": return
        if ch == "1":
            key = _select_power(ui, player, ctx, "ТОРГОВОЕ ПОСОЛЬСТВО")
            if key and trade is not None and hasattr(trade, "propose_contract"):
                ok = bool(trade.propose_contract(player, key, ctx, forced=True))
                ui.info("Предложение передано в Consilium Orbis." if ok else "Переговоры сейчас невозможны либо дело уже ожидает решения.", "GREEN" if ok else "RED"); ui.pause()
        elif ch == "2":
            key = _select_power(ui, player, ctx)
            if key: _power_detail(ui, player, ctx, key, states)
        elif ch == "3":
            history = _list(state.get("history"))[-50:]
            ui.screen(); ui.header("ТАБУЛЯРИЙ ТОРГОВЛИ", "📜")
            if history:
                ui.table("Последние записи", ["Ход", "Держава", "Событие", "Содержание"], [
                    (h.get("turn"), _power_name(player, ctx, str(h.get("power") or "—")), h.get("title"), h.get("text")) for h in reversed(history)
                ], "CYAN")
            else: ui.info("Архив пуст.", "GRAY")
            ui.pause()


def _dynasty_menu(ui: UI, player: Any, ctx: dict) -> None:
    module = _module(ctx, "DYNASTIES")
    if module is not None and hasattr(module, "open_menu"):
        module.open_menu(player, ctx)
        return
    ui.screen(); ui.header("ДИНАСТИИ И БРАКИ", "👑")
    ui.info("Модуль roma_dynasties.py не найден. Дипломатические статусы брака отображаются в досье держав, но активные переговоры недоступны.", "RED")
    ui.pause()


def _council_menu(ui: UI, player: Any, ctx: dict, states: dict[str, dict]) -> None:
    module = _module(ctx, "WORLD_COUNCIL")
    while True:
        state = _ensure_module(module, player, ctx)
        states["council"] = state
        queue = _list(state.get("queue"))
        settings = _dict(state.get("settings"))
        ui.screen(); ui.header("CONSILIUM ORBIS", "🏛", "Единый входящий ящик войн, торговли, браков, ультиматумов и кризисов")
        if queue:
            ui.table("Ожидают решения", ["Важность", "Тип", "Держава", "Дело", "До хода"], [
                (e.get("severity"), e.get("type"), _power_name(player, ctx, str(e.get("power") or "—")), e.get("title"), e.get("expires_turn")) for e in queue
            ], "RED")
        else:
            ui.info("Неотложных международных дел нет.", "GREEN")
        ui.info(f"Автооткрытие после хода: {'включено' if settings.get('auto_open', True) else 'выключено'}; максимум дел за заседание: {settings.get('max_events_after_turn', 8)}.", "CYAN")
        ui.menu([
            ("1", "Рассмотреть ожидающие дела", "открыть заседание сейчас", "📨"),
            ("2", "Архив решений", "принятые, отложенные и истёкшие дела", "📜"),
            ("3", "Настройки заседаний", "автооткрытие и предел дел", "⚙"),
            ("Q", "Назад", "", "↩"),
        ], title="Совет")
        ch = ui.choice("\n  Выбор: ", ["1", "2", "3", "Q"])
        if ch == "Q": return
        if ch == "1":
            if module is not None and hasattr(module, "process_pending"):
                module.process_pending(player, ctx, interactive=True)
            else:
                ui.info("Consilium Orbis недоступен.", "RED"); ui.pause()
        elif ch == "2":
            history = _list(state.get("history"))[-60:]
            ui.screen(); ui.header("АРХИВ CONSILIUM ORBIS", "📜")
            if history:
                ui.table("Решения", ["Ход", "Статус", "Тип", "Держава", "Дело"], [
                    (h.get("resolved_turn", h.get("created_turn")), h.get("status"), h.get("type"), _power_name(player, ctx, str(h.get("power") or "—")), h.get("title")) for h in reversed(history)
                ], "GOLD")
            else: ui.info("Архив пуст.", "GRAY")
            ui.pause()
        elif ch == "3":
            settings["auto_open"] = ui.choice(f"\n  Автооткрытие сейчас {'Y' if settings.get('auto_open', True) else 'N'}. Установить Y/N: ", ["Y", "N"]) == "Y"
            try:
                raw = input("  Максимум дел за заседание (1-20): ").strip()
                settings["max_events_after_turn"] = max(1, min(20, int(raw)))
            except (ValueError, EOFError):
                pass


def _unified_archive(ui: UI, player: Any, ctx: dict, states: dict[str, dict]) -> None:
    rows: list[tuple] = []
    for source, items in (
        ("ИИ", _list(states["ai"].get("history"))),
        ("Державы", _list(states["nations"].get("history"))),
        ("Войны", _list(states["wars"].get("history"))),
        ("Торговля", _list(states["trade"].get("history"))),
        ("Совет", _list(states["council"].get("history"))),
    ):
        for item in items:
            turn = _i(item.get("turn", item.get("resolved_turn", item.get("created_turn", 0))), 0)
            rows.append((turn, source, _power_name(player, ctx, str(item.get("power") or "Рим")), item.get("title", item.get("type", "событие")), item.get("text", item.get("summary", item.get("status", "")))))
    fp = _dict(getattr(player, "foreign_policy", {}))
    for item in _list(fp.get("dispatches")):
        rows.append((_i(item.get("turn", 0), 0), "Дипломатия", _power_name(player, ctx, str(item.get("target") or item.get("power") or "Рим")), item.get("title", "Депеша"), item.get("text", item.get("summary", ""))))
    rows.sort(key=lambda row: row[0], reverse=True)
    ui.screen(); ui.header("ТАБУЛЯРИЙ МИРОВОЙ ПОЛИТИКИ", "📚", "Единая хроника вместо нескольких разрозненных архивов")
    if rows:
        ui.table("Последние международные события", ["Ход", "Источник", "Держава", "Событие", "Содержание"], rows[:MAX_ARCHIVE_ROWS], "GOLD")
    else:
        ui.info("Международная хроника пока пуста.", "GRAY")
    ui.pause()


def _system_map(ui: UI, player: Any, ctx: dict, states: dict[str, dict]) -> None:
    modules = []
    for name, role in (
        ("DIPLOMACY_AI", "намерения, цели и отношения держав"),
        ("NATIONS", "идентичность, армии и уникальные бонусы"),
        ("WARFARE_AI", "прямые войны и кампании"),
        ("DIPLOMATIC_TRADE", "контракты и торговые споры"),
        ("DYNASTIES", "браки, дома и супруга"),
        ("WORLD_COUNCIL", "очередь срочных решений"),
    ):
        module = _module(ctx, name)
        modules.append((name, "доступен" if module is not None else "нет", role))
    ui.screen(); ui.header("УСТРОЙСТВО МИРОВОЙ ПОЛИТИКИ", "📚", MODULE_VERSION)
    ui.wrap("Единый центр является фасадом над существующими механиками. Он не создаёт вторые отношения, вторые войны или вторые торговые договоры: все экраны читают и изменяют одни и те же состояния игрока.", "WHITE")
    ui.table("Подсистемы", ["Модуль", "Статус", "Ответственность"], modules, "CYAN")
    ui.section("Что удалено как отдельная механика", "RED")
    ui.info("• Отдельная кнопка «Стратегический ИИ держав»: ИИ теперь работает в фоне, а игрок видит разведывательные выводы.")
    ui.info("• Отдельный сборный пункт «Державы, войны и династии»: его функции распределены по логичным разделам единого центра.")
    ui.info("• Дублирующие досье: государственные, дипломатические и разведывательные сведения объединены в одну карточку державы.")
    ui.info("• Разрозненные архивы: добавлен общий Табулярий мировой политики.")
    errors = _list(_dict(getattr(player, "world_politics", {})).get("last_errors"))
    if errors:
        ui.section("Последние ошибки обработки", "RED")
        for error in errors:
            ui.info("• " + str(error), "RED")
    ui.pause()


def _run_section(section: str, ui: UI, player: Any, ctx: dict, states: dict[str, dict]) -> None:
    if section == "dossiers": _dossiers_menu(ui, player, ctx, states)
    elif section == "diplomacy": _diplomatic_office(ui, player, ctx)
    elif section == "intelligence": _intelligence_menu(ui, player, ctx, states)
    elif section == "wars": _wars_menu(ui, player, ctx, states)
    elif section == "trade": _trade_menu(ui, player, ctx, states)
    elif section == "dynasties": _dynasty_menu(ui, player, ctx)
    elif section == "council": _council_menu(ui, player, ctx, states)
    elif section == "archive": _unified_archive(ui, player, ctx, states)
    elif section == "help": _system_map(ui, player, ctx, states)


def open_menu(player: Any, ctx: dict | None = None, start_section: str | None = None) -> None:
    ctx = _ctx(ctx)
    ui = UI(ctx)
    facade = ensure_state(player, ctx)
    states = _module_states(player, ctx)
    if start_section in {"dossiers", "diplomacy", "intelligence", "wars", "trade", "dynasties", "council", "archive", "help"}:
        _run_section(str(start_section), ui, player, ctx, states)

    while True:
        facade["last_open_turn"] = _i(getattr(player, "turn", 1), 1)
        states = _module_states(player, ctx)
        ui.screen(); ui.header("RES PUBLICA ORBIS", "🌍", "Единый центр мировой политики Рима")
        _dashboard(ui, player, ctx, states)
        ui.menu([
            ("1", "Державы и дипломатические действия", "единое досье, миссии, договоры и ультиматумы", "🗺"),
            ("2", "Канцелярия внешней политики", "доктрина, миссии, кризисы и депеши", "🏛"),
            ("3", "Стратегическая разведка", "угрозы, планы, коалиции и контрразведка", "🕸"),
            ("4", "Войны и кампании", "фронты, армии, счёт войны и мир", "⚔"),
            ("5", "Международная торговля", "контракты, посольства и споры", "⚖"),
            ("6", "Династии и браки", "царские дома, союзы и супруга", "👑"),
            ("7", "Consilium Orbis", "срочные решения и послеходовый совет", "📨"),
            ("8", "Табулярий мировой политики", "единая международная хроника", "📚"),
            ("9", "Устройство системы", "что объединено и какие модули работают", "⚙"),
            ("Q", "Назад", "", "↩"),
        ], title="Мировая политика")
        ch = ui.choice("\n  Ваш приказ: ", ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Q"])
        if ch == "Q":
            return
        section = {"1": "dossiers", "2": "diplomacy", "3": "intelligence", "4": "wars", "5": "trade", "6": "dynasties", "7": "council", "8": "archive", "9": "help"}[ch]
        facade["last_section"] = section
        _run_section(section, ui, player, ctx, states)
