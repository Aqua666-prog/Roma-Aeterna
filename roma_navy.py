#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna 3.0.1 — MARE NOSTRUM CORE.

Самостоятельное ядро флота Рима.

Модуль намеренно не импортирует ``roma_aeterna`` и не обращается к
``game_price`` или Roma Economica. Благодаря этому содержание флота может
входить в экономический контекст, не создавая цикл:

    economy context -> fleet upkeep -> market price -> economy context

Старое состояние ``player.v24['fleet']`` сохраняется как совместимый alias на
``player.navy_system['fleet']``. Поэтому прежнее меню, старые сохранения и
оперативные армии продолжают работать во время постепенного переноса морских
механик в отдельный модуль.

Публичный контракт:
    ensure_state(player, ctx=None, legacy_fleet=None)
    raw_upkeep(player, ctx=None)
    upkeep(player, ctx=None)
    economy_snapshot(player, ctx=None)
    squadron_value(squadron, key, ctx=None)
    naval_power(player, ctx=None, zone_id=None)
    maneuver(player, ctx=None)
    marine_power(player, ctx=None)
    transport_capacity(player, ctx=None)
    apply_losses(player, severity, won, ctx=None, zone_id=None)
    process_turn(player, ctx=None)
    audit_invariants(player, ctx=None)
