# Personal AI Agent Platform — Deployment Plan (v3)

**Status:** Phase 0 (requirements/hardware audit) complete — entering Phase 1 (host preparation)
**Date:** 2026-08-09
**Country:** Brazil
**Primary host:** Acer Aspire F5-573G-75A3 running Ubuntu 26.04 LTS
**Clients:** Primary Linux host (server) + wife's Windows 11 laptop (web client only)
**Users:** Two authenticated users only — user and wife

---

## Changelog since v2

- Wife's Windows hardware confirmed: Acer Aspire 5 N20C4, i5, 8 GB RAM, 256 GB SSD — she remains web-client-only, so this hardware is sufficient regardless of spec.
- Linux HDD/SSD partition layout confirmed via `lsblk`.
- NVIDIA driver is now installed and working (previously "not installed"): driver 580.173.02, CUDA 13.0, GeForce 940MX, 4096 MiB VRAM total, currently idle.
- Home network topology confirmed: existing resilient Multi-WAN setup: two ISPs, two modems in bridge mode, TP-Link ER605 V2 load-balancing router, AP-mode Wi-Fi, UPS, DHCP reservations, QoS. Full write-up: https://medium.com/@chrystian_3642/high-availability-home-internet-setup-with-multi-wan-ef7c0f9e0103. AI server will live LAN-only, not exposed to either WAN initially.
- Authentication mechanism decided: username + password, two accounts (user, wife), configured on first interaction. 2FA/passkeys deferred to Phase 10.
- **First functional agent confirmed: News Aggregator** (was "proposed" in v2, now "decided"), with scope defined (sources, categories, output format).
- Phase 0 marked mostly complete; Phase 1 (Linux host preparation) is next, with a concrete checklist of commands to run before installing anything.

Everything else from v2 (data classification, no direct bank/Gov.br authentication, Qwen-only local strategy, Claude Code for cloud coding, MCP as tool abstraction, agent gateway design) remains unchanged and is carried forward below.

---

## 1. Executive Summary

We are building a **private, local-first family AI agent platform**.

The Linux Acer laptop hosts the agent platform and local AI. The wife's Windows laptop accesses it through a simple web interface, so she does not need to install, configure, or understand the underlying AI stack.

The system combines:

- Local Qwen models through Ollama.
- Claude Code for selected cloud-based coding tasks.
- MCP as the tool/integration abstraction.
- A local agent gateway responsible for routing, permissions, authentication, approvals, and audit logging.
- Local deterministic software for financial/document processing.
- Official APIs where useful for non-sensitive services such as Google Calendar and Instagram.
- **No direct AI authentication or automated login to banking or Gov.br services.**

The architecture is intentionally model-agnostic so that Qwen, Claude, Ollama, MCP components, or other technologies can be replaced later without redesigning the whole platform.

Hardware and network baselines are now fully documented (see sections 4 and 24), authentication is decided, and the **first concrete build target is the News Aggregator agent**, chosen because it exercises the whole platform (scheduler, collection, local model, storage, web UI) without touching any sensitive data.

---

## 2. Objectives

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

## 3. Architecture Decision: Central Linux Host

### DECIDED

The Linux Acer laptop is the central AI/agent server.

```text
                         HOME NETWORK
                              |
                 +------------+------------+
                 |                         |
          Linux Acer Laptop          Wife's Acer Aspire 5 N20C4
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

She only needs to:

1. Turn on/use her Windows computer.
2. Open the agent web page.
3. Authenticate (username + password).
4. Ask for what she needs.

She should not need to:

- Install Ollama.
- Download models.
- Install Python.
- Configure agents.
- Manage API keys.
- Understand MCP.
- Maintain AI software.

The central Linux host also creates one controlled security boundary for sensitive local processing. Her machine's modest specs (8 GB RAM, no discrete GPU) are irrelevant to platform performance since she never runs inference locally.

---

## 4. Hardware Baseline

### 4.1 Linux AI/Agent Server (confirmed)

**Machine:** Acer Aspire F5-573G-75A3
**Firmware:** V1.27 / 2017-05-26
**OS:** Ubuntu 26.04 LTS
**Kernel:** 7.0.0-1003-gke

**CPU**
- Intel Core i7-7500U, Kaby Lake, 2 physical cores / 4 threads, 2.70 GHz base (up to 3.50 GHz), AVX2, FMA, 4 MB L3 cache.

**Memory**
- 16 GiB RAM (~15 GiB available to Linux), swap 4 GiB.

**GPU — confirmed working**
- Integrated: Intel HD Graphics 620.
- Discrete: NVIDIA GeForce 940MX (GM107/Maxwell), **driver now installed and functioning**:
  ```text
  Driver: 580.173.02
  CUDA:   13.0
  VRAM:   4096 MiB total, 4 MiB in use, 0% utilization, 51°C idle
  ```
  → The 940MX is a genuine but small 4 GB VRAM device. Usable for benchmarking small quantized models, not a high-end accelerator.

**Storage — confirmed layout**
```text
sda  223.6G  (Kingston SA400S37240G SSD)
├─sda1  1G      /boot/efi
└─sda2  222.5G  /                (root — OS, applications, agent platform, active services)

