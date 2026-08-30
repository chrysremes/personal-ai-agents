# Phase 3 Implementation Review — Follow-up Gaps

**Reviewed:** 2026-08-30  
**Sources:** `PHASE-3-SPECIFICATION.md` and `PHASE-3-IMPLEMENTATION-ISSUES.md`  
**Scope:** Current `gateway/` implementation (read-only review; no functional code changed).

## Conclusion

Phase 3 has a substantial scaffold and its current automated suite passes (28 tests), but it does **not** yet meet the Phase 3 completion criteria. The gaps below are confirmed from the route registration and implementation source.

## Priority 1 — Complete before Phase 3 sign-off

### P1-1: Approval cannot execute an approved request

- **Requirement:** An approved request must be re-submitted and return the model response; pending entries must expire after five minutes. See specification lines 443–447 and implementation issue 3.6, lines 351–367.
- **Evidence:** `gateway/routes_chat.py:375-387` removes the cached request and returns “Please resubmit to process”; it never calls a provider. The cache stores no timestamp and has no expiry handling (`gateway/routes_chat.py:43-44`, `127-132`, `166-172`).
- **Impact:** Both the YELLOW approval success criterion and the documented RED approval flow cannot succeed. A user must manually send another request, which is then classified again and requires approval again.
- **Follow-up:** Store the pending request with owner and expiry, validate ownership, and perform the approved inference through the same queue/provider/audit path. Return 410 for expired entries.

### P1-2: Logout is a non-functional placeholder

- **Requirement:** `POST /auth/logout` requires bearer authentication, revokes the associated refresh token, and records an audit event. See specification lines 282–296 and implementation issue 2.5.
- **Evidence:** `gateway/routes_auth.py:255-275` has no `get_current_user` dependency, does not read a refresh token, does not update `RefreshToken.revoked_at`, and does not write an audit log.
- **Impact:** A logout response reports success while existing refresh tokens remain usable until expiry.
- **Follow-up:** Define how the logout request identifies the refresh token, require the JWT dependency, revoke only the requesting user's token(s), and test that a later refresh returns 401.

### P1-3: YELLOW data can bypass the cloud-approval check

- **Requirement:** YELLOW data requires approval before it is sent to a cloud model. See specification lines 402–411 and implementation issue 3.5, lines 325–335.
- **Evidence:** The approval guard accepts only the exact value `"claude-code"` (`gateway/routes_chat.py:148-186`), while provider selection treats every model name containing `"claude"` as cloud (`gateway/routes_chat.py:188-190`). For example, `model_preference="claude-opus"` bypasses approval and selects `ClaudeProvider`.
- **Impact:** Private YELLOW data can be routed to a cloud provider without the required user approval.
- **Follow-up:** Resolve models through an allowlisted `ModelConfig` record before classification policy is applied; classify provider type from that record, not a substring.

### P1-4: MCP tool API is entirely absent

- **Requirement:** Provide a registry plus authenticated `GET /tools` and `POST /tools/{tool_name}` endpoints with validation and audit logging. See specification lines 451–510 and implementation issues 6.1–6.3, lines 516–566.
- **Evidence:** `gateway/main.py:103-106` registers only auth, chat, and audit routers; no MCP registry or tool route exists. `gateway/IMPLEMENTATION_SUMMARY.md:185-190` also lists all related work as incomplete.
- **Impact:** One of the gateway's stated Phase 3 responsibilities and both tool endpoints are unavailable.
- **Follow-up:** Implement a minimal in-process registry with stub tools, schema validation, authentication, and audit records.

### P1-5: Required RED classification coverage is incomplete

- **Requirement:** Detect unformatted CPF, Portuguese bank and transaction terms, CNPJ, RG, and specified credential contexts as RED. See specification lines 618–628.
- **Evidence:** `gateway/config.yaml:8-26` includes only formatted CPF and a small English-keyword set; it has no unformatted CPF, CNPJ, RG, `agência`, `conta corrente`, `transferência`, `débito`, `crédito`, `extrato`, or `saldo` patterns. `gateway/classifier.py:61-75` can only classify configured patterns.
- **Impact:** Some financial and identity data designated RED can be classified GREEN or YELLOW and therefore be eligible for cloud routing.
- **Follow-up:** Add the missing named patterns (with word boundaries/context where needed), retain human-readable pattern names, and add regression tests for each required category.

### P1-6: Audit redaction does not reuse the classifier's RED rules

- **Requirement:** Redact all RED matches in errors using the same classifier patterns. See specification lines 140–143 and implementation issue 4.2, lines 409–421.
- **Evidence:** `gateway/audit.py:113-128` declares the full redaction TODO and applies only three independent regexes. `gateway/logging_config.py:196-200` returns the unredacted error value before it is passed to the database task.
- **Impact:** RED data not covered by the three ad hoc expressions may be retained in the SQLite audit trail or stdout audit entry.
- **Follow-up:** Create one shared redaction utility driven by the configured RED pattern set; apply it before both structured-log and database writes; test CPF, bank terms, and non-RED text.

## Priority 2 — Required API/configuration completeness

### P2-1: `/status` and the specified health payload are missing

- **Requirement:** Expose `GET /status` and report database/Ollama/queue state from `GET /health`. See specification lines 514–541.
- **Evidence:** `gateway/main.py:112-116` returns only `{"status": "ok"}`; no `/status` route is registered.
- **Impact:** Clients cannot obtain the required operational status, and a healthy HTTP process can be reported even when dependencies are unavailable.
- **Follow-up:** Add dependency checks and queue depth to `/health`; add `/status` with version, phase, uptime, available models, active sessions, and queue depth.

