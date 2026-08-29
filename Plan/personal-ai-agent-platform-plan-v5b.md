# Personal AI Agent Platform — Deployment Plan (v6)

**Status:** Phase 2 (Ollama + Qwen benchmark) complete — entering Phase 3 (Agent Gateway + Authentication)
**Date:** 2026-08-19
**Country:** Brazil
**Primary host:** Acer Aspire F5-573G-75A3 running Ubuntu 26.04 LTS
**Clients:** Primary Linux host (server) + wife's Windows 11 laptop (web client only)
**Users:** Two authenticated users only — user and wife

---

## Changelog since v5

Prompted by external review of v5. Two gaps were raised and both are addressed below — no new hardware testing was performed; this is planning/policy work layered onto the existing Phase 2 findings.

- **New section 6b — Concurrency & Resource Budget.** Phase 2 only benchmarked one model running alone. The real Phase 3+ architecture (Agent Gateway + Docker + Ollama + Web UI, potentially several agents) will share the same 2-core/4-thread CPU and 16 GB RAM, and the accidental model-overlap during Phase 2 benchmarking already showed RAM climbing toward ~10 GiB with swap engaged. **Decision:** the Agent Gateway will enforce single-inference-at-a-time via an explicit request queue, batch/interactive jobs will be time-separated, and any future vector DB/embeddings component (implied by the finance/tax RAG-style use cases in section 2, not yet built) must be re-benchmarked for footprint before it's added to the resource budget.
- **New section 27a — Operational Concerns.** Five previously-missing areas now have a stated default policy: resource monitoring, disaster-recovery testing, SSD capacity forecasting, log-retention, and an Ollama/model upgrade strategy. None of these require new tooling to start — they're lightweight, home-scale defaults (cron scripts, logrotate, a quarterly restore test) that can be upgraded later if needed.
- **Decisions table (section 28) and Phase 3 / Phase 10 checklists updated** to reflect the above as carried decisions rather than open gaps.

---

## Changelog since v4

Phase 2 (Ollama + Qwen benchmark) is complete. Summary — full detail in section 25 (Phase 2) and the new section 6a:

- **Ollama installed:** version `0.32.14`, official install script, systemd-managed.
- **Critical hardware/software finding:** the NVIDIA 940MX (Maxwell, compute capability 5.0) is **not supported by this Ollama build's precompiled CUDA kernels**, which only target compute capability 7.5+ (Turing and later). CUDA silently falls back to CPU-only inference — this is an Ollama-build limitation, not a driver or hardware problem (driver 580.173.02 / CUDA 13.0 is healthy).
- **Vulkan workaround found and made permanent:** the 940MX is fully usable via Ollama's Vulkan backend instead. A systemd drop-in (`CUDA_VISIBLE_DEVICES=` empty) forces Ollama to skip the broken CUDA path and pick Vulkan by default on every boot — no manual flags needed. Full GPU acceleration restored.
- **Qwen3.5 (not Qwen 2.5) is the current model family** on Ollama's registry as of this benchmarking; tags used: `qwen3.5:0.8b`, `qwen3.5:2b`, `qwen3.5:4b`, `qwen3.5:9b`.
- **Benchmarked CPU-only vs. GPU/Vulkan across four model sizes.** First GPU pass was contaminated by overlapping model instances (5-minute `OLLAMA_KEEP_ALIVE` letting a prior model stay loaded); a clean re-run (`ollama stop` + confirmed VRAM unload between models) showed GPU/Vulkan winning clearly at every size once contention was removed.
- **Thermal/throttling analysis:** peak temperature reached 78°C under sustained load. A full read of the clock-speed trace found **two distinct behaviors**: an early hot stretch held full clock (862 MHz) with no throttling, but a later sustained stretch (~74–75°C, over 2 minutes) showed the clock capped at 653 MHz (76% of max) while the GPU stayed in active P0 state — a genuine throttling signature, most likely affecting the 9b run. Not a safety concern (well under ~97°C danger zone) but a real performance cap on extended heavy use.
- **Model tier decision:** `qwen3.5:2b` as the default interactive model, `qwen3.5:4b` as an opt-in heavier-reasoning model for tax/coding tasks, `qwen3.5:9b` restricted to non-interactive/batch use only.
- Phase 2 marked complete; Phase 3 (Agent Gateway + Authentication) is next.

