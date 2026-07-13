# -*- coding: utf-8 -*-
"""
roma_map_textual.py — карта провинций Roma Aeterna на Textual (совместима с v2.31).

Это отдельный безопасный UI-слой:
• не импортирует основной файл игры;
• берёт данные через caller_globals=globals();
• если Textual недоступен или карта падает — возвращает None, не ломая партию;
• кнопка "O" открывает старое меню управления провинциями.
"""

from __future__ import annotations

import logging

log = logging.getLogger("roma.textual_map")

try:
    from textual.app import App, ComposeResult
    from textual.containers import Vertical, VerticalScroll
    from textual.widgets import Static, Button
    TEXTUAL_MAP_AVAILABLE = True
except Exception as _e:
    log.info("Textual-карта недоступна: %s", _e)
    TEXTUAL_MAP_AVAILABLE = False


REGION_GROUPS = [
    ("ITALIA", ["Latium", "Campania", "Etruria", "Umbria", "Samnium", "Apulia", "Bruttium", "Liguria"]),
    ("OCCIDENS", ["Gallia", "Gallia Narbonensis", "Aquitania", "Belgica", "Hispania", "Lusitania", "Baetica"]),
    ("SEPTENTRIO", ["Germania Inferior", "Germania Superior", "Magna Germania", "Britannia", "Caledonia", "Hibernia"]),
    ("MARE NOSTRUM", ["Sicilia", "Sardinia et Corsica", "Carthago", "Numidia", "Mauretania", "Cyrenaica", "Aegyptus"]),
    ("GRAECIA ET BALKANI", ["Macedonia", "Achaea", "Epirus", "Illyricum", "Thracia", "Dacia"]),
    ("ORIENS", ["Asia Minor", "Bithynia", "Galatia", "Cappadocia", "Pontus", "Cilicia", "Syria", "Judaea", "Armenia", "Mesopotamia"]),
]


def safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _gather_ctx(caller_globals: dict | None) -> dict:
    g = caller_globals or {}
    keys = [
        "PROVINCES_DATA",
        "GAME_VERSION",
        "player_status_display",
        "get_era",
        "frontier_provinces",
        "city_campaign_progress",
        "province_by_name",
        "ensure_all_states",
    ]
    return {k: g[k] for k in keys if k in g}


def _province_name_set(items) -> set[str]:
    names = set()
    for item in items or []:
        if isinstance(item, dict):
            name = item.get("name")
        else:
            name = getattr(item, "name", None)
        if name:
            names.add(str(name))
    return names


def _province_defs(ctx: dict) -> list[dict]:
    data = ctx.get("PROVINCES_DATA", [])
    return [p for p in data if isinstance(p, dict) and p.get("name")]


def _province_by_name(ctx: dict, name: str) -> dict | None:
    fn = ctx.get("province_by_name")
    if callable(fn):
        try:
            p = fn(name)
            if isinstance(p, dict):
                return p
        except Exception:
            pass
    for p in _province_defs(ctx):
        if p.get("name") == name:
            return p
    return None


def _frontier_names(player, ctx: dict, owned: set[str]) -> set[str]:
    fn = ctx.get("frontier_provinces")
    if callable(fn):
        try:
            return {p.get("name") for p in fn(player) if isinstance(p, dict) and p.get("name")}
        except Exception:
            pass

    frontier = set()
    for name in owned:
        prov = _province_by_name(ctx, name)
        if prov:
            frontier.update(prov.get("neighbors", []))
    return frontier - owned


def _enemy_province_names(player) -> set[str]:
    result = set()
    for army in getattr(player, "enemy_armies", []) or []:
        if isinstance(army, dict):
            name = army.get("province")
        else:
            name = getattr(army, "province", None)
        if name:
            result.add(str(name))
    for siege in getattr(player, "enemy_ai_sieges", []) or []:
        if isinstance(siege, dict) and siege.get("province"):
            result.add(str(siege.get("province")))
    return result


def _status_for(name: str, owned: set[str], frontier: set[str], enemies: set[str]) -> str:
    if name in owned:
        return "owned_enemy" if name in enemies else "owned"
    if name in enemies:
        return "enemy"
    if name in frontier:
        return "frontier"
    return "unknown"


