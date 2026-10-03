# Local NPC mission authority activation

Observed on 2026-10-03 in the existing isolated two-instance test environment.

- Protocol `3d7b86a`, Gateway `0607554`, Coordinator `1347938`.
- Both Release builds succeeded with zero warnings and zero errors.
- Gateway transfer writers were stopped before applying migration 005. The decision table was absent; there were zero character commit journal entries to backfill. NPC journals and leases were retained.
- A dedicated key was installed in the existing mode-0600 Gateway and Coordinator env files using the reusable configuration helper. No credentials were printed or committed.
- New service artifacts were staged in release directories and activated through symlinks, retaining the prior artifact directories for rollback. Existing LLServer processes, MySQL, Redis and heartbeat reporting continued running.
- Gateway and Coordinator `/health/ready` both returned HTTP 200 after restart.
- The private authority route returned 401 for no credential, an incorrect service credential and the source game-instance credential. With the correct service key, a fresh unknown character transfer returned HTTP 200 with `accepted=false` and `character_transfer_binding_mismatch`.
- The four private configuration helper tests passed.
- After the new Coordinator started at 10:17:55 UTC, a journal query observed six autonomous transfers from `li01` to `li02` and four in the opposite direction reaching `SourceReleased`. At that observation, zero NPC journals were in phases 2–6. This establishes continued journal completion through the deployed Coordinator, not a new movement or unique-active-copy measurement.

This is deployment/readiness/authentication evidence. It does not establish a successful coupled player/MissionRuntime/NPC transfer, exact AI continuation during that transfer, or recovery from every source/target/Coordinator crash phase. Those runtime acceptance checks remain open.
