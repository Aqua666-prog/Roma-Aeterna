#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Property-based и регрессионные тесты Roma Economica v3.

Hypothesis используется, если установлен. В чистом Termux/Pydroid тесты всё
равно работают: включается детерминированный fuzz-набор без внешних пакетов.
"""
from __future__ import annotations

import copy
import math
import random
import unittest

import roma_economy as eco

try:
    from hypothesis import given, settings, strategies as st
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False


class DummyPlayer:
    def __init__(self) -> None:
        self.name = "Testus Oeconomicus"
        self.turn = 1
        self.gold = 1000
        self.grain = 500
        self.unrest = 20
        self.morale = 70
        self.senate_rep = 65
        self.people_rep = 65
        self.science_points = 0
        self.faith = 0


def make_context(provinces: int = 3, unrest: float = 20.0, income_mult: float = 1.0) -> dict:
    profiles = []
    for i in range(max(1, provinces)):
        profiles.append({
            "name": f"Provincia {i}",
            "wealth": 2 + i % 5,
            "city_count": 1 + i % 2,
            "city_population": 70 + i * 6,
            "agriculture": 0.55 + (i % 3) * 0.18,
            "mining": 0.20 + (i % 4) * 0.14,
            "manufacturing": 0.25 + (i % 5) * 0.08,
            "construction": 0.24 + (i % 3) * 0.09,
            "commerce": 0.28 + (i % 4) * 0.11,
            "romanization": 25 + i * 4,
            "unrest": min(10, i % 6),
            "garrison": i % 4,
        })
    return {
        "province_count": len(profiles),
        "provinces": profiles,
        "avg_romanization": sum(p["romanization"] for p in profiles) / len(profiles),
        "avg_province_unrest": sum(p["unrest"] for p in profiles) / len(profiles),
        "legion_count": max(1, provinces // 2),
        "legion_force_limit": 2 + provinces // 2,
        "legion_quality_index": 1.0,
        "trade_pacts": min(4, provinces // 2),
        "trade_route_value": provinces * 4,
        "tribute_income": 0,
        "tribute_paid": 0,
        "special_gold_income": provinces * 2,
        "special_grain_income": provinces,
        "fleet_upkeep": 0,
        "state_domain_income": provinces * 2.5,
        "agriculture_index": provinces * 0.8,
        "grain_productivity": 0,
        "tech_productivity": 0.02,
        "base_revenue": 30,
        "treasury_cash": 1000,
        "income_mult": income_mult,
        "effective_unrest": unrest,
        "senate_rep": 65,
        "people_rep": 65,
        "morale": 70,
        "climate_factor": 1.0,
        "embargo_level": 0.0,
    }


class EconomyInvariantTests(unittest.TestCase):
    def test_migration_from_v1(self) -> None:
        p = DummyPlayer()
        p.economy = {"version": 1, "population": 250.0, "capital_stock": 180.0, "money_supply": 800.0}
        state = eco.ensure_economy_state(p, make_context())
        self.assertEqual(state["version"], eco.ECONOMY_VERSION)
        self.assertEqual(set(state["sectoral_capital"]), set(eco.SECTOR_KEYS))
        self.assertIn("financial", state)
        self.assertIn("trade", state)
        self.assertIn("innovation", state)

    def test_long_run_invariants(self) -> None:
        p = DummyPlayer()
        ctx = make_context(5)
        for turn in range(1, 301):
            p.turn = turn
            ctx["treasury_cash"] = p.gold
            eco.apply_turn(p, ctx)
            self.assertEqual([], eco.audit_invariants(p, ctx))

    def test_seeded_shocks_are_reproducible(self) -> None:
        p1, p2 = DummyPlayer(), DummyPlayer()
        ctx = make_context(4)
        s1 = eco.ensure_economy_state(p1, ctx)
        s2 = eco.ensure_economy_state(p2, ctx)
        self.assertEqual(eco.apply_economic_shocks(p1, ctx, s1), eco.apply_economic_shocks(p2, ctx, s2))
        self.assertEqual(s1["active_shocks"], s2["active_shocks"])

    def test_national_accounts_identity(self) -> None:
        p = DummyPlayer()
        report = eco.preview_turn(p, make_context())
        exp = report["national_accounts"]["expenditure"]
        total = exp["consumption"] + exp["investment"] + exp["government"] + exp["net_exports"] + exp["statistical_discrepancy"]
        self.assertAlmostEqual(exp["gdp"], total, places=6)

    def test_budget_and_sector_shares(self) -> None:
        for seed in range(100):
            rng = random.Random(seed)
            budget = eco.normalize_budget_shares({k: rng.uniform(-20, 100) for k in eco.BUDGET_KEYS})
            sectors = eco.normalize_sector_shares({k: rng.uniform(-20, 100) for k in eco.SECTOR_KEYS}, eco.DEFAULT_SECTOR_LABOR_SHARES)
            self.assertAlmostEqual(sum(budget.values()), 1.0, places=12)
            self.assertAlmostEqual(sum(sectors.values()), 1.0, places=12)
            self.assertTrue(all(v >= 0 for v in budget.values()))
            self.assertTrue(all(v >= 0 for v in sectors.values()))


if HYPOTHESIS_AVAILABLE:
    class HypothesisEconomyTests(unittest.TestCase):
        @settings(max_examples=80, deadline=None)
        @given(
            tax=st.floats(min_value=0.0, max_value=0.65, allow_nan=False, allow_infinity=False),
            tariff=st.floats(min_value=0.0, max_value=0.45, allow_nan=False, allow_infinity=False),
            provinces=st.integers(min_value=1, max_value=20),
            unrest=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        )
        def test_statement_is_finite(self, tax: float, tariff: float, provinces: int, unrest: float) -> None:
            p = DummyPlayer()
            ctx = make_context(provinces, unrest)
            eco.set_tax_rate(p, tax)
            eco.set_tariff_rate(p, tariff)
            report = eco.preview_turn(p, ctx)
            self.assertTrue(math.isfinite(report["macro"]["real_output"]))
            self.assertTrue(math.isfinite(report["overall_balance"]))
            self.assertEqual(set(report["sectors"]["output"]), set(eco.SECTOR_KEYS))
            self.assertEqual([], eco.audit_invariants(p, ctx))

        @settings(max_examples=60, deadline=None)
        @given(st.dictionaries(
            keys=st.sampled_from(list(eco.BUDGET_KEYS)),
            values=st.floats(min_value=-100, max_value=1000, allow_nan=False, allow_infinity=False),
            min_size=0,
            max_size=len(eco.BUDGET_KEYS),
        ))
        def test_budget_normalization_property(self, raw: dict[str, float]) -> None:
            result = eco.normalize_budget_shares(raw)
            self.assertAlmostEqual(sum(result.values()), 1.0, places=12)
            self.assertTrue(all(value >= 0 for value in result.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
