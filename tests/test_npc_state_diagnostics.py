import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import json


path = Path(__file__).resolve().parents[1] / "tools/compare-npc-state.py"
spec = importlib.util.spec_from_file_location("npc_state", path)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)
NPC = "00000000-0000-0000-0000-000000000001"


def sample(instance="li01", tick=1, version=6, x=0):
    return {"InstanceId": instance, "CurrentTick": tick, "Npcs": [{
        "NpcId": NPC, "OwnershipVersion": version, "Position": {"X": x, "Y": 0, "Z": 0}}]}


class NpcStateTests(unittest.TestCase):
    def test_one_copy_and_missing_copy(self):
        empty = sample("li02")
        empty["Npcs"] = []
        self.assertTrue(diagnostics.compare_copies([sample(), empty], [NPC])[1])
        self.assertFalse(diagnostics.compare_copies([empty], [NPC])[1])

    def test_duplicate_copy_and_duplicate_instance_are_rejected(self):
        result, accepted = diagnostics.compare_copies([sample(), sample("li02")], [NPC])
        self.assertFalse(accepted)
        self.assertEqual(2, result["ActiveCopyCounts"][NPC])
        with self.assertRaises(ValueError):
            diagnostics.compare_copies([sample(), sample()], [NPC])

    def test_movement_and_stationary_ship(self):
        result, accepted = diagnostics.compare_movement(sample(), sample(tick=2, x=50), [NPC])
        self.assertTrue(accepted)
        self.assertEqual(50, result["DistanceMoved"][NPC])
        self.assertFalse(diagnostics.compare_movement(sample(), sample(tick=2), [NPC])[1])

    def test_movement_requires_same_lease_and_increasing_tick(self):
        for second in [sample(tick=2, version=7), sample(tick=1), sample("li02", tick=2)]:
            with self.assertRaises(ValueError):
                diagnostics.compare_movement(sample(), second, [NPC])

    def test_last_console_sample_and_duplicate_identity_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "console.log"
            path.write_text("noise\nNPC_STATE " + json.dumps(sample()) +
                            "\nNPC_STATE " + json.dumps(sample(tick=2)) + "\n")
            self.assertEqual(2, diagnostics.read_sample(path)["CurrentTick"])
            invalid = sample()
            invalid["Npcs"].append(copy.deepcopy(invalid["Npcs"][0]))
            path.write_text(json.dumps(invalid))
            with self.assertRaises(ValueError):
                diagnostics.read_sample(path)


if __name__ == "__main__":
    unittest.main()
