#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "prepare-nexus-baseline.py"
spec = importlib.util.spec_from_file_location("nexus_prepare", SCRIPT)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.game = self.root / "game"
        self.universe = self.game / "DATA" / "UNIVERSE"
        self.systems = self.universe / "SYSTEMS"
        self.systems.mkdir(parents=True)
        ids = [f"{p}{i:02d}" for p, n in prepare.RANGES.items() for i in range(1, n + 1)]
        entries = []
        for nickname, folder in [(x, x.upper()) for x in ids] + [("FP7_system", "FP7"), ("ew06", "EW06")]:
            directory = self.systems / folder
            directory.mkdir()
            (directory / (nickname + ".INI")).write_text("[SystemInfo]\n")
            entries.append(f"[System]\nnickname = {nickname}\nfile = systems\\{folder}\\{nickname}.ini\n")
        (self.systems / "INTRO").mkdir()
        (self.systems / "miners").mkdir()
        (self.universe / "universe.INI").write_text("\n".join(entries))

    def tearDown(self):
        self.temp.cleanup()

    def test_complete_unique_assignment_uses_world_nicknames(self):
        plan = prepare.inventory(self.game)
        systems = [x for group in plan["instances"] for x in group["systems"]]
        self.assertEqual(8, len(plan["instances"]))
        self.assertEqual(45, len(systems))
        self.assertEqual(len(systems), len(set(systems)))
        mixed = plan["instances"][-1]
        self.assertEqual(["ew06", "fp7_system"], mixed["systems"])
        self.assertEqual(["ew06", "fp7", "intro", "miners"], mixed["assetDirectories"])
        self.assertEqual(["intro", "miners"], plan["nonWorldDirectories"])

    def test_missing_required_world_fails(self):
        universe = self.universe / "universe.INI"
        universe.write_text(universe.read_text().replace("nickname = br01", "nickname = renamed"))
        with self.assertRaisesRegex(ValueError, "Required systems missing"):
            prepare.inventory(self.game)

    def test_reprepare_preserves_private_keys_and_database_state(self):
        output = self.root / "output"
        state = self.root / "persistent"
        command = [sys.executable, str(SCRIPT), "--game", str(self.game), "--output", str(output), "--state-root", str(state)]
        subprocess.run(command, check=True, capture_output=True)
        keys = state / "private" / "instance-keys.json"
        before = keys.read_bytes()
        database = state / "state" / "li-01" / "characters.sqlite3"
        database.write_bytes(b"existing-character-state")
        subprocess.run(command, check=True, capture_output=True)
        self.assertEqual(before, keys.read_bytes())
        self.assertEqual(0o600, stat.S_IMODE(keys.stat().st_mode))
        self.assertEqual(b"existing-character-state", database.read_bytes())
        topology = json.loads((output / "topology.json").read_text())
        self.assertEqual(8, len({g["port"] for g in topology["instances"]}))
        self.assertEqual(8, len(set(json.loads(before).values())))
        env = (state / "private" / "gateway-instances.env").read_text()
        self.assertIn("Gateway__GameInstanceKeysFile=", env)
        self.assertEqual(json.loads(before), json.loads((state / "private" / "gateway-instances.json").read_text()))


if __name__ == "__main__":
    unittest.main()
