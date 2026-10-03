#!/usr/bin/env python3
"""Enable/disable the Debug mission fixture in an existing two-instance E2E run."""
import argparse
import json
import os
from pathlib import Path
import stat
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-root", type=Path, required=True)
    parser.add_argument("--mission", default="Mission_01a")
    parser.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    if not args.disable and (not args.mission.strip() or len(args.mission) > 96):
        parser.error("Mission nickname must contain 1–96 characters.")
    edits = []
    for name in ("li01", "li02"):
        path = args.test_root / "gameserver" / f"llserver-{name}.json"
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode):
            parser.error("Existing regular E2E configuration files are required.")
        value = json.loads(path.read_text())
        if value.get("InstanceId") != name or value.get("TestNewCharacterRank") != 50:
            parser.error("Refusing to modify a configuration without the two-instance E2E test preset.")
        value["TestMissionNickname"] = None if args.disable else args.mission
        edits.append((path, mode, value))
    for path, mode, value in edits:
        fd, temporary = tempfile.mkstemp(prefix=".e2e-mission-", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(json.dumps(value, indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, stat.S_IMODE(mode))
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    print("Debug E2E mission fixture " + ("disabled" if args.disable else "configured") + "; restart both test GameServers.")


if __name__ == "__main__":
    main()
