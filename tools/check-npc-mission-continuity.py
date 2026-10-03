#!/usr/bin/env python3
"""Check an idle mission timer fixture against its frozen handoff and target ticks."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys
import uuid

spec = importlib.util.spec_from_file_location('npc_state', Path(__file__).with_name('compare-npc-state.py'))
state_reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state_reader)


def compare(frozen, sample, instance, spawn_tick, tick_rate=60):
    if len(frozen) != 1:
        raise ValueError('Exactly one frozen snapshot report required')
    frozen = frozen[0]
    transfer = uuid.UUID(frozen['TransferId'])
    if transfer.int == 0 or transfer != uuid.UUID(frozen['MissionRuntimeId']):
        raise ValueError('Mission and transfer identities must match')
    if sample['InstanceId'] != instance or type(spawn_tick) is not int or spawn_tick < 0 or sample['CurrentTick'] < spawn_tick:
        raise ValueError('Expected instance and increasing target simulation ticks required')
    if not math.isfinite(tick_rate) or tick_rate <= 0:
        raise ValueError('Positive finite tick rate required')
    elapsed = (sample['CurrentTick'] - spawn_tick) / tick_rate
    live = {n['NpcId']: n for n in sample['Npcs']}
    seen = set()
    rows = []
    mission = frozen['Mission']
    for npc in frozen['Npcs']:
        identity = str(uuid.UUID(npc['NpcId']))
        if identity in seen or uuid.UUID(identity).int == 0:
            raise ValueError('Duplicate or empty frozen NPC identity')
        seen.add(identity)
        target = live.get(identity)
        if target is None or target['OwnershipVersion'] != npc['OwnershipVersion'] + 1:
            raise ValueError('Missing target NPC or mismatched ownership fence')
        if target['SystemId'].lower() != frozen['TargetSystemId'].lower():
            raise ValueError('Target NPC is in another system')
        current = target['MissionState']
        for field in ['MissionNickname', 'RandomState', 'LastSaveTrigger', 'ActiveObjective',
                      'Labels', 'GeneratedMission', 'PendingLines', 'CompletedTriggers', 'SchemaVersion']:
            if mission[field] != current[field]:
                raise ValueError('Mission fixture state changed: ' + field)
        old = {t['Nickname']: t for t in mission['ActiveTriggers']}
        new = {t['Nickname']: t for t in current['ActiveTriggers']}
        if len(old) != len(mission['ActiveTriggers']) or len(new) != len(current['ActiveTriggers']) or old.keys() != new.keys() or not old:
            raise ValueError('Active fixture trigger set changed or is empty')
        timers = []
        for name, trigger in old.items():
            actual = new[name]
            for field in ['Deactivated', 'Satisfied', 'Conditions']:
                if trigger[field] != actual[field]:
                    raise ValueError('Fixture condition state changed: ' + field)
            expected = trigger['ActiveSeconds'] + elapsed
            difference = actual['ActiveSeconds'] - expected
            if not math.isfinite(difference) or abs(difference) > 0.05:
                raise ValueError('Mission timer did not resume from its frozen value')
            timers.append({'Nickname': name, 'FrozenSeconds': trigger['ActiveSeconds'],
                           'ExpectedSeconds': expected, 'ActualSeconds': actual['ActiveSeconds'],
                           'DifferenceSeconds': difference})
        rows.append({'NpcId': identity, 'OwnershipVersion': target['OwnershipVersion'], 'Timers': timers})
    if not rows:
        raise ValueError('No frozen mission NPCs')
    return {'TransferId': str(transfer), 'InstanceId': instance, 'SpawnTick': spawn_tick,
            'CaptureTick': sample['CurrentTick'], 'NpcChecks': rows,
            'Scope': 'Idle mission fixture without intervening mission actions; tick, fence and snapshot continuity only.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frozen', type=Path, help='NpcTransferDiagnostics snapshot --json output')
    parser.add_argument('sample', type=Path, help='Target npc-state capture or log')
    parser.add_argument('--instance', required=True)
    parser.add_argument('--spawn-tick', required=True, type=int, help='Target SpawnPlayer tick from Debug client log')
    args = parser.parse_args()
    try:
        result = compare(json.loads(args.frozen.read_text()), state_reader.read_sample(args.sample), args.instance, args.spawn_tick)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print('Mission continuity rejected: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
