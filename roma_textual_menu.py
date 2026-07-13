# -*- coding: utf-8 -*-
"""
roma_textual_menu.py — полноэкранное главное меню Roma Aeterna на Textual.

Назначение
==========
Отдельный, самодостаточный слой Textual, который рисует главное меню в стиле
скриншота (тёмный фон, золотой заголовок, пурпурно-малиновый подзаголовок,
золотая рамка статуса, крупные кнопки-карточки, сгруппированные по разделам).

Модуль НИЧЕГО не знает о внутренностях игры сверх маленького контракта:

    • объект player с атрибутами/методами:
        .gold .grain .glory .year .turn .faith .religion .difficulty
        .provinces .legions .tech_researched .ai_factions
        .income() -> (gold, grain)      # чистый приход/расход считается снаружи
        .upkeep() -> (gold, grain)
      (все они уже есть в основном файле игры)

    • набор helper'ов, которые передаются в run_textual_menu(...) как ctx —
      это позволяет не тянуть импортом весь 25k-строчный файл и тестировать
      меню изолированно. Если ctx не передан, модуль пытается взять функции
      из глобального пространства вызывающего модуля.

Ключи, которые возвращает меню, ПОЛНОСТЬЮ совпадают с ключами разделов
main_menu(), поэтому textual-меню — drop-in замена: оно возвращает ту же
строку-приказ ("1", "2", "4", "P", "D", ... "Q"), что и классическое меню.

Безопасность запуска
====================
    • Если textual не установлен (частый случай на Pydroid) — TEXTUAL_AVAILABLE
      = False, а run_textual_menu() вернёт None. Вызывающий код должен в этом
      случае откатиться на Rich/ANSI-меню.
    • Любое исключение внутри Textual перехватывается и логируется, меню
      возвращает None (безопасный откат), а не роняет партию.
"""

from __future__ import annotations

import os
import logging

log = logging.getLogger("roma.textual_menu")

# Зафиксированный дизайн со скриншота: алый фон, золотые рамки и кнопки.
DESIGN_ID = "imperial-crimson-gold-v4-economica"

# ─── Мягкий импорт Textual ─────────────────────────────────────────────────
try:
    from textual.app import App, ComposeResult
    from textual.containers import Vertical, VerticalScroll
    from textual.widgets import Static, Button, Footer
    TEXTUAL_AVAILABLE = True
except Exception as _e:  # ImportError и всё, что Pydroid может подкинуть
    log.info("Textual недоступен: %s", _e)
    TEXTUAL_AVAILABLE = False


# ─── Палитра (совпадает со скриншотом v2.24.x) ─────────────────────────────
GOLD      = "#f6d365"   # заголовок, рамка статуса, акцент «Кампания»
CRIMSON   = "#ff5c8a"   # подзаголовок SENATUS • LEGIONES • ...
PARCHMENT = "#f4e8b8"   # основной текст
BLUE      = "#7aa2f7"   # рамки карточек-разделов
CYAN      = "#7dcfff"   # заголовки разделов
GREEN     = "#98c379"
PURPLE    = "#c792ea"
GREY      = "#9aa0aa"
BG        = "#3b0008"

# Соответствие «цвет раздела из игры → цвет заголовка карточки в Textual».
# Ключи — это строки, которые лежат в MenuSection.color (C.RED и т.п.). Мы не
# импортируем C, поэтому маппим по названию раздела ниже, а это — запасной путь.
_SECTION_TITLE_COLORS = {
    "Кампания": GOLD,
    "Государство": GOLD,
    "Экономика": GREEN,
    "Развитие и события": CYAN,
    "Развитие": CYAN,
    "Система": PURPLE,
}


# ─── Утилиты, не зависящие от Textual (тестируются напрямую) ────────────────
def safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _terminal_columns(default: int = 80) -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return default


