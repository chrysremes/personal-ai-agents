# Personal AI Agent Platform — Deployment Plan

**Status:** Architecture and planning phase  
**Date:** 2026-08-09  
**Country:** Brazil  
**Primary host:** Acer F5-573G-75A3 running Ubuntu 26.04 LTS  
**Clients:** Linux host + wife's Windows computer

---

## 1. Objectives

Build a personal/family AI agent platform that can:

- Schedule and manage Google Calendar meetings.
- Create and manage Instagram marketing content.
- Gather and summarize news from multiple sources.
- Assist with finance and Brazilian tax workflows, including IRPF and Receita Saúde / Gov.br-related tasks.
- Provide a coding agent for software-development work.
- Keep sensitive financial, authentication, government, and PII data local.
- Be easy for the wife to use through a web interface.
- Remain model- and technology-agnostic so components can be replaced as the AI ecosystem evolves.

### Core principle

> **The LLM should not directly own accounts or unrestricted access to sensitive systems. It should request narrowly scoped tools, with permissions and human approval for consequential actions.**

---

# 2. High-Level Architecture

```text
                         PERSONAL AI PLATFORM
                                  |
                         +--------+--------+
                         |  Web Interface  |
                         +--------+--------+
                                  |
                         +--------+--------+
                         |  Agent Gateway  |
                         | routing/security|
                         | approvals/audit |
                         +--------+--------+
                                  |
                    +-------------+-------------+
                    |                           |
              LOCAL MODELS                 CLOUD MODEL
                 Ollama                    Claude Code
                    |                           |
              Qwen 3.5 /                    Coding and
             local models                 non-sensitive work
                    |
              +-----+------+
              |            |
        General AI    Local Coding
          Qwen 3.5    Qwen3-Coder
              |
             MCP
              |
    +---------+----------+----------+----------+
    |         |          |          |          |
 Calendar   News     Instagram   Finance   Gov.br
    |         |          |          |          |
 Google      RSS       Meta API   Local DB   Official
 Calendar                          /files    services
```

The wife's computer should initially act only as a **web client**. The Linux laptop hosts the agent platform and local AI.

---

# 3. Host Hardware

## Primary AI/Agent Server

**Acer Aspire F5-573G-75A3**

- CPU: Intel Core i7, 7th generation
- RAM: 16 GB
- GPU: NVIDIA GeForce 940MX
- Linux SSD
- Local-data HDD
- OS: Ubuntu 26.04 LTS

### Consequence for model selection

This is a relatively constrained local-AI machine by current standards.

The initial local model will therefore be:

> **Qwen 3.5**, using a model size/quantization selected after benchmarking the actual machine.

We should **not assume that large Qwen 3.5 variants or Kimi K2.5 are practical** on this hardware.

The NVIDIA 940MX should not be treated as the main reason to choose a model; CPU/RAM and the available GPU memory are likely to be the practical constraints.

---

# 4. Model Strategy

## 4.1 Local general-purpose model

### Decision: Qwen 3.5

Use Qwen 3.5 through Ollama for:

- Private/PII-aware tasks
- Finance
- Tax preparation
- Government-service preparation
- Local document analysis
- Local personal assistant tasks
- General reasoning where sensitive information is involved

The exact model size will be selected after hardware benchmarking.

---

## 4.2 Local coding model

Candidate:

### Qwen3-Coder

Use it when local/private software-development tasks require a coding-specialized model and the hardware can run an appropriate quantized version.

The architecture must not depend on Qwen3-Coder specifically, however.

---

## 4.3 Cloud coding model

### Decision: Claude Code

Use Claude Code primarily for:

- High-capability coding
- Repository-level engineering
- Complex software-development tasks
- Non-sensitive reasoning
- Tasks where frontier cloud capability is valuable

### Hard privacy rule

Claude Code must **not receive RED-classified financial, government, authentication, or highly sensitive PII data**.

---

# 5. Model-Agnostic Design

The application must never hard-code a specific model.

Instead:

```text
Agent
  |
Model Router
  |
+-----------+-----------+-----------+
|           |           |
Claude    Ollama      Future Model
           |
       Qwen/Kimi/...
```

Example configuration:

```yaml
models:
  cloud_coding:
    provider: anthropic
    model: claude-...

  local_general:
    provider: ollama
    model: qwen3.5:...

  local_coding:
    provider: ollama
    model: qwen3-coder:...
```

Changing models should require configuration changes rather than rewriting agents.

---

# 6. Privacy Architecture

Three data classifications will be used.

## GREEN — Cloud allowed

Examples:

- Public news
- Public documentation
- Generic programming questions
- Public marketing ideas
- Public social-media content
- Public repositories

---

## YELLOW — Cloud only with explicit permission

Examples:

- Private source code
- Internal business documents
- Unpublished marketing plans
- Private project information

The user must explicitly approve sending this information to a cloud model.

---

## RED — Local only

Examples:

- CPF and other sensitive PII
- Bank statements
- Bank-account information
- Financial transactions
- IRPF data
- Tax documents
- Gov.br credentials/tokens
- Receita Saúde information
- Medical/patient information
- Passwords and authentication secrets
- Highly sensitive family documents

### Rule

```text
RED DATA
   |
LOCAL PROCESSING ONLY
   |
LOCAL MODEL / LOCAL TOOL
   |
LOCAL STORAGE
```

There must be **no automatic fallback from local to cloud** for RED data.

---

# 7. Security Principles

## 7.1 Least privilege

Agents receive only the permissions required for a task.

Example:

```text
calendar.read       ALLOW
calendar.create     ALLOW + approval
calendar.modify     ALLOW + approval
calendar.delete     DENY initially

finance.read        LOCAL ONLY
finance.transfer    DENY initially

instagram.publish   ALLOW + approval
govbr.submit        ALLOW + approval
shell.execute       DENY by default
```

---

## 7.2 Human approval for consequential actions

Require explicit approval before:

- Sending financial transactions
- Submitting government forms
- Publishing Instagram posts
- Sending important emails
- Deleting files/data
- Making other irreversible or externally visible changes

Example:

```text
ACTION REQUIRES APPROVAL

Publish Instagram post?

[content preview]

[Cancel]                 [Approve]
```

---

## 7.3 Credentials

Never expose passwords or secrets to prompts.

Do not store sensitive credentials directly in ordinary `.env` files.

Use an OS credential/keyring or dedicated encrypted secret mechanism.

---

# 8. Tool Architecture — MCP

### Decision: Model Context Protocol (MCP)

MCP should be the primary tool integration layer.

Planned tools:

```text
Calendar MCP
News MCP
Instagram MCP
Finance MCP
Filesystem MCP
Git/Coding MCP
Gov.br MCP
```

The same tools should be usable by different models.

Example:

```text
Claude
  |
  +-- Calendar MCP
  +-- Git MCP
  +-- News MCP

Qwen
  |
  +-- Finance MCP
  +-- Filesystem MCP
  +-- Gov.br MCP
```

This is a major part of the long-term flexibility strategy.

---

# 9. Agent Gateway

Build a small local Python service responsible for:

- Model routing
- Agent selection
- MCP integration
- Permission enforcement
- Approval workflows
- Audit logging
- Data-classification enforcement
- Session management
- User identification
- Local storage

Initial technology preference:

- Python
- FastAPI
- Pydantic
- SQLite initially
- PostgreSQL later only if justified
- MCP
- Ollama API

---

# 10. User Interface

The wife should have the simplest possible experience.

Initial interface:

```text
http://<agent-server>/ 
```

or, preferably on the home network:

```text
https://<agent-server>/
```

Example:

