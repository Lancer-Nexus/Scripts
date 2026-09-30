#!/usr/bin/env python3
"""Provision a private local development CA and QUIC certificates; never change active services."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile


def run(*args):
    return subprocess.run(["openssl", *map(str, args)], check=True, capture_output=True)


def provision_npc_transfer_certificates(private, ca, ca_key, groups):
    cert_dir = private / "npc-transfer-certs"
    cert_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(cert_dir, 0o700)
    trust = cert_dir / "npc-transfer-ca.crt"
    if trust.exists():
        if trust.read_bytes() != ca.read_bytes():
            raise ValueError("Existing NPC transfer CA differs from the preserved development CA")
    else:
        trust.write_bytes(ca.read_bytes())
    os.chmod(trust, 0o600)

    identities = [group["instanceId"] for group in groups]
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,127}", identity) for identity in identities):
        raise ValueError("NPC transfer instance IDs must be valid DNS certificate identities")
    for identity in identities:
        pfx = cert_dir / f"{identity}.pfx"
        crt = cert_dir / f"{identity}.crt"
        if pfx.exists() != crt.exists():
            raise ValueError(f"Incomplete NPC transfer certificate for {identity}; refusing to replace it")
        if not pfx.exists():
            with tempfile.TemporaryDirectory(prefix="nexus-npc-tls-", dir=cert_dir) as directory:
                temp = Path(directory)
                key = temp / "key.pem"
                csr = temp / "request.csr"
                temp_pfx = temp / f"{identity}.pfx"
                temp_crt = temp / f"{identity}.crt"
                ext = temp / "extensions.cnf"
                ext.write_text(
                    "basicConstraints=critical,CA:FALSE\n"
                    "keyUsage=critical,digitalSignature,keyEncipherment\n"
                    "extendedKeyUsage=clientAuth,serverAuth\n"
                    f"subjectAltName=DNS:{identity}\n")
                run("req", "-new", "-newkey", "rsa:2048", "-noenc", "-keyout", key,
                    "-out", csr, "-subj", f"/CN={identity}")
                run("x509", "-req", "-in", csr, "-CA", ca, "-CAkey", ca_key, "-CAcreateserial",
                    "-days", "365", "-out", temp_crt, "-extfile", ext)
                run("pkcs12", "-export", "-out", temp_pfx, "-inkey", key, "-in", temp_crt, "-certfile", ca,
                    "-passout", "pass:")
                run("verify", "-CAfile", trust, "-purpose", "sslclient", temp_crt)
                run("verify", "-CAfile", trust, "-purpose", "sslserver", temp_crt)
                run("x509", "-in", temp_crt, "-noout", "-checkhost", identity)
                os.chmod(temp_pfx, 0o600)
                os.replace(temp_crt, crt)
                os.replace(temp_pfx, pfx)
        run("verify", "-CAfile", trust, "-purpose", "sslclient", crt)
        run("verify", "-CAfile", trust, "-purpose", "sslserver", crt)
        run("x509", "-in", crt, "-noout", "-checkhost", identity)
        os.chmod(pfx, 0o600)
    return cert_dir


def local_coordinator_api_key(private):
    path = private / "npc-coordinator-api-key"
    if path.exists():
        key = path.read_text().strip()
        if len(key.encode("utf-8")) < 32:
            raise ValueError("Existing local Coordinator API key is too short; refusing to replace it")
        os.chmod(path, 0o600)
        return key
    key = secrets.token_urlsafe(48)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(key + "\n")
    return key


def write_secret_environment(private, api_key):
    path = private / "instance-secrets.env"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".instance-secrets.", dir=private)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as output:
            output.write("LANCER_NEXUS_COORDINATOR_API_KEY=" + api_key + "\n")
            output.write("LANCER_NEXUS_NPC_TRANSFER_CERT_PASSWORD=\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    os.chmod(path, 0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads((args.root.resolve() / "topology.json").read_text())
    agent = json.loads(Path(plan["instances"][0]["agentConfig"]).read_text())["Agent"]
    node = agent["NodeId"]
    coordinator = agent["Coordinator"]["ServerName"]
    for name in [node, coordinator]:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,127}", name):
            parser.error("Certificate identities must be DNS names")
    private = Path(plan["privateRoot"])
    os.umask(0o077)
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    ca = private / "cluster-ca.crt"
    ca_key = private / "cluster-ca.key"
    if ca.exists() != ca_key.exists():
        parser.error("Incomplete existing CA; refusing to replace it")
    if not ca.exists():
        run("req", "-x509", "-newkey", "rsa:3072", "-noenc", "-days", "365",
            "-keyout", ca_key, "-out", ca, "-subj", "/CN=Nexus local development CA",
            "-addext", "basicConstraints=critical,CA:TRUE", "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    npc_cert_dir = provision_npc_transfer_certificates(private, ca, ca_key, plan["instances"])
    api_key = local_coordinator_api_key(private)
    write_secret_environment(private, api_key)
    for identity, stem, purpose in [(node, node, "clientAuth"), (coordinator, "coordinator-quic", "serverAuth")]:
        pfx = private / f"{stem}.pfx"
        crt = private / f"{stem}.crt"
        if pfx.exists() != crt.exists():
            parser.error("Incomplete existing leaf certificate; refusing to replace it")
        if not pfx.exists():
            with tempfile.TemporaryDirectory(prefix="nexus-tls-") as directory:
                temp = Path(directory)
                key = temp / "key.pem"
                csr = temp / "request.csr"
                ext = temp / "extensions.cnf"
                ext.write_text(f"basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
                               f"extendedKeyUsage={purpose}\nsubjectAltName=DNS:{identity}\n")
                run("req", "-new", "-newkey", "rsa:2048", "-noenc", "-keyout", key,
                    "-out", csr, "-subj", f"/CN={identity}")
                run("x509", "-req", "-in", csr, "-CA", ca, "-CAkey", ca_key, "-CAcreateserial",
                    "-days", "365", "-out", crt, "-extfile", ext)
                run("pkcs12", "-export", "-out", pfx, "-inkey", key, "-in", crt, "-certfile", ca,
                    "-passout", "pass:")
        run("verify", "-CAfile", ca, "-purpose", "sslclient" if purpose == "clientAuth" else "sslserver", crt)
        run("x509", "-in", crt, "-noout", "-checkhost", identity)
        os.chmod(pfx, 0o600)
    endpoint = agent["Coordinator"]["QuicEndpoint"]
    address, port = endpoint.rsplit(":", 1)
    env = private / "coordinator-quic.env"
    env.write_text(f"Coordinator__Quic__Enabled=true\nCoordinator__Quic__ListenAddress={address}\n"
                   f"Coordinator__Quic__Port={int(port)}\nCoordinator__Quic__NodeId=coordinator-01\n"
                   f"Coordinator__Quic__InstanceId=coordinator-01\n"
                   f"Coordinator__Quic__ServerCertificatePath={private / 'coordinator-quic.pfx'}\n"
                   f"Coordinator__Quic__ClientCaCertificatePath={ca}\n"
                   f"Coordinator__InternalApiKey={api_key}\n"
                   "Coordinator__Quic__RequiredCapabilities__0=cluster_handshake_v1\n")
    os.chmod(env, 0o600)
    print(f"Local development mTLS certificates prepared, including NPC transfer identities in {npc_cert_dir}.")


if __name__ == "__main__":
    main()
