# Nexus baseline

One game instance hosts each system group. All systems share that instance's player capacity, database and UDP endpoint. A jump inside the group is local; a jump to another group uses the existing fenced transfer lifecycle.

| Instance | Worlds | Local UDP port |
|---|---|---|
| br-01 | BR01–BR06 | 26000 |
| bw-01 | BW01–BW10 | 26001 |
| ew-01 | EW01–EW05 | 26002 |
| iw-01 | IW01–IW06 | 26003 |
| ku-01 | KU01–KU06 | 26004 |
| li-01 | LI01–LI05 | 26005 |
| rh-01 | RH01–RH05 | 26006 |
| mixed-01 | EW06, FP7_system, HI01, HI02, KU07, ST01, ST02, ST02c, ST03, ST03b | 26007 |

The current inventory contains 53 registered worlds and 55 SYSTEMS directories. Mixed also accounts for `intro` and `miners`, which contain assets but are not registered worlds. Folder `fp7` is mapped through universe.ini to `fp7_system`. New registered worlds outside the explicit ranges are assigned to Mixed on the next preparation.

## Prepare

From the containing workspace:

```bash
python3 Scripts/bin/prepare-nexus-baseline.py \
  --game output/dev/client --output output/dev/nexus \
  --state-root runtime/nexus/dev
```

The collector performs this step for both dev and release outputs. Persistent databases, private keys and Agent sequence files stay in `runtime/nexus/<variant>`, outside the collected release tree. Repeated preparation preserves keys and database files. `config/nexus-baseline.json` is the committed inventory snapshot; the generated `topology.json` carries deployment-specific absolute paths.

Defaults: 127.0.0.1, UDP 26000–26007, 200 players per group, Gateway `https://localhost:38443`, Coordinator QUIC `127.0.0.1:7443`. Use `--bind`, `--first-port`, `--max-players`, `--gateway`, `--node`, `--coordinator` and `--coordinator-name` for another private host. No firewall or active service changes are made by preparation.

For a Gateway signed by a private development CA, pass `--gateway-ca /path/to/gateway-ca.pem` once. The certificate is copied into persistent state and the generated server starter sets `SSL_CERT_FILE`. Repeated collection retains that trust file. This is separate from the QUIC mTLS CA. The local prepared configurations already contain the current E2E Gateway trust certificate.

Each group receives LLServer JSON, Agent JSON, private instance environment, Agent environment, and an isolated database/status directory. The private `gateway-instances.env` file points `Gateway__GameInstanceKeysFile` at the private JSON key map. Load this environment into the updated Gateway before starting group servers; a key file avoids invalid shell variable names for IDs containing hyphens. Existing configured keys are retained and file entries override matching IDs. Keep the private files out of Git and logs; the generator uses mode 0600 and a private directory with mode 0700.

## Start a prepared component

The generated local starter also accepts `output/dev/nexus/run.sh instance br-01` or `output/dev/nexus/run.sh agent br-01`.

Build and collect the updated LLServer, Agent and Coordinator first. Do not run an old binary with these multi-system configurations.

```bash
python3 Scripts/bin/run-nexus-component.py instance br-01 \
  --root output/dev/nexus --app-dir output/dev/server/llserver

python3 Scripts/bin/run-nexus-component.py agent br-01 \
  --root output/dev/nexus --app-dir output/dev/agent/agent
```

The Agent still reports one instance per process. Start one Agent per group, using the distinct generated Agent IDs and sequence files. Before Agent start, provision the node client certificate and cluster CA at the generated private paths, with the certificate DNS SAN matching NodeId. Enable the Coordinator QUIC listener with its matching server certificate/client CA using `config/coordinator.env.example`. Preparation does not invent ready heartbeats. For the prepared local dev/release configurations, local development certificates are provisioned separately with:

```bash
python3 Scripts/bin/prepare-nexus-dev-tls.py --root output/dev/nexus
```

The helper preserves an existing development CA and writes `coordinator-quic.env` alongside the private keys. Load it into Coordinator on activation. For production, provision the deployment CA/certificates through the host operator instead of using the local development CA.

Game instances are eligible for placement only after fresh, authenticated Agent heartbeats report the exact owned system set. Capacity is shared across all worlds of a group. Existing single-world LLServer/Agent configurations continue to work.

The old `li01`/`li02` E2E instances are separate from baseline `li-01`. Adopting the new baseline requires draining the old instances and transferring existing characters through the authoritative lease protocol. Do not rewrite their leases or run overlapping deployments as if they shared authority. The existing E2E services are left running by preparation.

## Validate

```bash
Scripts/bin/ln-validate-instance-config.sh \
  --instance-env runtime/nexus/dev/private/br-01.env \
  --llserver-config output/dev/nexus/config/br-01.json \
  --agent-env runtime/nexus/dev/private/br-01.agent.env
```

Repeat for each instance. The check includes the complete system set, endpoint, player limit and status path. Inspect actual fresh runtime snapshots before considering any instance online.
