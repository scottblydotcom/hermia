#!/bin/bash
# Collect results from fleet machines and push to gateway Postgres.
# Postgres is Docker-internal on the gateway (172.18.0.8:5432) — push must run
# from the gateway host, not from this Mac.
set -e

HERMIA_DIR=~/Git/hermia
RESULTS_DIR=$HERMIA_DIR/results

echo "=== Collecting results from fleet ==="
echo "M3 Pro..."  && rsync -a m3pro:/Users/user/hermia/results/   "$RESULTS_DIR"/
echo "OpenClaw..." && rsync -a openclaw:/home/scott/hermia/results/ "$RESULTS_DIR"/
# Windows: manual scp to $RESULTS_DIR before running this script
# Marcus 3090: add rsync line here when results dir confirmed

echo "=== Syncing aggregated results to gateway ==="
rsync -a "$RESULTS_DIR"/ gateway:/home/scott/hermia/results/

echo "=== Pushing to Postgres from gateway ==="
ssh gateway '
  set -e
  source /home/scott/ai-lab/ai-stack/.env
  cd /home/scott/hermia
  source .venv/bin/activate
  hermia-push --dsn "postgresql://scott:${POSTGRES_PASSWORD}@172.18.0.8:5432/litellm" --results-dir results
'

echo "=== Done. Check Grafana: https://scottai.tailc7d860.ts.net:3000/d/955440f9-0e8c-4553-b18e-c120768abbc3 ==="
