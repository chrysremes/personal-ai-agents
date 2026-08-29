# ADR-0003: Hard Enforcement of RED-Data Local-Only Rule

**Status**: Accepted (2026-08-29)  
**Phase**: 3 (Agent Gateway + Authentication)

---

## Context

The platform processes three classes of data:

- **GREEN**: Cloud-safe (public content, generic questions).
- **YELLOW**: Requires explicit user approval before cloud transmission (private code, unpublished marketing).
- **RED**: Personal, financial, tax, and government data that must never leave the local host (CPF, bank statements, financial transactions, IRPF docs, Gov.br/bank credentials, sensitive PII).

**RED data classification is not optional for this project.** The user's objective is to keep financial and tax data local and under control, with no automated transmission to cloud APIs (even to trusted providers like Anthropic). Section 9 of the plan explicitly states this is a hard rule, reflecting advice from the Receita Federal ("we never ask for passwords").

**Two implementation approaches:**
1. **Policy/recommendation**: Document that RED data should not go to cloud; rely on user discipline.
2. **Technical enforcement**: Gateway automatically blocks RED-data requests to cloud models; failure mode is explicit rejection (not silent fallback).

---

## Decision

**Implement hard technical enforcement of RED-data local-only rule at the Gateway layer.**

Specifically:
- Gateway infers data classification via regex pattern matching on the prompt text (e.g., detect CPF patterns, bank keywords, IRPF references).
- **If data is classified RED**:
  - **Gateway rejects the request with status `approval_required: true` + `cloud_model_blocked: true`.**
  - Explains to user: "This data appears to contain sensitive financial/tax information and cannot be sent to cloud models. Local processing only. Approve?"
  - **Only local models (Qwen via Ollama) are allowed; no fallback to Claude Code.**
- **If data is classified YELLOW**:
  - **Gateway rejects the request with status `approval_required: true`.**
  - Explains: "This data appears sensitive. Approve sending to Claude Code?"
  - User must explicitly approve to proceed.
- **If data is classified GREEN**:
  - **No approval required; can route to either local or cloud model per agent/user preference.**

**Audit logging must record:**
- Data classification result (GREEN/YELLOW/RED).
- Which patterns triggered RED or YELLOW classification (for audit trail).
- Whether approval was requested/granted.
- Which model actually served the request.

---

## Rationale

### Why technical enforcement, not policy?

**Technical enforcement advantages:**
- **Accident prevention**: User forgets to manually check, prompt accidentally includes a CPF, gateway blocks it. Better than silent failure.
- **Audit trail**: Log explicitly shows which requests were blocked and why. Useful for later forensics ("did RED data leak?").
- **No escalation**: Gateway never auto-escalates RED data to cloud as a fallback. Failure is explicit; user must re-phrase or approve local-only processing.
- **Matches the platform's core ethos**: The entire architecture is designed to keep sensitive data local. Enforcement mirrors that intent.

**Policy/recommendation disadvantages:**
- No guarantee of compliance (users make mistakes under time pressure).
- No audit trail of near-misses (requests that were close to violating but user happened to notice).
- Maintenance burden: Agent developers and users must remember the rules and follow them consistently.

### Why regex pattern matching for classification?

**Why not ML-based classification?**
- Regex is fast (sub-millisecond), deterministic, auditable.
- ML classifier would require inference (slow, consumes model resources).
- Regex patterns can be reviewed and audited; ML confidence scores are opaque.
- Conservative false-positives (over-blocking) is safer than false-negatives (leaking RED data).

**Why not manual user tagging?**
- Users forget or under-estimate sensitivity of their own data.
- Regex + user tagging hybrid: Regex blocks obvious RED patterns; user can downgrade YELLOW to GREEN if they're certain it's safe. Better than either alone.

### Why reject, not sanitize?

**Why reject instead of removing sensitive fields?**
- Attempting to auto-sanitize (e.g., remove numbers that look like CPF) could silently corrupt user queries ("I want to sum columns A and B").
- Better to reject and let user re-phrase than to silently alter their request.
- User explicitly approves local-only processing, so the request succeeds but is guaranteed to stay local.

---

## Consequences

