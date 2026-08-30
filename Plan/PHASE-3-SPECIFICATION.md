# Phase 3 Specification: Agent Gateway + Authentication

**Version**: 1.0  
**Date**: 2026-08-29  
**Phase**: 3 (Agent Gateway + Authentication)  
**Status**: Ready for Implementation

---

## 1. Overview

The Agent Gateway is a FastAPI service running in Docker that:

- **Authenticates** requests via username/password → JWT token flow.
- **Routes** model calls to local Qwen (via Ollama) or cloud providers (Claude Code).
- **Enforces** single-inference-at-a-time via in-memory request queue.
- **Classifies** data and enforces RED-data local-only rules.
- **Exposes** MCP tools as REST endpoints.
- **Logs** all actions for audit trails.
- **Manages** sessions and user permissions.

The Gateway is stateless (JWTs are self-contained), runs in Docker, and is orchestrated via Docker Compose.

**2026-08-30 implementation note:** On the Acer Aspire deployment, Phase 3 uses
the Phase 2 host `ollama.service` as the single local inference runtime because
that service already carries the host-specific Vulkan setup. Docker Compose
starts the Gateway container only, with host networking, and the Gateway calls
Ollama at `http://127.0.0.1:11434`. See
[ADR-0004](../docs/adr/0004-host-ollama-runtime-for-phase-3.md).

---

## 2. Architecture Overview

```
┌──────────────────────────────────────────────┐
│         Web UI (Phase 4)                     │
│    (login form, chat interface, etc.)        │
└─────────────────────────────────────────────┘
                      │
                      │ HTTP + Bearer JWT
                      ▼
┌──────────────────────────────────────────────┐
│      AGENT GATEWAY (FastAPI, Docker)         │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ Auth Layer (JWT verification)        │   │
│  └──────────────────────────────────────┘   │
│                      │                       │
│  ┌──────────────────────────────────────┐   │
│  │ Data Classifier (RED/YELLOW/GREEN)   │   │
│  └──────────────────────────────────────┘   │
│                      │                       │
│  ┌──────────────────────────────────────┐   │
│  │ Request Queue (async.Semaphore(1))   │   │
│  └──────────────────────────────────────┘   │
│                      │                       │
│       ┌──────────────┴──────────────┐        │
│       │                             │        │
│  ┌─────────────────┐        ┌─────────────┐ │
│  │ Ollama Provider │        │Claude Code  │ │
│  │ (local Qwen)    │        │ (cloud)     │ │
│  └─────────────────┘        └─────────────┘ │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │ Audit Logger (SQLite)                │   │
│  └──────────────────────────────────────┘   │
└──────────────────────────────────────────────┘
       │                    │
       │ Ollama API         │
       │ (127.0.0.1:11434)  │
       ▼                    │
   ┌────────┐               │ Claude Code
   │ Ollama │               │ API (Cloud)
   └────────┘               │
                            ▼
                       (External)
```

---

## 3. Database Schema

### SQLite Tables

All tables are created at startup via SQLAlchemy ORM. Below is the ERD.