```text
+---------------------------------------------+
|              PERSONAL AI                    |
+---------------------------------------------+
|                                             |
| What can I do for you?                      |
|                                             |
| > Schedule a meeting with Carlos Friday...  |
|                                             |
|                    [Send]                   |
|                                             |
+---------------------------------------------+
| Available agents                            |
|                                             |
| 📅 Calendar                                  |
| 📰 News                                      |
| 📣 Marketing                                 |
| 💰 Finance                                   |
| 🧾 Taxes                                     |
| 💻 Coding                                    |
+---------------------------------------------+
```

The goal is that the wife does **not** need to know:

- Ollama
- MCP
- Python
- Docker
- model names
- command-line tools
- agent configuration

Those are implementation details.

---

# 11. Network Architecture

Initial preferred topology:

```text
                    HOME LAN
                       |
              +--------+--------+
              |                 |
       Linux Acer Laptop    Windows PC
              |
       Agent Platform
       Ollama
       MCP
       Database
       Local Files
```

The Linux machine is the central private AI server.

The Windows machine accesses the platform through the web UI.

### Internet exposure

Initially:

> **Do not expose the agent directly to the public Internet.**

Access should remain restricted to the trusted home network.

Remote access can be evaluated later as a separate security project.

---

# 12. Finance Architecture

Finance should be treated as a specialized subsystem.

```text
                    FINANCE AGENT
                          |
             +------------+------------+
             |                         |
       Deterministic services       Local LLM
             |                         |
      +------+------+                  |
      |      |      |                  |
    Bank   Tax   Documents             |
      |      |      |                  |
      +------+------+------------------+
                     |
                 Local DB
```

The deterministic layer should handle:

- Calculations
- Transaction normalization
- Categorization
- PDF/CSV extraction
- Reconciliation
- Validation
- Duplicate detection
- Tax calculations/rules where possible

The LLM should primarily handle:

- Natural-language interaction
- Classification suggestions
- Document interpretation
- Explanations
- Anomaly investigation

Sensitive raw data should remain local.

---

# 13. Bank Integration

Before considering browser automation, investigate:

1. Official bank APIs
2. Open Finance Brasil
3. Official integrations
4. Local import/export mechanisms

Preferred architecture:

```text
Bank
 |
Open Finance / Official API
 |
Local connector
 |
Local finance database
 |
Local AI
```

Avoid unrestricted browser/screen scraping whenever an official integration exists.

---

# 14. Gov.br / Receita Federal Architecture

Government services receive special treatment.

Priority:

```text
1. Official API
       ↓
2. Official SDK
       ↓
3. OAuth / authorized integration
       ↓
4. MCP integration
       ↓
5. Controlled browser automation
```

For IRPF, Receita Saúde and Gov.br workflows:

```text
AI
 |
Prepare
 |
Validate
 |
Display complete action
 |
Human approval
 |
Authenticated official service
 |
Submit
```

The AI should not autonomously submit sensitive government information without an explicit approval step.

---

# 15. Google Calendar

Use official Google Calendar APIs and OAuth.

Do not initially automate Google Calendar through browser/password automation.

Permission rollout:

```text
Phase 1: calendar.read
Phase 2: calendar.create + approval
Phase 3: calendar.modify + approval
Phase 4: calendar.delete, only if actually required
```

---

# 16. Instagram / Marketing

Use official Meta/Instagram APIs where supported.

Marketing Agent capabilities:

- Content calendar
- Caption generation
- Hashtag suggestions
- Image-generation prompts
- Post drafts
- Scheduling
- Analytics

Initial workflow:

```text
AI
 |
Create draft
 |
Human approval
 |
Publish
```

Automatic publishing can be considered later for low-risk content.

---

# 17. News Agent

This should be the first real agent because it is low-risk and useful.

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

Example:

```text
Good morning.

🤖 AI
3 important developments

⚡ Technology
4 developments

🇧🇷 Brazil
5 developments

💰 Finance
3 developments

🔬 Research
4 developments
```

This will also serve as the first end-to-end test of the platform.

---

# 18. Coding Agent

Coding should remain somewhat separate from the family assistant.

```text
                    CODING
                       |
              +--------+--------+
              |                 |
         Claude Code        Local Coding
              |                 |
           Cloud             Ollama
              |                 |
      Allowed projects     Private projects
```

