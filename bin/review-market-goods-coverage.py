#!/usr/bin/env python3
"""Build a report-pinned inventory for every good in the dynamic-market scope."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def build_review(report_bytes):
    report = json.loads(report_bytes)
    if report.get("schemaVersion") != 1:
        raise ValueError("Unsupported market catalog report schema")

    goods = report.get("goods")
    markets = report.get("markets")
    unlisted = report.get("unlistedGoodIds")
    if not isinstance(goods, list) or not isinstance(markets, list) or not isinstance(unlisted, list):
        raise ValueError("Market catalog report is missing goods, markets or unlistedGoodIds")

    by_id = {}
    for good in goods:
        good_id = good.get("goodId") if isinstance(good, dict) else None
        if not isinstance(good_id, str) or not good_id or good_id in by_id:
            raise ValueError("Market catalog contains an invalid or duplicate goodId")
        by_id[good_id] = good
    if any(not isinstance(good_id, str) for good_id in unlisted) or len(set(unlisted)) != len(unlisted):
        raise ValueError("unlistedGoodIds contains invalid or duplicate IDs")
    if not set(unlisted).issubset(by_id):
        raise ValueError("unlistedGoodIds references an unknown good")

    packages = {}
    offers = {}
    for market in markets:
        market_id = market.get("marketId")
        if not isinstance(market_id, str) or not market_id:
            raise ValueError("Market catalog contains an invalid marketId")
        system_ids = market.get("systemIds", [])
        if not isinstance(system_ids, list) or any(not isinstance(item, str) for item in system_ids):
            raise ValueError(f"Market '{market_id}' has invalid systemIds")
        for offer in market.get("entries", []):
            good_id = offer.get("goodId") if isinstance(offer, dict) else None
            if good_id not in by_id:
                raise ValueError(f"Market '{market_id}' references an unknown good")
            offers.setdefault(good_id, []).append({
                "marketId": market_id,
                "systemIds": system_ids,
                "staticBuyable": bool(offer.get("forSale")),
                "priceResolution": offer.get("priceResolution"),
                "baselineUnitPrice": offer.get("baselineUnitPrice"),
                "legacyPackagePrice": offer.get("legacyPackagePrice"),
                "source": offer.get("source"),
            })
        for good in goods:
            if good.get("category") != "ship":
                continue
            package_id = good["goodId"]
            hull_id = good.get("hullGoodId")
            if hull_id:
                packages.setdefault(hull_id, []).append({"packageId": package_id, "role": "hull"})
            for addon in good.get("addons", []):
                equipment_id = addon.get("equipmentId") if isinstance(addon, dict) else None
                if equipment_id:
                    packages.setdefault(equipment_id, []).append({
                        "packageId": package_id,
                        "role": "addon",
                        "amount": addon.get("amount"),
                        "hardpoint": addon.get("hardpoint"),
                    })

    rows = []
    unlisted_set = set(unlisted)
    for good_id in sorted(by_id):
        good = by_id[good_id]
        category = good.get("category", "")
        source = good.get("source", "")
        references = sorted(packages.get(good_id, []), key=lambda item: (item["packageId"], item["role"]))
        if category == "ship":
            trade_class = "ship_package_bundle"
            booking_path = "atomic_bundle_required"
        elif category == "shiphull":
            trade_class = "package_hull_component" if references else "standalone_ship_hull"
            booking_path = "atomic_bundle_required" if references else "needs_standalone_hull_review"
        elif category == "commodity":
            trade_class = "commodity"
            booking_path = "single_good_trade"
        elif category == "equipment" and references:
            trade_class = "package_addon_or_equipment"
            booking_path = "single_good_trade_or_atomic_bundle"
        elif category == "equipment" and source == "weapon_good.ini":
            trade_class = "weapon"
            booking_path = "single_good_trade"
        elif category == "equipment" and source == "st_good.ini":
            trade_class = "special_equipment"
            booking_path = "single_good_trade"
        elif category == "equipment":
            trade_class = "equipment"
            booking_path = "single_good_trade"
        else:
            trade_class = "manual_classification_required"
            booking_path = "manual_review_required"

        good_offers = sorted(offers.get(good_id, []), key=lambda item: item["marketId"])
        rows.append({
            "goodId": good_id,
            "category": category,
            "definitionSource": source,
            "legacyPrice": good.get("price"),
            "dynamicScope": "included",
            "tradeClass": trade_class,
            "bookingPath": booking_path,
            "packageReferences": references,
            "staticOfferCount": len(good_offers),
            "staticBuyableOfferCount": sum(1 for offer in good_offers if offer["staticBuyable"]),
            "staticOffers": good_offers,
            "wasUnlisted": good_id in unlisted_set,
            "policyStatus": "location_policy_required",
        })

    class_counts = dict(sorted(Counter(row["tradeClass"] for row in rows).items()))
    return {
        "schemaVersion": 1,
        "catalogReportSha256": hashlib.sha256(report_bytes).hexdigest(),
        "catalogReportSchemaVersion": report["schemaVersion"],
        "goodsCount": len(rows),
        "unlistedGoodCount": len(unlisted_set),
        "staticOfferPairCount": sum(row["staticOfferCount"] for row in rows),
        "staticBuyableOfferPairCount": sum(row["staticBuyableOfferCount"] for row in rows),
        "tradeClassCounts": class_counts,
        "dynamicScopeRule": "Every catalog good is in scope; location policies alone authorize player offers.",
        "activationRule": "This inventory grants no market access. A reviewed, versioned policy is required per marketId/goodId.",
        "goods": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="market catalog JSON generated by analyze-market-catalog.py")
    parser.add_argument("--output", type=Path, required=True, help="review JSON output path")
    args = parser.parse_args()
    review = build_review(args.report.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {review['goodsCount']} goods and {review['staticOfferPairCount']} static offer pairs; no market policy was activated.")


if __name__ == "__main__":
    main()
