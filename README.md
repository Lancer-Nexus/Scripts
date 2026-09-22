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

`systemd/lancer-nexus-agent.service` runs the existing outbound-only Agent worker as the unprivileged `lancer` user. It creates the persistent sequence directory `/var/lib/lancer-nexus-agent` and the host-local runtime directory `/run/lancer-nexus` used by the LLServer status snapshot. The unit does not start or stop game instances and does not open inbound ports.

Install the unit only after placing the published Agent release at `/opt/lancer-nexus/current/agent/` and creating `/etc/lancer-nexus/agent.env` from the example. Then validate and enable it explicitly:

```bash
systemd-analyze verify systemd/lancer-nexus-agent.service
sudo install -o root -g root -m 0644 systemd/lancer-nexus-agent.service /etc/systemd/system/lancer-nexus-agent.service
sudo systemctl daemon-reload
sudo systemctl enable lancer-nexus-agent.service
```

Starting the unit is intentionally a separate operator action. Certificate files and `agent.env` remain outside the release directory and must be readable by the `lancer` service account without putting private keys or passwords in Git.