sdb  931.5G  (Western Digital WD10JPVX HDD, 5400 RPM)
└─sdb1  931.5G  /mnt/data        (candidate for financial/tax documents, news archive, reports, backups)
```
Before storing any RED-classified data on `/mnt/data`, we will inspect its filesystem type, mount options, ownership, permissions, and existing contents (see Phase 1 checklist, section 25).

**Network**
- Qualcomm Atheros Wi-Fi, Realtek Gigabit Ethernet — both available.

**Current system state**
- GNOME 50.1, Wayland, Intel GPU currently driving the display, Docker-related interfaces already present, ~1,920 packages installed.

### 4.2 Wife's Windows Client (confirmed)

**Machine:** Acer Aspire 5 N20C4
- CPU: Intel Core i5
- RAM: 8 GB
- Storage: 256 GB SSD
- OS: Windows 11

This machine will **only** run a web browser against the Linux server. Exact CPU generation/integrated GPU are not needed since no local AI workload runs here.

---

## 5. Hardware Implications for Local AI

The Linux host is **not a modern high-performance local-LLM workstation**, but it is now fully characterized:

1. 2-core / 4-thread CPU — the main bottleneck for inference speed.
2. 16 GB RAM — enough for small-to-medium quantized models plus the platform itself, if managed carefully.
3. NVIDIA 940MX with a confirmed **4 GB VRAM** ceiling — usable for small quantized Qwen models (roughly up to ~7–8B at 4-bit), not for anything larger; larger models will run CPU-only or be ruled out.
4. HDD (`/mnt/data`) is suitable for bulk/document storage, not for active model weights (keep active Ollama models on the SSD for I/O speed).

Therefore, unchanged from v2:

> **We optimize for small/medium quantized Qwen models and practical responsiveness, not maximum model size.**

Formal benchmarking (CPU-only vs. GPU-assisted, tokens/sec, RAM/VRAM usage, thermal behavior under sustained load) is scheduled in Phase 2, now that the driver situation is resolved and the ceiling (4 GB VRAM) is known.

---

## 6. Local Model Strategy

### DECIDED: Qwen only for local models

Kimi is removed from the initial architecture (a 1T-parameter model like Kimi K2.6/K2.7 needs ~350 GB combined RAM+VRAM for genuine local inference — completely out of reach for this hardware; the Ollama `:cloud` tags are not actually local and were correctly excluded).

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

**Initial policy:** don't install several large models simultaneously. Start with one practical Qwen 3.5 quantization sized for the 4 GB VRAM / 16 GB RAM ceiling, benchmark it, then decide whether a second coding-specialized Qwen model is worthwhile.

---

## 7. Cloud Model Strategy

### DECIDED: Claude Code

Claude Code is the preferred cloud coding environment for tasks where cloud processing is acceptable:

- General software engineering.
- Repository analysis.
- Refactoring.
- Complex coding.
- Architecture assistance.
- Public/non-sensitive code.
- Tasks explicitly approved for cloud processing.

**Privacy boundary:** Claude Code must never receive RED-classified data (section 8).

---

## 8. Data Classification

Three classes govern all routing decisions.

**GREEN — Cloud allowed:** public news, public documentation, generic programming questions, public marketing concepts, public social-media content, public repositories.

**YELLOW — Explicit approval required:** private source code, internal project documents, unpublished marketing material, private business information. The system must warn the user and request approval before sending YELLOW data to a cloud model.

**RED — Local only:** CPF, bank statements, bank account information, financial transactions, Informes de Rendimentos, IRPF documents, tax records, financial reports, sensitive PII, Gov.br credentials, bank credentials, authentication secrets, sensitive medical/patient information.

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

**No automatic cloud fallback for RED data — this is a hard rule, technically enforced, not a policy suggestion.**

---

## 9. Brazilian Banking and Gov.br Decision

### DECIDED

We will **not** build direct AI authentication or direct AI communication with banking or Gov.br services. The AI will not receive bank or Gov.br passwords, store banking credentials, log into banking websites or Gov.br, automatically submit tax/government forms, automatically perform financial transactions, or control a browser session authenticated to a bank or Gov.br.

This is not just a convenience simplification — the Receita Federal explicitly warns that it never asks for banking or Gov.br passwords by any channel; any tool that requests them, even one you build yourself, reproduces the shape of a phishing vector against your own accounts.

---

## 10. What the Finance/Tax Agent WILL Do

Operates entirely on local data supplied by the users. Typical inputs: bank CSV exports, bank statements, PDFs, Informes de Rendimentos, previous IRPF information, receipts, financial spreadsheets, other tax-related documents.

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
- "Analyze these bank exports and summarize our annual income and expenses."
- "Compare this year's Informe de Rendimentos with last year's information."
- "Organize the information needed for my IRPF."
- "Identify missing information in the documents I provided."
- "Generate a report with the values and fields I need to enter manually."
- "Prepare the information in a format ready to paste into the official service."

The user remains responsible for reviewing and entering/submitting information in the official government/banking system.

---

## 11. Finance Agent Design

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

Deterministic software handles: numeric calculations, date handling, currency handling, transaction normalization, duplicate detection, totals, reconciliation, structured extraction, validation.

Qwen handles: natural-language interaction, classification, interpretation, summarization, explanation, identification of potentially missing information.

**The LLM is never the source of truth for financial arithmetic.**

---

## 12. Gov.br / Receita Workflow

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

Goal: **AI-assisted preparation, not AI-controlled government authentication/submission.**

---

## 13. Authentication — DECIDED (mechanism confirmed)

Two users only: **user** and **wife**.

**Mechanism:** username + password, configured during the first interaction / initial setup.

Requirements:
- Separate usernames per account.
- Password setup happens once, at first run.
- Passwords stored only as secure hashes (e.g. Argon2id/bcrypt) — no plaintext, ever, anywhere (config files, logs, backups).
- Secure session handling with expiration.
- Explicit logout.
- Failed-login protection (rate limiting / lockout).
- Local authentication database (SQLite, per section 17).
- Authorization checks on every protected operation, not just at login.

Deferred to Phase 10: TOTP 2FA, passkeys/WebAuthn, device/session management, reverse-proxy authentication layer.

---

## 14. User Permissions

```text
                    Agent Platform
                         |
              +----------+----------+
              |                     |
            User                  Wife
              |                     |
       authenticated          authenticated