Use Claude Code for high-capability, non-sensitive work.

Use local Qwen/Qwen3-Coder for sensitive repositories or projects that must remain local.

---

# 19. Initial Software Stack

## Required

```text
Ubuntu 26.04 LTS
Python
Git
Ollama
FastAPI
Pydantic
MCP
SQLite
```

## Likely

```text
Docker
Node.js
Playwright
```

## Later / only when justified

```text
PostgreSQL
n8n
additional agent frameworks
remote-access infrastructure
```

Avoid installing several overlapping agent platforms at the beginning.

---

# 20. Implementation Phases

## Phase 0 — Hardware and requirements audit

Already identified:

- Acer F5-573G-75A3
- Core i7 7th gen
- 16 GB RAM
- GeForce 940MX
- SSD + HDD
- Ubuntu 26.04 LTS

Still needed:

- Exact CPU model
- Exact 940MX VRAM
- Available SSD/HDD capacity
- NVIDIA driver status
- Wife's Windows PC specifications
- Google account/calendar requirements
- Instagram account type
- Banks to be integrated
- Exact Gov.br/Receita workflows required

---

## Phase 1 — Base platform

Install/configure:

- Git
- Python
- Node.js
- Docker
- Ollama
- VS Code

Verify the Linux host.

---

## Phase 2 — Local AI

Install Ollama.

Benchmark Qwen 3.5 variants.

Determine the largest practical model for:

- Latency
- RAM usage
- Context length
- Portuguese performance
- Tool calling
- Reasoning
- Document handling

Do not select Kimi K2.5 unless hardware testing shows it is practical.

---

## Phase 3 — Agent Gateway

Implement:

```text
personal-ai/
├── gateway/
├── agents/
│   ├── calendar/
│   ├── news/
│   ├── marketing/
│   ├── finance/
│   ├── govbr/
│   └── coding/
├── mcp/
├── security/
├── models/
├── storage/
└── tests/
```

---

## Phase 4 — News Agent

First production-like agent.

Goals:

- Source ingestion
- Deduplication
- Summarization
- Ranking
- Daily digest
- Local persistence

---

## Phase 5 — Google Calendar

Implement:

- OAuth
- Read calendar
- Create events
- Approval workflow
- Modify events

---

## Phase 6 — Marketing / Instagram

Implement:

- Content generation
- Drafts
- Human approval
- Meta/Instagram integration
- Scheduling

---

## Phase 7 — Finance

Implement:

- Local document ingestion
- CSV/PDF parsing
- Transaction database
- Categorization
- Reconciliation
- Reports
- Open Finance/API investigation

---

## Phase 8 — Gov.br / Receita

Implement only after the finance subsystem is trusted.

Start with:

```text
prepare
→ validate
→ review
```

Then carefully add:

```text
human approval
→ authenticated submission
```

---

## Phase 9 — Coding

Integrate:

- Claude Code
- Local coding model
- Git
- Repository permissions
- Cloud/local routing

---

## Phase 10 — Security hardening

Implement:

- Authentication
- Role/user separation
- MCP permissions
- Data classification
- Approval UI
- Audit logs
- Credential management
- Local-only routing for RED data
- Backup/recovery strategy
- Network restrictions

---

# 21. Testing Strategy

Every agent should have:

### Unit tests

Test deterministic business logic independently of the LLM.

### Integration tests

Test:

```text
Agent → MCP → Service
```

### Security tests

Verify:

```text
RED data → never reaches cloud model
```

### Approval tests

Verify that dangerous actions cannot execute without approval.

### Failure tests

Examples:

- Google unavailable
- Ollama unavailable
- model timeout
- invalid credentials
- malformed PDF
- Gov.br unavailable
- duplicate transaction
- network disconnected

---

# 22. Observability and Audit

The system should record locally:

- User
- Agent
- Timestamp
- Model used
- Tool invoked
- Action requested
- Approval status
- Result
- Errors

