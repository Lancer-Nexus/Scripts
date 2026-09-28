#!/usr/bin/env python3
"""Prepare eight private LLServer instances from the installed Freelancer inventory."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import ssl

RANGES = {"br": 6, "bw": 10, "ew": 5, "iw": 6, "ku": 6, "li": 5, "rh": 5}


def child(parent, name):
    matches = [p for p in parent.iterdir() if p.name.lower() == name.lower()]
    if len(matches) != 1:
        raise ValueError(f"Missing or ambiguous asset path: {parent / name}")
    return matches[0]


def inventory(game):
    universe = child(child(game, "data"), "universe")
    systems = child(universe, "systems")
    folders = {p.name.lower(): p for p in systems.iterdir() if p.is_dir()}
    worlds = {}
    # Freelancer INIs have repeated sections and entries; ConfigParser cannot parse them.
    text = child(universe, "universe.ini").read_text(encoding="utf-8-sig")
    for section in re.split(r"(?m)^\s*\[", text):
        if not section.lower().startswith("system]"):
            continue
        nickname = re.search(r"(?im)^\s*nickname\s*=\s*([^;\r\n]+)", section)
        file = re.search(r"(?im)^\s*file\s*=\s*([^;\r\n]+)", section)
        if not nickname or not file:
            raise ValueError("System section without nickname/file")
        system = nickname[1].strip().lower()
        parts = file[1].strip().replace("\\", "/").split("/")
        if len(parts) < 3 or parts[0].lower() != "systems" or parts[1].lower() not in folders:
            raise ValueError(f"System {system} has no SYSTEMS directory")
        path = universe
        for part in parts:
            if part in ("", ".", ".."):
                raise ValueError("Unsafe universe file path")
            path = child(path, part)
        if system in worlds:
            raise ValueError(f"Duplicate system nickname: {system}")
        worlds[system] = parts[1].lower()
    assigned = {f"{prefix}{i:02d}" for prefix, count in RANGES.items() for i in range(1, count + 1)}
    if not assigned <= worlds.keys():
        raise ValueError(f"Required systems missing: {sorted(assigned - worlds.keys())}")
    groups = []
    for prefix, count in RANGES.items():
        ids = [f"{prefix}{i:02d}" for i in range(1, count + 1)]
        groups.append({"instanceId": f"{prefix}-01", "group": prefix,
                       "systems": ids, "assetDirectories": sorted({worlds[x] for x in ids})})
    covered_folders = {x for group in groups for x in group["assetDirectories"]}
    groups.append({"instanceId": "mixed-01", "group": "mixed",
                   "systems": sorted(worlds.keys() - assigned),
                   "assetDirectories": sorted(folders.keys() - covered_folders)})
    return {"schemaVersion": 1, "instances": groups,
            "nonWorldDirectories": sorted(folders.keys() - set(worlds.values())),
            "systemCount": len(worlds), "systemDirectoryCount": len(folders)}


def flatten(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flatten(item, prefix + "__" + key if prefix else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from flatten(item, prefix + "__" + str(index))
    else:
        yield prefix, str(value)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def prepare(args):
    game = args.game.resolve()
    output = args.output.resolve()
    state_root = args.state_root.resolve() if args.state_root else output
    address = ipaddress.ip_address(args.bind)
    if address.version != 4:
        raise ValueError("The prepared LLServer binding currently requires IPv4")
    if not (address.is_private or address.is_loopback) or address.is_unspecified:
        raise ValueError("Use a concrete private or loopback game address")
    if args.first_port < 1024 or args.first_port + 7 > 65535 or args.max_players <= 0:
        raise ValueError("Invalid port range/player limit")
    from urllib.parse import urlparse
    if urlparse(args.gateway).scheme != "https" or not urlparse(args.gateway).hostname:
        raise ValueError("Gateway must use HTTPS")
    plan = inventory(game)
    if args.inventory:
        write_json(args.inventory, plan)
    output.mkdir(parents=True, exist_ok=True)
    credentials = state_root / "private" / "instance-keys.json"
    credentials.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(credentials.parent, 0o700)
    gateway_ca = credentials.parent / "gateway-http-ca.crt"
    if args.gateway_ca:
        ssl.create_default_context(cafile=str(args.gateway_ca))
        if args.gateway_ca.resolve() != gateway_ca:
            shutil.copyfile(args.gateway_ca, gateway_ca)
        gateway_ca.chmod(0o600)
    keys = json.loads(credentials.read_text()) if credentials.exists() else {}
    for group in plan["instances"]:
        keys.setdefault(group["instanceId"], secrets.token_urlsafe(32))
    if any(not isinstance(key, str) or len(key) < 32 for key in keys.values()):
        raise ValueError("Invalid persisted instance key")
    if len(set(keys.values())) != len(keys):
        raise ValueError("Instance keys must be distinct")
    # Never replace a published key during a repeated prepare.
    with os.fdopen(os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(keys, f)
    os.chmod(credentials, 0o600)
    for index, group in enumerate(plan["instances"]):
        instance = group["instanceId"]
        state = state_root / "state" / instance
        state.mkdir(parents=True, exist_ok=True)
        port = args.first_port + index
        endpoint = f"[{address}]:{port}" if address.version == 6 else f"{address}:{port}"
        config = {"ServerName": f"Lancer Nexus {group['group'].upper()}",
                  "ServerDescription": "Nexus baseline: " + ", ".join(group["systems"]),
                  "FreelancerPath": str(game), "LoginUrl": args.gateway,
                  "DatabasePath": str(state / "characters.sqlite3"), "Port": port,
                  "BindAddress": str(address),
                  "MaxPlayers": args.max_players, "ThreadCount": 0,
                  "InstanceId": instance, "SystemId": group["systems"][0],
                  "SystemIds": group["systems"], "InstanceEndpoint": endpoint,
                  "RuntimeStatusFile": str(state / "status.json"), "DrainFlagFile": str(state / "drain.flag")}
        write_json(output / "config" / f"{instance}.json", config)
        env = state_root / "private" / f"{instance}.env"
        with os.fdopen(os.open(env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            f.write(f"LANCER_NEXUS_GAME_INSTANCE_KEY={keys[instance]}\n")
            f.write(f"INSTANCE_ID={instance}\nSYSTEM_ID={config['SystemId']}\n")
            f.write(f"SYSTEM_IDS={','.join(group['systems'])}\n")
            f.write(f"PRIVATE_BIND_ADDRESS={address}\nGAME_UDP_PORT={port}\n")
            f.write(f"PUBLIC_PLAYER_LIMIT={args.max_players}\nLLSERVER_RUNTIME_STATUS_FILE={config['RuntimeStatusFile']}\n")
        os.chmod(env, 0o600)
        agent = {"Agent": {"NodeId": args.node, "AgentId": f"{args.node}-{instance}",
                 "StateFile": str(state / "agent-sequence.txt"),
                 "Coordinator": {"QuicEndpoint": args.coordinator, "ServerName": args.coordinator_name,
                     "ClientCertificatePath": str(state_root / "private" / f"{args.node}.pfx"),
                     "CaCertificatePath": str(state_root / "private" / "cluster-ca.crt"),
                     "HeartbeatIntervalSeconds": 5},
                 "Instance": {"InstanceId": instance, "SystemId": config["SystemId"],
                     "SystemIds": group["systems"], "Endpoint": endpoint,
                     "StatusFile": config["RuntimeStatusFile"], "MaxPlayers": args.max_players}}}
        write_json(output / "config" / f"{instance}.agent.json", agent)
        agent_env = state_root / "private" / f"{instance}.agent.env"
        with os.fdopen(os.open(agent_env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            for name, value in flatten(agent):
                if "\n" in value or "\r" in value:
                    raise ValueError("Environment values must be single line")
                f.write(f"{name}={value}\n")
        os.chmod(agent_env, 0o600)
        # Separate Agent processes preserve the current one-instance-per-Agent worker model.
        group.update({"port": port, "endpoint": endpoint, "maxPlayers": args.max_players,
                      "config": str(output / "config" / f"{instance}.json"),
                      "agentConfig": str(output / "config" / f"{instance}.agent.json")})
    key_config = state_root / "private" / "gateway-instances.json"
    with os.fdopen(os.open(key_config, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump({g["instanceId"]: keys[g["instanceId"]] for g in plan["instances"]}, f)
    os.chmod(key_config, 0o600)
    env = state_root / "private" / "gateway-instances.env"
    with os.fdopen(os.open(env, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(f"Gateway__GameInstanceKeysFile={key_config}\n")
    os.chmod(env, 0o600)
    plan["stateRoot"] = str(state_root)
    plan["privateRoot"] = str(state_root / "private")
    if gateway_ca.exists():
        plan["gatewayCaCertificatePath"] = str(gateway_ca)
    write_json(output / "topology.json", plan)
    import shlex
    runner = Path(__file__).with_name("run-nexus-component.py").resolve()
    starter = output / "run.sh"
    starter.write_text("#!/usr/bin/env bash\nset -Eeuo pipefail\n" +
        "[[ $# -eq 2 ]] || { echo 'Usage: run.sh instance|agent INSTANCE_ID' >&2; exit 64; }\n" +
        "case \"$1\" in\n" +
        "  instance) app_dir=" + shlex.quote(str(output.parent / "server" / "llserver")) + ";;\n" +
        "  agent) app_dir=" + shlex.quote(str(output.parent / "agent" / "agent")) + ";;\n" +
        "  *) exit 64;;\nesac\n" +
        "exec python3 " + shlex.quote(str(runner)) + " \"$1\" \"$2\" --root " +
        shlex.quote(str(output)) + " --app-dir \"$app_dir\"\n")
    starter.chmod(0o755)
    print(f"Prepared {len(plan['instances'])} instances for {plan['systemCount']} systems in {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--state-root", type=Path, help="Persistent keys/databases outside replaceable build output")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--first-port", type=int, default=26000)
    parser.add_argument("--max-players", type=int, default=200)
    parser.add_argument("--gateway", default="https://localhost:38443")
    parser.add_argument("--gateway-ca", type=Path, help="Trusted Gateway HTTPS CA for a private local deployment")
    parser.add_argument("--node", default="nexus-local")
    parser.add_argument("--coordinator", default="127.0.0.1:7443")
    parser.add_argument("--coordinator-name", default="coordinator.internal.example")
    args = parser.parse_args()
    try:
        prepare(args)
    except (ValueError, OSError, json.JSONDecodeError, ssl.SSLError) as error:
        parser.exit(1, f"Configuration failed: {error}\n")


if __name__ == "__main__":
    main()
