#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna — CIVITATES ET PROVINCIAE.

Живые города, провинциальная динамика и интерактивные события после хода.
Модуль намеренно не импортирует основной файл игры: связь идёт через ``player``
и словарь ``ctx`` (обычно ``globals()`` из roma_aeterna.py).

Публичный контракт:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None, interactive=True)
    present_pending_events(player, ctx=None)
    open_menu(player, ctx=None)
    empire_metrics(player, ctx=None)

Список городских событий находится в CITY_EVENT_CATALOG и полностью вынесен
из основного файла игры.
"""
from __future__ import annotations

import copy
import math
import random
import re
import textwrap
from typing import Any

MODULE_VERSION = "1.0.0-civitates"
SCHEMA_VERSION = 1
MAX_HISTORY = 240
MAX_PENDING = 12


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
                fn()
                return
            except Exception:
                pass

    def header(self, title: str, icon: str = "🏙", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try:
                fn(title, icon, getattr(self.C, "GOLD", ""), subtitle)
                return
            except TypeError:
                try:
                    fn(title, icon, getattr(self.C, "GOLD", ""))
                except Exception:
                    pass
        print(self.color(f"\n{'═' * 74}\n  {icon} {title}\n{'═' * 74}", "GOLD", True))
        if subtitle:
            self.wrap(subtitle, "GRAY")

    def section(self, title: str, color: str = "CYAN") -> None:
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
        widths = [len(_plain(h)) for h in headers]
        clean_rows: list[list[str]] = []
        for row in rows:
            clean = [_plain(v) for v in row]
            clean_rows.append(clean)
            for n, value in enumerate(clean[: len(widths)]):
                widths[n] = min(28, max(widths[n], len(value)))
        print("  " + " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
        print("  " + "-+-".join("-" * width for width in widths))
        for row in clean_rows:
            print("  " + " | ".join(row[i][: widths[i]].ljust(widths[i]) for i in range(len(headers))))

    def choice(self, prompt: str, valid: list[str]) -> str:
        valid = [str(x).upper() for x in valid]
        fn = self.ctx.get("read_choice")
        if callable(fn):
            try:
                return str(fn(self.color(prompt, "CYAN"), valid)).upper()
            except Exception:
                pass
        while True:
            answer = input(prompt).strip().upper()
            if answer in valid:
                return answer
            print("  Допустимо: " + ", ".join(valid))

    def pause(self) -> None:
        fn = self.ctx.get("rui_pause") or self.ctx.get("pause")
        if callable(fn):
            try:
                fn()
                return
            except Exception:
                pass
        input("\n  Нажмите Enter, чтобы продолжить...")


# Условия — символические ключи, проверяемые _eligible(). Все эффекты и варианты
# находятся здесь, а не в основном файле. Это позволяет расширять пул без правок
# roma_aeterna.py.
CITY_EVENT_CATALOG: list[dict[str, Any]] = [
    {"id": "harvest_boom", "title": "Изобильная жатва", "category": "economy", "icon": "🌾", "weight": 12, "condition": "agricultural"},
    {"id": "grain_shortage", "title": "Недостаток хлеба", "category": "economy", "icon": "🥖", "weight": 10, "condition": "food_low"},
    {"id": "market_fair", "title": "Большая городская ярмарка", "category": "trade", "icon": "🏺", "weight": 9, "condition": "prosperous"},
    {"id": "guild_dispute", "title": "Спор коллегий ремесленников", "category": "society", "icon": "⚒", "weight": 8, "condition": "craft"},
    {"id": "aqueduct_failure", "title": "Повреждение акведука", "category": "infrastructure", "icon": "🚰", "weight": 8, "condition": "infrastructure_risk"},
    {"id": "epidemic", "title": "Городская моровая болезнь", "category": "disaster", "icon": "☠", "weight": 5, "condition": "health_risk"},
    {"id": "urban_fire", "title": "Пожар в инсулах", "category": "disaster", "icon": "🔥", "weight": 7, "condition": "dense_city"},
    {"id": "river_flood", "title": "Разлив реки", "category": "disaster", "icon": "🌊", "weight": 5, "condition": "river_city"},
    {"id": "earthquake", "title": "Землетрясение", "category": "disaster", "icon": "🪨", "weight": 3, "condition": "any"},
    {"id": "banditry", "title": "Разбой на провинциальных дорогах", "category": "security", "icon": "🗡", "weight": 9, "condition": "order_risk"},
    {"id": "tax_resistance", "title": "Сопротивление налоговой переписи", "category": "politics", "icon": "📜", "weight": 8, "condition": "loyalty_risk"},
    {"id": "governor_corruption", "title": "Донос на наместника", "category": "politics", "icon": "⚖", "weight": 7, "condition": "governor"},
    {"id": "veteran_colony", "title": "Земля для ветеранов", "category": "military", "icon": "🛡", "weight": 6, "condition": "military"},
    {"id": "elite_petition", "title": "Петиция муниципальной знати", "category": "politics", "icon": "🏛", "weight": 9, "condition": "any"},
    {"id": "citizenship_debate", "title": "Спор о римском гражданстве", "category": "culture", "icon": "🦅", "weight": 6, "condition": "culture_mid"},
    {"id": "religious_procession", "title": "Торжественная процессия", "category": "religion", "icon": "🕯", "weight": 7, "condition": "religious"},
    {"id": "cult_conflict", "title": "Столкновение культовых общин", "category": "religion", "icon": "⚡", "weight": 5, "condition": "culture_low"},
    {"id": "philosopher_school", "title": "Школа философа", "category": "science", "icon": "📚", "weight": 6, "condition": "cultural"},
    {"id": "engineering_breakthrough", "title": "Предложение городских инженеров", "category": "science", "icon": "🏗", "weight": 5, "condition": "infrastructure_mid"},
    {"id": "port_congestion", "title": "Затор в гавани", "category": "trade", "icon": "⚓", "weight": 7, "condition": "port"},
    {"id": "piracy_rumors", "title": "Слухи о пиратах", "category": "security", "icon": "🏴", "weight": 6, "condition": "port"},
    {"id": "slave_unrest", "title": "Тайные сходки рабов", "category": "society", "icon": "⛓", "weight": 5, "condition": "wealthy_unstable"},
    {"id": "gladiatorial_games", "title": "Просьба устроить игры", "category": "society", "icon": "🏟", "weight": 8, "condition": "dense_city"},
    {"id": "urban_migration", "title": "Наплыв переселенцев", "category": "demography", "icon": "👥", "weight": 8, "condition": "prosperous"},
    {"id": "wall_repairs", "title": "Ветхие городские стены", "category": "military", "icon": "🧱", "weight": 7, "condition": "defense_low"},
    {"id": "frontier_refugees", "title": "Беженцы с пограничья", "category": "demography", "icon": "🏕", "weight": 6, "condition": "frontier"},
    {"id": "coin_shortage", "title": "Нехватка разменной монеты", "category": "economy", "icon": "🪙", "weight": 6, "condition": "trade"},
    {"id": "local_festival", "title": "Муниципальный праздник", "category": "culture", "icon": "🎭", "weight": 8, "condition": "any"},
    {"id": "smuggling_ring", "title": "Сеть контрабандистов", "category": "security", "icon": "🕵", "weight": 7, "condition": "trade"},
    {"id": "municipal_rivalry", "title": "Соперничество городов", "category": "politics", "icon": "🏙", "weight": 7, "condition": "multi_city"},
    {"id": "raid_warning", "title": "Весть о приближении налётчиков", "category": "military", "icon": "🐺", "weight": 7, "condition": "frontier"},
    {"id": "provincial_census", "title": "Провинциальный ценз", "category": "administration", "icon": "📋", "weight": 6, "condition": "any"},
]
EVENT_BY_ID = {item["id"]: item for item in CITY_EVENT_CATALOG}

CATEGORY_LABELS = {
    "economy": "Экономика", "trade": "Торговля", "society": "Общество",
    "infrastructure": "Инфраструктура", "disaster": "Бедствие", "security": "Безопасность",
    "politics": "Политика", "military": "Военное дело", "culture": "Культура",
    "religion": "Религия", "science": "Наука", "demography": "Население",
    "administration": "Управление",
}


def _city_key(province_name: str, city_name: str) -> str:
    return f"{province_name}::{city_name}"


def _city_template_index(ctx: dict) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    for province in _list(ctx.get("PROVINCES_DATA", [])):
        if not isinstance(province, dict):
            continue
        pname = str(province.get("name", ""))
        for city in _list(province.get("cities", [])):
            if isinstance(city, dict) and city.get("name"):
                result[(pname, str(city["name"]))] = city
    return result


def _default_city_state(province: dict, city: dict, player: Any) -> dict:
    population = max(4, _i(city.get("population", 20), 20, 1, 2000))
    province_unrest = _i(province.get("unrest", 0), 0, 0, 10)
    wealth = _i(province.get("wealth", 2), 2, 0, 30)
    romanization = _clamp(province.get("romanization", 0), 0, 100, 0)
    garrison = _i(province.get("garrison", 0), 0, 0, 10)
    difficulty = _i(city.get("difficulty", 3), 3, 1, 10)
    ctype = str(city.get("type", "город"))
    trade_bonus = 10 if any(x in ctype.lower() for x in ("порт", "торг", "реч", "мор")) else 0
    health_bonus = 6 if any(x in ctype.lower() for x in ("курорт", "свящ", "религ")) else 0
    defense_bonus = 8 if any(x in ctype.lower() for x in ("воен", "креп", "осад", "погранич")) else 0
    return {
        "name": str(city.get("name", "Город")),
        "province": str(province.get("name", "Провинция")),
        "type": ctype,
        "population": population,
        "prosperity": _clamp(42 + wealth * 4 + trade_bonus - province_unrest * 3, 5, 95, 45),
        "order": _clamp(58 + garrison * 7 - province_unrest * 7, 5, 95, 55),
        "health": _clamp(58 + health_bonus - max(0, population - 80) // 4, 10, 95, 58),
        "infrastructure": _clamp(38 + wealth * 4 + difficulty * 2, 10, 90, 45),
        "culture": _clamp(20 + romanization * 3 // 5, 5, 95, 25),
        "loyalty": _clamp(48 + romanization // 2 + garrison * 3 - province_unrest * 5, 5, 95, 50),
        "food": _clamp(58 + wealth * 2 - province_unrest * 4, 5, 100, 60),
        "defense": _clamp(30 + difficulty * 5 + garrison * 6 + defense_bonus, 5, 100, 45),
        "trade": _clamp(30 + wealth * 5 + trade_bonus, 5, 100, 40),
        "pollution": _clamp(max(0, population - 60) // 2, 0, 70, 0),
        "status": "стабильный",
        "last_event_turn": 0,
        "event_cooldowns": {},
        "active_effects": [],
        "founded_turn": _i(getattr(player, "turn", 1), 1, 1),
    }


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    state = getattr(player, "city_system", None)
    if not isinstance(state, dict):
        state = {}
        player.city_system = state
    state.setdefault("schema", SCHEMA_VERSION)
    state.setdefault("version", MODULE_VERSION)
    state.setdefault("cities", {})
    state.setdefault("pending", [])
    state.setdefault("history", [])
    state.setdefault("last_tick_turn", 0)
    state.setdefault("settings", {})
    state["settings"].setdefault("events_per_turn", "dynamic")
    state["settings"].setdefault("auto_resolve_noninteractive", True)
    state["settings"].setdefault("show_city_digest", True)

    cities = _dict(state.get("cities"))
    templates = _city_template_index(ctx)
    owned_names: set[str] = set()
    for province in _list(getattr(player, "provinces", [])):
        if not isinstance(province, dict) or not province.get("name"):
            continue
        pname = str(province["name"])
        owned_names.add(pname)
        city_rows = _list(province.get("cities", []))
        if not city_rows:
            city_rows = [c for (pn, _), c in templates.items() if pn == pname]
        for city in city_rows:
            if not isinstance(city, dict) or not city.get("name"):
                continue
            cname = str(city["name"])
            key = _city_key(pname, cname)
            row = cities.get(key) if isinstance(cities.get(key), dict) else _default_city_state(province, city, player)
            defaults = _default_city_state(province, city, player)
            for field_name, default in defaults.items():
                row.setdefault(field_name, copy.deepcopy(default))
            row["name"] = cname
            row["province"] = pname
            row["type"] = str(city.get("type", row.get("type", "город")))
            row["population"] = _i(row.get("population", defaults["population"]), defaults["population"], 1, 5000)
            for metric in ("prosperity", "order", "health", "infrastructure", "culture", "loyalty", "food", "defense", "trade", "pollution"):
                row[metric] = _clamp(row.get(metric, defaults.get(metric, 50)), 0, 100, defaults.get(metric, 50))
            row["event_cooldowns"] = {str(k): _i(v, 0, 0) for k, v in _dict(row.get("event_cooldowns")).items() if _i(v, 0) > 0}
            row["active_effects"] = [x for x in _list(row.get("active_effects")) if isinstance(x, dict)][-12:]
            row["last_event_turn"] = _i(row.get("last_event_turn", 0), 0, 0)
            cities[key] = row

    # Удалённые/потерянные провинции не участвуют в текущем ходе, но история их
    # городов сохраняется в архиве. Поле active помечает их без потери данных.
    for row in cities.values():
        if isinstance(row, dict):
            row["active"] = str(row.get("province", "")) in owned_names

    state["cities"] = cities
    state["pending"] = [x for x in _list(state.get("pending")) if isinstance(x, dict)][-MAX_PENDING:]
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state["last_tick_turn"] = _i(state.get("last_tick_turn", 0), 0, 0)
    state["schema"] = SCHEMA_VERSION
    state["version"] = MODULE_VERSION
    player.city_system = state
    return state


def _province_map(player: Any) -> dict[str, dict]:
    return {
        str(p.get("name")): p
        for p in _list(getattr(player, "provinces", []))
        if isinstance(p, dict) and p.get("name")
    }


def _is_port(city: dict) -> bool:
    text = (str(city.get("type", "")) + " " + str(city.get("name", ""))).lower()
    return any(x in text for x in ("порт", "мор", "гаван", "реч", "carthago", "alexandria", "syracus", "brund", "massilia", "genua", "caralis"))


def _is_frontier(province: dict, player: Any, ctx: dict) -> bool:
    owned = {str(p.get("name")) for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)}
    definition = None
    fn = ctx.get("province_by_name")
    if callable(fn):
        try:
            definition = fn(province.get("name"))
        except Exception:
            definition = None
    if not isinstance(definition, dict):
        definition = province
    neighbors = [str(x) for x in _list(definition.get("neighbors", []))]
    return any(name not in owned for name in neighbors)


def _eligible(condition: str, player: Any, province: dict, city: dict, ctx: dict) -> bool:
    ctype = str(city.get("type", "")).lower()
    if condition == "any": return True
    if condition == "agricultural": return any(x in ctype for x in ("землед", "сель", "вин", "скот", "реч")) or city.get("food", 0) >= 55
    if condition == "food_low": return city.get("food", 50) <= 48 or _i(getattr(player, "grain", 0), 0) < 80
    if condition == "prosperous": return city.get("prosperity", 0) >= 58
    if condition == "craft": return any(x in ctype for x in ("ремес", "торг", "пром", "металл")) or city.get("trade", 0) >= 50
    if condition == "infrastructure_risk": return city.get("infrastructure", 50) <= 58 or city.get("population", 0) >= 70
    if condition == "health_risk": return city.get("health", 50) <= 58 or city.get("population", 0) >= 85 or city.get("pollution", 0) >= 35
    if condition == "dense_city": return city.get("population", 0) >= 45
    if condition == "river_city": return any(x in ctype for x in ("реч", "порт")) or any(x in str(city.get("name", "")).lower() for x in ("roma", "alexandria", "babylon", "ctesiphon"))
    if condition == "order_risk": return city.get("order", 50) <= 62 or _i(province.get("unrest", 0), 0) >= 3
    if condition == "loyalty_risk": return city.get("loyalty", 50) <= 60 or _i(province.get("romanization", 0), 0) < 35
    if condition == "governor": return str(province.get("name", "")) in _dict(getattr(player, "governors", {}))
    if condition == "military": return any(x in ctype for x in ("воен", "креп", "осад", "погранич")) or city.get("defense", 0) >= 55
    if condition == "culture_mid": return 20 <= city.get("culture", 0) <= 75
    if condition == "religious": return any(x in ctype for x in ("религ", "свящ", "культ")) or bool(getattr(player, "religion", None))
    if condition == "culture_low": return city.get("culture", 50) <= 48 or city.get("loyalty", 50) <= 50
    if condition == "cultural": return any(x in ctype for x in ("культур", "религ", "администр")) or city.get("culture", 0) >= 45
    if condition == "infrastructure_mid": return 30 <= city.get("infrastructure", 0) <= 75
    if condition == "port": return _is_port(city)
    if condition == "wealthy_unstable": return city.get("prosperity", 0) >= 55 and city.get("order", 100) <= 65
    if condition == "defense_low": return city.get("defense", 100) <= 58 or _is_frontier(province, player, ctx)
    if condition == "frontier": return _is_frontier(province, player, ctx)
    if condition == "trade": return city.get("trade", 0) >= 45 or _is_port(city)
    if condition == "multi_city":
        count = sum(1 for row in _dict(getattr(player, "city_system", {}).get("cities", {})).values() if isinstance(row, dict) and row.get("active") and row.get("province") == province.get("name"))
        return count >= 2
    return True


def _effect_text(effects: dict) -> str:
    labels = {
        "gold": "золото", "grain": "зерно", "glory": "слава", "science": "наука", "faith": "вера",
        "senate_rep": "Сенат", "people_rep": "народ", "unrest": "волнения Рима", "morale": "мораль",
        "province_unrest": "волнения провинции", "province_wealth": "богатство провинции", "garrison": "гарнизон", "romanization": "романизация",
        "population": "население", "prosperity": "процветание", "order": "порядок", "health": "здоровье",
        "infrastructure": "инфраструктура", "culture": "культура", "loyalty": "лояльность", "food": "продовольствие",
        "defense": "оборона", "trade": "торговля", "pollution": "загрязнение",
    }
    parts = []
    for key, amount in effects.items():
        if key in {"active_effect", "log"}:
            continue
        if not isinstance(amount, (int, float)) or amount == 0:
            continue
        sign = "+" if amount > 0 else ""
        parts.append(f"{labels.get(key, key)} {sign}{int(amount)}")
    return "; ".join(parts) if parts else "долгосрочные политические последствия"


def _option(key: str, label: str, desc: str, effects: dict, *, gold: int = 0, grain: int = 0, faith: int = 0, ai: int = 50) -> dict:
    return {
        "key": key, "label": label, "desc": desc, "effects": effects,
        "requires": {"gold": max(0, gold), "grain": max(0, grain), "faith": max(0, faith)},
        "ai": ai,
    }


def _build_options(event_id: str, player: Any, province: dict, city: dict) -> list[dict]:
    pop = _i(city.get("population", 30), 30, 1)
    wealthy = city.get("prosperity", 50) >= 60
    costs = {
        "small": max(12, min(45, 10 + pop // 3)),
        "medium": max(25, min(90, 22 + pop // 2)),
        "large": max(45, min(150, 35 + pop)),
    }
    # Варианты сформулированы так, чтобы всегда существовал бесплатный или
    # дешёвый выход. Игра не запирает пользователя из-за нехватки ресурсов.
    options: dict[str, list[dict]] = {
        "harvest_boom": [
            _option("1", "Закупить излишки в государственные амбары", "Казна оплачивает урожай и создаёт резерв.", {"grain": 55, "food": 12, "loyalty": 4}, gold=costs["medium"], ai=82),
            _option("2", "Разрешить свободную продажу", "Купцы богатеют, но Рим не получает полного запаса.", {"gold": 35, "prosperity": 8, "trade": 5, "food": -3}, ai=72),
            _option("3", "Изъять чрезвычайную десятину", "Быстрый доход ценой недовольства землевладельцев.", {"grain": 70, "province_unrest": 1, "loyalty": -7}, ai=35),
        ],
        "grain_shortage": [
            _option("1", "Открыть государственные амбары", "Раздать хлеб и не допустить голода.", {"grain": -40, "food": 18, "health": 5, "loyalty": 7, "people_rep": 2}, grain=40, ai=86),
            _option("2", "Закупить хлеб у соседей", "Дорого, но без расхода римского резерва.", {"food": 14, "trade": 3, "gold": -costs["large"]}, gold=costs["large"], ai=70),
            _option("3", "Ввести нормирование", "Порядок удержан, однако город беднеет.", {"order": 5, "prosperity": -6, "loyalty": -5, "health": -3}, ai=42),
        ],
        "market_fair": [
            _option("1", "Даровать налоговые льготы", "Ярмарка станет центром межпровинциальной торговли.", {"gold": -costs["small"], "trade": 11, "prosperity": 8, "loyalty": 3}, gold=costs["small"], ai=78),
            _option("2", "Взять обычные пошлины", "Умеренная прибыль без сильного вмешательства.", {"gold": 32, "trade": 4, "prosperity": 3}, ai=74),
            _option("3", "Обложить купцов чрезвычайным сбором", "Казна наполнится, но ярмарка может уйти в другой город.", {"gold": 65, "trade": -8, "loyalty": -4}, ai=40),
        ],
        "guild_dispute": [
            _option("1", "Учредить арбитраж магистратов", "Стороны подчиняются публичному решению.", {"gold": -costs["small"], "order": 7, "prosperity": 4, "loyalty": 3}, gold=costs["small"], ai=82),
            _option("2", "Поддержать крупнейшую коллегию", "Производство восстановится быстро, но возникнет монополия.", {"prosperity": 7, "trade": 3, "loyalty": -3, "province_wealth": 1}, ai=61),
            _option("3", "Не вмешиваться", "Спор затянется и ударит по рынку.", {"order": -4, "prosperity": -5}, ai=28),
        ],
        "aqueduct_failure": [
            _option("1", "Немедленно восстановить акведук", "Инженеры получают всё необходимое.", {"gold": -costs["large"], "infrastructure": 12, "health": 10, "loyalty": 3}, gold=costs["large"], ai=90),
            _option("2", "Возложить ремонт на город", "Муниципий платит сам, но его хозяйство ослабевает.", {"infrastructure": 6, "prosperity": -6, "loyalty": -4}, ai=52),
            _option("3", "Ограничиться временными цистернами", "Дешёвое решение лишь откладывает кризис.", {"gold": -costs["small"], "health": -3, "infrastructure": -4, "food": -3}, gold=costs["small"], ai=38),
        ],
        "epidemic": [
            _option("1", "Развернуть лазареты и подвоз воды", "Дорогая санитарная кампания спасает жителей.", {"gold": -costs["large"], "health": 15, "population": -1, "loyalty": 6, "pollution": -8}, gold=costs["large"], ai=94),
            _option("2", "Закрыть ворота и рынки", "Карантин сдерживает болезнь ценой торговли.", {"health": 8, "order": 4, "trade": -8, "prosperity": -5, "population": -2}, ai=75),
            _option("3", "Поручить заботу местным общинам", "Казна не тратится, но потери будут тяжелее.", {"health": -10, "population": -5, "loyalty": -7}, ai=20),
        ],
        "urban_fire": [
            _option("1", "Создать пожарные когорты", "Пожар тушат, а город получает постоянную службу.", {"gold": -costs["large"], "infrastructure": 7, "order": 5, "health": 2, "population": -1}, gold=costs["large"], ai=90),
            _option("2", "Компенсировать владельцам часть убытков", "Город восстанавливается без полного государственного контроля.", {"gold": -costs["medium"], "prosperity": 3, "loyalty": 6, "infrastructure": -3}, gold=costs["medium"], ai=73),
            _option("3", "Пусть квартал отстроится сам", "Казна цела, но бедняки остаются без крова.", {"population": -3, "infrastructure": -9, "order": -7, "unrest": 2}, ai=23),
        ],
        "river_flood": [
            _option("1", "Соорудить дамбы и отводные каналы", "Капитальное строительство защищает город надолго.", {"gold": -costs["large"], "infrastructure": 13, "food": 5, "prosperity": 3}, gold=costs["large"], ai=88),
            _option("2", "Выдать зерно пострадавшим", "Помощь людям без полной перестройки русла.", {"grain": -30, "loyalty": 7, "health": 3, "infrastructure": -4}, grain=30, ai=72),
            _option("3", "Переселить низинные кварталы", "Жёсткая мера уменьшает будущий риск, но вызывает гнев.", {"population": -2, "health": 6, "order": -3, "loyalty": -4}, ai=52),
        ],
        "earthquake": [
            _option("1", "Объявить имперскую реконструкцию", "Римская казна поднимает город из руин.", {"gold": -costs["large"], "infrastructure": 8, "loyalty": 8, "population": -2, "glory": 2}, gold=costs["large"], ai=90),
            _option("2", "Освободить город от налогов", "Восстановление медленное, но хозяйство получает передышку.", {"province_wealth": -1, "prosperity": 5, "loyalty": 5, "infrastructure": -6}, ai=68),
            _option("3", "Сохранить обычные повинности", "Казна не уступает, город несёт тяжёлые потери.", {"population": -4, "infrastructure": -12, "loyalty": -8, "province_unrest": 1}, ai=18),
        ],
        "banditry": [
            _option("1", "Послать вспомогательные когорты", "Дороги очищены, но операция требует денег.", {"gold": -costs["medium"], "order": 10, "trade": 5, "defense": 3}, gold=costs["medium"], ai=84),
            _option("2", "Вооружить местные общины", "Дешёвая самооборона укрепляет муниципий.", {"order": 5, "defense": 6, "loyalty": 2, "province_unrest": -1}, ai=70),
            _option("3", "Откупиться от главарей", "Тишина наступит быстро, но преступники станут сильнее.", {"gold": -costs["small"], "order": 2, "loyalty": -5, "trade": -3}, gold=costs["small"], ai=34),
        ],
        "tax_resistance": [
            _option("1", "Пересмотреть оценку имущества", "Справедливый ценз повышает доверие, но уменьшает сборы.", {"gold": -costs["small"], "loyalty": 8, "order": 4, "province_unrest": -1}, gold=costs["small"], ai=82),
            _option("2", "Направить ликторов", "Налоги будут взысканы силой.", {"gold": 45, "order": 2, "loyalty": -9, "province_unrest": 1}, ai=42),
            _option("3", "Отложить сбор до следующего года", "Компромисс успокаивает город, но казна теряет доход.", {"gold": -20, "loyalty": 5, "prosperity": 3}, ai=66),
        ],
        "governor_corruption": [
            _option("1", "Начать публичное расследование", "Наместник и обвинители предстанут перед судом.", {"gold": -costs["small"], "loyalty": 7, "order": 4, "senate_rep": 1, "province_wealth": -1}, gold=costs["small"], ai=84),
            _option("2", "Потребовать тайную долю в казну", "Коррупция сохраняется, но Рим получает деньги.", {"gold": 55, "loyalty": -8, "province_unrest": 1}, ai=25),
            _option("3", "Оставить наместника под наблюдением", "Рискованный компромисс без немедленных потрясений.", {"order": -2, "loyalty": -2, "trade": 2}, ai=50),
        ],
        "veteran_colony": [
            _option("1", "Выделить общественную землю", "Ветераны укрепят рубеж и романизацию.", {"gold": -costs["medium"], "population": 4, "defense": 10, "culture": 7, "loyalty": 5}, gold=costs["medium"], ai=86),
            _option("2", "Купить участки у местных владельцев", "Дороже, зато без конфискаций.", {"gold": -costs["large"], "population": 3, "defense": 7, "loyalty": 7, "prosperity": 2}, gold=costs["large"], ai=82),
            _option("3", "Отказать в поселении", "Казна не тратится, но армия недовольна.", {"morale": -4, "loyalty": -2}, ai=25),
        ],
        "elite_petition": [
            _option("1", "Принять делегацию и дать привилегии", "Местная верхушка становится опорой Рима.", {"gold": -costs["small"], "loyalty": 8, "culture": 4, "senate_rep": 1}, gold=costs["small"], ai=80),
            _option("2", "Потребовать встречной общественной стройки", "Привилегии выдаются в обмен на вклад в город.", {"infrastructure": 6, "loyalty": 3, "prosperity": -2}, ai=76),
            _option("3", "Отказать провинциалам", "Рим сохраняет дистанцию и раздражает элиту.", {"loyalty": -7, "province_unrest": 1, "senate_rep": 1}, ai=32),
        ],
        "citizenship_debate": [
            _option("1", "Расширить гражданские права", "Муниципий теснее связывается с Римом.", {"culture": 11, "loyalty": 8, "romanization": 5, "senate_rep": -1}, ai=85),
            _option("2", "Даровать права только элите", "Умеренная интеграция без полного равенства.", {"culture": 6, "loyalty": 3, "prosperity": 3}, ai=72),
            _option("3", "Сохранить прежний статус", "Консервативная политика нравится части Сената.", {"senate_rep": 2, "culture": -3, "loyalty": -5}, ai=38),
        ],
        "religious_procession": [
            _option("1", "Оплатить торжества", "Пышная церемония укрепляет согласие и престиж.", {"gold": -costs["medium"], "faith": 8, "order": 5, "loyalty": 5, "glory": 1}, gold=costs["medium"], ai=78),
            _option("2", "Разрешить процессии за счёт общин", "Рим признаёт обычаи, не расходуя казну.", {"faith": 4, "loyalty": 3, "culture": 2}, ai=75),
            _option("3", "Ограничить церемонии", "Порядок формально усилен, но верующие возмущены.", {"order": 3, "faith": -3, "loyalty": -7}, ai=30),
        ],
        "cult_conflict": [
            _option("1", "Созвать совет жрецов и старейшин", "Переговоры снижают напряжение.", {"gold": -costs["small"], "order": 7, "loyalty": 4, "culture": 3}, gold=costs["small"], ai=84),
            _option("2", "Поддержать официальный культ", "Власть демонстрирует силу, но меньшинства отчуждаются.", {"faith": 6, "order": 3, "loyalty": -5, "culture": -3}, ai=51),
            _option("3", "Не вмешиваться", "Уличное противостояние может разрастись.", {"order": -8, "health": -2, "province_unrest": 1}, ai=20),
        ],
        "philosopher_school": [
            _option("1", "Учредить публичную школу", "Рим финансирует преподавание и библиотеку.", {"gold": -costs["medium"], "science": 16, "culture": 9, "glory": 1}, gold=costs["medium"], ai=86),
            _option("2", "Даровать помещение без жалованья", "Дешёвая поддержка даёт умеренный эффект.", {"science": 8, "culture": 5, "infrastructure": -1}, ai=74),
            _option("3", "Запретить подозрительное учение", "Консерваторы довольны, образованные горожане — нет.", {"senate_rep": 1, "science": -5, "culture": -6, "loyalty": -3}, ai=28),
        ],
        "engineering_breakthrough": [
            _option("1", "Оплатить опытное строительство", "Успех даст городу новые методы работ.", {"gold": -costs["large"], "infrastructure": 14, "science": 10, "glory": 1}, gold=costs["large"], ai=88),
            _option("2", "Поручить проект частным подрядчикам", "Меньше расходов, но часть выгоды уйдёт подрядчикам.", {"gold": -costs["small"], "infrastructure": 7, "prosperity": 4}, gold=costs["small"], ai=72),
            _option("3", "Отложить проект", "Риск отсутствует, возможность упущена.", {"science": -1}, ai=30),
        ],
        "port_congestion": [
            _option("1", "Расширить причалы и склады", "Гавань сможет принимать больше судов.", {"gold": -costs["large"], "infrastructure": 10, "trade": 12, "prosperity": 5}, gold=costs["large"], ai=90),
            _option("2", "Ввести расписание и портовые сборы", "Административная реформа приносит доход.", {"gold": 25, "trade": 5, "order": 3}, ai=75),
            _option("3", "Оставить порт без изменений", "Затор уменьшит торговлю и здоровье кварталов.", {"trade": -8, "health": -3, "pollution": 5}, ai=25),
        ],
        "piracy_rumors": [
            _option("1", "Снарядить морские патрули", "Торговые пути получают защиту.", {"gold": -costs["medium"], "trade": 6, "order": 5, "defense": 5}, gold=costs["medium"], ai=82),
            _option("2", "Субсидировать вооружение купцов", "Купцы защищают себя сами.", {"gold": -costs["small"], "trade": 4, "defense": 3, "prosperity": 2}, gold=costs["small"], ai=69),
            _option("3", "Считать слухи преувеличенными", "При неудаче рынки понесут потери.", {"trade": -6, "prosperity": -4}, ai=32),
        ],
        "slave_unrest": [
            _option("1", "Расследовать злоупотребления владельцев", "Умеренная реформа снижает причины мятежа.", {"gold": -costs["small"], "order": 8, "loyalty": 4, "prosperity": -3, "people_rep": 1}, gold=costs["small"], ai=82),
            _option("2", "Усилить городскую стражу", "Сходки разогнаны, но напряжение сохраняется.", {"order": 7, "defense": 3, "loyalty": -5}, ai=62),
            _option("3", "Провести массовые наказания", "Страх восстанавливает тишину ценой будущей ненависти.", {"order": 12, "population": -2, "loyalty": -12, "province_unrest": 1}, ai=28),
        ],
        "gladiatorial_games": [
            _option("1", "Устроить великолепные игры", "Город празднует щедрость власти.", {"gold": -costs["large"], "order": 7, "loyalty": 7, "people_rep": 3, "glory": 2}, gold=costs["large"], ai=77),
            _option("2", "Разрешить игры на средства магистратов", "Местная элита платит и получает престиж.", {"order": 5, "loyalty": 3, "prosperity": 1}, ai=75),
            _option("3", "Запретить расточительство", "Казна цела, толпа разочарована.", {"people_rep": -2, "order": -3}, ai=35),
        ],
        "urban_migration": [
            _option("1", "Разбить новые кварталы и провести воду", "Переселенцы становятся полноценными жителями.", {"gold": -costs["large"], "population": 7, "infrastructure": 6, "prosperity": 5, "health": 2}, gold=costs["large"], ai=84),
            _option("2", "Расселить людей по окрестным селениям", "Рост распределяется без перегрузки города.", {"population": 3, "food": -3, "province_wealth": 1, "loyalty": 2}, ai=72),
            _option("3", "Закрыть ворота для новых жителей", "Порядок сохранён, но хозяйство теряет рабочие руки.", {"order": 4, "prosperity": -4, "loyalty": -3}, ai=42),
        ],
        "wall_repairs": [
            _option("1", "Полностью перестроить стены", "Город получает современную оборонительную линию.", {"gold": -costs["large"], "defense": 16, "infrastructure": 5, "glory": 1}, gold=costs["large"], ai=90),
            _option("2", "Провести срочный ремонт", "Дешевле, но без капитальной реконструкции.", {"gold": -costs["medium"], "defense": 9, "infrastructure": 2}, gold=costs["medium"], ai=76),
            _option("3", "Положиться на гарнизон", "Стены продолжат ветшать.", {"defense": -7, "order": -2}, ai=25),
        ],
        "frontier_refugees": [
            _option("1", "Принять и снабдить переселенцев", "Новые жители благодарны Риму, но требуют хлеба.", {"grain": -30, "population": 6, "loyalty": 5, "food": -6, "people_rep": 1}, grain=30, ai=80),
            _option("2", "Поселить их как пограничных земледельцев", "Колонисты одновременно кормят и защищают рубеж.", {"gold": -costs["medium"], "population": 4, "food": 4, "defense": 6, "culture": 2}, gold=costs["medium"], ai=85),
            _option("3", "Не пропускать через границу", "Ресурсы сохранены, репутация Рима страдает.", {"loyalty": -4, "people_rep": -1, "order": 2}, ai=35),
        ],
        "coin_shortage": [
            _option("1", "Доставить монету из казны", "Расчёты восстанавливаются без изменения цен.", {"gold": -costs["medium"], "trade": 8, "prosperity": 5}, gold=costs["medium"], ai=80),
            _option("2", "Разрешить местные кредитные расписки", "Рынок оживает, но возрастает риск спекуляций.", {"trade": 7, "prosperity": 4, "order": -2}, ai=68),
            _option("3", "Ничего не предпринимать", "Торговля сжимается до возвращения монеты.", {"trade": -7, "prosperity": -5}, ai=25),
        ],
        "local_festival": [
            _option("1", "Поддержать праздник из казны", "Городские традиции связываются с римской властью.", {"gold": -costs["small"], "culture": 6, "loyalty": 6, "order": 3}, gold=costs["small"], ai=76),
            _option("2", "Разрешить праздник без субсидии", "Обычаи сохранены без расходов.", {"culture": 4, "loyalty": 3}, ai=72),
            _option("3", "Заменить его римскими играми", "Романизация ускоряется, но часть жителей оскорблена.", {"culture": 8, "romanization": 4, "loyalty": -3, "glory": 1}, ai=55),
        ],
        "smuggling_ring": [
            _option("1", "Создать следственную комиссию", "Контрабандисты и их покровители будут раскрыты.", {"gold": -costs["small"], "order": 8, "trade": 3, "loyalty": 3}, gold=costs["small"], ai=82),
            _option("2", "Предложить амнистию за уплату пошлин", "Часть теневой торговли станет законной.", {"gold": 30, "trade": 5, "order": 2}, ai=76),
            _option("3", "Получать тайную долю", "Казна богатеет, законность разрушается.", {"gold": 60, "order": -8, "loyalty": -5, "province_unrest": 1}, ai=24),
        ],
        "municipal_rivalry": [
            _option("1", "Объявить конкурс общественных построек", "Соперничество превращается в созидание.", {"gold": -costs["medium"], "infrastructure": 7, "culture": 4, "prosperity": 3}, gold=costs["medium"], ai=82),
            _option("2", "Поддержать более лояльный город", "Опора Рима усиливается, но соседние элиты обижены.", {"loyalty": 6, "province_unrest": 1, "prosperity": 2}, ai=51),
            _option("3", "Не вмешиваться", "Соперничество перерастает в уличные столкновения.", {"order": -6, "loyalty": -3}, ai=25),
        ],
        "raid_warning": [
            _option("1", "Усилить стены и дозоры", "Город готовится встретить налётчиков.", {"gold": -costs["medium"], "defense": 11, "order": 4, "garrison": 1}, gold=costs["medium"], ai=89),
            _option("2", "Эвакуировать запасы за стены", "Потери от рейда будут меньше, но торговля остановится.", {"food": 5, "defense": 5, "trade": -5}, ai=72),
            _option("3", "Считать донесение ложной тревогой", "Экономика не нарушена, однако риск остаётся.", {"defense": -3}, ai=28),
        ],
        "provincial_census": [
            _option("1", "Провести точный и умеренный ценз", "Налоговая база уточняется без излишнего давления.", {"gold": -costs["small"], "province_wealth": 1, "order": 3, "loyalty": 3}, gold=costs["small"], ai=83),
            _option("2", "Использовать ценз для повышения сборов", "Казна получает больше, город раздражён.", {"gold": 50, "loyalty": -6, "province_unrest": 1}, ai=44),
            _option("3", "Передать перепись местной знати", "Дёшево, но данные могут быть искажены.", {"gold": 15, "loyalty": 2, "order": -2}, ai=57),
        ],
    }
    return copy.deepcopy(options.get(event_id, [
        _option("1", "Поддержать город", "Умеренные расходы ради стабильности.", {"gold": -costs["small"], "loyalty": 4, "order": 3}, gold=costs["small"], ai=75),
        _option("2", "Не вмешиваться", "Муниципий решит вопрос самостоятельно.", {"loyalty": -2}, ai=40),
    ]))


def _can_afford(player: Any, option: dict) -> bool:
    req = _dict(option.get("requires"))
    return (
        _i(getattr(player, "gold", 0), 0) >= _i(req.get("gold", 0), 0)
        and _i(getattr(player, "grain", 0), 0) >= _i(req.get("grain", 0), 0)
        and _i(getattr(player, "faith", 0), 0) >= _i(req.get("faith", 0), 0)
    )


def _apply_effects(player: Any, province: dict, city: dict, effects: dict) -> dict:
    before = {
        "gold": _i(getattr(player, "gold", 0), 0), "grain": _i(getattr(player, "grain", 0), 0),
        "glory": _i(getattr(player, "glory", 0), 0), "science": _i(getattr(player, "science_points", 0), 0),
        "faith": _i(getattr(player, "faith", 0), 0),
    }
    player_fields = {
        "gold": ("gold", 0, None), "grain": ("grain", 0, None), "glory": ("glory", 0, None),
        "science": ("science_points", 0, None), "faith": ("faith", 0, None),
        "senate_rep": ("senate_rep", 0, 100), "people_rep": ("people_rep", 0, 100),
        "unrest": ("unrest", 0, 100), "morale": ("morale", 0, 100),
    }
    for key, (attr, low, high) in player_fields.items():
        amount = _i(effects.get(key, 0), 0)
        if amount:
            current = _i(getattr(player, attr, 0), 0)
            value = current + amount
            value = max(low, value)
            if high is not None:
                value = min(high, value)
            setattr(player, attr, value)

    province_fields = {
        "province_unrest": ("unrest", 0, 10), "province_wealth": ("wealth", 0, 30),
        "garrison": ("garrison", 0, 10), "romanization": ("romanization", 0, 100),
    }
    for key, (field, low, high) in province_fields.items():
        amount = _i(effects.get(key, 0), 0)
        if amount:
            province[field] = max(low, min(high, _i(province.get(field, 0), 0) + amount))

    city_fields = ("prosperity", "order", "health", "infrastructure", "culture", "loyalty", "food", "defense", "trade", "pollution")
    for key in city_fields:
        amount = _i(effects.get(key, 0), 0)
        if amount:
            city[key] = _clamp(_i(city.get(key, 50), 50) + amount, 0, 100, 50)
    population_delta = _i(effects.get("population", 0), 0)
    if population_delta:
        city["population"] = max(1, _i(city.get("population", 20), 20) + population_delta)
    if isinstance(effects.get("active_effect"), dict):
        city.setdefault("active_effects", []).append(copy.deepcopy(effects["active_effect"]))
        city["active_effects"] = city["active_effects"][-12:]
    return {key: _i(getattr(player, key if key != "science" else "science_points", 0), 0) - before[key] for key in before}


def _record(player: Any, ctx: dict, event: dict, option: dict, result_text: str) -> None:
    state = ensure_state(player, ctx)
    record = {
        "turn": _i(getattr(player, "turn", 1), 1, 1),
        "year": _i(getattr(player, "year", 0), 0),
        "event_id": event.get("event_id"),
        "title": event.get("title"),
        "province": event.get("province"),
        "city": event.get("city"),
        "choice": option.get("label"),
        "result": result_text,
        "category": event.get("category"),
    }
    state["history"].append(record)
    state["history"] = state["history"][-MAX_HISTORY:]
    log_event = ctx.get("log_event")
    if callable(log_event):
        try:
            log_event(player, f"{event.get('city')}, {event.get('province')}: {event.get('title')} — {option.get('label')}")
        except Exception:
            pass
    summary = ctx.get("turn_summary_add")
    if callable(summary):
        try:
            summary(player, f"{event.get('city')}: {event.get('title')} — {result_text}")
        except Exception:
            pass
    annales = ctx.get("ANNALES")
    if annales is not None and hasattr(annales, "record_event"):
        try:
            annales.record_event(
                player,
                category="province",
                title=f"{event.get('title')} в {event.get('city')}",
                text=f"{option.get('label')}. {result_text}",
                reason=f"Состояние города и провинции потребовало решения власти.",
                severity=2 if event.get("category") not in {"disaster", "military"} else 3,
                data={"province": event.get("province"), "city": event.get("city"), "event_id": event.get("event_id")},
            )
        except Exception:
            pass


def _update_status(city: dict) -> None:
    danger = min(city.get("order", 50), city.get("health", 50), city.get("loyalty", 50), city.get("food", 50))
    strength = (city.get("prosperity", 50) + city.get("infrastructure", 50) + city.get("culture", 50)) // 3
    if danger <= 22:
        city["status"] = "критический кризис"
    elif danger <= 38:
        city["status"] = "неустойчивый"
    elif strength >= 72 and danger >= 60:
        city["status"] = "цветущий"
    elif strength >= 58:
        city["status"] = "развивающийся"
    else:
        city["status"] = "стабильный"


def _tick_city(player: Any, province: dict, city: dict, ctx: dict) -> None:
    unrest = _i(province.get("unrest", 0), 0, 0, 10)
    garrison = _i(province.get("garrison", 0), 0, 0, 10)
    romanization = _clamp(province.get("romanization", 0), 0, 100, 0)
    wealth = _i(province.get("wealth", 2), 2, 0, 30)
    governor = _dict(getattr(player, "governors", {})).get(str(province.get("name")))
    governor_loyalty = _i(getattr(governor, "loyalty", 50), 50, 0, 100) if governor else 50

    # Медленные эндогенные изменения. Никакой показатель не прыгает сам по себе
    # на десятки пунктов: главные скачки происходят только через события.
    city["order"] = _clamp(city.get("order", 50) + (1 if garrison >= 2 else 0) - (1 if unrest >= 4 else 0), 0, 100, 50)
    city["loyalty"] = _clamp(city.get("loyalty", 50) + (1 if romanization >= 55 else 0) + (1 if governor_loyalty >= 70 else 0) - (1 if unrest >= 5 else 0), 0, 100, 50)
    city["prosperity"] = _clamp(city.get("prosperity", 50) + (1 if wealth >= 5 and city.get("order", 0) >= 55 else 0) - (1 if city.get("order", 0) <= 35 else 0), 0, 100, 50)
    city["trade"] = _clamp(city.get("trade", 40) + (1 if city.get("prosperity", 0) >= 65 else 0) - (1 if unrest >= 5 else 0), 0, 100, 40)
    city["culture"] = _clamp(city.get("culture", 30) + (1 if romanization >= 40 else 0), 0, 100, 30)
    city["infrastructure"] = _clamp(city.get("infrastructure", 45) - (1 if city.get("population", 0) >= 100 and random.random() < 0.35 else 0), 0, 100, 45)
    city["pollution"] = _clamp(city.get("pollution", 0) + (1 if city.get("population", 0) >= 80 else 0) - (1 if city.get("infrastructure", 0) >= 70 else 0), 0, 100, 0)
    city["health"] = _clamp(city.get("health", 55) + (1 if city.get("infrastructure", 0) >= 65 else 0) - (1 if city.get("pollution", 0) >= 35 else 0), 0, 100, 55)
    city["food"] = _clamp(city.get("food", 55) + (1 if wealth >= 4 else 0) - (1 if city.get("population", 0) >= 100 else 0), 0, 100, 55)

    growth_score = city.get("health", 50) + city.get("food", 50) + city.get("prosperity", 50) - 150
    if growth_score >= 45 and random.random() < 0.28:
        city["population"] = min(5000, _i(city.get("population", 20), 20) + 1)
    elif growth_score <= -45 and random.random() < 0.30:
        city["population"] = max(1, _i(city.get("population", 20), 20) - 1)

    # Длительные эффекты от решений.
    effects = []
    for effect in _list(city.get("active_effects")):
        if not isinstance(effect, dict):
            continue
        remaining = _i(effect.get("remaining", 0), 0) - 1
        tick = _dict(effect.get("tick"))
        if tick:
            _apply_effects(player, province, city, tick)
        if remaining > 0:
            effect["remaining"] = remaining
            effects.append(effect)
    city["active_effects"] = effects

    cooldowns = {}
    for event_id, turns in _dict(city.get("event_cooldowns")).items():
        turns = _i(turns, 0) - 1
        if turns > 0:
            cooldowns[str(event_id)] = turns
    city["event_cooldowns"] = cooldowns
    _update_status(city)


def _event_score(item: dict, player: Any, province: dict, city: dict, ctx: dict) -> float:
    score = float(_i(item.get("weight", 5), 5, 1, 100))
    event_id = str(item.get("id", ""))
    if event_id in _dict(city.get("event_cooldowns")):
        return 0.0
    if not _eligible(str(item.get("condition", "any")), player, province, city, ctx):
        return 0.0
    # Состояние города влияет на типы событий.
    category = item.get("category")
    if category == "disaster":
        score *= 0.65 + max(0, 60 - min(city.get("health", 50), city.get("infrastructure", 50))) / 45
    elif category in {"security", "military"}:
        score *= 0.75 + max(0, 65 - min(city.get("order", 50), city.get("defense", 50))) / 50
    elif category in {"economy", "trade"}:
        score *= 0.8 + city.get("trade", 40) / 100
    elif category in {"culture", "science", "religion"}:
        score *= 0.75 + city.get("culture", 30) / 110
    if city.get("last_event_turn", 0) == _i(getattr(player, "turn", 1), 1) - 1:
        score *= 0.35
    return max(0.0, score)


def _generate_event(player: Any, province: dict, city: dict, ctx: dict, excluded_ids: set[str]) -> dict | None:
    candidates: list[tuple[dict, float]] = []
    for item in CITY_EVENT_CATALOG:
        if item["id"] in excluded_ids:
            continue
        score = _event_score(item, player, province, city, ctx)
        if score > 0:
            candidates.append((item, score))
    if not candidates:
        return None
    selected = random.choices([x[0] for x in candidates], weights=[x[1] for x in candidates], k=1)[0]
    event_id = str(selected["id"])
    descriptions = {
        "harvest_boom": "Сельская округа сообщает о редком изобилии. Решение о судьбе излишков ждёт Рима.",
        "grain_shortage": "Цена хлеба растёт, толпа собирается у пекарен, а муниципальные амбары быстро пустеют.",
        "market_fair": "В город прибыли купцы из нескольких провинций; магистраты просят определить режим ярмарки.",
        "guild_dispute": "Коллегии мастеров остановили работу и обвиняют друг друга в нарушении договоров.",
        "aqueduct_failure": "Обрушение участка водовода лишило водой несколько кварталов.",
        "epidemic": "В бедных кварталах множатся внезапные смерти; врачи требуют немедленных мер.",
        "urban_fire": "Огонь охватил тесные жилые кварталы и угрожает складам.",
        "river_flood": "Вода вышла из берегов, затопила поля и нижние улицы.",
        "earthquake": "Подземный толчок повредил дома, стены и общественные здания.",
        "banditry": "Караваны избегают дорог, а сборщики налогов требуют вооружённого сопровождения.",
        "tax_resistance": "Горожане отвергают новую оценку имущества и обвиняют чиновников в произволе.",
        "governor_corruption": "В Рим доставлены свидетельства незаконных поборов и продажи судебных решений.",
        "veteran_colony": "Отслужившие солдаты просят землю и право основать колонию.",
        "elite_petition": "Декурионы и богатые домовладельцы прибыли с просьбой о новых правах.",
        "citizenship_debate": "Муниципий расколот спором: кому должны принадлежать римские права.",
        "religious_procession": "Жрецы и общины готовят церемонию, способную собрать весь город.",
        "cult_conflict": "Соперничающие культовые общины обвиняют друг друга в святотатстве.",
        "philosopher_school": "Известный наставник предлагает основать школу и библиотеку.",
        "engineering_breakthrough": "Местные инженеры представили новый способ строительства и просят покровительства.",
        "port_congestion": "Суда неделями ждут разгрузки, товары портятся, портовые сборщики спорят о порядке.",
        "piracy_rumors": "Капитаны сообщают о неизвестных кораблях, следящих за торговыми маршрутами.",
        "slave_unrest": "Стража раскрыла тайные собрания рабов и подозревает подготовку мятежа.",
        "gladiatorial_games": "Народ и магистраты просят зрелищ, чтобы отметить общественный праздник.",
        "urban_migration": "Тысячи людей ищут работу и жильё внутри городских стен.",
        "wall_repairs": "Инженеры предупреждают: часть укреплений не выдержит серьёзной осады.",
        "frontier_refugees": "К воротам пришли семьи, бежавшие от войны и набегов.",
        "coin_shortage": "Торговцы не могут разменивать крупную монету, сделки переходят в долг и бартер.",
        "local_festival": "Город просит подтвердить старинный праздник и участие римской власти.",
        "smuggling_ring": "Таможенники обнаружили сеть тайных складов и покровителей среди знати.",
        "municipal_rivalry": "Два города провинции спорят о первенстве, почестях и распределении средств.",
        "raid_warning": "Разведчики заметили движение вооружённых отрядов к границе провинции.",
        "provincial_census": "Настало время уточнить население, имущество и налоговые обязательства.",
    }
    return {
        "id": f"CE-{getattr(player, 'turn', 1)}-{random.randint(10000, 99999)}",
        "event_id": event_id,
        "title": selected["title"],
        "category": selected["category"],
        "icon": selected.get("icon", "🏙"),
        "province": str(province.get("name", "Провинция")),
        "city": str(city.get("name", "Город")),
        "description": descriptions.get(event_id, "Муниципальные власти ожидают решения Рима."),
        "created_turn": _i(getattr(player, "turn", 1), 1, 1),
        "options": _build_options(event_id, player, province, city),
    }


def _auto_choice(player: Any, event: dict) -> dict:
    affordable = [o for o in _list(event.get("options")) if isinstance(o, dict) and _can_afford(player, o)]
    if not affordable:
        affordable = [o for o in _list(event.get("options")) if isinstance(o, dict)]
    if not affordable:
        return _option("1", "Не вмешиваться", "", {}, ai=1)
    return max(affordable, key=lambda o: _i(o.get("ai", 50), 50))


def resolve_event(player: Any, event: dict, option: dict, ctx: dict | None = None) -> str:
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    province = _province_map(player).get(str(event.get("province")))
    city = state["cities"].get(_city_key(str(event.get("province")), str(event.get("city"))))
    if not isinstance(province, dict) or not isinstance(city, dict):
        return "Событие утратило актуальность: город больше не находится под властью Рима."
    if not _can_afford(player, option):
        option = _auto_choice(player, event)
    effects = _dict(option.get("effects"))
    _apply_effects(player, province, city, effects)
    event_id = str(event.get("event_id", "event"))
    city.setdefault("event_cooldowns", {})[event_id] = random.randint(5, 9)
    city["last_event_turn"] = _i(getattr(player, "turn", 1), 1)
    _update_status(city)
    result = _effect_text(effects)
    _record(player, ctx, event, option, result)
    return result


def present_pending_events(player: Any, ctx: dict | None = None) -> int:
    ctx = _ctx(ctx)
    ui = UI(ctx)
    state = ensure_state(player, ctx)
    pending = [x for x in _list(state.get("pending")) if isinstance(x, dict)]
    state["pending"] = []
    if not pending:
        return 0
    resolved = 0
    for index, event in enumerate(pending, 1):
        ui.screen()
        ui.header("CIVITATES ET PROVINCIAE", event.get("icon", "🏙"), f"Городское событие {index}/{len(pending)} после завершения хода")
        ui.info(f"{event.get('city')} • {event.get('province')} • {CATEGORY_LABELS.get(event.get('category'), event.get('category'))}", "CYAN")
        ui.section(str(event.get("title", "Городское событие")), "GOLD")
        ui.wrap(event.get("description", ""), "WHITE")
        valid = []
        for option in _list(event.get("options")):
            if not isinstance(option, dict):
                continue
            key = str(option.get("key", len(valid) + 1)).upper()
            valid.append(key)
            req = _dict(option.get("requires"))
            costs = []
            if _i(req.get("gold", 0), 0): costs.append(f"{_i(req['gold'])} зол.")
            if _i(req.get("grain", 0), 0): costs.append(f"{_i(req['grain'])} зерна")
            if _i(req.get("faith", 0), 0): costs.append(f"{_i(req['faith'])} веры")
            affordability = "" if _can_afford(player, option) else " [НЕДОСТАТОЧНО РЕСУРСОВ]"
            cost_text = f" ({', '.join(costs)})" if costs else ""
            print(ui.color(f"\n  {key}. {option.get('label')}{cost_text}{affordability}", "GREEN" if _can_afford(player, option) else "RED", True))
            ui.wrap(option.get("desc", ""), "GRAY")
            ui.info("Последствия: " + _effect_text(_dict(option.get("effects"))), "CYAN")
        answer = ui.choice("\n  Решение Рима: ", valid)
        chosen = next((o for o in _list(event.get("options")) if str(o.get("key", "")).upper() == answer), None)
        if not isinstance(chosen, dict) or not _can_afford(player, chosen):
            affordable = [o for o in _list(event.get("options")) if isinstance(o, dict) and _can_afford(player, o)]
            if not affordable:
                chosen = _auto_choice(player, event)
            else:
                ui.info("Выбранный приказ невозможно оплатить; принят наиболее близкий доступный вариант.", "GOLD")
                chosen = affordable[0]
        result = resolve_event(player, event, chosen, ctx)
        ui.section("Решение исполнено", "GREEN")
        ui.info(result, "GREEN")
        resolved += 1
        ui.pause()
    return resolved


def process_turn(player: Any, ctx: dict | None = None, interactive: bool = True) -> list[dict]:
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 1), 1, 1)
    if state.get("last_tick_turn") >= turn:
        if interactive and state.get("pending"):
            present_pending_events(player, ctx)
        return []
    state["last_tick_turn"] = turn
    provinces = _province_map(player)
    active_cities = []
    for row in state["cities"].values():
        if not isinstance(row, dict) or not row.get("active"):
            continue
        province = provinces.get(str(row.get("province")))
        if not isinstance(province, dict):
            continue
        _tick_city(player, province, row, ctx)
        active_cities.append((province, row))
    if not active_cities:
        return []

    # Гарантирован хотя бы один городской сюжет за ход; крупная держава может
    # получить два-три, но поток ограничен, чтобы не превращать ход в спам.
    province_count = len(provinces)
    slots = min(3, 1 + province_count // 8)
    if turn <= 3:
        slots = 1
    selected_events: list[dict] = []
    used_cities: set[str] = set()
    used_ids: set[str] = set()
    pool = list(active_cities)
    for _ in range(slots):
        if not pool:
            break
        weighted = []
        for province, city in pool:
            pressure = 100 - min(city.get("order", 50), city.get("health", 50), city.get("loyalty", 50))
            weight = 1.0 + pressure / 65 + city.get("population", 20) / 220
            weighted.append(max(0.2, weight))
        province, city = random.choices(pool, weights=weighted, k=1)[0]
        event = _generate_event(player, province, city, ctx, used_ids)
        key = _city_key(str(province.get("name")), str(city.get("name")))
        pool = [(p, c) for p, c in pool if _city_key(str(p.get("name")), str(c.get("name"))) != key]
        if not event:
            continue
        selected_events.append(event)
        used_cities.add(key)
        used_ids.add(str(event.get("event_id")))

    state["pending"].extend(selected_events)
    state["pending"] = state["pending"][-MAX_PENDING:]
    if interactive:
        present_pending_events(player, ctx)
    elif state["settings"].get("auto_resolve_noninteractive", True):
        pending = list(state["pending"])
        state["pending"] = []
        for event in pending:
            resolve_event(player, event, _auto_choice(player, event), ctx)
    return selected_events


def empire_metrics(player: Any, ctx: dict | None = None) -> dict[str, float]:
    state = ensure_state(player, ctx)
    cities = [x for x in state["cities"].values() if isinstance(x, dict) and x.get("active")]
    if not cities:
        return {"cities": 0, "population": 0, "prosperity": 0, "order": 0, "health": 0, "loyalty": 0, "infrastructure": 0, "crisis_cities": 0}
    def avg(key: str) -> float:
        return sum(_f(c.get(key, 0), 0.0) for c in cities) / len(cities)
    return {
        "cities": len(cities),
        "population": sum(_i(c.get("population", 0), 0) for c in cities),
        "prosperity": avg("prosperity"), "order": avg("order"), "health": avg("health"),
        "loyalty": avg("loyalty"), "infrastructure": avg("infrastructure"),
        "crisis_cities": sum(1 for c in cities if c.get("status") in {"неустойчивый", "критический кризис"}),
    }


def _city_rows_for_province(state: dict, province_name: str) -> list[dict]:
    rows = [c for c in _dict(state.get("cities")).values() if isinstance(c, dict) and c.get("active") and c.get("province") == province_name]
    return sorted(rows, key=lambda c: (-_i(c.get("population", 0), 0), str(c.get("name", ""))))


def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx)
    ui = UI(ctx)
    state = ensure_state(player, ctx)
    while True:
        ui.screen()
        ui.header("CIVITATES ET PROVINCIAE", "🏙", f"Городская система {MODULE_VERSION}")
        metrics = empire_metrics(player, ctx)
        ui.info(
            f"Городов: {int(metrics['cities'])} • население: {int(metrics['population'])} тыс. • "
            f"процветание: {metrics['prosperity']:.0f} • порядок: {metrics['order']:.0f} • "
            f"здоровье: {metrics['health']:.0f} • кризисных городов: {int(metrics['crisis_cities'])}",
            "CYAN",
        )
        provinces = sorted({str(c.get("province")) for c in state["cities"].values() if isinstance(c, dict) and c.get("active")})
        ui.section("Провинции", "GOLD")
        for index, pname in enumerate(provinces, 1):
            rows = _city_rows_for_province(state, pname)
            avg_order = sum(c.get("order", 0) for c in rows) / max(1, len(rows))
            avg_loyalty = sum(c.get("loyalty", 0) for c in rows) / max(1, len(rows))
            print(f"  {index}. {pname} — {len(rows)} гор.; порядок {avg_order:.0f}; лояльность {avg_loyalty:.0f}")
        print("\n  H. Архив городских событий")
        print("  Q. Назад")
        valid = [str(i) for i in range(1, len(provinces) + 1)] + ["H", "Q"]
        answer = ui.choice("\n  Выбор: ", valid)
        if answer == "Q":
            return
        if answer == "H":
            ui.screen(); ui.header("АРХИВ ГОРОДСКИХ СОБЫТИЙ", "📜")
            history = _list(state.get("history"))[-30:]
            if not history:
                ui.info("Архив пока пуст.", "GRAY")
            else:
                rows = [(x.get("turn"), x.get("city"), x.get("title"), x.get("choice")) for x in reversed(history)]
                ui.table("Последние решения", ["Ход", "Город", "Событие", "Решение"], rows, "GOLD")
            ui.pause(); continue
        pname = provinces[int(answer) - 1]
        rows = _city_rows_for_province(state, pname)
        ui.screen(); ui.header(pname.upper(), "🏛", "Муниципальная ведомость")
        table_rows = [
            (
                c.get("name"), c.get("population"), c.get("prosperity"), c.get("order"),
                c.get("health"), c.get("loyalty"), c.get("infrastructure"), c.get("status"),
            )
            for c in rows
        ]
        ui.table("Города", ["Город", "Нас.", "Процв.", "Поряд.", "Здор.", "Лоял.", "Инфр.", "Статус"], table_rows, "CYAN")
        ui.pause()

# ─── OPERA PUBLICA v3.2: MUNICIPAL CONSTRUCTION ────────────────────────────
BUILDINGS_IMPORT_ERROR = ""
try:
    import roma_buildings as BUILDINGS
except Exception as _buildings_import_error:
    BUILDINGS = None
    BUILDINGS_IMPORT_ERROR = f"{type(_buildings_import_error).__name__}: {_buildings_import_error}"

MODULE_VERSION = "1.1.0-opera-publica"
SCHEMA_VERSION = 2

_ensure_state_before_buildings = ensure_state
def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    state = _ensure_state_before_buildings(player, ctx)
    state.setdefault("last_project_turn", 0)
    state.setdefault("last_building_yield_turn", 0)
    state.setdefault("building_history", [])
    state["building_history"] = [x for x in _list(state.get("building_history")) if isinstance(x, dict)][-240:]
    state["schema"] = SCHEMA_VERSION
    state["version"] = MODULE_VERSION
    if BUILDINGS is not None:
        for city in _dict(state.get("cities")).values():
            if isinstance(city, dict):
                BUILDINGS.ensure_city(city)
    player.city_system = state
    return state


def building_economy_snapshot(player: Any, ctx: dict | None = None) -> dict:
    ensure_state(player, ctx)
    if BUILDINGS is None:
        return {
            "gold_per_turn": 0, "grain_per_turn": 0, "science_per_turn": 0,
            "faith_per_turn": 0, "upkeep": 0, "resource_output": {},
            "resource_input": {}, "sector_bonuses": {},
            "province_sector_bonuses": {}, "building_count": 0,
        }
    return BUILDINGS.economy_snapshot(player, _ctx(ctx))


_resolve_event_before_buildings = resolve_event
def resolve_event(player: Any, event: dict, option: dict, ctx: dict | None = None) -> str:
    ctx = _ctx(ctx)
    if event.get("kind") != "building_project" or BUILDINGS is None:
        return _resolve_event_before_buildings(player, event, option, ctx)
    state = ensure_state(player, ctx)
    province = _province_map(player).get(str(event.get("province")))
    city = state["cities"].get(_city_key(str(event.get("province")), str(event.get("city"))))
    if not isinstance(province, dict) or not isinstance(city, dict):
        return "Проект утратил актуальность: город больше не находится под властью Рима."
    result = BUILDINGS.execute_project(player, province, city, option, ctx)
    building_id = str(event.get("building_id", option.get("building_id", "")))
    building = BUILDINGS.BUILDING_CATALOG.get(building_id, {})
    action = str(option.get("project_action", ""))
    if action.startswith("build") and building_id in city.get("buildings", []):
        state["building_history"].append({
            "turn": _i(getattr(player, "turn", 1), 1), "province": province.get("name"),
            "city": city.get("name"), "building_id": building_id,
            "building": building.get("name", building_id), "action": action,
        })
        state["building_history"] = state["building_history"][-240:]
    city["last_event_turn"] = _i(getattr(player, "turn", 1), 1)
    _update_status(city)
    _record(player, ctx, event, option, result)
    return result


_auto_choice_before_buildings = _auto_choice
def _auto_choice(player: Any, event: dict) -> dict:
    if event.get("kind") == "building_project" and BUILDINGS is not None:
        state = ensure_state(player, {})
        city = state["cities"].get(_city_key(str(event.get("province")), str(event.get("city"))), {})
        for option in _list(event.get("options")):
            if isinstance(option, dict) and str(option.get("project_action", "")).startswith("build"):
                if BUILDINGS.can_execute(player, city, option, {}):
                    return option
        return next((o for o in _list(event.get("options")) if o.get("project_action") == "defer"), _list(event.get("options"))[-1])
    return _auto_choice_before_buildings(player, event)


_present_pending_before_buildings = present_pending_events
def present_pending_events(player: Any, ctx: dict | None = None) -> int:
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    pending = [x for x in _list(state.get("pending")) if isinstance(x, dict)]
    projects = [x for x in pending if x.get("kind") == "building_project"]
    normal = [x for x in pending if x.get("kind") != "building_project"]
    if not projects:
        return _present_pending_before_buildings(player, ctx)

    state["pending"] = normal
    ui = UI(ctx)
    resolved = 0
    for index, event in enumerate(projects, 1):
        ui.screen()
        ui.header("OPERA PUBLICA", "🏗", f"Муниципальный проект {index}/{len(projects)} после завершения хода")
        ui.info(f"{event.get('city')} • {event.get('province')}", "CYAN")
        ui.section(str(event.get("title", "Городская строительная инициатива")), "GOLD")
        ui.wrap(event.get("description", ""), "WHITE")
        valid: list[str] = []
        city = state["cities"].get(_city_key(str(event.get("province")), str(event.get("city"))), {})
        for option in _list(event.get("options")):
            if not isinstance(option, dict):
                continue
            key = str(option.get("key", len(valid) + 1)).upper()
            valid.append(key)
            req = _dict(option.get("requires"))
            costs = []
            if _i(req.get("gold", 0), 0): costs.append(f"{_i(req['gold'])} зол.")
            if _i(req.get("grain", 0), 0): costs.append(f"{_i(req['grain'])} зерна")
            for resource, amount in _dict(req.get("resources")).items():
                costs.append(f"{BUILDINGS.resource_name(resource, ctx)} ×{_f(amount):g}")
            affordable = BUILDINGS.can_execute(player, city, option, ctx)
            suffix = "" if affordable else " [НЕДОСТАТОЧНО СРЕДСТВ ИЛИ МАТЕРИАЛОВ]"
            cost_text = f" ({', '.join(costs)})" if costs else ""
            print(ui.color(f"\n  {key}. {option.get('label')}{cost_text}{suffix}", "GREEN" if affordable else "RED", True))
            ui.wrap(option.get("desc", ""), "GRAY")
        answer = ui.choice("\n  Решение Рима: ", valid)
        chosen = next((o for o in _list(event.get("options")) if str(o.get("key", "")).upper() == answer), None)
        if not isinstance(chosen, dict) or not BUILDINGS.can_execute(player, city, chosen, ctx):
            ui.info("Выбранный подряд невозможно исполнить; проект отложен.", "GOLD")
            chosen = next((o for o in _list(event.get("options")) if o.get("project_action") == "defer"), _list(event.get("options"))[-1])
        result = resolve_event(player, event, chosen, ctx)
        ui.section("Постановление исполнено", "GREEN")
        ui.wrap(result, "GREEN")
        resolved += 1
        ui.pause()

    if normal:
        resolved += _present_pending_before_buildings(player, ctx)
    return resolved


_process_turn_before_buildings = process_turn
def process_turn(player: Any, ctx: dict | None = None, interactive: bool = True) -> list[dict]:
    ctx = _ctx(ctx)
    state = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 1), 1, 1)
    generated: list[dict] = []
    if BUILDINGS is not None and _i(state.get("last_project_turn", 0), 0) < turn:
        provinces = _province_map(player)
        active: list[tuple[dict, dict]] = []
        for city in _dict(state.get("cities")).values():
            if not isinstance(city, dict) or not city.get("active"):
                continue
            province = provinces.get(str(city.get("province")))
            if not isinstance(province, dict):
                continue
            BUILDINGS.tick_city(city)
            active.append((province, city))
        slots = min(2, 1 + max(0, len(provinces) - 12) // 18)
        for province, city, building in BUILDINGS.select_projects(player, active, ctx, limit=slots):
            generated.append(BUILDINGS.make_project_event(player, province, city, building, ctx))
        state["pending"].extend(generated)
        state["pending"] = state["pending"][-MAX_PENDING:]
        state["last_project_turn"] = turn
        passive = BUILDINGS.apply_passive_civic_yields(player, ctx)
        if passive.get("science") or passive.get("faith"):
            summary = ctx.get("turn_summary_add")
            if callable(summary):
                summary(player, f"Муниципальные учреждения: +{passive.get('science', 0)} науки, +{passive.get('faith', 0)} веры")
    story_events = _process_turn_before_buildings(player, ctx, interactive)
    return generated + list(story_events or [])


_empire_metrics_before_buildings = empire_metrics
def empire_metrics(player: Any, ctx: dict | None = None) -> dict[str, float]:
    result = _empire_metrics_before_buildings(player, ctx)
    snap = building_economy_snapshot(player, ctx)
    result["buildings"] = float(snap.get("building_count", 0))
    result["building_gold"] = float(snap.get("gold_per_turn", 0))
    result["building_grain"] = float(snap.get("grain_per_turn", 0))
    result["building_upkeep"] = float(snap.get("upkeep", 0))
    return result


_open_menu_before_buildings = open_menu
def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx)
    ui = UI(ctx)
    state = ensure_state(player, ctx)
    while True:
        ui.screen()
        ui.header("CIVITATES ET OPERA PUBLICA", "🏙", f"Города и муниципальные сооружения • {MODULE_VERSION}")
        metrics = empire_metrics(player, ctx)
        ui.info(
            f"Городов: {int(metrics.get('cities', 0))} • зданий: {int(metrics.get('buildings', 0))} • "
            f"доход зданий: +{int(metrics.get('building_gold', 0))} зол./ход, +{int(metrics.get('building_grain', 0))} зерна/ход • "
            f"содержание: {int(metrics.get('building_upkeep', 0))} зол./ход",
            "CYAN",
        )
        provinces = sorted({str(c.get("province")) for c in state["cities"].values() if isinstance(c, dict) and c.get("active")})
        ui.section("Провинции", "GOLD")
        for index, pname in enumerate(provinces, 1):
            rows = _city_rows_for_province(state, pname)
            count = sum(len(_list(c.get("buildings"))) for c in rows)
            print(f"  {index}. {pname} — {len(rows)} гор.; сооружений {count}")
        print("\n  H. Архив городских решений")
        print("  Q. Назад")
        answer = ui.choice("\n  Выбор: ", [str(i) for i in range(1, len(provinces) + 1)] + ["H", "Q"])
        if answer == "Q": return
        if answer == "H":
            history = _list(state.get("history"))[-30:]
            ui.screen(); ui.header("АРХИВ ГОРОДСКИХ РЕШЕНИЙ", "📜")
            if history:
                ui.table("Последние решения", ["Ход", "Город", "Событие", "Решение"], [(x.get("turn"), x.get("city"), x.get("title"), x.get("choice")) for x in reversed(history)], "GOLD")
            else: ui.info("Архив пока пуст.", "GRAY")
            ui.pause(); continue
        pname = provinces[int(answer) - 1]
        rows = _city_rows_for_province(state, pname)
        ui.screen(); ui.header(pname.upper(), "🏛", "Муниципальная ведомость")
        ui.table("Города", ["#", "Город", "Тип", "Нас.", "Процв.", "Поряд.", "Зданий"], [
            (i, c.get("name"), c.get("type"), c.get("population"), c.get("prosperity"), c.get("order"), len(_list(c.get("buildings"))))
            for i, c in enumerate(rows, 1)
        ], "CYAN")
        choice = ui.choice("\n  Открыть город (номер) или Q: ", [str(i) for i in range(1, len(rows) + 1)] + ["Q"])
        if choice == "Q": continue
        city = rows[int(choice) - 1]
        ui.screen(); ui.header(str(city.get("name", "ГОРОД")).upper(), "🏗", f"{pname} • {city.get('type', 'город')}")
        built = [BUILDINGS.BUILDING_CATALOG.get(x) for x in _list(city.get("buildings"))] if BUILDINGS is not None else []
        built = [x for x in built if isinstance(x, dict)]
        if not built:
            ui.info("Построек пока нет. Муниципий выдвинет инициативу после завершения хода.", "GRAY")
        else:
            ui.table("Построенные сооружения", ["Сооружение", "Зол./ход", "Зерно/ход", "Содержание"], [
                (b.get("name"), _dict(b.get("effects")).get("gold_per_turn", 0), _dict(b.get("effects")).get("grain_per_turn", 0), b.get("upkeep", 0)) for b in built
            ], "GOLD")
        ui.pause()
