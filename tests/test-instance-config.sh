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

echo "instance configuration validation tests passed"
