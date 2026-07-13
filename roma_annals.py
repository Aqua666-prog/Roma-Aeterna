#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROMA AETERNA — ANNALES IMPERII / CHRONICA URBIS

Летопись имеет два разных слоя:
    1) краткие анналы — связный исторический рассказ о годе;
    2) tabularium — полный технический журнал событий, бросков и последствий.

Публичный контракт:
    ensure_state(player)
    begin_turn(player)
    record_event(player, ...)
    finalize_turn(player)
    show_turn_annals(player, ctx=None, turn_record=None, pause=True)
    show_turn_journal(player, ctx=None, turn_record=None, pause=True)
    open_history(player, ctx=None)
    install(game_globals)

Модуль не импортирует roma_aeterna.py и не создаёт циклических импортов.
"""
from __future__ import annotations

import copy
import re
import textwrap
import time
import uuid
from typing import Any

MODULE_VERSION = "2.0.1-chronica-urbis"
SCHEMA_VERSION = 3
MAX_HISTORY = 600
MAX_EVENTS_PER_TURN = 120

CATEGORY_META = {
    "military": ("⚔", "Военное дело"),
    "naval": ("⚓", "Флот и море"),
    "barbaricum": ("🐺", "Barbaricum"),
    "diplomacy": ("🌍", "Дипломатия"),
    "economy": ("💰", "Экономика"),
    "politics": ("🏛", "Политика и Сенат"),
    "society": ("👥", "Народ и общество"),
    "religion": ("🕯", "Религия"),
    "science": ("🔬", "Наука"),
    "construction": ("🏗", "Строительство"),
    "province": ("🗺", "Провинции"),
    "disaster": ("☠", "Бедствия"),
    "general": ("📜", "Общее"),
}

SEVERITY_LABELS = {
    1: "обычное",
    2: "заметное",
    3: "важное",
    4: "критическое",
    5: "великое",
}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _plain(text: Any) -> str:
    value = str(text or "")
    value = re.sub(r"\x1b\[[0-9;]*m", "", value)
    value = re.sub(r"\[[^\]]+\]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _sentence(text: Any) -> str:
    value = _plain(text)
    if not value:
        return ""
    value = value[0].upper() + value[1:]
    return value if value.endswith((".", "!", "?", ";")) else value + "."


def _join_ru(items: list[str]) -> str:
    clean = [str(x).strip() for x in items if str(x).strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    return ", ".join(clean[:-1]) + " и " + clean[-1]


def _snapshot(player) -> dict:
    provinces = _list(getattr(player, "provinces", []))
    legions = _list(getattr(player, "legions", []))
    factions = _list(getattr(player, "ai_factions", []))
    enemy_pressure = max(
        [_int(getattr(f, "influence", 0), 0) for f in factions if not getattr(f, "defeated", False)] or [0]
    )
    province_unrest = [
        _int(p.get("unrest", 0), 0)
        for p in provinces
        if isinstance(p, dict)
    ]
    barbarian_state = _dict(getattr(player, "barbarian_world", {}))
    return {
        "turn": _int(getattr(player, "turn", 0), 0),
        "year": _int(getattr(player, "year", 0), 0),
        "gold": _int(getattr(player, "gold", 0), 0),
        "grain": _int(getattr(player, "grain", 0), 0),
        "glory": _int(getattr(player, "glory", 0), 0),
        "morale": _int(getattr(player, "morale", 0), 0),
        "unrest": _int(getattr(player, "unrest", 0), 0),
        "senate_rep": _int(getattr(player, "senate_rep", 0), 0),
        "people_rep": _int(getattr(player, "people_rep", 0), 0),
        "faith": _int(getattr(player, "faith", 0), 0),
        "science": _int(getattr(player, "science_points", 0), 0),
        "provinces": len(provinces),
        "legions": len(legions),
        "max_enemy_influence": enemy_pressure,
        "max_province_unrest": max(province_unrest or [0]),
        "barbarian_pressure": _int(barbarian_state.get("pressure", 0), 0),
    }


def ensure_state(player) -> dict:
    """Создаёт и мигрирует сериализуемое состояние летописи."""
    state = getattr(player, "annals_state", None)
    if not isinstance(state, dict):
        state = {}
        player.annals_state = state

    state.setdefault("history", [])
    state.setdefault("current", [])
    state.setdefault("pending", [])
    state.setdefault("active", False)
    state.setdefault("snapshot_before", {})
    state.setdefault("snapshot_checkpoint", {})
    state.setdefault("last_turn_id", "")
    state.setdefault("settings", {})

    previous_schema = _int(state.get("schema", 1), 1)
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state["current"] = [x for x in _list(state.get("current")) if isinstance(x, dict)][-MAX_EVENTS_PER_TURN:]
    state["pending"] = [x for x in _list(state.get("pending")) if isinstance(x, dict)][-MAX_EVENTS_PER_TURN:]
    state["active"] = bool(state.get("active", False))

    if previous_schema < 2 and not state["active"] and state["current"]:
        state["pending"] = (state["current"] + state["pending"])[-MAX_EVENTS_PER_TURN:]
        state["current"] = []

    settings = _dict(state.get("settings"))
    settings.setdefault("auto_show", True)
    settings.setdefault("show_reasons", True)
    settings.setdefault("min_severity", 1)
    settings.setdefault("max_summary_events", 5)
    settings.setdefault("auto_view", "chronicle")
    settings.setdefault("journal_limit", 80)
    settings["auto_show"] = bool(settings.get("auto_show", True))
    settings["show_reasons"] = bool(settings.get("show_reasons", True))
    settings["min_severity"] = max(1, min(5, _int(settings.get("min_severity", 1), 1)))
    old_max = _int(settings.get("max_summary_events", 5), 5)
    settings["max_summary_events"] = max(3, min(8, 5 if old_max > 8 else old_max))
    settings["auto_view"] = "journal" if settings.get("auto_view") == "journal" else "chronicle"
    settings["journal_limit"] = max(20, min(120, _int(settings.get("journal_limit", 80), 80)))
    state["settings"] = settings

    checkpoint = _dict(state.get("snapshot_checkpoint"))
    if not checkpoint:
        checkpoint = _snapshot(player)
    state["snapshot_checkpoint"] = checkpoint

    before = _dict(state.get("snapshot_before"))
    if state["active"] and not before:
        state["snapshot_before"] = copy.deepcopy(checkpoint)
    elif not state["active"]:
        state["snapshot_before"] = {}

    # Старые записи не переписываются, но получают новый формат при показе.
    state["schema"] = SCHEMA_VERSION
    return state


def begin_turn(player) -> None:
    state = ensure_state(player)
    if state.get("active"):
        return
    state["current"] = copy.deepcopy(_list(state.get("pending")))[:MAX_EVENTS_PER_TURN]
    state["pending"] = []
    state["active"] = True
    checkpoint = _dict(state.get("snapshot_checkpoint")) or _snapshot(player)
    state["snapshot_before"] = copy.deepcopy(checkpoint)


def classify_event(text: str) -> tuple[str, int, bool]:
    low = _plain(text).lower()
    category = "general"
    severity = 1
    great = False

    # Сначала распознаются точные игровые форматы, затем широкие словари.
    if any(w in low for w in ("roma capta", "столица пала", "чума", "голод", "катастроф", "разграб", "уничтожен в битве")):
        category = "disaster"
    elif low.startswith("ауксилия") or low.startswith("бой:") or "легион" in low and any(w in low for w in ("бой", "побед", "поражен", "деблокад")):
        category = "barbaricum" if any(w in low for w in ("местные племена", "варвар", "герман", "гот", "гунн", "свев")) else "military"
    elif any(w in low for w in ("взят город", "занял город", "город потерян", "провинция потеряна", "римский контроль")):
        category = "province"
    elif any(w in low for w in ("дар наместника", "золот", "зерн", "доход", "расход", "рынок", "торгов", "налог", "казн", "дань", "содержание")):
        category = "economy"
    elif any(w in low for w in ("флот", "морская победа", "морское поражение", "эскадр", "десант", "порт", "пират", "захвачен остров")):
        category = "naval"
    elif any(w in low for w in ("barbaricum", "варвар", "плем", "миграц", "набег", "федерат", "герман", "гот", "гунн", "свев", "фронтир")):
        category = "barbaricum"
    elif any(w in low for w in ("бой", "битв", "легион", "ауксили", "арм", "осад", "побед", "поражен", "штурм", "артиллери")):
        category = "military"
    elif any(w in low for w in ("провинц", "романизац", "наместник")):
        category = "province"
    elif any(w in low for w in ("посол", "диплом", "договор", "ультимат", "коалиц", "держава", "объявила войну", "внешняя политика")):
        category = "diplomacy"
    elif any(w in low for w in ("сенат", "закон", "консул", "диктатур", "партия", "род ", "аристократ", "репутац")):
        category = "politics"
    elif any(w in low for w in ("раб", "народ", "гражданск", "мятеж", "восстан", "беспоряд")):
        category = "society"
    elif any(w in low for w in ("религи", "вера", "храм", "жрец", "культ", "пророч")):
        category = "religion"
    elif any(w in low for w in ("наук", "исслед", "технолог", "школ", "архив", "мастерск")):
        category = "science"
    elif any(w in low for w in ("постро", "строитель", "форум", "дорог", "акведук", "чудо", "укреплен")):
        category = "construction"

    if category == "disaster":
        severity = 4
    elif any(w in low for w in ("roma capta", "раздел империи", "пал карфаген", "основан константинополь")):
        severity = 5
        great = True
    elif any(w in low for w in ("гражданская война", "великий поход", "антиримская коалиция", "объявила войну", "провинция потеряна")):
        severity = 4
    elif any(w in low for w in ("взят город", "захвачен остров", "победа", "поражение", "миграция", "восстан", "осада", "потерян", "повысила ранг")):
        severity = 3
    elif any(w in low for w in ("заверш", "создан", "построен", "заключён", "открыт", "изучена", "принял")):
        severity = 2

    if any(w in low for w in ("содержание", "баттл-пасс", "ждёт ответа", "итоги ресурсов")):
        severity = min(severity, 1)
    if "научные школы и архивы" in low:
        severity = 2
    return category, severity, great


def infer_reasons(player, text: str, category: str) -> list[dict]:
    """Возвращает только причины, относящиеся к самому событию.

    Общий снимок державы более не приклеивается к каждой записи: число легионов,
    мораль и влияние врага выводятся лишь тогда, когда действительно объясняют
    результат конкретного события.
    """
    snap = _snapshot(player)
    clean = _plain(text)
    low = clean.lower()
    reasons: list[dict] = []

    def add(label: str, value: Any = None, direction: str = "neutral", weight: int = 0) -> None:
        key = (label.casefold(), str(value))
        if any((str(r.get("label", "")).casefold(), str(r.get("value"))) == key for r in reasons):
            return
        reasons.append({"label": label, "value": value, "direction": direction, "weight": weight})

    score = re.search(r"\((\d+)\s*:\s*(\d+)(?:,|;|\))", clean)
    if score:
        roman, enemy = int(score.group(1)), int(score.group(2))
        margin = roman - enemy
        if margin >= 12:
            add("Убедительный тактический перевес", f"{roman}:{enemy}", "up", 4)
        elif margin > 0:
            add("Небольшой перевес решил исход боя", f"{roman}:{enemy}", "up", 3)
        elif margin <= -12:
            add("Противник добился решающего перевеса", f"{roman}:{enemy}", "down", 4)
        else:
            add("Рим уступил в равном столкновении", f"{roman}:{enemy}", "down", 3)

    tactics = re.search(r",\s*([^,()]+?)\s+vs\s+([^()]+?)\)", clean, flags=re.IGNORECASE)
    if tactics:
        add("Выбранный римский боевой порядок", tactics.group(1).strip(), "neutral", 2)

    if "взят город" in low or "захвачен остров" in low or "взял второй город" in low:
        add("Успешное завершение военной операции", None, "up", 4)
    elif "город" in low and any(w in low for w in ("враг занял", "потерян", "удерживает")):
        add("Оборона города не смогла остановить противника", None, "down", 4)

    if "повысила ранг" in low or "ветеран" in low:
        add("Боевой опыт, накопленный в прежних столкновениях", None, "up", 3)
    if "содержание" in low:
        add("Регулярные обязательства по снабжению войск", None, "neutral", 2)
    if "дар наместника" in low:
        add("Лояльность провинциальной администрации", None, "up", 3)
    if "законы республики" in low:
        add("Действие принятых государственных законов", None, "up", 3)
    if any(w in low for w in ("школ", "архив", "мастерск")) and "+" in low:
        add("Государственное покровительство образованию и ремеслу", None, "up", 3)
    if "ждёт ответа" in low or "просьба рода" in low:
        add("Патронатные обязательства перед знатным родом", None, "neutral", 2)
    if "баттл-пасс" in low:
        add("Награда за общий ход кампании", None, "up", 1)

    pressure = re.search(r"давлен(?:ие|ия)\s+(\d+)\s*/\s*100", low)
    if pressure:
        value = int(pressure.group(1))
        add("Давление на пограничье", value, "down" if value >= 60 else "neutral", 3)
    if any(w in low for w in ("набег", "миграц", "самовольное поселение")):
        add("Активность племён за пределами римского порядка", None, "down", 3)
    if "федерат" in low:
        add("Соглашение о поселении и военной службе", None, "neutral", 3)

    if "побед" in low or "отбил" in low or "разбил" in low:
        if snap["morale"] >= 80 and category in {"military", "naval", "barbaricum"}:
            add("Высокий боевой дух войск", snap["morale"], "up", 2)
    if "поражен" in low or "проиграл" in low or "пала" in low:
        if snap["morale"] < 60:
            add("Ослабленный боевой дух державы", snap["morale"], "down", 3)
    if "восстан" in low or "мятеж" in low or "беспоряд" in low:
        if snap["unrest"] >= 30:
            add("Накопившееся общественное недовольство", snap["unrest"], "down", 4)
    if "голод" in low:
        add("Недостаточные запасы зерна", snap["grain"], "down", 5)

    return reasons[:3]


def _battle_parts(title: str) -> tuple[str, str, str, int | None, int | None, str, str] | None:
    m = re.search(
        r"^(?:⚔\s*)?Бой:\s*(.+?)\s+против\s+(.+?)\s+—\s+(победа|поражение)\s*\((\d+)\s*:\s*(\d+)(?:,\s*(.+?)\s+vs\s+(.+?))?\)$",
        _plain(title), flags=re.IGNORECASE,
    )
    if not m:
        return None
    return (
        m.group(1).strip(), m.group(2).strip(), m.group(3).lower(),
        int(m.group(4)), int(m.group(5)), (m.group(6) or "").strip(), (m.group(7) or "").strip(),
    )


def _aux_parts(title: str) -> tuple[str, str, str] | None:
    clean = _plain(title)
    outcome = "победа" if any(w in clean.lower() for w in ("победа", "отбила", "разбил")) else "поражение" if any(w in clean.lower() for w in ("поражение", "проиграла")) else ""
    m = re.search(r"Ауксилия(?:\s+автобоем)?(?:\s+(?:отбила|проиграла)\s+[^:]+)?\s*:\s*(.+?)\s+против\s+(.+?)(?:\s+—|\s*\(|$)", clean, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip(), outcome


def _event_narrative(event: dict) -> str:
    title = _plain(event.get("title", ""))
    low = title.lower()
    category = event.get("category", "general")

    battle = _battle_parts(title)
    if battle:
        actor, enemy, outcome, roman, hostile, tactic, enemy_tactic = battle
        if outcome == "победа":
            first = f"Воины {actor} сошлись с силами «{enemy}» и одержали победу"
        else:
            first = f"Воины {actor} вступили в бой с силами «{enemy}», но были вынуждены уступить"
        second = f"Исход был решён со счётом {roman}:{hostile}"
        if tactic:
            second += f"; римляне применили тактику «{tactic}»"
        return _sentence(first) + " " + _sentence(second)

    aux = _aux_parts(title)
    if aux:
        unit, enemy, outcome = aux
        if outcome == "победа":
            return _sentence(f"Союзный отряд «{unit}» остановил силы «{enemy}» и заслужил признание командования")
        if outcome == "поражение":
            return _sentence(f"Союзный отряд «{unit}» не сумел удержать натиск сил «{enemy}»")
        return _sentence(f"Ауксилия «{unit}» была направлена против сил «{enemy}»")

    m = re.search(r"Взят город\s+(.+?)\s+в провинции\s+(.+?)\s+легионом\s+(.+)$", title, flags=re.IGNORECASE)
    if m:
        city, province, legion = m.group(1), m.group(2), m.group(3)
        return _sentence(f"После успешной операции {legion} овладел городом {city}; римская власть в провинции {province} укрепилась")

    m = re.search(r"Враг занял\s+(.+?)\s+в\s+(.+?)(?:;|$)", title, flags=re.IGNORECASE)
    if m:
        return _sentence(f"Противник овладел городом {m.group(1)} в провинции {m.group(2)}, и Сенату пришлось готовить ответную операцию")

    m = re.search(r"Провинция\s+(.+?)\s+потеряна", title, flags=re.IGNORECASE)
    if m:
        return _sentence(f"Рим лишился провинции {m.group(1)}; известие об этом стало тяжёлым ударом для Республики")

    m = re.search(r"Ауксилия повысила ранг:\s*(.+?)\s+—\s+(.+)$", title, flags=re.IGNORECASE)
    if m:
        return _sentence(f"За проявленную стойкость отряд «{m.group(1)}» был причислен к категории «{m.group(2)}»")

    m = re.search(r"Научные школы и архивы:\s*\+(\d+)\s+очков науки", title, flags=re.IGNORECASE)
    if m:
        return _sentence(f"Школы, архивы и мастерские Республики прибавили {m.group(1)} очков к общему запасу знаний")

    m = re.search(r"Дар наместника\s+(.+?):\s*\+(\d+)\s+золота", title, flags=re.IGNORECASE)
    if m:
        return _sentence(f"Наместник {m.group(1)} передал в государственную казну {m.group(2)} золотых")

    m = re.search(r"Просьба рода\s+(.+?):\s*ждёт ответа", title, flags=re.IGNORECASE)
    if m:
        return _sentence(f"Род {m.group(1)} обратился к консулу с прошением, ответ на которое ещё не был дан")

    if "законы республики" in low:
        return _sentence("Принятые прежде законы Республики принесли казне и хлебным складам новые поступления")
    if "содержание ауксилии" in low:
        return _sentence("Казна оплатила обычное содержание союзных подразделений")
    if "содержание артиллерии" in low or "артиллерийские корпуса: содержание" in low:
        return _sentence("На содержание артиллерийских корпусов были отпущены государственные средства")
    if "осадный арсенал: содержание" in low or "содержание осадного арсенала" in low:
        return _sentence("Осадные машины потребовали очередных расходов на хранение и обслуживание")
    if "баттл-пасс" in low:
        return _sentence(title.replace("Баттл-пасс", "Кампания отметила наградой"))

    if category == "barbaricum" or low.startswith("barbaricum:"):
        body = re.sub(r"^barbaricum:\s*", "", title, flags=re.IGNORECASE)
        if "давление" in body.lower():
            return _sentence(f"С пограничья донесли: {body}")
        return _sentence(f"За пределами римского порядка произошло следующее: {body}")

    if category == "naval":
        return _sentence(f"На море было отмечено событие: {title}")
    if category == "politics":
        return _sentence(f"В политической жизни Республики было записано: {title}")
    if category == "religion":
        return _sentence(f"Жрецы и хранители культов засвидетельствовали: {title}")
    if category == "science":
        return _sentence(f"Учёные и мастера Республики сообщили: {title}")
    return _sentence(title)


def record_event(
    player,
    title: str,
    *,
    category: str | None = None,
    severity: int | None = None,
    reasons: list[dict] | None = None,
    effects: list[dict] | None = None,
    chance: int | float | None = None,
    roll: int | float | None = None,
    great: bool | None = None,
    source: str = "game",
    details: str = "",
) -> dict | None:
    state = ensure_state(player)
    clean = _plain(title)
    if not clean:
        return None
    guessed_category, guessed_severity, guessed_great = classify_event(clean)
    category = category or guessed_category
    severity = max(1, min(5, _int(severity, guessed_severity)))
    great = guessed_great if great is None else bool(great)
    event = {
        "id": uuid.uuid4().hex[:12],
        "turn": _int(getattr(player, "turn", 0), 0),
        "year": _int(getattr(player, "year", 0), 0),
        "title": clean,
        "details": _plain(details),
        "category": category if category in CATEGORY_META else "general",
        "severity": severity,
        "great": bool(great),
        "reasons": copy.deepcopy(reasons) if isinstance(reasons, list) else infer_reasons(player, clean, category),
        "effects": copy.deepcopy(effects) if isinstance(effects, list) else [],
        "chance": chance,
        "roll": roll,
        "source": source,
        "created_at": int(time.time()),
    }
    event["narrative"] = _event_narrative(event)

    bucket_name = "current" if state.get("active") else "pending"
    bucket = state[bucket_name]
    dedupe = (event["title"].casefold(), event["category"])
    if any(
        (str(e.get("title", "")).casefold(), e.get("category")) == dedupe
        for e in bucket if isinstance(e, dict)
    ):
        return None
    if len(bucket) >= MAX_EVENTS_PER_TURN:
        return None
    bucket.append(event)
    return event


def _resource_effects(before: dict, after: dict) -> list[dict]:
    labels = {
        "gold": "Казна", "grain": "Зерно", "glory": "Слава", "morale": "Боевой дух",
        "unrest": "Волнения", "senate_rep": "Поддержка Сената", "people_rep": "Поддержка народа",
        "faith": "Вера", "science": "Наука", "provinces": "Провинции", "legions": "Легионы",
    }
    effects = []
    for key, label in labels.items():
        old = _int(before.get(key, 0), 0)
        new = _int(after.get(key, 0), 0)
        delta = new - old
        if delta:
            effects.append({"label": label, "before": old, "after": new, "delta": delta})
    return effects


def _resource_event(turn_record: dict) -> dict | None:
    for event in _list(turn_record.get("events")):
        if isinstance(event, dict) and event.get("source") == "annals" and _list(event.get("effects")):
            return event
    return None


def _event_fingerprint(event: dict) -> str:
    title = _plain(event.get("title", "")).lower()
    aux = _aux_parts(title)
    if aux:
        unit, enemy, outcome = aux
        return "aux|" + re.sub(r"\W+", "", unit.lower()) + "|" + re.sub(r"\W+", "", enemy.lower()) + "|" + outcome
    battle = _battle_parts(event.get("title", ""))
    if battle:
        return "battle|" + re.sub(r"\W+", "", battle[0].lower()) + "|" + re.sub(r"\W+", "", battle[1].lower()) + "|" + battle[2]
    normalized = re.sub(r"^(barbaricum|⚠|☠|⚔|🐺|📜)\s*:?\s*", "", title)
    return re.sub(r"\W+", "", normalized)[:140]


def _battle_margin(event: dict) -> int:
    m = re.search(r"\((\d+)\s*:\s*(\d+)", _plain(event.get("title", "")))
    return abs(int(m.group(1)) - int(m.group(2))) if m else 0


def _is_routine(event: dict) -> bool:
    low = _plain(event.get("title", "")).lower()
    return any(term in low for term in (
        "итоги ресурсов", "содержание ауксилии", "содержание артиллер", "осадный арсенал: содержание",
        "содержание осадного арсенала", "баттл-пасс", "научные школы и архивы", "законы республики",
        "ждёт ответа", "флот и торговля обработаны пакетом",
    ))


def _highlight_score(event: dict) -> int:
    severity = _int(event.get("severity", 1), 1)
    low = _plain(event.get("title", "")).lower()
    score = severity * 10 + (50 if event.get("great") else 0)
    score += {
        "disaster": 22, "province": 18, "military": 10, "naval": 10, "barbaricum": 9,
        "politics": 8, "diplomacy": 8, "society": 7, "religion": 6, "science": 4,
        "construction": 5, "economy": 2, "general": 0,
    }.get(event.get("category"), 0)
    if any(w in low for w in ("взят город", "провинция потеряна", "roma capta", "повысила ранг", "сенат объявил диктатуру")):
        score += 20
    if _is_routine(event):
        score -= 35
    score += min(12, _battle_margin(event) // 3)
    return score


def _select_highlights(turn_record: dict, limit: int = 5) -> list[dict]:
    candidates = [e for e in _list(turn_record.get("events")) if isinstance(e, dict) and not _is_routine(e)]
    candidates.sort(key=lambda e: (_highlight_score(e), _int(e.get("created_at", 0), 0)), reverse=True)
    selected: list[dict] = []
    seen: set[str] = set()
    battle_count = 0
    for event in candidates:
        fp = _event_fingerprint(event)
        if fp in seen:
            continue
        is_battle = _battle_parts(event.get("title", "")) is not None or _aux_parts(event.get("title", "")) is not None
        if is_battle and battle_count >= 2:
            continue
        seen.add(fp)
        selected.append(event)
        battle_count += int(is_battle)
        if len(selected) >= limit:
            break
    return selected


def _unique_events(turn_record: dict) -> list[dict]:
    result = []
    seen = set()
    for event in _list(turn_record.get("events")):
        if not isinstance(event, dict) or _is_routine(event):
            continue
        fp = _event_fingerprint(event)
        if fp in seen:
            continue
        seen.add(fp)
        result.append(event)
    return result


def _build_turn_chronicle(turn_record: dict) -> str:
    year = turn_record.get("year", "?")
    events = _unique_events(turn_record)
    clauses: list[str] = []

    captures = []
    losses = []
    victories = 0
    defeats = 0
    for event in events:
        title = _plain(event.get("title", ""))
        low = title.lower()
        m = re.search(r"Взят город\s+(.+?)\s+в провинции\s+(.+?)\s+легионом", title, flags=re.IGNORECASE)
        if m:
            captures.append(f"{m.group(1)} в {m.group(2)}")
        m = re.search(r"Провинция\s+(.+?)\s+потеряна", title, flags=re.IGNORECASE)
        if m:
            losses.append(m.group(1))
        if any(w in low for w in ("— победа", " отбила ", "одержал победу", "морская победа")):
            victories += 1
        if any(w in low for w in ("— поражение", " проиграл", "потерпел поражение")):
            defeats += 1

    if captures:
        clauses.append(f"римские войска овладели {_join_ru(captures[:4])}")
    if losses:
        clauses.append(f"Республика утратила {_join_ru(losses[:3])}")
    if victories and not captures:
        if victories == 1:
            clauses.append("римское оружие одержало победу в отмеченном летописцами столкновении")
        else:
            clauses.append(f"римское оружие одержало победу в {victories} отмеченных столкновениях")
    elif victories > 1:
        clauses.append(f"кроме того, войска выиграли ещё {victories} столкновения")
    if defeats:
        clauses.append("однако не все военные предприятия завершились успехом" if defeats == 1 else f"однако {defeats} столкновения завершились неудачей")

    important_nonmil = [
        e for e in events
        if e.get("category") in {"politics", "diplomacy", "society", "religion", "science", "construction"}
        and _int(e.get("severity", 1), 1) >= 2
    ]
    if important_nonmil:
        narrative = _plain(important_nonmil[0].get("narrative")) or _event_narrative(important_nonmil[0])
        clauses.append(narrative.rstrip("."))

    resource = _resource_event(turn_record)
    effects = _list(resource.get("effects")) if resource else []
    by_label = {str(e.get("label")): _int(e.get("delta", 0), 0) for e in effects if isinstance(e, dict)}
    gold = by_label.get("Казна", 0)
    grain = by_label.get("Зерно", 0)
    glory = by_label.get("Слава", 0)
    science = by_label.get("Наука", 0)
    if gold > 0:
        clauses.append(f"казна пополнилась на {gold} золотых")
    elif gold < 0:
        clauses.append(f"расходы превысили поступления на {abs(gold)} золотых")
    if grain < 0:
        clauses.append(f"хлебные запасы сократились на {abs(grain)}")
    elif grain > 0 and not gold:
        clauses.append(f"хлебные склады получили ещё {grain} мер зерна")
    if glory >= 25:
        clauses.append("слава Республики заметно возросла")
    if science >= 10:
        clauses.append("учёные и мастера расширили запас государственных знаний")

    after = _dict(turn_record.get("snapshot_after"))
    ending = ""
    if _int(after.get("barbarian_pressure", 0), 0) >= 60:
        ending = "Тем не менее пограничное давление оставалось опасным, и бдительность была необходима."
    elif _int(after.get("max_enemy_influence", 0), 0) >= 65:
        ending = "Несмотря на успехи, влияние внешних противников требовало от Сената осторожности."
    elif _int(after.get("unrest", 0), 0) >= 45 or _int(after.get("max_province_unrest", 0), 0) >= 7:
        ending = "Военные и хозяйственные успехи не устранили внутреннего беспокойства."
    elif clauses:
        ending = "Так завершился год, в целом благоприятный для римского государства."
    else:
        ending = "Год прошёл без деяний, которые летописцы сочли бы достойными пространного рассказа."

    if not clauses:
        return f"В {year} году от основания Города {ending[0].lower() + ending[1:]}"
    body = "; ".join(clauses)
    body = body[0].upper() + body[1:]
    return f"В {year} году от основания Города {body}. {ending}"


def finalize_turn(player) -> dict:
    state = ensure_state(player)
    if not state.get("active"):
        begin_turn(player)
        state = ensure_state(player)

    before = _dict(state.get("snapshot_before")) or _dict(state.get("snapshot_checkpoint"))
    after = _snapshot(player)
    effects = _resource_effects(before, after)
    if effects:
        record_event(
            player,
            "Итоги ресурсов и состояния державы",
            category="economy",
            severity=1,
            reasons=[],
            effects=effects,
            source="annals",
        )

    turn_record = {
        "id": uuid.uuid4().hex[:12],
        "turn": after["turn"],
        "year": after["year"],
        "started_turn": _int(before.get("turn", after["turn"]), after["turn"]),
        "started_year": _int(before.get("year", after["year"]), after["year"]),
        "events": copy.deepcopy(state["current"]),
        "snapshot_before": copy.deepcopy(before),
        "snapshot_after": copy.deepcopy(after),
        "created_at": int(time.time()),
    }
    turn_record["chronicle"] = _build_turn_chronicle(turn_record)
    turn_record["highlight_ids"] = [e.get("id") for e in _select_highlights(turn_record, 5)]

    state["history"].append(turn_record)
    state["history"] = state["history"][-MAX_HISTORY:]
    state["last_turn_id"] = turn_record["id"]
    state["current"] = []
    state["active"] = False
    state["snapshot_before"] = {}
    state["snapshot_checkpoint"] = copy.deepcopy(after)
    state["schema"] = SCHEMA_VERSION
    return turn_record


def _wrap_print(text: str, width: int = 72, indent: str = "  ") -> None:
    for line in textwrap.wrap(_plain(text), width=width, break_long_words=False, break_on_hyphens=False) or [""]:
        print(indent + line)


def _meaningful_reasons(event: dict) -> list[dict]:
    result = []
    generic = {
        "совокупный результат решений и событий хода",
        "совокупный результат решений и событий завершённого хода",
    }
    for reason in _list(event.get("reasons")):
        if not isinstance(reason, dict):
            continue
        if str(reason.get("label", "")).casefold() in generic:
            continue
        result.append(reason)
    return result[:2]


def _compact_effect_lines(turn_record: dict) -> list[str]:
    event = _resource_event(turn_record)
    if not event:
        return []
    lines = []
    for effect in _list(event.get("effects")):
        if not isinstance(effect, dict):
            continue
        delta = _int(effect.get("delta", 0), 0)
        marker = "↑" if delta > 0 else "↓"
        lines.append(
            f"{marker} {effect.get('label', 'Показатель')}: {effect.get('before')} → {effect.get('after')} ({delta:+d})"
        )
    return lines


def _clear(ctx: dict) -> None:
    fn = ctx.get("rui_screen_start") or ctx.get("clear")
    if callable(fn):
        try:
            fn()
        except Exception:
            pass


def show_turn_annals(player, ctx: dict | None = None, turn_record: dict | None = None, pause: bool = True) -> None:
    """Показывает краткие исторические анналы, а не полный отладочный лог."""
    state = ensure_state(player)
    ctx = ctx if isinstance(ctx, dict) else {}
    if turn_record is None:
        history = _list(state.get("history"))
        turn_record = history[-1] if history else None
    if not isinstance(turn_record, dict):
        print("\n  📜 Летопись пока пуста.")
        return

    settings = _dict(state.get("settings"))
    limit = max(3, min(8, _int(settings.get("max_summary_events", 5), 5)))
    highlights = _select_highlights(turn_record, limit)
    chronicle = _plain(turn_record.get("chronicle")) or _build_turn_chronicle(turn_record)

    _clear(ctx)
    print("\n" + "═" * 76)
    print(f"  📜 ANNALES IMPERII — Ход {turn_record.get('turn', '?')}, {turn_record.get('year', '?')} AUC")
    print("═" * 76)
    print("\n  COMMENTARIUS ANNI — СВОДНАЯ ЗАПИСЬ")
    print("  " + "─" * 70)
    _wrap_print(chronicle)

    print("\n  RES GESTAE — ДЕЯНИЯ, ДОСТОЙНЫЕ ПАМЯТИ")
    print("  " + "─" * 70)
    if not highlights:
        print("  Летописцы не выделили отдельных деяний.")
    for index, event in enumerate(highlights, 1):
        icon = CATEGORY_META.get(event.get("category"), CATEGORY_META["general"])[0]
        narrative = _plain(event.get("narrative")) or _event_narrative(event)
        print(f"\n  {index}. {icon}")
        _wrap_print(narrative, width=68, indent="     ")
        if settings.get("show_reasons", True):
            reasons = _meaningful_reasons(event)
            if reasons:
                print("     Основание записи:")
                for reason in reasons:
                    marker = {"up": "↑", "down": "↓", "neutral": "•"}.get(reason.get("direction"), "•")
                    suffix = f": {reason.get('value')}" if reason.get("value") is not None else ""
                    print(f"       {marker} {reason.get('label', 'Обстоятельство')}{suffix}")

    effect_lines = _compact_effect_lines(turn_record)
    if effect_lines:
        print("\n  STATUS REI PUBLICAE — СОСТОЯНИЕ РЕСПУБЛИКИ")
        print("  " + "─" * 70)
        for line in effect_lines:
            print("  " + line)

    total = len([e for e in _list(turn_record.get("events")) if isinstance(e, dict)])
    shown_ids = {e.get("id") for e in highlights}
    hidden = len([e for e in _list(turn_record.get("events")) if isinstance(e, dict) and e.get("id") not in shown_ids and e is not _resource_event(turn_record)])
    print("\n  TABULARIUM")
    print("  " + "─" * 70)
    print(f"  Полный журнал хранит {total} записей; вне кратких анналов осталось {max(0, hidden)}.")
    print("  Откройте «Летопись Империи» → «Полный журнал последнего хода».")
    print("\n" + "═" * 76)
    if pause:
        _pause(ctx)


def _event_lines(event: dict, show_reasons: bool = True) -> list[str]:
    category = event.get("category", "general")
    icon = CATEGORY_META.get(category, CATEGORY_META["general"])[0]
    severity = _int(event.get("severity", 1), 1)
    star = " ★" if event.get("great") else ""
    lines = [f"{icon} {event.get('title', 'Событие')}{star}"]
    details = _plain(event.get("details", ""))
    if details:
        lines.append(f"   {details}")
    chance, roll = event.get("chance"), event.get("roll")
    if chance is not None:
        lines.append(f"   Вероятность: {chance}%" + (f"; бросок: {roll}" if roll is not None else ""))
    if show_reasons:
        reasons = _meaningful_reasons(event)
        if reasons:
            lines.append("   Основания:")
            for reason in reasons:
                marker = {"up": "↑", "down": "↓", "neutral": "•"}.get(reason.get("direction"), "•")
                suffix = f": {reason.get('value')}" if reason.get("value") is not None else ""
                lines.append(f"     {marker} {reason.get('label', 'Обстоятельство')}{suffix}")
    effects = _list(event.get("effects"))
    if effects:
        lines.append("   Последствия:")
        for effect in effects[:20]:
            if not isinstance(effect, dict):
                continue
            delta = _int(effect.get("delta", 0), 0)
            marker = "↑" if delta > 0 else "↓"
            lines.append(f"     {marker} {effect.get('label', 'Показатель')}: {effect.get('before')} → {effect.get('after')} ({delta:+d})")
    if severity >= 4:
        lines.append(f"   Значимость: {SEVERITY_LABELS.get(severity, 'важное')}")
    lines.append(f"   Источник: {event.get('source', 'game')}")
    return lines


def show_turn_journal(player, ctx: dict | None = None, turn_record: dict | None = None, pause: bool = True) -> None:
    """Показывает полный технический tabularium без художественного сокращения."""
    state = ensure_state(player)
    ctx = ctx if isinstance(ctx, dict) else {}
    if turn_record is None:
        history = _list(state.get("history"))
        turn_record = history[-1] if history else None
    if not isinstance(turn_record, dict):
        print("\n  📜 Журнал пока пуст.")
        return
    settings = _dict(state.get("settings"))
    min_severity = _int(settings.get("min_severity", 1), 1)
    limit = _int(settings.get("journal_limit", 80), 80)
    events = [
        e for e in _list(turn_record.get("events"))
        if isinstance(e, dict) and _int(e.get("severity", 1), 1) >= min_severity
    ]
    _clear(ctx)
    print("\n" + "═" * 76)
    print(f"  🗄 TABULARIUM IMPERII — Ход {turn_record.get('turn', '?')}, {turn_record.get('year', '?')} AUC")
    print("═" * 76)
    for index, event in enumerate(events[:limit], 1):
        lines = _event_lines(event, bool(settings.get("show_reasons", True)))
        print(f"\n  {index}. {lines[0]}")
        for line in lines[1:]:
            print("  " + line)
    if len(events) > limit:
        print(f"\n  … скрыто записей: {len(events) - limit}. Увеличьте лимит в настройках.")
    print("\n" + "═" * 76)
    if pause:
        _pause(ctx)


def _read_choice(ctx: dict, prompt: str, valid: list[str]) -> str:
    fn = ctx.get("read_choice")
    if callable(fn):
        try:
            return str(fn(prompt, valid)).upper()
        except Exception:
            pass
    while True:
        try:
            value = input(prompt).strip().upper()
        except (EOFError, KeyboardInterrupt):
            return "Q"
        if value in valid:
            return value


def open_history(player, ctx: dict | None = None) -> None:
    ctx = ctx if isinstance(ctx, dict) else {}
    state = ensure_state(player)
    while True:
        history = _list(state.get("history"))
        print("\n" + "═" * 76)
        pending_count = len(_list(state.get("pending"))) + (len(_list(state.get("current"))) if state.get("active") else 0)
        print(f"  📜 ANNALES IMPERII  •  ходов: {len(history)}  •  незавершённых записей: {pending_count}")
        print(f"  CHRONICA URBIS  •  модуль {MODULE_VERSION}")
        print("═" * 76)
        print("  1. Краткие анналы последнего хода")
        print("  2. Полный журнал последнего хода")
        print("  3. Последние 10 годовых записей")
        print("  4. Великие события")
        print("  5. Фильтр по категории")
        print("  6. Настройки")
        print("  Q. Назад")
        choice = _read_choice(ctx, "  Выбор: ", ["1", "2", "3", "4", "5", "6", "Q"])
        if choice == "Q":
            return
        if choice == "1":
            show_turn_annals(player, ctx)
        elif choice == "2":
            show_turn_journal(player, ctx)
        elif choice == "3":
            print("\n  ПОСЛЕДНИЕ 10 ГОДОВЫХ ЗАПИСЕЙ")
            for record in history[-10:]:
                print(f"\n  {record.get('year')} AUC • ход {record.get('turn')}")
                _wrap_print(_plain(record.get("chronicle")) or _build_turn_chronicle(record), width=68, indent="    ")
            _pause(ctx)
        elif choice == "4":
            great = []
            for record in history:
                for event in _list(record.get("events")):
                    if isinstance(event, dict) and (event.get("great") or _int(event.get("severity", 1), 1) >= 5):
                        great.append(event)
            print("\n  ★ ACTA AETERNA — ВЕЛИКИЕ СОБЫТИЯ")
            if not great:
                print("  Пока ни одно событие не вошло в вечность.")
            for event in great[-50:]:
                narrative = _plain(event.get("narrative")) or _event_narrative(event)
                print(f"\n  ★ {event.get('year')} AUC")
                _wrap_print(narrative, width=68, indent="    ")
            _pause(ctx)
        elif choice == "5":
            keys = list(CATEGORY_META)
            print("\n  Категории:")
            for i, key in enumerate(keys, 1):
                icon, name = CATEGORY_META[key]
                print(f"  {i}. {icon} {name}")
            valid = [str(i) for i in range(1, len(keys) + 1)] + ["Q"]
            pick = _read_choice(ctx, "  Категория: ", valid)
            if pick == "Q":
                continue
            category = keys[int(pick) - 1]
            print(f"\n  {CATEGORY_META[category][1].upper()}")
            found = 0
            for record in history:
                for event in _list(record.get("events")):
                    if isinstance(event, dict) and event.get("category") == category:
                        print(f"\n  {event.get('year')} AUC")
                        _wrap_print(_plain(event.get("narrative")) or _event_narrative(event), width=68, indent="    ")
                        found += 1
            if not found:
                print("  Записей нет.")
            _pause(ctx)
        elif choice == "6":
            settings = state["settings"]
            print("\n  1. Автопоказ:", "включён" if settings.get("auto_show", True) else "выключен")
            print("  2. Объяснения обстоятельств:", "показывать" if settings.get("show_reasons", True) else "скрывать")
            print("  3. Минимальная значимость полного журнала:", settings.get("min_severity", 1))
            print("  4. Число главных деяний:", settings.get("max_summary_events", 5))
            print("  5. Автопоказ открывает:", "полный журнал" if settings.get("auto_view") == "journal" else "краткие анналы")
            print("  6. Лимит полного журнала:", settings.get("journal_limit", 80))
            pick = _read_choice(ctx, "  Изменить (1–6/Q): ", ["1", "2", "3", "4", "5", "6", "Q"])
            if pick == "1":
                settings["auto_show"] = not bool(settings.get("auto_show", True))
            elif pick == "2":
                settings["show_reasons"] = not bool(settings.get("show_reasons", True))
            elif pick == "3":
                settings["min_severity"] = int(_read_choice(ctx, "  Уровень 1–5: ", ["1", "2", "3", "4", "5"]))
            elif pick == "4":
                settings["max_summary_events"] = int(_read_choice(ctx, "  От 3 до 8: ", [str(i) for i in range(3, 9)]))
            elif pick == "5":
                settings["auto_view"] = "journal" if settings.get("auto_view") != "journal" else "chronicle"
            elif pick == "6":
                settings["journal_limit"] = int(_read_choice(ctx, "  Лимит: ", ["20", "40", "60", "80", "100", "120"]))


def _pause(ctx: dict) -> None:
    fn = ctx.get("pause") or ctx.get("rui_pause")
    if callable(fn):
        try:
            fn("Нажмите Enter, чтобы продолжить...")
            return
        except TypeError:
            try:
                fn()
                return
            except Exception:
                pass
    try:
        input("  Нажмите Enter, чтобы продолжить...")
    except (EOFError, KeyboardInterrupt):
        pass


def install(game_globals: dict) -> bool:
    """Встраивает летопись в меню, журнал событий, состояния и конец хода."""
    if not isinstance(game_globals, dict):
        return False
    if game_globals.get("_ANNALES_INSTALLED"):
        return True

    original_summary_add = game_globals.get("turn_summary_add")
    original_log_event = game_globals.get("log_event")
    original_end_turn = game_globals.get("end_turn")
    original_sections = game_globals.get("_main_menu_sections_v2257")
    original_dispatch = game_globals.get("dispatch_main_choice")
    original_ensure_all = game_globals.get("ensure_all_states")
    menu_item_cls = game_globals.get("MenuItem")
    menu_section_cls = game_globals.get("MenuSection")
    color_cls = game_globals.get("C")

    if not all(callable(x) for x in (original_summary_add, original_end_turn, original_sections, original_dispatch)):
        return False

    def wrapped_ensure_all(player, *args, **kwargs):
        result = original_ensure_all(player, *args, **kwargs) if callable(original_ensure_all) else None
        ensure_state(player)
        return result

    def wrapped_log_event(player, message: str, *args, **kwargs):
        result = original_log_event(player, message, *args, **kwargs) if callable(original_log_event) else None
        try:
            record_event(player, str(message), source="event_log")
        except Exception:
            pass
        return result

    def wrapped_summary_add(player, text: str, *args, **kwargs) -> None:
        original_summary_add(player, text, *args, **kwargs)
        try:
            record_event(player, str(text), source="turn_summary")
        except Exception:
            pass

    def _restore_unfinished(player) -> None:
        state = ensure_state(player)
        merged, seen = [], set()
        for event in _list(state.get("current")) + _list(state.get("pending")):
            if not isinstance(event, dict):
                continue
            key = (str(event.get("title", "")).casefold(), event.get("category"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(event)
        state["pending"] = merged[-MAX_EVENTS_PER_TURN:]
        state["current"] = []
        state["active"] = False
        state["snapshot_before"] = {}

    def wrapped_end_turn(player, *args, **kwargs):
        begin_turn(player)
        try:
            result = original_end_turn(player, *args, **kwargs)
        except Exception:
            _restore_unfinished(player)
            raise
        turn_record = finalize_turn(player)
        settings = ensure_state(player).get("settings", {})
        if settings.get("auto_show", True):
            if settings.get("auto_view") == "journal":
                show_turn_journal(player, game_globals, turn_record, pause=True)
            else:
                show_turn_annals(player, game_globals, turn_record, pause=True)
        save_fn = game_globals.get("save_game")
        if callable(save_fn):
            try:
                save_fn(player)
            except Exception:
                pass
        return result

    def wrapped_sections():
        sections = list(original_sections())
        if menu_item_cls is None or menu_section_cls is None:
            return sections
        if any(getattr(item, "key", None) == "N" for section in sections for item in getattr(section, "items", ())):
            return sections
        for index, section in enumerate(sections):
            if getattr(section, "title", "") == "Кампания":
                items = list(getattr(section, "items", ()))
                items.append(menu_item_cls("N", "Летопись Империи", "анналы и полный tabularium", "📜"))
                sections[index] = menu_section_cls(
                    getattr(section, "title", "Кампания"),
                    getattr(section, "icon", "⚔"),
                    getattr(section, "color", getattr(color_cls, "RED", "") if color_cls else ""),
                    tuple(items),
                )
                break
        return sections

    def wrapped_dispatch(player, choice):
        if choice == "N":
            open_history(player, game_globals)
            return True
        return original_dispatch(player, choice)

    if callable(original_ensure_all):
        game_globals["ensure_all_states"] = wrapped_ensure_all
    if callable(original_log_event):
        game_globals["log_event"] = wrapped_log_event
    game_globals["turn_summary_add"] = wrapped_summary_add
    game_globals["end_turn"] = wrapped_end_turn
    game_globals["_main_menu_sections_v2257"] = wrapped_sections
    game_globals["dispatch_main_choice"] = wrapped_dispatch
    game_globals["annals_record_event"] = record_event
    game_globals["annals_open_history"] = open_history
    game_globals["annals_show_journal"] = show_turn_journal
    game_globals["annals_ensure_state"] = ensure_state
    game_globals["ANNALES_MODULE_VERSION"] = MODULE_VERSION
    game_globals["_ANNALES_INSTALLED"] = True
    return True


def _self_test() -> None:
    class P:
        turn = 3
        year = 702
        gold = 260
        grain = 454
        glory = 442
        morale = 95
        unrest = 10
        senate_rep = 55
        people_rep = 60
        faith = 26
        science_points = 12
        provinces = [{"name": "Latium", "unrest": 1}, {"name": "Etruria", "unrest": 1}]
        legions = [object(), object()]
        ai_factions = []
        barbarian_world = {"pressure": 30}

    p = P()
    begin_turn(p)
    record_event(p, "Бой: Legio II Consularis против Местные племена: гарнизон Populonia — победа (37:11, Фронтальный удар vs Осторожное наступление)")
    record_event(p, "Взят город Populonia в провинции Etruria легионом Legio II Consularis")
    record_event(p, "Ауксилия: Союзнические педиты против Регийская морская пехота — победа (59:40; арсенал +0)")
    record_event(p, "Ауксилия автобоем отбила осада: Союзнические педиты против Регийская морская пехота")
    p.gold = 650
    p.grain = 608
    p.glory = 507
    p.morale = 97
    p.faith = 50
    p.science_points = 24
    record = finalize_turn(p)
    assert len(record["events"]) == 5
    assert "Populonia" in record["chronicle"]
    highlights = _select_highlights(record, 5)
    assert len([e for e in highlights if _aux_parts(e.get("title", ""))]) == 1
    assert _compact_effect_lines(record)
    assert ensure_state(p)["history"]


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        _self_test()
        print("roma_annals self-test: OK")
