#!/usr/bin/env python3
"""Report Freelancer goods and market coverage against the Nexus system inventory."""

import argparse
import json
from pathlib import Path
import re
import sys


def child(parent, name):
    matches = [path for path in parent.iterdir() if path.name.lower() == name.lower()]
    if len(matches) != 1:
        raise ValueError(f"Missing or ambiguous asset path: {parent / name}")
    return matches[0]


def parse_ini(path):
    """Keep repeated sections and entries; Freelancer INIs are not ConfigParser files."""
    sections = []
    current = None
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        section_match = re.fullmatch(r"\[([^]]+)\]", line)
        if section_match:
            current = {"name": section_match.group(1).strip().lower(), "entries": [], "line": line_number}
            sections.append(current)
            continue
        if "=" in line:
            if current is None:
                raise ValueError(f"Entry before section in {path}:{line_number}")
            key, value = line.split("=", 1)
            current["entries"].append((key.strip().lower(), value.strip()))
    return sections


def values(section, key):
    return [value for name, value in section["entries"] if name == key.lower()]


def one(section, key, path):
    found = values(section, key)
    if len(found) != 1 or not found[0]:
        raise ValueError(f"Expected one {key} entry in {path}:{section['line']}")
    return found[0]


def safe_asset(root, relative):
    parts = relative.replace("\\", "/").split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Unsafe Freelancer data path: {relative}")
    path = root
    for part in parts:
        path = child(path, part)
    if not path.is_file():
        raise ValueError(f"Expected a file: {path}")
    return path


def configured_directory(base, relative, boundary):
    path = base
    for part in relative.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            path = path.parent
        else:
            path = child(path, part)
        try:
            path.relative_to(boundary)
        except ValueError as error:
            raise ValueError(f"Configured directory escapes game root: {relative}") from error
    return path


def load_data_paths(game):
    exe = child(game, "exe")
    freelancer_ini = child(exe, "freelancer.ini")
    sections = parse_ini(freelancer_ini)
    freelancer = next((s for s in sections if s["name"] == "freelancer"), None)
    data_section = next((s for s in sections if s["name"] == "data"), None)
    if freelancer is None or data_section is None:
        raise ValueError(f"Missing [Freelancer] or [Data] in {freelancer_ini}")
    data_path = configured_directory(exe, one(freelancer, "data path", freelancer_ini), game)
    if not data_path.is_dir():
        raise ValueError(f"Freelancer data path does not exist: {data_path}")
    goods = [safe_asset(data_path, value) for value in values(data_section, "goods")]
    markets = [safe_asset(data_path, value) for value in values(data_section, "markets")]
    universe_value = one(data_section, "universe", freelancer_ini)
    universe_ini = safe_asset(data_path, universe_value)
    if not goods or not markets:
        raise ValueError(f"No goods or markets configured in {freelancer_ini}")
    return data_path, goods, markets, universe_ini


