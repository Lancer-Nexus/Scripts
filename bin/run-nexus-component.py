#!/usr/bin/env python3
"""Start one prepared Nexus game instance or its outbound Agent."""
import argparse
import json
import os
from pathlib import Path
import stat


def flatten(value, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from flatten(item, prefix + "__" + key if prefix else key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from flatten(item, prefix + "__" + str(index))
    else:
        yield prefix, str(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("instance", "agent"))
    parser.add_argument("instance")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--app-dir", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    plan = json.loads((root / "topology.json").read_text())
    group = next((x for x in plan["instances"] if x["instanceId"] == args.instance), None)
    if group is None:
        parser.error("Instance is not part of the prepared topology")
    environment = dict(os.environ)
    if "DOTNET_ROOT" not in environment and Path("/opt/dotnet-10/dotnet").exists():
        environment["DOTNET_ROOT"] = "/opt/dotnet-10"
        environment["DOTNET_ROOT_X64"] = "/opt/dotnet-10"
    app_dir = args.app_dir.resolve()
    if args.role == "instance":
        config = Path(group["config"])
        values = json.loads(config.read_text())
        if values["InstanceId"] != args.instance or values["SystemIds"] != group["systems"]:
            parser.error("LLServer system ownership does not match topology")
        secret_file = Path(plan["privateRoot"]) / "instance-keys.json"
        if stat.S_IMODE(secret_file.stat().st_mode) & 0o077:
            parser.error("Private instance key file must have mode 0600")
        environment["LANCER_NEXUS_GAME_INSTANCE_KEY"] = json.loads(secret_file.read_text())[args.instance]
        if plan.get("gatewayCaCertificatePath"):
            environment["SSL_CERT_FILE"] = plan["gatewayCaCertificatePath"]
        executable = app_dir / "LLServer"
        argv = [str(executable), "--config=" + str(config)]
    else:
        config = json.loads(Path(group["agentConfig"]).read_text())
        for key in ("ClientCertificatePath", "CaCertificatePath"):
            if not Path(config["Agent"]["Coordinator"][key]).is_file():
                parser.error("Agent requires provisioned mTLS certificate and CA files")
        environment.update(flatten(config))
        executable = app_dir / "LancerNexus.Agent"
        argv = [str(executable)]
    if not executable.is_file() or not os.access(executable, os.X_OK):
        parser.error("Build and collect the executable before starting")
    os.chdir(app_dir)
    print(f"Starting {args.role} {args.instance}", flush=True)
    os.execve(executable, argv, environment)


if __name__ == "__main__":
    main()
