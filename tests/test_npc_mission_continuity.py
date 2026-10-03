import copy
import importlib.util
from pathlib import Path
import unittest
import uuid

spec = importlib.util.spec_from_file_location('continuity', Path(__file__).parents[1] / 'tools/check-npc-mission-continuity.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MissionContinuityTests(unittest.TestCase):
    def fixture(self):
        identity = str(uuid.uuid4())
        transfer = str(uuid.uuid4())
        mission = dict(MissionNickname='fixture', RandomState=123, LastSaveTrigger='', ActiveObjective=None,
                       Labels=[], GeneratedMission=None, PendingLines=[], CompletedTriggers=[], SchemaVersion=4,
                       ActiveTriggers=[dict(Nickname='timer', ActiveSeconds=10, Conditions=[], Deactivated=False, Satisfied='')])
        frozen = [dict(TransferId=transfer, MissionRuntimeId=transfer, TargetSystemId='li03', Mission=mission,
                       Npcs=[dict(NpcId=identity, OwnershipVersion=1)])]
        current = copy.deepcopy(mission)
        current['ActiveTriggers'][0]['ActiveSeconds'] = 12
        sample = dict(InstanceId='li02', CurrentTick=180,
                      Npcs=[dict(NpcId=identity, OwnershipVersion=2, SystemId='Li03', MissionState=current)])
        return frozen, sample

    def test_resumes_frozen_time_with_target_ticks(self):
        frozen, sample = self.fixture()
        result = module.compare(frozen, sample, 'li02', 60)
        self.assertEqual(0, result['NpcChecks'][0]['Timers'][0]['DifferenceSeconds'])

    def test_reset_timer_and_changed_fence_or_context_are_rejected(self):
        for field, value in [('timer', 2), ('OwnershipVersion', 1), ('RandomState', 999), ('SystemId', 'li01')]:
            with self.subTest(field=field):
                frozen, sample = self.fixture()
                npc = sample['Npcs'][0]
                if field == 'timer':
                    npc['MissionState']['ActiveTriggers'][0]['ActiveSeconds'] = value
                elif field == 'RandomState':
                    npc['MissionState'][field] = value
                else:
                    npc[field] = value
                with self.assertRaises(ValueError):
                    module.compare(frozen, sample, 'li02', 60)

    def test_mismatched_transfer_and_missing_npc_are_rejected(self):
        frozen, sample = self.fixture()
        frozen[0]['MissionRuntimeId'] = str(uuid.uuid4())
        with self.assertRaises(ValueError):
            module.compare(frozen, sample, 'li02', 60)
        frozen, sample = self.fixture()
        sample['Npcs'] = []
        with self.assertRaises(ValueError):
            module.compare(frozen, sample, 'li02', 60)
