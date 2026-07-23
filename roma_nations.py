#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna — GENTES ET REGNA.

Каталог полноценных иностранных цивилизаций. Модуль хранит уникальные
особенности держав, национальные войска, эксклюзивные товары и пассивные
бонусы, которые Рим получает только через торговлю, союз, династический брак
или подчинение конкретной страны.

Публичный контракт:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None)
    get_nation(key)
    get_roster(key)
    get_modifier(player, name, default=0)
    open_menu(player, ctx=None)
"""
from __future__ import annotations

import copy
import random
import re
import textwrap
from typing import Any

MODULE_VERSION = "1.0.0-gentes-regna"
SCHEMA_VERSION = 1


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

    def header(self, title: str, icon: str = "🦅", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try:
                fn(title, icon, getattr(self.C, "GOLD", ""), subtitle); return
            except TypeError:
                try: fn(title, icon, getattr(self.C, "GOLD", ""))
                except Exception: pass
        print(self.color(f"\n{'═' * 76}\n  {icon} {title}\n{'═' * 76}", "GOLD", True))
        if subtitle: self.wrap(subtitle, "GRAY")

    def section(self, title: str, color: str = "CYAN") -> None:
        fn = self.ctx.get("rui_section")
        if callable(fn) and self.C is not None:
            try: fn(title, getattr(self.C, color, "")); return
            except Exception: pass
        print(self.color(f"\n  ── {title} ──", color, True))

    def wrap(self, text: Any, color: str = "WHITE") -> None:
        fn = self.ctx.get("ui_wrap")
        if callable(fn) and self.C is not None:
            try: fn(str(text), color=getattr(self.C, color, "")); return
            except Exception: pass
        for line in textwrap.wrap(str(text), width=76, break_long_words=False):
            print(self.color("  " + line, color))

    def table(self, title: str, headers: list[str], rows: list[tuple], color: str = "CYAN") -> None:
        fn = self.ctx.get("rui_table")
        if callable(fn) and self.C is not None:
            try: fn(title, headers, rows, color=getattr(self.C, color, "")); return
            except Exception: pass
        self.section(title, color)
        widths = [len(_plain(h)) for h in headers]
        clean_rows: list[list[str]] = []
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
            value = input(prompt).strip().upper()
            if value in valid: return value
            print("  Допустимо: " + ", ".join(valid))

    def pause(self) -> None:
        fn = self.ctx.get("rui_pause") or self.ctx.get("pause")
        if callable(fn):
            try: fn(); return
            except Exception: pass
        input("\n  Нажмите Enter, чтобы продолжить...")


NATIONS: dict[str, dict[str, Any]] = {
    "carthage": {
        "name": "Карфаген", "demonym": "пунийцы", "government": "торговая олигархия",
        "capital": "Карфаген", "color": "PURPLE", "icon": "⛵",
        "identity": "Талассократия купцов, верфей и наёмных армий.",
        "war_doctrine": "Морская блокада, наёмники, обходы и истощение казны противника.",
        "exclusive_goods": ["purple", "incense", "silver"],
        "trade_bonus": "Пунические фактории: +8 золота и пурпур по действующему договору.",
        "alliance_bonus": "Морские проводники: +12% к силе Рима в прибрежных операциях.",
        "marriage_bonus": "Связи Совета ста четырёх: дипломатический капитал и дешёвые контракты.",
        "client_bonus": "Пунические гавани: постоянный доход с западного моря.",
        "modifiers": {"naval_combat": 12, "trade_price": -10, "blockade": 18},
        "units": [
            {"id": "sacred_band", "name": "Священный отряд", "class": "тяжёлая пехота", "attack": 18, "defense": 19, "mobility": 5, "cost": 18, "trait": "не отступает при высокой морали"},
            {"id": "liby_phoenician", "name": "Ливийско-финикийская пехота", "class": "линейная пехота", "attack": 14, "defense": 15, "mobility": 6, "cost": 11, "trait": "строй и дисциплина"},
            {"id": "numidian_horse", "name": "Нумидийские всадники", "class": "лёгкая конница", "attack": 13, "defense": 7, "mobility": 20, "cost": 10, "trait": "изматывающие налёты"},
            {"id": "war_elephants", "name": "Боевые слоны", "class": "ударные звери", "attack": 22, "defense": 9, "mobility": 7, "cost": 22, "trait": "шок против пехоты"},
            {"id": "quinquereme", "name": "Пуническая квинкверема", "class": "флот", "attack": 20, "defense": 17, "mobility": 15, "cost": 20, "trait": "морское превосходство"},
        ],
    },
    "numidia": {
        "name": "Нумидия", "demonym": "нумидийцы", "government": "конное царство",
        "capital": "Цирта", "color": "GOLD", "icon": "🐎",
        "identity": "Подвижная монархия всадников, пастбищ и пустынных путей.",
        "war_doctrine": "Налёты, ложные отступления, разведка и отказ от тяжёлых осад.",
        "exclusive_goods": ["horses", "leather", "livestock"],
        "trade_bonus": "Царские табуны: регулярные поставки лошадей и кожи.",
        "alliance_bonus": "Пустынные проводники: меньше потерь от рейдов и выше мобильность.",
        "marriage_bonus": "Связь с царским домом: лояльность африканских провинций.",
        "client_bonus": "Нумидийская конница поступает в римскую ауксилию.",
        "modifiers": {"cavalry_combat": 18, "raid": 16, "pursuit": 14},
        "units": [
            {"id": "numidian_riders", "name": "Нумидийские всадники", "class": "лёгкая конница", "attack": 15, "defense": 7, "mobility": 23, "cost": 9, "trait": "круговой обстрел"},
            {"id": "royal_guard", "name": "Царская конная дружина", "class": "ударная конница", "attack": 19, "defense": 13, "mobility": 18, "cost": 17, "trait": "решающая погоня"},
            {"id": "desert_scouts", "name": "Пустынные разведчики", "class": "разведка", "attack": 9, "defense": 8, "mobility": 25, "cost": 7, "trait": "засады и разведка"},
            {"id": "tribal_spears", "name": "Племенные копейщики", "class": "лёгкая пехота", "attack": 10, "defense": 12, "mobility": 10, "cost": 7, "trait": "дешёвое ополчение"},
        ],
    },
    "pergamon": {
        "name": "Пергам", "demonym": "пергамцы", "government": "эллинистическая монархия",
        "capital": "Пергам", "color": "CYAN", "icon": "📚",
        "identity": "Учёная бюрократическая держава библиотек, мастерских и дипломатии.",
        "war_doctrine": "Дисциплинированная фаланга, инженеры, крепости и осторожная коалиционная война.",
        "exclusive_goods": ["papyrus", "marble", "wine"],
        "trade_bonus": "Пергамские книги и врачи: наука и здоровье городов.",
        "alliance_bonus": "Эллинистические инженеры: усиление осад и укреплений.",
        "marriage_bonus": "Царский культурный патронаж: наука и репутация в Сенате.",
        "client_bonus": "Библиотечная сеть: постоянный прирост науки.",
        "modifiers": {"siege": 14, "fortification": 15, "science": 18},
        "units": [
            {"id": "pergamene_phalanx", "name": "Пергамская фаланга", "class": "сариссофоры", "attack": 16, "defense": 20, "mobility": 4, "cost": 14, "trait": "непробиваемый фронт"},
            {"id": "galatian_guard", "name": "Галатская царская гвардия", "class": "тяжёлая пехота", "attack": 19, "defense": 15, "mobility": 8, "cost": 17, "trait": "контрудар"},
            {"id": "royal_engineers", "name": "Царские инженеры", "class": "осадные части", "attack": 13, "defense": 12, "mobility": 5, "cost": 16, "trait": "ломает укрепления"},
            {"id": "asian_cavalry", "name": "Малоазийская конница", "class": "средняя конница", "attack": 14, "defense": 11, "mobility": 15, "cost": 12, "trait": "прикрытие флангов"},
        ],
    },
    "parthia": {
        "name": "Парфия", "demonym": "парфяне", "government": "аристократическая конная держава",
        "capital": "Гекатомпил", "color": "RED", "icon": "🏹",
        "identity": "Империя домов, степных путей, конных лучников и закованных всадников.",
        "war_doctrine": "Стратегическая глубина, притворное отступление, окружение и уничтожение коммуникаций.",
        "exclusive_goods": ["horses", "spices", "silk"],
        "trade_bonus": "Восточные караваны: специи, шёлк и рост торгового дохода.",
        "alliance_bonus": "Парфянские инструкторы: усиление конницы и преследования.",
        "marriage_bonus": "Связь с домом Аршакидов: престиж и влияние на Востоке.",
        "client_bonus": "Великий шёлковый путь: большой караванный доход.",
        "modifiers": {"cavalry_combat": 22, "feigned_retreat": 20, "eastern_trade": 20},
        "units": [
            {"id": "horse_archers", "name": "Конные лучники", "class": "стрелковая конница", "attack": 17, "defense": 8, "mobility": 23, "cost": 12, "trait": "парфянский выстрел"},
            {"id": "cataphracts", "name": "Катафракты", "class": "сверхтяжёлая конница", "attack": 24, "defense": 19, "mobility": 13, "cost": 24, "trait": "сокрушительный таран"},
            {"id": "noble_retinue", "name": "Дружина азатов", "class": "тяжёлая конница", "attack": 20, "defense": 16, "mobility": 16, "cost": 19, "trait": "высокая стойкость"},
            {"id": "eastern_spears", "name": "Восточные копейщики", "class": "гарнизон", "attack": 10, "defense": 15, "mobility": 7, "cost": 8, "trait": "удерживает города"},
        ],
    },
    "egypt": {
        "name": "Египет", "demonym": "египтяне", "government": "дворцовая монархия",
        "capital": "Александрия", "color": "BLUE", "icon": "🌾",
        "identity": "Нильская житница, храмовая экономика, двор и крупнейшие города Востока.",
        "war_doctrine": "Оборона дельты, флот, наёмники и затяжная война за счёт огромного продовольствия.",
        "exclusive_goods": ["wheat", "papyrus", "linen"],
        "trade_bonus": "Нильские поставки: крупный приток зерна и папируса.",
        "alliance_bonus": "Александрийские мастера: здоровье городов и морская логистика.",
        "marriage_bonus": "Птолемеевский двор: легитимность, зерно и международный престиж.",
        "client_bonus": "Аннона Египта: гарантированный продовольственный резерв.",
        "modifiers": {"grain_supply": 24, "naval_combat": 8, "urban_health": 15},
        "units": [
            {"id": "machimoi", "name": "Махимои", "class": "египетская пехота", "attack": 13, "defense": 15, "mobility": 7, "cost": 10, "trait": "стойкость на своей земле"},
            {"id": "cleruch_cavalry", "name": "Клерухическая конница", "class": "средняя конница", "attack": 15, "defense": 12, "mobility": 15, "cost": 13, "trait": "землевладельческая элита"},
            {"id": "agema", "name": "Царская агема", "class": "гвардия", "attack": 20, "defense": 19, "mobility": 8, "cost": 20, "trait": "дворцовая дисциплина"},
            {"id": "nile_fleet", "name": "Нильская эскадра", "class": "флот", "attack": 16, "defense": 18, "mobility": 13, "cost": 16, "trait": "оборона дельты"},
        ],
    },
    "gauls": {
        "name": "Галльская конфедерация", "demonym": "галлы", "government": "союз племён",
        "capital": "Бибракте", "color": "GREEN", "icon": "🐗",
        "identity": "Союз общин, знати, друидов и военных дружин, способный внезапно объединиться.",
        "war_doctrine": "Засады, стремительный натиск, массовое ополчение и война за славу вождей.",
        "exclusive_goods": ["iron", "wine", "amber"],
        "trade_bonus": "Галльские кузницы: железо, вино и дешёвое вооружение.",
        "alliance_bonus": "Племенные проводники: преимущество в лесах и против засад.",
        "marriage_bonus": "Союз с домом вождя: меньше волнений в Галлии и больше народной поддержки.",
        "client_bonus": "Галльские дружины пополняют ауксилию и гарнизоны.",
        "modifiers": {"forest_combat": 20, "levy_recovery": 18, "ambush": 16},
        "units": [
            {"id": "gaesatae", "name": "Гезаты", "class": "ударные мечники", "attack": 21, "defense": 10, "mobility": 12, "cost": 14, "trait": "яростный первый натиск"},
            {"id": "noble_cavalry", "name": "Конница знати", "class": "тяжёлая конница", "attack": 18, "defense": 14, "mobility": 16, "cost": 16, "trait": "вождеская дружина"},
            {"id": "tribal_swords", "name": "Племенные мечники", "class": "массовая пехота", "attack": 15, "defense": 11, "mobility": 10, "cost": 8, "trait": "быстрое пополнение"},
            {"id": "druidic_guard", "name": "Стража друидов", "class": "элита", "attack": 16, "defense": 17, "mobility": 9, "cost": 15, "trait": "поднимает мораль"},
            {"id": "war_chariots", "name": "Боевые колесницы", "class": "подвижные войска", "attack": 17, "defense": 9, "mobility": 18, "cost": 14, "trait": "сеет беспорядок"},
        ],
    },
}


RESOURCE_FALLBACK = {
    "purple": ("gold", 8), "incense": ("gold", 6), "silver": ("gold", 10),
    "horses": ("morale", 1), "leather": ("gold", 3), "livestock": ("grain", 5),
    "papyrus": ("science", 3), "marble": ("glory", 2), "wine": ("people", 1),
    "spices": ("gold", 7), "silk": ("gold", 9), "wheat": ("grain", 12),
    "linen": ("gold", 3), "iron": ("morale", 1), "amber": ("gold", 5),
}


def get_nation(key: str) -> dict:
    return copy.deepcopy(NATIONS.get(str(key), {}))


def get_roster(key: str) -> list[dict]:
    return copy.deepcopy(_dict(NATIONS.get(str(key), {})).get("units", []))


def unit_by_id(power_key: str, unit_id: str) -> dict:
    return next((copy.deepcopy(u) for u in get_roster(power_key) if u.get("id") == unit_id), {})


def _resource_state(player: Any, ctx: dict) -> dict | None:
    module = ctx.get("RESOURCE_ECONOMY")
    if module is not None and hasattr(module, "ensure_state"):
        try:
            context_fn = ctx.get("resource_economy_context")
            context = context_fn(player) if callable(context_fn) else {}
            return module.ensure_state(player, context)
        except Exception:
            return None
    state = getattr(player, "resource_economy", None)
    return state if isinstance(state, dict) else None


def add_resource(player: Any, ctx: dict | None, resource: str, amount: float) -> float:
    ctx = _ctx(ctx)
    state = _resource_state(player, ctx)
    if state is not None and isinstance(state.get("stockpiles"), dict):
        state["stockpiles"][resource] = max(0.0, float(state["stockpiles"].get(resource, 0.0)) + float(amount))
        return float(amount)
    fallback, value = RESOURCE_FALLBACK.get(resource, ("gold", max(1, int(round(amount)))))
    scaled = max(1, int(round(value * max(0.1, float(amount) / 4.0))))
    if fallback == "gold": player.gold = _i(getattr(player, "gold", 0), 0) + scaled
    elif fallback == "grain": player.grain = _i(getattr(player, "grain", 0), 0) + scaled
    elif fallback == "science": player.science_points = _i(getattr(player, "science_points", 0), 0) + scaled
    elif fallback == "glory": player.glory = _i(getattr(player, "glory", 0), 0) + scaled
    elif fallback == "people": player.people_rep = _clamp(getattr(player, "people_rep", 50) + scaled, 0, 100, 50)
    elif fallback == "morale": player.morale = _clamp(getattr(player, "morale", 70) + scaled, 0, 120, 70)
    return float(amount)


def remove_resource(player: Any, ctx: dict | None, resource: str, amount: float) -> bool:
    ctx = _ctx(ctx)
    state = _resource_state(player, ctx)
    if state is not None and isinstance(state.get("stockpiles"), dict):
        stock = float(state["stockpiles"].get(resource, 0.0))
        if stock + 1e-9 < amount: return False
        state["stockpiles"][resource] = max(0.0, stock - amount)
        return True
    return False


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    diplomacy = getattr(player, "diplomacy", None)
    if not isinstance(diplomacy, dict):
        diplomacy = {}; player.diplomacy = diplomacy
    state = getattr(player, "nation_system", None)
    if not isinstance(state, dict):
        state = {}; player.nation_system = state
    state.setdefault("schema", SCHEMA_VERSION)
    state.setdefault("version", MODULE_VERSION)
    state.setdefault("powers", {})
    state.setdefault("modifiers", {})
    state.setdefault("history", [])
    state.setdefault("last_tick_turn", 0)
    powers = _dict(state.get("powers"))
    for key, nation in NATIONS.items():
        p = powers.get(key) if isinstance(powers.get(key), dict) else {}
        p.setdefault("known", True)
        p.setdefault("unique_benefits_unlocked", [])
        p.setdefault("trade_turns", 0)
        p.setdefault("alliance_turns", 0)
        p.setdefault("marriage_turns", 0)
        p.setdefault("client_turns", 0)
        p.setdefault("wars_fought", 0)
        p.setdefault("units_encountered", [])
        p["name"] = nation["name"]
        p["unique_benefits_unlocked"] = [str(x) for x in _list(p.get("unique_benefits_unlocked"))][-12:]
        p["units_encountered"] = [str(x) for x in _list(p.get("units_encountered"))][-20:]
        for metric in ("trade_turns", "alliance_turns", "marriage_turns", "client_turns", "wars_fought"):
            p[metric] = _i(p.get(metric, 0), 0, 0)
        powers[key] = p
        diplomacy.setdefault(key, {"name": nation["name"], "disposition": 50, "strength": 5})
    state["powers"] = powers
    state["modifiers"] = _dict(state.get("modifiers"))
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-160:]
    state["last_tick_turn"] = _i(state.get("last_tick_turn", 0), 0, 0)
    state["schema"] = SCHEMA_VERSION
    state["version"] = MODULE_VERSION
    player.nation_system = state
    return state


def _record(player: Any, ctx: dict, key: str, title: str, text: str) -> None:
    state = ensure_state(player, ctx)
    item = {"turn": _i(getattr(player, "turn", 1), 1), "power": key, "title": title, "text": text}
    state["history"].append(item); state["history"] = state["history"][-160:]
    log = ctx.get("log_event")
    if callable(log):
        try: log(player, f"{title}: {text}")
        except Exception: pass
    annales = ctx.get("ANNALES")
    if annales is not None and hasattr(annales, "record_event"):
        try: annales.record_event(player, category="diplomacy", title=title, text=text, reason="Уникальная связь с иностранной державой.", severity=2, data={"power": key, "system": "gentes_regna"})
        except Exception: pass


def _unlock(pstate: dict, benefit: str) -> bool:
    unlocked = pstate.setdefault("unique_benefits_unlocked", [])
    if benefit in unlocked: return False
    unlocked.append(benefit)
    return True


def _rebuild_modifiers(player: Any, state: dict) -> None:
    diplomacy = _dict(getattr(player, "diplomacy", {}))
    totals: dict[str, int] = {}
    sources: dict[str, list[str]] = {}
    for key, nation in NATIONS.items():
        row = _dict(diplomacy.get(key))
        relation_levels: list[tuple[str, float]] = []
        if row.get("trade_pact"): relation_levels.append(("trade", 0.35))
        if row.get("alliance"): relation_levels.append(("alliance", 0.65))
        if row.get("married"): relation_levels.append(("marriage", 0.80))
        if row.get("client"): relation_levels.append(("client", 1.00))
        for relation, factor in relation_levels:
            for name, value in nation.get("modifiers", {}).items():
                gain = int(round(float(value) * factor))
                totals[name] = totals.get(name, 0) + gain
                sources.setdefault(name, []).append(f"{nation['name']} ({relation}) +{gain}")
    state["modifiers"] = totals
    state["modifier_sources"] = sources


def get_modifier(player: Any, name: str, default: int = 0) -> int:
    state = ensure_state(player)
    return _i(_dict(state.get("modifiers")).get(name, default), default)


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 1), 1)
    if state.get("last_tick_turn") >= turn: return state
    state["last_tick_turn"] = turn
    diplomacy = _dict(getattr(player, "diplomacy", {}))
    for key, nation in NATIONS.items():
        row = _dict(diplomacy.get(key))
        pstate = state["powers"][key]
        if row.get("trade_pact"):
            pstate["trade_turns"] += 1
            if key == "carthage":
                player.gold = _i(getattr(player, "gold", 0), 0) + 8; add_resource(player, ctx, "purple", 0.7)
            elif key == "numidia": add_resource(player, ctx, "horses", 1.0); add_resource(player, ctx, "leather", 0.8)
            elif key == "pergamon": player.science_points = _i(getattr(player, "science_points", 0), 0) + 4; add_resource(player, ctx, "papyrus", 0.7)
            elif key == "parthia": player.gold = _i(getattr(player, "gold", 0), 0) + 6; add_resource(player, ctx, "spices", 0.8)
            elif key == "egypt": player.grain = _i(getattr(player, "grain", 0), 0) + 16; add_resource(player, ctx, "papyrus", 0.5)
            elif key == "gauls": add_resource(player, ctx, "iron", 1.0); add_resource(player, ctx, "wine", 0.8)
            if pstate["trade_turns"] == 1 and _unlock(pstate, "trade"):
                _record(player, ctx, key, "Открыт уникальный торговый бонус", nation["trade_bonus"])
        if row.get("alliance"):
            pstate["alliance_turns"] += 1
            if pstate["alliance_turns"] == 1 and _unlock(pstate, "alliance"):
                _record(player, ctx, key, "Открыт союзный бонус", nation["alliance_bonus"])
        if row.get("married"):
            pstate["marriage_turns"] += 1
            if key == "egypt": player.grain = _i(getattr(player, "grain", 0), 0) + 4
            elif key == "pergamon": player.science_points = _i(getattr(player, "science_points", 0), 0) + 2
            elif key == "gauls" and turn % 3 == 0: player.people_rep = _clamp(getattr(player, "people_rep", 50) + 1, 0, 100, 50)
            if pstate["marriage_turns"] == 1 and _unlock(pstate, "marriage"):
                _record(player, ctx, key, "Открыт династический бонус", nation["marriage_bonus"])
        if row.get("client"):
            pstate["client_turns"] += 1
            player.gold = _i(getattr(player, "gold", 0), 0) + (5 if key not in ("carthage", "parthia") else 9)
            if pstate["client_turns"] == 1 and _unlock(pstate, "client"):
                _record(player, ctx, key, "Открыт бонус клиентского царства", nation["client_bonus"])
    _rebuild_modifiers(player, state)
    return state


def _detail(ui: UI, player: Any, key: str) -> None:
    nation = NATIONS[key]; state = ensure_state(player); pstate = state["powers"][key]
    row = _dict(getattr(player, "diplomacy", {}).get(key))
    ui.screen(); ui.header(nation["name"].upper(), nation["icon"], nation["identity"])
    ui.table("Держава", ["Параметр", "Содержание"], [
        ("Столица", nation["capital"]), ("Устройство", nation["government"]),
        ("Военная доктрина", nation["war_doctrine"]),
        ("Отношения", f"отношение {row.get('disposition', 0)}; доверие {row.get('trust', 0)}; напряжение {row.get('tension', 0)}"),
        ("Эксклюзивные товары", ", ".join(nation["exclusive_goods"])),
        ("Торговый бонус", nation["trade_bonus"]), ("Союзный бонус", nation["alliance_bonus"]),
        ("Брачный бонус", nation["marriage_bonus"]), ("Клиентский бонус", nation["client_bonus"]),
        ("Открыто", ", ".join(pstate.get("unique_benefits_unlocked", [])) or "ничего"),
    ], "GOLD")
    ui.table("Национальная армия", ["Часть", "Класс", "Ат.", "Защ.", "Подв.", "Особенность"], [
        (u["name"], u["class"], u["attack"], u["defense"], u["mobility"], u["trait"]) for u in nation["units"]
    ], "CYAN")
    ui.pause()


def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx); ui = UI(ctx); state = ensure_state(player, ctx)
    while True:
        ui.screen(); ui.header("GENTES ET REGNA", "🦅", f"Уникальные цивилизации — {MODULE_VERSION}")
        rows = []
        diplomacy = _dict(getattr(player, "diplomacy", {}))
        for key, nation in NATIONS.items():
            row = _dict(diplomacy.get(key)); p = state["powers"][key]
            links = []
            if row.get("trade_pact"): links.append("торговля")
            if row.get("alliance"): links.append("союз")
            if row.get("married"): links.append("брак")
            if row.get("client"): links.append("клиент")
            if row.get("at_war"): links.append("ВОЙНА")
            rows.append((nation["name"], nation["government"], ", ".join(nation["exclusive_goods"]), ", ".join(links) or "нет", ", ".join(p.get("unique_benefits_unlocked", [])) or "—"))
        ui.table("Державы", ["Держава", "Устройство", "Уникальные товары", "Связи", "Бонусы"], rows, "CYAN")
        ui.section("Действия", "GOLD")
        print("  1. Подробное досье и национальная армия")
        print("  2. Активные уникальные модификаторы Рима")
        print("  Q. Назад")
        answer = ui.choice("\n  Выбор: ", ["1", "2", "Q"])
        if answer == "Q": return
        if answer == "1":
            keys = list(NATIONS)
            ui.screen(); ui.header("ВЫБОР ДЕРЖАВЫ", "📜")
            for i, key in enumerate(keys, 1): print(f"  {i}. {NATIONS[key]['name']}")
            ch = ui.choice("\n  Держава (или Q): ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
            if ch != "Q": _detail(ui, player, keys[int(ch) - 1])
        elif answer == "2":
            ui.screen(); ui.header("УНИКАЛЬНЫЕ МОДИФИКАТОРЫ", "⭐")
            _rebuild_modifiers(player, state)
            sources = _dict(state.get("modifier_sources"))
            if not state["modifiers"]:
                ui.wrap("Рим пока не получил уникальных преимуществ от иностранных держав.", "GRAY")
            else:
                ui.table("Модификаторы", ["Параметр", "Итого", "Источники"], [(name, value, "; ".join(sources.get(name, []))) for name, value in sorted(state["modifiers"].items())], "GOLD")
            ui.pause()


# ─── RES PUBLICA ORBIS COMPATIBILITY ROUTE ────────────────────────────────
# Старые прямые входы оставлены для сторонних модов и старых горячих клавиш,
# но в актуальной сборке ведут в соответствующий раздел единого центра.
_legacy_open_menu_before_world_politics = open_menu

def open_menu(player: Any, ctx: dict | None = None) -> None:
    context = _ctx(ctx)
    facade = context.get("WORLD_POLITICS")
    if facade is not None and hasattr(facade, "open_menu"):
        facade.open_menu(player, context, start_section="dossiers")
        return
    return _legacy_open_menu_before_world_politics(player, context)