---

## Changelog since v3

- **`/mnt/data` fully characterized:** `ext4`, mounted `rw,nosuid,nodev,relatime` — a native Linux filesystem with no restrictions that would complicate RED-data storage. Top-level dir is `root:root` `755`; contains only `lost+found` and an existing `chrystian:chrystian`-owned folder.
- **Existing `/mnt/data/chrystian/` content identified:** this is a personal home-directory backup (~531 GB — Documents 58G, OneDrive 396G, Downloads 21G, Videos 22G, SteamGames 11G, dotfiles including `.ssh`/`.gnupg`/`.docker`), unrelated to the AI platform. **Decision:** platform storage will live in a new sibling directory, `/mnt/data/ai-platform/`, kept fully separate from this personal backup.
- **Docker confirmed installed and healthy:** `29.7.2` / Compose `v5.5.0`, service active and enabled at boot. No installation work needed for Phase 3.
- **Host firewall inspected — none active.** `ufw` is inactive; the only iptables rules present are Docker's own `FORWARD`-chain rules, with `INPUT`/`OUTPUT` unrestricted. **Decision:** enable `ufw` as defense-in-depth (the router already blocks WAN exposure), default-deny incoming, allow SSH from the LAN subnet only for now. Note for later: Docker can bypass `ufw` rules for published container ports, so this will need revisiting once Phase 3/4 services publish ports.
- **Power/server behavior decided:** laptop stays always-on — suspend/sleep on lid-close is disabled (`systemd-logind`), sleep/suspend/hibernate targets masked.
- **Network connection decided:** stays on Wi-Fi (no switch to the available wired `enp4s0f1`); Wi-Fi power-saving is disabled via NetworkManager to reduce drop/reconnect risk now that the laptop is a server.
- **Static LAN IP decided:** `192.168.0.112` (current DHCP-assigned address) will be converted to a DHCP reservation on the TP-Link ER605.
- **Backup strategy — default proposed, destination still open (non-blocking):** periodic versioned backups (e.g. `restic`/`borg`) of the SSD config/DB and the new `/mnt/data/ai-platform/backups` tree; exact destination (external drive vs. secondary NAS/cloud) still undecided and doesn't block Phase 2/3.
- Phase 1 marked complete; Phase 2 (Ollama + Qwen benchmark) is next.

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

### CONFIRMED (Phase 2): model tier decision

Benchmarking (section 6a) settled this into a three-tier policy rather than a single model:

| Tier | Model | Role |
|---|---|---|
| Default | `qwen3.5:2b` | Everyday interactive chat/agent use — fast (~11.5 tok/s GPU) and clearly above the ~10 tok/s interactive-usability threshold. |
| Heavier reasoning | `qwen3.5:4b` | Opt-in for tax-document analysis and coding help where a few extra seconds is acceptable (~8.1 tok/s GPU). |
| Batch-only | `qwen3.5:9b` | Restricted to non-interactive/background jobs (e.g. overnight news summarization) — too slow for real-time chat (~3.6 tok/s GPU) and the size most exposed to sustained-load thermal throttling. |

All inference runs via Ollama's **Vulkan backend**, not CUDA (see section 6a for why).

---

## 6a. Ollama + GPU Setup — Phase 2 findings (DECIDED)

### Ollama installation

```bash
curl -fsSL https://ollama.com/install.sh | sh
```
Installed as systemd service `ollama.service`. Confirmed version: `0.32.14`.

### Critical finding: CUDA does not work on the 940MX with this Ollama build

The 940MX is a Maxwell-generation GPU, compute capability 5.0. Ollama `0.32.14`'s precompiled CUDA kernels only cover compute capability 7.5 and above (Turing+). On startup, Ollama's CUDA discovery finds the GPU but explicitly skips it:

```
skipping CUDA device — compute capability not in compiled architectures
device="NVIDIA GeForce 940MX" cc=500 archs="[750 800 860 870 890 900 1000 1030 1100 1200 1210]"
```

Without any further configuration, Ollama silently falls back to **CPU-only inference** — no error is raised, so this is easy to miss. Confirmed via `nvidia-smi` showing 0% GPU utilization and no `ollama`/`llama-server` process during a normal run.

