#!/usr/bin/env python3
"""Replace the collected Mission_01a with a backed-up, minimal NPC transfer fixture."""
import argparse
from pathlib import Path
import re
import shutil


def fixture(original):
    sections = re.split(r"(?m)(?=^\[)", original.replace("\r\n", "\n"))
    required = []
    for header, nickname in (("Mission", None), ("NPC", "transport1_m01a"), ("NPC", "escort_m01a")):
        matches = [s for s in sections if s.startswith(f"[{header}]\n") and
                   (nickname is None or re.search(r"(?m)^nickname\s*=\s*" + re.escape(nickname) + r"\s*$", s))]
        if len(matches) != 1:
            raise ValueError("Expected one mission header and both original NPC descriptors.")
        required.append(matches[0].strip())
    extra = """
[MsnShip]
nickname = nexus_transfer_transport
NPC = transport1_m01a
jumper = true
label = nexus_transfer_convoy

[MsnShip]
nickname = nexus_transfer_escort
NPC = escort_m01a
jumper = true
label = nexus_transfer_convoy

[MsnFormation]
nickname = nexus_transfer_formation
position = -12300, -200, -81000
orientation = 1, 0, 0, 0
formation = escort_transports_delta_formation
ship = nexus_transfer_transport
ship = nexus_transfer_escort

[Trigger]
nickname = nexus_npc_transfer_test_spawn
system = Li01
InitState = ACTIVE
Cnd_True = no_params
Act_MovePlayer = -12831, 0, -81511, 1000
Act_SpawnFormation = nexus_transfer_formation
Act_MarkObj = nexus_transfer_transport, 1
Act_MarkObj = nexus_transfer_escort, 1

[Trigger]
nickname = nexus_npc_transfer_timer
InitState = ACTIVE
Cnd_Timer = 600
"""
    return ("\n\n".join(required) + "\n\n" + extra.strip() + "\n").replace("\n", "\r\n").encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-root", type=Path, required=True)
    parser.add_argument("--test-root", type=Path, required=True)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if not args.test_root.is_dir():
        parser.error("Existing isolated E2E state directory required.")
    target = args.client_root / "data/missions/m01a/m01a.ini"
    backup = args.test_root / "isolated-mission-original/m01a.ini"
    if args.restore:
        shutil.copy2(backup, target)
        print("Original collected Mission_01a restored; restart test GameServers.")
        return
    original = (backup if backup.exists() else target).read_bytes().decode("utf-8-sig")
    content = fixture(original)
    if not backup.exists():
        backup.parent.mkdir(parents=True, mode=0o700)
        shutil.copy2(target, backup)
    target.write_bytes(content)
    print("Isolated mission fixture installed: two Jumper NPCs, formation, label and active timer; restart test GameServers.")


if __name__ == "__main__":
    main()
