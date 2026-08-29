# Agent Gateway - Phase 3

Central authentication and routing service for Personal AI Agent Platform.

- **Version**: 3.0.0
- **Phase**: 3 (Agent Gateway + Authentication)
- **Status**: Ready for testing and hardening

## Overview

The Agent Gateway is a FastAPI service running in Docker that:

- **Authenticates** requests via username/password → JWT token flow
- **Routes** model calls to local Qwen (via Ollama) or cloud providers (Claude Code)
- **Enforces** single-inference-at-a-time via request queue
- **Classifies** data and enforces RED-data local-only rules
- **Logs** all actions to SQLite audit trail
- **Manages** sessions and user permissions (stateless JWT)

## Architecture

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
│  ├─ Auth Layer (JWT verification)            │
│  ├─ Data Classifier (RED/YELLOW/GREEN)       │
│  ├─ Request Queue (async.Semaphore(1))       │
│  ├─ Ollama Provider (local Qwen)             │
│  ├─ Claude Provider (cloud)                  │
│  └─ Audit Logger (SQLite)                    │
└──────────────────────────────────────────────┘
       │                    │
       │                    │
       ▼                    ▼
   Ollama API          Claude API
  (127.0.0.1:11434)   (api.anthropic.com)
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Linux host with 2+ cores, 4GB+ RAM
- Ollama running with Qwen models (Phase 2+)

### Setup

1. **Clone repository and navigate to gateway:**
   ```bash
   cd gateway/
   ```

2. **Create .env file:**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   # IMPORTANT: Set GATEWAY_JWT_SECRET to a random string (min 32 chars)
   ```

3. **Start services with Docker Compose:**
   ```bash
   docker-compose up -d
   ```

4. **Verify Gateway is running:**
   ```bash
   curl http://localhost:8000/health
   # Expected response: {"status": "ok"}
   ```

5. **Create first user (one-time setup):**
   ```bash
   curl -X POST http://localhost:8000/auth/admin/setup/user \
     -H "Content-Type: application/json" \
     -d '{"username": "user", "password": "your_secure_password"}'
   ```

## Installation (Manual)

If not using Docker:

1. **Create virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set environment variables:**
   ```bash
   export GATEWAY_ENV=development
   export GATEWAY_JWT_SECRET="your-secret-key-min-32-chars"
   export OLLAMA_BASE_URL=http://localhost:11434
   ```

4. **Run application:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

## Configuration

### Environment Variables

Key variables (see `.env.example` for complete list):

- `GATEWAY_ENV`: "development" or "production"
- `GATEWAY_JWT_SECRET`: Secret key for JWT signing (min 32 characters, required)
- `GATEWAY_DB_PATH`: SQLite database path (default: `/data/ai-platform/gateway.db`)
- `GATEWAY_LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `OLLAMA_BASE_URL`: Ollama API endpoint (default: `http://ollama:11434`)
- `CLAUDE_API_KEY`: Claude API key (optional, for Phase 7+)

### config.yaml

Optional YAML configuration file with data classification patterns:

```yaml
data_classification:
  red_patterns:
    - \bCPF\b
    - \d{3}\.\d{3}\.\d{3}-\d{2}  # CPF format
    - "bank account"
    # ... more patterns
  yellow_patterns:
    - "confidential"
    - "proprietary"
```

## API Endpoints

### Authentication (Public)

#### `POST /auth/login`
Login and get tokens.

**Request:**
```json
{
  "username": "user",
  "password": "password123"
}
```

