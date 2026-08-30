# Personal AI Agent Platform — Deployment Plan

**Status:** Architecture and requirements baseline  
**Date:** 2026-08-09  
**Country:** Brazil  
**Primary host:** Acer Aspire F5-573G-75A3 running Ubuntu 26.04 LTS  
**Clients:** Primary Linux host + wife's Windows 11 laptop  
**Users:** Two authenticated users only — user and wife

---

# 1. Executive Summary

We are building a **private, local-first family AI agent platform**.

The Linux Acer laptop will host the agent platform and local AI. The wife's Windows laptop will access it through a simple web interface, so she does not need to install, configure, or understand the underlying AI stack.

The system will combine:

- Local Qwen models through Ollama.
- Claude Code for selected cloud-based coding tasks.
- MCP as the tool/integration abstraction.
- A local agent gateway responsible for routing, permissions, authentication, approvals, and audit logging.
- Local deterministic software for financial/document processing.
- Official APIs where useful for non-sensitive services such as Google Calendar and Instagram.
- **No direct AI authentication or automated login to banking or Gov.br services.**

The architecture is intentionally model-agnostic so that Qwen, Claude, Ollama, MCP components, or other technologies can be replaced later without redesigning the whole platform.

---

# 2. Objectives

The platform should support:

- Google Calendar scheduling and management.
- Instagram marketing content generation and publishing workflows.
- News aggregation and daily summaries.
- Personal finance analysis.
- Brazilian tax-document organization and analysis.
- IRPF-related preparation and summaries.
- Analysis of banking exports and "Informes de Rendimentos".
- Preparation of information and reports that are ready to paste into official services.
- Coding assistance for the user.
- Local processing of sensitive personal, financial, tax, and PII data.
- A simple web interface suitable for the wife.
- Strong authentication because only two people should have access.

---

# 3. Architecture Decision: Central Linux Host

## DECIDED

The Linux Acer laptop is the central AI/agent server.

```text
                         HOME NETWORK
                              |
                 +------------+------------+
                 |                         |
          Linux Acer Laptop          Wife's Windows Laptop
                 |                         |
         Agent Platform             Web Browser only
         Ollama                    No AI installation
         Local database
         MCP services
         Security
         Web interface
```

### Why this decision

The wife should have the simplest possible experience.

She should only need:

1. Turn on/use her Windows computer.
2. Open the agent web page.
3. Authenticate.
4. Ask for what she needs.

She should not need to:

- Install Ollama.
- Download models.
- Install Python.
- Configure agents.
- Manage API keys.
- Understand MCP.
- Maintain AI software.

The central Linux host also creates one controlled security boundary for sensitive local processing.

---

# 4. Hardware Baseline

## 4.1 Linux AI/Agent Server

**Machine:** Acer Aspire F5-573G-75A3  
**Firmware:** V1.27 / 2017-05-26  
**OS:** Ubuntu 26.04 LTS  
**Kernel:** 7.0.0-1003-gke

### CPU

- Intel Core i7-7500U
- Kaby Lake
- 2 physical cores
- 4 threads
- 2.70 GHz base
- Up to 3.50 GHz
- AVX2
- FMA
- 4 MB L3 cache

### Memory

- 16 GiB RAM
- ~15 GiB currently available to Linux
- Current available memory at measurement: ~6.4 GiB
- Swap: 4 GiB

### GPU

Integrated:

- Intel HD Graphics 620

Discrete:

- NVIDIA GeForce 940MX
- GM107 / Maxwell
- Current NVIDIA driver is **not installed/running**
- `ubuntu-drivers` identifies `nvidia-driver-580` as the recommended distribution driver.

### Storage

SSD:

- Kingston SA400S37240G
- ~224 GB
- Root filesystem on SSD
- ~218 GB root partition
- ~56 GB currently used

HDD:

- Western Digital WD10JPVX
- ~932 GB
- 5400 RPM

Total:

- ~1.13 TiB
- ~585 GiB currently used

### Network

- Qualcomm Atheros Wi-Fi
- Realtek Gigabit Ethernet
- Both available on the Linux host

### Current system state

- GNOME 50.1
- Wayland
- Intel GPU currently driving display
- NVIDIA driver currently unavailable
- System has Docker-related interfaces already present
- System has approximately 1,920 packages installed.

---

# 5. Hardware Implications for Local AI

The machine is **not a modern high-performance local-LLM workstation**.

The main constraints are:

1. 2-core / 4-thread CPU.
2. 16 GB RAM.
3. Older GeForce 940MX.
4. Unknown practical usable VRAM until GPU/driver inspection.
5. Current Linux workload already consumes substantial memory.
6. HDD is suitable for bulk storage but not ideal for active model inference.

Therefore:

> **We will optimize for small/medium quantized Qwen models and practical responsiveness, not maximum model size.**

We should benchmark before deciding the exact Qwen model variant.

We should also avoid treating the NVIDIA 940MX as guaranteed inference hardware until its driver and VRAM configuration are verified.

---

# 6. Local Model Strategy

## DECIDED: Qwen only for local models

Kimi is removed from the initial architecture.

We will focus exclusively on the Qwen family for local inference.

Potential roles:

```text
Ollama
 |
 +-- Qwen 3.5
 |     |
 |     +-- general/private assistant
 |
 +-- Qwen3-Coder
       |
       +-- local/private coding
```

The exact model sizes will be selected based on benchmarking.

### Initial policy

Do not install several large models simultaneously.

Start with one practical Qwen 3.5 model.

Benchmark it.

Then decide whether a second coding-specialized Qwen model is worthwhile.

---

# 7. Cloud Model Strategy

## DECIDED: Claude Code

Claude Code will be the preferred cloud coding environment for tasks where cloud processing is acceptable.

Appropriate uses include:

- General software engineering.
- Repository analysis.
- Refactoring.
- Complex coding.
- Architecture assistance.
- Public/non-sensitive code.
- Tasks explicitly approved for cloud processing.

### Privacy boundary

Claude Code must not receive sensitive RED-classified data.

---

# 8. Data Classification

The system will use three classes.

## GREEN — Cloud allowed

Examples:

- Public news.
- Public documentation.
- Generic programming questions.
- Public marketing concepts.
- Public social-media content.
- Public repositories.

---

## YELLOW — Explicit approval required

Examples:

- Private source code.
- Internal project documents.
- Unpublished marketing material.
- Private business information.

Before sending YELLOW information to a cloud model, the system should explicitly warn the user and request approval.

---

## RED — Local only

Examples:

- CPF.
- Bank statements.
- Bank account information.
- Financial transactions.
- "Informes de Rendimentos".
- IRPF documents.
- Tax records.
- Financial reports.
- Personal/family documents containing sensitive PII.
- Gov.br credentials.
- Bank credentials.
- Authentication secrets.
- Sensitive medical/patient information.

### Hard rule

```text
RED DATA
   |
   +--> Local processing
   |
   +--> Local Qwen
   |
   +--> Local tools
   |
   +--> Local storage
```

There will be **no automatic cloud fallback**.

---

# 9. Brazilian Banking and Gov.br Decision

## DECIDED

We will **not build direct AI authentication or direct AI communication with banking or Gov.br services**.

The AI will not:

- Receive bank passwords.
- Receive Gov.br passwords.
- Store banking credentials.
- Log into banking websites.
- Log into Gov.br.
- Automatically submit tax/government forms.
- Automatically perform financial transactions.
- Control a browser session authenticated to a bank or Gov.br.

This significantly reduces the security risk and simplifies the architecture.

---

# 10. What the Finance/Tax Agent WILL Do

The Finance/Tax Agent will operate entirely on local data supplied by the users.

Typical inputs:

- Bank CSV exports.
- Bank statements.
- PDFs.
- "Informes de Rendimentos".
- Previous "Imposto de Renda" information.
- Receipts.
- Financial spreadsheets.
- Other tax-related documents.

Typical tasks:

```text
Documents
   |
Local extraction
   |
Normalization
   |
Local database / structured data
   |
Local Qwen
   |
Analysis / classification / summaries
   |
Ready-to-review reports
```

Examples of useful requests:

> "Analyze these bank exports and summarize our annual income and expenses."

> "Compare this year's Informe de Rendimentos with last year's information."

> "Organize the information needed for my IRPF."

> "Identify missing information in the documents I provided."

> "Generate a report with the values and fields I need to enter manually."

> "Prepare the information in a format ready to paste into the official service."

The user remains responsible for reviewing and entering/submitting the information in the official government/banking system.

---

# 11. Finance Agent Design

The Finance Agent should separate deterministic processing from AI reasoning.

```text
                    FINANCE AGENT
                          |
             +------------+------------+
             |                         |
       Deterministic layer         Local Qwen
             |                         |
       +-----+------+                  |
       |            |                  |
    Parsing      Calculations          |
       |            |                  |
       +-----+------+------------------+
             |
       Structured local data
             |
          Reports
```

Deterministic software should handle:

