#!/usr/bin/env bash
# Validate host services required by the Phase 3 Gateway container.

set -euo pipefail

OLLAMA_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
GATEWAY_PORT="${GATEWAY_PORT:-8000}"
COMPOSE_CONFIG="$(docker compose config)"
JWT_SECRET="${GATEWAY_JWT_SECRET:-}"

if [[ -z "${JWT_SECRET}" ]]; then
    JWT_SECRET="$(
        printf '%s\n' "${COMPOSE_CONFIG}" \
            | sed -n 's/^[[:space:]]*GATEWAY_JWT_SECRET:[[:space:]]*//p' \
            | head -n 1
    )"
fi

if [[ -z "${JWT_SECRET}" || "${#JWT_SECRET}" -lt 32 ]]; then
    echo "GATEWAY_JWT_SECRET must be set to at least 32 characters." >&2
    exit 1
fi

if command -v systemctl >/dev/null 2>&1; then
    OLLAMA_LOAD_STATE="$(systemctl show -p LoadState --value ollama.service 2>/dev/null || true)"
    if [[ -n "${OLLAMA_LOAD_STATE}" && "${OLLAMA_LOAD_STATE}" != "not-found" ]] \
        && ! systemctl is-active --quiet ollama; then
        echo "ollama.service is not active." >&2
        exit 1
    fi
fi

curl -fsS "${OLLAMA_URL}/api/tags" >/dev/null

if command -v ss >/dev/null 2>&1; then
    if ss -H -ltn "sport = :${GATEWAY_PORT}" | grep -q .; then
        echo "Port ${GATEWAY_PORT} is already in use." >&2
        exit 1
    fi
fi
