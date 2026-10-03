#!/usr/bin/env python3
"""Keep the local LI01 and LI02 transfer-test GameServers registered."""

import json
import os
import pathlib
import ssl
import sys
import time
import urllib.error
import urllib.request

state = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/lancer-nexus-first-e2e-run")
disable_npc_transfer = "--disable-npc-transfer" in sys.argv[1:]
coordinator_url = os.environ.get("ASPNETCORE_URLS", "https://localhost:38444").rstrip("/")
api_key = os.environ["Coordinator__InternalApiKey"]
context = ssl.create_default_context(cafile=str(state / "localhost-cert.pem"))
status_files = (
    state / "gameserver/li01-instance-status.json",
    state / "gameserver/li02-instance-status.json",
)
server_configs = {
    "li01": state / "gameserver/llserver-li01.json",
    "li02": state / "gameserver/llserver-li02.json",
}


def post(path: str, body: dict) -> dict:
    request = urllib.request.Request(
        coordinator_url + path,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, context=context, timeout=4) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{path} returned HTTP {error.code}") from None


# Use a Unix-time base so a reporter restart advances beyond the Coordinator's
# persisted sequence instead of replaying from one.
sequence = int(time.time())
print("LI01/LI02 GameServer heartbeat reporter active; Ctrl+C stops it.", flush=True)
while True:
    try:
        available = [path for path in status_files if path.is_file()]
        if not available:
            print("Waiting for LI01 and LI02 LLServer runtime status...", flush=True)
        else:
            sequence += 1
            agent = post("/internal/v1/agents/heartbeat", {
                "agentId": "first-e2e-agent",
                "nodeId": "localhost",
                "buildVersion": "local-e2e",
                "protocolVersion": 1,
                "capabilities": ["instance_heartbeat_v1"],
                "sequence": sequence,
            })
            for status_file in status_files:
                if not status_file.is_file():
                    continue
                status = json.loads(status_file.read_text())
                capabilities = ["client_version_hello_v1", "join_ticket_v1"]
                npc_endpoint = status.get("NpcTransferEndpoint")
                config_path = server_configs.get(status["InstanceId"])
                if config_path is not None and config_path.is_file():
                    server_config = json.loads(config_path.read_text())
                    if server_config.get("NpcCoordinatorUrl"):
                        capabilities.append("npc_ownership_v1")
                    if not disable_npc_transfer and server_config.get("NpcTransferPort", 0) > 0:
                        capabilities.append("npc_transfer_v1")
                        if npc_endpoint is None:
                            host = server_config["NpcTransferListenAddress"]
                            host = f"[{host}]" if ":" in host else host
                            npc_endpoint = f"quic://{host}:{server_config['NpcTransferPort']}"
                # The Coordinator tracks instance sequences independently. Use
                # one monotonic local sequence for each status stream.
                instance = post("/internal/v1/instances/heartbeat", {
                    "agentId": "first-e2e-agent",
                    "instanceId": status["InstanceId"],
                    "systemId": status["SystemId"],
                    "sequence": sequence,
                    "isReady": status["IsReady"],
                    "isDraining": status["IsDraining"],
                    "currentPlayers": status["CurrentPlayers"],
                    "maxPlayers": status["MaxPlayers"],
                    "endpoint": status["Endpoint"],
                    "capabilities": capabilities,
                    "npcTransferEndpoint": None if disable_npc_transfer else npc_endpoint,
                })
                print(
                    f"heartbeat seq={sequence}: agent={agent.get('reasonCode')} "
                    f"instance={status['InstanceId']} system={status['SystemId']} "
                    f"result={instance.get('reasonCode')} ready={status['IsReady']} "
                    f"players={status['CurrentPlayers']}/{status['MaxPlayers']}",
                    flush=True,
                )
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"heartbeat retry: {error}", flush=True)
    time.sleep(5)