### Fix: force the Vulkan backend

Ollama also has a Vulkan inference backend, which is far less restrictive about GPU age. `vulkaninfo --summary` confirmed the 940MX is fully visible via Vulkan (driver `580.173.02`, `DRIVER_ID_NVIDIA_PROPRIETARY`). The problem was that Ollama's device-discovery claims the 940MX for the (broken) CUDA path first and never falls back to offering it via Vulkan — hiding the GPU from CUDA entirely was required to get Ollama to pick Vulkan instead.

**Permanent fix (applied):**
```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/vulkan-gpu.conf > /dev/null <<'EOF'
[Service]
Environment="CUDA_VISIBLE_DEVICES="
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

Confirmed working — Ollama now logs, on every normal start, without any manual flags:
```
inference compute id=0 filter_id=1 library=Vulkan compute=0.0 name=Vulkan1 description="NVIDIA GeForce 940MX" ... total="4.2 GiB" available="4.1 GiB"
```

### Benchmark method

`ollama run <model> --verbose` reports load time, prompt-eval rate, and eval rate (tokens/sec) directly. Four Qwen3.5 sizes were tested: `0.8b`, `2b`, `4b`, `9b`, each with the same prompt ("Summarize in 3 sentences: what is local-first software?").

**First GPU pass was invalid — overlapping instances.** `OLLAMA_KEEP_ALIVE` defaults to 5 minutes, so running four models back-to-back left prior models still resident; `nvidia-smi` showed two simultaneous `llama-server` processes sharing the GPU during the 4b/9b portion. This depressed their throughput artificially.

**Clean re-run** (`ollama stop <model>` + `sleep 3` + confirmed VRAM back to baseline before starting the next model) gave the trustworthy numbers below.

### Results (tokens/sec, eval rate)

| Model | CPU-only | GPU/Vulkan (clean) |
|---|---|---|
| `qwen3.5:0.8b` | 16.88 | 23.54 |
| `qwen3.5:2b` | 8.87 | 11.50 |
| `qwen3.5:4b` | 5.28 | 8.10 |
| `qwen3.5:9b` | *(not tested — CPU too slow to be relevant)* | 3.59 |

GPU/Vulkan wins clearly at every size once measured cleanly (2b: +30%, 4b: +53% over CPU). CPU inference used only 2 of the 4 logical threads on the i7-7500U (`n_threads = 2` in Ollama's default config) — a possible future tuning lever, not adjusted in this pass.

### VRAM and RAM

Peak VRAM across all models: ~3.4 GiB of 4.0 GiB (~82%) — comfortable headroom, no CPU offload forced. System RAM did climb toward ~10 GiB of 14 GiB (with ~1.3 GiB swap) during the *contended* GPU test specifically because of the overlapping-instance issue above — expected to be much lower under normal single-model-at-a-time operation.

### Thermal behavior

Peak GPU temperature: 78°C, monitored via `nvidia-smi --query-gpu=timestamp,temperature.gpu,clocks.sm,clocks.max.sm,pstate`. Two distinct patterns found in the clock trace:
- An earlier sustained-load stretch held the full 862 MHz clock straight through 78°C — no throttling.
- A later sustained stretch (~74–75°C for 2+ minutes, coinciding with the `9b` run) showed the clock capped at **653 MHz (76% of max) while in active P0 state** — a genuine throttling signature, distinct from the harmless idle power-state dips (135–233 MHz at P8) seen between model loads.

Neither reading approaches the ~97°C danger zone for this GPU generation, so this is a **performance consideration, not a safety concern** — but it reinforces keeping `9b` out of sustained interactive use, and is worth a periodic recheck once the laptop has been running as an always-on server for a longer stretch (see section 19 backup/maintenance follow-ups).

---

## 6b. Concurrency & Resource Budget (NEW)

### Why this section exists

Section 6a's benchmarks are all **single-model, nothing-else-running** numbers. They're the right numbers for choosing a model tier, but they don't describe what the machine will actually be doing from Phase 3 onward: the Agent Gateway (FastAPI), Docker, Ollama plus one loaded model, the Web UI, the local database, and — eventually — several agents (News, Calendar, Marketing, Finance, Coding) that could in principle be invoked close together. The 2-core/4-thread i7-7500U is the tighter constraint here, tighter than the 4 GB VRAM ceiling, because unlike VRAM it's shared by *everything* on the host, not just Ollama.

There's already direct empirical evidence this matters: the first (invalid) Phase 2 GPU pass, where `OLLAMA_KEEP_ALIVE` left a prior model resident while the next one loaded, pushed system RAM to ~10 GiB of 14 GiB and engaged ~1.3 GiB of swap — from just *two* overlapping model instances, with nothing else running. That was an accident during benchmarking; in production, overlap can happen routinely unless it's explicitly prevented (e.g. the wife asks a question while the News Aggregator's scheduled batch job is running).

### Resource budget (rough, to be refined with real monitoring — see 27a)

| Component | Footprint | Notes |
|---|---|---|
| OS + background services | ~1–2 GB RAM, low CPU | Baseline, already running today |
| Docker + Agent Gateway + Web UI + DB | ~1–2 GB RAM, low-moderate CPU | Always resident once Phase 3/4 ship |
| One loaded Ollama model (2b/4b tier) | 1.5–3.5 GB VRAM, modest RAM, most of the CPU/GPU budget while generating | Should be the only *inference* workload at a time |
| `9b` batch jobs | Same VRAM range but slower, most exposed to GPU throttling (section 6a) | Push to off-hours, not concurrent with interactive use |
| Future vector DB / embeddings | **Unknown — not yet built** | Must be benchmarked before being added to this table |

At 16 GB total RAM, this leaves comfortable headroom for one thing running at a time, but not much slack for several agents genuinely running in parallel — especially once a vector DB or embedding step is added for finance/tax document retrieval, which section 2's objectives imply but which doesn't exist yet in this plan.

### DECIDED: concurrency policy

- **Single-inference-at-a-time, enforced at the Agent Gateway**, not left to Ollama's own defaults. The Gateway will serialize model calls through an explicit request queue/lock, regardless of `OLLAMA_KEEP_ALIVE` or `OLLAMA_MAX_LOADED_MODELS` behavior — Phase 2 already showed relying on Ollama's defaults alone isn't safe on this hardware.
- **`OLLAMA_MAX_LOADED_MODELS=1`** set explicitly (systemd override, alongside the existing Vulkan override from section 6a) rather than relying on the default keep-alive window.
- **Batch jobs (`9b` tier, overnight News summarization) are time-separated from interactive use** — scheduled during low-usage hours, not run concurrently with anything else.
- **Any future vector DB/embeddings component must be benchmarked for RAM/CPU footprint before adoption**, and preference should go to an embedded/in-process store (e.g. an SQLite-based vector extension) over a separate always-on server process, to minimize permanent background footprint on this hardware.
- **This policy is provisional, not permanent.** Once Phase 3–5 are live and real usage/resource data exists (section 27a), it can be relaxed if the data supports it — but it's the safe default until then.

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

## 19. Storage Strategy — layout and inspection confirmed (Phase 1)

```text
SSD (/dev/sda2, 222.5 GB, mounted at /)
|
+-- OS
+-- agent application
+-- database
+-- active Ollama models
+-- logs