#### `users` Table

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,  -- Argon2 hash
  created_at TEXT NOT NULL,      -- ISO 8601 timestamp
  last_login_at TEXT,            -- ISO 8601 timestamp, nullable
  is_active BOOLEAN DEFAULT TRUE
);
```

**Constraints:**
- `username` must be 3–32 alphanumeric characters (enforced in validator).
- `password_hash` is Argon2 output (96 bytes, base64-encoded when stored).

#### `refresh_tokens` Table

```sql
CREATE TABLE refresh_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  token TEXT UNIQUE NOT NULL,  -- cryptographically random string
  issued_at TEXT NOT NULL,     -- ISO 8601 timestamp
  expires_at TEXT NOT NULL,    -- ISO 8601 timestamp (7 days from issued_at)
  revoked_at TEXT,             -- ISO 8601 timestamp, nullable (NULL = not revoked)
  FOREIGN KEY(user_id) REFERENCES users(id)
);
```

**Constraints:**
- Token is 32 random bytes (hex-encoded, 64 characters).
- `revoked_at` is used to manually invalidate a token before expiry (future use).

#### `audit_logs` Table

```sql
CREATE TABLE audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,      -- ISO 8601 UTC
  user_id INTEGER,              -- nullable if unauthenticated request
  request_id TEXT NOT NULL UNIQUE,  -- UUID for tracing
  agent TEXT,                   -- agent name (e.g., 'news', 'calendar')
  action TEXT NOT NULL,         -- 'request_inference', 'request_tool', 'login', etc.
  model TEXT,                   -- which model was used (e.g., 'qwen3.5:2b', 'claude-code')
  data_class TEXT,              -- 'GREEN', 'YELLOW', 'RED'
  data_class_patterns TEXT,     -- JSON array of matched patterns
  approval_required BOOLEAN,    -- whether approval was needed
  approval_status TEXT,         -- 'auto_approved', 'user_approved', 'user_rejected', 'blocked'
  tokens_used TEXT,             -- JSON: {"input": N, "output": M}
  result TEXT NOT NULL,         -- 'success', 'error', 'timeout', 'blocked_red_data', etc.
  error_message TEXT,           -- nullable, error details (with RED patterns redacted)
  queue_wait_ms INTEGER,        -- milliseconds spent in request queue
  duration_ms INTEGER,          -- total request duration
  FOREIGN KEY(user_id) REFERENCES users(id)
);
```

**Constraints:**
- `timestamp` is indexed for fast time-range queries.
- `error_message` has RED patterns redacted before storage (see ADR-0003).
- `data_class_patterns` is a JSON array string.

#### `model_config` Table

```sql
CREATE TABLE model_config (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model_name TEXT UNIQUE NOT NULL,  -- 'qwen3.5:2b', 'qwen3.5:4b', 'claude-code'
  provider TEXT NOT NULL,            -- 'ollama' or 'claude'
  tier TEXT,                         -- 'default', 'heavier', 'batch', 'cloud'
  timeout_seconds INTEGER NOT NULL,  -- default 120
  enabled BOOLEAN DEFAULT TRUE,
  metadata TEXT                      -- JSON blob for provider-specific config
);
```

**Initial data (seeded at startup):**

```json
[
  {
    "model_name": "qwen3.5:2b",
    "provider": "ollama",
    "tier": "default",
    "timeout_seconds": 120,
    "enabled": true,
    "metadata": {}
  },
  {
    "model_name": "qwen3.5:4b",
    "provider": "ollama",
    "tier": "heavier",
    "timeout_seconds": 180,
    "enabled": true,
    "metadata": {}
  },
  {
    "model_name": "qwen3.5:9b",
    "provider": "ollama",
    "tier": "batch",
    "timeout_seconds": 600,
    "enabled": true,
    "metadata": {}
  },
  {
    "model_name": "claude-code",
    "provider": "claude",
    "tier": "cloud",
    "timeout_seconds": 120,
    "enabled": true,
    "metadata": { "api_endpoint": "https://api.anthropic.com/v1/messages" }
  }
]
```

---

## 4. API Endpoints

All endpoints (except auth endpoints) require `Authorization: Bearer <jwt>` header.

### Authentication Endpoints (Public)

#### `POST /auth/login`

**Request:**
```json
{
  "username": "user",
  "password": "password123"
}
```

**Success Response (200):**
```json
{
  "access_token": "<jwt_token>",
  "refresh_token": "<refresh_token_string>",
  "token_type": "bearer",
  "expires_in": 900
}
```

**Error Response (401):**
```json
{
  "detail": "Invalid username or password"
}
```

**Error Response (403):** (user account disabled)
```json
{
  "detail": "User account is inactive"
}
```

**Behavior:**
- Verify username exists + password matches (Argon2 comparison).
- Generate JWT (exp = now + 15 min).
- Generate refresh token (exp = now + 7 days, store in DB).
- Log login action to audit_logs with user_id.
- Update user.last_login_at.

---

#### `POST /auth/refresh`

**Request:**
```json
{
  "refresh_token": "<refresh_token_string>"
}
```

**Success Response (200):**
```json
{
  "access_token": "<new_jwt_token>",
  "token_type": "bearer",
  "expires_in": 900
}
```

**Error Response (401):**
```json
{
  "detail": "Refresh token expired or invalid"
}
```

**Behavior:**
- Look up refresh token in DB.
- Verify it exists, hasn't expired, and hasn't been revoked.
- If valid, issue new JWT.
- Log refresh action to audit_logs.

---

#### `POST /auth/logout`

**Request:** (no body)

**Success Response (200):**
```json
{
  "message": "Logged out successfully"
}
```

**Behavior:**
- Revoke the refresh token associated with this JWT (set revoked_at = now).
- Clear any server-side session (none, since stateless; this is for consistency).
- Log logout action to audit_logs.

---

#### `POST /admin/setup/user` (One-time, setup-mode only)

**Request:**
```json
{
  "username": "user",
  "password": "password123"
}
```

**Success Response (200):**
```json
{
  "user_id": 1,
  "username": "user",
  "message": "First user created. Setup endpoint is now disabled."
}
```

**Error Response (403):** (if users table is not empty)
```json
{
  "detail": "Setup endpoint is disabled (users already exist)"
}
```

**Behavior:**
- Check if users table is empty.
- If empty, create first user with provided username + Argon2-hashed password.
- Log setup action.
- Subsequent calls to this endpoint return 403 (setup mode disabled).

---

### Chat / Inference Endpoints (Authenticated)

#### `POST /chat`

**Request:**
```json
{
  "prompt": "Summarize the latest news on AI",
  "model_preference": "qwen3.5:2b",    // optional, null = auto-select
  "agent": "news",                      // optional, agent name
  "streaming": false                    // optional, default false
}
```

**Success Response (200):**
```json
{
  "id": "req-uuid-12345",
  "model_used": "qwen3.5:2b",
  "data_class": "GREEN",
  "data_class_patterns": [],
  "approval_required": false,
  "approval_status": "auto_approved",
  "response": "Here are the top AI news items...",
  "tokens_used": {
    "input": 12,
    "output": 45
  },
  "duration_ms": 8500
}
```

**Approval-Required Response (202):**
```json
{
  "id": "req-uuid-12345",
  "approval_required": true,
  "cloud_model_blocked": false,
  "data_class": "YELLOW",
  "data_class_patterns": ["Private Code"],
  "message": "This data appears private/sensitive. Approve sending to Claude Code?",
  "allowed_models": ["qwen3.5:2b", "qwen3.5:4b"],
  "duration_ms": 150
}
```

**RED-Data Blocked Response (403):**
```json
{
  "id": "req-uuid-12345",
  "approval_required": true,
  "cloud_model_blocked": true,
  "data_class": "RED",
  "data_class_patterns": ["CPF", "Bank Account Keywords"],
  "message": "Sensitive financial/tax data detected and cannot be sent to cloud models. Local processing only. Approve?",
  "allowed_models": ["qwen3.5:2b", "qwen3.5:4b", "qwen3.5:9b"],
  "duration_ms": 150
}
```

**Error Response (503):** (Ollama unavailable)
```json
{
  "detail": "Ollama service is unavailable",
  "retry_after_seconds": 5
}
```

**Behavior:**
1. Verify JWT + extract user_id.
2. Classify prompt data (GREEN/YELLOW/RED).
3. If RED: return 403 with allowed_models = local-only.
4. If YELLOW and model_preference includes cloud: return 202 approval_required.
5. Acquire inference queue semaphore (wait if needed).
6. Select model (explicit preference or auto-select default).
7. Call appropriate provider (Ollama or Claude Code).
8. Return response or error.
9. Log action to audit_logs with tokens_used, duration.

---

#### `POST /chat/approve` (after approval-required response)

**Request:**
```json
{
  "request_id": "req-uuid-12345",
  "approved": true
}
```

**Success Response (200):**
```json
{
  "id": "req-uuid-12345",
  "model_used": "claude-code",
  "response": "...",
  "tokens_used": {"input": 12, "output": 50}
}
```

**Rejected Response (200):**
```json
{
  "id": "req-uuid-12345",
  "message": "Request cancelled by user"
}
```

**Behavior:**
- Look up request_id in some cache (in-memory dict or short-lived Redis, stored during /chat call).
- If approved=true, re-submit with the requested cloud model.
- If approved=false, cancel (return cancellation message).
- Log approval_status to audit_logs.

---

### Tool Endpoints (MCP)

#### `POST /tools/{tool_name}`

**Request:**
```json
{
  "arguments": {
    "key1": "value1",
    "key2": "value2"
  }
}
```

**Success Response (200):**
```json
{
  "id": "req-uuid-12345",
  "tool": "google_calendar.list_events",
  "status": "success",
  "result": {
    "events": [...]
  },
  "duration_ms": 500
}
```

**Error Response (400):** (invalid arguments)
```json
{
  "detail": "Missing required argument: date_range"
}
```

**Behavior:**
- Look up tool definition from MCP registry.
- Validate arguments against schema.
- Call MCP tool handler (stub for Phase 3; filled in by Phase 5+).
- Log tool call to audit_logs.
- Return result or error.

---

#### `GET /tools`

**Response (200):**
```json
{
  "tools": [
    {
      "name": "google_calendar.list_events",
      "description": "List events from Google Calendar",
      "arguments": {
        "date_range": {"type": "string", "required": true}
      }
    },
    ...
  ]
}
```

---

### Health & Status Endpoints

#### `GET /health`

**Response (200):**
```json
{
  "status": "healthy",
  "database": "connected",
  "ollama": "connected",
  "queue_depth": 0
}
```

---

#### `GET /status`

**Response (200):**
```json
{
  "gateway_version": "0.1.0",
  "phase": 3,
  "uptime_seconds": 3600,
  "models_available": ["qwen3.5:2b", "qwen3.5:4b", "claude-code"],
  "active_sessions": 1,
  "queue_depth": 0
}
```

---

### Audit Log Endpoints (Admin)

#### `GET /audit/logs`

**Query Parameters:**
- `user_id` (optional): filter by user.
- `start_time` (optional): ISO 8601 timestamp, start of range.
- `end_time` (optional): ISO 8601 timestamp, end of range.
- `agent` (optional): filter by agent name.
- `result` (optional): 'success', 'error', 'timeout', 'blocked_red_data'.
- `limit` (optional, default 100): max rows to return.

**Response (200):**
```json
{
  "logs": [
    {
      "timestamp": "2026-08-29T14:32:45Z",
      "user": "wife",
      "agent": "news",
      "action": "request_inference",
      "model": "qwen3.5:2b",
      "data_class": "GREEN",
      "result": "success",
      "duration_ms": 8500
    },
    ...
  ],
  "total": 150
}
```

**Behavior:**
- Query audit_logs table with filters.
- Return paginated results (limit per request).
- For Phase 3, only the authenticated user can view their own logs. (Phase 10 may add admin-view-all.)

---

## 5. Error Handling & Retry Policy

### Retry Logic

**Automatic retry on:**
- `timeout` (inference took too long): retry up to 3 times, exponential backoff (1s, 2s, 4s).
- `connection_refused` (Ollama crashed): retry up to 3 times, exponential backoff.
- `http_5xx` (Ollama returns 500+): retry once, then fail.

**Fail immediately on:**
- `out_of_memory` (VRAM exhausted): don't retry.
- `model_not_found`: don't retry.
- `invalid_request` (malformed prompt): don't retry.
- `authentication_error` (API key invalid): don't retry.

### Error Response Format

All error responses include:
```json
{
  "error": {
    "code": "timeout",
    "message": "Request timed out after 3 retries",
    "retry_after": 5,
    "request_id": "req-uuid-12345"
  }
}
```

---

## 6. Data Classification (Detailed)

### RED Patterns (Data Must Stay Local)

Regex patterns that trigger RED classification:

- **CPF**: `\d{3}\.\d{3}\.\d{3}-\d{2}` (formatted) or `\d{11}` (unformatted, at word boundary).
- **Bank keywords**: `\b(agência|conta corrente|conta|dígito|banco)\b` (Portuguese).
- **IRPF/Tax keywords**: `\b(IRPF|informe de rendimentos|imposto de renda|receitanet|Gov\.br)\b` (case-insensitive).
- **Financial transactions**: `\b(transferência|débito|crédito|extrato|saldo)\b` (Portuguese).
- **Credential keywords**: `\bsenha\b`, `\bcódigo\b` (in context of "my X is...").
- **CNPJ**: `\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}` (formatted).
- **RG**: `\b(RG|RG:)\b` (document ID keyword).

### YELLOW Patterns (Requires Approval for Cloud)

- **Private code keywords**: `\b(repositório privado|proprietary|confidential|internal|secret)\b`.
- **Private business keywords**: `\b(confidential|business secret|for internal use only)\b`.

### GREEN Classification

All other data.

---

## 7. Configuration

### Environment Variables (`.env`)

```bash
# Server
GATEWAY_ENV=production              # or 'development'
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
GATEWAY_WORKERS=4