**Response (200):**
```json
{
  "access_token": "<jwt_token>",
  "refresh_token": "<refresh_token_string>",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### `POST /auth/refresh`
Refresh access token using refresh token.

**Request:**
```json
{
  "refresh_token": "<refresh_token_string>"
}
```

**Response (200):**
```json
{
  "access_token": "<new_jwt_token>",
  "token_type": "bearer",
  "expires_in": 900
}
```

#### `POST /auth/logout`
Logout and revoke refresh token.

**Response (200):**
```json
{
  "message": "Logged out successfully"
}
```

#### `POST /admin/setup/user` (One-time)
Create first user (only active if users table is empty).

**Request:**
```json
{
  "username": "user",
  "password": "password123"
}
```

**Response (200):**
```json
{
  "user_id": 1,
  "username": "user",
  "message": "First user created. Setup endpoint is now disabled."
}
```

### Chat / Inference (Authenticated)

All endpoints below require `Authorization: Bearer <jwt_token>` header.

#### `POST /chat`
Submit prompt for inference.

**Request:**
```json
{
  "prompt": "Summarize the latest news on AI",
  "model_preference": "qwen3.5:2b",
  "agent": "news"
}
```

**Response (200 - Success):**
```json
{
  "id": "req-uuid-12345",
  "model_used": "qwen3.5:2b",
  "data_class": "GREEN",
  "data_class_patterns": [],
  "approval_required": false,
  "approval_status": "auto_approved",
  "response": "Here are the top AI news items...",
  "tokens_used": {"input": 12, "output": 45},
  "duration_ms": 8500
}
```

**Response (202 - Approval Required):**
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

**Response (403 - RED Data Blocked):**
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

#### `POST /chat/approve`
Approve or deny a pending chat request.

**Request:**
```json
{
  "request_id": "req-uuid-12345",
  "approved": true
}
```

**Response (200):**
```json
{
  "request_id": "req-uuid-12345",
  "status": "approved",
  "message": "Request approved. Please resubmit to process."
}
```

### Audit Logging (Authenticated)

#### `GET /audit/logs`
Query audit logs for current user.

**Query Parameters:**
- `start_time`: ISO 8601 start time (optional)
- `end_time`: ISO 8601 end time (optional)
- `agent`: Filter by agent name (optional)
- `result`: Filter by result ("success", "error", etc.) (optional)
- `limit`: Max results (default 100, max 1000)

**Response (200):**
```json
{
  "logs": [
    {
      "id": 123,
      "timestamp": "2026-08-29T14:32:45Z",
      "user_id": 1,
      "request_id": "req-uuid-12345",
      "agent": "news",
      "action": "chat",
      "model": "qwen3.5:2b",
      "data_class": "GREEN",
      "data_class_patterns": [],
      "approval_required": false,
      "approval_status": "auto_approved",
      "tokens_used": {"input": 12, "output": 45},
      "result": "success",
      "error_message": null,
      "queue_wait_ms": 150,
      "duration_ms": 8500
    }
  ],
  "total": 1
}
```

## Data Classification

The Gateway automatically classifies all data as **RED**, **YELLOW**, or **GREEN** based on pattern matching:

- **RED**: Sensitive data, never sent to cloud (CPF, bank statements, financial records)
- **YELLOW**: Requires approval before cloud transmission (proprietary code, internal docs)
- **GREEN**: Cloud-safe (public news, generic questions)

Patterns are loaded from `config.yaml`. RED-data requests are blocked from cloud models and require local-only processing.

## Error Responses

All errors follow a standard format:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested resource was not found",
    "retry_after": 30,
    "request_id": "req-uuid-12345"
  }
}
```

Common status codes:

- `400 Bad Request`: Invalid request
- `401 Unauthorized`: Missing or invalid token
- `403 Forbidden`: RED data detected (local-only)
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Ollama unavailable
- `504 Gateway Timeout`: Request timeout

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Running with hot-reload

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Database

The SQLite database is created automatically at startup. To reset:

```bash
# Delete the database file
rm /data/ai-platform/gateway.db

# Restart the service
docker-compose restart gateway
```

## Security

### JWT Configuration

- Token algorithm: HS256
- Access token TTL: 15 minutes
- Refresh token TTL: 7 days
- Secret must be min 32 characters (required)

### Password Storage

- Algorithm: Argon2 (memory-hard, resistant to brute-force)
- Min length: 8 characters
- Each password hashed differently (salt included)

### Audit Logging

- All actions logged to SQLite with full context
- RED patterns redacted before storage
- Timestamps in UTC, ISO 8601 format
- Audit logs retained for 90 days (archival in Phase 4+)

## Monitoring

### Health Check

```bash
curl http://localhost:8000/health
# Response: {"status": "ok"}
```

### Logs

JSON-formatted logs are output to stdout (captured by Docker):

```bash
docker logs gateway
```

Each log entry includes:
- timestamp
- level (INFO, WARNING, ERROR, etc.)
- logger name
- message
- request_id (for tracing)
- Sensitive data (JWT, passwords, API keys) are redacted

### Metrics

- Queue depth (concurrent requests waiting)
- Queue wait time (time from submission to acquisition)
- Request duration (total end-to-end time)
- Token usage (input/output tokens)
- Error rates by type

## Troubleshooting

### Gateway fails to start

**Check logs:**
```bash
docker logs gateway
```

**Common issues:**
- `GATEWAY_JWT_SECRET` not set or too short
- Database file path not writable
- Ollama not responding

### High latency

- Check queue depth: multiple requests waiting for model lock
- Check Ollama performance: may need faster hardware
- See "Performance Testing" section for benchmarks

### Database errors

- Check disk space: SQLite needs space for logs
- Check permissions: gateway user must write to `/data/ai-platform/`
- Check file locks: ensure only one gateway instance running

## Next Steps (Phase 4+)

- Web UI (login form, chat interface)
- Session management improvements
- Rate limiting and quotas
- Multi-user permissions and scopes
- News Aggregator agent (Phase 5)
- Google Calendar integration (Phase 6)

## See Also

- [CONTEXT.md](../../CONTEXT.md) — Domain model and architecture
- [docs/adr/](../../docs/adr/) — Architecture Decision Records
- [PHASE-3-SPECIFICATION.md](../../Plan/PHASE-3-SPECIFICATION.md) — Full Phase 3 spec
- [PHASE-3-IMPLEMENTATION-ISSUES.md](../../Plan/PHASE-3-IMPLEMENTATION-ISSUES.md) — Implementation details