HDD (/dev/sdb1, 931.5 GB, mounted at /mnt/data, ext4, rw,nosuid,nodev,relatime)
|
+-- chrystian/          existing personal home-directory backup (~531 GB), UNTOUCHED by the platform
|
+-- ai-platform/        NEW — dedicated tree for this project
    +-- documents/       personal documents
    +-- financial/       financial documents
    +-- tax/             tax documents
    +-- archives/        local archives
    +-- backups/         backups
    +-- datasets/        large datasets
```

**Confirmed via Phase 1 inspection:**
- Filesystem: `ext4`, mount options `rw,nosuid,nodev,relatime` — no restrictions that would complicate ownership/permissions for RED-classified data.
- `/mnt/data` top-level: `root:root`, `755`.
- Existing contents: only `lost+found` and a `chrystian:chrystian`-owned folder holding a full personal home-directory backup (Documents 58G, OneDrive 396G, Downloads 21G, Videos 22G, SteamGames 11G, dotfiles). This predates the project and is unrelated to it.

**Decision:** rather than nesting platform data inside the existing personal-backup folder, create a new sibling directory `/mnt/data/ai-platform/` owned by `chrystian:chrystian`, `750`, holding the six subdirectories above. This keeps the platform's storage footprint fully separated from the personal backup.

Setup commands (run on the host):
```bash
sudo mkdir -p /mnt/data/ai-platform/{documents,financial,tax,archives,backups,datasets}
sudo chown -R chrystian:chrystian /mnt/data/ai-platform
sudo chmod -R 750 /mnt/data/ai-platform
```

**Backup strategy (default proposed, destination still open — non-blocking for Phase 2/3):** periodic versioned backups (e.g. `restic` or `borg`) covering the SSD-side config/DB and the `/mnt/data/ai-platform/` tree, written into `ai-platform/backups/` and — once decided — mirrored to an external drive or secondary location. The exact backup destination is the one open item carried into later hardening work; it does not block Ollama installation or agent development.

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

**Server connection — decided (Phase 1):** the server stays on Wi-Fi (`wlp3s0`, currently `192.168.0.112/24` via DHCP). The available wired NIC (`enp4s0f1`) is not being used. To reduce the risk of drops/slow reconnects now that this interface carries a server role, Wi-Fi power-saving is disabled:

```bash
sudo mkdir -p /etc/NetworkManager/conf.d
sudo tee /etc/NetworkManager/conf.d/wifi-powersave-off.conf > /dev/null <<'EOF'
[connection]
wifi.powersave = 2
EOF
sudo systemctl restart NetworkManager
```

**Static IP — decided (Phase 1):** `192.168.0.112` (the current DHCP-assigned address) is reserved as a DHCP reservation on the TP-Link ER605, keyed to `wlp3s0`'s MAC address (configured on the router's admin UI, not on the host).

**Host firewall — decided (Phase 1):** `ufw` was found inactive; the only iptables rules present were Docker's own `FORWARD`-chain rules. As defense-in-depth alongside the router's LAN-only posture:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from 192.168.0.0/24 to any port 22 proto tcp
sudo ufw enable
sudo ufw status verbose
```

