#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 --url HTTPS_URL [--ca FILE]" >&2
}

url=''
ca_file=''
while (($# > 0)); do
  case "$1" in
    --url)
      (($# >= 2)) || { usage; exit 64; }
      url=$2; shift 2 ;;
    --ca)
      (($# >= 2)) || { usage; exit 64; }
      ca_file=$2; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      usage; exit 64 ;;
  esac
done

[[ "$url" == https://* && "$url" != *$'\n'* && "$url" != *$'\r'* ]] || {
  echo "HTTPS URL is required" >&2
  exit 64
}
if [[ -n "$ca_file" && ! -r "$ca_file" ]]; then
  echo "CA file is not readable" >&2
  exit 66
fi
command -v curl >/dev/null || { echo "curl is required" >&2; exit 69; }

curl_args=(--fail --silent --show-error --connect-timeout 3 --max-time 10 --output /dev/null)
if [[ -n "$ca_file" ]]; then
  curl_args+=(--cacert "$ca_file")
fi
curl "${curl_args[@]}" "$url" || {
  echo "readiness check failed: $url" >&2
  exit 1
}

echo "service ready: $url"
