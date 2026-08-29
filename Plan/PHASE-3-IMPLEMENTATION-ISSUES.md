# Phase 3 Implementation Issues

**Version**: 1.0  
**Date**: 2026-08-29  
**Total Estimated Effort**: ~40–50 days (2-person team or 1 person, 2 months)

---

## Roadmap Overview

```
Week 1: Project scaffold + core models
Week 2: Auth endpoints + tests
Week 3: Chat/inference + queue
Week 4: Data classification + audit logging
Week 5: Error handling + MCP stubs
Week 6: Docker + deployment
Week 7: Integration tests + docs
Week 8+: Manual testing, hardening, release
```

---

## Epic 1: Project Setup & Core Infrastructure

### Issue 1.1: Create FastAPI project scaffold
**Size**: 1 day  
**Depends on**: None  
**Description**:
- Create `/gateway` folder with standard FastAPI structure.
- Folders: `gateway/`, `tests/`, `docs/`.
- Files: `main.py`, `models.py`, `schemas.py`, `config.py`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.env.example`.
- Set up `pyproject.toml` or `requirements.txt` with FastAPI, SQLAlchemy, Pydantic, python-dotenv, argon2-cffi, PyJWT, httpx.
- Add `.gitignore` (exclude `.env`, `__pycache__`, `.pytest_cache`, `*.db`).

**Acceptance Criteria**:
- Can run `pip install -r requirements.txt` without errors.
- Can import all main modules.
- `uvicorn gateway.main:app` starts the server without errors.

---

### Issue 1.2: Set up SQLAlchemy ORM + SQLite connection
**Size**: 1 day  
**Depends on**: 1.1  
**Description**:
- Create `gateway/db.py` with SQLAlchemy engine, session factory, Base class.
- Set SQLite connection string from config (default: `/data/ai-platform/gateway.db`).
- Create `gateway/models.py` with SQLAlchemy model definitions (Users, RefreshTokens, AuditLogs, ModelConfig).
- Add database initialization function that creates tables on startup.
- Add fixtures for testing (in-memory SQLite for unit tests).

**Acceptance Criteria**:
- `python -c "from gateway.db import engine; engine.execute('SELECT 1')"` works.
- SQLite file is created at the configured path.
- All tables exist after startup.
- Fixtures create isolated test databases.

---

### Issue 1.3: Set up configuration loader (YAML + .env)
**Size**: 1 day  
**Depends on**: 1.1  
**Description**:
- Create `gateway/config.py` with Pydantic config model.
- Load from environment variables (GATEWAY_ENV, GATEWAY_DB_PATH, etc.).
- Load from `config.yaml` (server, auth, models, ollama, data_classification sections).
- Merge env + YAML (env overrides YAML).
- Validate required fields at startup.

**Acceptance Criteria**:
- Can load both `.env` and `config.yaml` without errors.
- Environment variable overrides YAML value.
- Missing required field raises clear error message at startup.
- Example `.env` and `config.yaml` are checked in.

---

### Issue 1.4: Set up logging infrastructure
**Size**: 1 day  
**Depends on**: 1.3  
**Description**:
- Configure Python `logging` module with JSON formatter (for structured logs).
- Logs go to stdout (Docker can capture them).
- Audit-specific logger: writes to SQLite audit_logs table (see Issue 4.1).
- Log levels configurable via GATEWAY_LOG_LEVEL.
- Ensure JWT tokens are never logged (redact in formatter).

**Acceptance Criteria**:
- Logs are formatted as JSON.
- JWT tokens don't appear in logs.
- Log level can be changed via environment variable.
- Audit logs are separate from regular logs.

---

## Epic 2: Authentication & Session Management

### Issue 2.1: Implement password hashing (Argon2)
**Size**: 0.5 day  
**Depends on**: 1.2  
**Description**:
- Create `gateway/auth.py` with functions:
  - `hash_password(password: str) -> str` (use argon2-cffi).
  - `verify_password(password: str, hash: str) -> bool`.
- Add password validation: min 8 chars, require mix of upper/lower/digits/symbols (future relaxable for testing).
- Add tests for hashing (ensure same password produces different hashes, verify works correctly).

**Acceptance Criteria**:
- `hash_password("test123!")` returns different hash each time.
- `verify_password("test123!", hash)` returns True.
- `verify_password("wrong", hash)` returns False.

---

### Issue 2.2: Implement JWT token generation & verification
**Size**: 1 day  
**Depends on**: 2.1  
**Description**:
- Create JWT helper functions in `gateway/auth.py`:
  - `create_access_token(user_id: int, expires_delta: timedelta) -> str`.
  - `verify_access_token(token: str) -> dict` (returns claims or raises exception).
  - `create_refresh_token() -> str` (random, secure).
- Use PyJWT library (HS256 algorithm, secret from config).
- Token structure: `{"user_id": N, "exp": unix_timestamp}`.
- Add tests for token creation, verification, expiry.

**Acceptance Criteria**:
- Created token can be verified and claims extracted.
- Expired token raises exception.
- Invalid signature raises exception.
- Token TTL is 15 minutes (900 seconds).

---

### Issue 2.3: Implement `/auth/login` endpoint
**Size**: 1 day  
**Depends on**: 1.2, 2.1, 2.2  
**Description**:
- Create endpoint: `POST /auth/login`.
- Request schema: `{username, password}`.
- Response schema: `{access_token, refresh_token, token_type, expires_in}`.
- Logic:
  - Query users table by username.
  - Verify password (Argon2).
  - Generate JWT (15-min TTL).
  - Generate refresh token (7-day TTL), insert into refresh_tokens table.
  - Update user.last_login_at.
  - Log login action to audit_logs.
  - Return tokens.
- Error cases: invalid username (401), invalid password (401), inactive user (403).

**Acceptance Criteria**:
- Valid login returns tokens.
- Invalid password returns 401.
- Inactive user returns 403.
- Audit log contains login entry.
- Refresh token is stored in DB.

---

### Issue 2.4: Implement `/auth/refresh` endpoint
**Size**: 0.5 day  
**Depends on**: 1.2, 2.2  
**Description**:
- Create endpoint: `POST /auth/refresh`.
- Request: `{refresh_token}`.
- Response: `{access_token, token_type, expires_in}`.
- Logic:
  - Look up refresh_token in DB.
  - Verify it exists, hasn't expired, not revoked.
  - Issue new JWT.
  - Log refresh action.
  - Return new JWT.
- Error: invalid/expired token (401).

**Acceptance Criteria**:
- Valid refresh token returns new JWT.
- Expired token returns 401.
- Revoked token returns 401.

---

### Issue 2.5: Implement `/auth/logout` endpoint
**Size**: 0.5 day  
**Depends on**: 1.2, 2.2  
**Description**:
- Create endpoint: `POST /auth/logout` (requires Bearer token).
- Logic: revoke the refresh token (set revoked_at = now).
- Log logout action.
- Return 200 message.

**Acceptance Criteria**:
- After logout, refresh token is marked revoked.
- Subsequent refresh attempts fail (401).

---

### Issue 2.6: Implement JWT middleware (verify token on all requests)
**Size**: 1 day  
**Depends on**: 2.2  
**Description**:
- Create middleware or dependency injection (FastAPI `Depends`).
- Middleware verifies Bearer token in `Authorization` header on all authenticated endpoints.
- Extracts user_id from token and makes it available to handlers (via request context or function parameter).
- Returns 401 if token missing/invalid.
- Endpoints that don't require auth: `/auth/login`, `/auth/refresh`, `/admin/setup/user`, `/health`.

**Acceptance Criteria**:
- Requests without token to protected endpoint return 401.
- Requests with valid token pass through.
- Requests with invalid token return 401.
- user_id is available to handlers.

---

### Issue 2.7: Implement `/admin/setup/user` endpoint (one-time setup)
**Size**: 0.5 day  
**Depends on**: 1.2, 2.1  
**Description**:
- Create endpoint: `POST /admin/setup/user` (no auth required, only active if users table empty).
- Request: `{username, password}`.
- Response: `{user_id, username, message}`.
- Logic:
  - Check if users table is empty.
  - If yes, create user with Argon2-hashed password.
  - Log setup action.
  - Disable endpoint (return 403 on subsequent calls).
  - Return user_id.
- Error: users already exist (403).

**Acceptance Criteria**:
- First call creates user and succeeds.
- Second call returns 403.
- Created user can log in.

---

## Epic 3: Chat / Inference Endpoints & Model Routing

### Issue 3.1: Create Ollama client library (`OllamaProvider`)
**Size**: 1 day  
**Depends on**: 1.3  
**Description**:
- Create `gateway/providers/ollama.py` with `OllamaProvider` class.
- Methods:
  - `async generate(prompt: str, model: str) -> dict` (calls Ollama HTTP API).
  - `list_models() -> list`.
  - `health_check() -> bool`.
- Use httpx (async HTTP client).
- Ollama endpoint: from config (default: `http://ollama:11434`).
- Handle errors: connection refused, timeout, model not found.
- Log requests (prompt length, model, duration).