For sensitive data, logs should avoid storing raw PII whenever possible.

Example:

```text
2026-08-09 09:32
User: wife
Agent: calendar
Action: create_event
Approval: approved
Result: success
```

rather than logging entire private documents or credentials.

---

# 23. Long-Term Flexibility

The architecture must allow replacement of:

```text
Claude
Qwen
Kimi
Ollama
MCP servers
Google APIs
Meta APIs
database
web UI
```

without redesigning the entire system.

The stable layers should be:

```text
                    USER
                     |
                  Web UI
                     |
               Agent Gateway
                     |
          +----------+----------+
          |                     |
      Model API              MCP Tools
          |                     |
   +------+------+       +------+------+ 
   |             |       |      |      |
 Cloud         Local   Calendar News Finance ...
 Model         Model
```

This is the primary architectural defense against rapid AI ecosystem changes.

---

# 24. Decisions Already Made

| Decision | Status |
|---|---|
| Central Linux host | **DECIDED** |
| Wife uses web UI | **DECIDED** |
| Ubuntu 26.04 LTS | **DECIDED** |
| Ollama | **DECIDED** |
| Qwen 3.5 as initial local model family | **DECIDED** |
| Claude Code for cloud coding | **DECIDED** |
| MCP as tool abstraction | **DECIDED** |
| RED data local-only | **DECIDED** |
| Human approval for consequential actions | **DECIDED** |
| Model-agnostic architecture | **DECIDED** |
| Official APIs before browser automation | **DECIDED** |
| News Agent as first functional agent | **PROPOSED** |
| Qwen3-Coder local coding model | **CANDIDATE** |
| Kimi K2.5 local model | **CANDIDATE / hardware dependent** |
| n8n | **LATER / optional** |
| PostgreSQL | **LATER / optional** |

---

# 25. Immediate Next Steps

## Step 1 — Complete Linux hardware inventory

Run:

```bash
inxi -Fxxxz
free -h
lscpu
nvidia-smi
```

If `nvidia-smi` is unavailable, determine the installed NVIDIA driver and GPU information separately.

---

## Step 2 — Collect Windows hardware information

Record:

```text
CPU:
RAM:
GPU:
VRAM:
Storage:
Windows version:
```

---

## Step 3 — Determine local model feasibility

Use the actual Linux hardware to select:

- Qwen 3.5 model size
- Quantization
- Context length
- CPU/GPU execution strategy

---

## Step 4 — Design the local network/security model

Before exposing the web UI to the Windows machine:

- Define LAN access
- Define authentication
- Define users
- Define local-only services
- Define storage locations
- Define firewall rules

---

## Step 5 — Install Ollama and run the first local benchmark

Only after the hardware/model decision.

---

# 26. Guiding Principles

The project should always follow these principles:

1. **Local-first for sensitive data.**
2. **Cloud only when there is a clear benefit.**
3. **The model never gets unrestricted authority.**
4. **Tools perform actions; models request them.**
5. **Human approval for consequential actions.**
6. **Official APIs before browser automation.**
7. **Model-agnostic architecture.**
8. **Simple UX for the wife.**
9. **Deterministic software for financial calculations and validation.**
10. **Security boundaries must be technical, not merely policy-based.**
11. **Start small and add agents incrementally.**
12. **Every important component should be replaceable.**

---

## Target End State

The finished system should feel like:

> **"Our private family AI assistant."**

The wife should be able to open a web page and say:

```text
"Schedule a dentist appointment next Tuesday at 14:00."

"Prepare three Instagram posts for next week."

"What were the most important news stories today?"

"Organize these receipts for our taxes."

"Prepare the Receita Saúde information from these documents."
```

And you should be able to use the same platform for:

```text
"Analyze this repository."

"Refactor this Python module."

"Run the tests and fix the failures."

"Explain this architecture."

"Work on this private repository without sending its contents to the cloud."
```

while the underlying system automatically routes each task to the appropriate **local model, cloud model, deterministic service, or human approval workflow**.
