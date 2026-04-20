#!/bin/bash
# ══════════════════════════════════════════════════════════════════
# OpenMTSN Tactical Jamming Simulator
# ══════════════════════════════════════════════════════════════════
# Usage: ./jam_swarm.sh <container_name> [loss_percentage]
# Example: ./jam_swarm.sh mtsn-node-alpha 40
# To Clear: ./jam_swarm.sh mtsn-node-alpha clear
# ══════════════════════════════════════════════════════════════════

CONTAINER=$1
LOSS=${2:-30}

if [ -z "$CONTAINER" ]; then
    echo "Usage: $0 <container_name> [loss_percentage|clear]"
    exit 1
fi

if [ "$LOSS" == "clear" ]; then
    echo "--- Restoring clearing electronic interference on $CONTAINER ---"
    docker exec -it --privileged "$CONTAINER" tc qdisc del dev eth0 root 2>/dev/null
    exit 0
fi

echo "--- Injecting $LOSS% Electronic Jamming into $CONTAINER ---"
docker exec -it --privileged "$CONTAINER" tc qdisc add dev eth0 root netem loss $LOSS% delay 500ms 100ms
echo "EW ATTACK ACTIVE: Node $CONTAINER is now experiencing denied communications."