def baseline_systems(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1 or not isinstance(data.get("instances"), list):
        raise ValueError(f"Unsupported Nexus baseline: {path}")
    result = {}
    for instance in data["instances"]:
        instance_id = instance.get("instanceId")
        systems = instance.get("systems")
        if not instance_id or not isinstance(systems, list):
            raise ValueError(f"Invalid instance entry in {path}")
        for system_id in systems:
            normalized = system_id.lower()
            if normalized in result:
                raise ValueError(f"System assigned more than once in {path}: {system_id}")
            result[normalized] = instance_id
    if not result:
        raise ValueError(f"Nexus baseline has no systems: {path}")
    return result


def universe_system_files(universe_ini):
    universe_root = universe_ini.parent
    systems = {}
    for section in parse_ini(universe_ini):
        if section["name"] != "system":
            continue
        nickname = one(section, "nickname", universe_ini).lower()
        filename = one(section, "file", universe_ini)
        system_file = safe_asset(universe_root, filename)
        if nickname in systems:
            raise ValueError(f"Duplicate system nickname in {universe_ini}: {nickname}")
        systems[nickname] = system_file
    if not systems:
        raise ValueError(f"No [System] entries found in {universe_ini}")
    return systems


def universe_base_directories(universe_ini):
    universe_root = universe_ini.parent
    result = {}
    for section in parse_ini(universe_ini):
        if section["name"] != "base":
            continue
        base_id = one(section, "nickname", universe_ini).lower()
        filename = one(section, "file", universe_ini)
        parts_from_data = filename.replace("\\", "/").split("/")
        base_file = (safe_asset(universe_root.parent, filename)
                     if parts_from_data[0].lower() == "universe"
                     else safe_asset(universe_root, filename))
        parts = [part.lower() for part in base_file.relative_to(universe_root).parts]
        if len(parts) < 3 or parts[0] != "systems":
            raise ValueError(f"Base file is outside SYSTEMS/<asset> in {universe_ini}:{section['line']}")
        if base_id in result:
            raise ValueError(f"Duplicate base nickname in {universe_ini}: {base_id}")
        system_ids = values(section, "system")
        result[base_id] = {
            "assetDirectory": parts[1],
            "systemId": system_ids[0].lower() if len(system_ids) == 1 and system_ids[0] else None,
            "file": base_file,
        }
    return result


def mission_created_bases(universe_ini):
    mission_file = universe_ini.parent / "missioncreatedsolars.ini"
    if not mission_file.is_file():
        return set()
    return {value.lower() for section in parse_ini(mission_file)
            if section["name"] == "missioncreatedsolar" for value in values(section, "base")}


def add_good_catalog(paths):
    goods = {}
    duplicate_ids = []
    for path in paths:
        for section in parse_ini(path):
            if section["name"] != "good":
                continue
            nickname = one(section, "nickname", path).lower()
            definition = {
                "goodId": nickname,
                "category": (values(section, "category") or [""])[0].lower(),
                "price": (values(section, "price") or [""])[0],
                "source": path.name,
            }
            if nickname in goods:
                duplicate_ids.append(nickname)
            else:
                goods[nickname] = definition
    return goods, sorted(set(duplicate_ids))


def add_market_catalog(paths):
    markets = {}
    entry_count = 0
    malformed = []
    for path in paths:
        for section in parse_ini(path):
            if section["name"] != "basegood":
                continue
            market_id = one(section, "base", path).lower()
            market = markets.setdefault(market_id, {"marketId": market_id, "entries": []})
            for raw in values(section, "marketgood"):
                entry_count += 1
                fields = [part.strip() for part in raw.split(",")]
                if len(fields) < 7 or not fields[0]:
                    malformed.append(f"{path.name}:{section['line']}")
                    continue
                try:
                    minimum = int(fields[3])
                    maximum = int(fields[4])
                    rank = int(fields[1])
                    rep = float(fields[2])
                    preserve = int(fields[5])
                    multiplier = float(fields[6])
                except ValueError:
                    malformed.append(f"{path.name}:{section['line']}")
                    continue
                market["entries"].append({
                    "goodId": fields[0].lower(),
                    "rank": rank,
                    "reputationThreshold": rep,
                    "min": minimum,
                    "max": maximum,
                    "forSale": maximum > 0,
                    "preserve": preserve > 0,
                    "multiplier": multiplier,
                    "source": path.name,
                })
    return markets, entry_count, malformed


def analyze(game, baseline_path):
    _, goods_paths, market_paths, universe_ini = load_data_paths(game.resolve())
    instance_by_system = baseline_systems(baseline_path)
    source_system_files = universe_system_files(universe_ini)
    universe_base_dirs = universe_base_directories(universe_ini)
    missing_worlds = sorted(set(instance_by_system) - set(source_system_files))
    if missing_worlds:
        raise ValueError(f"Nexus systems missing from Freelancer universe: {', '.join(missing_worlds)}")

    goods, duplicate_ids = add_good_catalog(goods_paths)
    markets, market_entry_count, malformed_entries = add_market_catalog(market_paths)
    unknown_goods = sorted({entry["goodId"] for market in markets.values() for entry in market["entries"]
                            if entry["goodId"] not in goods})

    universe_root = universe_ini.parent
    systems_by_asset_directory = {}
    all_system_asset_directories = set()
    for system_id, path in source_system_files.items():
        parts = [part.lower() for part in path.relative_to(universe_root).parts]
        if len(parts) < 3 or parts[0] != "systems":
            raise ValueError(f"System file is outside SYSTEMS/<asset>: {path}")
        asset_directory = parts[1]
        all_system_asset_directories.add(asset_directory)
        systems_by_asset_directory.setdefault(asset_directory, set()).add(system_id)

    market_ids_by_system = {system_id: set() for system_id in source_system_files}
    docked_systems_by_base = {}
    for system_id, path in source_system_files.items():
        for section in parse_ini(path):
            for base_id in values(section, "dock_with"):
                normalized = base_id.lower()
                docked_systems_by_base.setdefault(normalized, set()).add(system_id)

    mission_bases = mission_created_bases(universe_ini)
    missing_base_definitions = sorted(market_id for market_id, market in markets.items()
                                      if market["entries"] and market_id not in universe_base_dirs)
    market_systems = {}
    for market_id, market in markets.items():
        base = universe_base_dirs.get(market_id)
        asset_directory = base["assetDirectory"] if base else None
        declared_system = base["systemId"] if base else None
        systems = ({declared_system} if declared_system else
                   set(systems_by_asset_directory.get(asset_directory, set())) if asset_directory else set())
        market_systems[market_id] = systems
        if market["entries"]:
            for system_id in systems:
                market_ids_by_system[system_id].add(market_id)

    system_rows = []
    for system_id, instance_id in sorted(instance_by_system.items()):
        market_ids = sorted(market_ids_by_system[system_id])
        entries = [entry for market_id in market_ids for entry in markets[market_id]["entries"]]
        system_rows.append({
            "systemId": system_id,
            "instanceId": instance_id,
            "marketIds": market_ids,
            "marketEntryCount": len(entries),
            "uniqueGoodCount": len({entry["goodId"] for entry in entries}),
            "buyableGoodCount": len({entry["goodId"] for entry in entries if entry["forSale"]}),
        })

    market_rows = []
    for market_id, market in sorted(markets.items()):
        entries = market["entries"]
        base = universe_base_dirs.get(market_id)
        asset_directory = base["assetDirectory"] if base else None
        systems = sorted(market_systems[market_id])
        nexus_systems = [system_id for system_id in systems if system_id in instance_by_system]
        mapping_kind = ("nexus_system" if nexus_systems else
                        "outside_nexus_system" if systems else
                        "non_world_asset" if asset_directory in non_world_asset_directories else
                        "unresolved")
        market_rows.append({
            "marketId": market_id,
            "assetDirectory": asset_directory,
            "declaredSystemId": base["systemId"] if base else None,
            "mappingSource": ("universe_base_system" if base and base["systemId"] else
                              "base_asset_directory" if base else "unresolved"),
            "mappingKind": mapping_kind,
            "systemIds": systems,
            "dockedSystemIds": sorted(docked_systems_by_base.get(market_id, set())),
            "missionCreatedSolar": market_id in mission_bases,
            "instanceIds": sorted({instance_by_system[s] for s in systems if s in instance_by_system}),
            "entryCount": len(entries),
            "uniqueGoodCount": len({entry["goodId"] for entry in entries}),
            "buyableGoodCount": len({entry["goodId"] for entry in entries if entry["forSale"]}),
            "entries": sorted(entries, key=lambda e: (e["goodId"], e["source"], e["rank"])),
        })

    listed_goods = {entry["goodId"] for market in markets.values() for entry in market["entries"]}
    goods_by_category = {}
    for definition in goods.values():
        category = definition["category"] or "unspecified"
        goods_by_category[category] = goods_by_category.get(category, 0) + 1
    unmapped_markets = missing_base_definitions
    system_asset_root = child(universe_root, "systems")
    non_world_asset_directories = sorted(
        {path.name.lower() for path in system_asset_root.iterdir() if path.is_dir()} -
        all_system_asset_directories)
    markets_using_non_world_asset_files = sorted(
        market_id for market_id, market in markets.items()
        if market["entries"] and universe_base_dirs.get(market_id, {}).get("assetDirectory")
        in non_world_asset_directories)
    non_world_markets = sorted(
        market_id for market_id, market in markets.items()
        if market["entries"] and not market_systems[market_id] and
        universe_base_dirs.get(market_id, {}).get("assetDirectory") in non_world_asset_directories)
    canonical_market_systems = {row["systemId"] for row in system_rows if row["marketIds"]}
    unassigned_systems = sorted(set(source_system_files) - set(instance_by_system))
    report = {
        "schemaVersion": 1,
        "sources": {
            "freelancerIni": "EXE/Freelancer.ini",
            "goodsFiles": [path.name for path in goods_paths],
            "marketFiles": [path.name for path in market_paths],
            "universeFile": universe_ini.name,
            "baselineFile": baseline_path.name,
        },
        "summary": {
            "goodDefinitionCount": len(goods),
            "goodsByCategory": dict(sorted(goods_by_category.items())),
            "marketEntryCount": market_entry_count,
            "uniqueMarketGoodCount": len(listed_goods),
            "uniqueBuyableGoodCount": len({entry["goodId"] for market in markets.values()
                                             for entry in market["entries"] if entry["forSale"]}),
            "unlistedGoodCount": len(set(goods) - listed_goods),
            "marketIdCount": len(markets),
            "marketIdsWithEntries": sum(bool(market["entries"]) for market in markets.values()),
            "marketIdsWithBuyableGoods": sum(any(entry["forSale"] for entry in market["entries"])
                                              for market in markets.values()),
            "marketIdsMappedToNexusSystems": sum(
                bool(market["entries"]) and any(system_id in instance_by_system
                                                  for system_id in market_systems[market_id])
                for market_id, market in markets.items()),
            "marketIdsUsingNonWorldAssetFiles": len(markets_using_non_world_asset_files),
            "marketIdsWithNoSystemMapping": sum(bool(market["entries"]) and not market_systems[market_id]
                                                 for market_id, market in markets.items()),
            "universeSystemCount": len(source_system_files),
            "nexusSystemCount": len(instance_by_system),
            "nexusSystemsWithMarkets": len(canonical_market_systems),
            "nexusSystemsWithoutMarkets": len(instance_by_system) - len(canonical_market_systems),
            "unknownMarketGoodCount": len(unknown_goods),
            "duplicateGoodIdCount": len(duplicate_ids),
            "malformedMarketEntryCount": len(malformed_entries),
            "unmappedMarketIdCount": len(unmapped_markets),
            "marketsOutsideNexusSystems": sum(
                bool(market["entries"]) and bool(market_systems[market_id]) and
                not any(system_id in instance_by_system for system_id in market_systems[market_id])
                for market_id, market in markets.items()),
            "unassignedUniverseSystemCount": len(unassigned_systems),
        },
        "goods": [goods[key] for key in sorted(goods)],
        "unlistedGoodIds": sorted(set(goods) - listed_goods),
        "unknownMarketGoodIds": unknown_goods,
        "duplicateGoodIds": duplicate_ids,
        "malformedMarketEntries": malformed_entries,
        "unmappedMarketIds": unmapped_markets,
        "marketsOutsideNexusSystems": sorted(
            market_id for market_id, market in markets.items()
            if market["entries"] and market_systems[market_id] and
            not any(system_id in instance_by_system for system_id in market_systems[market_id])),
        "nonWorldMarkets": non_world_markets,
        "marketsUsingNonWorldAssetFiles": markets_using_non_world_asset_files,
        "missingBaseDefinitions": unmapped_markets,
        "unassignedUniverseSystemIds": unassigned_systems,
        "systems": system_rows,
        "markets": market_rows,
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True,
                        help="Freelancer installation root containing EXE/Freelancer.ini and DATA")
    parser.add_argument("--baseline", type=Path,
                        default=Path(__file__).resolve().parents[1] / "config" / "nexus-baseline.json")
    parser.add_argument("--output", type=Path, help="Write the JSON report here; stdout is the default")
    args = parser.parse_args()
    try:
        report = analyze(args.game, args.baseline)
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        if any(report["summary"][key] for key in (
                "unknownMarketGoodCount", "duplicateGoodIdCount", "malformedMarketEntryCount",
                "unmappedMarketIdCount", "marketsOutsideNexusSystems", "unassignedUniverseSystemCount")):
            return 1
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(2, f"Market analysis failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