- Numeric calculations.
- Date handling.
- Currency handling.
- Transaction normalization.
- Duplicate detection.
- Totals.
- Reconciliation.
- Structured extraction.
- Validation.

Qwen should handle:

- Natural-language interaction.
- Classification.
- Interpretation.
- Summarization.
- Explanation.
- Identification of potentially missing information.

The LLM should **not be the source of truth for financial arithmetic**.

---

# 12. Gov.br / Receita Workflow

For Gov.br/Receita-related work, the workflow will be:

```text
User documents
      |
Local processing
      |
Local Qwen
      |
Prepare information
      |
Validate
      |
Generate human-readable report
      |
USER REVIEWS
      |
USER ENTERS/SUBMITS
      |
Official Gov.br / Receita service
```

This is intentionally different from an autonomous agent.

The goal is:

> **AI-assisted preparation, not AI-controlled government authentication/submission.**

---

# 13. Authentication

## DECIDED

There are exactly two users:

- User
- Wife

Authentication is required.

The web interface must not be publicly accessible without authentication.

Initial requirements:

- Separate user accounts.
- Strong passwords.
- Secure session handling.
- Password hashes, never plaintext passwords.
- Session expiration.
- Logout.
- Basic brute-force protection.
- Local audit trail.

Later we can consider:

- TOTP/2FA.
- Passkeys.
- Reverse proxy with additional authentication.
- Device/session management.

---

# 14. User Permissions

Initially:

```text
                    Agent Platform
                         |
              +----------+----------+
              |                     |
            User                  Wife
              |                     |
       authenticated          authenticated
```

Both users may use the common family agents.

Sensitive personal data should nevertheless have logical ownership where appropriate.

For example:

```text
/user-data/user/
/user-data/wife/
/shared/
```

This allows us to prevent accidental exposure of one person's private documents to the other if that becomes necessary.

---

# 15. Web Interface

The wife should interact only through a browser.

Target:

```text
http://<linux-host>/
```

or eventually:

```text
https://<linux-host>/
```

Example:

```text
+---------------------------------------------+
|              PERSONAL AI                    |
+---------------------------------------------+
|                                             |
| What can I do for you?                      |
|                                             |
| > Schedule a meeting next Tuesday...        |
|                                             |
|                    [Send]                   |
|                                             |
+---------------------------------------------+
| 📅 Calendar    📰 News       📣 Marketing   |
| 💰 Finance    🧾 Taxes       💻 Coding      |
+---------------------------------------------+
```

The complexity of the AI infrastructure should remain invisible to her.

---

# 16. MCP

## DECIDED

Use Model Context Protocol as the main tool abstraction.

Planned integrations:

```text
Calendar MCP
News MCP
Instagram MCP
Finance MCP
Filesystem MCP
Git/Coding MCP
```

Gov.br MCP is **not required for direct authentication/submission** and should not be created for that purpose.

Instead, Gov.br/Receita functionality will focus on local preparation and report generation.

---

# 17. Agent Gateway

Build a local Python gateway responsible for:

- Authentication.
- User/session management.
- Agent routing.
- Model routing.
- MCP integration.
- Permission enforcement.
- Data classification.
- Approval workflows.
- Audit logs.
- Local storage.
- Cloud/local policy enforcement.

Preferred initial stack:

```text
Python
FastAPI
Pydantic
SQLite
MCP
Ollama
```

PostgreSQL can be introduced later if needed.

---

# 18. Model Routing

The application should not directly depend on Qwen or Claude.

Example:

```text
                    Agent Gateway
                         |
                   Data Classifier
                         |
             +-----------+-----------+
             |                       |
          LOCAL                   CLOUD
             |                       |
        Ollama/Qwen             Claude Code
             |
       Qwen 3.5 / Qwen3-Coder
```

Rules:

```text
RED    -> LOCAL
YELLOW -> ASK
GREEN  -> CLOUD or LOCAL
```

---

# 19. Storage Strategy

The SSD should host active services and models where practical.

Suggested structure:

```text
SSD
|
+-- OS
+-- agent application
+-- database
+-- active Ollama models
+-- logs
```

The HDD should be used primarily for:

```text
HDD
|
+-- personal documents
+-- financial documents
+-- tax documents
+-- local archives
+-- backups
+-- large datasets
```

However, the final storage layout should be decided after checking:

- Current HDD partitions/filesystem.
- Available space.
- Backup requirements.
- Whether the HDD contains existing important data.

---

# 20. News Agent

The News Agent remains the first planned production-like agent.

Pipeline:

