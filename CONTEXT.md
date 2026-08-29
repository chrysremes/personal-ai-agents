# Context: Personal AI Agent Platform

## Overview

A **private, local-first family AI agent platform** combining local Qwen models via Ollama, Claude Code for cloud tasks, and an MCP abstraction layer. The platform is built for two users (user and wife) on a Linux host with a Windows web-client architecture.

---

## Key Terms (Glossary)

### Agent Gateway
The central FastAPI service (Phase 3) that:
- Authenticates requests (username/password → JWT tokens)
- Routes user prompts to appropriate models (local Qwen or Claude Code)
- Enforces single-model-at-a-time inference via a request queue
- Classifies data and enforces RED-data local-only rules
- Logs all actions for audit trails
- Exposes MCP tools as REST endpoints
- Manages session lifecycle and permissions

Also called: "the Gateway."

### Agent
An autonomous or semi-autonomous component that accomplishes a specific goal (e.g., News Aggregator, Finance Analyzer, Calendar Manager). Agents call the Gateway to request model inference, MCP tools, or other services.

Phases 5+ define specific agents. Phase 3 builds the Gateway that agents will use.

### Model Tier
A quantization/size class of the Qwen model selected for a specific use case:

- **Default tier (`qwen3.5:2b`)**: Everyday interactive chat, ~11.5 tok/s on GPU, well above the ~10 tok/s interactivity threshold.
- **Heavier reasoning (`qwen3.5:4b`)**: Tax documents, coding help, where extra latency is acceptable (~8.1 tok/s on GPU).
- **Batch-only (`qwen3.5:9b`)**: Non-interactive overnight jobs (e.g., News summarization), too slow for real-time (~3.6 tok/s on GPU, exposed to thermal throttling).

Determined in Phase 2; selection is final for Phase 3+.

### Request Queue / Single-Inference Lock
The Gateway enforces **at most one Qwen model inference at a time**, preventing resource contention on the 2-core/4-thread CPU and 4 GB VRAM. Implemented as an in-memory async semaphore (Phase 3). Protects against:
- Overlapping model loads exhausting VRAM
- CPU context-switching overhead from simultaneous inference
- Thermal throttling under concurrent high-load

Also called: "concurrency lock," "inference queue."

### Data Classification
A three-tier labeling system for all data flowing through the platform:

- **GREEN**: Cloud-safe (public news, public docs, generic programming questions, public marketing concepts). May be sent to Claude Code.
- **YELLOW**: Requires explicit user approval before cloud transmission (private source code, unpublished marketing, internal documents).
- **RED**: Local-only, never sent to cloud (CPF, bank statements, financial transactions, IRPF docs, tax records, PII, Gov.br/bank credentials, sensitive medical data).

The Gateway infers classification from content (regex patterns, keywords) and enforces it via routing decisions.

### Audit Log
A structured JSON log (stored in SQLite) of every action taken by the platform:
```json
{
  "timestamp": "2026-08-29T14:32:45Z",
  "user": "wife",
  "agent": "news-aggregator",
  "action": "request_inference",
  "model": "qwen3.5:2b",
  "data_class": "GREEN",
  "approval_required": false,
  "approval_status": "auto_approved",
  "result": "success",
  "tokens_used": {"input": 50, "output": 120},
  "error": null
}
```

Includes built-in redaction of RED patterns before logging. Retained for 90 days, archived monthly.

### MCP (Model Context Protocol)
The tool/integration abstraction. The Gateway consumes MCP tool definitions and exposes them via REST endpoints (`/tools/<tool_name>`). Agents call REST, not MCP directly, simplifying audit logging and security.

### Session / JWT Token
**Session**: A user's authenticated connection state.

**JWT Token** (short-lived): Signed, stateless token containing user ID and permissions, TTL 15 minutes. Verified cryptographically on each request (no database lookup).

**Refresh Token** (longer-lived): Opaque token stored in SQLite, TTL 7 days. Allows user to obtain a new JWT without re-entering password.

### Approval Workflow
When a request is flagged as requiring approval (RED data, sensitive action):
1. Gateway returns status `approval_required: true` with the request.
2. Web UI renders an approval dialog.
3. User approves or denies.
4. Web UI re-submits the request (if approved).
5. Gateway processes the re-submission.

The Gateway itself does not hold or orchestrate approval — it only flags and rejects unapproved requests.

### Provider
A pluggable model backend. Currently supported:

- **Ollama Provider**: Calls Ollama's HTTP API to invoke local Qwen models.
- **Claude Code Provider**: Calls Anthropic's API (configured in Phase 3, used in Phase 9).

Providers are abstract; the Gateway doesn't know or care which model backend is serving a request (once routing is decided, the provider handles the rest).

---

## Decisions (To Be Expanded as ADRs)

- **Architecture**: Central Linux host (Acer Aspire) runs the Gateway; wife's Windows laptop is web-client-only.
- **Authentication**: Stateless JWT-based (short-lived token + refresh token), stored in SQLite, Argon2 password hashing.
- **Concurrency**: Single-inference-at-a-time, enforced by Gateway-level request queue (not Ollama's defaults).
- **Data Classification**: Automatic inference via regex patterns; RED data never sent to cloud (hard technical enforcement).
- **Logging**: Structured JSON to SQLite, with RED-pattern redaction before storage.
- **Session TTL**: 15 min (JWT) + 7 days (refresh token).
- **Model Routing**: Agent declares preference, Gateway applies classification rules, User can override if approved.
- **MCP Usage**: Gateway consumes MCP, exposes REST endpoints; agents call REST, not MCP directly.
- **Approval**: Gateway flags; Web UI orchest rates; user approves/denies.
- **Error Handling**: Retry on timeout + connection errors (3x, exponential backoff); fail immediately on out-of-memory or invalid request.
- **Containerization**: Docker (Gateway, later Web UI, agents) + Docker Compose orchestration.
- **Configuration**: YAML config file + `.env` for secrets.
- **First-Login Setup**: Special `/admin/setup/user` endpoint (one-time, active only if user table empty).

---

## Phase Timeline (Current)

- **Phase 1** ✅ (Linux host preparation)
- **Phase 2** ✅ (Ollama + Qwen benchmark)
- **Phase 3** 🔄 (Agent Gateway + Authentication) — **IN PROGRESS**
- **Phase 4** (Web UI)
- **Phase 5** (News Aggregator)
- **Phase 6** (Google Calendar)
- **Phase 7** (Marketing / Instagram)
- **Phase 8** (Finance / Tax)
- **Phase 9** (Coding)
- **Phase 10** (Security Hardening)

---

## See Also

- [AGENTS.md](AGENTS.md) — Agent skills and coordination strategy.
- [docs/agents/](docs/agents/) — Triage labels, issue tracker, domain structure.
- [docs/adr/](docs/adr/) — Architectural Decision Records (ADRs) for hard-to-reverse choices.
- [Plan/personal-ai-agent-platform-plan-v5b.md](Plan/personal-ai-agent-platform-plan-v5b.md) — Full project plan with hardware specs, objectives, phases.
