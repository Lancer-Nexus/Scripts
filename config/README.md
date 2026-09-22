# Example configuration data

These are templates, not production values. Replace `10.20.0.x` with the assigned private addresses and use a host-owned secret store for passwords, API keys and private keys. The `.example`/`.json` files contain no credentials. `topology.example.json` is the port/address reference; `../docs/route-map.md` states which paths are implemented versus planned.

| Project | Template | Inbound binding in the example | Status |
|---|---|---|---|
| Client | `client.example.json` | None; outbound HTTPS to Gateway | Cluster login settings are illustrative |
| Gateway | `gateway.env.example` | Public TCP 443 | Kestrel accepts these standard settings; auth/routing keys are planned |
| Coordinator | `coordinator.env.example` | Private TCP 8444 and optional UDP 7443 | HTTP/state/heartbeat settings are consumed; QUIC accepts Hello, AgentHeartbeat and InstanceHeartbeat streams |
| Agent | `agent.env.example`, `../systemd/lancer-nexus-agent.service` | None; outbound QUIC UDP 7443 to Coordinator | .NET worker sends mTLS Hello and sequenced Agent heartbeats; optional instance heartbeat reads the matching LLServer runtime-status file; host lifecycle remains unimplemented |
| Events | `events.env.example` | None | Template only; no standalone Events listener exists yet |
| Cluster | `cluster.example.json` | None; in-process integration | Disabled by default; template only |
| Protocol | In `topology.example.json` | None | Contract library, not a network service |
| Scripts | `hosts.example.env` | None | Deployment configuration; scripts must not open firewall ports implicitly |
| Game instance | `instance.env.example` | Private UDP 2300 | Example binding only; LLServer and Agent use the same 200-player limit and runtime-status path; never expose an instance directly to the public Internet |

`ASPNETCORE_URLS` and the standard `Kestrel__Certificates__Default__*` settings are consumed by the current ASP.NET Core hosts. Coordinator registry timeouts, reservation lifetimes, state-file path and QUIC options are also consumed. Agent QUIC endpoint, certificate, CA, heartbeat interval, capabilities, sequence-state and optional instance-status settings are consumed by the worker. Events, Client, Cluster and most Gateway-specific keys document intended configuration contracts only; do not assume they are active until those services implement them.

Before starting the Agent, create and restrict the parent directory of `Agent__StateFile` for the service account. Resolve `Agent__Coordinator__ServerName` to the configured private Coordinator address and issue the Coordinator certificate for that DNS name.

The sample public player endpoint on UDP 2300 is deliberately marked as planned. A Gateway/L4 game-traffic relay and per-instance port mapping have not been implemented. Do not publish game-instance ports or add them to a firewall based on this template alone.

For a live LLServer instance, map `LLSERVER_RUNTIME_STATUS_FILE`, `INSTANCE_ID`, `SYSTEM_ID`, `PRIVATE_BIND_ADDRESS` and `GAME_UDP_PORT` to the LLServer JSON fields `RuntimeStatusFile`, `InstanceId`, `SystemId` and `InstanceEndpoint`. Set `MaxPlayers` to `PUBLIC_PLAYER_LIMIT`; the Agent `Agent__Instance__MaxPlayers` must use the same value. The runtime-status file is host-local and must be writable by LLServer and readable by the Agent.
