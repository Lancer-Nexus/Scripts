# AGENTS.md – Lancer Nexus Scripts

## Mission

Make deployments repeatable, auditable and safe across Linux machines.

## MVP architecture baseline

- Scripts owns safe host deployment and systemd lifecycle only; Agent owns host control, Coordinator owns placement, Gateway owns identity and game instances own live simulation.
- Deployment and draining must respect `Requested -> Reserved -> Prepared -> SourceFrozen -> TargetAccepted -> Committed -> SourceReleased`; never interrupt an in-flight transfer before its defined timeout or recovery handling.
- MySQL `lease_version` fencing protects character authority; Redis is non-authoritative transient infrastructure and must not be reset by deployment scripts.
- Release checks and service communication follow the versioned `Protocol` contracts and negotiated capabilities.

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
