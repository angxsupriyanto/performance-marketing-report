#!/bin/sh
# Read-only checks for the report service. Prints PASS/FAIL lines and exits 1 if anything failed.
# The token is never printed and never put on a command line.
#
#   Inside Docker (preferred):  verify-report-service.sh --container report-service --n8n-container <n8n container>
#   Plain HTTP (for a local run): verify-report-service.sh --url http://127.0.0.1:8080 --token-file token.txt
set -u

container=""; n8n=""; url=""; token_file=""
while [ $# -gt 0 ]; do
  case "$1" in
    --container) container="$2"; shift 2 ;;
    --n8n-container) n8n="$2"; shift 2 ;;
    --url) url="$2"; shift 2 ;;
    --token-file) token_file="$2"; shift 2 ;;
    *) echo "unknown option: $1" >&2; exit 64 ;;
  esac
done

failures=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; failures=$((failures + 1)); }
check() { if [ "$1" = "ok" ]; then pass "$2"; else fail "$2"; fi; }

# Python probe used both inside the container and (via curl-free fallback) on the host.
probe='
import json, os, sys, urllib.request, urllib.error
base, token_path = sys.argv[1], sys.argv[2]
token = open(token_path).read().strip() if token_path else ""
def call(path, body=None, bearer=None):
    req = urllib.request.Request(base + path, data=body, method="POST" if body is not None else "GET")
    if bearer is not None:
        req.add_header("Authorization", "Bearer " + bearer)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
status, body = call("/healthz")
print("health", status, "bu1" in body and "bu2" in body)
print("no_token", call("/v1/analysis/apply", b"{}")[0])
print("wrong_token", call("/v1/analysis/apply", b"{}", "x" * 40)[0])
print("good_token", call("/v1/analysis/apply", b"{}", token)[0])
'

report_probe() {
  # $1 = interpreter command prefix, $2 = base URL, $3 = token path
  out=$($1 python3 -c "$probe" "$2" "$3" 2>/dev/null) || { fail "probe could not run"; return; }
  echo "$out" | grep -q '^health 200 True$' && pass "health endpoint answers and lists bu1 and bu2" || fail "health endpoint did not answer 200 with bu1 and bu2"
  echo "$out" | grep -q '^no_token 401$' && pass "request without token is refused (401)" || fail "request without token was not refused"
  echo "$out" | grep -q '^wrong_token 401$' && pass "request with wrong token is refused (401)" || fail "request with wrong token was not refused"
  case "$(echo "$out" | sed -n 's/^good_token //p')" in 400|422) pass "request with the real token is accepted (rejected only for its empty body)" ;; *) fail "the real token was not accepted" ;; esac
}

if [ -n "$container" ]; then
  command -v docker >/dev/null 2>&1 || { echo "FAIL: docker not found"; exit 1; }
  state=$(docker inspect -f '{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{else}}nohealthcheck{{end}}' "$container" 2>/dev/null)
  [ "$state" = "true healthy" ] && check ok "container is running and healthy" || check no "container is running and healthy (got: ${state:-not found})"
  ports=$(docker port "$container" 2>/dev/null)
  [ -z "$ports" ] && check ok "no port is published on the host" || check no "no port is published on the host (found: $ports)"
  uid=$(docker exec "$container" id -u 2>/dev/null)
  [ -n "$uid" ] && [ "$uid" != "0" ] && check ok "process does not run as root (uid $uid)" || check no "process does not run as root (uid ${uid:-unknown})"
  ro=$(docker inspect -f '{{.HostConfig.ReadonlyRootfs}}' "$container" 2>/dev/null)
  [ "$ro" = "true" ] && check ok "root filesystem is read-only" || check no "root filesystem is read-only (got: ${ro:-unknown})"
  report_probe "docker exec $container" "http://127.0.0.1:8080" "/run/secrets/report_service_token"
  if [ -n "$n8n" ]; then
    reach=$(docker exec "$n8n" wget -qO- -T 5 http://report-service:8080/healthz 2>/dev/null)
    case "$reach" in *'"status": "ok"'*) pass "n8n container reaches http://report-service:8080 over the Docker network" ;; *) fail "n8n container cannot reach http://report-service:8080 (is it on the same network, and is the service named report-service?)" ;; esac
  else
    echo "SKIP: pass --n8n-container to test the path from n8n"
  fi
elif [ -n "$url" ] && [ -n "$token_file" ]; then
  report_probe "env" "$url" "$token_file"
else
  echo "usage: --container NAME [--n8n-container NAME] | --url URL --token-file FILE" >&2; exit 64
fi

[ "$failures" -eq 0 ] && { echo "ALL CHECKS PASSED"; exit 0; }
echo "$failures CHECK(S) FAILED"; exit 1