**Acceptance Criteria**:
- Can connect to running Ollama instance.
- Can list available models.
- Can generate text for a prompt.
- Errors are handled gracefully.

---

### Issue 3.2: Create Claude Code provider stub (`ClaudeProvider`)
**Size**: 0.5 day  
**Depends on**: 1.3  
**Description**:
- Create `gateway/providers/claude.py` with `ClaudeProvider` class.
- Methods:
  - `async generate(prompt: str, model: str) -> dict` (stub for Phase 7+, returns placeholder).
  - `health_check() -> bool` (check API key is set, not validated yet).
- Read API key from environment or config.
- Log calls but don't actually invoke Anthropic API yet.

**Acceptance Criteria**:
- Provider can be instantiated.
- `health_check()` returns True if API key is set.
- `generate()` returns placeholder response.

---

### Issue 3.3: Implement data classifier (regex engine)
**Size**: 1 day  
**Depends on**: 1.3, 1.4  
**Description**:
- Create `gateway/classifier.py` with `classify_data(prompt: str) -> Classification` function.
- Classification object: `{level: 'RED'|'YELLOW'|'GREEN', patterns: list[str]}`.
- Load patterns from config (RED patterns, YELLOW patterns).
- Run regex matching (case-insensitive for most patterns).
- Return highest-severity classification (RED > YELLOW > GREEN).
- Log classification to audit logs (not just during errors).