```

Both users may use the common family agents. Sensitive personal data still gets logical ownership where appropriate:

```text
/user-data/user/
/user-data/wife/
/shared/
```

This prevents accidental exposure of one person's private documents to the other if that becomes necessary.

---

## 15. Web Interface

The wife interacts only through a browser, initially at `http://<linux-host>/` on the LAN (moving to `https://` once a certificate strategy is in place — see section 24).

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

The complexity of the AI infrastructure remains invisible to her.

---

## 16. MCP

### DECIDED

Model Context Protocol is the main tool abstraction.

```text
Calendar MCP
News MCP
Instagram MCP
Finance MCP
Filesystem MCP
Git/Coding MCP
```

Gov.br MCP is **not** built for direct authentication/submission — that functionality stays as local preparation and report generation only (section 12).

---

## 17. Agent Gateway

A local Python gateway responsible for authentication, user/session management, agent routing, model routing, MCP integration, permission enforcement, data classification, approval workflows, audit logs, local storage, and cloud/local policy enforcement.

Preferred initial stack:
```text
Python
FastAPI
Pydantic
SQLite
MCP
Ollama
```
PostgreSQL can be introduced later if needed (currently optional/deferred).

---

## 18. Model Routing

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

```text
RED    -> LOCAL
YELLOW -> ASK
GREEN  -> CLOUD or LOCAL
```

---

## 19. Storage Strategy — layout confirmed

```text
SSD (/dev/sda2, 222.5 GB, mounted at /)
|
+-- OS
+-- agent application
+-- database
+-- active Ollama models
+-- logs

HDD (/dev/sdb1, 931.5 GB, mounted at /mnt/data)
|
+-- personal documents
+-- financial documents
+-- tax documents
+-- local archives
+-- backups
+-- large datasets
```

