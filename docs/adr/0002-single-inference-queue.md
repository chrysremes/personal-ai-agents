# ADR-0002: Single-Inference-at-a-Time Queue Enforcement

**Status**: Accepted (2026-08-29)  
**Phase**: 3 (Agent Gateway + Authentication)

---

## Context

The Linux host has **2 physical cores / 4 threads (i7-7500U)** and **4 GB VRAM (NVIDIA 940MX)**, shared between the OS, Docker, the Agent Gateway, Ollama, and (later) agents.

**Phase 2 benchmarking found that overlapping model instances during the same 5-minute period caused:**
- System RAM climbed to ~10 GiB of 14 GiB (with 1.3 GiB swap engaged).
- GPU clock throttling (653 MHz / 76% of max) despite moderate temperature (74–75°C).

The root cause: Ollama's default `OLLAMA_KEEP_ALIVE` (5 minutes) allows multiple quantized models to remain resident simultaneously, competing for VRAM and CPU cycles. This was an accident during Phase 2 benchmarking; in production with multiple agents, overlap can happen routinely.

**Options:**
1. **Trust Ollama's defaults** (`OLLAMA_KEEP_ALIVE` + `OLLAMA_MAX_LOADED_MODELS`): No explicit Gateway-level enforcement.
2. **Request queue at Gateway**: Serialize all model calls through a single lock; only one inference runs at a time.
3. **Hybrid**: Relax the queue for non-interactive/batch jobs, serialize interactive requests.

---

## Decision

**Implement a request queue at the Gateway level, enforcing single-inference-at-a-time globally.**

Specifically:
- Gateway maintains an in-memory `asyncio.Semaphore(1)` that gates all calls to `ollama.generate()`.
- Before calling Ollama, handlers acquire the semaphore (`async with queue_semaphore: ...`).
- If multiple requests arrive, they are queued in the async runtime; only one proceeds at a time.
- Additionally, set `OLLAMA_MAX_LOADED_MODELS=1` via systemd override to prevent Ollama itself from holding multiple models.
- Timeout for individual requests: 120 sec (default tier), 180 sec (heavier reasoning), fail immediately if timeout exceeded.

---

## Rationale

### Why enforce at Gateway, not leave to Ollama?

**Gateway-level enforcement advantages:**
- **Explicit and auditable**: Audit log records which request held the lock and for how long.
- **Applies to all agents consistently**: Doesn't rely on agent authors remembering to serialize; the Gateway enforces it.
- **Survives Ollama restarts**: If Ollama is restarted (Phase 3+), the queue persists in the Gateway. Requests re-queue and re-submit.
- **Measurable queue depth**: Telemetry can track "how many requests were queued at peak usage" for future capacity planning.

**Ollama-level-only disadvantages:**
- Phase 2 showed relying on Ollama's defaults (`OLLAMA_KEEP_ALIVE`) is not safe — you can't predict when models will be unloaded.
- Future agents won't know to coordinate; dual enforcement (Ollama + agent-level) is fragile.

### Why single-at-a-time, not multiple-with-limits?

**Current decision (single-at-a-time):**
- Simple to reason about and audit.
- Safe on 2-core/4GB hardware.
- Sufficient for Phase 3–5 (News, Calendar, Marketing are light workloads).

**Future alternative (multiple with limits):**
- Revisit once Phase 3–5 are live and real usage data exists (see section 27a in the plan).
- If monitoring shows 80%+ idle time during concurrent requests, can relax to 2–3 concurrent inferences with explicit VRAM/CPU budget.
- Requires re-benchmarking (section 6b note on vector DB footprint, batching implications).

---

## Consequences

### Positive
- **Prevents VRAM exhaustion**: No accidental overlapping model loads.
- **Predictable performance**: Each request's resource footprint is isolated.
- **Audit trail**: Every queued request is logged with queue wait time.
- **No agent complexity**: Agents don't need to know about concurrency; Gateway handles it.

### Negative
- **Latency impact**: If user asks Question B while Question A is being answered (10-20 sec response time), Question B waits. For 2b model (~11.5 tok/s), a 100-token response is ~9 sec + overhead. Acceptable for family-scale usage.
- **Not optimal for bursty traffic**: If the wife and user both ask questions simultaneously, one will experience noticeable delay. Mitigated by batch-job scheduling (news summarization runs at night, not during peak interactive use).
- **Doesn't apply to vector DB / embeddings** (not yet built): Future Phase 8+ finance/tax agent may have separate resource contention if a vector DB is added. Must be re-benchmarked and potentially managed separately (see section 6b).

---

## Implementation Notes

- Use Python `asyncio.Semaphore(1)` (simple, built-in, no external dependencies).
- Place the semaphore in a shared module (e.g., `gateway/concurrency.py`) accessible to all model-calling handlers.
- Wrap Ollama calls:
  ```python
  async with inference_queue:
      response = await ollama_provider.generate(prompt, model)
  ```
- Log queue entry/exit for telemetry (request ID, wait time, duration).
- Don't retry if timeout is reached; fail fast and inform user ("Model request timed out, please try again").
- Document in API: "Model requests are serialized; expect delays if multiple requests arrive simultaneously."

---

## Monitoring & Future Adjustments

**Metrics to capture (Phase 3+):**
- Queue depth (how many requests waiting).
- Queue wait time (time from submission to acquisition of semaphore).
- Inference duration (time spent in Ollama.generate()).
- Peak concurrent request count (for capacity planning).

**Trigger for revisiting this decision:**
- If real usage shows <20% queue depth (i.e., queue rarely has backlog), relaxation to 2–3 parallel inferences is safe.
- If vector DB / embeddings is added (Phase 8+), re-benchmark with new component and adjust budget accordingly.

---

## Alternatives Considered

1. **No explicit queue** (rely on Ollama): Risky; Phase 2 showed accidents happen.
2. **Redis queue (Celery/RQ)**: Overkill for single-instance. Phase 3 uses in-memory queue; can migrate to Redis in Phase 10 if scaling.
3. **Per-agent concurrency limits**: Would require agents to know about each other, complexity increases. Gateway-level lock is simpler.

---

## See Also

- [CONTEXT.md](../../CONTEXT.md) — Request Queue / Single-Inference Lock definition.
- Section 6b of [Plan/personal-ai-agent-platform-plan-v5b.md](../../Plan/personal-ai-agent-platform-plan-v5b.md) — Concurrency & Resource Budget.
- Section 27a (Operational Concerns) — Monitoring strategy.