```text
Sources
 |
RSS / APIs / approved web sources
 |
Normalize
 |
Deduplicate
 |
Classify
 |
Summarize
 |
Rank
 |
Local storage
 |
Daily digest
```

This is intentionally low-risk and gives us a complete end-to-end test of:

- Web collection.
- Agent orchestration.
- Local model inference.
- Scheduling.
- Database storage.
- Web presentation.

---

# 21. Google Calendar

Use official Google APIs and OAuth.

Do not use browser/password automation initially.

Permission rollout:

```text
Phase 1: Read
Phase 2: Create + approval
Phase 3: Modify + approval
Phase 4: Delete, only if necessary
```

---

# 22. Instagram / Marketing

Use official Meta/Instagram APIs where supported.

Capabilities:

- Content calendar.
- Caption generation.
- Hashtag suggestions.
- Marketing ideas.
- Image prompts.
- Draft posts.
- Scheduling.
- Analytics.

Initial workflow:

```text
AI creates draft
       |
Human reviews
       |
Human approves
       |
Publish
```

---

# 23. Coding

Coding remains a separate capability.

```text
                     CODING
                        |
             +----------+----------+
             |                     |
        Claude Code          Local Qwen
             |                     |
        Cloud allowed          Private code
```

Claude Code is preferred when:

- Cloud processing is allowed.
- Maximum coding capability is useful.

Local Qwen/Qwen3-Coder is preferred when:

- Code is sensitive.
- Repository data should remain local.

---

# 24. Implementation Phases

## Phase 0 — Requirements and hardware audit

### Completed

- Central Linux host decided.
- Wife's web-only access decided.
- Linux hardware documented.
- Qwen selected as local model family.
- Kimi removed from initial scope.
- Banking/Gov.br direct authentication removed from scope.
- Two-user authentication requirement established.

### Still needed

- Wife's exact Windows hardware.
- Exact Linux HDD partition/filesystem layout.
- NVIDIA driver/VRAM investigation.
- Network topology for the agent server.
- Final authentication mechanism.
- Exact Google/Instagram requirements.
- Exact finance/tax document workflows.

---

## Phase 1 — Host preparation

Tasks:

- Review existing Ubuntu installation.
- Verify available disk space.
- Verify HDD layout.
- Review Docker installation.
- Review NVIDIA driver state.
- Configure host firewall.
- Configure static/reserved LAN address.
- Establish service account strategy.

---

## Phase 2 — Ollama + Qwen

Tasks:

1. Install/verify Ollama.
2. Determine NVIDIA 940MX capabilities.
3. Benchmark CPU-only inference.
4. Benchmark GPU-assisted inference if practical.
5. Test candidate Qwen 3.5 sizes/quantizations.
6. Select one default local model.
7. Record latency/RAM usage.

---

## Phase 3 — Agent Gateway

Tasks:

- Create project repository.
- Create Python environment.
- Implement FastAPI service.
- Implement authentication.
- Implement user management.
- Implement model abstraction.
- Implement Ollama provider.
- Implement cloud provider abstraction.
- Implement basic audit log.
- Implement MCP integration.

---

## Phase 4 — Web UI

Tasks:

- Login.
- Chat interface.
- Agent selection.
- Conversation history.
- Approval dialogs.
- Basic status/errors.
- User-specific sessions.

---

## Phase 5 — News Agent

Tasks:

- Source configuration.
- RSS/API collection.
- Deduplication.
- Summarization.
- Daily scheduling.
- Web presentation.
- Optional notifications.

---

## Phase 6 — Google Calendar

Tasks:

- OAuth.
- Read calendar.
- Create events.
- Approval.
- Modify events.

---

## Phase 7 — Marketing

Tasks:

- Content generation.
- Draft workflow.
- Image generation integration.
- Instagram/Meta integration.
- Approval.
- Publishing.

---

## Phase 8 — Finance/Tax

Tasks:

- PDF/CSV ingestion.
- Document extraction.
- Local structured storage.
- Transaction normalization.
- Financial summaries.
- Informe de Rendimentos processing.
- Previous IRPF comparison.
- Tax-information reports.
- Ready-to-paste report generation.

No bank/Gov.br authentication.

---

## Phase 9 — Coding

Tasks:

- Claude Code workflow.
- Local Qwen coding workflow.
- Git integration.
- Repository classification.
- Cloud/local routing.

---

## Phase 10 — Security hardening

Tasks:

- Strong authentication.
- Optional 2FA.
- Firewall.
- LAN-only access.
- Secrets management.
- File permissions.
- Model-routing enforcement.
- RED-data tests.
- Audit logging.
- Backup strategy.
- Recovery testing.

