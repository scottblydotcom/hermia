#!/usr/bin/env bash
# overnight.sh — Hermia fleet overnight runner
# Phase 1: remediation (one-shot, parallel)
# Phase 2: N=5 full repeats per node (independent parallel loops)
#
# Usage: bash overnight.sh [N]
#   N = number of repeat runs per node (default 5)
#
# Tunnels required before running (example — substitute your node IPs):
#   ssh -fNL 11440:NODE_1_IP:11434 gateway   # openclaw
#   ssh -fNL 11450:NODE_2_IP:11434 gateway   # m3pro
#   ssh -fNL 11410:NODE_3_IP:11434 gateway   # m1pro
#   ssh -fNL 11430:NODE_4_IP:11434 gateway   # windows

set -uo pipefail

HERMIA_DIR="$(cd "$(dirname "$0")" && pwd)"
N="${1:-5}"
LOG_DIR="$HERMIA_DIR/logs/overnight_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_DIR/overnight.log"; }

# ── Preflight: check tunnels ──────────────────────────────────────────────────
log "=== PREFLIGHT: checking tunnels ==="
all_ok=true
declare -A TUNNEL_NAMES=(["11440"]="openclaw" ["11450"]="m3pro" ["11410"]="m1pro" ["11430"]="windows")
for port in 11440 11450 11410 11430; do
    if nc -z localhost "$port" 2>/dev/null; then
        log "  ✓ port $port (${TUNNEL_NAMES[$port]}) up"
    else
        log "  ✗ port $port (${TUNNEL_NAMES[$port]}) DOWN — tunnel missing"
        all_ok=false
    fi
done

if [ "$all_ok" = false ]; then
    log "ERROR: one or more tunnels are down. Run the ssh tunnel commands and retry."
    exit 1
fi

# ── Phase 1: Remediation ──────────────────────────────────────────────────────
log ""
log "=== PHASE 1: REMEDIATION (parallel, one-shot) ==="

run_remediation() {
    local yaml="$1" label="$2"
    log "  Starting remediation: $label"
    cd "$HERMIA_DIR" && uv run hermia --fleet "$yaml" \
        >> "$LOG_DIR/remediation-${label}.log" 2>&1 \
        && log "  ✓ Remediation complete: $label" \
        || log "  ✗ Remediation had errors: $label (check $LOG_DIR/remediation-${label}.log)"
}

run_remediation fleet-remediation-m3pro.yaml    m3pro    &
run_remediation fleet-remediation-windows.yaml  windows  &
wait
log "Phase 1 complete."

# ── Phase 2: Overnight repeats ────────────────────────────────────────────────
log ""
log "=== PHASE 2: OVERNIGHT REPEATS (N=$N per node, all nodes parallel) ==="

run_node() {
    local yaml="$1" label="$2"
    local node_log="$LOG_DIR/${label}.log"
    for i in $(seq 1 "$N"); do
        log "  $label: starting run $i/$N"
        cd "$HERMIA_DIR" && uv run hermia --fleet "$yaml" \
            >> "$node_log" 2>&1 \
            && log "  $label: run $i/$N complete" \
            || log "  $label: run $i/$N had errors (check $node_log)"
    done
    log "  $label: ALL $N RUNS DONE"
}

run_node fleet-erics-5090.yaml      erics-5090   &
run_node marcus-only.yaml           marcus-3090  &
run_node fleet-m1pro.yaml           m1pro        &
run_node fleet-m3pro.yaml           m3pro        &
run_node fleet-openclaw.yaml        openclaw     &
run_node fleet-windows-stable.yaml  windows      &

wait
log ""
log "=== ALL OVERNIGHT RUNS COMPLETE ==="
log "Results in: $HERMIA_DIR/results/"
log "Logs in:    $LOG_DIR/"
