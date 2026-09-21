# AGENTS.md – Lancer Nexus Scripts

## Mission

Make deployments repeatable, auditable and safe across Linux machines.

## Rules

- Use strict shell mode and quote paths and variables.
- Validate arguments, artifacts, hashes and target paths before changing anything.
- Never execute arbitrary network-provided shell commands.
- Do not delete production data or reset MySQL/Redis from routine scripts.
- Use systemd for service lifecycle and support graceful draining.
- Keep secrets out of Git, command lines and logs.
- Make deployment and rollback steps idempotent.
- Use an atomic release-directory and `current`-symlink strategy.
- Run readiness checks after every deployment.

## Verification

Test scripts with shellcheck, a disposable Linux host and failure injection for interrupted uploads, failed health checks, service crashes and rollback.