Additional ports (for the web UI, etc.) will be opened — LAN-only — as those services come online in Phase 3/4. Note: Docker manipulates iptables directly and can bypass `ufw` rules for published container ports, so container port publishing will need explicit review when it starts.

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

### Phase 0 — Requirements and hardware audit — **complete**

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

Non-blocking items remaining for later phases:
- Exact Google Calendar / Instagram API requirements (will be defined at Phase 6/7).
- Exact finance/tax document workflows (Phase 8).
- Exact backup destination (external drive vs. secondary location) — proposed method decided, destination still open.

### Phase 1 — Linux host preparation — **complete**

Inspection commands run and results captured:

```bash
# Storage
findmnt /mnt/data                    # ext4, rw,nosuid,nodev,relatime
df -h / /mnt/data                    # / 149G avail (29% used); /mnt/data 339G avail (62% used)
ls -ld /mnt/data                     # root:root, 755
sudo ls -la /mnt/data | head -50     # lost+found + existing chrystian/ folder
sudo ufw status verbose              # inactive
sudo iptables -L -n -v               # only Docker's own FORWARD-chain rules present
ls -la /mnt/data/chrystian           # personal home-dir backup, ~531 GB total
du -sh /mnt/data/chrystian/*

# Docker
docker --version                     # 29.7.2
docker compose version               # v5.5.0
systemctl status docker --no-pager   # active, enabled, running 6+ days

# Network
ip -br addr                          # wlp3s0 UP, 192.168.0.112/24 (DHCP); enp4s0f1 present but DOWN
ip route                             # default via 192.168.0.1 dev wlp3s0
```

