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
