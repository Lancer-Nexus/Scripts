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
    coordinator_http_url = args.coordinator_http_url
    if not coordinator_http_url:
        quic = urlparse("//" + args.coordinator)
        if not quic.hostname or quic.port is None:
            raise ValueError("Coordinator QUIC endpoint must be a host:port")
        host = f"[{quic.hostname}]" if ":" in quic.hostname else quic.hostname
        coordinator_http_url = f"https://{host}:8444"
    coordinator_http = urlparse(coordinator_http_url)
    if (coordinator_http.scheme not in ("https", "http") or not coordinator_http.hostname or
            coordinator_http.username or coordinator_http.password or coordinator_http.query or
            coordinator_http.fragment or coordinator_http.path not in ("", "/") or
            (coordinator_http.scheme == "http" and coordinator_http.hostname not in
             ("localhost", "127.0.0.1", "::1"))):
        raise ValueError("NPC Coordinator URL must be HTTPS (HTTP is allowed only for loopback development)")
    if args.npc_transfer_port_base and (args.npc_transfer_port_base < 1024 or
                                        args.npc_transfer_port_base + 7 > 65535):
        raise ValueError("NPC transfer port base must leave eight valid private ports")
    if args.npc_transfer_port_base and not (args.npc_transfer_port_base + 7 < args.first_port or
                                            args.npc_transfer_port_base > args.first_port + 7):
        raise ValueError("NPC transfer ports must not overlap the game UDP port range")
    transfer_cert_dir = args.npc_transfer_cert_dir.resolve() if args.npc_transfer_cert_dir else None
    if args.npc_transfer_port_base and transfer_cert_dir is None:
        raise ValueError("NPC transfer certificates are required when the transfer listener is enabled")
    plan = inventory(game)
    if args.npc_transfer_port_base:
        if not (transfer_cert_dir / "npc-transfer-ca.crt").is_file():
            raise ValueError("NPC transfer CA certificate is missing from the certificate directory")
        missing_certificates = [str(transfer_cert_dir / f"{group['instanceId']}.pfx")
                               for group in plan["instances"]
                               if not (transfer_cert_dir / f"{group['instanceId']}.pfx").is_file()]
        if missing_certificates:
            raise ValueError("NPC transfer server certificates are missing: " + ", ".join(missing_certificates))
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
                  "NpcCoordinatorUrl": coordinator_http_url,
                  "DatabasePath": str(state / "characters.sqlite3"), "Port": port,
                  "BindAddress": str(address),
                  "MaxPlayers": args.max_players, "ThreadCount": 0,
                  "InstanceId": instance, "SystemId": group["systems"][0],
                  "SystemIds": group["systems"], "InstanceEndpoint": endpoint,
                  "RuntimeStatusFile": str(state / "status.json"), "DrainFlagFile": str(state / "drain.flag")}
        if args.npc_transfer_port_base:
            server_certificate = transfer_cert_dir / f"{instance}.pfx"
            config.update({
                "NpcTransferListenAddress": str(address),
                "NpcTransferPort": args.npc_transfer_port_base + index,
                "NpcTransferServerCertificate": str(server_certificate),
                "NpcTransferClientCaCertificate": str(transfer_cert_dir / "npc-transfer-ca.crt"),
                "NpcTransferStagingDirectory": str(state / "npc-transfers")
            })
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
    parser.add_argument("--coordinator-http-url", help="Private Coordinator HTTP base URL; defaults to https://<QUIC-host>:8444")
    parser.add_argument("--coordinator-name", default="coordinator.internal.example")
    parser.add_argument("--npc-transfer-port-base", type=int, default=0,
                        help="Enable NPC mTLS/QUIC listeners on eight consecutive private ports")
    parser.add_argument("--npc-transfer-cert-dir", type=Path,
                        help="Directory containing <instance>.pfx certificates and npc-transfer-ca.crt")
    args = parser.parse_args()
    try:
        prepare(args)
    except (ValueError, OSError, json.JSONDecodeError, ssl.SSLError) as error:
        parser.exit(1, f"Configuration failed: {error}\n")


if __name__ == "__main__":
    main()