**Acceptance Criteria**:
- CPF patterns trigger RED.
- Bank keywords trigger RED.
- IRPF keywords trigger RED.
- "confidential" triggers YELLOW.
- Generic text triggers GREEN.
- Multiple matches are recorded.

---

### Issue 3.4: Implement request queue (asyncio.Semaphore)
**Size**: 0.5 day  
**Depends on**: None  
**Description**:
- Create `gateway/queue.py` with global `inference_semaphore = asyncio.Semaphore(1)`.
- Wrapper function: `async with acquire_queue(request_id: str) -> context_manager`.
- Track queue entry/exit time for metrics.
- Log queue wait time to audit logs.

**Acceptance Criteria**:
- Multiple concurrent requests are serialized.
- First request acquires lock, others wait.
- Queue metrics are logged.

---

### Issue 3.5: Implement `/chat` endpoint
**Size**: 2 days  
**Depends on**: 3.1, 3.2, 3.3, 3.4, 2.6  
**Description**:
- Create endpoint: `POST /chat` (requires auth).
- Request schema: `{prompt, model_preference?, agent?, streaming?}`.
- Response schema: `{id, model_used, data_class, approval_required, approval_status, response, tokens_used?, duration_ms}`.
- Logic:
  1. Verify JWT (middleware).
  2. Classify data (RED/YELLOW/GREEN).
  3. If RED: return 403 with `approval_required=true`, `cloud_model_blocked=true`, allowed_models=local-only.
  4. If YELLOW and model_preference is cloud: return 202 with `approval_required=true`.
  5. Acquire queue semaphore.
  6. Select model (explicit preference or auto-select default tier).
  7. Call appropriate provider.
  8. Log to audit_logs (tokens, duration, result).
  9. Return response.
- Error handling: Ollama unavailable (retry 3x, then 503), timeout (retry 3x, then 504), invalid request (400).

**Acceptance Criteria**:
- Can submit prompt and receive response.
- RED data is blocked (403).
- YELLOW data requires approval (202).
- GREEN data proceeds without approval.
- Tokens used are recorded.
- Request is logged to audit_logs.

---

