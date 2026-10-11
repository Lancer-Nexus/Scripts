#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "review-unlisted-market-goods.py"
spec = importlib.util.spec_from_file_location("review_unlisted_market_goods", SCRIPT)
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


def good(good_id, category, source="goods.ini", **extra):
    return {"goodId": good_id, "category": category, "source": source, "price": "10", **extra}


class UnlistedMarketGoodsTests(unittest.TestCase):
    def test_classifies_package_hulls_addons_and_nonmarket_goods(self):
        report = {
            "schemaVersion": 1,
            "goods": [
                good("hull_a", "shiphull"),
                good("hull_story", "shiphull"),
                good("shield_a", "equipment", "st_good.ini"),
                good("gun_a", "equipment", "weapon_good.ini"),
                good("cargo_a", "commodity"),
                good("package_a", "ship", hullGoodId="hull_a", addons=[{
                    "equipmentId": "shield_a", "amount": 1, "hardpoint": "HpShield01"
                }]),
            ],
            "unlistedGoodIds": ["hull_a", "hull_story", "shield_a", "gun_a", "cargo_a"],
        }
        result = reviewer.build_review(json.dumps(report).encode())
        rows = {row["goodId"]: row for row in result["goods"]}
        self.assertEqual("ship_hull_component", rows["hull_a"]["reviewClass"])
        self.assertEqual("package_a", rows["hull_a"]["packageReferences"][0]["packageId"])
        self.assertEqual("unreferenced_ship_hull", rows["hull_story"]["reviewClass"])
        self.assertEqual("ship_package_addon", rows["shield_a"]["reviewClass"])
        self.assertEqual("unlisted_weapon", rows["gun_a"]["reviewClass"])
        self.assertEqual("unlisted_commodity", rows["cargo_a"]["reviewClass"])
        self.assertTrue(all(row["marketPolicyStatus"] == "disabled_until_explicit_review" for row in rows.values()))

    def test_rejects_unknown_unlisted_good(self):
        report = {"schemaVersion": 1, "goods": [good("known", "equipment")], "unlistedGoodIds": ["missing"]}
        with self.assertRaisesRegex(ValueError, "unknown good"):
            reviewer.build_review(json.dumps(report).encode())

    def test_rejects_duplicate_catalog_ids(self):
        report = {
            "schemaVersion": 1,
            "goods": [good("duplicate", "equipment"), good("duplicate", "commodity")],
            "unlistedGoodIds": [],
        }
        with self.assertRaisesRegex(ValueError, "duplicate goodId"):
            reviewer.build_review(json.dumps(report).encode())

    def test_rejects_duplicate_unlisted_ids(self):
        report = {"schemaVersion": 1, "goods": [good("known", "equipment")], "unlistedGoodIds": ["known", "known"]}
        with self.assertRaisesRegex(ValueError, "duplicate IDs"):
            reviewer.build_review(json.dumps(report).encode())


if __name__ == "__main__":
    unittest.main()
