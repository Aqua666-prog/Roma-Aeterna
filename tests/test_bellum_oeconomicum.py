from __future__ import annotations

import contextlib
import copy
import io
import random
import unittest

import roma_aeterna as game


class BellumOeconomicumTests(unittest.TestCase):
    def setUp(self) -> None:
        random.seed(2600)
        self.player = game.Player("Testus", "optimates", "normal")
        game.ensure_all_states(self.player)
        owned = {p.get("name") for p in self.player.provinces if isinstance(p, dict)}
        self.target = next(
            p for p in game.PROVINCES_DATA
            if isinstance(p, dict) and p.get("name") not in owned and p.get("cities")
        )

    def test_city_reward_is_one_time(self) -> None:
        city = copy.deepcopy(self.target["cities"][0])
        first = game.city_conquest_reward(self.player, self.target, city, announce=False)
        second = game.city_conquest_reward(self.player, self.target, city, announce=False)
        self.assertGreater(first["gold"], 0)
        self.assertTrue(second.get("duplicate"))
        self.assertEqual(second["gold"], 0)

    def test_province_policy_recovers_and_produces(self) -> None:
        province = game.captured_province_copy(self.target["name"])
        province.update({
            "economic_policy": "integration",
            "economic_policy_turn": 1,
            "war_damage": 0.45,
            "occupation_progress": 0.05,
            "romanization": 10,
            "garrison": 0,
        })
        self.player.provinces.append(province)
        before = province["war_damage"]
        with contextlib.redirect_stdout(io.StringIO()):
            gold, grain = game.conquered_province_economy_tick(self.player)
        self.assertLess(province["war_damage"], before)
        self.assertIsInstance(gold, int)
        self.assertIsInstance(grain, int)

    def test_schema_and_invariants(self) -> None:
        context = game.advanced_economy_context(self.player)
        state = game.ADVANCED_ECONOMY.ensure_economy_state(self.player, context)
        self.assertEqual(state["version"], 4)
        self.assertEqual(game.ADVANCED_ECONOMY.audit_invariants(self.player, context), [])

    def test_serialization_preserves_policy(self) -> None:
        province = game.captured_province_copy(self.target["name"])
        province.update({
            "economic_policy": "military",
            "economic_policy_turn": 1,
            "war_damage": 0.37,
            "occupation_progress": 0.22,
            "romanization": 12,
            "garrison": 1,
        })
        self.player.provinces.append(province)
        game.ensure_conquest_economy_state(self.player)["claimed_provinces"].append(province["name"])
        game.ADVANCED_ECONOMY.ensure_economy_state(self.player, game.advanced_economy_context(self.player))
        restored = game.Player.from_dict(self.player.to_dict())
        game.ensure_all_states(restored)
        restored_province = next(p for p in restored.provinces if p.get("name") == province["name"])
        self.assertEqual(restored_province["economic_policy"], "military")
        self.assertIn(province["name"], restored.conquest_economy["claimed_provinces"])
        self.assertEqual(restored.economy["version"], 4)


if __name__ == "__main__":
    unittest.main()