The physical layout matches the v2 design intent exactly. **Before storing anything RED-classified on `/mnt/data`,** Phase 1 must confirm: filesystem type, mount options, ownership, permissions, and whether any existing data lives there that needs to be accounted for.

---

## 20. News Agent — first functional agent (DECIDED, scope defined)

### Why News first

It exercises almost the entire platform at low risk:

```text
Scheduler
    |
Source collection
    |
Web/RSS/API tools
    |
Deduplication
    |
Classification
    |
Local Qwen
    |
Summarization
    |
Ranking
    |
Local database
    |
Web UI
```

It requires no banking credentials, no Gov.br credentials, no financial transactions, no sensitive PII, and no external publishing permissions — a clean end-to-end test of collection, orchestration, local inference, scheduling, storage, and presentation.

### Initial scope

**Sources:** RSS feeds and official news APIs first; selected public web sources where useful. Avoid uncontrolled scraping as the default. Exact source list to be defined during implementation.

**Processing pipeline:**
```text
Collect → Normalize → Deduplicate → Classify → Rank → Summarize → Store
```

**Initial categories:** Brazil, International, Technology, Artificial Intelligence, Science, Finance/Economy, Software/Engineering, Research.

**Output — daily digest example:**
```text
Good morning.

🇧🇷 Brazil
3 important stories

🌎 International
3 important stories

🤖 AI / Technology
5 important stories

💰 Finance / Economy
3 important stories

🔬 Science / Research
3 important stories
```
Each summary must retain the original source and publication info so the user can inspect the source article — no reproduction of full article text, summaries in the platform's own words.

---

## 21. Google Calendar

Official Google APIs and OAuth. No browser/password automation.

```text
Phase 1: Read
Phase 2: Create + approval
Phase 3: Modify + approval
Phase 4: Delete, only if necessary
```

---

## 22. Instagram / Marketing

Official Meta/Instagram APIs where supported. Capabilities: content calendar, caption generation, hashtag suggestions, marketing ideas, image prompts, draft posts, scheduling, analytics.

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

## 23. Coding

```text
                     CODING
                        |
             +----------+----------+
             |                     |
        Claude Code          Local Qwen
             |                     |
        Cloud allowed          Private code
```

Claude Code preferred when cloud processing is allowed and maximum coding capability is useful. Local Qwen/Qwen3-Coder preferred when code or repository data is sensitive and should remain local.

---

## 24. Network Architecture — confirmed

The agent server lives inside the existing home network, which already runs a resilient **Multi-WAN** architecture:

- Two independent ISPs.
- Two ISP modems in bridge mode.
- TP-Link ER605 V2 Multi-WAN router/load balancer.
- Wireless router in Access Point mode.
- UPS for critical network equipment.
- DHCP reservations for selected devices.
- Load balancing, Application Optimized Routing, QoS.
- SNMPv3 monitoring, Linux-based WAN monitoring.

Full write-up: https://medium.com/@chrystian_3642/high-availability-home-internet-setup-with-multi-wan-ef7c0f9e0103

**Implication:** the network is already well suited to hosting the AI server reliably. Initial topology:

```text
Home LAN
    |
    +-- Linux AI Server
    |
    +-- Wife's Windows Client
```

**Initial access model — LAN-only, no WAN exposure:**
```text
Internet
    X
    |
Home LAN
    |
Linux AI Server
    |
Authenticated Web UI
```

Remote access (e.g. reverse proxy + TLS + additional auth for use outside the home) is deferred to a separate security project, after Phase 10 hardening.

---

## 25. Implementation Phases

### Phase 0 — Requirements and hardware audit — **mostly complete**

Completed:
- Central Linux host decided.
- Wife's web-only access decided.
- Wife's exact hardware confirmed (Acer Aspire 5 N20C4, i5, 8 GB, 256 GB SSD).
- Linux hardware fully documented, including confirmed NVIDIA driver/VRAM (940MX, 4 GB).
- Linux storage layout confirmed (`lsblk`).
- Existing multi-WAN network architecture reviewed and confirmed suitable.
- Authentication mechanism decided (username + password, two accounts).
- Qwen selected as the sole local model family; Kimi removed from scope.
- Claude Code confirmed for cloud coding.
- Banking/Gov.br direct authentication excluded from scope.
- Two-user authentication requirement established.
- **News Aggregator selected and scoped as the first functional agent.**

