#!/bin/bash
# Health check script for Agent Gateway
# Waits for Ollama to be healthy before returning success

set -e

OLLAMA_URL="${OLLAMA_BASE_URL:-http://ollama:11434}"
MAX_RETRIES=30
RETRY_INTERVAL=1

echo "Waiting for Ollama at $OLLAMA_URL..."

for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf "$OLLAMA_URL/api/tags" > /dev/null 2>&1; then
        echo "Ollama is healthy!"
        exit 0
    fi
    
    echo "Attempt $i/$MAX_RETRIES: Ollama not ready, retrying in ${RETRY_INTERVAL}s..."
    sleep $RETRY_INTERVAL
done

echo "Ollama did not become healthy after $MAX_RETRIES attempts"
exit 1
