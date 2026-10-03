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