def build_dashboard_text(player, ctx: dict) -> str:
    """Собирает многострочный статус игрока для золотой рамки.

    ctx содержит функции/словари игры. Всё обёрнуто в getattr/get с дефолтами,
    поэтому даже неполный player не роняет рендер (важно для тестов и раннего
    запуска до полной инициализации состояния).
    """
    status_fn      = ctx.get("player_status_display", lambda p: getattr(p, "name", "Рим"))
    get_era        = ctx.get("get_era", lambda p: {"name": "—"})
    difficulty_map = ctx.get("DIFFICULTY_PRESETS", {})
    religion_map   = ctx.get("RELIGION_CHOICES", {})
    provinces_data = ctx.get("PROVINCES_DATA", [])
    tech_tree      = ctx.get("TECH_TREE", {})
    game_version   = ctx.get("GAME_VERSION", "?")

    # Приход/расход. income()/upkeep() возвращают (gold, grain).
    try:
        gi, gri = player.income()
        gc, grc = player.upkeep()
    except Exception as e:  # на всякий случай — не валим меню
        log.warning("income/upkeep недоступны: %s", e)
        gi = gri = gc = grc = 0
    net_gold  = safe_int(gi) - safe_int(gc)
    net_grain = safe_int(gri) - safe_int(grc)

    era = get_era(player) or {}
    era_name = era.get("name", "—") if isinstance(era, dict) else "—"

    diff_key = getattr(player, "difficulty", "normal")
    diff_entry = difficulty_map.get(diff_key) or difficulty_map.get("normal") or {}
    diff_label = diff_entry.get("label", str(diff_key))

    religion = getattr(player, "religion", None)
    if religion and religion in religion_map:
        rel_name = religion_map[religion].get("name", "выбрана")
    else:
        rel_name = "не выбрана"

    # Крупнейшая угроза среди непобеждённых фракций ИИ.
    factions = [f for f in getattr(player, "ai_factions", []) if not getattr(f, "defeated", False)]
    if factions:
        threat = max(factions, key=lambda f: getattr(f, "influence", 0))
        threat_text = f"{getattr(threat, 'name', 'враг')}: {getattr(threat, 'influence', 0)}"
    else:
        threat_text = "нет серьёзной угрозы"

    n_prov  = len(getattr(player, "provinces", []))
    n_all   = len(provinces_data) if provinces_data else n_prov
    n_leg   = len(getattr(player, "legions", []))
    n_tech  = len(getattr(player, "tech_researched", []))
    n_all_t = len(tech_tree) if tech_tree else n_tech

    consuls = status_fn(player)
    gold    = getattr(player, "gold", 0)
    grain   = getattr(player, "grain", 0)
    glory   = getattr(player, "glory", 0)
    faith   = getattr(player, "faith", 0)
    year    = getattr(player, "year", 0)
    turn    = getattr(player, "turn", 0)

    foreign_state = getattr(player, "foreign_policy", {}) if isinstance(getattr(player, "foreign_policy", {}), dict) else {}
    doctrine_map = ctx.get("FOREIGN_POLICY_DOCTRINES", {})
    doctrine_key = str(foreign_state.get("doctrine", "balance"))
    doctrine_name = doctrine_map.get(doctrine_key, {}).get("name", doctrine_key)
    diplomatic_capital = safe_int(foreign_state.get("capital", 0), 0)
    diplomatic_capital_max = safe_int(foreign_state.get("capital_max", 0), 0)
    global_tension = safe_int(foreign_state.get("global_tension", 0), 0)
    active_missions = len(foreign_state.get("active_missions", []) or [])

    annals_state = getattr(player, "annals_state", {})
    if not isinstance(annals_state, dict):
        annals_state = {}
    annals_history = annals_state.get("history", [])
    if not isinstance(annals_history, list):
        annals_history = []
    annals_pending = annals_state.get("pending", [])
    if not isinstance(annals_pending, list):
        annals_pending = []
    annals_current = annals_state.get("current", [])
    if not isinstance(annals_current, list):
        annals_current = []
    annals_open_events = len(annals_pending) + (len(annals_current) if annals_state.get("active") else 0)

    economy = getattr(player, "economy", {})
    if not isinstance(economy, dict):
        economy = {}
    inflation = float(economy.get("inflation", 0.0) or 0.0)
    debt = safe_int(economy.get("debt", 0), 0)
    confidence = float(economy.get("confidence", 0.0) or 0.0)
    financial = economy.get("financial", {}) if isinstance(economy.get("financial", {}), dict) else {}
    banking_health = float(financial.get("banking_health", 0.0) or 0.0)
    trade = economy.get("trade", {}) if isinstance(economy.get("trade", {}), dict) else {}
    trade_balance = float(trade.get("trade_balance", 0.0) or 0.0)

    return (
        f"{consuls}  •  {year} AUC  •  Ход {turn}  •  {era_name}  •  {diff_label}\n"
        f"💰 Казна {gold} ({net_gold:+}/ход)   🌾 Зерно {grain} ({net_grain:+}/ход)   🏆 Слава {glory}\n"
        f"🗺 Провинции {n_prov}/{n_all}   ⚔ Легионы {n_leg}   🔬 Технологии {n_tech}/{n_all_t}\n"
        f"🕯 Религия: {rel_name}   ✨ Вера: {faith}   ☠ Угроза: {threat_text}\n"
        f"🌍 {doctrine_name}   📜 ДК {diplomatic_capital}/{diplomatic_capital_max}   🕊 Миссии {active_missions}   ⚠ Напряжённость {global_tension}/100\n"
        f"📈 Инфляция {inflation:+.1%}   📜 Долг {debt}   🏦 Банки {banking_health:.0%}   ⚓ Торг. баланс {trade_balance:+.0f}   🤝 Доверие {confidence:.0%}\n"
        f"📜 Летопись: {len(annals_history)} завершённых ходов   ✍ Текущих записей: {annals_open_events}"
    )


