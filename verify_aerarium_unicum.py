#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for Roma Aeterna 4.3 Aerarium Unicum."""
from __future__ import annotations

import ast
import contextlib
import io
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(1, str(PARENT))
os.environ.setdefault("ROMA_NONINTERACTIVE", "1")

import roma_aeterna as game  # noqa: E402


class Checks:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        self.rows.append((name, bool(condition), detail))
        if not condition:
            raise AssertionError(f"{name}: {detail}")


def silence_end_turn() -> None:
    game.pause = lambda *args, **kwargs: None
    for name in (
        "random_event",
        "maybe_history_quiz_event",
        "maybe_prophecy_event",
        "maybe_aristocrat_event",
        "handle_foreign_and_governor_gifts",
        "maybe_barbarian_gifts",
        "maybe_spawn_great_person",
        "maybe_religion_event",
        "maybe_spawn_sacred_general",
        "handle_civil_war",
        "process_pending_interactions",
        "process_resource_economy_interactions",
        "show_turn_summary",
    ):
        setattr(game, name, lambda *args, **kwargs: None)
    game.show_imperial_resource_report = lambda *args, **kwargs: None


def main() -> int:
    c = Checks()

    # 1. Syntax/import contract.
    for filename in ("roma_aeterna.py", "roma_economy.py", "roma_resources.py", "roma_technology_overhaul.py"):
        source = (ROOT / filename).read_text(encoding="utf-8")
        compile(source, filename, "exec")
    c.check("Python compilation", True, "4 files")
    c.check("Game version", game.GAME_VERSION == "4.3.0-aerarium-unicum", game.GAME_VERSION)
    c.check("Economy version", getattr(game.ADVANCED_ECONOMY, "ECONOMY_VERSION", 0) >= 13)
    c.check("Resource version", getattr(game.RESOURCE_ECONOMY, "RESOURCE_ECONOMY_VERSION", 0) >= 5)

    # 2. Resource module has no assignments to player.gold.
    tree = ast.parse((ROOT / "roma_resources.py").read_text(encoding="utf-8"))
    treasury_writes: list[int] = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr == "gold":
                treasury_writes.append(node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "setattr":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and node.args[1].value == "gold":
                treasury_writes.append(node.lineno)
    c.check("No resource treasury writes", not treasury_writes, str(treasury_writes))

    # 3. Resource tick changes goods only.
    resource_player = game.Player("Resourcius", "optimates", "normal")
    game.ensure_all_states(resource_player)
    resource_player.turn = 2
    gold_before = resource_player.gold
    flow = game.RESOURCE_ECONOMY.apply_turn(resource_player, game.resource_economy_context(resource_player))
    c.check("Resource tick preserves gold", resource_player.gold == gold_before, f"{gold_before}->{resource_player.gold}")
    c.check("Hidden auto-buy is zero", int(flow.get("auto_purchase_cost", -1)) == 0, str(flow.get("auto_purchase_cost")))

    # 4. Full integration: route and caravan go through the economy statement exactly once.
    silence_end_turn()
    player = game.Player("Aerarius", "optimates", "normal")
    game.ensure_all_states(player)
    game.ensure_v24_state(player)
    game.ensure_republic_overhaul_state(player)
    player.v24["trade_routes"] = [{"name": "Roma ↔ Test", "value": 144, "active": True}]
    player.v24["caravans"] = [{
        "origin": "Roma",
        "dest": "Test",
        "goods": "wine",
        "amount": 5,
        "value": 120,
        "turns": 1,
        "risk": 0,
        "escort": "legion",
    }]
    random.seed(7)
    with contextlib.redirect_stdout(io.StringIO()):
        game.end_turn(player)
    statement = player.economy["last_statement"]
    revenues = statement["revenues"]
    c.check("Route exact in statement", revenues.get("trade_routes") == 144, str(revenues.get("trade_routes")))
    c.check("Caravan exact in statement", revenues.get("caravans") == 120, str(revenues.get("caravans")))
    c.check("Caravan removed after arrival", not player.v24["caravans"])
    c.check("Resource tick ran on same turn", player.resource_economy.get("last_processed_turn") == player.turn)

    # 5. Mare Nostrum no longer changes gold after Roma Economica has posted it.
    before_v24 = player.gold
    with contextlib.redirect_stdout(io.StringIO()):
        game.v24_end_turn_tick(player)
    c.check("No second route credit", player.gold == before_v24, f"{before_v24}->{player.gold}")

    # 6. Caravan cannot repeat on the next turn.
    with contextlib.redirect_stdout(io.StringIO()):
        game.end_turn(player)
    second = player.economy["last_statement"]["revenues"]
    c.check("Caravan not repeated", second.get("caravans", 0) == 0, str(second.get("caravans")))
    c.check("Route remains regular", second.get("trade_routes") == 144, str(second.get("trade_routes")))

    # 7. Resource offer returns a delta; only Roma Economica applies it.
    offer_player = game.Player("Mercator", "optimates", "normal")
    game.ensure_all_states(offer_player)
    rctx = game.resource_economy_context(offer_player)
    rstate = game.RESOURCE_ECONOMY.ensure_state(offer_player, rctx)
    rstate["pending_investment_offer"] = {
        "resource": "iron",
        "name": "Железо",
        "icon": "⚒",
        "tiers": [{"key": "1", "cost": 50, "level_gain": 0.5, "yield_bonus": 7}],
    }
    before_offer = offer_player.gold
    unauthorized = game.RESOURCE_ECONOMY.resolve_investment_offer(offer_player, "1", rctx)
    c.check("Offer asks treasury authorization", unauthorized.get("requires_treasury") is True)
    c.check("Unauthorized offer preserves gold", offer_player.gold == before_offer)
    authorized_context = dict(rctx)
    authorized_context["treasury_authorized"] = True
    accepted = game.RESOURCE_ECONOMY.resolve_investment_offer(offer_player, "1", authorized_context)
    c.check("Resource module still preserves gold", offer_player.gold == before_offer)
    transaction = game.economy_cash_transaction(
        offer_player,
        accepted["gold_delta"],
        accepted["label"],
        category=accepted["category"],
    )
    c.check("Central transaction applied", transaction.get("ok") and offer_player.gold == before_offer - 50)

    passed = sum(1 for _, ok, _ in c.rows if ok)
    print(f"AERARIUM UNICUM: {passed}/{len(c.rows)} checks passed")
    for name, ok, detail in c.rows:
        suffix = f" — {detail}" if detail else ""
        print(f"{'PASS' if ok else 'FAIL'}: {name}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
