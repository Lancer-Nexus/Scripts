#!/usr/bin/env bash
set -Eeuo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "$script_dir/.." && pwd)
tmp_dir=$(mktemp -d)
trap 'rm -rf -- "$tmp_dir"' EXIT

instance_env="$repo_dir/config/instance.env.example"
llserver_config="$repo_dir/config/llserver.instance.example.json"
agent_env="$repo_dir/config/agent.env.example"
validator="$repo_dir/bin/ln-validate-instance-config.sh"
healthcheck="$repo_dir/bin/ln-healthcheck-instance.sh"

"$validator" \
  --instance-env "$instance_env" \
  --llserver-config "$llserver_config" \
  --agent-env "$agent_env" >/dev/null

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
  '.WrittenAtUtc = $now | .IsReady = true | .CurrentPlayers = 3 | .Endpoint = .InstanceEndpoint' \
  "$llserver_config" > "$status_file"
"$healthcheck" --status-file "$status_file" --endpoint 10.20.0.31:2300 >/dev/null

not_ready_status="$tmp_dir/not-ready.json"
jq '.IsReady = false' "$status_file" > "$not_ready_status"
if "$healthcheck" --status-file "$not_ready_status" >/dev/null 2>&1; then
  echo "healthcheck accepted a not-ready instance" >&2
  exit 1
fi

echo "instance configuration validation tests passed"