def _mark(status: str) -> str:
    return {
        "owned": "🟩",
        "owned_enemy": "🟧",
        "frontier": "🟨",
        "enemy": "🟥",
        "unknown": "⬛",
    }.get(status, "⬛")


def _style(status: str) -> str:
    return {
        "owned": "#98c379",
        "owned_enemy": "#ffb86c",
        "frontier": "#f6d365",
        "enemy": "#ff5555",
        "unknown": "#9aa0aa",
    }.get(status, "#9aa0aa")


def _short(name: str, width: int = 16) -> str:
    return name if len(name) <= width else name[:width - 1] + "…"


def _tile(name: str, owned: set[str], frontier: set[str], enemies: set[str], width: int = 20) -> str:
    if not name:
        return " " * width
    status = _status_for(name, owned, frontier, enemies)
    label = f"{_mark(status)} {_short(name, width - 3)}"
    return f"[{_style(status)}]{label:<{width}}[/]"


def build_schematic_map(player, ctx: dict) -> str:
    owned = _province_name_set(getattr(player, "provinces", []))
    frontier = _frontier_names(player, ctx, owned)
    enemies = _enemy_province_names(player)

    # Схема специально не географически точная до мили: это tabula imperii,
    # читаемая на телефоне. Главное — видеть ядро, фронтир и угрозы.
    rows = [
        ["", "Caledonia", "Hibernia"],
        ["", "Britannia", "Magna Germania"],
        ["Hispania", "Gallia", "Belgica"],
        ["Lusitania", "Gallia Narbonensis", "Germania Inferior"],
        ["Baetica", "Liguria", "Germania Superior"],
        ["Carthago", "Latium", "Dacia"],
        ["Sardinia et Corsica", "Campania", "Illyricum"],
        ["Numidia", "Sicilia", "Macedonia"],
        ["Mauretania", "Bruttium", "Achaea"],
        ["Cyrenaica", "Aegyptus", "Asia Minor"],
        ["", "Judaea", "Syria"],
        ["", "Armenia", "Mesopotamia"],
    ]
    lines = ["[bold #ffd700]TABULA IMPERII[/]\n"]
    for row in rows:
        lines.append("".join(_tile(name, owned, frontier, enemies, 21) for name in row).rstrip())
    lines.append("")
    lines.append("[#98c379]🟩 Provincia Romana[/]   [#f6d365]🟨 Fines / фронтир[/]")
    lines.append("[#ff5555]🟥 Hostes[/]             [#ffb86c]🟧 Осада/враг в нашей провинции[/]")
    return "\n".join(lines)


def _city_list(prov: dict) -> list[dict]:
    cities = prov.get("cities", [])
    return [c for c in cities if isinstance(c, dict)]


def _legions_in(player, province_name: str, prov: dict | None) -> list:
    city_names = {c.get("name") for c in _city_list(prov or {}) if c.get("name")}
    if province_name == "Latium":
        city_names.add("Roma")
    city_names.add(province_name)
    result = []
    for leg in getattr(player, "legions", []) or []:
        loc = getattr(leg, "location", "")
        if loc in city_names:
            result.append(leg)
    return result


def _enemy_armies_in(player, province_name: str) -> list:
    result = []
    for army in getattr(player, "enemy_armies", []) or []:
        if isinstance(army, dict):
            prov = army.get("province")
        else:
            prov = getattr(army, "province", None)
        if prov == province_name:
            result.append(army)
    return result


