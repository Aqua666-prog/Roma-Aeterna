#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roma Aeterna — CONSILIUM ORBIS.

Единая очередь важных международных событий после хода. Механика нужна для
того, чтобы игрок не искал критические предложения по меню: войны, торговые
договоры, браки, ультиматумы и разговоры с супругой сами появляются в
послеходовом совете и разворачиваются в несколько этапов обсуждения.

Публичный контракт:
    ensure_state(player, ctx=None)
    enqueue(player, event_type, title, summary, payload=None, ...)
    has_pending(player, event_type=None, power=None)
    process_pending(player, ctx=None, interactive=True)
    open_menu(player, ctx=None)
"""
from __future__ import annotations

import re
import textwrap
import uuid
from typing import Any

MODULE_VERSION = "3.0.0-consilium-orbis"
SCHEMA_VERSION = 1
MAX_QUEUE = 40
MAX_HISTORY = 240


def _i(value: Any, default: int = 0, low: int | None = None, high: int | None = None) -> int:
    try:
        value = int(round(float(value)))
    except (TypeError, ValueError, OverflowError):
        value = default
    if low is not None: value = max(low, value)
    if high is not None: value = min(high, value)
    return value


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
                if bold: code = getattr(self.C, "BOLD", "") + code
                return fn(str(text), code)
            except Exception: pass
        return str(text)

    def screen(self) -> None:
        fn = self.ctx.get("rui_screen_start") or self.ctx.get("clear")
        if callable(fn):
            try: fn(); return
            except Exception: pass

    def header(self, title: str, icon: str = "🏛", subtitle: str = "") -> None:
        fn = self.ctx.get("rui_header")
        if callable(fn) and self.C is not None:
            try: fn(title, icon, getattr(self.C, "GOLD", ""), subtitle); return
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
            clean = [_plain(v) for v in row]; clean_rows.append(clean)
            for i, value in enumerate(clean[:len(widths)]): widths[i] = min(34, max(widths[i], len(value)))
        print("  " + " | ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)))
        print("  " + "-+-".join("-" * w for w in widths))
        for row in clean_rows:
            print("  " + " | ".join(row[i][:widths[i]].ljust(widths[i]) for i in range(len(headers))))

    def choice(self, prompt: str, valid: list[str]) -> str:
        valid = [str(v).upper() for v in valid]
        fn = self.ctx.get("read_choice")
        if callable(fn):
            try: return str(fn(self.color(prompt, "CYAN"), valid)).upper()
            except Exception: pass
        while True:
            value = input(prompt).strip().upper()
            if value in valid: return value
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


def ensure_state(player: Any, ctx: dict | None = None) -> dict:
    state = getattr(player, "world_council", None)
    if not isinstance(state, dict):
        state = {}; player.world_council = state
    state.setdefault("schema", SCHEMA_VERSION)
    state.setdefault("version", MODULE_VERSION)
    state.setdefault("queue", [])
    state.setdefault("history", [])
    state.setdefault("last_processed_turn", 0)
    state.setdefault("settings", {})
    state["settings"].setdefault("max_events_after_turn", 8)
    state["settings"].setdefault("auto_open", True)
    queue = []
    for event in _list(state.get("queue")):
        if not isinstance(event, dict): continue
        event.setdefault("id", uuid.uuid4().hex[:12])
        event.setdefault("type", "generic.notice")
        event.setdefault("title", "Совет держав")
        event.setdefault("summary", "Получено новое донесение.")
        event.setdefault("payload", {})
        event.setdefault("power", None)
        event.setdefault("severity", 2)
        event.setdefault("created_turn", _i(getattr(player, "turn", 1), 1))
        event.setdefault("expires_turn", event["created_turn"] + 8)
        event.setdefault("status", "pending")
        event.setdefault("dedupe", "")
        event["severity"] = _i(event.get("severity", 2), 2, 1, 5)
        event["created_turn"] = _i(event.get("created_turn", 1), 1, 1)
        event["expires_turn"] = _i(event.get("expires_turn", event["created_turn"] + 8), event["created_turn"] + 8, event["created_turn"])
        event["payload"] = _dict(event.get("payload"))
        if event.get("status") == "pending": queue.append(event)
    state["queue"] = queue[-MAX_QUEUE:]
    state["history"] = [x for x in _list(state.get("history")) if isinstance(x, dict)][-MAX_HISTORY:]
    state["last_processed_turn"] = _i(state.get("last_processed_turn", 0), 0, 0)
    state["schema"] = SCHEMA_VERSION; state["version"] = MODULE_VERSION
    player.world_council = state
    return state


def enqueue(
    player: Any,
    event_type: str,
    title: str,
    summary: str,
    payload: dict | None = None,
    *,
    power: str | None = None,
    severity: int = 3,
    expires_in: int = 8,
    dedupe: str | None = None,
    ctx: dict | None = None,
) -> dict | None:
    state = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 1), 1, 1)
    dedupe_key = str(dedupe or f"{event_type}:{power or ''}:{turn}")
    for event in state["queue"]:
        if event.get("status") == "pending" and event.get("dedupe") == dedupe_key:
            return None
    event = {
        "id": uuid.uuid4().hex[:12], "type": str(event_type), "title": str(title), "summary": str(summary),
        "payload": dict(payload or {}), "power": power, "severity": _i(severity, 3, 1, 5),
        "created_turn": turn, "expires_turn": turn + max(1, _i(expires_in, 8, 1, 99)),
        "status": "pending", "dedupe": dedupe_key,
    }
    state["queue"].append(event); state["queue"] = state["queue"][-MAX_QUEUE:]
    return event


def has_pending(player: Any, event_type: str | None = None, power: str | None = None) -> bool:
    state = ensure_state(player)
    for event in state["queue"]:
        if event.get("status") != "pending": continue
        if event_type and event.get("type") != event_type: continue
        if power and event.get("power") != power: continue
        return True
    return False


def _route_module(ctx: dict, event_type: str) -> Any:
    prefix = event_type.split(".", 1)[0]
    return {
        "war": ctx.get("WARFARE_AI"),
        "battle": ctx.get("WAR_DIRECTOR_3"),
        "campaign": ctx.get("WAR_DIRECTOR_3"),
        "trade": ctx.get("DIPLOMATIC_TRADE"),
        "marriage": ctx.get("DYNASTIES"),
        "spouse": ctx.get("DYNASTIES"),
        "dynasty": ctx.get("DYNASTIES"),
    }.get(prefix)


def _generic_event(ui: UI, player: Any, event: dict, ctx: dict) -> bool:
    ui.screen(); ui.header(event.get("title", "CONSILIUM ORBIS"), "📨", "Срочное международное донесение")
    ui.section("I. Донесение", "CYAN"); ui.wrap(event.get("summary", ""), "WHITE")
    ui.section("II. Обсуждение", "GOLD"); ui.wrap("Совет выслушал послов, военных и казначеев. Решение не требует отдельной механики, но занесено в государственный архив.", "GRAY")
    ui.pause()
    return True


def _archive(player: Any, event: dict, result: str) -> None:
    state = ensure_state(player)
    archived = dict(event); archived["status"] = result; archived["resolved_turn"] = _i(getattr(player, "turn", 1), 1)
    state["history"].append(archived); state["history"] = state["history"][-MAX_HISTORY:]


def process_pending(player: Any, ctx: dict | None = None, interactive: bool = True) -> dict:
    ctx = _ctx(ctx); state = ensure_state(player, ctx)
    turn = _i(getattr(player, "turn", 1), 1)
    # Истёкшие посольства не исчезают бесследно: они считаются молчаливым отказом.
    survivors = []
    for event in state["queue"]:
        if event.get("expires_turn", turn + 1) < turn:
            _archive(player, event, "expired")
            module = _route_module(ctx, str(event.get("type", "")))
            if module is not None and hasattr(module, "expire_council_event"):
                try: module.expire_council_event(player, event, ctx)
                except Exception: pass
        else:
            survivors.append(event)
    state["queue"] = survivors
    if not interactive or not state["settings"].get("auto_open", True): return state
    pending = sorted(state["queue"], key=lambda e: (-_i(e.get("severity", 2), 2), _i(e.get("created_turn", 1), 1)))
    if not pending: return state
    ui = UI(ctx)
    ui.screen(); ui.header("CONSILIUM ORBIS", "🏛", "Послы, полководцы и царские дома ожидают решения после завершения года")
    ui.info(f"Неотложных дел: {len(pending)}. Каждое важное дело будет рассмотрено по этапам.", "CYAN")
    ui.pause("Открыть заседание...")
    limit = _i(state["settings"].get("max_events_after_turn", 8), 8, 1, 20)
    processed = 0
    for event in list(pending):
        if processed >= limit: break
        if event not in state["queue"]: continue
        module = _route_module(ctx, str(event.get("type", "")))
        resolved = True
        try:
            if module is not None and hasattr(module, "handle_council_event"):
                resolved = bool(module.handle_council_event(player, event, ctx, ui))
            else:
                resolved = _generic_event(ui, player, event, ctx)
        except (EOFError, KeyboardInterrupt):
            resolved = False
        except Exception as exc:
            debug = ctx.get("debug_log")
            if callable(debug):
                try: debug("Consilium event failed (%s): %s", event.get("type"), exc, exc_info=True)
                except Exception: pass
            ui.info(f"Заседание прервано из-за внутренней ошибки: {type(exc).__name__}: {exc}", "RED")
            ui.pause(); resolved = False
        if resolved:
            state["queue"].remove(event); _archive(player, event, "resolved")
        else:
            event["postponed_turn"] = turn
        processed += 1
    state["last_processed_turn"] = turn
    return state


def open_menu(player: Any, ctx: dict | None = None) -> None:
    ctx = _ctx(ctx); ui = UI(ctx); state = ensure_state(player, ctx)
    while True:
        ui.screen(); ui.header("CONSILIUM ORBIS", "🏛", f"Международные механики и послеходовые обсуждения — {MODULE_VERSION}")
        queue = state.get("queue", [])
        if queue:
            ui.table("Ожидают решения", ["Важн.", "Тип", "Держава", "Дело", "До хода"], [
                (e.get("severity"), e.get("type"), e.get("power") or "—", e.get("title"), e.get("expires_turn")) for e in queue
            ], "RED")
        else:
            ui.info("Неотложных дел нет.", "GRAY")
        ui.section("Разделы", "GOLD")
        print("  1. Рассмотреть ожидающие дела сейчас")
        print("  2. Державы и их уникальные армии")
        print("  3. Прямые войны и кампании")
        print("  4. Международная торговля")
        print("  5. Династии, брак и супруга")
        print("  6. Архив решений")
        print("  7. Оперативные армии Рима")
        print("  8. Экономика, наука и религия держав ИИ")
        print("  9. Bellum Universale: активные кампании и блокады")
        print("  Q. Назад")
        ch = ui.choice("\n  Выбор: ", ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Q"])
        if ch == "Q": return
        if ch == "1": process_pending(player, ctx, interactive=True)
        elif ch == "2":
            module = ctx.get("NATIONS")
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
        elif ch == "3":
            module = ctx.get("WARFARE_AI")
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
        elif ch == "4":
            module = ctx.get("DIPLOMATIC_TRADE")
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
        elif ch == "5":
            module = ctx.get("DYNASTIES")
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
        elif ch == "7":
            module = ctx.get("ARMY_GROUPS")
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
        elif ch == "8":
            module = ctx.get("AI_CIVILIZATION")
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
        elif ch == "9":
            module = ctx.get("WAR_DIRECTOR_3")
            if module is not None and hasattr(module, "open_menu"): module.open_menu(player, ctx)
        elif ch == "6":
            ui.screen(); ui.header("ACTA CONSILII", "📜")
            history = state.get("history", [])[-50:]
            if history:
                ui.table("Последние решения", ["Ход", "Статус", "Тип", "Дело", "Держава"], [
                    (e.get("resolved_turn", e.get("created_turn")), e.get("status"), e.get("type"), e.get("title"), e.get("power") or "—") for e in reversed(history)
                ], "CYAN")
            else: ui.info("Архив пока пуст.", "GRAY")
            ui.pause()
