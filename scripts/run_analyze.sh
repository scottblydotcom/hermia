#!/bin/bash
set -e
source ~/ai-lab/ai-stack/.env
cd /home/scott/hermia
source .venv/bin/activate
hermia-analyze \
  --dsn "postgresql://scott:${POSTGRES_PASSWORD}@192.0.2.2:5432/litellm" \
  --last 10 \
  --export-jsonl analysis/findings.jsonl
