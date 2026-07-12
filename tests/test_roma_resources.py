from __future__ import annotations

import unittest
from types import SimpleNamespace

import roma_resources as resources


class ResourceEconomyTests(unittest.TestCase):
    def make_player(self):
        economy = {
            "population": 900.0,
            "infrastructure": 42.0,
            "confidence": 0.72,
            "price_level": 1.0,
            "tax_capacity": 0.50,
            "sectoral_productivity": {
                "agriculture": 1.0,
                "mining": 1.0,
                "manufacturing": 1.0,
                "construction": 1.0,
                "commerce": 1.0,
            },
            "sectoral_output": {
                "agriculture": 60.0,
                "mining": 30.0,
                "manufacturing": 35.0,
                "construction": 25.0,
                "commerce": 40.0,
            },
        }
        return SimpleNamespace(
            name="Testus",
            faction="optimates",
            turn=1,
            gold=50_000,
            metals={"iron": 4, "copper": 3, "silver": 1, "gold_ore": 0},
            unrest=0,
            people_rep=55,
            senate_rep=60,
            morale=75,
            science_points=0,
            economy=economy,
        )

    def context(self, player):
        return {
            "turn": player.turn,
            "provinces": [
                {"name": "Latium", "wealth": 3, "romanization": 75, "unrest": 1},
                {"name": "Campania", "wealth": 4, "romanization": 65, "unrest": 1},
                {"name": "Hispania", "wealth": 4, "romanization": 40, "unrest": 2},
            ],
            "population": player.economy["population"],
            "infrastructure": player.economy["infrastructure"],
            "confidence": player.economy["confidence"],
            "price_level": player.economy["price_level"],
            "sectoral_productivity": player.economy["sectoral_productivity"],
            "sectoral_output": player.economy["sectoral_output"],
            "legion_count": 2,
            "aux_count": 1,
            "fleet_size": 1,
            "wonder_count": 0,
            "science_points": 0,
            "senate_rep": player.senate_rep,
            "people_rep": player.people_rep,
            "effective_unrest": player.unrest,
            "average_wealth": 3.7,
            "price_multiplier": 2.0,
            "diplomatic_partners": [
                {"key": "egypt", "name": "Египет", "relation": 65},
                {"key": "carthage", "name": "Карфаген", "relation": 55},
            ],
            "barbarian_partners": [
                {"key": "suebi", "name": "Свевы", "relation": 40},
            ],
        }

    def test_automatic_tick_is_idempotent(self):
        player = self.make_player()
        context = self.context(player)
        flow = resources.apply_turn(player, context)
        self.assertTrue(flow["production"])
        state = resources.ensure_state(player, context)
        stock = dict(state["stockpiles"])
        resources.apply_turn(player, context)
        self.assertEqual(stock, state["stockpiles"])

    def test_investment_offer_changes_capacity(self):
        player = self.make_player()
        context = self.context(player)
        state = resources.ensure_state(player, context)
        state["next_investment_turn"] = 1
        player.turn = 5
        resources.apply_turn(player, context)
        offer = resources.pending_offers(player, context)["investment"]
        self.assertIsInstance(offer, dict)
        key = offer["resource"]
        before = state["production_levels"][key]
        result = resources.resolve_investment_offer(player, "1", context)
        self.assertTrue(result["ok"])
        self.assertGreater(state["production_levels"][key], before)

    def test_trade_offer_can_be_resolved(self):
        player = self.make_player()
        context = self.context(player)
        state = resources.ensure_state(player, context)
        state["next_trade_turn"] = 1
        player.turn = 6
        resources.apply_turn(player, context)
        offer = resources.pending_offers(player, context)["trade"]
        self.assertIsInstance(offer, dict)
        result = resources.resolve_trade_offer(player, True, context)
        if not result["ok"]:
            result = resources.resolve_trade_offer(player, False, context)
        self.assertTrue(result["ok"])

    def test_legacy_metals_stay_synchronised(self):
        player = self.make_player()
        context = self.context(player)
        state = resources.ensure_state(player, context)
        player.metals["iron"] = 9
        player.turn = 2
        resources.apply_turn(player, context)
        self.assertEqual(player.metals["iron"], round(state["stockpiles"]["iron"]))

    def test_stress_invariants(self):
        player = self.make_player()
        for turn in range(1, 121):
            player.turn = turn
            context = self.context(player)
            resources.apply_turn(player, context)
            offers = resources.pending_offers(player, context)
            if offers["investment"]:
                resources.resolve_investment_offer(player, "Q", context)
            if offers["trade"]:
                resources.resolve_trade_offer(player, False, context)
            self.assertEqual(resources.audit_invariants(player, context), [])


if __name__ == "__main__":
    unittest.main()
