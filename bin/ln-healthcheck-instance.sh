#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 --status-file FILE [--endpoint HOST:PORT] [--max-age SECONDS]" >&2
}

status_file=''
expected_endpoint=''
max_age=10
while (($# > 0)); do
  case "$1" in
    --status-file)
      (($# >= 2)) || { usage; exit 64; }
      status_file=$2; shift 2 ;;
    --endpoint)
      (($# >= 2)) || { usage; exit 64; }
      expected_endpoint=$2; shift 2 ;;
    --max-age)
      (($# >= 2)) || { usage; exit 64; }
      max_age=$2; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      usage; exit 64 ;;
  esac
done

[[ -n "$status_file" ]] || { usage; exit 64; }
[[ -r "$status_file" ]] || { echo "status file is not readable" >&2; exit 1; }
[[ "$max_age" =~ ^[0-9]+$ && "$max_age" -gt 0 ]] || { echo "invalid max age" >&2; exit 64; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 69; }
command -v date >/dev/null || { echo "date is required" >&2; exit 69; }

written_at=$(jq -er '.WrittenAtUtc // empty' "$status_file") || { echo "invalid status JSON" >&2; exit 1; }
written_epoch=$(date -u -d "$written_at" +%s 2>/dev/null) || { echo "invalid status timestamp" >&2; exit 1; }
now_epoch=$(date -u +%s)
age=$((now_epoch - written_epoch))
(( age >= 0 && age <= max_age )) || { echo "status is stale or from the future" >&2; exit 1; }

jq -e '
  (.IsReady == true) and
  (.CurrentPlayers >= 0) and
  (.MaxPlayers > 0) and
  (.CurrentPlayers <= .MaxPlayers) and
  (.InstanceId | type == "string" and length > 0) and
  (.SystemId | type == "string" and length > 0) and
  (.Endpoint | type == "string" and length > 0)
' "$status_file" >/dev/null || { echo "instance is not ready or status is invalid" >&2; exit 1; }

if [[ -n "$expected_endpoint" ]]; then
  actual_endpoint=$(jq -er '.Endpoint' "$status_file")
  [[ "$actual_endpoint" == "$expected_endpoint" ]] || { echo "instance endpoint mismatch" >&2; exit 1; }
fi

echo "instance ready: $(jq -r '.InstanceId' "$status_file")"
