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

# The functional checks live in service/selftest.py so no shell quoting is involved.
selftest_output() {
  # $@ = command that runs the self-test; prints its PASS/FAIL lines and counts failures.
  out=$("$@" 2>&1) || true
  echo "$out" | grep -E '^(PASS|FAIL):' || fail "self-test could not run: $(echo "$out" | tail -1)"
  n=$(echo "$out" | grep -c '^FAIL:') ; failures=$((failures + n))
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
  selftest_output docker exec "$container" python -m service.selftest
  if [ -n "$n8n" ]; then
    reach=$(docker exec "$n8n" wget -qO- -T 5 http://report-service:8080/healthz 2>/dev/null)
    case "$reach" in *'"status": "ok"'*) pass "n8n container reaches http://report-service:8080 over the Docker network" ;; *) fail "n8n container cannot reach http://report-service:8080 (is it on the same network, and is the service named report-service?)" ;; esac
  else
    echo "SKIP: pass --n8n-container to test the path from n8n"
  fi
elif [ -n "$url" ] && [ -n "$token_file" ]; then
  here=$(cd "$(dirname "$0")/.." && pwd)
  run_local() { (cd "$here" && python3 -m service.selftest --url "$url" --token-file "$token_file"); }
  selftest_output run_local
else
  echo "usage: --container NAME [--n8n-container NAME] | --url URL --token-file FILE" >&2; exit 64
fi

[ "$failures" -eq 0 ] && { echo "ALL CHECKS PASSED"; exit 0; }
echo "$failures CHECK(S) FAILED"; exit 1