def sections_to_plain(sections) -> list[dict]:
    """Переводит MenuSection/MenuItem (frozen dataclass) в простые dict.

    Так модуль не зависит от импорта классов игры и легко тестируется. Каждая
    секция -> {title, icon, items:[{key,title,hint,icon}, ...]}.
    """
    plain = []
    for sec in sections:
        items = []
        for it in getattr(sec, "items", ()):
            items.append({
                "key": str(getattr(it, "key", "")).upper(),
                "title": getattr(it, "title", ""),
                "hint": getattr(it, "hint", ""),
                "icon": getattr(it, "icon", ""),
            })
        plain.append({
            "title": getattr(sec, "title", ""),
            "icon": getattr(sec, "icon", "•"),
            "items": items,
        })
    return plain


def all_valid_keys(plain_sections) -> list[str]:
    return [it["key"] for sec in plain_sections for it in sec["items"]]


def _slug(key: str) -> str:
    """Безопасный id виджета Textual: только буквы/цифры/подчёркивание.

    Ключи меню — одиночные буквы/цифры, но цифровой id в Textual валиден только
    если не начинается с цифры, поэтому префиксуем.
    """
    return "k_" + "".join(ch if (ch.isalnum() or ch == "_") else "_" for ch in key)


# ─── Textual-приложение ─────────────────────────────────────────────────────
if TEXTUAL_AVAILABLE:

    class RomaTextualMenu(App):
        """Главное меню Roma Aeterna. Возвращает выбранный ключ через .run()."""

        # CSS в стиле скриншота: тёмный фон, золотой заголовок, малиновый
        # подзаголовок, золотая рамка статуса, синие рамки-карточки, крупные
        # кнопки. Вертикальная прокрутка — под телефон (Pydroid).
        CSS = """
        Screen {
            background: #2b0008;
            color: #f4e8b8;
        }

        #root {
            padding: 1 2;
        }

        #title {
            height: auto;
            text-align: center;
            text-style: bold;
            color: #ffd700;
            margin-bottom: 1;
        }

        #subtitle {
            height: auto;
            text-align: center;
            color: #d66b9b;
            margin-bottom: 1;
        }

        #dashboard {
            height: auto;
            border: round #f6d365;
            background: #350009;
            color: #f4e8b8;
            padding: 1 2;
            margin-bottom: 1;
        }

        .section {
            height: auto;
            border: round #d4af37;
            background: #3a000b;
            padding: 1 2;
            margin-bottom: 1;
        }

        .section-title {
            height: auto;
            text-style: bold;
            color: #f6d365;
            margin-bottom: 1;
        }

        Button {
            background: #5a0010;
            color: #f6d365;
            border: round #d4af37;
            width: 100%;
            height: 3;
            margin-bottom: 1;
            content-align: center middle;
        }

        Button:hover {
            background: #8b0000;
            color: #ffffff;
            border: round #ffd700;
        }

        Button:focus {
            background: #700014;
            color: #ffd86b;
            border: round #ffd700;
        }

        #hint {
            height: auto;
            text-align: center;
            color: #9aa0aa;
            margin-top: 1;
        }

        Footer {
            background: #102638;
            color: #f4e8b8;
        }
        """

        # ── Клавиши ────────────────────────────────────────────────────────
        # Textual читает BINDINGS как атрибут КЛАССА при определении класса и
        # официально не поддерживает изменение биндингов во время работы (метод
        # App.bind помечен как приватный/удаляемый в будущих версиях). Поэтому
        # объявляем биндинги статически из полного канонического набора клавиш
        # главного меню игры. Набор фиксирован (_main_menu_sections_v2257), так
        # что это безопасно и совпадает с валидными ключами. action_choose сам
        # игнорирует ключ, если раздел с ним в текущем меню отсутствует.
        #
        # Формат кортежа Textual: (клавиша, строка-действие, подпись для Footer).
        # Аргумент передаётся ВНУТРИ строки действия: "choose('Q')".
        BINDINGS = [
            (k.lower(), f"choose('{k}')", label)
            for k, label in [
                ("1", "Провинции"), ("2", "Легионы"), ("4", "Ход"),
                ("V", "Победа"), ("P", "Сенат"), ("D", "Религия"),
                ("C", "Советник"), ("5", "Экономика"), ("F", "Флот"),
                ("6", "Внешняя политика"), ("7", "Наука"), ("9", "Пасс"),
                ("A", "Ауксилия"), ("B", "Варвары"), ("T", "Артиллерия"),
                ("L", "Люди"), ("W", "Чудеса"), ("Y", "Пророчества"),
                ("Z", "Штаб"), ("8", "Лог"), ("N", "Летопись"), ("S", "Сохранить"), ("Q", "Выход"),
            ]
        ] + [("escape", "choose('Q')", "Выход")]

        def __init__(self, player, ctx: dict, sections):
            super().__init__()
            self.player = player
            self.ctx = ctx or {}
            self._plain = sections_to_plain(sections)
            self._valid = set(all_valid_keys(self._plain))
            self.choice: str | None = None

        def compose(self) -> ComposeResult:
            title_color = ""  # цвет задаётся в CSS
            game_version = self.ctx.get("GAME_VERSION", "?")
            dashboard = build_dashboard_text(self.player, self.ctx)

            body = [
                Static("ROMA AETERNA", id="title"),
                Static(
                    f"SENATUS • LEGIONES • PROVINCIAE • AURUM  •  v{game_version}",
                    id="subtitle",
                ),
                Static(dashboard, id="dashboard"),
            ]

            for sec in self._plain:
                children = [Static(f"{sec['icon']} {sec['title']}", classes="section-title")]
                for it in sec["items"]:
                    label = f"{it['key']}  {it['icon']} {it['title']}".replace("  ", " ").strip()
                    # Чуть аккуратнее: ключ, иконка, название
                    label = f"{it['key']}   {it['icon']} {it['title']}" if it["icon"] else f"{it['key']}   {it['title']}"
                    children.append(Button(label, id=_slug(it["key"])))
                body.append(Vertical(*children, classes="section"))

            body.append(Static(
                "Можно нажимать клавиши или выбирать мышкой. После раздела игра вернётся сюда.",
                id="hint",
            ))
            body.append(Footer())

            yield VerticalScroll(*body, id="root")

        def on_button_pressed(self, event: "Button.Pressed") -> None:
            btn_id = event.button.id or ""
            # id имеет вид k_<KEY>; восстанавливаем ключ
            key = btn_id[2:] if btn_id.startswith("k_") else btn_id
            self.action_choose(key)

        def action_choose(self, choice: str) -> None:
            choice = str(choice).upper()
            if choice not in self._valid:
                return  # игнорируем неизвестные приказы, меню не закрываем
            self.choice = choice
            self.exit(choice)


