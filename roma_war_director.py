#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna 3.1 — BELLUM PROVINCIALE.

Оперативный директор войн. Иностранные державы самостоятельно выбирают армии,
провинции, города и морские зоны, планируют походы, навязывают Риму полевые и
морские сражения и оккупируют города. Критические столкновения автоматически
попадают в Consilium Orbis и разворачиваются в несколько стадий.

Публичный контракт:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None)
    handle_council_event(player, event, ctx, ui)
    expire_council_event(player, event, ctx)
    open_province_menu(player, province_name, ctx=None)
    open_menu(player, ctx=None)
"""
from __future__ import annotations

import random
import re
import textwrap
import uuid
from typing import Any

MODULE_VERSION = "3.1.0-bellum-provinciale"
SCHEMA_VERSION = 1
MAX_HISTORY = 400
MAX_CAMPAIGNS_PER_POWER = 2


def _i(value: Any, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    try: value = int(round(float(value)))
    except (TypeError, ValueError, OverflowError): value = default
    if low is not None: value = max(low, value)
    if high is not None: value = min(high, value)
    return value


def _f(value: Any, default: float = 0.0) -> float:
    try: return float(value)
    except (TypeError, ValueError, OverflowError): return default


def _clamp(value: Any, low: int = 0, high: int = 100, default: int = 0) -> int:
    return _i(value, default, low, high)


def _list(value: Any) -> list: return value if isinstance(value, list) else []
def _dict(value: Any) -> dict: return value if isinstance(value, dict) else {}
def _ctx(ctx: dict | None) -> dict: return ctx if isinstance(ctx, dict) else {}


def _plain(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r"\[[^\]]+\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


class UI:
    def __init__(self, ctx: dict | None = None): self.ctx = _ctx(ctx); self.C = self.ctx.get("C")
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
                try: fn(title, icon, getattr(self.C, "RED", "")); return
                except Exception: pass
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


POWER_CAMPAIGN_STYLE = {
    "carthage": {"amphibious": 0.82, "tempo": 2, "targets": ["Sicilia", "Sardinia et Corsica", "Campania", "Latium"], "tactic": "blockade and landing"},
    "numidia": {"amphibious": 0.03, "tempo": 2, "targets": ["Carthago", "Sicilia", "Mauretania", "Hispania"], "tactic": "raids and pursuit"},
    "pergamon": {"amphibious": 0.28, "tempo": 3, "targets": ["Asia Minor", "Achaea", "Macedonia", "Syria"], "tactic": "methodical siege"},
    "parthia": {"amphibious": 0.00, "tempo": 2, "targets": ["Syria", "Armenia", "Judaea", "Cilicia"], "tactic": "feigned retreat and encirclement"},
    "egypt": {"amphibious": 0.58, "tempo": 3, "targets": ["Cyrenaica", "Syria", "Carthago", "Sicilia"], "tactic": "fleet-supported attrition"},
    "gauls": {"amphibious": 0.02, "tempo": 2, "targets": ["Gallia", "Gallia Narbonensis", "Liguria", "Latium"], "tactic": "mass assault and ambush"},
}


def _nation(ctx: dict, key: str) -> dict:
    module = ctx.get("NATIONS")
    if module is not None and hasattr(module, "get_nation"):
        try: return module.get_nation(key)
        except Exception: pass
    return {"name": key, "capital": key, "war_doctrine": "неизвестная доктрина", "modifiers": {}}


def _ai(ctx: dict) -> Any: return ctx.get("AI_CIVILIZATION")
def _armies(ctx: dict) -> Any: return ctx.get("ARMY_GROUPS")


def _world_enqueue(player: Any, ctx: dict, **kwargs: Any) -> bool:
    council = ctx.get("WORLD_COUNCIL")
    if council is None or not hasattr(council, "enqueue"): return False
    try: return council.enqueue(player, ctx=ctx, **kwargs) is not None
    except Exception: return False


def _record(player: Any, state: dict, title: str, text: str, power: str | None, ctx: dict, severity: int = 3) -> None:
    item = {"turn": _i(getattr(player, "turn", 1), 1), "power": power, "title": title, "text": text}
    state.setdefault("history", []).append(item); state["history"] = state["history"][-MAX_HISTORY:]
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
        try: annales.record_event(player, category="military", title=title, text=text,
                                  reason="Самостоятельная операция иностранной державы против Рима.",
                                  severity=severity, data={"power": power, "system": "bellum_universale"})
        except Exception: pass


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    state = getattr(player, "war_director_3", None)
    if not isinstance(state, dict): state = {}; player.war_director_3 = state
    state.setdefault("schema", SCHEMA_VERSION); state.setdefault("version", MODULE_VERSION)
    state.setdefault("campaigns", []); state.setdefault("occupied_cities", {}); state.setdefault("lost_provinces", {})
    state.setdefault("blockades", {}); state.setdefault("history", []); state.setdefault("last_tick_turn", 0)
    state.setdefault("next_campaign_turn", {}); state.setdefault("settings", {})
    state["settings"].setdefault("max_campaigns_per_power", MAX_CAMPAIGNS_PER_POWER)
    state["settings"].setdefault("battle_notice", True)
    campaigns = []
    for raw in _list(state.get("campaigns")):
        if not isinstance(raw, dict): continue
        c = dict(raw)
        c.setdefault("id", "CMP-" + uuid.uuid4().hex[:10]); c.setdefault("power", "")
        c.setdefault("army_id", None); c.setdefault("type", "land"); c.setdefault("stage", "planning")
        c.setdefault("province", "Latium"); c.setdefault("city", "Roma"); c.setdefault("sea_zone", None)
        c.setdefault("progress", 0); c.setdefault("created_turn", _i(getattr(player, "turn", 1), 1))
        c.setdefault("next_action_turn", c["created_turn"] + 1); c.setdefault("pending_event", False)
        c.setdefault("status", "active"); c.setdefault("last_result", "подготовка")
        c["progress"] = _i(c.get("progress", 0), 0, 0, 20); c["next_action_turn"] = _i(c.get("next_action_turn", 1), 1, 1)
        if c.get("status") == "active": campaigns.append(c)
    state["campaigns"] = campaigns[-30:]
    occupied = {}
    for province, rows in _dict(state.get("occupied_cities")).items():
        fixed = {}
        if isinstance(rows, dict):
            for city, data in rows.items():
                if isinstance(data, dict):
                    data.setdefault("power", ""); data.setdefault("since_turn", 1); data.setdefault("victories", 1)
                    fixed[str(city)] = data
        occupied[str(province)] = fixed
    state["occupied_cities"] = occupied
    state["lost_provinces"] = {str(k): v for k, v in _dict(state.get("lost_provinces")).items() if isinstance(v, dict)}
    state["blockades"] = {str(k): v for k, v in _dict(state.get("blockades")).items() if isinstance(v, dict)}
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state["last_tick_turn"] = _i(state.get("last_tick_turn", 0), 0, 0)
    state["next_campaign_turn"] = {str(k): _i(v, 1, 1) for k, v in _dict(state.get("next_campaign_turn")).items()}
    state["schema"] = SCHEMA_VERSION; state["version"] = MODULE_VERSION
    player.war_director_3 = state
    return state


def _province_def(ctx: dict, name: str) -> dict:
    return next((p for p in _list(ctx.get("PROVINCES_DATA")) if isinstance(p, dict) and p.get("name") == name), {})


def _owned_provinces(player: Any, ctx: dict) -> list[dict]:
    owned = [p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict)]
    names = {p.get("name") for p in owned}
    if "Latium" not in names:
        latium = _province_def(ctx, "Latium")
        if latium: owned.insert(0, latium)
    return owned


def _sea_zone_for(ctx: dict, province: str) -> str | None:
    for zone, data in _dict(ctx.get("SEA_ZONES")).items():
        if province in _list(_dict(data).get("provinces")): return str(zone)
    return None


def _city_rows(ctx: dict, province: str) -> list[dict]:
    return [c for c in _list(_province_def(ctx, province).get("cities")) if isinstance(c, dict)]


def _occupied(state: dict, province: str, city: str) -> dict | None:
    return _dict(_dict(state.get("occupied_cities")).get(province)).get(city)


def _choose_target(player: Any, key: str, state: dict, ctx: dict) -> tuple[str, str]:
    owned = _owned_provinces(player, ctx); style = POWER_CAMPAIGN_STYLE.get(key, {})
    preferences = _list(style.get("targets")); occupied = state.get("occupied_cities", {})
    candidates = []
    for province in owned:
        name = str(province.get("name", "")); definition = _province_def(ctx, name) or province
        cities = [c for c in _list(definition.get("cities")) if isinstance(c, dict)] or [{"name": name, "population": 60}]
        for city in cities:
            city_name = str(city.get("name", name)); occ = _occupied(state, name, city_name)
            score = _i(definition.get("wealth", 3), 3) * 12 + _i(city.get("population", 60), 60) // 3
            if name in preferences: score += (len(preferences) - preferences.index(name)) * 26
            if name == "Latium": score += 35
            if occ: score += 80 + _i(occ.get("victories", 1), 1) * 20
            zone = _sea_zone_for(ctx, name)
            if zone and POWER_CAMPAIGN_STYLE.get(key, {}).get("amphibious", 0) > 0.4: score += 18
            score += random.randint(0, 20)
            candidates.append((score, name, city_name))
    if not candidates: return "Latium", "Roma"
    _, province, city = max(candidates)
    return province, city


def _active_wars(player: Any) -> list[str]:
    keys = [str(k) for k, row in _dict(getattr(player, "diplomacy", {})).items() if isinstance(row, dict) and row.get("at_war")]
    for key, war in _dict(_dict(getattr(player, "foreign_warfare", {})).get("wars")).items():
        if isinstance(war, dict) and war.get("status", "active") == "active" and str(key) not in keys: keys.append(str(key))
    return keys


def _campaigns_for(state: dict, key: str) -> list[dict]:
    return [c for c in state["campaigns"] if c.get("power") == key and c.get("status") == "active"]


def _create_campaign(player: Any, key: str, state: dict, ctx: dict) -> dict | None:
    ai = _ai(ctx)
    if ai is None or not hasattr(ai, "choose_field_army"): return None
    turn = _i(getattr(player, "turn", 1), 1)
    used_armies = {
        str(c.get("army_id")) for c in state.get("campaigns", [])
        if c.get("status") == "active" and c.get("army_id")
    }
    army = ai.choose_field_army(player, key, ctx)
    if army and str(army.get("id")) in used_armies:
        power = ai.get_power_state(player, key, ctx) if hasattr(ai, "get_power_state") else {}
        candidates = [
            row for row in _list(_dict(power).get("armies"))
            if row.get("units")
            and str(row.get("id")) not in used_armies
            and _i(row.get("available_turn", 0), 0) <= turn
        ]
        if candidates:
            if hasattr(ai, "land_power"):
                army = max(candidates, key=lambda row: ai.land_power(player, key, ctx, row.get("id")))
            else:
                army = max(candidates, key=lambda row: len(_list(row.get("units"))))
        else:
            army = None
    if not army: return None
    province, city = _choose_target(player, key, state, ctx); zone = _sea_zone_for(ctx, province)
    style = POWER_CAMPAIGN_STYLE.get(key, {}); naval = ai.naval_power(player, key, ctx) if hasattr(ai, "naval_power") else 0
    amphibious = bool(zone and naval >= 22 and random.random() < _f(style.get("amphibious", 0), 0))
    campaign = {
        "id": "CMP-" + uuid.uuid4().hex[:10], "power": key, "army_id": army.get("id"),
        "type": "amphibious" if amphibious else "land", "stage": "planning",
        "province": province, "city": city, "sea_zone": zone if amphibious else None,
        "progress": 0, "created_turn": _i(getattr(player, "turn", 1), 1),
        "next_action_turn": _i(getattr(player, "turn", 1), 1) + 1,
        "pending_event": False, "status": "active", "last_result": "штаб готовит операцию",
    }
    state["campaigns"].append(campaign)
    army["objective"] = f"{city}, {province}"; army["stance"] = "planning"
    nation = _nation(ctx, key)
    _record(player, state, f"{nation.get('name', key)} начинает подготовку кампании", f"Разведка отмечает мобилизацию армии {army.get('name')} и интерес к направлению {province}.", key, ctx, 3)
    return campaign


def _event_pending(player: Any, campaign: dict, ctx: dict) -> bool:
    council = ctx.get("WORLD_COUNCIL")
    if council is None or not hasattr(council, "has_pending"): return bool(campaign.get("pending_event"))
    try:
        for event_type in ("battle.naval", "battle.city"):
            if council.has_pending(player, event_type, campaign.get("power")): return True
    except Exception: pass
    return False


def _queue_naval(player: Any, campaign: dict, ctx: dict) -> bool:
    key = campaign["power"]; nation = _nation(ctx, key); zone_name = _dict(_dict(ctx.get("SEA_ZONES")).get(campaign.get("sea_zone"))).get("name", campaign.get("sea_zone"))
    queued = _world_enqueue(player, ctx, event_type="battle.naval",
        title=f"Вражеский флот навязывает бой: {zone_name}",
        summary=f"{nation.get('name', key)} выводит боевые эскадры для прикрытия армии, направленной к городу {campaign['city']}. Уклонение откроет путь высадке и блокаде.",
        payload={"campaign_id": campaign["id"]}, power=key, severity=5, expires_in=2,
        dedupe=f"battle.naval:{campaign['id']}")
    if queued: campaign["pending_event"] = True; campaign["last_result"] = "ожидается морское сражение"
    return queued


def _queue_city(player: Any, campaign: dict, ctx: dict) -> bool:
    key = campaign["power"]; nation = _nation(ctx, key)
    queued = _world_enqueue(player, ctx, event_type="battle.city",
        title=f"Битва за {campaign['city']}",
        summary=f"Армия державы {nation.get('name', key)} завершила движение к городу {campaign['city']} в провинции {campaign['province']} и требует немедленного ответа Рима.",
        payload={"campaign_id": campaign["id"]}, power=key, severity=5, expires_in=2,
        dedupe=f"battle.city:{campaign['id']}")
    if queued: campaign["pending_event"] = True; campaign["last_result"] = "враг навязывает бой у города"
    return queued


def _war_score(player: Any, key: str, delta: int) -> None:
    war = _dict(_dict(_dict(getattr(player, "foreign_warfare", {})).get("wars")).get(key))
    if war:
        war["war_score"] = _i(war.get("war_score", 0) + delta, 0, -100, 100)
        if delta > 0: war["enemy_weariness"] = _clamp(war.get("enemy_weariness", 0) + max(1, delta // 3), 0, 100, 0)
        else: war["roman_weariness"] = _clamp(war.get("roman_weariness", 0) + max(1, -delta // 3), 0, 100, 0)


def _apply_blockade(player: Any, state: dict, campaign: dict, ctx: dict, severity: int = 25) -> None:
    zone = campaign.get("sea_zone") or _sea_zone_for(ctx, campaign.get("province")) or "unknown"
    row = state["blockades"].setdefault(zone, {"power": campaign["power"], "strength": 0, "since_turn": _i(getattr(player, "turn", 1), 1)})
    row["power"] = campaign["power"]; row["strength"] = _clamp(row.get("strength", 0) + severity, 0, 100, 0)
    gold_loss = min(_i(getattr(player, "gold", 0), 0), max(8, severity // 2)); grain_loss = min(_i(getattr(player, "grain", 0), 0), max(6, severity // 3))
    player.gold = max(0, _i(getattr(player, "gold", 0), 0) - gold_loss); player.grain = max(0, _i(getattr(player, "grain", 0), 0) - grain_loss)
    _record(player, state, "Вражеская морская блокада", f"Зона {zone}: давление {row['strength']}/100; Рим теряет {gold_loss} золота и {grain_loss} зерна.", campaign["power"], ctx, 4)


def _lift_blockade(state: dict, zone: str | None) -> None:
    if not zone: return
    if zone in state.get("blockades", {}):
        state["blockades"][zone]["strength"] = max(0, _i(state["blockades"][zone].get("strength", 0), 0) - 45)
        if state["blockades"][zone]["strength"] <= 0: state["blockades"].pop(zone, None)


def _occupy_city(player: Any, state: dict, campaign: dict, ctx: dict, unopposed: bool = False) -> str:
    province = campaign["province"]; city = campaign["city"]; key = campaign["power"]
    rows = state["occupied_cities"].setdefault(province, {}); existing = _dict(rows.get(city))
    victories = _i(existing.get("victories", 0), 0) + 1
    rows[city] = {"power": key, "since_turn": existing.get("since_turn", _i(getattr(player, "turn", 1), 1)), "victories": victories}
    for prov in _list(getattr(player, "provinces", [])):
        if isinstance(prov, dict) and prov.get("name") == province: prov["unrest"] = min(100, _i(prov.get("unrest", 0), 0) + (18 if unopposed else 12))
    player.unrest = _clamp(getattr(player, "unrest", 0) + (8 if unopposed else 5), 0, 100, 0)
    player.glory = max(0, _i(getattr(player, "glory", 0), 0) - (10 if unopposed else 6))
    if victories >= 2 and province != "Latium":
        owned = next((p for p in _list(getattr(player, "provinces", [])) if isinstance(p, dict) and p.get("name") == province), None)
        if owned is not None:
            state["lost_provinces"][province] = dict(owned); player.provinces.remove(owned)
            _record(player, state, f"Провинция {province} потеряна", f"После повторной победы у города {city} держава {_nation(ctx, key).get('name', key)} уничтожает римскую администрацию.", key, ctx, 5)
            return "province_lost"
    if province == "Latium" and victories >= 2:
        player.unrest = 100; player.senate_rep = max(0, _i(getattr(player, "senate_rep", 50), 50) - 20); player.people_rep = max(0, _i(getattr(player, "people_rep", 50), 50) - 20)
        return "capital_crisis"
    return "city_occupied"


def _recapture_city(player: Any, state: dict, campaign: dict, ctx: dict) -> bool:
    province = campaign["province"]; city = campaign["city"]
    rows = state["occupied_cities"].get(province, {})
    if city in rows:
        del rows[city]
        if not rows: state["occupied_cities"].pop(province, None)
        lost = state["lost_provinces"].pop(province, None)
        if lost and not any(isinstance(p, dict) and p.get("name") == province for p in _list(getattr(player, "provinces", []))): player.provinces.append(lost)
        _record(player, state, f"{city} освобождён", f"Римская армия восстанавливает власть в провинции {province}.", campaign["power"], ctx, 4)
        return True
    return False


def _campaign_by_id(state: dict, cid: str) -> dict | None:
    return next((c for c in state["campaigns"] if c.get("id") == cid), None)


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx); state = ensure_state(player, ctx); turn = _i(getattr(player, "turn", 1), 1)
    if state.get("last_tick_turn", 0) >= turn: return state
    state["last_tick_turn"] = turn
    army_module = _armies(ctx)
    if army_module is not None and hasattr(army_module, "process_turn"):
        try: army_module.process_turn(player, ctx)
        except Exception: pass
    ai = _ai(ctx)
    if ai is not None and hasattr(ai, "process_turn"):
        try: ai.process_turn(player, ctx)
        except Exception: pass

    wars = _active_wars(player)
    # Блокады ежегодно причиняют ограниченный ущерб и постепенно ослабевают без поддержки.
    for zone, block in list(state["blockades"].items()):
        strength = _clamp(block.get("strength", 0), 0, 100, 0)
        if strength <= 0 or block.get("power") not in wars: state["blockades"].pop(zone, None); continue
        player.gold = max(0, _i(getattr(player, "gold", 0), 0) - max(1, strength // 18))
        player.grain = max(0, _i(getattr(player, "grain", 0), 0) - max(1, strength // 25))
        block["strength"] = max(0, strength - 3)

    for campaign in list(state["campaigns"]):
        if campaign.get("power") not in wars:
            campaign["status"] = "cancelled"; continue
        if campaign.get("status") != "active" or turn < _i(campaign.get("next_action_turn", turn), turn): continue
        if campaign.get("pending_event") and _event_pending(player, campaign, ctx): continue
        campaign["pending_event"] = False
        stage = campaign.get("stage")
        if stage == "planning":
            campaign["progress"] += 1
            if campaign["progress"] >= 1:
                campaign["stage"] = "naval_approach" if campaign.get("type") == "amphibious" else "march"
                campaign["next_action_turn"] = turn + 1; campaign["last_result"] = "армия выступила"
        elif stage == "naval_approach":
            if not _queue_naval(player, campaign, ctx): campaign["next_action_turn"] = turn + 1
        elif stage == "march":
            campaign["progress"] += 1; tempo = _i(POWER_CAMPAIGN_STYLE.get(campaign["power"], {}).get("tempo", 2), 2, 1, 4)
            if campaign["progress"] >= tempo:
                if not _queue_city(player, campaign, ctx): campaign["next_action_turn"] = turn + 1
            else: campaign["next_action_turn"] = turn + 1; campaign["last_result"] = f"марш к {campaign['city']}"
        elif stage == "cooldown":
            campaign["status"] = "completed"
            if ai is not None and hasattr(ai, "get_power_state"):
                try:
                    p = ai.get_power_state(player, campaign["power"], ctx)
                    army = next((a for a in p.get("armies", []) if a.get("id") == campaign.get("army_id")), None)
                    if army: army["stance"] = "reserve"; army["objective"] = None; army["available_turn"] = turn + 1
                except Exception: pass
    state["campaigns"] = [c for c in state["campaigns"] if c.get("status") == "active"]

    for key in wars:
        active = _campaigns_for(state, key); cap = _i(state["settings"].get("max_campaigns_per_power", MAX_CAMPAIGNS_PER_POWER), MAX_CAMPAIGNS_PER_POWER, 1, 4)
        if len(active) >= cap: continue
        next_turn = _i(state["next_campaign_turn"].get(key, turn), turn)
        if turn < next_turn: continue
        power_state = ai.get_power_state(player, key, ctx) if ai is not None and hasattr(ai, "get_power_state") else {}
        exhaustion = _i(_dict(power_state).get("war_exhaustion", 0), 0)
        chance = max(0.12, 0.62 - exhaustion / 160)
        if random.random() <= chance:
            campaign = _create_campaign(player, key, state, ctx)
            if campaign: state["next_campaign_turn"][key] = turn + random.randint(3, 6)
        else: state["next_campaign_turn"][key] = turn + 1
    return state


def _select_roman_group(ui: Any, player: Any, ctx: dict, naval: bool, location: str | None = None) -> dict | None:
    module = _armies(ctx)
    if module is None or not hasattr(module, "available_groups"): return None
    groups = module.available_groups(player, ctx, naval=naval)
    if not groups: return None
    recommended = module.best_group(player, ctx, naval=naval, location=location) if hasattr(module, "best_group") else groups[0]
    ui.section("Рекомендация штаба", "GREEN")
    power = module.group_power(player, recommended, ctx)
    ui.info(f"{recommended.get('name')}: {'морская' if naval else 'полевая'} мощь {power['naval' if naval else 'land']}, готовность {power['readiness']}.", "GREEN")
    print("  1. Принять рекомендацию штаба")
    print("  2. Выбрать другую оперативную армию")
    print("  3. Не выводить армию")
    ch = ui.choice("  Решение: ", ["1", "2", "3"])
    if ch == "1": return recommended
    if ch == "3": return None
    rows = []
    for i, group in enumerate(groups, 1):
        p = module.group_power(player, group, ctx); rows.append((str(i), group.get("name"), group.get("location"), p["naval" if naval else "land"], p["readiness"], group.get("doctrine")))
    ui.table("Доступные армии", ["#", "Армия", "Позиция", "Мощь", "Гот.", "Доктрина"], rows, "CYAN")
    pick = ui.choice("  Армия: ", [str(i) for i in range(1, len(groups) + 1)] + ["Q"])
    return None if pick == "Q" else groups[int(pick) - 1]


def _dice(ctx: dict, roman: int, enemy: int) -> tuple[int, tuple[int, int, int], int, tuple[int, int, int], int]:
    fn = ctx.get("table_3d6_duel_totals")
    if callable(fn):
        try: return fn(roman, enemy)
        except Exception: pass
    rd = tuple(random.randint(1, 6) for _ in range(3)); ed = tuple(random.randint(1, 6) for _ in range(3))
    rt = roman + sum(rd) * 3; et = enemy + sum(ed) * 3
    return rt, rd, et, ed, rt - et


def _format_dice(ctx: dict, dice: tuple[int, int, int]) -> str:
    fn = ctx.get("format_3d6")
    if callable(fn):
        try: return str(fn(dice))
        except Exception: pass
    return f"3d6{dice}"


def _battle_context(player: Any, campaign: dict, ctx: dict) -> tuple[dict, dict, Any]:
    ai = _ai(ctx); power = ai.get_power_state(player, campaign["power"], ctx) if ai is not None and hasattr(ai, "get_power_state") else {}
    army = next((a for a in _list(_dict(power).get("armies")) if a.get("id") == campaign.get("army_id")), None)
    return power, army or {}, ai


def _city_defense(ctx: dict, province: str, city: str) -> int:
    p = _province_def(ctx, province); c = next((x for x in _list(p.get("cities")) if isinstance(x, dict) and x.get("name") == city), {})
    return 12 + _i(p.get("wealth", 3), 3) * 3 + _i(c.get("population", 60), 60) // 8


def _resolve_city_battle(player: Any, campaign: dict, group: dict | None, tactic: str, ctx: dict, ui: Any) -> bool:
    state = ensure_state(player, ctx); power, enemy_army, ai = _battle_context(player, campaign, ctx); key = campaign["power"]
    army_module = _armies(ctx)
    if group is None:
        outcome = _occupy_city(player, state, campaign, ctx, unopposed=True); _war_score(player, key, -12)
        campaign["stage"] = "cooldown"; campaign["next_action_turn"] = _i(getattr(player, "turn", 1), 1) + 2; campaign["last_result"] = outcome
        ui.wrap(f"Рим не выводит полевую армию. {campaign['city']} остаётся перед лицом организованного вторжения без оперативной деблокады.", "RED")
        ui.info(f"Результат: {outcome}.", "RED"); ui.pause(); return True
    gp = army_module.group_power(player, group, ctx); enemy = ai.land_power(player, key, ctx, campaign.get("army_id")) if ai is not None and hasattr(ai, "land_power") else 80
    city_bonus = _city_defense(ctx, campaign["province"], campaign["city"])
    location_bonus = 18 if group.get("location") in {campaign["province"], campaign["city"]} else -max(0, 18 - gp.get("mobility", 0) // 8)
    if tactic == "field": roman = gp["attack"] + gp["mobility"] // 2 + location_bonus; enemy = int(enemy * 1.05)
    elif tactic == "fortify": roman = gp["defense"] + city_bonus + location_bonus; enemy = int(enemy * 0.98)
    else: roman = gp["land"] + gp["mobility"] + location_bonus; enemy = int(enemy * 0.92)
    occupied = bool(_occupied(state, campaign["province"], campaign["city"]))
    if occupied: roman += 8; enemy += 15
    rt, rd, et, ed, margin = _dice(ctx, max(1, roman), max(1, enemy)); won = margin >= 0
    ui.screen(); ui.header(f"БИТВА ЗА {campaign['city'].upper()}", "⚔", f"{group.get('name')} против {enemy_army.get('name', power.get('name', key))}")
    ui.info(f"Рим: {_format_dice(ctx, rd)} + мощь {roman} = {rt}", "GREEN")
    ui.info(f"Враг: {_format_dice(ctx, ed)} + мощь {enemy} = {et}", "RED")
    severity = min(55, 10 + abs(margin) // 4)
    army_module.apply_battle_result(player, group, won, abs(margin), ctx, naval=False)
    if ai is not None and hasattr(ai, "apply_land_losses"): ai.apply_land_losses(player, key, campaign.get("army_id"), severity, not won, ctx)
    group["location"] = campaign["province"]; group["stance"] = "defend" if won else "refit"
    if won:
        recaptured = _recapture_city(player, state, campaign, ctx); player.glory = _i(getattr(player, "glory", 0), 0) + 12 + min(20, abs(margin) // 5)
        _war_score(player, key, 10 + min(12, abs(margin) // 8)); result = "город освобождён" if recaptured else "наступление противника сорвано"
        campaign["last_result"] = result; ui.wrap(f"Рим удерживает поле. {result.capitalize()}.", "GREEN")
    else:
        result = _occupy_city(player, state, campaign, ctx); _war_score(player, key, -10 - min(12, abs(margin) // 8)); campaign["last_result"] = result
        ui.wrap(f"Оперативная армия отступает. Враг входит в {campaign['city']}; результат: {result}.", "RED")
    campaign["stage"] = "cooldown"; campaign["next_action_turn"] = _i(getattr(player, "turn", 1), 1) + 2; campaign["pending_event"] = False
    _record(player, state, "Навязанное сражение завершено", f"{campaign['city']}: {'победа Рима' if won else 'победа ' + power.get('name', key)}; разница {margin:+}.", key, ctx, 5)
    ui.pause(); return True


def _city_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    state = ensure_state(player, ctx); campaign = _campaign_by_id(state, str(_dict(event.get("payload")).get("campaign_id", "")))
    if not campaign: return True
    key = campaign["power"]; nation = _nation(ctx, key); power, enemy_army, ai = _battle_context(player, campaign, ctx)
    ui.screen(); ui.header(f"ВРАГ У {campaign['city'].upper()}", "⚔", "I. Донесение разведки и требование немедленного решения")
    ui.wrap(f"Армия «{enemy_army.get('name', nation.get('name', key))}» под командованием {enemy_army.get('commander', 'неизвестного полководца')} достигла провинции {campaign['province']}. Цель операции — {campaign['city']}.")
    ui.info(f"Доктрина державы: {nation.get('war_doctrine', 'не установлена')}", "RED")
    ui.info(f"Оценка сухопутной мощи: {ai.land_power(player, key, ctx, campaign.get('army_id')) if ai is not None and hasattr(ai, 'land_power') else 'неизвестна'}.", "CYAN")
    ui.pause("Созвать военный совет...")
    ui.screen(); ui.header("CONSILIUM BELLI", "🏛", "II. Выбор оперативной армии")
    group = _select_roman_group(ui, player, ctx, naval=False, location=campaign["province"])
    if group is None:
        ui.screen(); ui.header("ГОРОД ОСТАЁТСЯ БЕЗ ПОЛЕВОЙ АРМИИ", "☠", "III. Последствия отказа от генерального боя")
        return _resolve_city_battle(player, campaign, None, "abandon", ctx, ui)
    ui.screen(); ui.header("ПЛАН СРАЖЕНИЯ", "🗺", "III. Рим выбирает способ принять навязанный бой")
    print("  1. Выйти навстречу и искать решающее полевое сражение")
    print("  2. Опираясь на стены, принять оборонительную битву у города")
    print("  3. Изматывать колонны, перерезать снабжение и ударить после марша")
    tactic = {"1": "field", "2": "fortify", "3": "harass"}[ui.choice("  План: ", ["1", "2", "3"])]
    ui.pause("Развернуть знамёна и начать сражение...")
    return _resolve_city_battle(player, campaign, group, tactic, ctx, ui)


def _resolve_naval_battle(player: Any, campaign: dict, group: dict | None, tactic: str, ctx: dict, ui: Any) -> bool:
    state = ensure_state(player, ctx); key = campaign["power"]; power, enemy_army, ai = _battle_context(player, campaign, ctx); army_module = _armies(ctx)
    if group is None:
        _apply_blockade(player, state, campaign, ctx, severity=35); _war_score(player, key, -8)
        campaign["stage"] = "march"; campaign["progress"] = 0; campaign["next_action_turn"] = _i(getattr(player, "turn", 1), 1) + 1; campaign["pending_event"] = False
        ui.wrap("Римский флот не выходит в море. Противник получает свободу манёвра, прикрывает транспорты и устанавливает блокаду.", "RED"); ui.pause(); return True
    gp = army_module.group_power(player, group, ctx); roman = gp["naval"]; enemy = ai.naval_power(player, key, ctx) if ai is not None and hasattr(ai, "naval_power") else 50
    if tactic == "line": roman += gp.get("cohesion", 0) // 3
    elif tactic == "boarding": roman += gp.get("land", 0) // 12; enemy = int(enemy * 1.03)
    else: roman += gp.get("mobility", 0) // 2; enemy = int(enemy * 0.95)
    rt, rd, et, ed, margin = _dice(ctx, max(1, roman), max(1, enemy)); won = margin >= 0
    zone_name = _dict(_dict(ctx.get("SEA_ZONES")).get(campaign.get("sea_zone"))).get("name", campaign.get("sea_zone"))
    ui.screen(); ui.header(f"МОРСКАЯ БИТВА: {str(zone_name).upper()}", "⚓", f"{group.get('name')} против флота державы {power.get('name', key)}")
    ui.info(f"Рим: {_format_dice(ctx, rd)} + мощь {roman} = {rt}", "GREEN"); ui.info(f"Враг: {_format_dice(ctx, ed)} + мощь {enemy} = {et}", "RED")
    severity = min(55, 10 + abs(margin) // 4)
    army_module.apply_battle_result(player, group, won, abs(margin), ctx, naval=True)
    if ai is not None and hasattr(ai, "apply_naval_losses"): ai.apply_naval_losses(player, key, severity, not won, ctx)
    if won:
        _lift_blockade(state, campaign.get("sea_zone")); _war_score(player, key, 8 + min(10, abs(margin) // 9)); player.glory = _i(getattr(player, "glory", 0), 0) + 10
        campaign["type"] = "land"; campaign["stage"] = "march"; campaign["progress"] = 0; campaign["last_result"] = "вражеская высадка лишилась морского прикрытия"
        # Разбитая высадка задерживается и несёт дополнительный урон.
        if ai is not None and hasattr(ai, "apply_land_losses"): ai.apply_land_losses(player, key, campaign.get("army_id"), max(5, severity // 2), False, ctx)
        ui.wrap("Рим сохраняет контроль моря. Вражеская армия вынуждена искать сухопутный путь и теряет темп.", "GREEN")
    else:
        _apply_blockade(player, state, campaign, ctx, severity=25 + min(25, abs(margin) // 4)); _war_score(player, key, -8 - min(10, abs(margin) // 9))
        campaign["stage"] = "march"; campaign["progress"] = 1; campaign["last_result"] = "вражеский флот открыл путь высадке"
        ui.wrap("Противник удерживает морскую зону, высаживает войска и перехватывает торговые суда.", "RED")
    campaign["next_action_turn"] = _i(getattr(player, "turn", 1), 1) + 1; campaign["pending_event"] = False
    _record(player, state, "Самостоятельное морское сражение", f"{zone_name}: {'победа Рима' if won else 'победа ' + power.get('name', key)}; разница {margin:+}.", key, ctx, 5)
    ui.pause(); return True


def _naval_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    state = ensure_state(player, ctx); campaign = _campaign_by_id(state, str(_dict(event.get("payload")).get("campaign_id", "")))
    if not campaign: return True
    key = campaign["power"]; nation = _nation(ctx, key); ai = _ai(ctx); zone_name = _dict(_dict(ctx.get("SEA_ZONES")).get(campaign.get("sea_zone"))).get("name", campaign.get("sea_zone"))
    ui.screen(); ui.header("ВРАЖЕСКИЕ ПАРУСА НА ГОРИЗОНТЕ", "⚓", "I. Флот противника сам ищет сражения")
    ui.wrap(f"Флот державы {nation.get('name', key)} входит в {zone_name}, прикрывая перевозку армии к городу {campaign['city']}. Если Рим уклонится, противник установит блокаду и высадится без боя.")
    ui.info(f"Оценка морской мощи: {ai.naval_power(player, key, ctx) if ai is not None and hasattr(ai, 'naval_power') else 'неизвестна'}.", "RED")
    ui.pause("Созвать адмирала и командующих армиями...")
    ui.screen(); ui.header("CONSILIUM CLASSIS", "🏛", "II. Выбор соединения с прикреплёнными эскадрами")
    group = _select_roman_group(ui, player, ctx, naval=True, location=campaign.get("sea_zone"))
    if group is None:
        ui.screen(); ui.header("МОРЕ УСТУПЛЕНО ПРОТИВНИКУ", "☠", "III. Блокада и беспрепятственная высадка")
        return _resolve_naval_battle(player, campaign, None, "avoid", ctx, ui)
    ui.screen(); ui.header("ПЛАН МОРСКОЙ БИТВЫ", "🌊", "III. Тактика римского флота")
    print("  1. Держать линию, использовать тараны и дисциплину эскадр")
    print("  2. Сблизиться, применить corvus и абордажные команды кораблей")
    print("  3. Ударить по транспортам и уклоняться от тяжёлых кораблей")
    tactic = {"1": "line", "2": "boarding", "3": "transports"}[ui.choice("  План: ", ["1", "2", "3"])]
    ui.pause("Поднять сигналы и начать бой...")
    return _resolve_naval_battle(player, campaign, group, tactic, ctx, ui)


def handle_council_event(player: Any, event: dict, ctx: dict | None, ui: Any) -> bool:
    ctx = _ctx(ctx); event_type = str(event.get("type", ""))
    if event_type == "battle.city": return _city_event(player, event, ctx, ui)
    if event_type == "battle.naval": return _naval_event(player, event, ctx, ui)
    return True


def expire_council_event(player: Any, event: dict, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx); state = ensure_state(player, ctx); campaign = _campaign_by_id(state, str(_dict(event.get("payload")).get("campaign_id", "")))
    if not campaign: return
    if event.get("type") == "battle.naval":
        _apply_blockade(player, state, campaign, ctx, severity=40); campaign["stage"] = "march"; campaign["progress"] = 1
        _record(player, state, "Рим не ответил на вызов в море", f"Флот державы {_nation(ctx, campaign['power']).get('name', campaign['power'])} устанавливает блокаду и высаживает армию.", campaign["power"], ctx, 5)
    elif event.get("type") == "battle.city":
        result = _occupy_city(player, state, campaign, ctx, unopposed=True); campaign["stage"] = "cooldown"
        _record(player, state, "Рим не явился к месту сражения", f"Город {campaign['city']} занят без генерального боя; результат: {result}.", campaign["power"], ctx, 5)
    campaign["pending_event"] = False; campaign["next_action_turn"] = _i(getattr(player, "turn", 1), 1) + 1



def open_province_menu(player: Any, province_name: str, ctx: dict | None = None) -> None:
    """Показывает вражеские кампании и оккупации, связанные с одной провинцией.

    Это обзор оборонительного театра. Наступательные приказы римским группам
    выдаются из меню провинций через ``roma_army_groups.open_province_operations``.
    """
    ctx = _ctx(ctx)
    ui = UI(ctx)
    state = ensure_state(player, ctx)
    process_turn(player, ctx)
    province_name = str(province_name or "").strip() or "Latium"
    zone = _sea_zone_for(ctx, province_name)
    zone_data = _dict(_dict(ctx.get("SEA_ZONES")).get(zone)) if zone else {}

    campaigns = [
        row for row in _list(state.get("campaigns"))
        if isinstance(row, dict)
        and row.get("status", "active") == "active"
        and str(row.get("province", "")) == province_name
    ]
    occupied = _dict(_dict(state.get("occupied_cities")).get(province_name))
    lost = _dict(_dict(state.get("lost_provinces")).get(province_name))
    blockade = _dict(_dict(state.get("blockades")).get(zone)) if zone else {}

    ui.screen()
    ui.header(
        f"BELLUM IN {province_name.upper()}",
        "🛡",
        "Вражеские кампании, оккупация городов и морское давление на выбранном театре",
    )
    ui.table("Оперативное состояние", ["Показатель", "Значение"], [
        ("Активные кампании", len(campaigns)),
        ("Оккупированные города", len(occupied)),
        ("Статус провинции", "утрачена" if lost else "под контролем Рима / не завоёвана"),
        ("Морская зона", zone_data.get("name", zone or "нет")),
        ("Блокада", f"{blockade.get('strength', 0)} — {_nation(ctx, blockade.get('power', '')).get('name', blockade.get('power', ''))}" if blockade else "нет"),
    ], "RED")

    if campaigns:
        ui.table("Кампании противника", ["Держава", "Тип", "Стадия", "Цель", "Итог", "След. ход"], [
            (
                _nation(ctx, row.get("power", "")).get("name", row.get("power", "")),
                row.get("type", "land"),
                row.get("stage", "planning"),
                row.get("city", province_name),
                row.get("last_result", "—"),
                row.get("next_action_turn", "—"),
            )
            for row in campaigns
        ], "RED")
    else:
        ui.info("На этой провинции нет активной наступательной кампании ИИ.", "GRAY")

    if occupied:
        ui.table("Оккупированные города", ["Город", "Оккупант", "С хода", "Побед"], [
            (
                city,
                _nation(ctx, data.get("power", "")).get("name", data.get("power", "")),
                data.get("since_turn", "—"),
                data.get("victories", 0),
            )
            for city, data in occupied.items() if isinstance(data, dict)
        ], "PURPLE")

    relevant_history = [
        item for item in _list(state.get("history"))
        if isinstance(item, dict) and province_name.lower() in str(item.get("text", "")).lower()
    ]
    if relevant_history:
        ui.table("Последние события театра", ["Ход", "Держава", "Событие", "Итог"], [
            (
                item.get("turn", "—"),
                _nation(ctx, item.get("power", "")).get("name", item.get("power") or "—"),
                item.get("title", "—"),
                item.get("text", "—"),
            )
            for item in reversed(relevant_history[-12:])
        ], "CYAN")

    ui.wrap(
        "Боевые приказы римским группам армий выдаются в карточке самой провинции. "
        "Bellum Provinciale здесь показывает только действия противника и последствия войны.",
        "CYAN",
    )
    ui.pause()

def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx); ui = UI(ctx); state = ensure_state(player, ctx)
    while True:
        process_turn(player, ctx)
        ui.screen(); ui.header("BELLUM UNIVERSALE", "⚔", f"Самостоятельные кампании, городские и морские сражения ИИ — {MODULE_VERSION}")
        if state["campaigns"]:
            ui.table("Активные кампании", ["Держава", "Тип", "Стадия", "Цель", "Результат", "След. ход"], [
                (_nation(ctx, c["power"]).get("name", c["power"]), c.get("type"), c.get("stage"), f"{c.get('city')} / {c.get('province')}", c.get("last_result"), c.get("next_action_turn")) for c in state["campaigns"]
            ], "RED")
        else: ui.info("Активных наступательных кампаний нет.", "GRAY")
        occupied_rows = []
        for province, cities in state["occupied_cities"].items():
            for city, data in cities.items(): occupied_rows.append((province, city, _nation(ctx, data.get("power", "")).get("name", data.get("power")), data.get("since_turn"), data.get("victories")))
        if occupied_rows: ui.table("Оккупированные города", ["Провинция", "Город", "Оккупант", "С хода", "Побед"], occupied_rows, "PURPLE")
        if state["blockades"]: ui.table("Морские блокады", ["Зона", "Держава", "Давление", "С хода"], [(z, _nation(ctx, d.get("power", "")).get("name", d.get("power")), d.get("strength"), d.get("since_turn")) for z, d in state["blockades"].items()], "BLUE")
        print("  1. Архив операций")
        print("  2. Состояние оперативных армий Рима")
        print("  3. Экономика и вооружённые силы ИИ")
        print("  Q. Назад")
        ch = ui.choice("\n  Выбор: ", ["1", "2", "3", "Q"])
        if ch == "Q": return
        if ch == "1":
            ui.screen(); ui.header("ACTA BELLORUM", "📜")
            if state["history"]: ui.table("Последние операции", ["Ход", "Держава", "Событие", "Итог"], [(x.get("turn"), _nation(ctx, x.get("power", "")).get("name", x.get("power") or "—"), x.get("title"), x.get("text")) for x in reversed(state["history"][-50:])], "CYAN")
            else: ui.info("Архив пуст.", "GRAY")
            ui.pause()
        elif ch == "2":
            module = _armies(ctx)
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
        elif ch == "3":
            module = _ai(ctx)
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
