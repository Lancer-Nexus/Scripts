# Lancer Nexus Scripts

The Scripts repository provides Linux host automation for Lancer Nexus services and game instances.

## Contents

- systemd units
- host installation and prerequisite checks
- release deployment and SHA256/signature verification
- start, stop, restart, status and log helpers
- draining, readiness checks and rollback
- example host and instance configuration

The scripts are designed for Linux hosts running the current .NET runtime. They may be invoked manually, over SSH or by CI/CD. MySQL and Redis remain external infrastructure and are never reset by a normal deployment.
