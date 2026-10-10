#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "$script_dir/.." && pwd)
tmp_dir=$(mktemp -d)
trap 'rm -rf -- "$tmp_dir"' EXIT

instance_env="$tmp_dir/instance.env"
sed 's/^LANCER_NEXUS_GAME_INSTANCE_KEY=$/LANCER_NEXUS_GAME_INSTANCE_KEY=0123456789abcdef0123456789abcdef/' "$repo_dir/config/instance.env.example" > "$instance_env"
llserver_config="$repo_dir/config/llserver.instance.example.json"
agent_env="$repo_dir/config/agent.env.example"
validator="$repo_dir/bin/ln-validate-instance-config.sh"
healthcheck="$repo_dir/bin/ln-healthcheck-instance.sh"
http_healthcheck="$repo_dir/bin/ln-healthcheck-http.sh"

"$validator" \
  --instance-env "$instance_env" \
  --llserver-config "$llserver_config" \
  --agent-env "$agent_env" >/dev/null

missing_redis_env="$tmp_dir/missing-redis.env"
grep -v '^LANCER_NEXUS_PERMISSION_REDIS_ENDPOINT=' "$instance_env" > "$missing_redis_env"
if "$validator" --instance-env "$missing_redis_env" --llserver-config "$llserver_config" --agent-env "$agent_env" >/dev/null 2>&1; then
  echo "validator accepted a missing permission Redis endpoint" >&2
  exit 1
fi
short_key_env="$tmp_dir/short-key.env"
sed 's/^LANCER_NEXUS_GAME_INSTANCE_KEY=.*/LANCER_NEXUS_GAME_INSTANCE_KEY=too-short/' "$instance_env" > "$short_key_env"
if "$validator" --instance-env "$short_key_env" --llserver-config "$llserver_config" --agent-env "$agent_env" >/dev/null 2>&1; then
  echo "validator accepted a short per-instance Gateway key" >&2
  exit 1
fi
bad_redis_env="$tmp_dir/bad-redis.env"
sed 's/^LANCER_NEXUS_PERMISSION_REDIS_ENDPOINT=.*/LANCER_NEXUS_PERMISSION_REDIS_ENDPOINT=redis.invalid:70000/' "$instance_env" > "$bad_redis_env"
if "$validator" --instance-env "$bad_redis_env" --llserver-config "$llserver_config" --agent-env "$agent_env" >/dev/null 2>&1; then
  echo "validator accepted an invalid permission Redis port" >&2
  exit 1
fi

bad_agent_env="$tmp_dir/agent.env"
sed 's/^Agent__Instance__MaxPlayers=200$/Agent__Instance__MaxPlayers=201/' "$agent_env" > "$bad_agent_env"
if "$validator" \
  --instance-env "$instance_env" \
  --llserver-config "$llserver_config" \
  --agent-env "$bad_agent_env" >/dev/null 2>&1; then
  echo "validator accepted a mismatched Agent player limit" >&2
  exit 1
fi

status_file="$tmp_dir/status.json"
jq --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '.WrittenAtUtc = $now | .IsReady = true | .PermissionsReady = true | .PermissionRevision = 1 | .CurrentPlayers = 3 | .Endpoint = .InstanceEndpoint' \
  "$llserver_config" > "$status_file"
"$healthcheck" --status-file "$status_file" --endpoint 10.20.0.31:2300 >/dev/null

missing_permission_status="$tmp_dir/missing-permission-readiness.json"
jq 'del(.PermissionsReady)' "$status_file" > "$missing_permission_status"
if "$healthcheck" --status-file "$missing_permission_status" >/dev/null 2>&1; then
  echo "healthcheck accepted a status without permission readiness" >&2
  exit 1
fi

not_ready_status="$tmp_dir/not-ready.json"
jq '.IsReady = false' "$status_file" > "$not_ready_status"
if "$healthcheck" --status-file "$not_ready_status" >/dev/null 2>&1; then
  echo "healthcheck accepted a not-ready instance" >&2
  exit 1
fi

stale_status="$tmp_dir/stale.json"
jq '.WrittenAtUtc = "2000-01-01T00:00:00Z"' "$status_file" > "$stale_status"
if "$healthcheck" --status-file "$stale_status" >/dev/null 2>&1; then
  echo "healthcheck accepted a stale instance" >&2
  exit 1
fi

over_capacity_status="$tmp_dir/over-capacity.json"
jq '.CurrentPlayers = .MaxPlayers + 1' "$status_file" > "$over_capacity_status"
if "$healthcheck" --status-file "$over_capacity_status" >/dev/null 2>&1; then
  echo "healthcheck accepted an over-capacity instance" >&2
  exit 1
fi

if "$http_healthcheck" --url http://127.0.0.1/health/ready >/dev/null 2>&1; then
  echo "HTTP healthcheck accepted an insecure URL" >&2
  exit 1
fi

echo "instance configuration validation tests passed"