"""
from __future__ import annotations

import copy
import math
import random
import uuid
from typing import Any

MODULE_VERSION = "3.0.1-mare-nostrum-core"
SCHEMA_VERSION = 1
MAX_HISTORY = 240


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


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _ctx(ctx: dict | None) -> dict:
    return ctx if isinstance(ctx, dict) else {}


def _zones(ctx: dict) -> dict:
    return _dict(ctx.get("SEA_ZONES"))


def _types(ctx: dict) -> dict:
    return _dict(ctx.get("FLEET_SQUADRON_TYPES"))


def _orders(ctx: dict) -> dict:
    return _dict(ctx.get("NAVAL_ORDERS"))


def _default_zone(ctx: dict) -> str:
    zones = _zones(ctx)
    return "tyrrhenian" if "tyrrhenian" in zones else (next(iter(zones), "tyrrhenian"))


def _default_fleet(ctx: dict) -> dict:
    zones = _zones(ctx)
    return {
        "squadrons": [],
        "flagships": [],
        "ships": [],
        "admiral": "Гай Дуилий",
        "naval_tradition": 0,
        "pirate_threat": 24,
        "sea_control": 10,
        "captured_islands": [],
        "sea_zone_control": {key: 0 for key in zones},
        "zone_piracy": {
            key: _i(_dict(row).get("base_pirates", 20), 20, 0, 100)
            for key, row in zones.items()
        },
        "zone_blockade": {key: 0 for key in zones},
        "zone_weather": {
            key: str(_dict(row).get("weather", "calm"))
            for key, row in zones.items()
        },
        "ports": {},
        "sea_routes": [],
        "convoy_readiness": 35,
        "landing_preparations": {key: 0 for key in zones},
        "naval_intel": 0,
        "last_naval_report": [],
    }


def _normalize_squadron(raw: dict, ctx: dict) -> dict | None:
    types = _types(ctx)
    legacy_map = _dict(ctx.get("LEGACY_FLAGSHIP_TO_SQUADRON"))
    kind = str(raw.get("type", ""))
    if kind not in types:
        kind = str(legacy_map.get(kind, ""))
    if kind not in types:
        return None
    zones = _zones(ctx)
    orders = _orders(ctx)
    zone = str(raw.get("zone", _default_zone(ctx)))
    if zones and zone not in zones:
        zone = _default_zone(ctx)
    order = str(raw.get("order", "reserve"))
    if orders and order not in orders:
        order = "reserve"
    default_name = str(_dict(types.get(kind)).get("name", kind))
    return {
        "id": str(raw.get("id") or "SQ-" + uuid.uuid4().hex[:10]),
        "type": kind,
        "name": str(raw.get("name") or default_name),
        "xp": _i(raw.get("xp", 0), 0, 0),
        "damage": _i(raw.get("damage", 0), 0, 0, 100),
        "zone": zone,
        "order": order,
        "morale": _i(raw.get("morale", 70), 70, 0, 100),
    }


def _merge_legacy(base: dict, legacy: dict, ctx: dict) -> dict:
    result = copy.deepcopy(base)
    if not legacy:
        return result

    normalized: list[dict] = []
    for raw in _list(legacy.get("squadrons")):
        if isinstance(raw, dict):
            row = _normalize_squadron(raw, ctx)
            if row:
                normalized.append(row)

    if not normalized:
        for raw in _list(legacy.get("flagships")) + _list(legacy.get("ships")):
            if isinstance(raw, dict):
                row = _normalize_squadron(raw, ctx)
                if row:
                    normalized.append(row)
    result["squadrons"] = normalized

    for key in (
        "admiral", "naval_tradition", "pirate_threat", "sea_control",
        "convoy_readiness", "naval_intel",
    ):
        if key in legacy:
            result[key] = copy.deepcopy(legacy[key])

    result["captured_islands"] = list(dict.fromkeys(str(x) for x in _list(legacy.get("captured_islands"))))
    result["sea_routes"] = list(dict.fromkeys(str(x) for x in _list(legacy.get("sea_routes"))))
    result["last_naval_report"] = [str(x) for x in _list(legacy.get("last_naval_report"))][-8:]
    result["ports"] = {
        str(key): {
            "level": _i(_dict(value).get("level", 1), 1, 1, 5),
            "damage": _i(_dict(value).get("damage", 0), 0, 0, 100),
        }
        for key, value in _dict(legacy.get("ports")).items()
    }

    zones = _zones(ctx)
    for zone, spec in zones.items():
        result["sea_zone_control"][zone] = _i(
            _dict(legacy.get("sea_zone_control")).get(zone, result["sea_zone_control"].get(zone, 0)),
            0, 0, 100,
        )
        result["zone_piracy"][zone] = _i(
            _dict(legacy.get("zone_piracy")).get(zone, _dict(spec).get("base_pirates", 20)),
            _i(_dict(spec).get("base_pirates", 20), 20), 0, 100,
        )
        result["zone_blockade"][zone] = _i(
            _dict(legacy.get("zone_blockade")).get(zone, 0), 0, 0, 100,
        )
        weather = str(_dict(legacy.get("zone_weather")).get(zone, _dict(spec).get("weather", "calm")))
        result["zone_weather"][zone] = weather if weather in {"calm", "windy", "storm"} else "calm"
        result["landing_preparations"][zone] = _i(
            _dict(legacy.get("landing_preparations")).get(zone, 0), 0, 0, 100,
        )
    return result


def ensure_state(player: Any, ctx: dict | None = None, legacy_fleet: dict | None = None) -> dict:
    """Возвращает единое состояние флота и создаёт alias для старого v24."""
    ctx = _ctx(ctx)
    system = getattr(player, "navy_system", None)
    if not isinstance(system, dict):
        system = {}
        player.navy_system = system
    system.setdefault("schema", SCHEMA_VERSION)
    system.setdefault("version", MODULE_VERSION)
    system.setdefault("history", [])
    system.setdefault("last_tick_turn", 0)
    system.setdefault("migrated", False)

    stored = system.get("fleet") if isinstance(system.get("fleet"), dict) else None
    if stored is None:
        source = legacy_fleet if isinstance(legacy_fleet, dict) else {}
        stored = _merge_legacy(_default_fleet(ctx), source, ctx)
        system["fleet"] = stored
        system["migrated"] = True
    else:
        # Нормализация без уничтожения новых данных.
        normalized = _merge_legacy(_default_fleet(ctx), stored, ctx)
        stored.clear()
        stored.update(normalized)
        system["fleet"] = stored

    system["history"] = [x for x in _list(system.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    system["last_tick_turn"] = _i(system.get("last_tick_turn", 0), 0, 0)
    system["schema"] = SCHEMA_VERSION
    system["version"] = MODULE_VERSION

    # Совместимость со всем старым кодом Mare Nostrum.
    if not isinstance(getattr(player, "v24", None), dict):
        player.v24 = {}
    player.v24["fleet"] = stored
    player.navy_system = system
    return stored


def squadron_value(squadron: dict, key: str, ctx: dict | None = None) -> int:
    ctx = _ctx(ctx)
    spec = _dict(_types(ctx).get(str(squadron.get("type", ""))))
    raw = _i(spec.get(key, 0), 0)
    damage = _i(squadron.get("damage", 0), 0, 0, 100)
    morale = _i(squadron.get("morale", 70), 70, 0, 100)
    xp = _i(squadron.get("xp", 0), 0, 0)
    xp_bonus = xp // 2 if key in {"power", "maneuver", "marines", "escort"} else 0
    value = (raw + xp_bonus) * max(0.15, (100 - damage) / 100.0) * (0.75 + morale / 250.0)
    return max(0, int(round(value)))


def raw_upkeep(player: Any, ctx: dict | None = None) -> int:
    """Базовое содержание без уровня цен и без вызова экономики."""
    ctx = _ctx(ctx)
    fleet = ensure_state(player, ctx)
    types = _types(ctx)
    raw = sum(
        _i(_dict(types.get(str(sq.get("type", "")))).get("upkeep", 0), 0)
        for sq in _list(fleet.get("squadrons")) if isinstance(sq, dict)
    )
    raw += sum(
        max(0, _i(_dict(port).get("level", 1), 1, 1, 5) - 1) * 3
        for port in _dict(fleet.get("ports")).values()
    )
    researched = set(str(x) for x in _list(getattr(player, "tech_researched", [])))
    if "naval_supply" in researched:
        raw -= 4
    return max(0, raw)


def _fixed_upkeep_scale(ctx: dict) -> float:
    """Только статическая дороговизна; динамический рынок запрещён."""
    configured = ctx.get("_configured_price_scale")
    if callable(configured):
        try:
            return max(1.0, min(10.0, _f(configured(upkeep=True), 1.5)))
        except Exception:
            pass
    settings = _dict(ctx.get("SETTINGS"))
    return max(1.0, min(10.0, _f(settings.get("global_upkeep_multiplier", 1.5), 1.5)))


def upkeep(player: Any, ctx: dict | None = None) -> int:
    """Фактическое содержание, безопасное для включения в экономический контекст."""
    ctx = _ctx(ctx)
    base = raw_upkeep(player, ctx)
    if base <= 0:
        return 0
    return max(0, int(math.ceil(base * _fixed_upkeep_scale(ctx))))


def economy_snapshot(player: Any, ctx: dict | None = None) -> dict[str, int]:
    ctx = _ctx(ctx)
    fleet = ensure_state(player, ctx)
    return {
        "raw_upkeep": raw_upkeep(player, ctx),
        "upkeep": upkeep(player, ctx),
        "squadrons": len([x for x in _list(fleet.get("squadrons")) if isinstance(x, dict)]),
        "ports": len(_dict(fleet.get("ports"))),
        "routes": len(_list(fleet.get("sea_routes"))),
    }


def maneuver(player: Any, ctx: dict | None = None) -> int:
    ctx = _ctx(ctx)
    return sum(squadron_value(sq, "maneuver", ctx) for sq in ensure_state(player, ctx).get("squadrons", []))


def marine_power(player: Any, ctx: dict | None = None) -> int:
    ctx = _ctx(ctx)
    return sum(squadron_value(sq, "marines", ctx) for sq in ensure_state(player, ctx).get("squadrons", []))


def transport_capacity(player: Any, ctx: dict | None = None) -> int:
    ctx = _ctx(ctx)
    return sum(squadron_value(sq, "cargo", ctx) for sq in ensure_state(player, ctx).get("squadrons", []))


def naval_power(player: Any, ctx: dict | None = None, zone_id: str | None = None) -> int:
    ctx = _ctx(ctx)
    fleet = ensure_state(player, ctx)
    squadrons = [
        sq for sq in _list(fleet.get("squadrons"))
        if isinstance(sq, dict)
        and _i(sq.get("damage", 0), 0) < 100
        and (zone_id is None or str(sq.get("zone")) == str(zone_id))
    ]
    power = sum(squadron_value(sq, "power", ctx) for sq in squadrons)
    power += _i(fleet.get("naval_tradition", 0), 0) // 4
    power += max(0, _i(getattr(player, "morale", 70), 70) - 50) // 5
    if zone_id:
        power += _i(_dict(fleet.get("sea_zone_control")).get(zone_id, 0), 0) // 3
        power -= _i(_dict(fleet.get("zone_piracy")).get(zone_id, 0), 0) // 8
        power -= _i(_dict(fleet.get("zone_blockade")).get(zone_id, 0), 0) // 10
        weather = str(_dict(fleet.get("zone_weather")).get(zone_id, "calm"))
        power -= 2 if weather == "windy" else 6 if weather == "storm" else 0
    return max(0, int(power))


def apply_losses(
    player: Any,
    severity: float,
    won: bool,
    ctx: dict | None = None,
    zone_id: str | None = None,
) -> dict[str, int]:
    """Наносит потери конкретным эскадрам без обращения к экономике."""
    ctx = _ctx(ctx)
    fleet = ensure_state(player, ctx)
    candidates = [
        sq for sq in _list(fleet.get("squadrons"))
        if isinstance(sq, dict)
        and _i(sq.get("damage", 0), 0) < 100
        and (zone_id is None or str(sq.get("zone")) == str(zone_id))
    ]
    severity = max(0.05, min(1.0, _f(severity, 0.25)))
    damaged = destroyed = 0
    for sq in candidates:
        chance = severity * (0.55 if won else 0.95)
        if random.random() > chance:
            continue
        delta = random.randint(4, 12) + int(severity * (18 if won else 34))
        sq["damage"] = _i(sq.get("damage", 0), 0, 0, 100) + delta
        sq["damage"] = min(100, sq["damage"])
        sq["morale"] = max(0, _i(sq.get("morale", 70), 70) - random.randint(3, 10))
        damaged += 1
        if sq["damage"] >= 100:
            destroyed += 1
    return {"damaged": damaged, "destroyed": destroyed}


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx)
    fleet = ensure_state(player, ctx)
    system = player.navy_system
    turn = _i(getattr(player, "turn", 1), 1, 1)
    if _i(system.get("last_tick_turn", 0), 0) >= turn:
        return fleet
    system["last_tick_turn"] = turn
    system.setdefault("history", []).append({
        "turn": turn,
        "squadrons": len(fleet.get("squadrons", [])),
        "upkeep": upkeep(player, ctx),
        "sea_control": _i(fleet.get("sea_control", 0), 0, 0, 100),
    })
    system["history"] = system["history"][-MAX_HISTORY:]
    return fleet


def audit_invariants(player: Any, ctx: dict | None = None) -> list[str]:
    ctx = _ctx(ctx)
    fleet = ensure_state(player, ctx)
    errors: list[str] = []
    seen: set[str] = set()
    for index, sq in enumerate(_list(fleet.get("squadrons"))):
        if not isinstance(sq, dict):
            errors.append(f"Эскадра #{index + 1} не является словарём.")
            continue
        sid = str(sq.get("id", ""))
        if not sid:
            errors.append(f"У эскадры #{index + 1} нет id.")
        elif sid in seen:
            errors.append(f"Повторяющийся id эскадры: {sid}.")
        seen.add(sid)
        if not 0 <= _i(sq.get("damage", 0), 0) <= 100:
            errors.append(f"Некорректные повреждения эскадры {sq.get('name')}.")
    if upkeep(player, ctx) < 0:
        errors.append("Содержание флота отрицательно.")
    if not isinstance(getattr(player, "v24", None), dict) or player.v24.get("fleet") is not fleet:
        errors.append("Старый alias player.v24['fleet'] не связан с navy_system.")
    return errors
