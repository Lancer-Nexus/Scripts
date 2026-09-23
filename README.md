# Lancer Nexus Scripts

The Scripts repository provides Linux host automation for Lancer Nexus services and game instances.

## Contents

- systemd units
- host installation and prerequisite checks
- release deployment and SHA256/signature verification
- start, stop, restart, status and log helpers
- draining, readiness checks and rollback
- example configuration for every project and the network topology
- the implemented/planned service route map

The scripts are designed for Linux hosts running the current .NET runtime. They may be invoked manually, over SSH or by CI/CD. MySQL and Redis remain external infrastructure and are never reset by a normal deployment.

See [`config/README.md`](config/README.md) for per-project templates and [`docs/route-map.md`](docs/route-map.md) for bind addresses, ports, API routes and implementation status. Example addresses are placeholders; templates do not change firewall rules or open ports.

## Agent systemd unit

`systemd/lancer-nexus-agent.service` runs the existing outbound-only Agent worker as the unprivileged `lancer` user. It creates the persistent sequence directory `/var/lib/lancer-nexus-agent` and reads the host-local runtime directory `/run/lancer-nexus` used by the LLServer status snapshot. Install `tmpfiles.d/lancer-nexus.conf` before starting services so both units share that directory. The Agent unit does not start or stop game instances and does not open inbound ports.

Install the unit only after placing the published Agent release at `/opt/lancer-nexus/current/agent/` and creating `/etc/lancer-nexus/agent.env` from the example. Then validate and enable it explicitly:

```bash
systemd-analyze verify systemd/lancer-nexus-agent.service
sudo install -o root -g root -m 0644 tmpfiles.d/lancer-nexus.conf /etc/tmpfiles.d/lancer-nexus.conf
sudo systemd-tmpfiles --create /etc/tmpfiles.d/lancer-nexus.conf
sudo install -o root -g root -m 0644 systemd/lancer-nexus-agent.service /etc/systemd/system/lancer-nexus-agent.service
sudo systemctl daemon-reload
sudo systemctl enable lancer-nexus-agent.service
```

Starting the unit is intentionally a separate operator action. Certificate files and `agent.env` remain outside the release directory and must be readable by the `lancer` service account without putting private keys or passwords in Git.

`systemd/lancer-nexus-instance@.service` is an operator-managed LLServer template. Enable an instance only after placing `/opt/lancer-nexus/current/client/LLServer`, `/opt/lancer-nexus/current/scripts/bin/ln-validate-instance-config.sh`, `/opt/lancer-nexus/current/scripts/bin/ln-wait-instance-ready.sh`, `/etc/lancer-nexus/instances/<id>.json`, `/etc/lancer-nexus/instances/<id>.env` and `/var/lib/lancer-nexus/instances/<id>/` in place. The unit runs the configuration preflight before every start; the JSON must set `RuntimeStatusFile` to the shared runtime directory and keep `InstanceEndpoint` private. This unit is not a remote Agent lifecycle implementation; it does not add a public listener or a Gateway relay.

After LLServer starts, the unit waits up to 90 seconds for the fresh runtime snapshot to pass `ln-healthcheck-instance.sh`. A server that never becomes ready is stopped by systemd and remains failed for operator diagnosis.

Before enabling an instance, validate the cross-repository settings without sourcing configuration as shell code:

```bash
./bin/ln-validate-instance-config.sh \
  --instance-env config/instance.env.example \
  --llserver-config config/llserver.instance.example.json \
  --agent-env config/agent.env.example
```

The check compares instance ID, system ID, private endpoint, player limit and runtime-status path. It requires `jq` and exits non-zero on missing, malformed or inconsistent values.

Run the repository-level validation test with:

```bash
./tests/test-instance-config.sh
```

The repository CI runs this test, ShellCheck and structural systemd validation on every push and pull request. CI substitutes placeholder executable paths only for unit parsing; deployment paths are not changed in the committed units.

After starting an instance, check its actual runtime readiness with:

```bash
./bin/ln-healthcheck-instance.sh \
  --status-file /run/lancer-nexus/liberty-01.status.json \
  --endpoint 10.20.0.31:2300
```

The check fails closed for missing, stale, malformed, not-ready or over-capacity status data.

Use `bin/ln-service.sh` for the supported service operations. It accepts only the existing Agent unit or an instance template:

```bash
./bin/ln-service.sh agent status
./bin/ln-service.sh instance:liberty-01 restart
./bin/ln-service.sh instance:liberty-01 logs
```

The wrapper validates instance IDs and does not accept arbitrary unit names or shell text. Gateway and Coordinator units are intentionally not exposed until their deployment units exist.
