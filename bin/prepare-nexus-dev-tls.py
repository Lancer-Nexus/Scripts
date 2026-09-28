#!/usr/bin/env python3
"""Provision a private local development CA and QUIC certificates; never change active services."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def run(*args):
    subprocess.run(["openssl", *map(str, args)], check=True, capture_output=True)


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
                   "Coordinator__Quic__RequiredCapabilities__0=cluster_handshake_v1\n")
    os.chmod(env, 0o600)
    print("Local development mTLS certificates and Coordinator QUIC environment prepared.")


if __name__ == "__main__":
    main()
