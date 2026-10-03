import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).parents[1] / 'tools/prepare-e2e-space-pilot.py'


class SpacePilotTests(unittest.TestCase):
    def test_restores_empty_pilot_retains_backup_and_refuses_second_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            server = root / 'state/gameserver'
            server.mkdir(parents=True)
            (server / 'llserver-li01.json').write_text(json.dumps(
                {'InstanceId': 'li01', 'TestNewCharacterRank': 50}))
            data = root / 'client/data/ships'
            data.mkdir(parents=True)
            (data / 'loadouts.ini').write_text('[Loadout]\nnickname = li_n_li_elite_loadout03\n'
                'archetype = li_elite\nequip = infinite_power\nequip = engine, HpEngine01\ncargo = ammo, 5\n')
            database = server / 'li01-characters.sqlite3'
            with sqlite3.connect(database) as db:
                db.execute('CREATE TABLE Characters (Id INTEGER,Name TEXT,Ship TEXT,Base TEXT,System TEXT,'
                           'X REAL,Y REAL,Z REAL,RotationX REAL,RotationY REAL,RotationZ REAL,RotationW REAL,Rank INTEGER)')
                db.execute("INSERT INTO Characters (Id,Name) VALUES (1,'Test')")
                db.execute('CREATE TABLE CargoItem (ItemName TEXT,ItemCount INTEGER,Hardpoint TEXT,Health REAL,'
                           'IsMissionItem INTEGER,CharacterId INTEGER,CreationDate REAL)')
            cmd = [sys.executable, str(TOOL), '--test-root', str(root / 'state'),
                   '--client-root', str(root / 'client')]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            with sqlite3.connect(database) as db:
                self.assertEqual(('li_elite', None, 'Li01', -81511), db.execute(
                    'SELECT Ship,Base,System,Z FROM Characters WHERE Id=1').fetchone())
                self.assertEqual(3, db.execute('SELECT COUNT(*) FROM CargoItem').fetchone()[0])
                self.assertGreater(db.execute('SELECT MIN(CreationDate) FROM CargoItem').fetchone()[0], 2400000)
            backups = list(server.glob('li01-before-space-pilot-*.sqlite3'))
            self.assertEqual(1, len(backups))
            self.assertEqual(0o600, backups[0].stat().st_mode & 0o777)
            with sqlite3.connect(backups[0]) as db:
                self.assertIsNone(db.execute('SELECT Ship FROM Characters').fetchone()[0])
                self.assertEqual(0, db.execute('SELECT COUNT(*) FROM CargoItem').fetchone()[0])
            # A distinct pilot can be created without changing the existing character or cargo.
            with sqlite3.connect(server / 'li02-characters.sqlite3') as peer:
                peer.execute('CREATE TABLE Characters (Id INTEGER)')
                peer.execute('INSERT INTO Characters VALUES (8)')
            cloned = subprocess.run(cmd + ['--pilot', 'Convoy', '--clone-from', 'Test'], capture_output=True, text=True)
            self.assertEqual(0, cloned.returncode, cloned.stderr)
            with sqlite3.connect(database) as db:
                self.assertEqual(9, db.execute("SELECT Id FROM Characters WHERE Name='Convoy'").fetchone()[0])
                self.assertEqual(3, db.execute('SELECT COUNT(*) FROM CargoItem WHERE CharacterId=1').fetchone()[0])
                self.assertEqual(3, db.execute('SELECT COUNT(*) FROM CargoItem WHERE CharacterId=9').fetchone()[0])
            second_clone = subprocess.run(cmd + ['--pilot', 'Convoy', '--clone-from', 'Test'], capture_output=True, text=True)
            self.assertNotEqual(0, second_clone.returncode)
            self.assertIn('already exists', second_clone.stderr)
            positioned = subprocess.run(cmd + ['--position-only'], capture_output=True, text=True)
            self.assertEqual(0, positioned.returncode, positioned.stderr)
            with sqlite3.connect(database) as db:
                self.assertEqual(3, db.execute('SELECT COUNT(*) FROM CargoItem WHERE CharacterId=1').fetchone()[0])
            repeat = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(0, repeat.returncode)
            self.assertIn('cargo is not empty', repeat.stderr)