---

# 25. Testing Strategy

Each component should have:

## Unit tests

For deterministic logic.

## Integration tests

```text
Agent → MCP → service
```

## Security tests

Verify:

```text
RED data → never sent to cloud
```

## Authentication tests

Verify:

- Invalid credentials rejected.
- Sessions expire.
- User isolation works.
- Unauthorized endpoints are blocked.

## Approval tests

Verify that sensitive actions cannot execute without approval.

## Failure tests

Test:

- Ollama unavailable.
- Cloud model unavailable.
- Google API unavailable.
- Invalid files.
- Corrupt PDFs.
- Network failure.
- Database unavailable.
- Invalid credentials.
- Model timeout.

---

# 26. Audit and Logging

The platform should record locally:

- User.
- Timestamp.
- Agent.
- Model.
- Tool.
- Action.
- Approval status.
- Result.
- Error.

Avoid storing raw sensitive documents or credentials in logs.

Example:

```text
2026-08-09 09:32
User: wife
Agent: calendar
Action: create_event
Approval: approved
Result: success
```

---

# 27. Decisions

| Decision | Status |
|---|---|
| Linux laptop is central AI/agent server | **DECIDED** |
| Wife uses web interface only | **DECIDED** |
| Two users only | **DECIDED** |
| Authentication required | **DECIDED** |
| Ubuntu 26.04 LTS | **DECIDED** |
| Ollama | **DECIDED** |
| Qwen family for local models | **DECIDED** |
| Kimi removed from initial scope | **DECIDED** |
| Claude Code for cloud coding | **DECIDED** |
| MCP as tool abstraction | **DECIDED** |
| RED data local-only | **DECIDED** |
| No direct bank authentication | **DECIDED** |
| No direct Gov.br authentication | **DECIDED** |
| No automatic bank transactions | **DECIDED** |
| No automatic Gov.br/Receita submission | **DECIDED** |
| Finance/tax processing from locally supplied documents | **DECIDED** |
| Generate ready-to-review / ready-to-paste reports | **DECIDED** |
| Human remains responsible for official submission | **DECIDED** |
| Official APIs before browser automation | **DECIDED** |
| News Agent as first functional agent | **PROPOSED** |
| Qwen3-Coder for local coding | **CANDIDATE** |
| n8n | **OPTIONAL / LATER** |
| PostgreSQL | **OPTIONAL / LATER** |
| 2FA/passkeys | **LATER SECURITY ENHANCEMENT** |
| Wife's exact hardware | **PENDING** |
| Exact Qwen model size | **PENDING BENCHMARK** |

---

# 28. Immediate Next Steps

### Next action: Linux host preparation

Before installing anything, inspect:

1. NVIDIA driver/940MX VRAM.
2. HDD partitions and filesystem.
3. Existing Docker installation.
4. Current network configuration.
5. Available RAM while idle.
6. SSD/HDD available space.
7. Whether the laptop should remain powered continuously as the home AI server.

Then:

> **Install and benchmark Ollama + Qwen.**

Only after measuring actual performance should we choose the final Qwen model size.

---

# 29. Guiding Principles

1. **Local-first for sensitive data.**
2. **No direct bank or Gov.br authentication.**
3. **AI assists financial/tax preparation; humans perform official submission.**
4. **Cloud only when there is a clear benefit.**
5. **The model never gets unrestricted authority.**
6. **Tools perform actions; models request them.**
7. **Human approval for consequential actions.**
8. **Official APIs before browser automation.**
9. **Qwen is the initial local-model family.**
10. **Claude Code is the preferred cloud coding environment.**
11. **Model-agnostic architecture.**
12. **Simple UX for the wife.**
13. **Deterministic software for financial calculations and validation.**
14. **Security boundaries must be technically enforced.**
15. **Start small and add agents incrementally.**
16. **Every major component should be replaceable.**

---

# 30. Target End State

The final system should feel like:

> **Our private family AI assistant.**

For the wife:

```text
Open browser
    |
Login
    |
"Schedule a meeting next Tuesday."
```

For personal/financial work:

```text
Upload bank exports / informes / tax documents
    |
Local analysis
    |
Qwen
    |
Structured summaries
    |
Ready-to-review / ready-to-paste reports
    |
Human submits officially
```

For coding:

```text
Private repository
    |
Local Qwen

Non-sensitive repository
    |
Claude Code
```

The underlying technology should remain invisible to the users while preserving strong technical boundaries around sensitive information.
