#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna — MERCATURA GENTIUM.

Расширенная торговля с иностранными государствами: долгосрочные контракты,
эксклюзивные товары, встречные предложения, задолженность, расторжение и
торговые привилегии. Важные предложения автоматически отправляются в
Consilium Orbis после хода.

Публичный контракт:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None)
    propose_contract(player, power_key, ctx=None, forced=False)
    handle_council_event(player, event, ctx, ui)
    expire_council_event(player, event, ctx)
    open_menu(player, ctx=None)
"""
from __future__ import annotations

import copy
import random
import re
import textwrap
import uuid
from typing import Any

MODULE_VERSION = "1.0.0-mercatura-gentium"
SCHEMA_VERSION = 1
MAX_HISTORY = 220


def _i(value: Any, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        value = default
    if low is not None: value = max(low, value)
    if high is not None: value = min(high, value)
    return value


def _f(value: Any, default: float = 0.0) -> float:
    try: return float(value)
    except (TypeError, ValueError, OverflowError): return default


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
    def header(self, title: str, icon: str = "⚖", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try: fn(title, icon, getattr(self.C, "GREEN", ""), subtitle); return
            except TypeError:
                try: fn(title, icon, getattr(self.C, "GREEN", ""))
                except Exception: pass
        print(self.color(f"\n{'═' * 76}\n  {icon} {title}\n{'═' * 76}", "GREEN", True))
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
            for i, value in enumerate(clean[:len(widths)]): widths[i] = min(32, max(widths[i], len(value)))
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
            answer = input(prompt).strip().upper()
            if answer in valid: return answer
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


GOODS_LABELS = {
    "purple": "тирский пурпур", "incense": "благовония", "silver": "серебро",
    "horses": "лошади", "leather": "кожа", "livestock": "скот",
    "papyrus": "папирус", "marble": "мрамор", "wine": "вино",
    "spices": "специи", "silk": "шёлк", "wheat": "пшеница", "linen": "лён",
    "iron": "железо", "amber": "янтарь",
}


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    state = getattr(player, "diplomatic_trade", None)
    if not isinstance(state, dict): state = {}; player.diplomatic_trade = state
    state.setdefault("schema", SCHEMA_VERSION); state.setdefault("version", MODULE_VERSION)
    state.setdefault("contracts", []); state.setdefault("history", []); state.setdefault("next_offer_turn", {})
    state.setdefault("last_tick_turn", 0); state.setdefault("merchant_reputation", 50)
    contracts = []
    for c in _list(state.get("contracts")):
        if not isinstance(c, dict): continue
        c.setdefault("id", uuid.uuid4().hex[:10]); c.setdefault("power", "")
        c.setdefault("direction", "import"); c.setdefault("resource", "wheat")
        c.setdefault("amount", 4.0); c.setdefault("price", 15); c.setdefault("duration", 6)
        c.setdefault("remaining", c["duration"]); c.setdefault("status", "active")
        c.setdefault("arrears", 0); c.setdefault("created_turn", _i(getattr(player, "turn", 1), 1))
        c.setdefault("bonus", ""); c.setdefault("exclusive", True)
        c["amount"] = max(0.1, _f(c.get("amount", 4), 4)); c["price"] = _i(c.get("price", 15), 15, 0)
        c["duration"] = _i(c.get("duration", 6), 6, 1, 40); c["remaining"] = _i(c.get("remaining", c["duration"]), c["duration"], 0, 40)
        c["arrears"] = _i(c.get("arrears", 0), 0, 0, 20)
        if c.get("status") in ("active", "suspended"): contracts.append(c)
    state["contracts"] = contracts[-40:]
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state["next_offer_turn"] = {str(k): _i(v, 1, 1) for k, v in _dict(state.get("next_offer_turn")).items()}
    state["last_tick_turn"] = _i(state.get("last_tick_turn", 0), 0, 0)
    state["merchant_reputation"] = _clamp(state.get("merchant_reputation", 50), 0, 100, 50)
    state["schema"] = SCHEMA_VERSION; state["version"] = MODULE_VERSION
    player.diplomatic_trade = state
    return state


def _record(player: Any, ctx: dict, title: str, text: str, power: str | None = None, tone: str = "info") -> None:
    state = ensure_state(player, ctx)
    item = {"turn": _i(getattr(player, "turn", 1), 1), "title": title, "text": text, "power": power, "tone": tone}
    state["history"].append(item); state["history"] = state["history"][-MAX_HISTORY:]
    log = ctx.get("log_event")
    if callable(log):
        try: log(player, f"{title}: {text}")
        except Exception: pass
    annales = ctx.get("ANNALES")
    if annales is not None and hasattr(annales, "record_event"):
        try: annales.record_event(player, category="economy", title=title, text=text, reason="Международная торговая дипломатия.", severity=2, data={"power": power, "system": "mercatura_gentium"})
        except Exception: pass


def _nation(ctx: dict, key: str) -> dict:
    module = ctx.get("NATIONS")
    if module is not None and hasattr(module, "get_nation"):
        try: return module.get_nation(key)
        except Exception: pass
    return {"name": key, "exclusive_goods": ["wheat"], "trade_bonus": "торговые выгоды"}


def _add_resource(player: Any, ctx: dict, resource: str, amount: float) -> None:
    module = ctx.get("NATIONS")
    if module is not None and hasattr(module, "add_resource"):
        module.add_resource(player, ctx, resource, amount)
    elif resource == "wheat": player.grain = _i(getattr(player, "grain", 0), 0) + int(round(amount * 3))
    else: player.gold = _i(getattr(player, "gold", 0), 0) + int(round(amount))


def _remove_resource(player: Any, ctx: dict, resource: str, amount: float) -> bool:
    module = ctx.get("NATIONS")
    if module is not None and hasattr(module, "remove_resource"):
        try: return bool(module.remove_resource(player, ctx, resource, amount))
        except Exception: return False
    return False


def _world_enqueue(player: Any, ctx: dict, **kwargs: Any) -> bool:
    council = ctx.get("WORLD_COUNCIL")
    if council is None or not hasattr(council, "enqueue"): return False
    return council.enqueue(player, ctx=ctx, **kwargs) is not None


def _power_state(player: Any, key: str) -> tuple[dict, dict]:
    row = _dict(_dict(getattr(player, "diplomacy", {})).get(key))
    ai = _dict(_dict(getattr(player, "diplomatic_ai", {})).get("powers", {})).get(key, {})
    return row, _dict(ai)


def _base_terms(player: Any, key: str, ctx: dict) -> dict:
    nation = _nation(ctx, key); row, ai = _power_state(player, key)
    goods = _list(nation.get("exclusive_goods")) or ["wheat"]
    resource = random.choice(goods)
    trade_drive = _i(ai.get("trade_drive", 55), 55, 0, 100)
    disposition = _i(row.get("disposition", 50), 50, 0, 100)
    trust = _i(row.get("trust", 40), 40, 0, 100)
    amount = round(2.5 + trade_drive / 25 + random.uniform(-0.5, 1.4), 1)
    base_price = {"purple": 25, "incense": 18, "silver": 22, "horses": 18, "leather": 12, "livestock": 11,
                  "papyrus": 14, "marble": 17, "wine": 11, "spices": 22, "silk": 28, "wheat": 12, "linen": 11,
                  "iron": 17, "amber": 18}.get(resource, 15)
    price = max(3, int(round(base_price * amount / 3.5 * (1.12 - disposition / 300 - trust / 500))))
    duration = random.randint(5, 9)
    return {
        "resource": resource, "amount": amount, "price": price, "duration": duration,
        "direction": "import", "bonus": str(nation.get("trade_bonus", "")), "exclusive": True,
    }


def propose_contract(player: Any, power_key: str, ctx: dict | None = None, forced: bool = False) -> bool:
    ctx = _ctx(ctx); state = ensure_state(player, ctx)
    nation = _nation(ctx, power_key); row, ai = _power_state(player, power_key)
    if not row or row.get("at_war") or row.get("client") and row.get("tribute", 0) < 0: return False
    active_for_power = [c for c in state.get("contracts", []) if c.get("power") == power_key and c.get("status") in ("active", "suspended")]
    if len(active_for_power) >= 2:
        return False
    council = ctx.get("WORLD_COUNCIL")
    if council is not None and hasattr(council, "has_pending"):
        try:
            if council.has_pending(player, "trade.offer", power_key): return False
        except Exception: pass
    if not forced:
        if _i(row.get("tension", 30), 30) >= 75 or _i(row.get("disposition", 50), 50) < 28: return False
        chance = 0.10 + _i(ai.get("trade_drive", 50), 50) / 500 + (0.08 if row.get("trade_pact") else 0)
        if random.random() >= chance: return False
    terms = _base_terms(player, power_key, ctx)
    text = f"{nation.get('name', power_key)} предлагает долгосрочный контракт на {GOODS_LABELS.get(terms['resource'], terms['resource'])}."
    queued = _world_enqueue(
        player, ctx,
        event_type="trade.offer", title=f"Торговое посольство: {nation.get('name', power_key)}",
        summary=text, payload={"terms": terms}, power=power_key, severity=3, expires_in=5,
        dedupe=f"trade.offer:{power_key}",
    )
    if queued:
        state["next_offer_turn"][power_key] = _i(getattr(player, "turn", 1), 1) + random.randint(5, 9)
    return queued


def _activate_contract(player: Any, ctx: dict, key: str, terms: dict) -> dict:
    state = ensure_state(player, ctx)
    contract = {
        "id": uuid.uuid4().hex[:10], "power": key, "direction": terms.get("direction", "import"),
        "resource": str(terms.get("resource", "wheat")), "amount": max(0.1, _f(terms.get("amount", 4), 4)),
        "price": _i(terms.get("price", 15), 15, 0), "duration": _i(terms.get("duration", 6), 6, 1, 40),
        "remaining": _i(terms.get("duration", 6), 6, 1, 40), "status": "active", "arrears": 0,
        "created_turn": _i(getattr(player, "turn", 1), 1), "bonus": str(terms.get("bonus", "")),
        "exclusive": bool(terms.get("exclusive", True)),
    }
    state["contracts"].append(contract)
    row = _dict(getattr(player, "diplomacy", {}).get(key))
    row["trade_pact"] = True; row["trade_pact_turn"] = _i(getattr(player, "turn", 1), 1)
    row["disposition"] = _clamp(row.get("disposition", 50) + 6, 0, 100, 50)
    row["trust"] = _clamp(row.get("trust", 40) + 5, 0, 100, 40)
    return contract


def _apply_contract(player: Any, ctx: dict, contract: dict) -> None:
    key = contract["power"]; row = _dict(getattr(player, "diplomacy", {}).get(key))
    if row.get("at_war"):
        contract["status"] = "suspended"; return
    resource = contract["resource"]; amount = _f(contract["amount"], 4); price = _i(contract["price"], 15)
    if contract.get("direction") == "import":
        if _i(getattr(player, "gold", 0), 0) >= price:
            player.gold -= price; _add_resource(player, ctx, resource, amount)
            contract["arrears"] = 0; contract["status"] = "active"
        else:
            contract["arrears"] = _i(contract.get("arrears", 0), 0) + 1
            contract["status"] = "suspended"
    else:
        if _remove_resource(player, ctx, resource, amount):
            player.gold = _i(getattr(player, "gold", 0), 0) + price
            contract["arrears"] = 0; contract["status"] = "active"
        else:
            contract["arrears"] = _i(contract.get("arrears", 0), 0) + 1; contract["status"] = "suspended"
    contract["remaining"] = max(0, _i(contract.get("remaining", 0), 0) - 1)


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx); state = ensure_state(player, ctx); turn = _i(getattr(player, "turn", 1), 1)
    if state.get("last_tick_turn") >= turn: return state
    state["last_tick_turn"] = turn
    ended = []
    for contract in list(state["contracts"]):
        _apply_contract(player, ctx, contract)
        if contract.get("arrears", 0) >= 2:
            _world_enqueue(player, ctx, event_type="trade.dispute", title="Торговый спор и просрочка",
                           summary="Иностранные купцы требуют погасить обязательства или пересмотреть договор.",
                           payload={"contract_id": contract["id"]}, power=contract["power"], severity=4,
                           expires_in=3, dedupe=f"trade.dispute:{contract['id']}")
        if contract.get("remaining", 0) <= 0:
            ended.append(contract)
            _world_enqueue(player, ctx, event_type="trade.renewal", title="Истечение торгового договора",
                           summary="Срок эксклюзивного контракта истёк; послы предлагают решить его судьбу.",
                           payload={"contract": copy.deepcopy(contract)}, power=contract["power"], severity=2,
                           expires_in=4, dedupe=f"trade.renewal:{contract['id']}")
    for c in ended:
        if c in state["contracts"]: state["contracts"].remove(c)
    diplomacy = _dict(getattr(player, "diplomacy", {}))
    for key, row in diplomacy.items():
        if not isinstance(row, dict): continue
        next_turn = state["next_offer_turn"].get(key, 2 + (abs(hash(key)) % 4))
        if turn >= next_turn: propose_contract(player, str(key), ctx, forced=False)
    return state


def _contract_by_id(state: dict, contract_id: str) -> dict | None:
    return next((c for c in state["contracts"] if c.get("id") == contract_id), None)


def _terms_text(terms: dict) -> str:
    direction = "Рим получает" if terms.get("direction", "import") == "import" else "Рим поставляет"
    return f"{direction} {terms.get('amount')} ед. товара «{GOODS_LABELS.get(terms.get('resource'), terms.get('resource'))}» за {terms.get('price')} золота каждый ход в течение {terms.get('duration')} ходов."


def _offer_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    key = str(event.get("power")); nation = _nation(ctx, key); terms = _dict(event.get("payload", {}).get("terms"))
    row, ai = _power_state(player, key)
    ui.screen(); ui.header(event.get("title", "ТОРГОВОЕ ПОСОЛЬСТВО"), "⚖", "I. Прибытие послов")
    ui.wrap(f"Посольство державы {nation.get('name', key)} прибыло с охраной, образцами товара и полномочиями заключить не разовую куплю, а долговременный государственный договор.")
    ui.info(f"Отношение: {row.get('disposition', 0)}; доверие: {row.get('trust', 0)}; торговый интерес: {ai.get('trade_drive', 50)}.", "CYAN")
    ui.pause("Выслушать предложение...")

    ui.screen(); ui.header("УСЛОВИЯ КОНТРАКТА", "📜", "II. Счёт купцов и заключение казначеев")
    ui.wrap(_terms_text(terms), "WHITE")
    ui.wrap(str(terms.get("bonus", "")), "GREEN")
    ui.info(f"Казна Рима: {_i(getattr(player, 'gold', 0), 0)} золота.", "GOLD")
    ui.pause("Созвать узкий совет...")

    ui.screen(); ui.header("CONSILIUM MERCATORUM", "🏛", "III. Политическое обсуждение")
    ui.wrap("Казначеи оценивают цену и устойчивость поставок; военные — стратегическую ценность товара; дипломаты предупреждают, что отказ или жёсткий торг останутся в памяти иностранного двора.")
    print("  A. Принять предложенные условия")
    print("  C. Выдвинуть встречные условия")
    print("  R. Отказать")
    print("  P. Отложить решение")
    choice = ui.choice("\n  Решение: ", ["A", "C", "R", "P"])
    if choice == "P": return False
    if choice == "R":
        row["disposition"] = _clamp(row.get("disposition", 50) - 3, 0, 100, 50)
        _record(player, ctx, "Торговое предложение отклонено", f"Рим отказал державе {nation.get('name', key)}.", key, "bad")
        ui.info("Послы покидают Рим без договора.", "RED"); ui.pause(); return True
    if choice == "C":
        ui.screen(); ui.header("ВСТРЕЧНОЕ ПРЕДЛОЖЕНИЕ", "🧾", "IV. Римская редакция условий")
        print("  1. Снизить цену на 20%")
        print("  2. Увеличить объём на 25% при той же цене")
        print("  3. Сократить срок до 4 ходов")
        counter = ui.choice("\n  Требование: ", ["1", "2", "3"])
        modified = copy.deepcopy(terms)
        if counter == "1": modified["price"] = max(1, int(round(modified["price"] * 0.8)))
        elif counter == "2": modified["amount"] = round(modified["amount"] * 1.25, 1)
        else: modified["duration"] = min(4, modified["duration"])
        acceptance = 0.30 + _i(row.get("disposition", 50), 50) / 250 + _i(row.get("trust", 40), 40) / 300 + _i(ai.get("trade_drive", 50), 50) / 400
        acceptance -= 0.08 if _i(row.get("tension", 30), 30) > 55 else 0
        ui.pause("Послы передают условия своему полномочному совету...")
        ui.screen(); ui.header("ОТВЕТ ИНОСТРАННОГО ДВОРА", "📨", "V. Завершение торга")
        if random.random() < acceptance:
            terms = modified; ui.wrap(f"{nation.get('name', key)} принимает римскую редакцию. {_terms_text(terms)}", "GREEN")
            row["trust"] = _clamp(row.get("trust", 40) + 2, 0, 100, 40)
        else:
            ui.wrap("Встречные условия отвергнуты. Послы готовы подписать первоначальный текст либо уехать ни с чем.", "RED")
            final = ui.choice("  Принять первоначальные условия? (Y/N): ", ["Y", "N"])
            if final == "N":
                row["disposition"] = _clamp(row.get("disposition", 50) - 2, 0, 100, 50)
                _record(player, ctx, "Торговые переговоры сорваны", f"Рим и {nation.get('name', key)} не согласовали цену.", key, "bad")
                ui.pause(); return True
    contract = _activate_contract(player, ctx, key, terms)
    ui.screen(); ui.header("FOEDUS MERCATORIUM", "✅", "VI. Ратификация")
    ui.wrap(f"Договор заключён. {_terms_text(contract)}", "GREEN")
    ui.wrap(str(contract.get("bonus", "")), "CYAN")
    _record(player, ctx, "Заключён международный контракт", f"{nation.get('name', key)}: {_terms_text(contract)}", key, "good")
    ui.pause(); return True


def _dispute_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    state = ensure_state(player, ctx); cid = str(event.get("payload", {}).get("contract_id", "")); contract = _contract_by_id(state, cid)
    if not contract: return True
    key = contract["power"]; nation = _nation(ctx, key); row, _ = _power_state(player, key)
    debt = contract["price"] * max(1, contract.get("arrears", 1))
    ui.screen(); ui.header("ТОРГОВЫЙ СПОР", "⚠", "I. Претензия иностранной фактории")
    ui.wrap(f"Купцы державы {nation.get('name', key)} заявляют о {contract.get('arrears')} пропущенных платежах. Требование: {debt} золота либо новая редакция договора.")
    ui.pause("Выслушать казначеев...")
    ui.screen(); ui.header("РАЗБОР ОБЯЗАТЕЛЬСТВ", "🏛", "II. Решение")
    print("  P. Немедленно погасить долг")
    print("  R. Реструктурировать: уменьшить объём и цену")
    print("  B. Разорвать договор")
    print("  D. Отложить")
    ch = ui.choice("\n  Решение: ", ["P", "R", "B", "D"])
    if ch == "D": return False
    if ch == "P":
        if _i(getattr(player, "gold", 0), 0) < debt:
            ui.info("В казне недостаточно золота. Решение отложено.", "RED"); ui.pause(); return False
        player.gold -= debt; contract["arrears"] = 0; contract["status"] = "active"
        row["trust"] = _clamp(row.get("trust", 40) + 2, 0, 100, 40)
        _record(player, ctx, "Торговый долг погашен", f"Рим выплатил {debt} золота державе {nation.get('name', key)}.", key, "good")
    elif ch == "R":
        contract["amount"] = round(contract["amount"] * 0.65, 1); contract["price"] = max(1, int(round(contract["price"] * 0.7)))
        contract["arrears"] = 0; contract["status"] = "active"; row["trust"] = _clamp(row.get("trust", 40) - 2, 0, 100, 40)
        _record(player, ctx, "Контракт реструктурирован", f"Объём торговли с {nation.get('name', key)} сокращён.", key)
    else:
        state["contracts"].remove(contract); row["trade_pact"] = False; row["disposition"] = _clamp(row.get("disposition", 50) - 8, 0, 100, 50); row["tension"] = _clamp(row.get("tension", 30) + 7, 0, 100, 30)
        _record(player, ctx, "Торговый договор разорван", f"Рим отказался от обязательств перед державой {nation.get('name', key)}.", key, "bad")
    ui.info("Решение занесено в акты торгового совета.", "GREEN"); ui.pause(); return True


def _renewal_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    old = _dict(event.get("payload", {}).get("contract")); key = str(event.get("power")); nation = _nation(ctx, key)
    ui.screen(); ui.header("ПРОДЛЕНИЕ ДОГОВОРА", "🔁", "I. Итоги завершённого контракта")
    ui.wrap(f"Контракт с державой {nation.get('name', key)} завершён. Предмет: {GOODS_LABELS.get(old.get('resource'), old.get('resource'))}; прежняя цена {old.get('price')} золота за ход.")
    ui.pause("Перейти к переговорам...")
    terms = copy.deepcopy(old); terms["duration"] = random.randint(5, 8); terms["price"] = max(1, int(round(_i(old.get("price", 15), 15) * random.uniform(0.92, 1.12))))
    ui.screen(); ui.header("НОВАЯ РЕДАКЦИЯ", "📜", "II. Решение")
    ui.wrap(_terms_text(terms))
    ch = ui.choice("  Продлить договор? (Y/N/P — отложить): ", ["Y", "N", "P"])
    if ch == "P": return False
    if ch == "Y":
        _activate_contract(player, ctx, key, terms); _record(player, ctx, "Торговый договор продлён", f"Контракт с {nation.get('name', key)} возобновлён.", key, "good")
    else:
        _record(player, ctx, "Торговый договор завершён", f"Рим не стал продлевать контракт с {nation.get('name', key)}.", key)
    ui.pause(); return True


def handle_council_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    etype = str(event.get("type", ""))
    if etype == "trade.offer": return _offer_event(player, event, ctx, ui)
    if etype == "trade.dispute": return _dispute_event(player, event, ctx, ui)
    if etype == "trade.renewal": return _renewal_event(player, event, ctx, ui)
    return True


def expire_council_event(player: Any, event: dict, ctx: dict) -> None:
    key = str(event.get("power") or ""); row, _ = _power_state(player, key)
    if event.get("type") == "trade.offer":
        row["disposition"] = _clamp(row.get("disposition", 50) - 2, 0, 100, 50)
        _record(player, ctx, "Посольство осталось без ответа", "Рим не рассмотрел торговое предложение в установленный срок.", key, "bad")
    elif event.get("type") == "trade.dispute":
        row["trust"] = _clamp(row.get("trust", 40) - 8, 0, 100, 40); row["tension"] = _clamp(row.get("tension", 30) + 8, 0, 100, 30)


def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx); ui = UI(ctx); state = ensure_state(player, ctx)
    while True:
        ui.screen(); ui.header("MERCATURA GENTIUM", "⚖", f"Государственная внешняя торговля — {MODULE_VERSION}")
        contracts = state.get("contracts", [])
        if contracts:
            ui.table("Действующие контракты", ["Держава", "Товар", "Объём", "Цена", "Ост.", "Статус"], [
                (_nation(ctx, c["power"]).get("name", c["power"]), GOODS_LABELS.get(c["resource"], c["resource"]), c["amount"], c["price"], c["remaining"], c["status"]) for c in contracts
            ], "GREEN")
        else: ui.info("Долгосрочных международных контрактов нет.", "GRAY")
        ui.section("Действия", "GOLD")
        print("  1. Направить торговое посольство")
        print("  2. Архив торговли")
        print("  Q. Назад")
        ch = ui.choice("\n  Выбор: ", ["1", "2", "Q"])
        if ch == "Q": return
        if ch == "1":
            keys = list(_dict(getattr(player, "diplomacy", {})))
            ui.screen(); ui.header("ТОРГОВОЕ ПОСОЛЬСТВО", "📨")
            for i, key in enumerate(keys, 1): print(f"  {i}. {_nation(ctx, key).get('name', key)}")
            s = ui.choice("\n  Держава (или Q): ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
            if s != "Q":
                key = keys[int(s) - 1]
                if propose_contract(player, key, ctx, forced=True): ui.info("Посольство созвано; предложение будет рассмотрено в Consilium Orbis.", "GREEN")
                else: ui.info("Сейчас переговоры невозможны или аналогичное дело уже ожидает решения.", "RED")
                ui.pause()
        elif ch == "2":
            ui.screen(); ui.header("ТАБУЛЯРИЙ ТОРГОВЛИ", "📜")
            if state["history"]:
                ui.table("Последние записи", ["Ход", "Держава", "Событие", "Содержание"], [(h.get("turn"), _nation(ctx, h.get("power", "")).get("name", h.get("power") or "—"), h.get("title"), h.get("text")) for h in reversed(state["history"][-40:])], "CYAN")
            else: ui.info("Архив пуст.", "GRAY")
            ui.pause()


# ─── RES PUBLICA ORBIS COMPATIBILITY ROUTE ────────────────────────────────
# Старые прямые входы оставлены для сторонних модов и старых горячих клавиш,
# но в актуальной сборке ведут в соответствующий раздел единого центра.
_legacy_open_menu_before_world_politics = open_menu

def open_menu(player: Any, ctx: dict | None = None) -> None:
    context = _ctx(ctx)
    facade = context.get("WORLD_POLITICS")
    if facade is not None and hasattr(facade, "open_menu"):
        facade.open_menu(player, context, start_section="trade")
        return
    return _legacy_open_menu_before_world_politics(player, context)
