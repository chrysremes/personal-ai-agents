# ADR-0004: Host Ollama Runtime for Phase 3

**Status**: Accepted (2026-08-30)
**Phase**: 3 (Agent Gateway + Authentication)

---

## Context

Phase 2 established the host `ollama.service` as the tuned local inference
runtime, including the machine-specific Vulkan backend configuration and local
Qwen model store. The original Phase 3 Compose file tried to start a second
Ollama runtime in Docker and publish host port `11434`, which conflicts with
the active host service and blocks the Gateway startup path.

## Decision

Use the host `ollama.service` as the single Ollama runtime for Phase 3. Docker
Compose starts the Agent Gateway container only, with host networking enabled,
and the Gateway calls Ollama at `http://127.0.0.1:11434`.

## Consequences

The default Phase 3 deployment keeps the known-good Phase 2 Vulkan setup and
avoids competing ownership of port `11434`. Containerized Ollama remains a
future option, but it needs a separate deployment decision that reproduces model
storage, device access, backend verification, and resource limits inside Docker.
