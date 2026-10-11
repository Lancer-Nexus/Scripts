#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "review-market-goods-coverage.py"
spec = importlib.util.spec_from_file_location("review_market_goods_coverage", SCRIPT)
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


class MarketGoodsCoverageTests(unittest.TestCase):
    def test_includes_every_good_and_keeps_policy_authorization_separate(self):
        report = {
            "schemaVersion": 1,
            "goods": [
                {"goodId": "gun", "category": "equipment", "source": "weapon_good.ini", "price": "10"},
                {"goodId": "hull", "category": "shiphull", "source": "goods.ini", "price": "20"},
                {"goodId": "package", "category": "ship", "source": "goods.ini", "hullGoodId": "hull", "addons": []},
            ],
            "unlistedGoodIds": ["hull"],
            "markets": [{
                "marketId": "base_a",
                "systemIds": ["li01"],
                "entries": [{"goodId": "gun", "forSale": True, "priceResolution": "integer_good_price",
                             "baselineUnitPrice": "10", "source": "market_misc.ini"}],
            }],
        }
        result = reviewer.build_review(json.dumps(report).encode())
        rows = {row["goodId"]: row for row in result["goods"]}
        self.assertEqual(3, result["goodsCount"])
        self.assertEqual(1, result["unlistedGoodCount"])
        self.assertEqual("included", rows["hull"]["dynamicScope"])
        self.assertEqual("package_hull_component", rows["hull"]["tradeClass"])
        self.assertEqual("atomic_bundle_required", rows["hull"]["bookingPath"])
        self.assertEqual(1, rows["gun"]["staticBuyableOfferCount"])
        self.assertEqual("location_policy_required", rows["gun"]["policyStatus"])

    def test_rejects_unknown_market_good(self):
        report = {
            "schemaVersion": 1,
            "goods": [{"goodId": "known", "category": "equipment"}],
            "unlistedGoodIds": [],
            "markets": [{"marketId": "base", "systemIds": ["li01"], "entries": [{"goodId": "missing"}]}],
        }
        with self.assertRaisesRegex(ValueError, "unknown good"):
            reviewer.build_review(json.dumps(report).encode())


if __name__ == "__main__":
    unittest.main()
