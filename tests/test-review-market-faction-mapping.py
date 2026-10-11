#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "review-market-faction-mapping.py"
spec = importlib.util.spec_from_file_location("review_market_faction_mapping", SCRIPT)
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


class MarketFactionMappingTests(unittest.TestCase):
    def test_reports_faction_mismatches_without_authorizing_offers(self):
        report = {
            "schemaVersion": 1,
            "markets": [
                {"marketId": "base_a", "systemIds": ["li01"], "localFactionId": "li_p_grp",
                 "baseFactionIds": [], "entryCount": 38, "buyableGoodCount": 0},
                {"marketId": "base_b", "systemIds": ["ku01"], "localFactionId": "ku_p_grp",
                 "baseFactionIds": ["ku_p_grp"], "entryCount": 12, "buyableGoodCount": 12},
                {"marketId": "base_c", "systemIds": ["li02"], "localFactionId": "li_n_grp",
                 "baseFactionIds": ["li_p_grp"], "entryCount": 0, "buyableGoodCount": 0},
            ],
        }
        result = reviewer.build_review(json.dumps(report).encode())
        self.assertEqual(3, result["summary"]["marketCount"])
        self.assertEqual(2, result["summary"]["localFactionOutsideBaseFactionCount"])
        self.assertEqual(1, result["summary"]["mismatchedMarketsWithStaticMarketEntriesCount"])
        self.assertEqual(0, result["summary"]["mismatchedMarketsWithBuyableGoodsCount"])
        self.assertEqual("MBase.local_faction", result["interpretation"]["marketFactionSource"])
        self.assertFalse(result["interpretation"]["mismatchAuthorizesOffers"])

    def test_rejects_duplicate_market_ids(self):
        market = {"marketId": "same", "systemIds": [], "localFactionId": "faction",
                  "baseFactionIds": [], "entryCount": 0, "buyableGoodCount": 0}
        with self.assertRaisesRegex(ValueError, "duplicate marketId"):
            reviewer.build_review(json.dumps({"schemaVersion": 1, "markets": [market, market]}).encode())

    def test_rejects_missing_local_faction(self):
        market = {"marketId": "base", "systemIds": [], "localFactionId": "",
                  "baseFactionIds": [], "entryCount": 0}
        with self.assertRaisesRegex(ValueError, "no localFactionId"):
            reviewer.build_review(json.dumps({"schemaVersion": 1, "markets": [market]}).encode())


if __name__ == "__main__":
    unittest.main()
