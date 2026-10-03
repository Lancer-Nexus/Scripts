#!/usr/bin/env python3
"""Compare read-only Debug LLServer npc-state samples without touching live state."""

import argparse
import json
import math
from pathlib import Path
import sys
import uuid


def read_sample(path: Path) -> dict:
    lines = path.read_text().splitlines()
    records = [line.split("NPC_STATE ", 1)[1] for line in lines if "NPC_STATE " in line]
    sample = json.loads(records[-1] if records else "\n".join(lines))
    if not isinstance(sample.get("InstanceId"), str) or not sample["InstanceId"]:
        raise ValueError("Missing instance identity")
    if type(sample.get("CurrentTick")) is not int or sample["CurrentTick"] < 0:
        raise ValueError("Invalid simulation tick")
    seen = set()
    for npc in sample["Npcs"]:
        identity = str(uuid.UUID(npc["NpcId"]))
        if identity == str(uuid.UUID(int=0)) or identity in seen:
            raise ValueError("Empty or duplicate NPC identity in one sample")
        seen.add(identity)
        npc["NpcId"] = identity
        if type(npc["OwnershipVersion"]) is not int or npc["OwnershipVersion"] <= 0:
            raise ValueError("Invalid ownership version")
        for axis in "XYZ":
            value = npc["Position"][axis]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Invalid NPC position")
    return sample


def compare_copies(samples: list[dict], ids: list[str]) -> tuple[dict, bool]:
    if len({sample["InstanceId"] for sample in samples}) != len(samples):
        raise ValueError("Copy comparison requires different instances")
    copies = {}
    for sample in samples:
        for npc in sample["Npcs"]:
            copies.setdefault(npc["NpcId"], []).append({
                "InstanceId": sample["InstanceId"], "OwnershipVersion": npc["OwnershipVersion"]
            })
    selected = ids or sorted(copies)
    counts = {identity: len(copies.get(identity, [])) for identity in selected}
    conflicts = {identity: copies[identity] for identity in selected if counts[identity] > 1}
    return {"ActiveCopyCounts": counts, "Conflicts": conflicts}, bool(counts) and all(count == 1 for count in counts.values())


def compare_movement(first: dict, second: dict, ids: list[str]) -> tuple[dict, bool]:
    if first["InstanceId"] != second["InstanceId"] or second["CurrentTick"] <= first["CurrentTick"]:
        raise ValueError("Movement comparison requires increasing ticks from the same instance")
    old = {npc["NpcId"]: npc for npc in first["Npcs"]}
    new = {npc["NpcId"]: npc for npc in second["Npcs"]}
    selected = ids or sorted(old.keys() & new.keys())
    distances = {}
    for identity in selected:
        if identity not in old or identity not in new:
            raise ValueError("Requested NPC is missing from a movement sample")
        if old[identity]["OwnershipVersion"] != new[identity]["OwnershipVersion"]:
            raise ValueError("Ownership changed between movement samples")
        distances[identity] = math.dist(
            [old[identity]["Position"][axis] for axis in "XYZ"],
            [new[identity]["Position"][axis] for axis in "XYZ"])
    return {"InstanceId": first["InstanceId"], "DistanceMoved": distances}, bool(distances) and all(
        distance > 0.01 for distance in distances.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples", nargs=2, type=Path)
    parser.add_argument("--npc", action="append", default=[], help="Stable NPC UUID; repeat for a group")
    parser.add_argument("--movement", action="store_true", help="Compare consecutive samples from one instance")
    args = parser.parse_args()
    try:
        samples = [read_sample(path) for path in args.samples]
        ids = [str(uuid.UUID(identity)) for identity in args.npc]
        result, accepted = (compare_movement(*samples, ids) if args.movement else compare_copies(samples, ids))
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0 if accepted else 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Invalid diagnostic sample: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
