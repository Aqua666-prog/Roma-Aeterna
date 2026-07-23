#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna 1.1 — BELLA REGNORUM PROVINCIALIA.

Прямые войны Рима с иностранными государствами. Каждая держава выставляет
собственные армии из национального ростера, воюет по уникальной доктрине,
держит устойчивые фронты и принимает политические решения. Главные кампании,
ультиматумы и мирные переговоры автоматически открываются после хода через
Consilium Orbis и проходят в несколько стадий.

Публичный контракт:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None)
    declare_war(player, power_key, ctx=None, reason='roman_declaration')
    handle_council_event(player, event, ctx, ui)
    expire_council_event(player, event, ctx)
    open_province_menu(player, province_name, ctx=None)
    open_menu(player, ctx=None)
"""
from __future__ import annotations

import copy
import random
import re
import textwrap
import uuid
from typing import Any

MODULE_VERSION = "1.1.0-provincial-fronts"
SCHEMA_VERSION = 1
MAX_HISTORY = 260


def _i(value: Any, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError, OverflowError): value = default
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
    def header(self, title: str, icon: str = "⚔", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try: fn(title, icon, getattr(self.C, "RED", ""), subtitle); return
            except TypeError:
                try: fn(title, icon, getattr(self.C, "RED", ""))
                except Exception: pass
        print(self.color(f"\n{'═' * 76}\n  {icon} {title}\n{'═' * 76}", "RED", True))
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
            for i, value in enumerate(clean[:len(widths)]): widths[i] = min(34, max(widths[i], len(value)))
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


FRONTS = {
    "carthage": ["Sicilia", "Africa Proconsularis", "Sardinia"],
    "numidia": ["Numidia", "Africa Proconsularis", "Mauretania"],
    "pergamon": ["Asia Minor", "Macedonia", "Achaea"],
    "parthia": ["Syria", "Asia Minor", "Armenia"],
    "egypt": ["Aegyptus", "Cyrenaica", "Syria"],
    "gauls": ["Gallia", "Gallia Narbonensis", "Cisalpine Gaul"],
}

DOCTRINES = {
    "carthage": {"name": "Пуническое удушение", "favored": "harass", "attack": 7, "defense": 4, "mobility": 5, "text": "Флот режет снабжение, наёмники связывают легионы, а удар наносится по казне и портам."},
    "numidia": {"name": "Война без фронта", "favored": "feigned", "attack": 4, "defense": 1, "mobility": 12, "text": "Конница избегает тяжёлой битвы, окружает обозы и исчезает до римской контратаки."},
    "pergamon": {"name": "Эллинистическая оборона", "favored": "defensive", "attack": 2, "defense": 10, "mobility": 0, "text": "Фаланга держит узлы дорог, инженеры укрепляют лагеря, союзники прикрывают фланги."},
    "parthia": {"name": "Стратегическая глубина", "favored": "feigned", "attack": 10, "defense": 4, "mobility": 13, "text": "Конные лучники выманивают легионы, катафракты добивают растянутый строй."},
    "egypt": {"name": "Оборона Нила", "favored": "defensive", "attack": 3, "defense": 9, "mobility": 2, "text": "Держава опирается на крепости, флот, зерновые запасы и наёмные гарнизоны."},
    "gauls": {"name": "Война вождей", "favored": "shock", "attack": 11, "defense": 1, "mobility": 7, "text": "Вожди ищут быстрой славы: засада, массовый натиск и попытка сломить мораль одним ударом."},
}

ROMAN_TACTICS = {
    "1": {"id": "disciplined", "name": "Методичное манипулярное наступление", "attack": 7, "defense": 5, "counter": ["shock"]},
    "2": {"id": "fortified", "name": "Укреплённый лагерь и изматывание", "attack": 1, "defense": 11, "counter": ["harass", "feigned"]},
    "3": {"id": "rapid", "name": "Стремительный марш и навязывание боя", "attack": 8, "defense": 1, "counter": ["defensive"]},
    "4": {"id": "screening", "name": "Ауксилия, разведка и прикрытие флангов", "attack": 4, "defense": 7, "counter": ["feigned", "harass"]},
    "5": {"id": "siege", "name": "Давление на города и коммуникации", "attack": 9, "defense": 0, "counter": ["defensive"]},
}


def _nation(ctx: dict, key: str) -> dict:
    module = ctx.get("NATIONS")
    if module is not None and hasattr(module, "get_nation"):
        try: return module.get_nation(key)
        except Exception: pass
    return {"name": key, "units": [], "war_doctrine": "обычная война", "icon": "⚔"}


def _roster(ctx: dict, key: str) -> list[dict]:
    module = ctx.get("NATIONS")
    if module is not None and hasattr(module, "get_roster"):
        try: return module.get_roster(key)
        except Exception: pass
    return []


def _world_enqueue(player: Any, ctx: dict, **kwargs: Any) -> bool:
    council = ctx.get("WORLD_COUNCIL")
    if council is None or not hasattr(council, "enqueue"): return False
    return council.enqueue(player, ctx=ctx, **kwargs) is not None


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    state = getattr(player, "foreign_warfare", None)
    if not isinstance(state, dict): state = {}; player.foreign_warfare = state
    state.setdefault("schema", SCHEMA_VERSION); state.setdefault("version", MODULE_VERSION)
    state.setdefault("wars", {}); state.setdefault("history", []); state.setdefault("last_tick_turn", 0)
    wars = {}
    for key, war in _dict(state.get("wars")).items():
        if not isinstance(war, dict): continue
        war.setdefault("id", uuid.uuid4().hex[:10]); war.setdefault("power", str(key)); war.setdefault("status", "active")
        war.setdefault("started_turn", _i(getattr(player, "turn", 1), 1)); war.setdefault("reason", "war")
        war.setdefault("war_score", 0); war.setdefault("roman_weariness", 0); war.setdefault("enemy_weariness", 0)
        war.setdefault("front", random.choice(FRONTS.get(str(key), ["Mediterraneum"])))
        war.setdefault("enemy_armies", []); war.setdefault("campaigns", 0); war.setdefault("next_campaign_turn", _i(getattr(player, "turn", 1), 1))
        war.setdefault("last_result", "война только началась"); war.setdefault("peace_offered", False)
        war["war_score"] = _i(war.get("war_score", 0), 0, -100, 100); war["roman_weariness"] = _clamp(war.get("roman_weariness", 0), 0, 100, 0); war["enemy_weariness"] = _clamp(war.get("enemy_weariness", 0), 0, 100, 0)
        war["campaigns"] = _i(war.get("campaigns", 0), 0, 0); war["next_campaign_turn"] = _i(war.get("next_campaign_turn", 1), 1, 1)
        armies = []
        for army in _list(war.get("enemy_armies")):
            if not isinstance(army, dict): continue
            army.setdefault("id", uuid.uuid4().hex[:10]); army.setdefault("name", "Иностранная армия")
            army.setdefault("units", []); army.setdefault("strength", 80); army.setdefault("morale", 75); army.setdefault("experience", 10)
            army.setdefault("commander", "неизвестный полководец"); army.setdefault("front", war["front"]); army.setdefault("status", "field")
            army["strength"] = _clamp(army.get("strength", 80), 0, 160, 80); army["morale"] = _clamp(army.get("morale", 75), 0, 100, 75); army["experience"] = _clamp(army.get("experience", 10), 0, 100, 10)
            army["units"] = [str(x) for x in _list(army.get("units"))][-8:]
            armies.append(army)
        war["enemy_armies"] = armies
        if war.get("status") == "active": wars[str(key)] = war
    state["wars"] = wars
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state["last_tick_turn"] = _i(state.get("last_tick_turn", 0), 0, 0)
    state["schema"] = SCHEMA_VERSION; state["version"] = MODULE_VERSION
    player.foreign_warfare = state
    return state


def _record(player: Any, ctx: dict, title: str, text: str, power: str | None = None, severity: int = 3) -> None:
    state = ensure_state(player, ctx)
    item = {"turn": _i(getattr(player, "turn", 1), 1), "power": power, "title": title, "text": text}
    state["history"].append(item); state["history"] = state["history"][-MAX_HISTORY:]
    log = ctx.get("log_event")
    if callable(log):
        try: log(player, f"{title}: {text}")
        except Exception: pass
    summary = ctx.get("turn_summary_add")
    if callable(summary):
        try: summary(player, f"{title}: {text}")
        except Exception: pass
    annales = ctx.get("ANNALES")
    if annales is not None and hasattr(annales, "record_event"):
        try: annales.record_event(player, category="military", title=title, text=text, reason="Прямая война с иностранной державой.", severity=severity, data={"power": power, "system": "bella_regnorum"})
        except Exception: pass


def _enemy_ai_state(player: Any, key: str) -> dict:
    return _dict(_dict(_dict(getattr(player, "diplomatic_ai", {})).get("powers", {})).get(key))


def _create_army(player: Any, key: str, ctx: dict, index: int = 1) -> dict:
    nation = _nation(ctx, key); roster = _roster(ctx, key); ai = _enemy_ai_state(player, key)
    if not roster:
        roster = [{"id": "levy", "name": "Ополчение", "attack": 11, "defense": 11, "mobility": 8, "trait": "массовость"}]
    weights = [max(1, _i(u.get("cost", 10), 10)) for u in roster]
    unit_count = 3 if len(roster) >= 3 else len(roster)
    selected: list[str] = []
    while len(selected) < max(1, unit_count):
        u = random.choices(roster, weights=weights, k=1)[0]
        if u["id"] not in selected or len(selected) >= len(roster): selected.append(u["id"])
    readiness = _i(ai.get("readiness", 60), 60)
    base = _clamp(55 + readiness // 2 + random.randint(-8, 12), 40, 130, 85)
    commander_pool = {
        "carthage": ["Адгербал Баркид", "Бомилькар Ганнонид", "Гискон Магон"],
        "numidia": ["Мастанабал", "Иемпсал", "Нарава"],
        "pergamon": ["Меноген", "Афиней", "Андроник"],
        "parthia": ["Сурена", "Карен", "Михрдат"],
        "egypt": ["Диоскурид", "Птолемей Кипрский", "Пелопс"],
        "gauls": ["Бренн", "Луктерий", "Критогнат"],
    }.get(key, ["Иностранный стратег"])
    return {
        "id": uuid.uuid4().hex[:10], "name": f"{nation.get('name', key)}: армия {index}", "units": selected,
        "strength": base, "morale": _clamp(65 + random.randint(-5, 15), 45, 95, 72),
        "experience": _clamp(10 + _i(ai.get("readiness", 50), 50) // 4 + random.randint(-4, 8), 5, 60, 25),
        "commander": random.choice(commander_pool), "front": random.choice(FRONTS.get(key, ["Mediterraneum"])), "status": "field",
    }


def declare_war(player: Any, power_key: str, ctx: dict | None = None, reason: str = "roman_declaration") -> dict | None:
    ctx = _ctx(ctx); state = ensure_state(player, ctx); diplomacy = _dict(getattr(player, "diplomacy", {})); row = _dict(diplomacy.get(power_key))
    if not row: return None
    if power_key in state["wars"]:
        return state["wars"].get(power_key)
    already_at_war = bool(row.get("at_war"))
    row["at_war"] = True; row["war_started_turn"] = _i(row.get("war_started_turn", 0), 0) or _i(getattr(player, "turn", 1), 1)
    # При войне, объявленной стратегическим ИИ, договоры могли быть разорваны
    # ещё в Orbis Politicus. Повторная нормализация безопасна и гарантирует,
    # что прямой военный слой не унаследует невозможный союз с противником.
    row["alliance"] = False; row["non_aggression"] = False; row["trade_pact"] = False; row["client"] = False
    row["tension"] = 100; row["disposition"] = min(_i(row.get("disposition", 50), 50), 12); row["trust"] = min(_i(row.get("trust", 40), 40), 8)
    ai = _enemy_ai_state(player, power_key); army_count = 1 + (1 if _i(ai.get("readiness", 55), 55) >= 72 else 0)
    war = {
        "id": uuid.uuid4().hex[:10], "power": power_key, "status": "active", "started_turn": _i(getattr(player, "turn", 1), 1),
        "reason": reason, "war_score": 0, "roman_weariness": 0, "enemy_weariness": 0,
        "front": random.choice(FRONTS.get(power_key, ["Mediterraneum"])),
        "enemy_armies": [_create_army(player, power_key, ctx, i + 1) for i in range(army_count)],
        "campaigns": 0, "next_campaign_turn": _i(getattr(player, "turn", 1), 1), "last_result": "объявлена война", "peace_offered": False,
    }
    state["wars"][power_key] = war
    nation = _nation(ctx, power_key)
    _record(player, ctx, "Началась межгосударственная война", f"Рим и {nation.get('name', power_key)} вступили в открытую войну. Причина: {reason}.", power_key, 5)
    return war


def _sync_wars(player: Any, ctx: dict, state: dict) -> None:
    diplomacy = _dict(getattr(player, "diplomacy", {}))
    for key, row in diplomacy.items():
        if not isinstance(row, dict): continue
        if row.get("at_war") and key not in state["wars"]: declare_war(player, str(key), ctx, reason="foreign_escalation")
        if not row.get("at_war") and key in state["wars"]:
            state["wars"][key]["status"] = "ended"; del state["wars"][key]


def _army_power(army: dict, key: str, ctx: dict) -> float:
    roster = {u["id"]: u for u in _roster(ctx, key)}
    units = [roster.get(uid, {}) for uid in army.get("units", [])]
    quality = sum(_f(u.get("attack", 10), 10) + _f(u.get("defense", 10), 10) * 0.7 + _f(u.get("mobility", 8), 8) * 0.25 for u in units) / max(1, len(units))
    return army.get("strength", 70) * 0.75 + army.get("morale", 70) * 0.25 + army.get("experience", 20) * 0.3 + quality


def _legion_power(legion: Any, player: Any, tactic: dict, operation: str, ctx: dict, doctrine: dict) -> float:
    base = _i(getattr(legion, "strength", 60), 60) * 0.9 + _i(getattr(legion, "quality", 4), 4) * 9
    base += _i(getattr(legion, "morale", 70), 70) * 0.28 - _i(getattr(legion, "fatigue", 0), 0) * 0.22
    base += tactic.get("attack", 0) * (1.1 if operation == "offensive" else 0.7) + tactic.get("defense", 0) * (1.1 if operation == "defensive" else 0.6)
    if doctrine.get("favored") in tactic.get("counter", []): base += 15
    nation_module = ctx.get("NATIONS")
    if nation_module is not None and hasattr(nation_module, "get_modifier"):
        try:
            base += nation_module.get_modifier(player, "cavalry_combat", 0) * (0.25 if tactic["id"] in ("rapid", "screening") else 0.05)
            base += nation_module.get_modifier(player, "siege", 0) * (0.35 if tactic["id"] == "siege" else 0.0)
        except Exception: pass
    return base


def _choose_enemy_army(war: dict) -> dict | None:
    alive = [a for a in war.get("enemy_armies", []) if _i(a.get("strength", 0), 0) > 0]
    return max(alive, key=lambda a: _army_power(a, war["power"], {}), default=None) if alive else None


def _queue_campaign(player: Any, key: str, war: dict, ctx: dict) -> bool:
    nation = _nation(ctx, key); army = next((a for a in war.get("enemy_armies", []) if a.get("strength", 0) > 0), None)
    if not army:
        army = _create_army(player, key, ctx, len(war.get("enemy_armies", [])) + 1); war["enemy_armies"].append(army)
    operation = random.choice(["invasion", "raid", "siege", "field_battle"])
    doctrine = DOCTRINES.get(key, {})
    return _world_enqueue(
        player, ctx,
        event_type="war.campaign", title=f"Военный совет: война с державой {nation.get('name', key)}",
        summary=f"Армия под командованием {army.get('commander')} действует на фронте {army.get('front')}. Доктрина противника: {doctrine.get('name', 'неизвестна')}.",
        payload={"army_id": army["id"], "enemy_operation": operation}, power=key, severity=5, expires_in=3,
        dedupe=f"war.campaign:{key}",
    )


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx); state = ensure_state(player, ctx); turn = _i(getattr(player, "turn", 1), 1)
    if state.get("last_tick_turn") >= turn: return state
    state["last_tick_turn"] = turn; _sync_wars(player, ctx, state)
    for key, war in list(state["wars"].items()):
        ai = _enemy_ai_state(player, key)
        war["roman_weariness"] = _clamp(war.get("roman_weariness", 0) + 1 + max(0, -war.get("war_score", 0)) // 30, 0, 100, 0)
        war["enemy_weariness"] = _clamp(war.get("enemy_weariness", 0) + 1 + max(0, war.get("war_score", 0)) // 30, 0, 100, 0)
        for army in war.get("enemy_armies", []):
            if army.get("strength", 0) <= 0: continue
            recovery = 3 + _i(ai.get("manpower", 50), 50) // 30
            army["strength"] = _clamp(army.get("strength", 0) + recovery, 0, 150, 70)
            army["morale"] = _clamp(army.get("morale", 60) + 2, 0, 100, 70)
        if not [a for a in war.get("enemy_armies", []) if a.get("strength", 0) > 15] and _i(ai.get("manpower", 50), 50) > 18:
            war["enemy_armies"].append(_create_army(player, key, ctx, len(war.get("enemy_armies", [])) + 1)); ai["manpower"] = _clamp(ai.get("manpower", 50) - 18, 0, 100, 50)
        council = ctx.get("WORLD_COUNCIL"); pending = False
        if council is not None and hasattr(council, "has_pending"):
            try: pending = council.has_pending(player, "war.campaign", key) or council.has_pending(player, "war.peace", key)
            except Exception: pending = False
        if not pending and turn >= _i(war.get("next_campaign_turn", turn), turn):
            if abs(_i(war.get("war_score", 0), 0)) >= 62 or war["roman_weariness"] >= 72 or war["enemy_weariness"] >= 72:
                _world_enqueue(player, ctx, event_type="war.peace", title=f"Мирные переговоры: {_nation(ctx, key).get('name', key)}", summary="Обе стороны оценивают цену продолжения войны и возможные условия мира.", payload={}, power=key, severity=5, expires_in=4, dedupe=f"war.peace:{key}")
            else:
                _queue_campaign(player, key, war, ctx)
            war["next_campaign_turn"] = turn + random.randint(1, 2)
    return state


def _find_army(war: dict, army_id: str) -> dict | None:
    return next((a for a in war.get("enemy_armies", []) if a.get("id") == army_id), None)


def _select_legion(player: Any, ui: Any) -> Any | None:
    legions = [l for l in _list(getattr(player, "legions", [])) if _i(getattr(l, "strength", 0), 0) > 0]
    if not legions: return None
    ui.section("Доступные легионы", "CYAN")
    for i, legion in enumerate(legions, 1):
        print(f"  {i}. {getattr(legion, 'name', 'Legio')} — сила {getattr(legion, 'strength', 0)}, качество {getattr(legion, 'quality', 0)}, мораль {getattr(legion, 'morale', 0)}, усталость {getattr(legion, 'fatigue', 0)}")
    ch = ui.choice("\n  Выберите легион (или Q): ", [str(i) for i in range(1, len(legions) + 1)] + ["Q"])
    return None if ch == "Q" else legions[int(ch) - 1]


def _resolve_battle(player: Any, war: dict, army: dict, legion: Any, tactic: dict, operation: str, ctx: dict) -> dict:
    key = war["power"]; doctrine = DOCTRINES.get(key, {}); nation = _nation(ctx, key)
    roman = _legion_power(legion, player, tactic, operation, ctx, doctrine) + random.gauss(0, 10)
    enemy = _army_power(army, key, ctx) + doctrine.get("attack", 0) * (1.0 if operation == "defensive" else 0.6) + doctrine.get("defense", 0) * (1.0 if operation == "offensive" else 0.6) + random.gauss(0, 10)
    if doctrine.get("favored") in tactic.get("counter", []): enemy -= 10
    margin = roman - enemy
    if margin >= 35: result = "decisive_victory"; score = 20; roman_loss = random.randint(4, 10); enemy_loss = random.randint(28, 42)
    elif margin >= 10: result = "victory"; score = 12; roman_loss = random.randint(8, 16); enemy_loss = random.randint(18, 30)
    elif margin > -10: result = "stalemate"; score = 0; roman_loss = random.randint(10, 19); enemy_loss = random.randint(10, 20)
    elif margin > -35: result = "defeat"; score = -12; roman_loss = random.randint(18, 30); enemy_loss = random.randint(7, 15)
    else: result = "rout"; score = -22; roman_loss = random.randint(28, 42); enemy_loss = random.randint(4, 11)
    legion.strength = max(1, _i(getattr(legion, "strength", 60), 60) - roman_loss)
    legion.morale = _clamp(getattr(legion, "morale", 70) + (8 if score > 0 else -12 if score < 0 else -2), 5, 100, 70)
    legion.fatigue = _clamp(getattr(legion, "fatigue", 0) + 18, 0, 100, 0)
    army["strength"] = max(0, _i(army.get("strength", 80), 80) - enemy_loss)
    army["morale"] = _clamp(army.get("morale", 70) + (6 if score < 0 else -14 if score > 0 else -4), 0, 100, 70)
    if army["strength"] <= 12: army["status"] = "destroyed"
    war["war_score"] = _i(war.get("war_score", 0) + score, 0, -100, 100)
    war["campaigns"] = _i(war.get("campaigns", 0), 0) + 1
    war["roman_weariness"] = _clamp(war.get("roman_weariness", 0) + max(2, roman_loss // 4), 0, 100, 0)
    war["enemy_weariness"] = _clamp(war.get("enemy_weariness", 0) + max(2, enemy_loss // 4), 0, 100, 0)
    player.grain = max(0, _i(getattr(player, "grain", 0), 0) - random.randint(6, 14))
    labels = {"decisive_victory": "решительная победа", "victory": "победа", "stalemate": "кровавое равновесие", "defeat": "поражение", "rout": "разгром"}
    war["last_result"] = f"{labels[result]} против армии {nation.get('name', key)}"
    return {"result": result, "label": labels[result], "score": score, "roman_loss": roman_loss, "enemy_loss": enemy_loss, "roman_power": round(roman, 1), "enemy_power": round(enemy, 1), "margin": round(margin, 1)}


def _raid_resolution(player: Any, war: dict, key: str, ctx: dict) -> dict:
    ai = _enemy_ai_state(player, key); chance = 0.45 + len(_list(getattr(player, "legions", []))) * 0.05 - _i(ai.get("readiness", 50), 50) / 400
    if random.random() < chance:
        loot = random.randint(18, 42); player.gold = _i(getattr(player, "gold", 0), 0) + loot; war["war_score"] = _i(war.get("war_score", 0) + 6, 0, -100, 100); war["enemy_weariness"] = _clamp(war.get("enemy_weariness", 0) + 5, 0, 100, 0)
        return {"success": True, "text": f"Римские колонны разорили склады и захватили {loot} золота.", "score": 6}
    loss = random.randint(8, 20); player.gold = max(0, _i(getattr(player, "gold", 0), 0) - loss); war["war_score"] = _i(war.get("war_score", 0) - 5, 0, -100, 100)
    return {"success": False, "text": f"Рейд попал в засаду; потеряно {loss} золота и обозов.", "score": -5}


def _campaign_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    key = str(event.get("power")); state = ensure_state(player, ctx); war = state["wars"].get(key)
    if not war: return True
    nation = _nation(ctx, key); doctrine = DOCTRINES.get(key, {}); army = _find_army(war, str(event.get("payload", {}).get("army_id", "")))
    if not army: army = next((a for a in war.get("enemy_armies", []) if a.get("strength", 0) > 0), None)
    if not army: return True
    roster = {u["id"]: u for u in _roster(ctx, key)}
    ui.screen(); ui.header(f"ВОЙНА С ДЕРЖАВОЙ {nation.get('name', key).upper()}", nation.get("icon", "⚔"), "I. Донесение с фронта")
    ui.wrap(event.get("summary", ""))
    ui.info(f"Фронт: {army.get('front')}; счёт войны: {war.get('war_score')}; усталость Рима/врага: {war.get('roman_weariness')}/{war.get('enemy_weariness')}.", "CYAN")
    ui.pause("Развернуть разведывательное досье...")

    ui.screen(); ui.header("РАЗВЕДКА О ПРОТИВНИКЕ", "🕵", "II. Армия и её национальный способ войны")
    ui.table("Иностранная армия", ["Параметр", "Значение"], [
        ("Командующий", army.get("commander")), ("Сила / мораль / опыт", f"{army.get('strength')} / {army.get('morale')} / {army.get('experience')}"),
        ("Доктрина", doctrine.get("name")), ("Замысел", doctrine.get("text")),
    ], "RED")
    ui.table("Состав", ["Часть", "Класс", "Атака", "Защита", "Подвижность", "Особенность"], [
        (roster.get(uid, {}).get("name", uid), roster.get(uid, {}).get("class", "—"), roster.get(uid, {}).get("attack", "—"), roster.get(uid, {}).get("defense", "—"), roster.get(uid, {}).get("mobility", "—"), roster.get(uid, {}).get("trait", "—")) for uid in army.get("units", [])
    ], "GOLD")
    ui.pause("Созвать военный совет...")

    ui.screen(); ui.header("CONSILIUM BELLI", "🏛", "III. Выбор оперативного замысла")
    print("  O. Навязать полевое сражение")
    print("  D. Занять оборону и встретить наступление")
    print("  R. Провести рейд по тылам")
    print("  N. Предложить переговоры")
    print("  P. Отложить решение")
    operation_choice = ui.choice("\n  Приказ: ", ["O", "D", "R", "N", "P"])
    if operation_choice == "P": return False
    if operation_choice == "N":
        _world_enqueue(player, ctx, event_type="war.peace", title=f"Переговоры с державой {nation.get('name', key)}", summary="Рим предложил открыть переговоры о прекращении войны.", payload={"roman_initiative": True}, power=key, severity=5, expires_in=4, dedupe=f"war.peace:{key}")
        ui.info("Послы с белыми жезлами направлены к противнику.", "CYAN"); ui.pause(); return True
    if operation_choice == "R":
        ui.screen(); ui.header("РЕЙД ПО ТЫЛАМ", "🔥", "IV. Исполнение операции")
        result = _raid_resolution(player, war, key, ctx); ui.wrap(result["text"], "GREEN" if result["success"] else "RED")
        _record(player, ctx, "Рейд в межгосударственной войне", result["text"], key, 3); ui.pause(); return True
    operation = "offensive" if operation_choice == "O" else "defensive"
    legion = _select_legion(player, ui)
    if legion is None:
        ui.info("Без боеспособного легиона полевую операцию провести невозможно. Решение отложено.", "RED"); ui.pause(); return False

    ui.screen(); ui.header("ТАКТИЧЕСКИЙ ПЛАН", "🛡", "IV. Приказ легату")
    for key_t, spec in ROMAN_TACTICS.items(): print(f"  {key_t}. {spec['name']} — атака {spec['attack']}, защита {spec['defense']}")
    tactic_key = ui.choice("\n  Тактика: ", list(ROMAN_TACTICS)); tactic = ROMAN_TACTICS[tactic_key]
    ui.pause("Передать таблички легату и начать сражение...")

    result = _resolve_battle(player, war, army, legion, tactic, operation, ctx)
    ui.screen(); ui.header("ИСХОД КАМПАНИИ", "⚔", "V. Донесение после боя")
    color = "GREEN" if result["score"] > 0 else "RED" if result["score"] < 0 else "GOLD"
    ui.wrap(f"Итог: {result['label']}. Расчётная сила Рима {result['roman_power']}, противника {result['enemy_power']}; изменение счёта войны {result['score']:+}.", color)
    ui.info(f"Потери легиона: {result['roman_loss']}; потери иностранной армии: {result['enemy_loss']}.", color)
    ui.info(f"Текущий счёт войны: {war['war_score']}; сила легиона {getattr(legion, 'strength', 0)}; сила врага {army.get('strength', 0)}.", "CYAN")
    _record(player, ctx, f"Кампания против державы {nation.get('name', key)}", f"{getattr(legion, 'name', 'Легион')} завершил бой: {result['label']}; счёт войны {war['war_score']}.", key, 4)
    ui.pause("Обсудить политические последствия...")

    ui.screen(); ui.header("ПОСЛЕДСТВИЯ", "📜", "VI. Война продолжается")
    if abs(war["war_score"]) >= 62:
        ui.wrap("Равновесие войны нарушено. На следующем заседании возможны переговоры о мире, подчинении или контрибуции.", "GOLD")
    elif army.get("status") == "destroyed":
        ui.wrap("Иностранная армия рассеяна, однако держава ещё может собрать новую из собственных национальных частей.", "GREEN")
    else:
        ui.wrap("Обе стороны сохраняют способность продолжать кампанию. Противник учтёт выбранную римскую тактику.", "WHITE")
    ui.pause(); return True


def _end_war(player: Any, key: str, war: dict, ctx: dict, outcome: str, tribute: int = 0, client: bool = False) -> None:
    row = _dict(_dict(getattr(player, "diplomacy", {})).get(key)); row["at_war"] = False; row["war_ended_turn"] = _i(getattr(player, "turn", 1), 1)
    row["tension"] = 45 if outcome == "roman_victory" else 55 if outcome == "white_peace" else 65
    row["non_aggression"] = True; row["non_aggression_turn"] = _i(getattr(player, "turn", 1), 1)
    if tribute:
        row["tribute"] = tribute; row["tribute_turn"] = _i(getattr(player, "turn", 1), 1)
    if client:
        row["client"] = True; row["alliance"] = True; row["disposition"] = 42; row["trust"] = 28
    war["status"] = "ended"; ensure_state(player, ctx)["wars"].pop(key, None)


def _peace_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    key = str(event.get("power")); state = ensure_state(player, ctx); war = state["wars"].get(key)
    if not war: return True
    nation = _nation(ctx, key); score = _i(war.get("war_score", 0), 0); row = _dict(_dict(getattr(player, "diplomacy", {})).get(key))
    ui.screen(); ui.header("МИРНАЯ КОНФЕРЕНЦИЯ", "🕊", "I. Стороны прибывают к месту переговоров")
    ui.wrap(f"Война с державой {nation.get('name', key)} достигла счёта {score}. Усталость Рима {war.get('roman_weariness')}, противника {war.get('enemy_weariness')}. Ни одна сторона не обязана принять мир, но цена продолжения растёт.")
    ui.pause("Выслушать предварительные позиции...")

    ui.screen(); ui.header("ПОЗИЦИИ СТОРОН", "⚖", "II. Требования и пределы уступок")
    if score >= 45:
        ui.wrap("Рим диктует условия. Иностранная сторона готова обсуждать контрибуцию, торговые привилегии и даже клиентский статус.", "GREEN")
        mode = "roman_advantage"
    elif score <= -45:
        ui.wrap("Иностранная сторона считает себя победительницей и требует золото, отказ от претензий и длительный пакт.", "RED")
        mode = "enemy_advantage"
    else:
        ui.wrap("Силы сторон близки. Реалистичный исход — белый мир, обмен пленными и временный пакт.", "GOLD")
        mode = "balanced"
    ui.pause("Перейти к закрытому заседанию...")

    ui.screen(); ui.header("ЗАКРЫТОЕ ЗАСЕДАНИЕ", "🏛", "III. Выбор римской позиции")
    if mode == "roman_advantage":
        print("  1. Контрибуция и торговые привилегии")
        print("  2. Превратить державу в клиентское царство")
        print("  3. Белый мир ради быстрого окончания войны")
        print("  4. Продолжить войну")
        ch = ui.choice("\n  Условия: ", ["1", "2", "3", "4"])
        if ch == "4": war["next_campaign_turn"] = _i(getattr(player, "turn", 1), 1) + 1; ui.info("Переговоры прерваны. Война продолжается.", "RED"); ui.pause(); return True
        if ch == "1":
            tribute = max(8, min(30, 8 + score // 4)); player.gold = _i(getattr(player, "gold", 0), 0) + 60; row["trade_pact"] = True; _end_war(player, key, war, ctx, "roman_victory", tribute=tribute)
            result = f"{nation.get('name', key)} выплачивает 60 золота и {tribute} золота дани за ход, открывая рынки Риму."
        elif ch == "2":
            acceptance = 0.40 + score / 160 + war.get("enemy_weariness", 0) / 300
            if random.random() < acceptance:
                _end_war(player, key, war, ctx, "roman_victory", tribute=12, client=True); result = f"{nation.get('name', key)} признала римское покровительство и стала клиентским царством."
            else:
                war["war_score"] = max(35, score - 8); war["next_campaign_turn"] = _i(getattr(player, "turn", 1), 1) + 1; result = "Требование клиентского статуса отвергнуто; война продолжается."; ui.wrap(result, "RED"); ui.pause(); return True
        else:
            _end_war(player, key, war, ctx, "white_peace"); result = "Заключён белый мир с обменом пленными и пактом о ненападении."
    elif mode == "enemy_advantage":
        demand = max(35, min(110, 35 + abs(score)))
        print(f"  1. Выплатить {demand} золота и заключить мир")
        print("  2. Торговаться о меньшей выплате")
        print("  3. Продолжить войну")
        ch = ui.choice("\n  Ответ: ", ["1", "2", "3"])
        if ch == "3": war["next_campaign_turn"] = _i(getattr(player, "turn", 1), 1) + 1; ui.info("Рим отверг требования. Война продолжается.", "RED"); ui.pause(); return True
        payment = demand if ch == "1" else max(20, demand // 2)
        success = ch == "1" or random.random() < 0.45 + row.get("trust", 20) / 250
        if not success:
            war["next_campaign_turn"] = _i(getattr(player, "turn", 1), 1) + 1; ui.info("Противник отверг римский торг. Война продолжается.", "RED"); ui.pause(); return True
        actual = min(payment, _i(getattr(player, "gold", 0), 0)); player.gold -= actual; _end_war(player, key, war, ctx, "roman_defeat"); result = f"Рим выплатил {actual} золота и получил мир без территориальных уступок."
    else:
        print("  1. Белый мир и обмен пленными")
        print("  2. Предложить взаимную торговлю после войны")
        print("  3. Продолжить войну")
        ch = ui.choice("\n  Позиция: ", ["1", "2", "3"])
        if ch == "3": war["next_campaign_turn"] = _i(getattr(player, "turn", 1), 1) + 1; ui.info("Переговоры завершены без мира.", "RED"); ui.pause(); return True
        _end_war(player, key, war, ctx, "white_peace")
        if ch == "2": row["trade_pact"] = True; row["disposition"] = _clamp(row.get("disposition", 30) + 8, 0, 100, 30); result = "Заключён белый мир и соглашение о послевоенной торговле."
        else: result = "Заключён белый мир и произведён обмен пленными."
    ui.screen(); ui.header("МИР ПОДПИСАН", "🕊", "IV. Ратификация")
    ui.wrap(result, "GREEN"); _record(player, ctx, "Завершена межгосударственная война", result, key, 5); ui.pause(); return True


def handle_council_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    etype = str(event.get("type", ""))
    if etype == "war.campaign": return _campaign_event(player, event, ctx, ui)
    if etype == "war.peace": return _peace_event(player, event, ctx, ui)
    return True


def expire_council_event(player: Any, event: dict, ctx: dict) -> None:
    key = str(event.get("power") or ""); war = ensure_state(player, ctx)["wars"].get(key)
    if not war: return
    if event.get("type") == "war.campaign":
        # Молчание означает потерю инициативы, но не автоматическую катастрофу.
        war["war_score"] = _i(war.get("war_score", 0) - 7, 0, -100, 100); war["roman_weariness"] = _clamp(war.get("roman_weariness", 0) + 6, 0, 100, 0)
        player.gold = max(0, _i(getattr(player, "gold", 0), 0) - 12)
        _record(player, ctx, "Противник захватил инициативу", "Рим не принял своевременного решения по кампании; враг разорил коммуникации.", key, 4)



def _province_record(ctx: dict, province_name: str) -> dict:
    lookup = ctx.get("province_by_name")
    if callable(lookup):
        try:
            row = lookup(province_name)
            if isinstance(row, dict):
                return row
        except Exception:
            pass
    direct = _dict(ctx.get("PROVINCE_BY_NAME"))
    if province_name in direct:
        return _dict(direct.get(province_name))
    for row in _list(ctx.get("PROVINCES_DATA")):
        if isinstance(row, dict) and str(row.get("name", "")) == province_name:
            return row
    return {}


def _war_relevant_to_province(key: str, war: dict, province_name: str) -> bool:
    names = {str(war.get("front", ""))}
    names.update(str(x) for x in FRONTS.get(str(key), []))
    for army in _list(war.get("enemy_armies")):
        if isinstance(army, dict):
            names.add(str(army.get("front", "")))
    aliases = {
        "Sardinia et Corsica": {"Sardinia"},
        "Gallia Cisalpina": {"Cisalpine Gaul"},
        "Africa Proconsularis": {"Carthago"},
    }
    names.update(aliases.get(province_name, set()))
    return province_name in names or bool(set(aliases.get(province_name, set())) & names)


def open_province_menu(player: Any, province_name: str, ctx: dict | None = None) -> None:
    """Показывает прямые войны, чьи фронты связаны с выбранной провинцией."""
    ctx = _ctx(ctx)
    ui = UI(ctx)
    state = ensure_state(player, ctx)
    _sync_wars(player, ctx, state)
    province_name = str(province_name or "").strip() or "Latium"
    province = _province_record(ctx, province_name)
    sea_zone = str(province.get("sea_zone", "") or "")
    access = str(province.get("campaign_access", "land") or "land")

    while True:
        wars = {
            key: war for key, war in _dict(state.get("wars")).items()
            if isinstance(war, dict)
            and war.get("status", "active") == "active"
            and _war_relevant_to_province(str(key), war, province_name)
        }
        ui.screen()
        ui.header(
            f"FRONS: {province_name.upper()}",
            "🌍",
            "Прямые войны держав, способные затронуть выбранную провинцию",
        )
        ui.table("Театр", ["Показатель", "Значение"], [
            ("Провинция", province_name),
            ("Тип доступа", access),
            ("Морская зона", sea_zone or "нет"),
            ("Связанных войн", len(wars)),
        ], "GOLD")

        if wars:
            ordered = list(wars.items())
            ui.table("Войны на театре", ["#", "Держава", "Фронт", "Счёт", "Уст. Рим/враг", "Армии", "Итог"], [
                (
                    index,
                    _nation(ctx, key).get("name", key),
                    war.get("front", "—"),
                    war.get("war_score", 0),
                    f"{war.get('roman_weariness', 0)}/{war.get('enemy_weariness', 0)}",
                    len([a for a in _list(war.get("enemy_armies")) if isinstance(a, dict) and a.get("strength", 0) > 0]),
                    war.get("last_result", "—"),
                )
                for index, (key, war) in enumerate(ordered, 1)
            ], "RED")
            ui.section("Действия", "GOLD")
            print("  1-N. Созвать внеочередной военный совет по выбранной войне")
            print("  Q. Назад")
            choice = ui.choice("\n  Выбор: ", [str(i) for i in range(1, len(ordered) + 1)] + ["Q"])
            if choice == "Q":
                return
            key, war = ordered[int(choice) - 1]
            if _queue_campaign(player, key, war, ctx):
                ui.info("Военный совет созван и помещён в Consilium Orbis.", "GREEN")
            else:
                ui.info("Совет по этой войне уже ожидает решения.", "GOLD")
            ui.pause()
        else:
            ui.info("На этом театре нет активной прямой войны держав.", "GRAY")
            ui.wrap(
                "Это не исключает местных защитников, варварские отряды или автономную кампанию "
                "Bellum Provinciale: они учитываются другими подсистемами.",
                "CYAN",
            )
            ui.pause()
            return

def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx); ui = UI(ctx); state = ensure_state(player, ctx); _sync_wars(player, ctx, state)
    while True:
        ui.screen(); ui.header("BELLA REGNORUM", "⚔", f"Прямые войны с уникальными государствами — {MODULE_VERSION}")
        wars = state.get("wars", {})
        if wars:
            ui.table("Активные войны", ["Держава", "Фронт", "Счёт", "Уст. Рим/враг", "Армии", "Последний итог"], [
                (_nation(ctx, key).get("name", key), war.get("front"), war.get("war_score"), f"{war.get('roman_weariness')}/{war.get('enemy_weariness')}", len([a for a in war.get("enemy_armies", []) if a.get("strength", 0) > 0]), war.get("last_result")) for key, war in wars.items()
            ], "RED")
        else: ui.info("Рим не ведёт прямых межгосударственных войн.", "GRAY")
        ui.section("Действия", "GOLD")
        print("  1. Объявить войну державе")
        print("  2. Потребовать внеочередной военный совет")
        print("  3. Просмотреть иностранные армии")
        print("  4. Военный архив")
        print("  Q. Назад")
        ch = ui.choice("\n  Выбор: ", ["1", "2", "3", "4", "Q"])
        if ch == "Q": return
        if ch == "1":
            diplomacy = _dict(getattr(player, "diplomacy", {})); keys = [k for k, row in diplomacy.items() if isinstance(row, dict) and not row.get("at_war")]
            ui.screen(); ui.header("ОБЪЯВЛЕНИЕ ВОЙНЫ", "📜")
            for i, key in enumerate(keys, 1): print(f"  {i}. {_nation(ctx, key).get('name', key)} — отношение {diplomacy[key].get('disposition', 0)}, напряжение {diplomacy[key].get('tension', 0)}")
            s = ui.choice("\n  Цель (или Q): ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
            if s != "Q":
                key = keys[int(s) - 1]
                ui.wrap("Объявление войны разрывает союз, торговлю, брак не прекращает, но делает супругу активным политическим фактором. Сенат и другие державы запомнят агрессию.", "RED")
                if ui.choice("  Подтвердить войну? (Y/N): ", ["Y", "N"]) == "Y":
                    declare_war(player, key, ctx, reason="roman_declaration"); _queue_campaign(player, key, state["wars"][key], ctx); ui.info("Война объявлена. Первый совет помещён в очередь Consilium Orbis.", "RED")
                ui.pause()
        elif ch == "2":
            keys = list(wars)
            if not keys: ui.info("Нет активных войн.", "GRAY"); ui.pause(); continue
            for i, key in enumerate(keys, 1): print(f"  {i}. {_nation(ctx, key).get('name', key)}")
            s = ui.choice("\n  Фронт (или Q): ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
            if s != "Q":
                key = keys[int(s) - 1]
                if _queue_campaign(player, key, wars[key], ctx): ui.info("Военный совет созван и ожидает рассмотрения.", "GREEN")
                else: ui.info("Совет по этой войне уже ожидает решения.", "GOLD")
                ui.pause()
        elif ch == "3":
            ui.screen(); ui.header("ИНОСТРАННЫЕ АРМИИ", "🛡")
            rows = []
            for key, war in wars.items():
                roster = {u["id"]: u for u in _roster(ctx, key)}
                for a in war.get("enemy_armies", []): rows.append((_nation(ctx, key).get("name", key), a.get("name"), a.get("commander"), a.get("strength"), a.get("morale"), ", ".join(roster.get(uid, {}).get("name", uid) for uid in a.get("units", []))))
            if rows: ui.table("Армии", ["Держава", "Армия", "Командующий", "Сила", "Мораль", "Части"], rows, "CYAN")
            else: ui.info("Разведка не видит активных армий.", "GRAY")
            ui.pause()
        elif ch == "4":
            ui.screen(); ui.header("COMMENTARII BELLI", "📜")
            if state["history"]: ui.table("Последние записи", ["Ход", "Держава", "Событие", "Содержание"], [(h.get("turn"), _nation(ctx, h.get("power", "")).get("name", h.get("power") or "—"), h.get("title"), h.get("text")) for h in reversed(state["history"][-50:])], "CYAN")
            else: ui.info("Архив пуст.", "GRAY")
            ui.pause()