Still open (non-blocking, resolved as Phase 1 executes):
- Exact `/mnt/data` filesystem type, mount options, ownership/permissions.
- Current Docker installation status.
- Firewall configuration review.
- LAN IP / DHCP reservation for the Linux server.
- Whether the laptop stays powered continuously as a server (lid-close behavior, suspend, UPS sufficiency for the laptop's own adapter, auto-restart of services).
- Exact Google Calendar / Instagram API requirements (will be defined at Phase 6/7).
- Exact finance/tax document workflows (Phase 8).

### Phase 1 — Linux host preparation — **next**

Checks to run before installing anything:

```bash
# Storage
findmnt /mnt/data
df -h / /mnt/data
ls -ld /mnt/data
sudo ls -la /mnt/data | head -50

# Docker
docker --version
docker compose version
systemctl status docker --no-pager

# Network
ip -br addr
ip route
```

Tasks:
- Inspect `/mnt/data` (filesystem, mount options, ownership, permissions, existing contents).
- Review existing Docker installation.
- Configure host firewall (LAN-only exposure).
- Determine/reserve a static LAN IP (DHCP reservation on the ER605).
- Decide continuous-power behavior for the laptop (suspend/lid-close/UPS/auto-restart of services).
- Create initial application/service directory structure (SSD for app+DB+models, HDD for documents/archives/backups per section 19).
- Establish a backup strategy for both SSD (config/DB) and HDD (documents).

### Phase 2 — Ollama + Qwen benchmark

1. Install/verify Ollama.
2. Confirm NVIDIA/CUDA availability inside Ollama (940MX, 4 GB VRAM ceiling now known).
3. Benchmark CPU-only inference.
4. Benchmark GPU-assisted inference.
5. Test candidate Qwen 3.5 quantizations that fit the 4 GB VRAM / 16 GB RAM envelope.
6. Measure RAM usage, VRAM usage, tokens/sec, sustained thermal behavior.
7. Select the default local model.

### Phase 3 — Agent Gateway + Authentication

- Create project repository.
- FastAPI service.
- Username/password authentication, user database, session management.
- Model abstraction (Ollama provider + cloud provider abstraction).
- Basic MCP support.
- Audit logging.
- Authorization layer.

### Phase 4 — Web UI

- Login.
- Chat interface.
- Conversation history.
- Agent selection.
- Approval dialogs.
- Basic status/error handling.
- User-specific sessions.

### Phase 5 — News Aggregator (first end-to-end milestone)

- Source configuration (RSS/APIs per section 20).
- Ingestion, normalization, deduplication, classification.
- Local Qwen summarization, ranking.
- Local persistence, daily scheduling.
- Web presentation with source links/citations.
- Error handling.

### Phase 6 — Google Calendar
OAuth → read → create + approval → modify + approval.

### Phase 7 — Marketing / Instagram
Content generation → draft workflow → human approval → Meta/Instagram integration → publishing.

### Phase 8 — Finance / Tax
PDF/CSV ingestion → bank-export analysis → Informe de Rendimentos processing → previous-IRPF comparison → financial summaries → tax-document organization → missing-information detection → ready-to-paste reports. All locally, no bank/Gov.br authentication.

### Phase 9 — Coding
Claude Code integration, local Qwen coding, repository classification, cloud/local routing, Git integration.

### Phase 10 — Security hardening
2FA/passkeys if desired, stronger session controls, backup/recovery, additional filesystem isolation, security testing, RED-data routing tests, network hardening (including any future remote-access project), audit review.

---

## 26. Testing Strategy

- **Unit tests** for deterministic logic.
- **Integration tests:** `Agent → MCP → service`.
- **Security tests:** verify `RED data → never sent to cloud`.
- **Authentication tests:** invalid credentials rejected, sessions expire, user isolation works, unauthorized endpoints blocked.
- **Approval tests:** sensitive actions cannot execute without approval.
- **Failure tests:** Ollama unavailable, cloud model unavailable, Google API unavailable, invalid/corrupt files, network failure, database unavailable, invalid credentials, model timeout.

---

## 27. Audit and Logging

Record locally: user, timestamp, agent, model, tool, action, approval status, result, error. Avoid storing raw sensitive documents or credentials in logs.

```text
2026-08-09 09:32
User: wife
Agent: calendar
Action: create_event
Approval: approved
Result: success
```

---

## 28. Decisions

| Decision | Status |
|---|---|
| Linux laptop is central AI/agent server | **DECIDED** |
| Wife uses web interface only | **DECIDED** |
| Wife's PC: Acer Aspire 5 N20C4, i5, 8 GB, 256 GB SSD | **CONFIRMED** |
| Two users only | **DECIDED** |
| Username + password authentication, set up on first interaction | **DECIDED** |
| Ubuntu 26.04 LTS | **DECIDED** |
| Ollama | **DECIDED** |
| Qwen family for all local models | **DECIDED** |
| Kimi removed from initial scope | **DECIDED** |
| Claude Code for cloud coding | **DECIDED** |
| MCP as tool abstraction | **DECIDED** |
| RED data local-only | **DECIDED** |
| No direct bank authentication | **DECIDED** |
| No direct Gov.br authentication | **DECIDED** |
| No automatic bank transactions | **DECIDED** |
| No automatic Gov.br/Receita submission | **DECIDED** |
| Finance/tax processing from locally supplied documents | **DECIDED** |
| Ready-to-review / ready-to-paste financial/tax reports | **DECIDED** |
| Human performs official submission | **DECIDED** |
| Official APIs before browser automation | **DECIDED** |
| Existing Multi-WAN home network reused, AI server LAN-only | **CONFIRMED / DECIDED** |
| NVIDIA 940MX driver working, 4 GB VRAM | **CONFIRMED** |
| Linux SSD/HDD partition layout | **CONFIRMED** |
| News Aggregator as first functional agent | **DECIDED** |
| Qwen3-Coder for local coding | **CANDIDATE** |
| n8n | **OPTIONAL / LATER** |
| PostgreSQL | **OPTIONAL / LATER** |
| 2FA/passkeys | **LATER (Phase 10)** |
| Exact Qwen model size/quantization | **PENDING BENCHMARK (Phase 2)** |
| `/mnt/data` filesystem/permissions | **PENDING INSPECTION (Phase 1)** |
| Laptop always-on/server power behavior | **PENDING DECISION (Phase 1)** |

---

## 29. Immediate Next Steps

**Next action: Phase 1 — Linux host preparation.**

Before installing anything, run the inspection commands in section 25 (Phase 1) to resolve: `/mnt/data` filesystem/permissions, Docker status, network/IP details, and the laptop's power/server behavior.

Then: **install and benchmark Ollama + Qwen (Phase 2).** Only after measuring actual performance on the confirmed 4 GB VRAM / 16 GB RAM / 2-core CPU envelope should the final Qwen model size be chosen.

After that: **build the Agent Gateway (Phase 3) and Web UI (Phase 4), then implement the News Aggregator (Phase 5) as the first end-to-end milestone**, before adding any higher-risk integration (Calendar, Instagram, Finance).

---

## 30. Guiding Principles

1. Local-first for sensitive data.
2. No direct bank or Gov.br authentication.
3. AI assists financial/tax preparation; humans perform official submission.
4. Cloud only when there is a clear benefit.
5. The model never gets unrestricted authority.
6. Tools perform actions; models request them.
7. Human approval for consequential actions.
8. Official APIs before browser automation.
9. Qwen is the initial local-model family.
10. Claude Code is the preferred cloud coding environment.
11. Model-agnostic architecture.
12. Simple UX for the wife.
13. Deterministic software for financial calculations and validation.
14. Security boundaries must be technically enforced.
15. Start small and add agents incrementally.
16. Every major component should be replaceable.

---

## 31. Target End State

```text
                         FAMILY AI
                             |
                     Authenticated Web UI
                       /             \
                    User             Wife
                      \               /
                       +-------------+
                              |
                        Agent Gateway
                              |
              +---------------+---------------+
              |                               |
          Local Qwen                    Claude Code
              |                               |
       Sensitive/private              Allowed cloud work
              |
             MCP
              |
    +---------+---------+---------+---------+
    |         |         |         |         |
  News    Calendar  Marketing  Finance   Coding
    |         |         |         |
   RSS      Google     Meta     Local
   APIs     OAuth      API      documents
```

For the wife:
```text
Open browser → Login → "Schedule a meeting next Tuesday."
```

For personal/financial work:
```text
Upload bank exports / informes / tax documents
    |
Local analysis (Qwen)
    |
Structured summaries
    |
Ready-to-review / ready-to-paste reports
    |
Human submits officially
```

For coding:
```text
Private repository → Local Qwen
Non-sensitive repository → Claude Code
```

**The immediate, tangible milestone: build and validate the News Aggregator end-to-end on the Linux laptop before adding any higher-risk integration.**

The underlying technology should remain invisible to the users while preserving strong technical boundaries around sensitive information.
