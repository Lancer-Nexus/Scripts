#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "analyze-unlisted-market-usage.py"
spec = importlib.util.spec_from_file_location("analyze_unlisted_market_usage", SCRIPT)
analyzer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyzer)


class UnlistedMarketUsageTests(unittest.TestCase):
    def test_counts_exact_whole_id_references_and_excludes_good_definitions(self):
        review = {
            "schemaVersion": 1,
            "goods": [
                {"goodId": "gun_a", "reviewClass": "unlisted_weapon"},
                {"goodId": "gun_a_long", "reviewClass": "unlisted_weapon"},
                {"goodId": "unused_good", "reviewClass": "other_equipment"},
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "EQUIPMENT").mkdir()
            (root / "SHIPS").mkdir()
            (root / "EQUIPMENT" / "weapon_good.ini").write_text("gun_a = 1\n", encoding="utf-8")
            (root / "SHIPS" / "loadouts.ini").write_text(
                "nickname = gun_a\nnickname = gun_a_long\nnickname = notgun_a\n",
                encoding="utf-8",
            )
            result = analyzer.build_usage_report(json.dumps(review).encode(), root)

        goods = {item["goodId"]: item for item in result["goods"]}
        self.assertEqual(1, goods["gun_a"]["externalReferenceCount"])
        self.assertEqual(1, goods["gun_a"]["externalReferenceFileCount"])
        self.assertEqual({"ships": 1}, goods["gun_a"]["assetGroupCounts"])
        self.assertEqual(1, goods["gun_a_long"]["externalReferenceCount"])
        self.assertEqual(2, result["totals"]["withExternalReferences"])
        self.assertEqual(1, result["totals"]["withoutExternalReferences"])
        self.assertEqual(2, result["sourceTextFileCount"])

    def test_rejects_duplicate_case_insensitive_ids(self):
        review = {"schemaVersion": 1, "goods": [{"goodId": "Gun_A"}, {"goodId": "gun_a"}]}
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "duplicate goodId"):
                analyzer.build_usage_report(json.dumps(review).encode(), Path(temporary))


if __name__ == "__main__":
    unittest.main()