# JWT
GATEWAY_JWT_SECRET=<random_64_chars>  # Generate with: python -c "import secrets; print(secrets.token_urlsafe(48))"
GATEWAY_JWT_ALGORITHM=HS256

# Database
GATEWAY_DB_PATH=/data/ai-platform/gateway.db   # SQLite file path

# Ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434        # Host ollama.service

# Claude Code (if using)
CLAUDE_API_KEY=<anthropic_api_key>             # Set only if Claude Code is enabled

# Logging
GATEWAY_LOG_LEVEL=INFO              # or DEBUG for verbose
GATEWAY_LOG_AUDIT_RETENTION_DAYS=90
```

### Config File (`config.yaml`)

```yaml
---
server:
  env: production
  host: 0.0.0.0
  port: 8000
  debug: false

auth:
  jwt_ttl_seconds: 900           # 15 minutes
  refresh_token_ttl_seconds: 604800  # 7 days
  password_min_length: 8

models:
  default_tier: default          # 'default', 'heavier', 'batch'
  inference_queue_size: 1        # single-at-a-time
  timeout_default_seconds: 120

ollama:
  base_url: http://127.0.0.1:11434
  max_retries: 3
  retry_backoff_ms: [1000, 2000, 4000]

data_classification:
  red_patterns:
    - pattern: '\d{3}\.\d{3}\.\d{3}-\d{2}'
      name: 'CPF'
    - pattern: '\bagência\b'
      name: 'Bank Account Keywords'
    # ... more patterns ...
  yellow_patterns:
    - pattern: '\bconfidential\b'
      name: 'Confidential'

