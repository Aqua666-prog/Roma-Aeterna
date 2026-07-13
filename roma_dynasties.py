#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna — DOMUS ET CONIUGIA.

Династические браки, иностранные царские дома, наследники и интеллектуальный
ИИ супруги. Супруга является постоянным персонажем: помнит решения, оценивает
состояние Рима и родной державы, формирует собственную повестку и инициирует
многоэтапные личные и государственные разговоры после хода.

Публичный контракт:
    ensure_state(player, ctx=None)
    process_turn(player, ctx=None)
    request_marriage(player, power_key, ctx=None)
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

MODULE_VERSION = "1.1.0-consilium-reginae"
SCHEMA_VERSION = 2
MAX_HISTORY = 240


def _i(value: Any, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError, OverflowError): value = default
    if low is not None: value = max(low, value)
    if high is not None: value = min(high, value)
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
    def header(self, title: str, icon: str = "👑", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try: fn(title, icon, getattr(self.C, "PURPLE", ""), subtitle); return
            except TypeError:
                try: fn(title, icon, getattr(self.C, "PURPLE", ""))
                except Exception: pass
        print(self.color(f"\n{'═' * 76}\n  {icon} {title}\n{'═' * 76}", "PURPLE", True))
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


CANDIDATES: dict[str, list[dict[str, Any]]] = {
    "carthage": [
        {"name": "Софонисба Магонова", "house": "Магониды", "age": 24, "traits": ["расчётливая", "красноречивая", "морская торговка"], "intellect": 86, "diplomacy": 88, "intrigue": 79, "stewardship": 84, "ambition": 78, "compassion": 54, "homeland_loyalty": 82, "question": "Готов ли Рим уважать договор, когда ему выгоднее нарушить его?"},
        {"name": "Элисса Ганнонова", "house": "Ганнониды", "age": 27, "traits": ["гордая", "наблюдательная", "бережливая"], "intellect": 82, "diplomacy": 75, "intrigue": 85, "stewardship": 91, "ambition": 84, "compassion": 43, "homeland_loyalty": 88, "question": "Что для тебя важнее: верность Сенату или данное супруге слово?"},
    ],
    "numidia": [
        {"name": "Танит Масиниссова", "house": "Массилы", "age": 22, "traits": ["смелая", "прямая", "чуткая к воинам"], "intellect": 72, "diplomacy": 77, "intrigue": 58, "stewardship": 67, "ambition": 63, "compassion": 80, "homeland_loyalty": 86, "question": "Станешь ли ты слушать человека степи, когда римские сенаторы будут смеяться над его советом?"},
        {"name": "Африка Гулуссова", "house": "Массилы", "age": 25, "traits": ["осторожная", "верная", "проницательная"], "intellect": 78, "diplomacy": 81, "intrigue": 69, "stewardship": 70, "ambition": 55, "compassion": 73, "homeland_loyalty": 79, "question": "Будет ли Нумидия союзницей Рима или всего лишь удобной конюшней?"},
    ],
    "pergamon": [
        {"name": "Стратоника Атталида", "house": "Атталиды", "age": 23, "traits": ["учёная", "мягкая", "политически терпеливая"], "intellect": 94, "diplomacy": 89, "intrigue": 66, "stewardship": 83, "ambition": 60, "compassion": 82, "homeland_loyalty": 74, "question": "Сможет ли Рим побеждать не только мечом, но и школой, законом и милосердием?"},
        {"name": "Апполонида Филетерова", "house": "Филетериды", "age": 29, "traits": ["рациональная", "властная", "покровительница искусств"], "intellect": 91, "diplomacy": 82, "intrigue": 77, "stewardship": 89, "ambition": 81, "compassion": 62, "homeland_loyalty": 71, "question": "Дашь ли ты мне действительную власть или только место на пире?"},
    ],
    "parthia": [
        {"name": "Родогуна Аршакидская", "house": "Аршакиды", "age": 21, "traits": ["гордая", "стратегичная", "неуступчивая"], "intellect": 88, "diplomacy": 72, "intrigue": 82, "stewardship": 69, "ambition": 91, "compassion": 46, "homeland_loyalty": 93, "question": "Если Рим и Парфия столкнутся, кем ты сочтёшь меня: супругой, заложницей или врагом?"},
        {"name": "Муса Фраата", "house": "Аршакиды", "age": 26, "traits": ["обаятельная", "тайная", "настойчивая"], "intellect": 84, "diplomacy": 86, "intrigue": 94, "stewardship": 76, "ambition": 89, "compassion": 51, "homeland_loyalty": 77, "question": "Способен ли правитель отличить совет от манипуляции — и всё же принять хороший совет?"},
    ],
    "egypt": [
        {"name": "Клеопатра Филометора", "house": "Птолемеи", "age": 22, "traits": ["харизматичная", "образованная", "царственная"], "intellect": 95, "diplomacy": 96, "intrigue": 88, "stewardship": 87, "ambition": 94, "compassion": 67, "homeland_loyalty": 85, "question": "Готов ли Рим видеть в Египте равную державу, а во мне — соучастницу власти?"},
        {"name": "Береника Птолемеевна", "house": "Птолемеи", "age": 28, "traits": ["прагматичная", "щедрая", "дворцовая интриганка"], "intellect": 89, "diplomacy": 84, "intrigue": 91, "stewardship": 92, "ambition": 87, "compassion": 58, "homeland_loyalty": 80, "question": "Что ты выберешь, если благополучие Рима потребует унизить мой дом?"},
    ],
    "gauls": [
        {"name": "Камулогена Верцингеторигова", "house": "Арверны", "age": 20, "traits": ["пылкая", "честная", "защитница рода"], "intellect": 75, "diplomacy": 70, "intrigue": 56, "stewardship": 62, "ambition": 72, "compassion": 83, "homeland_loyalty": 95, "question": "Сохранишь ли ты честь моего народа, когда твои легионы потребуют его покорности?"},
        {"name": "Эпона Дивитиакова", "house": "Эдуи", "age": 25, "traits": ["миротворица", "наблюдательная", "религиозная"], "intellect": 83, "diplomacy": 90, "intrigue": 61, "stewardship": 68, "ambition": 57, "compassion": 91, "homeland_loyalty": 88, "question": "Может ли союз с Римом сохранить свободу, или он лишь отсрочит рабство?"},
    ],
}

ACTION_LABELS = {
    "mediate_homeland": "посредничество между Римом и её родиной",
    "secure_trade": "торговое сближение с её родиной",
    "treasury_reform": "реформа дворцовых расходов",
    "grain_relief": "экстренная помощь продовольствием",
    "senate_network": "создание опоры в Сенате",
    "popular_patronage": "народное покровительство",
    "warn_plot": "предупреждение о заговоре",
    "military_advice": "военный совет",
    "heir_question": "вопрос о наследнике",
    "homeland_favor": "просьба в пользу родного дома",
}


RELATIONSHIP_STAGES = {
    0: "политический брак",
    1: "взаимное уважение",
    2: "доверительный союз",
    3: "партнёрство власти",
    4: "единая воля правящего дома",
}

HIDDEN_TIER_LABELS = {
    "none": "неразличимое влияние",
    "subtle_guidance": "тихое влияние",
    "consilium_reginae": "совет супруги",
    "concordia_domus": "согласие правящего дома",
    "imperium_duplex": "двуединая власть",
}

EDUCATION_FOCI = {
    "philosophy": {
        "name": "философская школа",
        "summary": "Супруга хочет пригласить философов, историков и законоведов, чтобы превратить двор в школу государственного мышления.",
        "skills": {"intellect": 7, "wisdom": 6, "diplomacy": 2},
    },
    "rhetoric": {
        "name": "риторика и языки",
        "summary": "Она предлагает собрать переводчиков, риторов и послов, чтобы лучше понимать чужие дворы и управлять переговорами.",
        "skills": {"diplomacy": 7, "intellect": 4, "wisdom": 2},
    },
    "administration": {
        "name": "школа управления",
        "summary": "Она намерена изучать отчёты наместников, казённые книги и практику провинциального управления.",
        "skills": {"stewardship": 7, "intellect": 4, "wisdom": 3},
    },
    "intelligence": {
        "name": "искусство тайной политики",
        "summary": "Она хочет обучить своих доверенных лиц шифрам, проверке донесений и распознаванию дворцовых заговоров.",
        "skills": {"intrigue": 7, "intellect": 4, "wisdom": 2},
    },
    "strategy": {
        "name": "военно-политическая стратегия",
        "summary": "Супруга просит допустить её к картам, донесениям и диспутам полководцев, чтобы изучать войну как продолжение политики.",
        "skills": {"intellect": 6, "wisdom": 5, "diplomacy": 2, "intrigue": 2},
    },
}

ACTION_LEARNING = {
    "mediate_homeland": {"diplomacy": 5, "wisdom": 3, "intellect": 2},
    "secure_trade": {"diplomacy": 4, "stewardship": 4, "intellect": 2},
    "treasury_reform": {"stewardship": 6, "intellect": 3, "wisdom": 2},
    "grain_relief": {"wisdom": 5, "stewardship": 3, "compassion": 2},
    "senate_network": {"intrigue": 5, "diplomacy": 3, "intellect": 2},
    "popular_patronage": {"diplomacy": 3, "wisdom": 4, "compassion": 2},
    "warn_plot": {"intrigue": 6, "intellect": 3, "wisdom": 2},
    "military_advice": {"intellect": 5, "wisdom": 4, "intrigue": 2},
    "heir_question": {"wisdom": 5, "diplomacy": 2, "stewardship": 2},
    "homeland_favor": {"diplomacy": 4, "wisdom": 3, "intrigue": 2},
}


def _nation(ctx: dict, key: str) -> dict:
    module = ctx.get("NATIONS")
    if module is not None and hasattr(module, "get_nation"):
        try: return module.get_nation(key)
        except Exception: pass
    return {"name": key, "marriage_bonus": "династический союз"}


def _world_enqueue(player: Any, ctx: dict, **kwargs: Any) -> bool:
    council = ctx.get("WORLD_COUNCIL")
    if council is None or not hasattr(council, "enqueue"): return False
    return council.enqueue(player, ctx=ctx, **kwargs) is not None


def _ensure_growth_fields(spouse: dict, turn: int) -> None:
    """Мигрирует старую супругу в развивающуюся модель без потери сейва."""
    spouse.setdefault("education", max(10, _i(spouse.get("intellect", 70), 70) // 4))
    spouse.setdefault("wisdom", max(35, (_i(spouse.get("intellect", 70), 70) + _i(spouse.get("stewardship", 65), 65)) // 3))
    spouse.setdefault("political_experience", 0)
    spouse.setdefault("advice_followed", 0)
    spouse.setdefault("advice_compromised", 0)
    spouse.setdefault("advice_rejected", 0)
    spouse.setdefault("obedience_streak", 0)
    spouse.setdefault("obedience_score", 0)
    spouse.setdefault("relationship_stage", 0)
    spouse.setdefault("hidden_tier", "none")
    spouse.setdefault("hidden_tier_turn", turn)
    spouse.setdefault("last_secret_tick_turn", 0)
    spouse.setdefault("next_development_turn", turn + random.randint(4, 7))
    spouse.setdefault("learning_progress", {})
    spouse.setdefault("secret_effect_totals", {})
    spouse.setdefault("secret_history", [])
    spouse.setdefault("development_history", [])
    spouse["education"] = _clamp(spouse.get("education", 10), 0, 100, 10)
    spouse["wisdom"] = _clamp(spouse.get("wisdom", 45), 0, 100, 45)
    spouse["political_experience"] = _i(spouse.get("political_experience", 0), 0, 0, 10000)
    spouse["advice_followed"] = _i(spouse.get("advice_followed", 0), 0, 0, 10000)
    spouse["advice_compromised"] = _i(spouse.get("advice_compromised", 0), 0, 0, 10000)
    spouse["advice_rejected"] = _i(spouse.get("advice_rejected", 0), 0, 0, 10000)
    spouse["obedience_streak"] = _i(spouse.get("obedience_streak", 0), 0, 0, 999)
    spouse["obedience_score"] = _clamp(spouse.get("obedience_score", 0), 0, 100, 0)
    spouse["relationship_stage"] = _i(spouse.get("relationship_stage", 0), 0, 0, 4)
    spouse["hidden_tier"] = str(spouse.get("hidden_tier", "none"))
    if spouse["hidden_tier"] not in HIDDEN_TIER_LABELS: spouse["hidden_tier"] = "none"
    spouse["hidden_tier_turn"] = _i(spouse.get("hidden_tier_turn", turn), turn, 0)
    spouse["last_secret_tick_turn"] = _i(spouse.get("last_secret_tick_turn", 0), 0, 0)
    spouse["next_development_turn"] = _i(spouse.get("next_development_turn", turn + 5), turn + 5, turn)
    spouse["learning_progress"] = {str(k): _i(v, 0, 0, 9999) for k, v in _dict(spouse.get("learning_progress")).items()}
    spouse["secret_effect_totals"] = {str(k): _i(v, 0, -100000, 100000) for k, v in _dict(spouse.get("secret_effect_totals")).items()}
    spouse["secret_history"] = [x for x in _list(spouse.get("secret_history")) if isinstance(x, dict)][-40:]
    spouse["development_history"] = [x for x in _list(spouse.get("development_history")) if isinstance(x, dict)][-50:]


def _relationship_stage(spouse: dict) -> int:
    trust = _clamp(spouse.get("trust", 60), 0, 100, 60)
    opinion = _clamp(spouse.get("opinion", 65), 0, 100, 65)
    obedience = _clamp(spouse.get("obedience_score", 0), 0, 100, 0)
    streak = _i(spouse.get("obedience_streak", 0), 0, 0)
    intellect = _clamp(spouse.get("intellect", 70), 0, 100, 70)
    if trust >= 92 and opinion >= 88 and obedience >= 82 and streak >= 8 and intellect >= 88: return 4
    if trust >= 82 and opinion >= 78 and obedience >= 58 and streak >= 5: return 3
    if trust >= 72 and opinion >= 68 and obedience >= 30: return 2
    if trust >= 60 and opinion >= 58: return 1
    return 0


def _hidden_tier_for(spouse: dict) -> str:
    intellect = _clamp(spouse.get("intellect", 70), 0, 100, 70)
    wisdom = _clamp(spouse.get("wisdom", 45), 0, 100, 45)
    trust = _clamp(spouse.get("trust", 60), 0, 100, 60)
    influence = _clamp(spouse.get("influence", 15), 0, 100, 15)
    obedience = _clamp(spouse.get("obedience_score", 0), 0, 100, 0)
    streak = _i(spouse.get("obedience_streak", 0), 0, 0)
    if intellect >= 96 and wisdom >= 88 and trust >= 94 and influence >= 72 and obedience >= 90 and streak >= 10:
        return "imperium_duplex"
    if intellect >= 90 and wisdom >= 75 and trust >= 88 and influence >= 50 and obedience >= 72 and streak >= 7:
        return "concordia_domus"
    if intellect >= 82 and wisdom >= 62 and trust >= 78 and influence >= 30 and obedience >= 48 and streak >= 4:
        return "consilium_reginae"
    if intellect >= 75 and wisdom >= 50 and trust >= 68 and obedience >= 22 and streak >= 2:
        return "subtle_guidance"
    return "none"


def _grant_learning(spouse: dict, gains: dict[str, int], multiplier: float = 1.0) -> list[str]:
    """Добавляет скрытые очки обучения; возвращает только реально выросшие параметры."""
    progress = spouse.setdefault("learning_progress", {})
    raised: list[str] = []
    for skill, raw_points in gains.items():
        if skill not in {"intellect", "wisdom", "diplomacy", "intrigue", "stewardship", "compassion"}: continue
        current = _clamp(spouse.get(skill, 50), 0, 100, 50)
        if current >= 100: continue
        points = max(0, int(round(raw_points * multiplier)))
        if points <= 0: continue
        progress[skill] = _i(progress.get(skill, 0), 0, 0) + points
        threshold = 9 + current // 18
        while progress[skill] >= threshold and spouse.get(skill, current) < 100:
            progress[skill] -= threshold
            spouse[skill] = _clamp(spouse.get(skill, current) + 1, 0, 100, current)
            current = spouse[skill]
            threshold = 9 + current // 18
            raised.append(skill)
    return raised


def _register_obedience(spouse: dict, choice: str, weight: int = 1) -> None:
    if choice == "1":
        spouse["advice_followed"] = _i(spouse.get("advice_followed", 0), 0) + 1
        spouse["obedience_streak"] = _i(spouse.get("obedience_streak", 0), 0) + max(1, weight)
        spouse["obedience_score"] = _clamp(spouse.get("obedience_score", 0) + 7 * max(1, weight), 0, 100, 0)
    elif choice == "2":
        spouse["advice_compromised"] = _i(spouse.get("advice_compromised", 0), 0) + 1
        spouse["obedience_streak"] = max(0, _i(spouse.get("obedience_streak", 0), 0) - 1)
        spouse["obedience_score"] = _clamp(spouse.get("obedience_score", 0) - 1, 0, 100, 0)
    else:
        spouse["advice_rejected"] = _i(spouse.get("advice_rejected", 0), 0) + 1
        spouse["obedience_streak"] = 0
        spouse["obedience_score"] = _clamp(spouse.get("obedience_score", 0) - 10, 0, 100, 0)


def _develop_after_decision(spouse: dict, action: str, choice: str, effect: str, turn: int) -> list[str]:
    failed_tokens = ("не провед", "отклон", "отмен", "игнор", "резерв сохранён", "не обнаружено")
    failed_execution = any(token in effect.lower() for token in failed_tokens)
    obedience_choice = "2" if choice == "1" and failed_execution else choice
    _register_obedience(spouse, obedience_choice)
    multiplier = 1.25 if choice == "1" else 0.65 if choice == "2" else 0.25
    if failed_execution:
        multiplier *= 0.65
    spouse["political_experience"] = _i(spouse.get("political_experience", 0), 0) + (5 if choice == "1" else 2 if choice == "2" else 1)
    spouse["education"] = _clamp(spouse.get("education", 0) + (2 if choice == "1" else 1 if choice == "2" else 0), 0, 100, 0)
    gains = dict(ACTION_LEARNING.get(action, {"intellect": 2, "wisdom": 2}))
    gains["intellect"] = gains.get("intellect", 0) + max(0, spouse.get("education", 0) // 35)
    raised = _grant_learning(spouse, gains, multiplier)
    spouse.setdefault("development_history", []).append({
        "turn": turn, "source": action, "choice": choice,
        "experience": 5 if choice == "1" else 2 if choice == "2" else 1,
        "raised": list(raised),
    })
    spouse["development_history"] = spouse["development_history"][-50:]
    spouse["relationship_stage"] = _relationship_stage(spouse)
    return raised


def _choose_education_focus(spouse: dict) -> str:
    values = {
        "philosophy": spouse.get("intellect", 70) + spouse.get("wisdom", 45),
        "rhetoric": spouse.get("diplomacy", 70) * 2,
        "administration": spouse.get("stewardship", 65) * 2,
        "intelligence": spouse.get("intrigue", 60) * 2,
        "strategy": spouse.get("intellect", 70) + spouse.get("intrigue", 60),
    }
    # Развивает сравнительно слабое направление, но амбициозная супруга чаще выбирает стратегию.
    if spouse.get("ambition", 60) >= 85 and random.random() < 0.35: return "strategy"
    return min(values, key=values.get)


def _enqueue_education_event(player: Any, spouse: dict, ctx: dict) -> bool:
    focus = _choose_education_focus(spouse)
    data = EDUCATION_FOCI[focus]
    return _world_enqueue(
        player, ctx,
        event_type="spouse.education", title=f"Школа супруги: {data['name']}",
        summary=data["summary"], payload={"focus": focus}, power=spouse.get("power"),
        severity=3, expires_in=6, dedupe="spouse.education",
    )


def _refresh_hidden_state(player: Any, spouse: dict, ctx: dict) -> None:
    turn = _i(getattr(player, "turn", 1), 1)
    spouse["relationship_stage"] = _relationship_stage(spouse)
    old = str(spouse.get("hidden_tier", "none"))
    new = _hidden_tier_for(spouse)
    if old == new: return
    spouse["hidden_tier"] = new
    spouse["hidden_tier_turn"] = turn
    spouse.setdefault("secret_history", []).append({"turn": turn, "from": old, "to": new})
    spouse["secret_history"] = spouse["secret_history"][-40:]
    ranks = ["none", "subtle_guidance", "consilium_reginae", "concordia_domus", "imperium_duplex"]
    if ranks.index(new) > ranks.index(old):
        _world_enqueue(
            player, ctx, event_type="spouse.ascendancy",
            title=f"Незримая перемена при дворе: {spouse.get('name')}",
            summary="Придворные замечают, что решения правящего дома всё чаще складываются в единую, почти безошибочную линию.",
            payload={"old": old, "new": new}, power=spouse.get("power"), severity=4,
            expires_in=8, dedupe=f"spouse.ascendancy:{new}",
        )
    else:
        _record(player, ctx, "Ослабление влияния супруги", "Прежнее согласие правящего дома стало менее устойчивым.", spouse.get("power"), "info")


def _add_secret_total(spouse: dict, key: str, amount: int) -> None:
    totals = spouse.setdefault("secret_effect_totals", {})
    totals[key] = _i(totals.get(key, 0), 0, -100000, 100000) + amount


def _apply_hidden_bonuses(player: Any, spouse: dict, ctx: dict, turn: int) -> None:
    """Применяет один раз за ход нераскрываемые игроку эффекты доверия."""
    if _i(spouse.get("last_secret_tick_turn", 0), 0) >= turn: return
    spouse["last_secret_tick_turn"] = turn
    tier = str(spouse.get("hidden_tier", "none"))
    if tier == "none": return

    gold = science = unrest = morale = senate = people = 0
    if tier == "subtle_guidance":
        gold = 1
        science = 1 if turn % 2 == 0 else 0
        unrest = -1 if turn % 3 == 0 else 0
    elif tier == "consilium_reginae":
        gold = 3; science = 1; unrest = -1
        morale = 1 if turn % 2 == 0 else 0
    elif tier == "concordia_domus":
        gold = 6; science = 2; unrest = -1; morale = 1
        senate = 1 if turn % 3 == 0 else 0
        people = 1 if turn % 4 == 0 else 0
    elif tier == "imperium_duplex":
        gold = 9; science = 3; unrest = -2; morale = 2
        senate = 1; people = 1

    if gold:
        player.gold = _i(getattr(player, "gold", 0), 0) + gold; _add_secret_total(spouse, "gold", gold)
    if science and hasattr(player, "science_points"):
        player.science_points = _i(getattr(player, "science_points", 0), 0) + science; _add_secret_total(spouse, "science", science)
    if unrest and hasattr(player, "unrest"):
        before = _i(getattr(player, "unrest", 0), 0)
        player.unrest = _clamp(before + unrest, 0, 100, before); _add_secret_total(spouse, "unrest", player.unrest - before)
    if morale and hasattr(player, "morale"):
        before = _i(getattr(player, "morale", 70), 70)
        player.morale = _clamp(before + morale, 0, 120, before); _add_secret_total(spouse, "morale", player.morale - before)
    if senate and hasattr(player, "senate_rep"):
        before = _i(getattr(player, "senate_rep", 50), 50)
        player.senate_rep = _clamp(before + senate, 0, 100, before); _add_secret_total(spouse, "senate_rep", player.senate_rep - before)
    if people and hasattr(player, "people_rep"):
        before = _i(getattr(player, "people_rep", 50), 50)
        player.people_rep = _clamp(before + people, 0, 100, before); _add_secret_total(spouse, "people_rep", player.people_rep - before)

    row = _dict(_dict(getattr(player, "diplomacy", {})).get(spouse.get("power")))
    if row and tier in {"consilium_reginae", "concordia_domus", "imperium_duplex"} and turn % 3 == 0:
        row["disposition"] = _clamp(row.get("disposition", 50) + 1, 0, 100, 50)
        if tier in {"concordia_domus", "imperium_duplex"}:
            row["trust"] = _clamp(row.get("trust", 40) + 1, 0, 100, 40)


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    state = getattr(player, "dynasty_system", None)
    if not isinstance(state, dict): state = {}; player.dynasty_system = state
    state.setdefault("schema", SCHEMA_VERSION); state.setdefault("version", MODULE_VERSION)
    state.setdefault("spouse", None); state.setdefault("heirs", []); state.setdefault("history", [])
    state.setdefault("proposed_candidates", []); state.setdefault("rejected_houses", {})
    state.setdefault("last_tick_turn", 0); state.setdefault("next_proposal_turn", 4)
    state.setdefault("dynastic_prestige", 0)
    if state.get("spouse") is not None and not isinstance(state.get("spouse"), dict): state["spouse"] = None
    spouse = state.get("spouse")
    if isinstance(spouse, dict):
        spouse.setdefault("id", uuid.uuid4().hex[:10]); spouse.setdefault("name", "Супруга")
        spouse.setdefault("power", ""); spouse.setdefault("house", "неизвестный дом"); spouse.setdefault("age", 24)
        spouse.setdefault("traits", []); spouse.setdefault("intellect", 70); spouse.setdefault("diplomacy", 70)
        spouse.setdefault("intrigue", 60); spouse.setdefault("stewardship", 65); spouse.setdefault("ambition", 60)
        spouse.setdefault("compassion", 60); spouse.setdefault("homeland_loyalty", 75)
        spouse.setdefault("opinion", 65); spouse.setdefault("trust", 60); spouse.setdefault("influence", 15)
        spouse.setdefault("stress", 10); spouse.setdefault("marriage_turn", _i(getattr(player, "turn", 1), 1))
        spouse.setdefault("next_action_turn", _i(getattr(player, "turn", 1), 1) + 2)
        spouse.setdefault("agenda", "укрепить династию"); spouse.setdefault("memories", [])
        spouse.setdefault("last_action", None); spouse.setdefault("children", 0); spouse.setdefault("question", "")
        for metric in ("intellect", "diplomacy", "intrigue", "stewardship", "ambition", "compassion", "homeland_loyalty", "opinion", "trust", "influence", "stress"):
            spouse[metric] = _clamp(spouse.get(metric, 60), 0, 100, 60)
        spouse["age"] = _i(spouse.get("age", 24), 24, 16, 90); spouse["children"] = _i(spouse.get("children", 0), 0, 0, 20)
        spouse["traits"] = [str(x) for x in _list(spouse.get("traits"))][-8:]
        spouse["memories"] = [x for x in _list(spouse.get("memories")) if isinstance(x, dict)][-30:]
        _ensure_growth_fields(spouse, _i(getattr(player, "turn", 1), 1))
    state["heirs"] = [x for x in _list(state.get("heirs")) if isinstance(x, dict)][-20:]
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state["proposed_candidates"] = [str(x) for x in _list(state.get("proposed_candidates"))][-30:]
    state["rejected_houses"] = {str(k): _i(v, 0, 0) for k, v in _dict(state.get("rejected_houses")).items()}
    state["last_tick_turn"] = _i(state.get("last_tick_turn", 0), 0, 0); state["next_proposal_turn"] = _i(state.get("next_proposal_turn", 4), 4, 1)
    state["dynastic_prestige"] = _i(state.get("dynastic_prestige", 0), 0, 0, 10000)
    state["schema"] = SCHEMA_VERSION; state["version"] = MODULE_VERSION
    player.dynasty_system = state
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
        try: annales.record_event(player, category="politics", title=title, text=text, reason="Династическая политика и решения супруги.", severity=3, data={"power": power, "system": "domus_coniugia"})
        except Exception: pass


def _candidate_id(candidate: dict, power: str) -> str:
    return f"{power}:{candidate.get('name', '')}"


def _available_candidate(player: Any, power: str, ctx: dict) -> dict | None:
    state = ensure_state(player, ctx); candidates = CANDIDATES.get(power, [])
    available = [c for c in candidates if _candidate_id(c, power) not in state["proposed_candidates"]]
    if not available: available = candidates
    if not available: return None
    # ИИ двора выбирает кандидатку под нужды Рима, а не чисто случайно.
    gold_low = _i(getattr(player, "gold", 0), 0) < 150
    senate_low = _i(getattr(player, "senate_rep", 50), 50) < 45
    return max(available, key=lambda c: c.get("stewardship", 0) * (1.3 if gold_low else 0.8) + c.get("diplomacy", 0) * (1.2 if senate_low else 0.9) + c.get("intellect", 0))


def request_marriage(player: Any, power_key: str, ctx: dict | None = None, forced: bool = True) -> bool:
    ctx = _ctx(ctx); state = ensure_state(player, ctx)
    if state.get("spouse"): return False
    row = _dict(_dict(getattr(player, "diplomacy", {})).get(power_key))
    if not row or row.get("at_war") or row.get("client") and row.get("disposition", 0) < 20: return False
    council = ctx.get("WORLD_COUNCIL")
    if council is not None and hasattr(council, "has_pending"):
        try:
            if council.has_pending(player, "marriage.offer", power_key): return False
        except Exception: pass
    candidate = _available_candidate(player, power_key, ctx)
    if not candidate: return False
    if not forced:
        chance = 0.05 + _i(row.get("disposition", 50), 50) / 500 + _i(row.get("trust", 40), 40) / 700
        if row.get("alliance"): chance += 0.10
        if random.random() >= chance: return False
    state["proposed_candidates"].append(_candidate_id(candidate, power_key))
    nation = _nation(ctx, power_key)
    queued = _world_enqueue(
        player, ctx,
        event_type="marriage.offer", title=f"Династическое посольство: {nation.get('name', power_key)}",
        summary=f"Дом {candidate.get('house')} предлагает брак с {candidate.get('name')}.",
        payload={"candidate": copy.deepcopy(candidate)}, power=power_key, severity=5, expires_in=6,
        dedupe=f"marriage.offer:{power_key}",
    )
    if queued: state["next_proposal_turn"] = _i(getattr(player, "turn", 1), 1) + random.randint(7, 12)
    return queued


def _spouse_memory(spouse: dict, turn: int, topic: str, choice: str, effect: str) -> None:
    spouse.setdefault("memories", []).append({"turn": turn, "topic": topic, "choice": choice, "effect": effect})
    spouse["memories"] = spouse["memories"][-30:]


def _choose_spouse_action(player: Any, spouse: dict, ctx: dict) -> tuple[str, str]:
    row = _dict(_dict(getattr(player, "diplomacy", {})).get(spouse.get("power")))
    war_state = _dict(getattr(player, "foreign_warfare", {})); wars = _dict(war_state.get("wars"))
    internal_threat = max([_i(getattr(f, "influence", 0), 0) for f in _list(getattr(player, "ai_factions", [])) if not getattr(f, "defeated", False)] or [0])
    scores = {
        "mediate_homeland": (95 if row.get("at_war") else 5) + spouse["diplomacy"] * 0.35 + spouse["homeland_loyalty"] * 0.45,
        "secure_trade": (35 if not row.get("trade_pact") and not row.get("at_war") else 5) + spouse["stewardship"] * 0.3 + spouse["diplomacy"] * 0.25,
        "treasury_reform": max(0, 220 - _i(getattr(player, "gold", 0), 0)) * 0.35 + spouse["stewardship"] * 0.45,
        "grain_relief": max(0, 160 - _i(getattr(player, "grain", 0), 0)) * 0.4 + spouse["compassion"] * 0.35,
        "senate_network": max(0, 60 - _i(getattr(player, "senate_rep", 50), 50)) * 1.2 + spouse["intrigue"] * 0.3 + spouse["diplomacy"] * 0.2,
        "popular_patronage": max(0, 60 - _i(getattr(player, "people_rep", 50), 50)) * 1.1 + spouse["compassion"] * 0.35,
        "warn_plot": max(0, internal_threat - 45) * 1.3 + spouse["intrigue"] * 0.45,
        "military_advice": (40 if wars else 3) + spouse["intellect"] * 0.35 + spouse["ambition"] * 0.2,
        "heir_question": (50 if spouse.get("children", 0) == 0 and _i(getattr(player, "turn", 1), 1) - spouse.get("marriage_turn", 1) >= 3 else 2) + spouse["ambition"] * 0.25,
        "homeland_favor": spouse["homeland_loyalty"] * 0.55 + spouse["ambition"] * 0.25 + (20 if row.get("tension", 0) > 50 else 0),
    }
    last = spouse.get("last_action")
    if last in scores: scores[last] -= 35
    action = max(scores, key=scores.get)
    reasons = {
        "mediate_homeland": "война с её родиной угрожает и браку, и международному положению Рима",
        "secure_trade": "она видит возможность связать два государства взаимной выгодой",
        "treasury_reform": "расходы двора и казны выглядят для неё неустойчивыми",
        "grain_relief": "она считает, что голод разрушает власть быстрее вражеской армии",
        "senate_network": "без опоры в Сенате династический союз останется хрупким",
        "popular_patronage": "народная репутация правителя требует видимого благодеяния",
        "warn_plot": "её люди заметили опасную концентрацию влияния и тайные встречи",
        "military_advice": "ход войны требует взгляда, не связанного привычками римских полководцев",
        "heir_question": "династия без наследника остаётся временным политическим соглашением",
        "homeland_favor": "родной дом ожидает доказательства, что брак изменил отношения держав",
    }
    return action, reasons[action]


def _enqueue_spouse_action(player: Any, spouse: dict, action: str, reason: str, ctx: dict) -> bool:
    return _world_enqueue(
        player, ctx,
        event_type="spouse.council", title=f"Личная аудиенция: {spouse.get('name')}",
        summary=f"Супруга просит обстоятельного разговора: {ACTION_LABELS.get(action, action)}.",
        payload={"action": action, "reason": reason}, power=spouse.get("power"), severity=4,
        expires_in=5, dedupe=f"spouse.council:{action}",
    )


def process_turn(player: Any, ctx: dict | None = None) -> dict:
    ctx = _ctx(ctx); state = ensure_state(player, ctx); turn = _i(getattr(player, "turn", 1), 1)
    if state.get("last_tick_turn") >= turn: return state
    state["last_tick_turn"] = turn
    spouse = state.get("spouse")
    if not spouse:
        if turn >= state.get("next_proposal_turn", 4):
            diplomacy = _dict(getattr(player, "diplomacy", {}))
            candidates = []
            for key, row in diplomacy.items():
                if not isinstance(row, dict) or row.get("at_war") or row.get("married"): continue
                score = _i(row.get("disposition", 50), 50) + _i(row.get("trust", 40), 40) + (15 if row.get("alliance") else 0) - _i(row.get("tension", 30), 30)
                if score >= 45 and key in CANDIDATES: candidates.append((score, key))
            if candidates:
                _, key = max(candidates)
                if not request_marriage(player, key, ctx, forced=False): state["next_proposal_turn"] = turn + 2
            else: state["next_proposal_turn"] = turn + 3
        return state
    _ensure_growth_fields(spouse, turn)
    spouse["age"] = _i(spouse.get("age", 24), 24) + (1 if turn % 5 == 0 else 0)
    # Даже без отдельного события годы при дворе дают медленный опыт, но не бесплатные уровни.
    spouse["political_experience"] = _i(spouse.get("political_experience", 0), 0) + 1
    if turn % 4 == 0:
        passive = {"intellect": 1, "wisdom": 1}
        if spouse.get("education", 0) >= 60: passive["intellect"] += 1
        _grant_learning(spouse, passive, 1.0)
    # Текущая политика меняет её мнение осмысленно.
    row = _dict(_dict(getattr(player, "diplomacy", {})).get(spouse.get("power")))
    if row.get("alliance") or row.get("trade_pact"): spouse["opinion"] = _clamp(spouse["opinion"] + 1, 0, 100, 65)
    if row.get("at_war"): spouse["stress"] = _clamp(spouse["stress"] + 4, 0, 100, 10); spouse["opinion"] = _clamp(spouse["opinion"] - (2 if spouse["homeland_loyalty"] > 70 else 1), 0, 100, 65)
    else: spouse["stress"] = _clamp(spouse["stress"] - 2, 0, 100, 10)

    _refresh_hidden_state(player, spouse, ctx)
    _apply_hidden_bonuses(player, spouse, ctx, turn)

    council = ctx.get("WORLD_COUNCIL")
    if turn >= _i(spouse.get("next_development_turn", turn + 1), turn + 1):
        pending_education = False
        if council is not None and hasattr(council, "has_pending"):
            try: pending_education = council.has_pending(player, "spouse.education")
            except Exception: pending_education = False
        if not pending_education and _enqueue_education_event(player, spouse, ctx):
            spouse["next_development_turn"] = turn + random.randint(6, 10)

    if turn >= _i(spouse.get("next_action_turn", turn + 1), turn + 1):
        pending = False
        if council is not None and hasattr(council, "has_pending"):
            try: pending = council.has_pending(player, "spouse.council")
            except Exception: pending = False
        if not pending:
            action, reason = _choose_spouse_action(player, spouse, ctx)
            if _enqueue_spouse_action(player, spouse, action, reason, ctx):
                spouse["last_action"] = action; spouse["next_action_turn"] = turn + random.randint(2, 4)
    return state


def _accept_marriage(player: Any, candidate: dict, key: str, ctx: dict, answer_tone: str) -> dict:
    state = ensure_state(player, ctx); spouse = copy.deepcopy(candidate)
    spouse.update({
        "id": uuid.uuid4().hex[:10], "power": key, "opinion": 68 if answer_tone == "respect" else 61,
        "trust": 66 if answer_tone == "respect" else 57, "influence": 18, "stress": 8,
        "marriage_turn": _i(getattr(player, "turn", 1), 1), "next_action_turn": _i(getattr(player, "turn", 1), 1) + 2,
        "agenda": "укрепить новый дом, не предав родину", "memories": [], "last_action": None, "children": 0,
        "education": max(15, _i(candidate.get("intellect", 70), 70) // 3),
        "wisdom": max(40, (_i(candidate.get("intellect", 70), 70) + _i(candidate.get("stewardship", 65), 65)) // 3),
        "political_experience": 0, "advice_followed": 0, "advice_compromised": 0, "advice_rejected": 0,
        "obedience_streak": 0, "obedience_score": 0, "relationship_stage": 1 if answer_tone == "respect" else 0,
        "hidden_tier": "none", "hidden_tier_turn": _i(getattr(player, "turn", 1), 1),
        "last_secret_tick_turn": 0, "next_development_turn": _i(getattr(player, "turn", 1), 1) + random.randint(4, 7),
        "learning_progress": {}, "secret_effect_totals": {}, "secret_history": [], "development_history": [],
    })
    _ensure_growth_fields(spouse, _i(getattr(player, "turn", 1), 1))
    state["spouse"] = spouse; state["dynastic_prestige"] += 20
    row = _dict(getattr(player, "diplomacy", {}).get(key)); row["married"] = True; row["marriage_turn"] = _i(getattr(player, "turn", 1), 1)
    row["disposition"] = _clamp(row.get("disposition", 50) + 18, 0, 100, 50); row["trust"] = _clamp(row.get("trust", 40) + 14, 0, 100, 40)
    row["non_aggression"] = True; row["non_aggression_turn"] = _i(getattr(player, "turn", 1), 1)
    _spouse_memory(spouse, _i(getattr(player, "turn", 1), 1), "first_conversation", answer_tone, "начало брака")
    return spouse


def _marriage_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    key = str(event.get("power")); candidate = _dict(event.get("payload", {}).get("candidate")); nation = _nation(ctx, key)
    row = _dict(_dict(getattr(player, "diplomacy", {})).get(key))
    if ensure_state(player, ctx).get("spouse"): return True
    ui.screen(); ui.header("ДИНАСТИЧЕСКОЕ ПОСОЛЬСТВО", "👑", "I. Публичная аудиенция")
    ui.wrap(f"Послы державы {nation.get('name', key)} предлагают соединить римский правящий дом с домом {candidate.get('house')}. Кандидатка — {candidate.get('name')}, {candidate.get('age')} лет.")
    ui.info(f"Отношение державы: {row.get('disposition', 0)}; доверие: {row.get('trust', 0)}; напряжение: {row.get('tension', 0)}.", "CYAN")
    ui.pause("Открыть досье кандидатки...")

    ui.screen(); ui.header(candidate.get("name", "КАНДИДАТКА"), "🌿", "II. Характер и способности")
    ui.table("Личное досье", ["Параметр", "Значение"], [
        ("Дом", candidate.get("house")), ("Черты", ", ".join(candidate.get("traits", []))),
        ("Интеллект", candidate.get("intellect")), ("Дипломатия", candidate.get("diplomacy")),
        ("Интрига", candidate.get("intrigue")), ("Управление", candidate.get("stewardship")),
        ("Амбиция", candidate.get("ambition")), ("Сострадание", candidate.get("compassion")),
        ("Верность родине", candidate.get("homeland_loyalty")),
    ], "PURPLE")
    ui.wrap(f"Уникальное следствие брака: {nation.get('marriage_bonus', 'династический союз')}", "GREEN")
    ui.pause("Выслушать Сенат и жрецов...")

    ui.screen(); ui.header("ПОЛИТИЧЕСКАЯ ЦЕНА БРАКА", "🏛", "III. Заключение Совета")
    ui.wrap("Брак даст пакт о ненападении, доверие и уникальный бонус державы. Но супруга сохранит личную волю, связь с родным домом и способность вмешиваться в решения. Она не является безмолвным модификатором.")
    print("  1. Продолжить переговоры и встретиться лично")
    print("  2. Вежливо отказаться")
    print("  P. Отложить")
    ch = ui.choice("\n  Решение: ", ["1", "2", "P"])
    if ch == "P": return False
    if ch == "2":
        row["disposition"] = _clamp(row.get("disposition", 50) - 9, 0, 100, 50); row["trust"] = _clamp(row.get("trust", 40) - 6, 0, 100, 40)
        ensure_state(player, ctx)["rejected_houses"][candidate.get("house", "")] = _i(getattr(player, "turn", 1), 1)
        _record(player, ctx, "Династический брак отклонён", f"Рим отказал дому {candidate.get('house')} державы {nation.get('name', key)}.", key, "bad")
        ui.info("Послы приняли отказ, но запомнили нанесённое дому унижение.", "RED"); ui.pause(); return True

    ui.screen(); ui.header("ЛИЧНАЯ БЕСЕДА", "🕯", "IV. Кандидатка говорит без послов")
    ui.wrap(f"{candidate.get('name')} спрашивает: «{candidate.get('question')}»", "CYAN")
    print("  R. Ответить с уважением к её самостоятельности и родине")
    print("  P. Ответить прагматично: интересы Рима всегда выше")
    print("  D. Уклониться от прямого обещания")
    answer = ui.choice("\n  Ответ: ", ["R", "P", "D"])
    tone = "respect" if answer == "R" else "pragmatic" if answer == "P" else "evasive"
    if answer == "R": candidate["opinion_seed"] = 8
    elif answer == "P": candidate["opinion_seed"] = -2
    else: candidate["opinion_seed"] = -5
    ui.pause("Перейти к окончательной клятве...")

    ui.screen(); ui.header("FOEDUS CONIUGII", "💍", "V. Окончательное решение")
    ui.wrap("После личной беседы можно заключить брак либо остановить церемонию до принесения клятв.")
    final = ui.choice("  Заключить брак? (Y/N): ", ["Y", "N"])
    if final == "N":
        row["disposition"] = _clamp(row.get("disposition", 50) - 12, 0, 100, 50); row["trust"] = _clamp(row.get("trust", 40) - 10, 0, 100, 40)
        _record(player, ctx, "Брак сорван перед клятвами", f"Переговоры с домом {candidate.get('house')} завершились унижением.", key, "bad")
        ui.info("Церемония отменена. Последствия будут тяжелее обычного отказа.", "RED"); ui.pause(); return True
    spouse = _accept_marriage(player, candidate, key, ctx, tone)
    spouse["opinion"] = _clamp(spouse["opinion"] + _i(candidate.get("opinion_seed", 0), 0), 0, 100, 65)
    ui.screen(); ui.header("ДИНАСТИЧЕСКИЙ СОЮЗ ЗАКЛЮЧЁН", "💍", "VI. Новая участница власти")
    ui.wrap(f"{spouse.get('name')} становится супругой правителя. Её мнение {spouse.get('opinion')}, доверие {spouse.get('trust')}, влияние {spouse.get('influence')}. Она будет самостоятельно оценивать политику и приглашать правителя на обсуждения.", "GREEN")
    _record(player, ctx, "Заключён династический брак", f"Римский дом соединён с домом {spouse.get('house')} державы {nation.get('name', key)}.", key, "good")
    ui.pause(); return True


def _action_options(action: str) -> tuple[str, str, str]:
    mapping = {
        "mediate_homeland": ("Поддержать посредничество", "Разрешить только тайные переговоры", "Отказать: война важнее брака"),
        "secure_trade": ("Дать полномочия на договор", "Разрешить ограниченную миссию", "Отказать в особых привилегиях"),
        "treasury_reform": ("Принять её план экономии", "Сократить лишь дворцовые расходы", "Отклонить вмешательство"),
        "grain_relief": ("Открыть большой продовольственный фонд", "Ограничиться адресной помощью", "Сохранить резерв армии"),
        "senate_network": ("Разрешить ей строить фракцию", "Дать лишь неформальные контакты", "Запретить вмешательство в Сенат"),
        "popular_patronage": ("Финансировать крупное благодеяние", "Провести скромную раздачу", "Отказаться от популизма"),
        "warn_plot": ("Довериться и начать чистку", "Проверить сведения тайно", "Не верить её агентам"),
        "military_advice": ("Принять её стратегию", "Передать совет полководцам", "Не допускать к военным делам"),
        "heir_question": ("Сделать наследование государственным приоритетом", "Не торопить судьбу", "Отложить вопрос на неопределённый срок"),
        "homeland_favor": ("Исполнить просьбу полностью", "Предложить компромисс", "Отказать родному дому"),
    }
    return mapping.get(action, ("Поддержать", "Искать компромисс", "Отказать"))


def _apply_spouse_choice(player: Any, spouse: dict, action: str, choice: str, ctx: dict) -> str:
    row = _dict(_dict(getattr(player, "diplomacy", {})).get(spouse.get("power")))
    strong = choice == "1"; compromise = choice == "2"
    if strong:
        spouse["opinion"] = _clamp(spouse["opinion"] + 7, 0, 100, 65); spouse["trust"] = _clamp(spouse["trust"] + 5, 0, 100, 60); spouse["influence"] = _clamp(spouse["influence"] + 4, 0, 100, 15)
    elif compromise:
        spouse["opinion"] = _clamp(spouse["opinion"] + 2, 0, 100, 65); spouse["trust"] = _clamp(spouse["trust"] + 1, 0, 100, 60)
    else:
        spouse["opinion"] = _clamp(spouse["opinion"] - 7, 0, 100, 65); spouse["trust"] = _clamp(spouse["trust"] - 5, 0, 100, 60); spouse["stress"] = _clamp(spouse["stress"] + 7, 0, 100, 10)
    effect = ""
    if action == "mediate_homeland":
        if strong:
            row["tension"] = _clamp(row.get("tension", 50) - 18, 0, 100, 50); row["trust"] = _clamp(row.get("trust", 40) + 8, 0, 100, 40); effect = "переговоры снизили напряжённость"
        elif compromise: row["tension"] = _clamp(row.get("tension", 50) - 7, 0, 100, 50); effect = "открыт тайный канал"
        else: row["tension"] = _clamp(row.get("tension", 50) + 5, 0, 100, 50); effect = "родной двор считает её униженной"
    elif action == "secure_trade":
        if strong:
            row["trade_pact"] = True; row["disposition"] = _clamp(row.get("disposition", 50) + 7, 0, 100, 50); effect = "открыты привилегированные рынки"
            trade = ctx.get("DIPLOMATIC_TRADE")
            if trade is not None and hasattr(trade, "propose_contract"):
                try: trade.propose_contract(player, spouse.get("power"), ctx, forced=True)
                except Exception: pass
        elif compromise: player.gold = _i(getattr(player, "gold", 0), 0) + 12; effect = "заключена малая купеческая сделка"
        else: row["disposition"] = _clamp(row.get("disposition", 50) - 4, 0, 100, 50); effect = "торговая миссия отменена"
    elif action == "treasury_reform":
        if strong: player.gold = _i(getattr(player, "gold", 0), 0) + 35; player.people_rep = _clamp(getattr(player, "people_rep", 50) - 2, 0, 100, 50); effect = "расходы резко сокращены"
        elif compromise: player.gold = _i(getattr(player, "gold", 0), 0) + 18; effect = "двор сократил излишества"
        else: effect = "реформа отклонена"
    elif action == "grain_relief":
        if strong and _i(getattr(player, "grain", 0), 0) >= 35:
            player.grain -= 35; player.people_rep = _clamp(getattr(player, "people_rep", 50) + 8, 0, 100, 50); player.unrest = _clamp(getattr(player, "unrest", 0) - 7, 0, 100, 0); effect = "проведена большая раздача зерна"
        elif compromise and _i(getattr(player, "grain", 0), 0) >= 15:
            player.grain -= 15; player.people_rep = _clamp(getattr(player, "people_rep", 50) + 3, 0, 100, 50); effect = "оказана адресная помощь"
        else: effect = "военный резерв сохранён"
    elif action == "senate_network":
        if strong: player.senate_rep = _clamp(getattr(player, "senate_rep", 50) + 7, 0, 100, 50); spouse["influence"] = _clamp(spouse["influence"] + 8, 0, 100, 15); effect = "супруга создала собственную сенатскую сеть"
        elif compromise: player.senate_rep = _clamp(getattr(player, "senate_rep", 50) + 3, 0, 100, 50); effect = "несколько родов привлечены на сторону дома"
        else: player.senate_rep = _clamp(getattr(player, "senate_rep", 50) - 1, 0, 100, 50); effect = "её политические связи ограничены"
    elif action == "popular_patronage":
        cost = 35 if strong else 15 if compromise else 0
        if cost and _i(getattr(player, "gold", 0), 0) >= cost:
            player.gold -= cost; player.people_rep = _clamp(getattr(player, "people_rep", 50) + (8 if strong else 3), 0, 100, 50); player.glory = _i(getattr(player, "glory", 0), 0) + (4 if strong else 1); effect = "народ увидел щедрость правящего дома"
        else: effect = "благодеяние не проведено"
    elif action == "warn_plot":
        factions = [f for f in _list(getattr(player, "ai_factions", [])) if not getattr(f, "defeated", False)]
        target = max(factions, key=lambda f: _i(getattr(f, "influence", 0), 0), default=None)
        if target:
            if strong: target.influence = max(0, _i(target.influence, 0) - 12); player.senate_rep = _clamp(getattr(player, "senate_rep", 50) - 2, 0, 100, 50); effect = f"сеть фракции «{target.name}» разгромлена"
            elif compromise: target.influence = max(0, _i(target.influence, 0) - 5); effect = f"за фракцией «{target.name}» установлено наблюдение"
            else: target.influence = min(100, _i(target.influence, 0) + 3); effect = "предупреждение проигнорировано"
        else: effect = "явной угрозы не обнаружено"
    elif action == "military_advice":
        if strong: player.morale = _clamp(getattr(player, "morale", 70) + 6, 0, 120, 70); effect = "армия получила новый оперативный план"
        elif compromise: player.morale = _clamp(getattr(player, "morale", 70) + 2, 0, 120, 70); effect = "совет передан штабам"
        else: effect = "военные дела остались закрыты для двора"
    elif action == "heir_question":
        if strong:
            chance = 0.45 + spouse["opinion"] / 500 + spouse["trust"] / 600
            if random.random() < chance:
                name = random.choice(["Marcus", "Lucius", "Gaius", "Julia", "Cornelia", "Aurelia"])
                heir = {"id": uuid.uuid4().hex[:10], "name": name, "born_turn": _i(getattr(player, "turn", 1), 1), "mother": spouse["name"], "house": spouse["house"], "legitimacy": _clamp(60 + spouse["influence"] // 2, 0, 100, 70)}
                ensure_state(player, ctx)["heirs"].append(heir); spouse["children"] += 1; effect = f"родился наследник: {name}"
            else: effect = "двор объявил наследование приоритетом, но рождения пока нет"
        elif compromise: effect = "вопрос оставлен частным делом супругов"
        else: effect = "вопрос наследования отложен"
    elif action == "homeland_favor":
        if strong:
            cost = min(45, max(15, _i(getattr(player, "gold", 0), 0) // 8)); player.gold = max(0, _i(getattr(player, "gold", 0), 0) - cost)
            row["disposition"] = _clamp(row.get("disposition", 50) + 10, 0, 100, 50); row["trust"] = _clamp(row.get("trust", 40) + 7, 0, 100, 40); effect = f"родному дому передано {cost} золота и знаки уважения"
        elif compromise: row["disposition"] = _clamp(row.get("disposition", 50) + 4, 0, 100, 50); effect = "достигнут ограниченный компромисс"
        else: row["disposition"] = _clamp(row.get("disposition", 50) - 7, 0, 100, 50); effect = "родной дом получил отказ"
    raised = _develop_after_decision(spouse, action, choice, effect, _i(getattr(player, "turn", 1), 1))
    _refresh_hidden_state(player, spouse, ctx)
    if raised:
        effect += "; выросли способности: " + ", ".join(raised)
    return effect


def _education_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    state = ensure_state(player, ctx); spouse = state.get("spouse")
    if not spouse: return True
    focus = str(_dict(event.get("payload")).get("focus", "philosophy"))
    data = EDUCATION_FOCI.get(focus, EDUCATION_FOCI["philosophy"])
    ui.screen(); ui.header(f"УЧЁНОЕ НАМЕРЕНИЕ: {spouse.get('name')}", "📚", "I. Просьба супруги")
    ui.wrap(data["summary"])
    ui.info(f"Нынешний интеллект {spouse['intellect']}; мудрость {spouse['wisdom']}; образование {spouse['education']}; политический опыт {spouse['political_experience']}.", "PURPLE")
    ui.pause("Выслушать программу обучения...")

    ui.screen(); ui.header(data["name"].upper(), "🏛", "II. Программа и политический смысл")
    ui.wrap("Супруга подчёркивает, что знания нужны ей не ради украшения двора: она намерена проверять решения, обучать наследников и говорить с правителем на равных.", "CYAN")
    ui.wrap("Полное покровительство ускорит развитие, но одновременно укрепит её авторитет и привычку правителя принимать её планы без возражений.", "GRAY")
    ui.pause("Перейти к решению...")

    ui.screen(); ui.header("РЕШЕНИЕ О ШКОЛЕ", "🪶", "III. Цена доверия")
    print("  1. Исполнить её замысел без оговорок — 45 золота")
    print("  2. Разрешить малый кружок учёных — 18 золота")
    print("  3. Отказать: двор не нуждается в новой школе")
    print("  P. Отложить")
    ch = ui.choice("\n  Ответ: ", ["1", "2", "3", "P"])
    if ch == "P": return False

    turn = _i(getattr(player, "turn", 1), 1)
    if ch == "1" and _i(getattr(player, "gold", 0), 0) >= 45:
        player.gold -= 45
        spouse["education"] = _clamp(spouse.get("education", 0) + 9, 0, 100, 0)
        spouse["wisdom"] = _clamp(spouse.get("wisdom", 45) + 3, 0, 100, 45)
        spouse["political_experience"] = _i(spouse.get("political_experience", 0), 0) + 6
        spouse["trust"] = _clamp(spouse.get("trust", 60) + 5, 0, 100, 60)
        spouse["influence"] = _clamp(spouse.get("influence", 15) + 4, 0, 100, 15)
        _register_obedience(spouse, "1")
        raised = _grant_learning(spouse, data["skills"], 1.55)
        effect = "замысел принят целиком; при дворе создана полноценная школа"
    elif ch in {"1", "2"} and _i(getattr(player, "gold", 0), 0) >= 18:
        player.gold -= 18
        spouse["education"] = _clamp(spouse.get("education", 0) + 4, 0, 100, 0)
        spouse["wisdom"] = _clamp(spouse.get("wisdom", 45) + 1, 0, 100, 45)
        spouse["political_experience"] = _i(spouse.get("political_experience", 0), 0) + 3
        spouse["trust"] = _clamp(spouse.get("trust", 60) + 1, 0, 100, 60)
        _register_obedience(spouse, "2")
        raised = _grant_learning(spouse, data["skills"], 0.8)
        effect = "разрешён ограниченный кружок наставников"
    else:
        spouse["trust"] = _clamp(spouse.get("trust", 60) - 5, 0, 100, 60)
        spouse["opinion"] = _clamp(spouse.get("opinion", 65) - 4, 0, 100, 65)
        spouse["stress"] = _clamp(spouse.get("stress", 10) + 5, 0, 100, 10)
        _register_obedience(spouse, "3")
        raised = []
        effect = "программа отвергнута; супруга продолжит учиться без государственной поддержки"
    spouse["relationship_stage"] = _relationship_stage(spouse)
    spouse.setdefault("development_history", []).append({"turn": turn, "source": f"education:{focus}", "choice": ch, "raised": raised})
    spouse["development_history"] = spouse["development_history"][-50:]
    _spouse_memory(spouse, turn, f"education:{focus}", ch, effect)
    _refresh_hidden_state(player, spouse, ctx)
    _record(player, ctx, f"Образование супруги: {data['name']}", effect, spouse.get("power"), "good" if ch == "1" else "bad" if ch == "3" else "info")
    ui.screen(); ui.header("ПОСЛЕ РЕШЕНИЯ", "🧠", "IV. Изменение личности")
    ui.wrap(effect + (". Выросли: " + ", ".join(raised) if raised else "."), "GREEN" if ch != "3" else "RED")
    ui.info(f"Интеллект {spouse['intellect']}; мудрость {spouse['wisdom']}; образование {spouse['education']}; опыт {spouse['political_experience']}.", "PURPLE")
    ui.pause(); return True


def _ascendancy_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    spouse = ensure_state(player, ctx).get("spouse")
    if not spouse: return True
    tier = str(_dict(event.get("payload")).get("new", spouse.get("hidden_tier", "none")))
    ui.screen(); ui.header("НЕЗРИМАЯ ВЛАСТЬ", "👁", "I. Наблюдения двора")
    ui.wrap("Сенаторы, послы и слуги замечают: правитель всё чаще принимает предложения супруги без возражений, а её советы удивительно точно предвосхищают кризисы.")
    ui.pause("Выслушать голоса при дворе...")
    ui.screen(); ui.header("ДВА ГОЛОСА — ОДНА ВОЛЯ", "👑", "II. Новое устройство власти")
    if tier == "subtle_guidance":
        ui.wrap("Её влияние ещё не оформлено должностью. Оно проявляется в своевременных письмах, удачных назначениях и решениях, чьи настоящие истоки известны лишь супругам.", "CYAN")
    elif tier == "consilium_reginae":
        ui.wrap("Сложился негласный Consilium Reginae — совет супруги. Она не подписывает постановлений, но её предварительное суждение уже меняет их содержание.", "CYAN")
    elif tier == "concordia_domus":
        ui.wrap("Правящий дом действует с редким согласованием. Двор больше не различает, где заканчивается замысел правителя и начинается мысль супруги.", "CYAN")
    else:
        ui.wrap("Возникло Imperium Duplex — двуединая власть. Формально правит один человек, но государственная воля рождается в постоянном союзе двух умов.", "CYAN")
    ui.wrap("Точные последствия остаются скрыты: они проявятся не отдельным указом, а цепью малых преимуществ в управлении, дипломатии и предотвращении кризисов.", "GRAY")
    _record(player, ctx, "Укрепилось незримое влияние супруги", HIDDEN_TIER_LABELS.get(tier, tier), spouse.get("power"), "good")
    ui.pause(); return True


def _spouse_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    state = ensure_state(player, ctx); spouse = state.get("spouse")
    if not spouse: return True
    action = str(event.get("payload", {}).get("action", "homeland_favor")); reason = str(event.get("payload", {}).get("reason", ""))
    nation = _nation(ctx, spouse.get("power"))
    ui.screen(); ui.header(f"АУДИЕНЦИЯ: {spouse.get('name')}", "🕯", "I. Личный разговор без свидетелей")
    ui.wrap(f"Супруга просит обсудить {ACTION_LABELS.get(action, action)}. Она объясняет: {reason}.")
    ui.info(f"Её мнение {spouse['opinion']}; доверие {spouse['trust']}; влияние {spouse['influence']}; стресс {spouse['stress']}; верность родине {spouse['homeland_loyalty']}.", "PURPLE")
    ui.pause("Выслушать её доводы полностью...")

    ui.screen(); ui.header("ЕЁ АРГУМЕНТ", "💬", "II. Собственная позиция супруги")
    arguments = {
        "mediate_homeland": f"«Я не прошу тебя забыть интересы Рима. Я прошу позволить мне доказать державе {nation.get('name', spouse.get('power'))}, что мир не равен слабости». ",
        "secure_trade": "«Когда два народа ежедневно зависят от одного договора, война становится дороже для обеих сторон». ",
        "treasury_reform": "«Казна гибнет не от одного великого расхода, а от тысячи расходов, которых никто не решается назвать лишними». ",
        "grain_relief": "«Голодный гражданин не различает законного правителя и тирана; он различает только того, кто дал ему хлеб». ",
        "senate_network": "«Сенат не единое тело. Это сеть домов, долгов и страхов. Её можно понять и направить». ",
        "popular_patronage": "«Власть должна иногда быть видимой как милость, а не только как приказ». ",
        "warn_plot": "«Я не обвиняю без доказательств. Но люди, которые считают меня чужеземкой, говорят при моих слугах слишком свободно». ",
        "military_advice": "«Ваши легаты знают римскую войну. Я предлагаю подумать, как мыслит тот, кто не обязан сражаться по-римски». ",
        "heir_question": "«Наш союз существует в настоящем. Наследник превратит его в будущее, с которым придётся считаться всем домам». ",
        "homeland_favor": "«Я стала частью Рима, но не перестала быть дочерью своего дома. Не заставляй меня выбирать там, где возможен компромисс». ",
    }
    ui.wrap(arguments.get(action, "«Я прошу рассмотреть это не как прихоть, а как часть нашей общей власти»."), "CYAN")
    ui.pause("Перейти к государственному решению...")

    opts = _action_options(action)
    ui.screen(); ui.header("РЕШЕНИЕ ПРАВИТЕЛЯ", "🏛", "III. Ответ и последствия")
    print(f"  1. {opts[0]}")
    print(f"  2. {opts[1]}")
    print(f"  3. {opts[2]}")
    print("  P. Отложить разговор")
    ch = ui.choice("\n  Ответ: ", ["1", "2", "3", "P"])
    if ch == "P": return False
    effect = _apply_spouse_choice(player, spouse, action, ch, ctx)
    _spouse_memory(spouse, _i(getattr(player, "turn", 1), 1), action, ch, effect)
    ui.screen(); ui.header("ПОСЛЕ РАЗГОВОРА", "🌙", "IV. Изменение отношений")
    ui.wrap(f"Итог: {effect}. Мнение супруги: {spouse['opinion']}; доверие: {spouse['trust']}; влияние: {spouse['influence']}.", "GREEN" if ch != "3" else "RED")
    _record(player, ctx, f"Совет супруги: {ACTION_LABELS.get(action, action)}", effect, spouse.get("power"), "good" if ch == "1" else "bad" if ch == "3" else "info")
    ui.pause(); return True


def handle_council_event(player: Any, event: dict, ctx: dict, ui: Any) -> bool:
    etype = str(event.get("type", ""))
    if etype == "marriage.offer": return _marriage_event(player, event, ctx, ui)
    if etype == "spouse.council": return _spouse_event(player, event, ctx, ui)
    if etype == "spouse.education": return _education_event(player, event, ctx, ui)
    if etype == "spouse.ascendancy": return _ascendancy_event(player, event, ctx, ui)
    return True


def expire_council_event(player: Any, event: dict, ctx: dict) -> None:
    key = str(event.get("power") or ""); row = _dict(_dict(getattr(player, "diplomacy", {})).get(key))
    if event.get("type") == "marriage.offer":
        row["disposition"] = _clamp(row.get("disposition", 50) - 7, 0, 100, 50); row["trust"] = _clamp(row.get("trust", 40) - 5, 0, 100, 40)
        _record(player, ctx, "Брачное посольство оставлено без ответа", "Иностранный царский дом счёл молчание демонстративным унижением.", key, "bad")
    elif event.get("type") in {"spouse.council", "spouse.education"}:
        spouse = ensure_state(player, ctx).get("spouse")
        if spouse:
            spouse["opinion"] = _clamp(spouse["opinion"] - 4, 0, 100, 65); spouse["trust"] = _clamp(spouse["trust"] - 3, 0, 100, 60)
            spouse["obedience_streak"] = 0
            spouse["obedience_score"] = _clamp(spouse.get("obedience_score", 0) - 5, 0, 100, 0)
            spouse["relationship_stage"] = _relationship_stage(spouse)
            _refresh_hidden_state(player, spouse, ctx)


def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx); ui = UI(ctx); state = ensure_state(player, ctx)
    while True:
        ui.screen(); ui.header("DOMUS ET CONIUGIA", "👑", f"Династии и интеллектуальный ИИ супруги — {MODULE_VERSION}")
        spouse = state.get("spouse")
        if spouse:
            ui.table("Супруга", ["Параметр", "Значение"], [
                ("Имя", spouse["name"]), ("Дом и родина", f"{spouse['house']} / {_nation(ctx, spouse['power']).get('name', spouse['power'])}"),
                ("Черты", ", ".join(spouse["traits"])), ("Мнение / доверие / влияние", f"{spouse['opinion']} / {spouse['trust']} / {spouse['influence']}"),
                ("Интеллект / мудрость / образование", f"{spouse['intellect']} / {spouse['wisdom']} / {spouse['education']}"),
                ("Дипломатия / интрига / управление", f"{spouse['diplomacy']} / {spouse['intrigue']} / {spouse['stewardship']}"),
                ("Амбиция / сострадание / опыт", f"{spouse['ambition']} / {spouse['compassion']} / {spouse['political_experience']}"),
                ("Верность родине / стресс", f"{spouse['homeland_loyalty']} / {spouse['stress']}"),
                ("Стадия отношений", RELATIONSHIP_STAGES.get(spouse.get('relationship_stage', 0), 'политический брак')),
                ("Безоговорочно принятые советы", f"{spouse['advice_followed']} (серия {spouse['obedience_streak']})"),
                ("Незримое влияние", HIDDEN_TIER_LABELS.get(spouse.get('hidden_tier', 'none'), 'неразличимое влияние')),
                ("Повестка", spouse['agenda']), ("Дети", spouse['children']),
            ], "PURPLE")
        else: ui.info("Правящий дом не связан династическим браком.", "GRAY")
        if state["heirs"]:
            ui.table("Наследники", ["Имя", "Родился", "Мать", "Легитимность"], [(h.get("name"), h.get("born_turn"), h.get("mother"), h.get("legitimacy")) for h in state["heirs"]], "GOLD")
        ui.section("Действия", "GOLD")
        print("  1. Направить брачное посольство" if not spouse else "  1. Просмотреть память и последние решения супруги")
        print("  2. Архив династии")
        print("  Q. Назад")
        ch = ui.choice("\n  Выбор: ", ["1", "2", "Q"])
        if ch == "Q": return
        if ch == "1" and not spouse:
            keys = [k for k in CANDIDATES if not _dict(_dict(getattr(player, "diplomacy", {})).get(k)).get("at_war")]
            ui.screen(); ui.header("БРАЧНОЕ ПОСОЛЬСТВО", "💍")
            for i, key in enumerate(keys, 1): print(f"  {i}. {_nation(ctx, key).get('name', key)}")
            s = ui.choice("\n  Держава (или Q): ", [str(i) for i in range(1, len(keys) + 1)] + ["Q"])
            if s != "Q":
                key = keys[int(s) - 1]
                if request_marriage(player, key, ctx, forced=True): ui.info("Посольство отправлено. Дело будет рассмотрено в Consilium Orbis.", "GREEN")
                else: ui.info("Сейчас брачные переговоры невозможны или уже ведутся.", "RED")
                ui.pause()
        elif ch == "1" and spouse:
            ui.screen(); ui.header("ПАМЯТЬ СУПРУГИ", "🧠")
            memories = spouse.get("memories", [])[-25:]
            if memories: ui.table("Решения, которые она помнит", ["Ход", "Тема", "Ответ", "Последствие"], [(m.get("turn"), ACTION_LABELS.get(m.get("topic"), m.get("topic")), m.get("choice"), m.get("effect")) for m in reversed(memories)], "CYAN")
            else: ui.info("Совместных политических решений пока не было.", "GRAY")
            ui.pause()
        elif ch == "2":
            ui.screen(); ui.header("ХРОНИКА ДОМА", "📜")
            if state["history"]: ui.table("События", ["Ход", "Событие", "Содержание"], [(h.get("turn"), h.get("title"), h.get("text")) for h in reversed(state["history"][-45:])], "CYAN")
            else: ui.info("Архив пуст.", "GRAY")
            ui.pause()