### Issue 3.6: Implement approval cache + `/chat/approve` endpoint
**Size**: 1 day  
**Depends on**: 3.5  
**Description**:
- Create in-memory cache (dict) for pending approval requests (request_id → prompt, model_preference, etc.).
- Cache entries expire after 5 minutes.
- Create endpoint: `POST /chat/approve`.
- Request: `{request_id, approved}`.
- Response: if approved, re-submit and return response; if denied, return cancellation message.
- Logic:
  - Look up request_id in cache.
  - If approved=true, re-submit with requested model (skip approval check this time).
  - If approved=false, delete from cache and return cancellation.
  - Log approval_status to audit_logs.
- Error: request_id not found (404), request expired (410).

**Acceptance Criteria**:
- RED-data request is cached.
- User approves, request succeeds.
- User denies, request is cancelled.
- Expired requests are cleaned up.

---

### Issue 3.7: Add model-selection logic (explicit vs. auto-select)
**Size**: 0.5 day  
**Depends on**: 3.5, 1.3  
**Description**:
- If `model_preference` is provided, use it (if allowed by data classification).
- Otherwise, auto-select based on data classification and agent context:
  - GREEN data → use default tier (qwen3.5:2b).
  - YELLOW (approved) → use default tier (unless user selected heavier).
  - RED (approved) → use default tier.
- Agent can hint at preferred tier (stored in agent registry, Phase 5+).

**Acceptance Criteria**:
- Explicit model selection is respected.
- Auto-selection picks default tier for simple requests.
- Model selection respects data-classification constraints.

---

## Epic 4: Audit Logging & Data Redaction

### Issue 4.1: Implement audit logging to SQLite
**Size**: 1 day  
**Depends on**: 1.2, 1.4  
**Description**:
- Create `gateway/audit.py` with `AuditLogger` class.
- Async method: `log_action(user_id, agent, action, model, data_class, patterns, approval_required, approval_status, tokens, result, error, duration_ms, queue_wait_ms)`.
- Write to audit_logs table.
- Before inserting `error_message`, redact RED patterns (see Issue 4.2).
- Serialize `data_class_patterns` and `tokens_used` as JSON.
- Timestamp in UTC.

**Acceptance Criteria**:
- Log entries are written to audit_logs table.
- Timestamps are UTC, ISO 8601 format.
- JSON fields are correctly serialized.

---

### Issue 4.2: Implement RED-pattern redaction in logs
**Size**: 0.5 day  
**Depends on**: 3.3, 4.1  
**Description**:
- Create `gateway/redaction.py` with `redact_red_patterns(text: str) -> str` function.
- Before logging error messages, replace matched RED patterns with `[REDACTED]`.
- Use same regex patterns as data classifier.
- Log file paths, PII in error messages, etc.

**Acceptance Criteria**:
- CPF in error message is replaced with [REDACTED].
- Bank keywords in error message are replaced.
- Non-RED content is not altered.

---

### Issue 4.3: Implement audit log retention & archival
**Size**: 1 day  
**Depends on**: 1.2, 4.1  
**Description**:
- Create background task or CLI command: `archive_old_audit_logs()`.
- Run monthly (scheduled or manual): move audit_logs older than 90 days to compressed file.
- Archive format: CSV or JSON, gzipped.
- Archive stored at `/mnt/data/ai-platform/backups/audit-logs/`.
- Document in README: how to run archival manually.

**Acceptance Criteria**:
- Logs older than 90 days are archived.
- Archive files are timestamped and gzipped.
- Can extract and search old logs if needed.

---

### Issue 4.4: Implement audit log query endpoint (`GET /audit/logs`)
**Size**: 1 day  
**Depends on**: 1.2, 4.1  
**Description**:
- Create endpoint: `GET /audit/logs` (requires auth).
- Query parameters: `user_id`, `start_time`, `end_time`, `agent`, `result`, `limit`.
- For Phase 3, user can only query their own logs (not admin-view-all yet).
- Response: `{logs: [...], total: N}`.
- Paginate: return up to `limit` rows (default 100).

**Acceptance Criteria**:
- Can query logs for current user.
- Filters work (e.g., only return GREEN data results).
- Pagination works.
- Cannot query other users' logs.

---

## Epic 5: Error Handling & Resilience

### Issue 5.1: Implement retry logic for Ollama calls
**Size**: 1 day  
**Depends on**: 3.1, 1.3  
**Description**:
- Create `gateway/retry.py` with `retry_async(func, max_retries=3, backoff=[1, 2, 4])` helper.
- Wrap all Ollama calls with retry logic.
- Retry on: timeout, connection refused, HTTP 5xx.
- Don't retry on: out of memory, model not found, invalid request, auth error.
- Exponential backoff between retries.
- Log each retry attempt.

