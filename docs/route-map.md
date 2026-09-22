# Lancer Nexus route map

This map separates implemented listeners from intended routes. Sample private addresses come from `config/topology.example.json`; they are not assigned production addresses. Default-deny firewalls should allow only the implemented routes needed by the deployed roles.

## Network paths

| Source | Destination | Transport / port | Purpose | State |
|---|---|---|---|---|
| Client | `gateway.example.net` | HTTPS/TCP 443 | Login, session and API entry | Gateway listener exists; only health and capability routes are implemented |
| Gateway | Coordinator private address | HTTPS/TCP 8444 | Placement and transfer control | Coordinator HTTP endpoints exist; Gateway client integration is not implemented |
| Agent | Coordinator private address | QUIC/TLS 1.3/mTLS, ALPN `lancer-nexus-control/1`, UDP 7443 | Hello negotiation and sequenced AgentHeartbeat requests/acks on one bidirectional stream per message | Implemented in Agent worker and Coordinator; reconnect uses bounded backoff; instance heartbeats and lifecycle commands remain unimplemented |
| Legacy Agent HTTP client | Coordinator private address | HTTPS/TCP 8444, `POST /internal/v1/agents/heartbeat` | Compatibility HTTP heartbeat endpoint | Implemented and bearer-protected; the current Agent worker uses QUIC |
| Coordinator | Agent | No inbound route | Future lifecycle commands | Not implemented; Agent should remain outbound-only |
| Client | Assigned game endpoint | UDP 2300 via `gateway.example.net` | Game packets | Planned only; no Gateway/L4 relay or per-instance mapping exists |
| Game instance | Its private host interface | UDP 2300 | Private game listener | Deployment example only; do not make it public |
| Gateway | MySQL / Redis on private addresses | TCP 3306 / TCP 6379 | Identity/character and transient session data | Planned; current Gateway does not connect to either service |
| Coordinator | MySQL on private address | TCP 3306 | Durable shared cluster state for later replicas | Planned; current Coordinator uses its local filesystem store |
| Events | MySQL / Redis on private addresses | TCP 3306 / TCP 6379 | Durable event state and transient event distribution | Planned; Events has no runtime integration yet |
| Events | Gateway / Coordinator APIs | HTTPS on private routes | Registration, reservation and result flow | Planned; Events has no standalone listener |
| Cluster integration | In-process host | No separate port | Optional LibreLancer hooks | Planned; disabled by default |
| Protocol | None | No port | Shared contracts and negotiation logic | Library only |
| Scripts | None | No port | Host deployment/systemd operations | Tooling only |

The client-game path remains an architecture gap: the cluster design forbids public direct instance ports, while the login-plan example returns `gateway.example.net:2300`. Until the relay and port-allocation design is implemented, keep game UDP private and do not advertise a usable public game endpoint.

## Implemented HTTP routes

| Service | Method | Path | Exposure |
|---|---|---|---|
| Gateway | GET | `/health/live` | Public listener; liveness only |
| Gateway | GET | `/health/ready` | Public listener; readiness |
| Gateway | GET | `/api/v1/capabilities` | Public listener |
| Coordinator | GET | `/health/live` | Private service listener |
| Coordinator | GET | `/health/ready` | Private service listener |
| Coordinator | GET | `/api/v1/capabilities` | Private service listener |
| Coordinator | POST | `/internal/v1/agents/heartbeat` | Private HTTPS + bearer key |
| Coordinator | POST | `/internal/v1/instances/heartbeat` | Private HTTPS + bearer key |
| Coordinator | GET | `/internal/v1/registry` | Private HTTPS + bearer key |
| Coordinator | POST | `/api/v1/placement` | Private HTTPS + bearer key |

The login, refresh, character, transfer, group and event routes in the architecture plan are not implemented in the current Gateway skeleton. They must not be put in an ingress allowlist as if they existed.

## Binding and firewall rules

- Gateway binds to `0.0.0.0:443/tcp` in the template; the host firewall should expose it only on the intended public interface and terminate HTTPS with a valid certificate.
- Coordinator HTTP binds to its private interface on `8444/tcp`; bearer-protected routes still require TLS. Do not bind them publicly.
- Coordinator QUIC binds to its private interface on `7443/udp` only when mTLS certificate configuration is complete. Client identity is the single DNS SAN that matches `ClusterHello.NodeId` and `AgentHeartbeat.NodeId`.
- Agent has no inbound listener. Allow its outbound UDP/7443 path only to the configured Coordinator; store its monotonic heartbeat sequence in persistent local state.
- Do not open UDP/2300 publicly until the Gateway game-traffic relay and destination mapping exist.
- MySQL/Redis are external dependencies; their ports are not opened by these templates or deployment scripts.
