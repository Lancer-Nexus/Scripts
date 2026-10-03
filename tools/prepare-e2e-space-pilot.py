#!/usr/bin/env python3
"""Restore an empty isolated test pilot's loadout and start it at the Li01 gate."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-root', type=Path, required=True)
    parser.add_argument('--client-root', type=Path, required=True)
    parser.add_argument('--pilot', default='Test')
    parser.add_argument('--clone-from', help='Create a separate local fixture pilot from this existing source pilot')
    args = parser.parse_args()
    config = args.test_root / 'gameserver/llserver-li01.json'
    value = json.loads(config.read_text())
    if value.get('InstanceId') != 'li01' or value.get('TestNewCharacterRank') != 50:
        parser.error('Existing two-instance E2E test preset required.')
    for process in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            argv = process.read_bytes().split(b'\0')
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if argv and Path(os.fsdecode(argv[0])).name == 'LLServer' and any(
                os.fsdecode(arg) == str(config.resolve()) for arg in argv):
            parser.error('Stop the source test GameServer before editing its SQLite database.')
    loadouts = (args.client_root / 'data/ships/loadouts.ini').read_text(encoding='utf-8-sig')
    sections = re.split(r'(?m)(?=^\[)', loadouts)
    selected = [s for s in sections if re.search(
        r'(?mi)^nickname\s*=\s*li_n_li_elite_loadout03\s*$', s)]
    if len(selected) != 1 or not re.search(r'(?mi)^archetype\s*=\s*li_elite\s*$', selected[0]):
        parser.error('Expected original test-pilot loadout was not found.')
    cargo = []
    for kind, text in re.findall(r'(?mi)^(equip|cargo)\s*=\s*([^\r\n]+)', selected[0]):
        parts = [p.strip() for p in text.split(',')]
        if kind.lower() == 'equip':
            cargo.append((parts[0], 1, parts[1] if len(parts) > 1 else 'internal'))
        else:
            cargo.append((parts[0], int(parts[1]), None))
    database = args.test_root / 'gameserver/li01-characters.sqlite3'
    if not database.is_file() or database.is_symlink():
        parser.error('Existing regular isolated character database required.')
    connection = sqlite3.connect(f'file:{database.resolve()}?mode=rw', uri=True)
    row = connection.execute('SELECT Id,Ship FROM Characters WHERE Name=?', (args.pilot,)).fetchone()
    clone = None
    if args.clone_from:
        if row is not None:
            parser.error('Clone destination pilot already exists; refusing to overwrite it.')
        if not args.pilot.strip() or len(args.pilot) > 23:
            parser.error('Fixture pilot name must contain 1–23 characters.')
        source = connection.execute('SELECT * FROM Characters WHERE Name=?', (args.clone_from,))
        columns = [item[0] for item in source.description]
        values = source.fetchone()
        if values is None:
            parser.error('Source fixture pilot does not exist.')
        clone = dict(zip(columns, values))
        maximum = connection.execute('SELECT COALESCE(MAX(Id),0) FROM Characters').fetchone()[0]
        peer = args.test_root / 'gameserver/li02-characters.sqlite3'
        if not peer.is_file() or peer.is_symlink():
            parser.error('Existing regular isolated target character database required for fixture IDs.')
        with sqlite3.connect(f'file:{peer.resolve()}?mode=ro', uri=True) as peer_db:
            maximum = max(maximum, peer_db.execute('SELECT COALESCE(MAX(Id),0) FROM Characters').fetchone()[0])
        clone.update(Id=maximum + 1, Name=args.pilot)
        row = (clone['Id'], clone['Ship'])
    if row is None or row[1] not in (None, 'li_elite'):
        parser.error('Expected isolated Liberty elite test pilot required.')
    if connection.execute('SELECT COUNT(*) FROM CargoItem WHERE CharacterId=?', (row[0],)).fetchone()[0]:
        parser.error('Pilot cargo is not empty; refusing to overwrite existing equipment.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = database.with_name(f'li01-before-space-pilot-{stamp}.sqlite3')
    descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    with sqlite3.connect(backup) as destination:
        connection.backup(destination)
    with connection:
        if clone is not None:
            connection.execute('INSERT INTO Characters (' + ','.join('"' + name + '"' for name in clone) +
                               ') VALUES (' + ','.join('?' for _ in clone) + ')', list(clone.values()))
        connection.execute("UPDATE Characters SET Ship='li_elite',Base=NULL,System='Li01',"
                           'X=-12831,Y=0,Z=-81511,RotationX=0,RotationY=0,RotationZ=0,RotationW=1,Rank=50 WHERE Id=?',
                           (row[0],))
        connection.executemany('INSERT INTO CargoItem '
            '(ItemName,ItemCount,Hardpoint,Health,IsMissionItem,CharacterId,CreationDate) VALUES (?,?,?,1,0,?,?)',
            [(name, count, hardpoint, row[0], datetime.now(timezone.utc).timestamp() / 86400 + 2440587.5) for name, count, hardpoint in cargo])
    connection.close()
    print('Empty test pilot restored in space with original loadout; private SQLite backup retained. Gateway lease unchanged.')


if __name__ == '__main__':
    main()
