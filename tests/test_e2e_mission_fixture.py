import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("mission_fixture", Path(__file__).parents[1] / "tools/isolate-e2e-mission.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class MissionFixtureTests(unittest.TestCase):
    def test_fixture_excludes_intro_and_preserves_required_npc_descriptors(self):
        original = """[Mission]
npc_ship_file = missions\\m01a\\npcships.ini
[NPC]
nickname = transport1_m01a
npc_ship_arch = transport
[NPC]
nickname = escort_m01a
npc_ship_arch = escort
[Trigger]
nickname = intro_cinematic
Act_PlayBink = intro
"""
        result = module.fixture(original).decode()
        self.assertNotIn("intro_cinematic", result)
        self.assertNotIn("Act_PlayBink", result)
        self.assertEqual(2, result.count("[NPC]"))
        self.assertEqual(2, result.count("[MsnShip]"))
        self.assertEqual(1, result.count("[MsnFormation]"))
        self.assertEqual(2, result.count("jumper = true"))
        self.assertIn("Cnd_Timer = 600", result)
        self.assertIn("Act_SpawnFormation = nexus_transfer_formation", result)

    def test_missing_original_npc_descriptors_are_rejected(self):
        with self.assertRaises(ValueError):
            module.fixture("[Mission]\nnpc_ship_file = missing\n")