def build_province_card(player, ctx: dict, province_name: str | None) -> str:
    data = _province_defs(ctx)
    if not data:
        return "[#ff5555]Нет PROVINCES_DATA: карта не получила данные мира.[/]"

    province_name = province_name or (getattr(player, "provinces", [{}])[0].get("name") if getattr(player, "provinces", None) else data[0].get("name"))
    prov = _province_by_name(ctx, province_name) or data[0]

    owned = _province_name_set(getattr(player, "provinces", []))
    frontier = _frontier_names(player, ctx, owned)
    enemies = _enemy_province_names(player)
    status = _status_for(prov["name"], owned, frontier, enemies)

    city_names = ", ".join(c.get("name", "urbs") for c in _city_list(prov)) or "нет городов"
    wealth = safe_int(prov.get("wealth", 0), 0)
    unrest = safe_int(prov.get("unrest", 0), 0)
    neighbors = ", ".join(prov.get("neighbors", [])) or "нет соседей"

    captured = None
    progress_fn = ctx.get("city_campaign_progress")
    if callable(progress_fn):
        try:
            c_done, c_total = progress_fn(player, prov["name"])
            captured = f"{c_done}/{c_total}"
        except Exception:
            captured = None

    legions = _legions_in(player, prov["name"], prov)
    enemies_here = _enemy_armies_in(player, prov["name"])

    owner_text = {
        "owned": "[#98c379]SPQR владеет провинцией[/]",
        "owned_enemy": "[#ffb86c]SPQR владеет провинцией, но там замечен враг[/]",
        "frontier": "[#f6d365]Фронтир: доступна для похода[/]",
        "enemy": "[#ff5555]Hostes: вражеские силы[/]",
        "unknown": "[#9aa0aa]Ещё вне прямого доступа Рима[/]",
    }.get(status, "—")

    lines = [
        f"[bold #ffd700]🏛 {prov['name']}[/]",
        owner_text,
        "",
        f"Города: [#f4e8b8]{city_names}[/]",
        f"Богатство: [#f6d365]{wealth}[/]   Смутность: [#ff8888]{unrest}[/]",
    ]
    if captured is not None:
        lines.append(f"Городская кампания: [#7dcfff]{captured}[/]")
    lines.append(f"Соседи: [#9aa0aa]{neighbors}[/]")
    lines.append("")

    if legions:
        lines.append("[#f6d365]Легионы в области:[/]")
        for leg in legions[:6]:
            lines.append(
                f"• {getattr(leg, 'name', 'Legio')} — сила {getattr(leg, 'strength', '?')}, "
                f"мораль {getattr(leg, 'morale', '?')}, позиция {getattr(leg, 'location', '?')}"
            )
    else:
        lines.append("[#9aa0aa]Легионов в области не видно.[/]")

    if enemies_here:
        lines.append("")
        lines.append("[#ff5555]Вражеские армии:[/]")
        for army in enemies_here[:6]:
            if isinstance(army, dict):
                lines.append(f"• {army.get('name', 'Hostes')} — сила {army.get('strength', '?')}, мораль {army.get('morale', '?')}")
            else:
                lines.append(f"• {getattr(army, 'name', 'Hostes')} — сила {getattr(army, 'strength', '?')}, мораль {getattr(army, 'morale', '?')}")
    return "\n".join(lines)


def build_region_buttons(player, ctx: dict) -> list[tuple[str, list[tuple[str, str, str]]]]:
    owned = _province_name_set(getattr(player, "provinces", []))
    frontier = _frontier_names(player, ctx, owned)
    enemies = _enemy_province_names(player)
    result = []
    available = {p["name"] for p in _province_defs(ctx)}
    for region, names in REGION_GROUPS:
        rows = []
        for name in names:
            if name not in available:
                continue
            status = _status_for(name, owned, frontier, enemies)
            rows.append((name, status, f"{_mark(status)} {name}"))
        if rows:
            result.append((region, rows))
    return result


