# Phase 3 Ollama Port Conflict Fix Plan

Date: 2026-08-30

## Problem

`docker compose up` fails while starting the `ollama` container:

```text
failed to bind host port 0.0.0.0:11434/tcp: address already in use
```

After that, `curl http://localhost:8000/health` fails because the `gateway`
container was created but not started. The startup sequence is blocked before
FastAPI can listen on port `8000`.

## Investigation Findings

- Phase 2 installed Ollama as a host `systemd` service and configured it for the
  Vulkan backend by setting `CUDA_VISIBLE_DEVICES=`.
- The host Ollama service is currently active.
- `curl http://localhost:11434/api/tags` succeeds and returns the expected local
  Qwen models: `qwen3.5:0.8b`, `qwen3.5:2b`, `qwen3.5:4b`, and `qwen3.5:9b`.
- No Docker container is currently publishing host port `11434`.
- `gateway/docker-compose.yml` defines an `ollama` service with
  `ports: ["11434:11434"]`, so Compose tries to bind a port that the host
  Ollama service already owns.
- The `gateway` service currently depends on the Compose-managed `ollama`
  service and sets `OLLAMA_BASE_URL=http://ollama:11434`, so it never starts
  when the `ollama` container cannot bind its host port.

## Root Cause

Phase 3 currently has two competing Ollama ownership models:

1. Phase 2 made host `ollama.service` the real local inference runtime,
   including the machine-specific Vulkan configuration.
2. Phase 3 Compose tries to start a second Ollama runtime in a container and
   publish it on the same host port, `11434`.

The bind error is the visible failure. The deeper design issue is that the
Phase 3 Compose file accidentally diverges from the Phase 2 decision to use the
host Ollama installation as the tuned, known-good inference service.

## Recommended Phase 3 Decision

Use host `ollama.service` as the single Ollama runtime for Phase 3.

Run only the Gateway in Docker for now, and have it call the host Ollama service
at `http://127.0.0.1:11434`.

The cleanest Linux-host option is to run the Gateway container with
`network_mode: host`. That lets the container reach the host loopback Ollama
service without changing Ollama to bind on a LAN-visible interface.

Do not make containerized Ollama the default in Phase 3 unless there is a
separate follow-up to reproduce the Phase 2 Vulkan behavior inside Docker,
including model storage, device access, and backend verification.

## Implementation Plan

### 1. Update Docker Compose

Edit `gateway/docker-compose.yml`:

- Remove the default `ollama` service.
- Remove the `ollama-data` volume if nothing else uses it.
- Remove `depends_on: ollama`.
- Remove the custom Compose network if the Gateway is the only remaining
  service.
- Set the Gateway environment variable:

```yaml
OLLAMA_BASE_URL: http://127.0.0.1:11434
```

- Add host networking to the Gateway service:

```yaml
network_mode: host
```

- Remove `ports: ["8000:8000"]`, because port publishing is ignored or invalid
  with host networking. Uvicorn binding to `0.0.0.0:8000` will expose the
  Gateway directly on the host port.
- Remove the obsolete top-level `version` key to eliminate the Compose warning.

Expected shape:

```yaml
services:
  gateway:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: gateway
    network_mode: host
    environment:
      GATEWAY_ENV: production
      GATEWAY_HOST: 0.0.0.0
      GATEWAY_PORT: 8000
      GATEWAY_LOG_LEVEL: INFO
      GATEWAY_DB_PATH: /data/ai-platform/gateway.db
      GATEWAY_JWT_SECRET: ${GATEWAY_JWT_SECRET:?GATEWAY_JWT_SECRET is required}
      OLLAMA_BASE_URL: http://127.0.0.1:11434
    volumes:
      - /mnt/data/ai-platform:/data/ai-platform
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
```

### 2. Update Gateway Defaults and Docs

Align Phase 3 docs and examples with host Ollama:

- `gateway/.env.example`: change `OLLAMA_BASE_URL` to
  `http://127.0.0.1:11434`.
- `gateway/config.yaml`: change `ollama.base_url` to
  `http://127.0.0.1:11434`, unless this file is intentionally meant to describe
  a multi-container deployment.
- `gateway/README.md`: document that Phase 3 expects host `ollama.service` to
  be active before starting the Gateway container.
- `gateway/DEVELOPMENT.md`: update Docker startup/troubleshooting commands.
- `gateway/IMPLEMENTATION_SUMMARY.md`: replace "Docker Compose starts Ollama +
  Gateway" with "Docker Compose starts Gateway and depends on host Ollama".
- `Plan/PHASE-3-SPECIFICATION.md`: add an implementation note or erratum that
  the current Acer Aspire Phase 3 deployment uses host Ollama because Phase 2
  established a host-specific Vulkan setup.

### 3. Add a Preflight Check

Add a small script, for example `gateway/scripts/check-phase3-runtime.sh`, that
fails fast when host Ollama is unavailable:

```bash
#!/usr/bin/env bash
set -euo pipefail

curl -fsS http://127.0.0.1:11434/api/tags >/dev/null
docker compose config >/dev/null
```

Optional checks:

- Confirm `systemctl is-active ollama` returns `active` on Linux hosts that use
  systemd.
- Confirm port `8000` is free before starting the Gateway.
- Confirm `GATEWAY_JWT_SECRET` is set and at least 32 characters.

### 4. Verification Commands

From `gateway/`:

```bash
./scripts/check-phase3-runtime.sh
docker compose up --build -d gateway
docker compose ps
curl -fsS http://localhost:8000/health
```

Expected health response:

```json
{
  "status": "healthy",
  "database": "connected",
  "ollama": "connected",
  "queue_depth": 0
}
```

Then verify the Phase 3 success path:

```bash
curl -fsS http://localhost:8000/docs >/dev/null
curl -X POST http://localhost:8000/admin/setup/user \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "SecurePass1!"}'
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "SecurePass1!"}'
```

After login, use the returned access token for a real `/chat` request and
confirm Ollama generates a response.

### 5. Regression Coverage

Keep the existing automated tests for:

- `/health` returns `ollama: connected` when `ollama_provider.health_check()`
  succeeds.
- `/health` returns degraded status when Ollama is unavailable.
- `/chat` maps Ollama connection failure to the Phase 3 `503` error contract.

Add a lightweight Compose/static test if useful:

- Parse `gateway/docker-compose.yml`.
- Assert no default service publishes host port `11434`.
- Assert the Gateway default Docker runtime points to host Ollama.

This catches the specific regression that caused the current failure.

### 6. Rollback and Alternate Path

If Phase 3 must return to a fully containerized Ollama deployment:

- Stop or disable host `ollama.service` before Compose starts, or use a
  different host port for the container.
- Mount the actual model store at the path Ollama expects inside the container.
- Recreate the Vulkan backend setup inside the container.
- Prove GPU/Vulkan is active from container logs before accepting performance
  results.
- Keep `OLLAMA_MAX_LOADED_MODELS=1` and the Gateway single-inference queue.

This path is higher risk for the Acer Aspire because the Phase 2 Vulkan setup is
already known to work on the host.

## Acceptance Criteria

- `docker compose up --build -d gateway` starts without attempting to bind
  `11434`.
- `curl http://localhost:8000/health` succeeds.
- Health reports `database: connected` and `ollama: connected`.
- Auth setup, login, and authenticated `/chat` work against local Qwen.
- Existing Phase 3 automated tests still pass.
- Documentation no longer tells operators to start a second default Ollama
  container on a host that already runs `ollama.service`.
