#!/usr/bin/env python3
"""Read-only HTTPS checks for a configured NPC mission authority boundary."""
import argparse
import importlib.util
import json
from pathlib import Path
import ssl
import urllib.error
import urllib.request
import uuid

spec = importlib.util.spec_from_file_location("authority_config", Path(__file__).with_name("configure-npc-mission-authority.py"))
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(url, trust, key=None, body=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    message = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=trust), NoRedirect())
        with opener.open(message, timeout=10) as response:
            return response.status, response.read(65536)
    except urllib.error.HTTPError as error:
        return error.code, error.read(65536)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-env", type=Path, required=True)
    parser.add_argument("--coordinator-env", type=Path, required=True)
    parser.add_argument("--ca-file", type=Path, required=True)
    parser.add_argument("--coordinator-url", required=True)
    args = parser.parse_args()
    try:
        gateway = config.read_private_env(args.gateway_env)[1]
        coordinator = config.read_private_env(args.coordinator_env)[1]
        key = gateway[config.GATEWAY_KEY]
        if coordinator[config.COORDINATOR_KEY] != key:
            raise ValueError("Mismatched private keys")
        origin = coordinator[config.COORDINATOR_URL].rstrip("/")
        if not origin.startswith("https://") or not args.coordinator_url.startswith("https://"):
            raise ValueError("HTTPS required")
        trust = ssl.create_default_context(cafile=str(args.ca_file))
        results = {}
        for name, base in (("gateway", origin), ("coordinator", args.coordinator_url.rstrip("/"))):
            code, _ = request(base + "/health/ready", trust)
            results[name + "_ready"] = code
            if code != 200:
                raise ValueError("Service readiness failed")
        transfer = str(uuid.uuid4())
        body = dict(transferId=transfer, sourceInstanceId="authority-smoke-source",
                    targetInstanceId="authority-smoke-target", targetSystemId="li03", decision=6, schemaVersion=1)
        route = origin + "/internal/v1/npc-mission-authority"
        for name, credential in (("unauthenticated", None), ("wrong_service_key", "invalid-" + uuid.uuid4().hex)):
            code, _ = request(route, trust, credential, body)
            results[name] = code
            if code != 401:
                raise ValueError("Authentication boundary failed")
        instance_key = next((value for name, value in gateway.items() if name.startswith("Gateway__GameInstanceKeys__")), None)
        if instance_key:
            code, _ = request(route, trust, instance_key, body)
            results["game_instance_key"] = code
            if code != 401:
                raise ValueError("Game credential admitted at service boundary")
        code, content = request(route, trust, key, body)
        result = json.loads(content)
        if (code != 200 or result.get("accepted") is not False or result.get("transferId") != transfer
                or result.get("reasonCode") != "character_transfer_binding_mismatch"):
            raise ValueError("Unknown character transfer was not rejected")
        results["authenticated_unknown_transfer"] = code
        results["unknown_transfer_accepted"] = False
        results["scope"] = "Readiness and authentication only; no character/NPC mutation or gameplay proof."
        print(json.dumps(results, indent=2))
    except (OSError, ValueError, KeyError):
        parser.exit(1, "Authority check failed; inspect service readiness, private configuration and TLS trust.\n")


if __name__ == "__main__":
    main()