if TEXTUAL_MAP_AVAILABLE:

    class RomaMapApp(App):
        CSS = """
        Screen {
            background: #210006;
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

        #schematic {
            height: auto;
            border: round #d4af37;
            background: #300008;
            padding: 1 1;
            margin-bottom: 1;
        }

        #province_card {
            height: auto;
            border: round #f6d365;
            background: #3a000b;
            padding: 1 2;
            margin-bottom: 1;
        }

        .region {
            height: auto;
            border: round #7a2c2c;
            background: #2b0008;
            padding: 1 2;
            margin-bottom: 1;
        }

        .region-title {
            height: auto;
            text-style: bold;
            color: #f6d365;
            margin-bottom: 1;
        }

        Button {
            width: 100%;
            height: 3;
            margin-bottom: 1;
            content-align: center middle;
            border: round #d4af37;
        }

        Button.owned {
            background: #153b1f;
            color: #dfffd6;
        }

        Button.owned_enemy {
            background: #5c2d00;
            color: #ffe0aa;
        }

        Button.frontier {
            background: #5a3f00;
            color: #fff1b8;
        }

        Button.enemy {
            background: #620000;
            color: #ffd0d0;
        }

        Button.unknown {
            background: #1a0005;
            color: #9aa0aa;
            border: round #604040;
        }

        Button.action {
            background: #5a0010;
            color: #f6d365;
            border: round #d4af37;
        }

        Button:hover {
            background: #8b0000;
            color: #ffffff;
        }

        #hint {
            height: auto;
            text-align: center;
            color: #9aa0aa;
            margin-top: 1;
            margin-bottom: 1;
        }
        """

        BINDINGS = [
            ("q", "back", "Назад"),
            ("escape", "back", "Назад"),
            ("o", "open_old", "Старое меню"),
            ("p", "open_old", "Провинции"),
        ]

        def __init__(self, player, ctx: dict):
            super().__init__()
            self.player = player
            self.ctx = ctx or {}
            self.province_by_button: dict[str, str] = {}
            owned = list(_province_name_set(getattr(player, "provinces", [])))
            self.selected = owned[0] if owned else (_province_defs(self.ctx)[0]["name"] if _province_defs(self.ctx) else None)

        def compose(self) -> ComposeResult:
            ensure = self.ctx.get("ensure_all_states")
            if callable(ensure):
                try:
                    ensure(self.player)
                except Exception:
                    pass

            version = self.ctx.get("GAME_VERSION", "?")
            era_fn = self.ctx.get("get_era", lambda p: {"name": "—"})
            try:
                era = era_fn(self.player) or {}
                era_name = era.get("name", "—") if isinstance(era, dict) else "—"
            except Exception:
                era_name = "—"

            body = [
                Static("TABULA IMPERII ROMANI", id="title"),
                Static(f"SPQR • PROVINCIAE • FINES • HOSTES  •  v{version}  •  {era_name}", id="subtitle"),
                Static(build_schematic_map(self.player, self.ctx), id="schematic"),
                Static(build_province_card(self.player, self.ctx, self.selected), id="province_card"),
                Static("Нажми провинцию для карточки. O/P — открыть старое управление провинциями. Q/Esc — назад.", id="hint"),
                Button("O   🗺 Открыть управление провинциями", id="open_old", classes="action"),
                Button("Q   🚪 Назад в главное меню", id="back", classes="action"),
            ]

            for region, rows in build_region_buttons(self.player, self.ctx):
                children = [Static(f"✦ {region}", classes="region-title")]
                for name, status, label in rows:
                    bid = "prov_" + "".join(ch if ch.isalnum() else "_" for ch in name)
                    self.province_by_button[bid] = name
                    children.append(Button(label, id=bid, classes=status))
                body.append(Vertical(*children, classes="region"))

            yield VerticalScroll(*body, id="root")

        def on_button_pressed(self, event) -> None:
            bid = event.button.id or ""
            if bid == "back":
                self.exit(None)
                return
            if bid == "open_old":
                self.exit("PROVINCE_MENU")
                return
            if bid in self.province_by_button:
                self.selected = self.province_by_button[bid]
                try:
                    card = self.query_one("#province_card", Static)
                    card.update(build_province_card(self.player, self.ctx, self.selected))
                except Exception as e:
                    log.warning("Не удалось обновить карточку провинции: %s", e)

        def action_back(self) -> None:
            self.exit(None)

        def action_open_old(self) -> None:
            self.exit("PROVINCE_MENU")


def run_textual_map(player, ctx: dict | None = None, caller_globals: dict | None = None) -> str | None:
    """Запускает карту. Возвращает:
    • "PROVINCE_MENU" — открыть старое меню провинций;
    • None — вернуться в главное меню / откат.
    """
    if not TEXTUAL_MAP_AVAILABLE:
        return None
    if ctx is None:
        ctx = _gather_ctx(caller_globals)
    try:
        ensure = ctx.get("ensure_all_states")
        if callable(ensure):
            ensure(player)
    except Exception:
        pass
    try:
        app = RomaMapApp(player, ctx)
        return app.run()
    except Exception as e:
        log.warning("Textual-карта упала, откат: %s", e, exc_info=True)
        return None
