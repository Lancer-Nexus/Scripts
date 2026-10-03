#!/usr/bin/env python3
"""Configure a private Gateway/Coordinator env-file pair without printing secrets."""
import argparse
import os
import re
import secrets
import shlex
import stat
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

GATEWAY_KEY = "Gateway__NpcMissionAuthorityApiKey"
COORDINATOR_KEY = "Coordinator__NpcMissionAuthorityApiKey"
COORDINATOR_URL = "Coordinator__NpcMissionAuthorityBaseUrl"


def read_private_env(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Env files must be regular, owned by the current user and private (0600).")
    lines = path.read_text().splitlines()
    values = {}
    for line in lines:
        match = re.fullmatch(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if not match:
            continue
        parts = shlex.split(match.group(2), comments=True)
        if len(parts) != 1 or match.group(1) in values:
            raise ValueError("Env files must contain unique literal assignments.")
        values[match.group(1)] = parts[0]
    return lines, values


def write_private_env(path, lines, updates):
    names = set(updates)
    output = []
    for line in lines:
        match = re.match(r"(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=", line)
        if match and match.group(1) in updates:
            name = match.group(1)
            output.append(f"{name}={shlex.quote(updates[name])}")
            names.remove(name)
        else:
            output.append(line)
    output.extend(f"{name}={shlex.quote(updates[name])}" for name in sorted(names))
    fd, temporary = tempfile.mkstemp(prefix=".npc-authority-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write("\n".join(output) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(gateway_path, coordinator_path, gateway_url):
    endpoint = urlsplit(gateway_url)
    if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password
            or endpoint.query or endpoint.fragment or endpoint.path not in ("", "/")):
        raise ValueError("Gateway URL must be an HTTPS origin without credentials, path or query.")
    if gateway_path.resolve() == coordinator_path.resolve():
        raise ValueError("Gateway and Coordinator env files must differ.")
    gateway_lines, gateway = read_private_env(gateway_path)
    coordinator_lines, coordinator = read_private_env(coordinator_path)
    existing = {value for value in (gateway.get(GATEWAY_KEY), coordinator.get(COORDINATOR_KEY)) if value}
    if len(existing) > 1:
        raise ValueError("Configured authority keys differ; refusing automatic rotation.")
    key = next(iter(existing), None) or secrets.token_hex(32)
    if len(key.encode()) < 32:
        raise ValueError("Authority key must contain at least 32 UTF-8 bytes.")
    other_keys = [value for name, value in gateway.items() if name.startswith("Gateway__GameInstanceKeys__")]
    other_keys.extend(value for name, value in gateway.items() if name.endswith("ApiKey") and name != GATEWAY_KEY)
    other_keys.extend(value for name, value in coordinator.items() if name.endswith("ApiKey") and name != COORDINATOR_KEY)
    key_file = gateway.get("Gateway__GameInstanceKeysFile")
    if key_file:
        import json
        other_keys.extend(json.loads(Path(key_file).read_text()).values())
    if key in other_keys:
        raise ValueError("Authority credential must be distinct from instance and other service keys.")
    # If interrupted between files, the next run reuses the first saved key.
    write_private_env(gateway_path, gateway_lines, {GATEWAY_KEY: key})
    write_private_env(coordinator_path, coordinator_lines, {COORDINATOR_KEY: key, COORDINATOR_URL: gateway_url})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-env", type=Path, required=True)
    parser.add_argument("--coordinator-env", type=Path, required=True)
    parser.add_argument("--gateway-url", required=True)
    args = parser.parse_args()
    try:
        configure(args.gateway_env, args.coordinator_env, args.gateway_url)
    except (OSError, ValueError):
        parser.exit(2, "Configuration rejected; check private files, literal assignments, distinct keys and HTTPS origin.\n")
    print("NPC mission authority configured; private credentials were not printed.")


if __name__ == "__main__":
    main()