def _gather_ctx_from_globals(caller_globals: dict | None) -> dict:
    """Собирает нужные helper'ы из глобалей вызывающего модуля.

    Позволяет из основного файла игры вызвать run_textual_menu(player) без явной
    передачи ctx: мы просто вытащим DIFFICULTY_PRESETS, get_era и т.д. из его
    globals().
    """
    g = caller_globals or {}
    keys = [
        "player_status_display", "get_era", "DIFFICULTY_PRESETS",
        "RELIGION_CHOICES", "PROVINCES_DATA", "TECH_TREE", "GAME_VERSION",
        "FOREIGN_POLICY_DOCTRINES", "ensure_all_states",
    ]
    return {k: g[k] for k in keys if k in g}


def run_textual_menu(player, sections, ctx: dict | None = None,
                     caller_globals: dict | None = None) -> str | None:
    """Запускает Textual-меню и возвращает выбранный ключ ("1", "P", "Q", ...).

    Возвращает None, если:
        • Textual не установлен (нужно откатиться на Rich/ANSI), или
        • во время работы меню произошла ошибка (безопасный откат).

    Параметры
    ---------
    player   : объект игрока.
    sections : список MenuSection (из _main_menu_sections_v2257()).
    ctx      : словарь helper'ов игры (см. модульный docstring). Если None —
               берётся из caller_globals.
    caller_globals : globals() вызывающего модуля (fallback-источник ctx).
    """
    if not TEXTUAL_AVAILABLE:
        return None

    if ctx is None:
        ctx = _gather_ctx_from_globals(caller_globals)

    # Гарантируем инициализацию состояния, если игра дала нам такую функцию.
    ensure = ctx.get("ensure_all_states")
    if callable(ensure):
        try:
            ensure(player)
        except Exception as e:
            log.warning("ensure_all_states упал: %s", e)

    try:
        app = RomaTextualMenu(player, ctx, sections)
        result = app.run()
        return result if result in set(all_valid_keys(sections_to_plain(sections))) else None
    except Exception as e:
        log.warning("Textual-меню упало, откат на Rich/ANSI: %s", e, exc_info=True)
        return None
