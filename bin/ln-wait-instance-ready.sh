#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 --llserver-config FILE [--timeout SECONDS]" >&2
}

config_file=''
timeout=90
while (($# > 0)); do
  case "$1" in
    --llserver-config)
      (($# >= 2)) || { usage; exit 64; }
      config_file=$2; shift 2 ;;
    --timeout)
      (($# >= 2)) || { usage; exit 64; }
      timeout=$2; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      usage; exit 64 ;;
  esac
done

[[ -r "$config_file" ]] || { echo "LLServer config is not readable" >&2; exit 66; }
[[ "$timeout" =~ ^[0-9]+$ && "$timeout" -gt 0 ]] || { echo "invalid timeout" >&2; exit 64; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 69; }

status_file=$(jq -er '.RuntimeStatusFile' "$config_file") || { echo "RuntimeStatusFile is missing" >&2; exit 65; }
endpoint=$(jq -er '.InstanceEndpoint' "$config_file") || { echo "InstanceEndpoint is missing" >&2; exit 65; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
healthcheck="$script_dir/ln-healthcheck-instance.sh"
[[ -x "$healthcheck" ]] || { echo "healthcheck is not executable" >&2; exit 69; }

started=$(date +%s)
while :; do
  if "$healthcheck" --status-file "$status_file" --endpoint "$endpoint" >/dev/null 2>&1; then
    echo "instance became ready: $endpoint"
    exit 0
  fi
  now=$(date +%s)
  if (( now - started >= timeout )); then
    echo "instance did not become ready within ${timeout}s" >&2
    exit 1
  fi
  sleep 1
done
