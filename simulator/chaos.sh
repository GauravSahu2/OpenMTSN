#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════
# OpenMTSN — Chaos Engineering Script
# ══════════════════════════════════════════════════════════
#
# Injects network degradation into node-alpha to validate
# the control plane's failover routing logic.
#
# Usage:
#   ./simulator/chaos.sh inject   # Apply chaos conditions
#   ./simulator/chaos.sh verify   # Check API for failover
#   ./simulator/chaos.sh reset    # Remove all chaos rules
#   ./simulator/chaos.sh full     # inject → wait → verify → reset
#
# Prerequisites:
#   - Docker Compose stack running (docker compose up -d)
#   - node-alpha container must have NET_ADMIN capability
# ══════════════════════════════════════════════════════════

set -euo pipefail

CONTAINER="mtsn-node-alpha"
API_URL="http://localhost:8000"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()   { echo -e "${CYAN}[CHAOS]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; }

# ── Inject chaos into node-alpha ──────────────────────────
inject_chaos() {
    log "Injecting chaos into ${CONTAINER}..."
    log "  → 80% packet loss"
    log "  → 500ms latency ± 200ms jitter"
    log "  → 25% packet corruption"

    # Install iproute2 if missing
    docker exec "${CONTAINER}" sh -c "which tc > /dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq iproute2 > /dev/null 2>&1)" || true

    # Clear any existing rules
    docker exec "${CONTAINER}" tc qdisc del dev eth0 root 2>/dev/null || true

    # Apply netem rules: 80% loss, 500ms delay ± 200ms, 25% corrupt
    docker exec "${CONTAINER}" tc qdisc add dev eth0 root netem \
        loss 80% \
        delay 500ms 200ms distribution normal \
        corrupt 25%

    ok "Chaos injected successfully"
    log "node-alpha is now experiencing severe network degradation"
}

# ── Verify failover via API ───────────────────────────────
verify_failover() {
    log "Waiting 10 seconds for telemetry to propagate..."
    sleep 10

    log "Querying API for node-alpha routing decision..."

    RESPONSE=$(curl -s "${API_URL}/route/node-alpha" 2>/dev/null || echo "UNREACHABLE")

    if [ "${RESPONSE}" = "UNREACHABLE" ]; then
        warn "API unreachable — is the stack running?"
        return 1
    fi

    echo ""
    log "API Response:"
    echo "${RESPONSE}" | python3 -m json.tool 2>/dev/null || echo "${RESPONSE}"
    echo ""

    # Check for failover
    SHOULD_FAILOVER=$(echo "${RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('should_failover', False))" 2>/dev/null || echo "unknown")
    RECOMMENDED=$(echo "${RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('recommended_uplink', 'unknown'))" 2>/dev/null || echo "unknown")

    if [ "${SHOULD_FAILOVER}" = "True" ]; then
        ok "FAILOVER TRIGGERED — node-alpha routed to: ${RECOMMENDED}"
        ok "Chaos test PASSED ✓"
        return 0
    else
        warn "No failover detected (should_failover=${SHOULD_FAILOVER})"
        warn "The agent may not have published degraded telemetry yet"
        return 1
    fi
}

# ── Reset chaos rules ────────────────────────────────────
reset_chaos() {
    log "Resetting network conditions on ${CONTAINER}..."
    docker exec "${CONTAINER}" tc qdisc del dev eth0 root 2>/dev/null || true
    ok "Network restored to normal"
}

# ── Full chaos test cycle ─────────────────────────────────
full_cycle() {
    echo ""
    echo "═══════════════════════════════════════════════════"
    echo "  OpenMTSN Chaos Engineering — Full Test Cycle"
    echo "═══════════════════════════════════════════════════"
    echo ""

    inject_chaos
    echo ""
    verify_failover
    RESULT=$?
    echo ""
    reset_chaos

    echo ""
    if [ ${RESULT} -eq 0 ]; then
        ok "═══ CHAOS TEST COMPLETE — ALL CHECKS PASSED ═══"
    else
        fail "═══ CHAOS TEST COMPLETE — SOME CHECKS FAILED ═══"
    fi
    return ${RESULT}
}

# ── CLI dispatcher ────────────────────────────────────────
case "${1:-full}" in
    inject)  inject_chaos ;;
    verify)  verify_failover ;;
    reset)   reset_chaos ;;
    full)    full_cycle ;;
    *)
        echo "Usage: $0 {inject|verify|reset|full}"
        exit 1
        ;;
esac