**Acceptance Criteria**:
- Transient errors trigger retries.
- Permanent errors fail immediately.
- Retry attempts are logged.

---

### Issue 5.2: Implement error response formatting
**Size**: 0.5 day  
**Depends on**: 3.1, 3.5  
**Description**:
- Standardize error responses across all endpoints.
- Format: `{error: {code, message, retry_after?, request_id}}`.
- Map internal errors to user-friendly messages.
- Include request_id for tracing.

**Acceptance Criteria**:
- All error responses follow the standard format.
- Error messages are user-friendly (no stack traces).
- request_id is present for audit trail.

---

### Issue 5.3: Implement timeout handling
**Size**: 0.5 day  
**Depends on**: 3.1, 3.5, 5.1  
**Description**:
- Configure timeouts per model tier (from config):
  - default tier: 120 sec.
  - heavier tier: 180 sec.
  - batch tier: 600 sec.
- Wrap Ollama calls with `asyncio.timeout()` or `httpx` timeout.
- On timeout, retry (up to max_retries), then return 504 Gateway Timeout.

**Acceptance Criteria**:
- Requests timeout after configured duration.
- Timeout triggers retries.
- Final 504 response includes message and request_id.

---

## Epic 6: MCP (Model Context Protocol) Integration

### Issue 6.1: Design MCP tool registry & abstraction
**Size**: 1 day  
**Depends on**: 1.3  
**Description**:
- Create `gateway/mcp.py` with:
  - `ToolRegistry` class: maps tool names to handler functions.
  - `Tool` schema: name, description, arguments (JSON schema), handler.
  - `register_tool(name, tool_def, handler)` function.
- Initially, tools are registered manually (Phase 5+ adds plugin discovery).
- Stub tools: `google_calendar.list_events`, `google_calendar.create_event`, etc. (Phase 6+ implements).

**Acceptance Criteria**:
- Tools can be registered.
- Tool registry can be queried.
- Tool definitions include schema for validation.

---

### Issue 6.2: Implement `/tools` endpoint (list available tools)
**Size**: 0.5 day  
**Depends on**: 6.1  
**Description**:
- Create endpoint: `GET /tools` (requires auth).
- Response: list of tool definitions (name, description, arguments).

**Acceptance Criteria**:
- Returns list of registered tools.
- Tool schemas are correct.

---

### Issue 6.3: Implement `/tools/{tool_name}` endpoint (call MCP tool)
**Size**: 1 day  
**Depends on**: 6.1  
**Description**:
- Create endpoint: `POST /tools/{tool_name}` (requires auth).
- Request: `{arguments: {...}}`.
- Response: `{id, tool, status, result, duration_ms}`.
- Logic:
  1. Verify JWT.
  2. Look up tool in registry.
  3. Validate arguments against schema.
  4. Call tool handler.
  5. Log to audit_logs (tool call, arguments, result).
  6. Return result.
- Error: tool not found (404), invalid arguments (400), tool error (500).

**Acceptance Criteria**:
- Can call registered tools.
- Arguments are validated.
- Tool calls are logged.

---

## Epic 7: Docker & Deployment

### Issue 7.1: Create Dockerfile for Gateway
**Size**: 0.5 day  
**Depends on**: 1.1, 1.3, 1.4  
**Description**:
- Write Dockerfile:
  - Base: python:3.11-slim.
  - Install requirements, copy code.
  - Expose port 8000.
  - CMD: uvicorn gateway.main:app.
- Add `.dockerignore`.

**Acceptance Criteria**:
- Dockerfile builds without errors.
- Image runs and server is reachable at port 8000.

---

### Issue 7.2: Create docker-compose.yml
**Size**: 0.5 day  
**Depends on**: 7.1  
**Description**:
- Write docker-compose.yml:
  - Service: ollama (official image, mount volumes for models).
  - Service: gateway (built from Dockerfile).
  - Volumes: /mnt/data/ai-platform for persistent data.
  - Environment: GATEWAY_DB_PATH, OLLAMA_BASE_URL, etc.
  - Networking: gateway and ollama on same network.
- Add comments explaining each section.

**Acceptance Criteria**:
- `docker-compose up` starts both services.
- Gateway and Ollama can communicate.

