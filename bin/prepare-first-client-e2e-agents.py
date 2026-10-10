#!/usr/bin/env python3
"""Create private QUIC/mTLS configuration for the isolated two-instance E2E run."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


def run(*args: str | Path) -> None:
    subprocess.run(["openssl", *map(str, args)], check=True, capture_output=True)


def atomic_write(path: Path, content: str, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def verify_pkcs12_identity(pfx: Path, certificate: Path, directory: Path) -> None:
    extracted_certificate = directory / "pfx-certificate.crt"
    extracted_key = directory / "pfx-key.pem"
    certificate_public_key = directory / "certificate-public-key.der"
    pfx_public_key = directory / "pfx-public-key.der"
    run("pkcs12", "-in", pfx, "-clcerts", "-nokeys", "-passin", "pass:", "-out", extracted_certificate)
    run("pkcs12", "-in", pfx, "-nocerts", "-nodes", "-passin", "pass:", "-out", extracted_key)
    run("x509", "-in", certificate, "-pubkey", "-noout", "-out", directory / "certificate-public-key.pem")
    run("pkey", "-in", extracted_key, "-pubout", "-outform", "DER", "-out", pfx_public_key)
    run("pkey", "-pubin", "-in", directory / "certificate-public-key.pem", "-outform", "DER",
        "-out", certificate_public_key)
    if certificate_public_key.read_bytes() != pfx_public_key.read_bytes():
        raise ValueError(f"PFX private key does not match certificate {certificate.name}")
    run("x509", "-in", extracted_certificate, "-outform", "DER", "-out", directory / "pfx-certificate.der")
    run("x509", "-in", certificate, "-outform", "DER", "-out", directory / "certificate.der")
    if (directory / "pfx-certificate.der").read_bytes() != (directory / "certificate.der").read_bytes():
        raise ValueError(f"PFX certificate does not match {certificate.name}")


def issue_certificate(private: Path, ca_cert: Path, ca_key: Path, identity: str,
                      stem: str, eku: str) -> tuple[Path, Path]:
    certificate = private / f"{stem}.crt"
    pfx = private / f"{stem}.pfx"
    if certificate.exists() or pfx.exists():
        if not certificate.is_file() or not pfx.is_file():
            raise ValueError(f"Incomplete existing certificate for {identity}; refusing to replace it")
        run("verify", "-CAfile", ca_cert, "-purpose", "sslserver" if eku == "serverAuth" else "sslclient", certificate)
        run("x509", "-in", certificate, "-noout", "-checkhost", identity)
        with tempfile.TemporaryDirectory(prefix="first-e2e-pfx-check-", dir=private) as directory:
            verify_pkcs12_identity(pfx, certificate, Path(directory))
        os.chmod(pfx, 0o600)
        return certificate, pfx

    with tempfile.TemporaryDirectory(prefix="first-e2e-cert-", dir=private) as directory:
        temp = Path(directory)
        key = temp / "key.pem"
        csr = temp / "request.csr"
        ext = temp / "extensions.cnf"
        temp_cert = temp / "certificate.crt"
        temp_pfx = temp / "identity.pfx"
        ext.write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            f"extendedKeyUsage={eku}\n"
            f"subjectAltName=DNS:{identity}\n"
        )
        run("req", "-new", "-newkey", "rsa:2048", "-noenc", "-keyout", key,
            "-out", csr, "-subj", f"/CN={identity}")
        run("x509", "-req", "-in", csr, "-CA", ca_cert, "-CAkey", ca_key,
            "-CAcreateserial", "-days", "7", "-sha256", "-out", temp_cert, "-extfile", ext)
        run("pkcs12", "-export", "-out", temp_pfx, "-inkey", key, "-in", temp_cert,
            "-certfile", ca_cert, "-passout", "pass:")
        run("verify", "-CAfile", ca_cert, "-purpose", "sslserver" if eku == "serverAuth" else "sslclient", temp_cert)
        run("x509", "-in", temp_cert, "-noout", "-checkhost", identity)
        verify_pkcs12_identity(temp_pfx, temp_cert, temp)
        os.chmod(temp_pfx, 0o600)
        os.replace(temp_cert, certificate)
        os.replace(temp_pfx, pfx)
    return certificate, pfx


def parse_environment(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        match = re.fullmatch(r"export ([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if match is None:
            raise ValueError(f"Unsupported environment line {line_number} in {path.name}")
        values = shlex.split(match.group(2))
        if len(values) != 1:
            raise ValueError(f"Invalid environment assignment on line {line_number} in {path.name}")
        result[match.group(1)] = values[0]
    return result


def write_environment(path: Path, values: dict[str, str]) -> None:
    atomic_write(path, "".join(f"export {key}={shlex.quote(value)}\n" for key, value in sorted(values.items())))


def prepare(run_root: Path, coordinator_port: int) -> None:
    os.umask(0o077)
    run_root = run_root.resolve()
    workspace = Path(__file__).resolve().parents[2]
    allowed_roots = (Path("/tmp"), workspace / "output/dev")
    if not any(run_root == root.resolve() or root.resolve() in run_root.parents for root in allowed_roots):
        raise ValueError("Run directory must be under /tmp or the workspace's output/dev directory")
    if run_root.stat().st_mode & 0o077:
        raise ValueError("Run directory must not be accessible by group or other users")
    coordinator_env_path = run_root / "coordinator.env"
    if not coordinator_env_path.is_file():
        raise ValueError("coordinator.env is missing; run prepare-first-client-e2e.py first")
    coordinator_values = parse_environment(coordinator_env_path)
    instances = []
    for suffix, instance_id, expected_system in (("li01", "li01", "li01"), ("li02", "li02", "li03")):
        config_path = run_root / f"gameserver/llserver-{suffix}.json"
        server_env_path = run_root / f"gameserver/{suffix}.env"
        if not config_path.is_file() or not server_env_path.is_file():
            raise ValueError(f"Missing {suffix} LLServer configuration or environment")
        config = json.loads(config_path.read_text())
        if config.get("InstanceId") != instance_id or str(config.get("SystemId", "")).casefold() != expected_system:
            raise ValueError(f"{suffix} LLServer config must identify {instance_id}/{expected_system}")
        if type(config.get("MaxPlayers")) is not int or config["MaxPlayers"] <= 0 or not isinstance(config.get("InstanceEndpoint"), str) or not config["InstanceEndpoint"]:
            raise ValueError(f"{suffix} LLServer config has an invalid endpoint or player limit")
        server_values = parse_environment(server_env_path)
        instances.append((suffix, instance_id, expected_system, config_path, server_env_path, config, server_values))

    private = run_root / "agent-control"
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(private, 0o700)
    ca_cert = private / "control-ca.crt"
    ca_key = private / "control-ca.key"
    if ca_cert.exists() != ca_key.exists():
        raise ValueError("Incomplete existing control CA; refusing to replace it")
    if not ca_cert.exists():
        run("req", "-x509", "-newkey", "rsa:3072", "-noenc", "-days", "7",
            "-keyout", ca_key, "-out", ca_cert, "-subj", "/CN=First Client E2E Control CA",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
        os.chmod(ca_key, 0o600)
        os.chmod(ca_cert, 0o600)
    else:
        run("verify", "-CAfile", ca_cert, ca_cert)
        os.chmod(ca_key, 0o600)
        os.chmod(ca_cert, 0o600)

    _, coordinator_pfx = issue_certificate(private, ca_cert, ca_key, "localhost", "coordinator", "serverAuth")
    coordinator_values.update({
        "Coordinator__Quic__Enabled": "true",
        "Coordinator__Quic__ListenAddress": "127.0.0.1",
        "Coordinator__Quic__Port": str(coordinator_port),
        "Coordinator__Quic__NodeId": "first-e2e-coordinator",
        "Coordinator__Quic__InstanceId": "first-e2e-coordinator",
        "Coordinator__Quic__ServerCertificatePath": str(coordinator_pfx),
        "Coordinator__Quic__ServerCertificatePassword": "",
        "Coordinator__Quic__ClientCaCertificatePath": str(ca_cert),
        "Coordinator__Quic__RequiredCapabilities__0": "cluster_handshake_v1",
    })
    write_environment(coordinator_env_path, coordinator_values)

    for suffix, instance_id, expected_system, config_path, server_env_path, config, server_values in instances:
        node_id = f"first-e2e-{suffix}"
        agent_id = f"first-e2e-agent-{suffix}"
        _, client_pfx = issue_certificate(private, ca_cert, ca_key, node_id, f"{suffix}-agent", "clientAuth")
        config.update({
            "FlHookCompatEnabled": True,
            "FlHookCompatClusterEventsEnabled": True,
            "CoordinatorQuicEndpoint": f"127.0.0.1:{coordinator_port}",
            "CoordinatorQuicServerName": "localhost",
            "ClusterAgentNodeId": node_id,
            "CoordinatorQuicClientCertificate": str(client_pfx),
            "CoordinatorQuicCaCertificate": str(ca_cert),
            "FlHookCompatTrustRootFile": str(private / "flhook-trust-root.json"),
            "FlHookCompatEventCursorFile": str(run_root / f"gameserver/{suffix}-flhook-events.cursor.json"),
            "FlHookCompatEventOutboxFile": str(run_root / f"gameserver/{suffix}-flhook-events.outbox.jsonl"),
        })
        atomic_write(config_path, json.dumps(config, indent=2) + "\n", 0o600)
        values = {
            "ASPNETCORE_ENVIRONMENT": "Production",
            "Agent__NodeId": node_id,
            "Agent__AgentId": agent_id,
            "Agent__BuildVersion": "local-e2e",
            "Agent__Coordinator__QuicEndpoint": f"127.0.0.1:{coordinator_port}",
            "Agent__Coordinator__ServerName": "localhost",
            "Agent__Coordinator__ClientCertificatePath": str(client_pfx),
            "Agent__Coordinator__ClientCertificatePassword": "",
            "Agent__Coordinator__CaCertificatePath": str(ca_cert),
            "Agent__Coordinator__HeartbeatIntervalSeconds": "2",
            "Agent__Instance__StatusFile": str(run_root / f"gameserver/{suffix}-instance-status.json"),
            "Agent__Instance__InstanceId": instance_id,
            "Agent__Instance__SystemId": expected_system,
            "Agent__Instance__Endpoint": config["InstanceEndpoint"],
            "Agent__Instance__MaxPlayers": str(config["MaxPlayers"]),
            "Agent__Capabilities__0": "cluster_handshake_v1",
            "Agent__Capabilities__1": "agent_heartbeat_v1",
            "Agent__Capabilities__2": "instance_heartbeat_v1",
            "Agent__Capabilities__3": "flhook_events_v1",
            "Agent__StateFile": str(private / f"{suffix}-heartbeat-sequence.txt"),
        }
        write_environment(private / f"{suffix}-agent.env", values)
        server_values["LANCER_NEXUS_COORDINATOR_QUIC_CLIENT_CERT_PASSWORD"] = ""
        write_environment(server_env_path, server_values)

    trust_root_path = private / "flhook-trust-root.json"
    if not trust_root_path.exists():
        atomic_write(trust_root_path, json.dumps({"Schema": 1, "Threshold": 1, "Keys": []}, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--coordinator-port", type=int, default=27443)
    args = parser.parse_args()
    if not 1 <= args.coordinator_port <= 65535:
        parser.error("--coordinator-port must be between 1 and 65535")
    try:
        prepare(args.run_dir, args.coordinator_port)
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"Prepared two real-Agent QUIC/mTLS configs under {args.run_dir.resolve() / 'agent-control'}.")


if __name__ == "__main__":
    main()
