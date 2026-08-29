# ADR-0001: Stateless JWT-Based Authentication

**Status**: Accepted (2026-08-29)  
**Phase**: 3 (Agent Gateway + Authentication)

---

## Context

The Agent Gateway must authenticate requests from the Web UI and agents. Two fundamental approaches exist:

1. **Stateless (JWT)**: Signed tokens contain claims (user ID, permissions); Gateway verifies signature without database lookup. Tokens are short-lived (15 min), backed by a database refresh-token store for extended sessions.

2. **Stateful (Opaque tokens)**: Random tokens stored in a session table; Gateway looks up permissions on each request. Simpler per-request logic, but requires database round-trip for every auth check.

Additionally, password storage must resist brute-force attacks. Options: bcrypt, Argon2, or simple salted SHA256.

---

## Decision

**Use stateless JWT-based authentication with Argon2 password hashing.**

Specifically:
- **Short-lived JWT** (15 minutes TTL, RS256 signature): Contains user ID, permission claim, issued-at + expiry.
- **Refresh token** (7-day TTL): Opaque random string stored in SQLite `refresh_tokens` table, linked to user.
- **Password storage**: Argon2 (via `argon2-cffi`), replaces plaintext in `users` table.
- **Session flow**:
  1. User logs in with username + password.
  2. Gateway validates password (Argon2 comparison), generates JWT + refresh token.
  3. Client sends JWT with each request in `Authorization: Bearer <jwt>`.
  4. Gateway verifies JWT signature (no database lookup).
  5. When JWT expires, client sends refresh token to `/auth/refresh` endpoint.
  6. Gateway validates refresh token (one DB lookup), issues new JWT.

---

## Rationale

### Why stateless JWT over stateful sessions?

**Stateless advantages:**
- **No per-request database lookup** for auth validation. On the 2-core i7, this reduces CPU overhead.
- **Crash resilience**: Sessions survive Gateway restart (tokens are self-contained). Users don't get logged out if the service bounces.
- **Horizontal scaling ready**: If Phase 10 scales to multiple instances, JWTs don't require shared session state.
- **Simpler architecture**: No session garbage collection, no session-store synchronization.

**Stateless disadvantages:**
- Can't revoke a token instantly (must wait for TTL expiry). Mitigated by short TTL (15 min).
- Token leaks on unsecured transport. Mitigated by TLS (future Phase 10 hardening).

### Why Argon2 over bcrypt?

**Argon2 advantages:**
- **Memory-hard algorithm**: Resists bulk brute-force attacks even with high computational resources (GPU clusters). Bcrypt is only CPU-hard.
- **Proven modern best practice**: Recommended by OWASP and cryptography experts as of 2024.
- **Parallelism tuning**: Can adjust memory + iteration cost independently.

**Bcrypt is acceptable** (widely used, battle-tested), but Argon2 offers better future-proofing against advances in attack hardware.

---

## Consequences

### Positive
- Lightweight authentication on every request (JWT verification is ~1ms cryptographic operation, no DB).
- Stateless Gateway simplifies deployment and testing.
- Refresh-token pattern balances security (short JWT TTL) with UX (user doesn't re-type password frequently).
- Argon2 provides strong resistance to brute-force credential attacks.

### Negative
- **Token revocation latency**: If a user is compromised, the token can be misused for up to 15 minutes. Acceptable for home deployment; add token revocation list (blacklist) in Phase 10 if needed.
- **Token leakage in logs**: Must ensure JWT is never logged (audit log redacts it).
- **Client must manage tokens**: Web UI must store JWT in memory (not localStorage to avoid XSS), send it with each request.

---

## Implementation Notes

- Use `PyJWT` library for token generation/verification.
- Use `argon2-cffi` for password hashing.
- Store JWT secret key in environment variable `GATEWAY_JWT_SECRET` (Phase 3) or encrypted secret manager (Phase 10).
- Verify JWT signature on every request at the Gateway layer (before routing to handler).
- Document in API: "All endpoints except `/auth/login`, `/auth/refresh`, `/admin/setup/user` require Bearer token."

---

## Alternatives Considered

1. **OAuth2 with external provider** (e.g., Google): Overkill for 2-user home platform; adds external dependency.
2. **mTLS (mutual TLS)**: Certificate-based auth; complex for client setup, not necessary.
3. **Simple API keys**: Stateless like JWT but less standard; harder to audit permission claims.

---

## See Also

- [CONTEXT.md](../../CONTEXT.md) — Session / JWT Token definition.
- [Phase 3 Specification](../../Plan/personal-ai-agent-platform-plan-v5b.md#phase-3) — Full Phase 3 requirements.
