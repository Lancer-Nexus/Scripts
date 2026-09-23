#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 <agent|coordinator|instance:INSTANCE_ID> {start|stop|restart|status|enable|disable|restart-failed|logs}" >&2
}

service_ref=${1:-}
action=${2:-}
if [[ "$service_ref" == "-h" || "$service_ref" == "--help" ]]; then
  usage
  exit 0
fi
[[ -n "$service_ref" && -n "$action" ]] || { usage; exit 64; }

case "$service_ref" in
  agent)
    unit='lancer-nexus-agent.service' ;;
  coordinator)
    unit='lancer-nexus-coordinator.service' ;;
  instance:*)
    instance_id=${service_ref#instance:}
    [[ "$instance_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ && "$instance_id" != *..* ]] || {
      echo "invalid instance ID" >&2
      exit 64
    }
    unit="lancer-nexus-instance@${instance_id}.service" ;;
  *)
    echo "unsupported service: $service_ref" >&2
    exit 64 ;;
esac

case "$action" in
  start|stop|restart|status|enable|disable|restart-failed)
    exec systemctl "$action" "$unit" ;;
  logs)
    exec journalctl -u "$unit" -n 200 -f ;;
  *)
    echo "unsupported action: $action" >&2
    usage
    exit 64 ;;
esac