Tasks completed:
- [x] Inspected `/mnt/data` — ext4, no restrictive mount options, safe for RED-classified data. Existing `chrystian/` folder identified as an unrelated personal home-directory backup.
- [x] Reviewed Docker — already installed and healthy, no action needed.
- [x] Firewall decision made — `ufw` to be enabled, default-deny incoming, LAN-only SSH allowed (commands in section 24).
- [x] Static LAN IP decided — `192.168.0.112`, to be reserved on the ER605 (section 24).
- [x] Power behavior decided — always-on, lid-close suspend disabled (commands below), Wi-Fi power-saving disabled (section 24).
- [x] Directory structure defined — new `/mnt/data/ai-platform/` tree, kept separate from the personal backup (section 19, with `mkdir`/`chown`/`chmod` commands).
- [x] Backup strategy — method proposed (`restic`/`borg`, versioned), destination still open and tracked as a non-blocking follow-up (section 19).

Power/lid-close commands (host, not yet run — to execute before leaving the laptop unattended as a server):
```bash
sudo mkdir -p /etc/systemd/logind.conf.d
sudo tee /etc/systemd/logind.conf.d/no-lid-suspend.conf > /dev/null <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
EOF
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
sudo systemctl restart systemd-logind   # note: this can drop the current session — safer to reboot afterward instead
```

### Phase 2 — Ollama + Qwen benchmark — **complete**

Tasks completed:
- [x] Ollama installed and verified (`0.32.14`, systemd-managed).
- [x] GPU/CUDA availability investigated — **found CUDA non-functional on the 940MX with this Ollama build** (Maxwell, compute capability 5.0, below the compiled minimum of 7.5). Root-caused, not just worked around.
- [x] Vulkan identified as a working alternative GPU backend for this hardware; permanent systemd override applied to force Ollama onto Vulkan by default (full commands and explanation in section 6a).
- [x] CPU-only inference benchmarked across `qwen3.5:0.8b/2b/4b`.
- [x] GPU/Vulkan inference benchmarked across `qwen3.5:0.8b/2b/4b/9b` — first pass invalidated by overlapping model instances, re-run cleanly with confirmed VRAM unload between models.
- [x] RAM, VRAM, and sustained thermal/clock behavior measured and analyzed (peak 78°C, one genuine throttling stretch identified at ~74–75°C/653 MHz during the `9b` run, no safety concern).
- [x] Default local model tier decided: `qwen3.5:2b` default, `qwen3.5:4b` opt-in heavier reasoning, `qwen3.5:9b` batch-only (section 6/6a).

Full benchmark data, the CUDA/Vulkan root cause, and the thermal analysis are in section 6a.

### Phase 3 — Agent Gateway + Authentication — **next**

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

## 27a. Operational Concerns (NEW)

Five areas had no stated policy in v5. None need heavy tooling to start — the defaults below are sized for a two-user home platform and can be upgraded later if actual usage justifies it.

### Resource monitoring

**DECIDED (default):** a lightweight cron job samples `free`, `df`, and `nvidia-smi` (CPU/RAM/VRAM/disk) every few minutes and appends to a local, rotated log under `/mnt/data/ai-platform/`. No automated alerting initially — there's no notification channel yet (section 22/Instagram integration could later double as one). The human reviews the log periodically, especially after enabling a new agent. A Prometheus/Grafana-style stack is a reasonable later upgrade if the cron log stops being enough, but isn't justified for two users today.

### Disaster-recovery testing

**DECIDED (default):** a **quarterly restore test** — restore the `restic`/`borg` backup (method decided in section 19; destination still open) to a scratch location and verify the platform DB and `ai-platform/` tree are intact and readable. This is added as a recurring Phase 10 task, not a one-time checkbox — an untested backup is not a verified recovery path.

### SSD capacity forecasting

**DECIDED (default):** SSD usage (`df -h /`, currently 29% used per the Phase 1 inspection) is checked monthly. **Soft threshold: 80% used** triggers action — pruning old Docker images, moving logs/archives to the HDD (`/mnt/data`), or removing unused model weights. Active model weights are individually small (single-digit GB), so the more likely long-run growth driver is Docker images, the database, and logs — which is also why the log-retention policy below matters.

### Log retention policy

**DECIDED (default):** application and audit logs (section 27) are rotated on a size/time basis (e.g. `logrotate`, capped and compressed, on the order of 90 days for audit logs) rather than left to grow unbounded. This is a low-volume two-user system, so the caps can be generous — the point is having a cap at all, not tight retention. Reaffirms the existing rule that raw sensitive documents and credentials are never written to logs.

### Ollama / model upgrade strategy

