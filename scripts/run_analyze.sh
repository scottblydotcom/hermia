#!/bin/bash
set -e
source /home/scott/ai-lab/ai-stack/.env
cd /home/scott/hermia
source .venv/bin/activate
hermia-analyze \
  --dsn "postgresql://scott:${POSTGRES_PASSWORD}@172.18.0.8:5432/litellm" \
  --last 10 \
  --export-jsonl analysis/findings.jsonl