---

### Issue 7.3: Create .env.example file
**Size**: 0.25 day  
**Depends on**: 1.3  
**Description**:
- Document all required environment variables.
- Provide example values (safe defaults).
- Comments explaining each variable.

**Acceptance Criteria**:
- `.env.example` is complete and commented.
- User can copy to `.env` and run.

---

### Issue 7.4: Create startup health-check script
**Size**: 0.5 day  
**Depends on**: 7.1, 7.2  
**Description**:
- Create `scripts/wait-for-ollama.sh`: wait for Ollama to be healthy before starting Gateway.
- Use `curl` to poll `http://ollama:11434/api/tags` until it succeeds.
- Add to docker-compose (depends_on + healthcheck).

**Acceptance Criteria**:
- Docker Compose waits for Ollama before starting Gateway.
- Both services are ready when compose is up.

---

## Epic 8: Testing

### Issue 8.1: Write unit tests for authentication
**Size**: 1 day  
**Depends on**: 2.1, 2.2, 2.7  
**Description**:
- Test password hashing: different hash each time, verification works.
- Test JWT creation/verification: token can be parsed, claims are correct, expired token fails.
- Test /auth/login: valid login succeeds, invalid password fails, inactive user fails.
- Test /auth/refresh: valid token refresh succeeds, expired token fails.
- Test /admin/setup/user: first user created, second call fails.
- Use pytest, mock database.
- Coverage: >90%.

**Acceptance Criteria**:
- 30+ test cases, all passing.
- Coverage >90% for auth module.

---

### Issue 8.2: Write unit tests for data classification
**Size**: 1 day  
**Depends on**: 3.3  
**Description**:
- Test RED patterns: CPF formats, bank keywords, IRPF keywords.
- Test YELLOW patterns: confidential, private code.
- Test GREEN: generic text.
- Test multi-pattern matches (prompt has both CPF and bank keywords → RED).
- Use pytest.

**Acceptance Criteria**:
- 20+ test cases, all passing.
- All patterns covered.

---

### Issue 8.3: Write unit tests for audit logging
**Size**: 0.5 day  
**Depends on**: 4.1, 4.2  
**Description**:
- Test audit log insertion: fields are correct, JSON serialization works.
- Test redaction: RED patterns are replaced in error messages.
- Test timestamp: UTC, ISO 8601 format.
- Use pytest + mock database.

**Acceptance Criteria**:
- 10+ test cases, all passing.

---

### Issue 8.4: Write integration tests (Gateway → Ollama)
**Size**: 2 days  
**Depends on**: 3.5, 3.1  
**Description**:
- Set up test Ollama instance (or mock HTTP server).
- Test end-to-end chat request:
  1. Login → get JWT.
  2. POST /chat with simple prompt.
  3. Receive response.
  4. Verify audit log entry.
- Test error cases: Ollama unavailable (503), timeout (504).
- Use pytest + Docker Compose for test environment.

**Acceptance Criteria**:
- 10+ integration test cases, all passing.
- E2E request/response flow verified.

---

### Issue 8.5: Write manual test suite (Postman / curl scripts)
**Size**: 1 day  
**Depends on**: 3.5, 4.4  
**Description**:
- Create Postman collection or curl scripts for manual testing.
- Covers: login, chat (GREEN/YELLOW/RED), approval, audit logs.
- Document steps in README.

**Acceptance Criteria**:
- Postman collection or curl scripts provided.
- All endpoints can be tested manually.

---

## Epic 9: Documentation

### Issue 9.1: Write API documentation (README)
**Size**: 1 day  
**Depends on**: 3.5, 7.1, 7.2  
**Description**:
- README.md: project overview, setup instructions, quick start.
- API.md: all endpoints, request/response examples.
- DEVELOPMENT.md: how to run locally, run tests, debug.
- Sections:
  - Overview & architecture.
  - Hardware requirements.
  - Installation (Docker).
  - Configuration (config.yaml, .env).
  - Running the Gateway.
  - API usage (examples).
  - Testing.
  - Troubleshooting.

**Acceptance Criteria**:
- README is clear and complete.
- New users can follow setup instructions.
- Examples are runnable.

---

