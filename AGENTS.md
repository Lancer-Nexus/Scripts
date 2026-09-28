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
- Service wrappers must allowlist unit names and actions; never pass arbitrary systemd arguments through.
- Do not delete production data or reset MySQL/Redis from routine scripts.
- Use systemd for service lifecycle and support graceful draining.
- Keep secrets out of Git, command lines and logs.
- Make deployment and rollback steps idempotent.
- Use an atomic release-directory and `current`-symlink strategy.
- Run readiness checks after every deployment.
- Readiness checks must fail closed for missing, stale, malformed or over-capacity instance status.
- Validate instance, LLServer and Agent configuration together before enabling an instance.
- Keep example topology, bind addresses and ports aligned with `config/topology.example.json` and `docs/route-map.md`; never imply an unimplemented route is live.
- Ignore real secrets and certificate files in Git while retaining `.example` templates.

## Verification

Test scripts with shellcheck, the repository validation tests, a disposable Linux host and failure injection for interrupted uploads, failed health checks, service crashes and rollback.

## Working-model escalation

- If a task requires complex reasoning beyond the current model's reliable scope, ask the user whether switching to a stronger model is desired before continuing.
- Do not switch models silently or broaden the task because a stronger model may be useful.

## Nexus baseline system groups

The base Nexus topology uses eight game instances, one per group: BR01-BR06 (`br-01`), BW01-BW10 (`bw-01`), EW01-EW05 (`ew-01`), IW01-IW06 (`iw-01`), KU01-KU06 (`ku-01`), LI01-LI05 (`li-01`), RH01-RH05 (`rh-01`), and `mixed-01` for all remaining registered systems. System nicknames are compared case insensitively and emitted lowercase. Folder names are not always world nicknames: `fp7` contains `fp7_system`; `intro` and `miners` are asset directories, not registered worlds.
Generate the full baseline from the collected Freelancer DATA and universe.ini, assign every registered world exactly once, and include all leftover SYSTEMS directories in Mixed. Keep database files, keys and Agent sequence state outside replaceable build output (`runtime/nexus/<variant>` in the workspace). Collect regenerates configuration and preserves private keys. Never advertise intro/miners as worlds or infer fp7_system from the directory name alone. Each group has its own LLServer config, Agent config, private key, database, status path and UDP port. Prepare does not enable systemd or start services; QUIC requires provisioned mTLS certificates.
