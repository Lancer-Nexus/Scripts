#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 --instance-env FILE --llserver-config FILE [--agent-env FILE]" >&2
}

instance_env=''
llserver_config=''
agent_env=''
while (($# > 0)); do
  case "$1" in
    --instance-env)
      (($# >= 2)) || { usage; exit 64; }
      instance_env=$2; shift 2 ;;
    --llserver-config)
      (($# >= 2)) || { usage; exit 64; }
      llserver_config=$2; shift 2 ;;
    --agent-env)
      (($# >= 2)) || { usage; exit 64; }
      agent_env=$2; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      usage; exit 64 ;;
  esac
done

[[ -n "$instance_env" && -n "$llserver_config" ]] || { usage; exit 64; }
[[ -r "$instance_env" ]] || { echo "instance env is not readable: $instance_env" >&2; exit 66; }
[[ -r "$llserver_config" ]] || { echo "LLServer config is not readable: $llserver_config" >&2; exit 66; }
if [[ -n "$agent_env" && ! -r "$agent_env" ]]; then
  echo "agent env is not readable: $agent_env" >&2
  exit 66
fi
command -v jq >/dev/null || { echo "jq is required" >&2; exit 69; }

env_value() {
  local file=$1 key=$2 value
  value=$(awk -F= -v wanted="$key" '
    $0 !~ /^[[:space:]]*#/ && $1 == wanted {
      sub(/^[^=]*=/, ""); print; exit
    }
  ' "$file")
  printf '%s' "$value"
}

require_value() {
  local name=$1 value=$2
  [[ -n "$value" ]] || { echo "missing $name" >&2; exit 65; }
}

instance_id=$(env_value "$instance_env" INSTANCE_ID)
system_id=$(env_value "$instance_env" SYSTEM_ID)
private_ip=$(env_value "$instance_env" PRIVATE_BIND_ADDRESS)
game_port=$(env_value "$instance_env" GAME_UDP_PORT)
player_limit=$(env_value "$instance_env" PUBLIC_PLAYER_LIMIT)
status_file=$(env_value "$instance_env" LLSERVER_RUNTIME_STATUS_FILE)
for required in instance_id system_id private_ip game_port player_limit status_file; do
  require_value "$required" "${!required}"
done
[[ "$game_port" =~ ^[0-9]+$ && "$game_port" -ge 1 && "$game_port" -le 65535 ]] || { echo "invalid GAME_UDP_PORT" >&2; exit 65; }
[[ "$player_limit" =~ ^[0-9]+$ && "$player_limit" -gt 0 ]] || { echo "invalid PUBLIC_PLAYER_LIMIT" >&2; exit 65; }
endpoint="${private_ip}:${game_port}"

jq -e --arg instance "$instance_id" \
       --arg system "$system_id" \
       --arg endpoint "$endpoint" \
       --arg status "$status_file" \
       --argjson players "$player_limit" \
  '(.InstanceId == $instance) and (.SystemId == $system) and
   (.InstanceEndpoint == $endpoint) and (.RuntimeStatusFile == $status) and
   (.MaxPlayers == $players)' "$llserver_config" >/dev/null || {
  echo "LLServer configuration does not match instance env" >&2
  exit 65
}

if [[ -n "$agent_env" ]]; then
  agent_instance=$(env_value "$agent_env" Agent__Instance__InstanceId)
  agent_system=$(env_value "$agent_env" Agent__Instance__SystemId)
  agent_endpoint=$(env_value "$agent_env" Agent__Instance__Endpoint)
  agent_players=$(env_value "$agent_env" Agent__Instance__MaxPlayers)
  agent_status=$(env_value "$agent_env" Agent__Instance__StatusFile)
  [[ "$agent_instance" == "$instance_id" && "$agent_system" == "$system_id" &&
     "$agent_endpoint" == "$endpoint" && "$agent_players" == "$player_limit" &&
     "$agent_status" == "$status_file" ]] || {
    echo "Agent configuration does not match instance env" >&2
    exit 65
  }
fi

echo "instance configuration valid: $instance_id"