### Positive
- **RED data never reaches cloud APIs** (strong guarantee for the user's peace of mind).
- **Audit trail is unambiguous**: Can review logs and confirm RED data was never sent to cloud.
- **User can't accidentally shoot themselves in the foot**: Gateway stops them before mistake happens.
- **Matches regulatory intent**: Brazilian financial/tax data handling has informal "keep it local" expectations; this enforces that.

### Negative
- **False positives possible**: Regex may misclassify some GREEN data as RED (e.g., user mentions a CPF in a public news article they're discussing). Mitigated by user being able to downgrade after seeing the error message.
- **User friction**: User may see "approval required" more often than they expect if the regex is conservative. Mitigated by tuning patterns (start conservative, relax based on real usage).
- **Doesn't prevent accidental RED-data leaks via MCP tools**: If an MCP tool silently uploads data to the internet, the Gateway can't prevent it. Mitigated by strict MCP tool review (Phase 5+) and audit logging of which tools are called and with what arguments.
- **Doesn't cover side-channel leaks**: Logging, error messages, or future features (e.g., user profile enrichment) could leak RED data if not carefully reviewed. Mitigated by ongoing security hardening (Phase 10).

---

## Implementation Notes

### Regex Patterns (Initial Set)

Red-flag patterns for RED classification:
- **CPF**: `\d{3}\.\d{3}\.\d{3}-\d{2}` (formatted) or `\d{11}` (unformatted).
- **Bank account**: `\bagência\b`, `\bconta\b`, `\bdigito\b` (Portuguese banking keywords).
- **IRPF/Tax**: `\bIRPF\b`, `\binforme de rendimentos\b`, `\breceitanet\b`, `\bGov\.br\b`.
- **Financial transactions**: `\btransferência\b`, `\bdébito\b`, `\bcrédito\b`, `\bextrato\b`, `\bconta corrente\b`.
- **Credential indicators**: `\bsenha\b`, `\bpincode\b`, `\btoken\b` (in context of "my X is...").
- **PII**: `\bCNPJ\b`, `\bRG\b`, `\bCE\b` (Registry keywords).

Yellow-flag patterns for YELLOW classification:
- **Private code indicators**: `\brepositório privado\b`, `\bsource code\b`, `\binternal\b`.
- **Private business**: `\bconfidencial\b`, `\bonly for internal use\b`.

### Gateway Implementation

In `gateway/classifier.py`:
```python
def classify_data(prompt: str) -> Classification:
    """
    Returns ('RED', patterns_matched), ('YELLOW', patterns_matched), or ('GREEN', []).
    Patterns_matched is a list of strings like ['CPF', 'Bank Account Keywords'].
    """
    red_matches = [...]
    yellow_matches = [...]
    
    if red_matches:
        return Classification(level='RED', patterns=red_matches)
    if yellow_matches:
        return Classification(level='YELLOW', patterns=yellow_matches)
    return Classification(level='GREEN', patterns=[])
```

In request handler:
```python
@app.post("/chat")
async def chat(request: ChatRequest):
    classification = classify_data(request.prompt)
    
    if classification.level == 'RED':
        # Reject RED data
        return {
            'id': request_id,
            'approval_required': True,
            'cloud_model_blocked': True,
            'message': f"Sensitive data detected ({', '.join(classification.patterns)}). "
                       "Local processing only. Approve?",
            'allowed_models': ['qwen3.5:2b', 'qwen3.5:4b', 'qwen3.5:9b']
        }
    
    elif classification.level == 'YELLOW':
        # Ask for approval for cloud transmission
        if not request.approval_granted:
            return {
                'id': request_id,
                'approval_required': True,
                'message': f"Private/sensitive data detected ({', '.join(classification.patterns)}). "
                           "Approve sending to Claude Code?",
                'allowed_models': ['qwen3.5:2b', 'qwen3.5:4b'] + (
                    ['claude-code'] if request.approval_granted else []
                )
            }
    
    # GREEN or approved YELLOW/RED: process normally
    ...
```

### Audit Logging

Every request log includes:
```json
{
  "timestamp": "...",
  "user": "...",
  "prompt_length": 120,
  "data_class": "RED",
  "data_class_patterns": ["CPF", "Bank Account Keywords"],
  "approval_required": true,
  "approval_status": "pending",
  "requested_model": "claude-code",
  "result": "blocked_red_data",
  "error": "RED data cannot be sent to cloud models"
}
```

---

## Tuning & Monitoring

**Initial tuning (Phase 3):**
- Start with conservative regex (over-block a bit to be safe).
- Test with sample prompts from Phase 5+ agents to see false-positive rate.

**Monitoring (Phase 3+):**
- Track how often each RED/YELLOW pattern is triggered.
- Categorize requests by "auto-approved", "user-approved", "user-rejected".
- If a pattern triggers >50% false positives (users downgrade after seeing error), relax or remove it.

---

## Alternatives Considered

1. **ML classifier (LLM-based)**: Overkill, slow, opaque, hard to audit.
2. **Manual user tagging**: User forgets; no audit trail.
3. **Policy only** (no enforcement): Easy to bypass accidentally.
4. **Auto-sanitization**: Risk of silently corrupting user intent.

---

## See Also

- Section 8 ([CONTEXT.md](../../CONTEXT.md)) — Data Classification (GREEN/YELLOW/RED).
- Section 8 of [Plan/personal-ai-agent-platform-plan-v5b.md](../../Plan/personal-ai-agent-platform-plan-v5b.md) — Data Classification (full definition).
- Section 9 (Brazilian Banking and Gov.br Decision) — Rationale for hard local-only rule.
