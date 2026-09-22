# Example configuration data

These are templates, not production values. Replace `10.20.0.x` with the assigned private addresses and use a host-owned secret store for passwords, API keys and private keys. The `.example`/`.json` files contain no credentials. `topology.example.json` is the port/address reference; `../docs/route-map.md` states which paths are implemented versus planned.

| Project | Template | Inbound binding in the example | Status |
|---|---|---|---|
| Client | `client.example.json` | None; outbound HTTPS to Gateway | Cluster login settings are illustrative |
| Gateway | `gateway.env.example` | Public TCP 443 | Kestrel accepts these standard settings; auth/routing keys are planned |
| Coordinator | `coordinator.env.example` | Private TCP 8444 and optional UDP 7443 | HTTP/state/heartbeat settings are consumed; QUIC settings configure the Hello listener |
| Agent | `agent.env.example` | None; outbound to Coordinator | Template only; Agent service implementation is not present yet |
| Events | `events.env.example` | None | Template only; no standalone Events listener exists yet |
| Cluster | `cluster.example.json` | None; in-process integration | Disabled by default; template only |
| Protocol | In `topology.example.json` | None | Contract library, not a network service |
| Scripts | `hosts.example.env` | None | Deployment configuration; scripts must not open firewall ports implicitly |
| Game instance | `instance.env.example` | Private UDP 2300 | Example binding only; never expose an instance directly to the public Internet |

`ASPNETCORE_URLS` and the standard `Kestrel__Certificates__Default__*` settings are consumed by the current ASP.NET Core hosts. Coordinator registry timeouts, reservation lifetimes, state-file path and QUIC options are also consumed. Agent, Events, Client, Cluster, and most Gateway-specific keys document intended configuration contracts only; do not assume they are active until those services implement them.

The sample public player endpoint on UDP 2300 is deliberately marked as planned. A Gateway/L4 game-traffic relay and per-instance port mapping have not been implemented. Do not publish game-instance ports or add them to a firewall based on this template alone.
