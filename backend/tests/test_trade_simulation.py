import unittest

from app.trade.simulation import (
    BidValidationError,
    build_review,
    run_clearing,
    run_settlement,
    validate_bid_schedule,
)


def _bids(side="buy"):
    return [
        {
            "period": period,
            "segments": [
                {"price": 350 if side == "buy" else 250, "volume": 80},
                {"price": 300 if side == "buy" else 300, "volume": 20},
            ],
        }
        for period in range(24)
    ]


class TradeSimulationTest(unittest.TestCase):
    def test_full_simulation_is_deterministic(self):
        bids = validate_bid_schedule(_bids(), period_count=24, max_volume=120, side="buy")
        snapshot = {"clearing_curve": [320.0] * 24}
        clearing = run_clearing(snapshot, bids, side="buy")
        self.assertEqual(clearing["cleared_volume"], 1920)
        self.assertEqual(clearing["fill_rate"], 80)
        first = run_settlement(clearing, side="buy", random_seed=42)
        second = run_settlement(clearing, side="buy", random_seed=42)
        self.assertEqual(first, second)
        review = build_review(clearing, first, side="buy")
        self.assertTrue(0 <= review["score"] <= 100)
        self.assertTrue(review["knowledge_gaps"])

    def test_bid_validation_rejects_wrong_price_order(self):
        bids = _bids()
        bids[0]["segments"] = [
            {"price": 200, "volume": 50},
            {"price": 300, "volume": 50},
        ]
        with self.assertRaisesRegex(BidValidationError, "递减"):
            validate_bid_schedule(bids, period_count=24, max_volume=120, side="buy")

    def test_bid_validation_rejects_incomplete_day(self):
        with self.assertRaisesRegex(BidValidationError, "24"):
            validate_bid_schedule(_bids()[:23], period_count=24, max_volume=120, side="buy")