### P2-2: The setup-user endpoint is exposed at the wrong URL

- **Requirement:** The one-time public setup endpoint is `POST /admin/setup/user`. See specification lines 300–330 and implementation issue 2.7.
- **Evidence:** The setup handler is declared at `/admin/setup/user` but sits in an `APIRouter(prefix="/auth")` (`gateway/routes_auth.py:30-31`, `285-289`), so its actual path is `/auth/admin/setup/user`.
- **Impact:** A client built to the specified public API receives 404. The README documents the implementation path rather than the contract path.
- **Follow-up:** Move the handler to a router without the `/auth` prefix, or adjust the router layout so the exposed route is exactly `/admin/setup/user`.

### P2-3: YAML configuration is not merged for most documented settings

- **Requirement:** Load `config.yaml`, merge it with environment variables (environment wins), and validate required settings. See implementation issue 1.3 and specification lines 670–709.
- **Evidence:** `gateway/config.py:75-89` reads only classification patterns and model tier timeouts from YAML. The YAML `server`, `database`, `auth`, `ollama`, and `audit_logging` values are otherwise ignored; `Settings` defaults/environment determine those values instead.
- **Impact:** Editing the documented YAML configuration does not configure the server, database, auth TTLs, Ollama behavior, or audit retention as users are led to expect.
- **Follow-up:** Define a typed YAML model, merge it before environment settings, and add tests proving YAML values load and environment values override them.

### P2-4: Audit events can be lost for a single request

- **Requirement:** Audit logs must contain the relevant chat and approval actions. See specification lines 411 and 443–447; implementation issues 4.1–4.2, lines 391–421.
- **Evidence:** `AuditLog.request_id` is unique (`gateway/models.py:49-63`), but a pending YELLOW/RED chat and its later approval both use the same ID (`gateway/routes_chat.py:155-164`, `377-395`). The database writer suppresses commit errors (`gateway/audit.py:87-101`), and the caller schedules writes without awaiting them (`gateway/logging_config.py:168-194`).
- **Impact:** The subsequent audit event fails the unique constraint and disappears silently, so the audit trail does not reliably evidence approval decisions.
- **Follow-up:** Model the original request and its events separately (unique event ID plus a non-unique request correlation ID), and surface/report failed audit writes rather than discarding them silently.

### P2-5: Audit log total is not the requested total

- **Requirement:** `GET /audit/logs` returns paginated results and the total matching records. See specification lines 548–581 and implementation issue 4.4, lines 442–456.
- **Evidence:** `gateway/routes_audit.py:73-76` sets `total=len(log_entries)` after applying the limit, with an explicit TODO.
- **Impact:** Clients cannot distinguish a complete result set from a truncated page.
- **Follow-up:** Execute a matching `COUNT(*)` query before applying the result limit and add pagination tests.

## Priority 3 — Verification and delivery gaps

### P3-1: Required test coverage has not been delivered

- **Requirement:** 30+ authentication tests, 20+ classification tests, 10+ audit tests, and 10+ Gateway-to-Ollama integration scenarios. See implementation issues 8.1–8.4, lines 637–700; the specification also requires all unit and integration tests to pass (lines 777–797, 847).
- **Evidence:** The present suite contains 28 tests total (`gateway/tests/test_core.py`, `gateway/tests/test_resilience.py`); `gateway/DEVELOPMENT.md:174-176` explicitly marks integration tests TODO. There are no endpoint-flow, audit-redaction, approval-flow, or live/mock Gateway-to-Ollama integration tests.
- **Impact:** Passing tests do not demonstrate the required user flows or the safety controls above.
- **Follow-up:** Add isolated endpoint/integration tests and an explicit coverage report, then re-run the Phase 3 acceptance matrix.

### P3-2: Password policy is weaker than the stated implementation requirement

- **Requirement:** Require at least eight characters and a mix of upper-case, lower-case, digits, and symbols. See implementation issue 2.1.
- **Evidence:** `gateway/auth.py:81-96` checks only the minimum length, and request schemas enforce only `min_length=8` (`gateway/schemas.py:14-16`, `37-39`).
- **Impact:** Weak passwords accepted during initial setup do not satisfy the security acceptance criteria.
- **Follow-up:** Enforce the specified character classes in the password manager and add positive/negative setup tests.

### P3-3: Audit archival/retention is not implemented

- **Requirement:** Archive audit logs older than 90 days to timestamped compressed files. See implementation issue 4.3, lines 425–438.
- **Evidence:** `gateway/IMPLEMENTATION_SUMMARY.md:160-163` says archival is not implemented; no archival command or scheduled task exists under `gateway/`.
- **Impact:** The configured audit trail grows indefinitely and does not meet the retention/archival deliverable.
- **Follow-up:** Implement a documented archive command/job with a retention setting and extraction test.

## Verification performed

- Current suite: `docker run --rm --env GATEWAY_ENV=test --env GATEWAY_JWT_SECRET=phase3-test-secret-at-least-32-chars agent-gateway-phase3-test python -m pytest -q`
- Result: **28 passed** (with four dependency deprecation/namespace warnings).
- No source files were modified as part of the review; this document is the only review output.