**DECIDED (default):** the installed Ollama version is **pinned**, not auto-updated — Phase 2 showed how much behavior (CUDA fallback, the Vulkan override) is tied to a specific build. Before any manual Ollama upgrade: (1) the systemd Vulkan override (section 6a) and `OLLAMA_MAX_LOADED_MODELS` setting (section 6b) are re-applied and re-verified, since an upgrade could reset or invalidate them; (2) a quick regression pass of the Phase 2 benchmark (one prompt per model tier, GPU/Vulkan path) confirms the new build still picks Vulkan and produces comparable throughput before it's trusted for daily use. This runbook lives alongside the systemd override files so it isn't lost.

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
| `/mnt/data` filesystem/permissions: ext4, safe for RED data | **CONFIRMED** |
| Existing `/mnt/data/chrystian/` = unrelated personal backup, left untouched | **CONFIRMED** |
| Platform storage lives in new `/mnt/data/ai-platform/` tree | **DECIDED** |
| Docker already installed and healthy | **CONFIRMED** |
| Host firewall: `ufw` enabled, LAN-only SSH, default-deny incoming | **DECIDED** |
| Static LAN IP `192.168.0.112` (DHCP reservation on ER605) | **DECIDED** |
| Laptop always-on, lid-close suspend disabled | **DECIDED** |
| Server stays on Wi-Fi (no switch to wired), Wi-Fi power-save disabled | **DECIDED** |
| Backup method: versioned (`restic`/`borg`); destination | **METHOD DECIDED / DESTINATION OPEN** |
| Ollama installed (`0.32.14`), systemd-managed | **CONFIRMED** |
| CUDA non-functional on 940MX with this Ollama build (root cause identified) | **CONFIRMED** |
| Vulkan backend forced permanently via systemd override — full GPU acceleration working | **DECIDED / CONFIRMED** |
| Default local model: `qwen3.5:2b` | **DECIDED** |
| Heavier-reasoning opt-in model: `qwen3.5:4b` | **DECIDED** |
| Batch-only model: `qwen3.5:9b` | **DECIDED** |
| GPU thermal behavior under sustained load: safe, but throttles (~76% clock) past ~2 min continuous heavy use | **CONFIRMED / MONITOR** |
| Agent Gateway enforces single-inference-at-a-time (explicit queue, not left to Ollama defaults) | **DECIDED** |
| `OLLAMA_MAX_LOADED_MODELS=1` set via systemd override | **DECIDED** |
| Batch (`9b`) jobs time-separated from interactive use | **DECIDED** |
| Future vector DB/embeddings: footprint must be benchmarked before adoption; prefer embedded store over separate server process | **NOTED / LATER** |
| Resource monitoring: cron-based CPU/RAM/VRAM/disk logging, no automated alerting yet | **DECIDED (default)** |
| Disaster-recovery: quarterly restore test of backups | **DECIDED (default)** |
| SSD capacity forecasting: monthly check, 80% used soft threshold | **DECIDED (default)** |
| Log retention: rotated/capped (audit logs ~90 days), no unbounded growth | **DECIDED (default)** |
| Ollama upgrade strategy: version pinned, override + benchmark regression check before any upgrade | **DECIDED (default)** |

---

## 29. Immediate Next Steps

**Next action: Phase 3 — Agent Gateway + Authentication.**

Phase 1 and Phase 2 are both complete. The host is prepared (storage, firewall, static IP, power behavior, network — section 19/24/25), and Ollama is installed with a confirmed, permanent GPU-acceleration fix (Vulkan via systemd override) and a benchmarked three-tier model policy (`qwen3.5:2b` default / `4b` opt-in / `9b` batch-only — section 6a).

Now: **build the Agent Gateway (Phase 3)** — FastAPI service, username/password authentication, model abstraction wired to the Ollama Vulkan setup and the new model tiers, basic MCP support, audit logging, authorization layer.

After that: **Web UI (Phase 4), then the News Aggregator (Phase 5) as the first end-to-end milestone**, before adding any higher-risk integration (Calendar, Instagram, Finance).

Non-blocking follow-up carried forward: periodically recheck GPU thermal behavior under longer sustained loads once the platform is in regular daily use, given the throttling observed in Phase 2 benchmarking (section 6a).

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
