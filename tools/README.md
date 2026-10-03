# Local transfer diagnostics

`first-client-e2e-heartbeat.py <run-directory>` registers the isolated LI01/LI02
test instances with Coordinator from their live LLServer status files. Source the
run directory's private `coordinator.env` before starting it. It requires Python 3
and uses the generated localhost CA; no additional packages are needed.

The reporter publishes separate private NPC QUIC endpoints and explicit ports,
using runtime status or legacy test configurations. Pass `--disable-npc-transfer`
when the test servers have no QUIC receiver. On one host, assign each LLServer a
distinct NPC port (for example 26455 and 26456). Stop with Ctrl+C. This helper is
for the isolated two-instance test environment; the eight-group baseline uses
the regular Agent workers.

Never include private environment files, passwords, bearer keys or certificates
in commits or logs. Stored snapshot inspection and mTLS handshake probes are
provided by Protocol's `tools/NpcTransferDiagnostics` project.

## Active copies and movement

Debug LLServer accepts the local console command `npc-state [NPC UUID]`. It
captures active identities, ownership versions, formation leaders and positions
between simulation updates and prints one `NPC_STATE` JSON line. This does not
open a network endpoint or pause the simulation.

`compare-npc-state.py` reads the last such line from each log (or a standalone JSON
sample) and compares two instances:

```bash
python3 tools/compare-npc-state.py source.log target.log --npc NPC-UUID
python3 tools/compare-npc-state.py before.log after.log --movement --npc NPC-UUID
```

Exit 0 means one active copy per selected ID, or measurable movement with an
unchanged ownership version. Exit 1 means that condition was not met; exit 2
means invalid samples. Repeat `--npc` to check every member of a formation.
Sample outside an in-flight handoff and verify the lease versions remain unchanged
across the sampling interval. Samples taken at different times are not a global
atomic snapshot and cannot independently prove absence of concurrent simulation.