### Issue 9.2: Generate OpenAPI docs (Swagger UI)
**Size**: 0.5 day  
**Depends on**: 3.1, 3.5  
**Description**:
- FastAPI auto-generates OpenAPI schema.
- Swagger UI available at `/docs`.
- ReDoc available at `/redoc`.
- All endpoints and schemas documented.

**Acceptance Criteria**:
- Swagger UI is accessible.
- All endpoints are documented.
- Schemas are correct.

---

## Epic 10: Security Hardening & Release

### Issue 10.1: Security review & fixing
**Size**: 1 day  
**Depends on**: All previous issues  
**Description**:
- Code review for security issues:
  - JWT secret generation & storage.
  - Password validation strength.
  - SQL injection prevention (ORM should handle).
  - XSS in error messages (N/A for API).
  - CORS policy (allow all for Phase 3, tighten in Phase 4).
- Fix any issues found.
- Add security comments in code.

**Acceptance Criteria**:
- No obvious security vulnerabilities.
- Security decisions are documented.

---

### Issue 10.2: Performance testing & optimization
**Size**: 1 day  
**Depends on**: 3.5, 5.1  
**Description**:
- Load test: 10–100 concurrent requests.
- Measure: response time, queue wait time, Ollama load.
- Optimize if needed: caching, connection pooling, etc.
- Document results in PERFORMANCE.md.

**Acceptance Criteria**:
- Can handle 10+ concurrent requests.
- Response times are acceptable (< 2 sec for simple prompts).
- Queue behavior is predictable.

---

### Issue 10.3: Final manual testing & sign-off
**Size**: 1 day  
**Depends on**: All previous issues  
**Description**:
- QA checklist:
  - Create account → login → chat → get response.
  - RED data is blocked → user approves → succeeds.
  - YELLOW data is flagged → user approves → succeeds.
  - Audit logs capture all actions.
  - Errors are handled gracefully.
  - Docker Compose works end-to-end.
  - Documentation is complete.
- Sign-off: all criteria met, ready to merge to main branch.

**Acceptance Criteria**:
- All QA checklist items pass.
- No known bugs or TODOs.
- Ready for Phase 4 (Web UI).

---

## Summary Table

| Epic | Issues | Est. Days | Owner |
|------|--------|-----------|-------|
| Setup | 1.1–1.4 | 4 | Backend |
| Auth | 2.1–2.7 | 5 | Backend |
| Chat | 3.1–3.7 | 8 | Backend |
| Audit | 4.1–4.4 | 4 | Backend |
| Errors | 5.1–5.3 | 2 | Backend |
| MCP | 6.1–6.3 | 3 | Backend |
| Docker | 7.1–7.4 | 2 | DevOps |
| Testing | 8.1–8.5 | 5 | QA / Backend |
| Docs | 9.1–9.2 | 2 | Tech Writer |
| Security | 10.1–10.3 | 3 | Security / Backend |
| **Total** | **43 issues** | **~40–50 days** | |

---

## Success Criteria (Phase 3 Complete)

All the following are true:

1. ✅ FastAPI Gateway runs in Docker and responds to requests.
2. ✅ User can create account via `/admin/setup/user`.
3. ✅ User can log in and receive JWT token.
4. ✅ Authenticated user can POST to `/chat` and receive model response from Ollama.
5. ✅ RED-data requests are classified and blocked (403).
6. ✅ YELLOW-data requests are flagged and require approval (202).
7. ✅ Approval workflow (`/chat/approve`) works end-to-end.
8. ✅ Audit logs capture all actions (login, chat, approval, error).
9. ✅ Ollama unavailability triggers retries and returns 503.
10. ✅ Request queue serializes inference (single-at-a-time).
11. ✅ Error responses are consistent and informative.
12. ✅ OpenAPI/Swagger UI is available at `/docs`.
13. ✅ All unit + integration tests pass (>85% coverage).
14. ✅ Manual test suite (Postman/curl) covers all endpoints.
15. ✅ Documentation (README, API, DEVELOPMENT) is complete.
16. ✅ Docker Compose starts both Ollama and Gateway.
17. ✅ Security review passed (no critical issues).
18. ✅ Performance testing confirms acceptable latency.

---

## See Also

- [PHASE-3-SPECIFICATION.md](PHASE-3-SPECIFICATION.md) — Full specification.
- [CONTEXT.md](../CONTEXT.md) — Domain model.
- [docs/adr/](../docs/adr/) — Architecture Decision Records.