audit_logging:
  retention_days: 90
  archive_path: /data/ai-platform/backups/audit-logs
```

---

## 8. Deployment & Docker

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY gateway/ ./gateway/
COPY config.yaml .
COPY .env .

# Create data directory
RUN mkdir -p /data/ai-platform

# Run
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose (`docker-compose.yml`)

```yaml
---
services:
  gateway:
    build: .
    container_name: gateway
    network_mode: host
    volumes:
      - /mnt/data/ai-platform:/data/ai-platform
      - /etc/ai-platform/secrets:/secrets:ro
    environment:
      GATEWAY_ENV: production
      GATEWAY_DB_PATH: /data/ai-platform/gateway.db
      OLLAMA_BASE_URL: http://127.0.0.1:11434
      CLAUDE_API_KEY_FILE: /secrets/claude-api-key
    restart: unless-stopped
```

---

## 9. Testing Requirements

### Unit Tests

- **Authentication**: password hashing, JWT generation/verification, refresh token flow.
- **Data classification**: regex patterns match RED/YELLOW/GREEN correctly.
- **Audit logging**: logs are written correctly, RED patterns are redacted.
- **Queue enforcement**: semaphore serializes requests.

### Integration Tests

- **Gateway → Ollama**: end-to-end inference request.
- **Login flow**: user logs in, receives tokens, can make authenticated request.
- **Approval workflow**: RED-data request is flagged, re-submission is approved.
- **Error retry**: timeout triggers retry, success on second attempt.

### Manual Testing

- Curl/Postman: test all endpoints.
- Approval dialog: RED-data request is shown, user approves, request succeeds.
- Audit log: verify logs contain correct action, user, model, duration.

---

## 10. Security Considerations

1. **JWT Secret**: Must be stored securely (not in code). Generated at first startup, stored in `.env`.
2. **Password Reset**: Phase 3 doesn't include self-service password reset. Admin-only for now.
3. **Rate Limiting**: Phase 3 has no rate limiting. Add in Phase 10 if needed (e.g., max 100 requests/minute per user).
4. **HTTPS**: Phase 3 runs HTTP (internal network). Add HTTPS in Phase 10 (reverse proxy with Let's Encrypt).
5. **CORS**: Phase 3 allows all origins (Docker internal network). Tighten in Phase 4 (Web UI deployed, set CORS to exact origin).

---

## 11. Phase 3 Deliverables Checklist

- [x] Requirements captured (this document).
- [ ] FastAPI project scaffold.
- [ ] SQLAlchemy models + migrations.
- [ ] Authentication endpoints (login, refresh, logout).
- [ ] Setup endpoint (/admin/setup/user).
- [ ] Chat endpoint (model routing, queue, classification).
- [ ] Approval endpoint (/chat/approve).
- [ ] Tools endpoints (MCP abstraction).
- [ ] Audit logging (SQLite writer, redaction).
- [ ] Data classification (regex engine).
- [ ] Error handling (retry policy, error responses).
- [ ] Ollama provider (client library).
- [ ] Claude Code provider (stub).
- [ ] Docker + Docker Compose.
- [ ] Config file loader.
- [ ] Unit tests (50+ test cases).
- [ ] Integration tests (10+ scenarios).
- [ ] API documentation (Swagger UI).
- [ ] README with setup + deployment.
- [ ] Manual testing (curl scripts, Postman collection).

---

## 12. Success Criteria (Phase 3 "Done")

1. **Gateway runs in Docker and is reachable at `http://localhost:8000`.**
2. **First user can be created via `/admin/setup/user` POST endpoint.**
3. **User can log in, receive JWT + refresh token.**
4. **Authenticated user can POST to `/chat` and receive response from Ollama.**
5. **RED-data request is classified correctly and blocked (403 response).**
6. **YELLOW-data request is flagged (202 response) and re-submission succeeds if approved.**
7. **Audit log contains entries for all actions (login, chat, approval, error).**
8. **Ollama unavailability triggers retries and eventually returns 503.**
9. **OpenAPI docs are available at `http://localhost:8000/docs`.**
10. **All unit + integration tests pass.**

---

## See Also

- [CONTEXT.md](../CONTEXT.md) — Domain model and key terms.
- [docs/adr/0001-stateless-jwt-authentication.md](../docs/adr/0001-stateless-jwt-authentication.md) — Auth architecture.
- [docs/adr/0002-single-inference-queue.md](../docs/adr/0002-single-inference-queue.md) — Concurrency.
- [docs/adr/0003-red-data-local-only-enforcement.md](../docs/adr/0003-red-data-local-only-enforcement.md) — Data classification.
