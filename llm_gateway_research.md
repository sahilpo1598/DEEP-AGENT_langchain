# LLM Gateways — Web Research Report

*Compiled from public web sources. Research snapshot; vendor features and pricing change frequently — verify before procurement.*

---

## 1. What Is an LLM Gateway?

An **LLM gateway** (also called an **AI gateway**) is a middleware/proxy layer that sits between your application and one or more LLM providers (OpenAI, Anthropic, Google, Mistral, Cohere, self-hosted models, etc.). It exposes a **single unified API** — most commonly the OpenAI chat-completions format, which has become the de-facto standard — and routes requests to whichever provider/model you configure.

Instead of writing and maintaining separate integrations, auth, retry, and billing logic for every provider, application code talks to the gateway and changes only a model string (or a routing policy) to switch providers.

Analogy used across sources: a **translator + traffic controller** for AI models.

### Where it fits in the stack
The industry now distinguishes three related gateway layers (defense-in-depth, not redundant):

| Layer | Governs | Example concerns |
|---|---|---|
| **API Gateway** | Traditional backend HTTP traffic | Auth, quotas, routing of general APIs |
| **LLM / AI Gateway** | Calls to the model ("the thinking step") | Provider routing, failover, caching, cost, guardrails |
| **MCP / Agent Gateway** | What the model *does* after deciding ("the acting step") | Tool/agent access, OAuth, session, audit of actions |

An **agent gateway** additionally orchestrates multi-step agent workflows and agent-to-agent (A2A) communication. **MCP gateway** (Model Context Protocol, open-sourced by Anthropic) centralizes agent-to-tool connectivity and credentials. One source's summary: *"One controls which brain the agent uses; the other controls which tools it can touch."*

---

## 2. Core Capabilities / Why Teams Adopt One

Reasons (repeatedly cited): call more than one provider, spend meaningfully on tokens, need governance/compliance, or scale past a single-team pilot.

**Traffic & reliability**
- Unified, OpenAI-compatible API across 100+ providers
- **Routing** — by model, cost, latency, availability, or workload type; conditional routing, traffic splitting, A/B tests
- **Fallbacks / retries** — automatic switch on outage, error, or rate limit
- **Load balancing** — weighted / least-latency across provider endpoints

**Cost & performance**
- **Caching** — exact-match and **semantic caching** (reuse responses for similar prompts; reportedly 40–60% savings on repetitive workloads)
- **Rate limiting & budgets** — per user/team/key/app; prevent runaway spend
- **Cost tracking / spend attribution** — by key, user, team, org, feature; tag-based tracking
- **Virtual keys** — scoped access tokens that don't expose the real provider keys

**Governance & security** (see §5)
- Access control (RBAC, SSO/SCIM, OIDC/JWT)
- Guardrails: prompt-injection & jailbreak detection, PII/secret redaction, content moderation
- Immutable audit logs (SOC 2, GDPR, HIPAA, ISO 27001 evidence)

**Observability**
- Request/response logging, traces, token usage, latency, error rates, Prometheus/OpenTelemetry metrics
- Routing visibility (which backend was hit and why)

**Ops benefits**
- Centralize provider credentials & key rotation; secret-manager integration
- Add models on "day-0" without app changes (Netflix reportedly gets new model access "usually within a day of release")
- Decouple app logic from provider-specific SDKs — avoids lock-in

---

## 3. Architecture & Deployment Patterns

- **Managed / SaaS control plane** — fastest to adopt; no infra to run (Portkey, OpenRouter, Cloudflare, Vercel, TrueFoundry SaaS).
- **Self-hosted open-source proxy** — full control, zero per-request markup, but you operate Postgres/Redis, secrets, upgrades (LiteLLM, Kong, Bifrost, theopenco/llmgateway).
- **Bring-your-own-cloud / on-prem / air-gapped** — for regulated or data-residency-sensitive teams.
- **Edge-native** — Cloudflare Workers/edge stack.

Common production concerns each gateway centralizes: request standardization, routing, caching, retries/fallback, budget enforcement, compliance logging — so "none of those concerns leak into application code."

**Build vs. buy guidance:** start with open-source (LiteLLM) or a managed service; move to self-hosting vs. managed primarily on delivery model preference and scale.

---

## 4. Vendor Landscape (with prices where public)

Prices are as published by vendors/roundups and drift quickly — treat as approximate.

| Vendor | Model | Type | Notable strengths | Headline pricing |
|---|---|---|---|---|
| **LiteLLM** (BerriAI) | Open-source (MIT core) + Enterprise | Self-hosted proxy / Python SDK | De-facto OSS standard; 100+ (→140+) providers, ~53K GitHub stars, 240M+ Docker pulls; virtual keys, budgets, fallbacks, guardrails, load balancing, logging | OSS **free**; Enterprise Basic ~**$250/mo**, Enterprise Premium ~**$30K/yr** |
| **Portkey** | Open-source gateway + managed platform | Hybrid | Governance & observability focus; guardrails, PII redaction, jailbreak detection, semantic caching, audit trails; "control plane for AI" | Free tier (~10K logs/mo) → **~$49/mo**; enterprise tiers to ~$5–10K/mo |
| **Kong AI Gateway** | AI plugins on Kong API Gateway (Apache-2.0 core) | Self-hosted/enterprise | Fits teams already on Kong; plugin ecosystem, rate limiting, RAG pipelines, PII; benchmarked as fastest/lowest-latency in Kong's own tests | Enterprise-gated advanced features; Kong's benchmark: **228% faster than Portkey, 859% faster than LiteLLM** (12 CPU test) |
| **Cloudflare AI Gateway** | Managed, edge-native | SaaS | Core features **free**: analytics, exact-match caching, rate limiting; 24 native providers; Workers AI integration (50+ models); DLP free | Core **free**; Unified Billing +5% on credits; Workers Paid for larger log limits; Workers AI $0.011/1K Neurons |
| **OpenRouter** | Managed marketplace/router | SaaS | Broadest single-endpoint access, unified credit billing, easy exploration | ~**5.5%** on credit purchases (+$0.80 min on small transactions) |
| **TrueFoundry** | Enterprise AI platform + gateway | Managed/self-hosted/VPC | 1,000+ models, RBAC/SSO, audit logs, MCP gateway, SOC2/HIPAA/GDPR/ISO 27001; bring-your-own-cloud | Free dev tier; paid from **~$499/mo** |
| **Vercel AI Gateway** | Managed, Vercel-native | SaaS | Tight AI SDK integration; no token markup + BYOK; auto fallback | $5/mo credits; provider list rates, no markup |
| **Bifrost** | Open-source, Go, single binary | Self-hosted | Very low overhead (~11 µs/request at 5K RPS); semantic caching, virtual keys, native MCP | Free to self-host |
| **Requesty** | Managed | SaaS | Flat 5% markup, EU routing, guardrails, 160+ models | ~5% markup |
| **Others** | | | Solo.io Agent Gateway, Gravitee AI/Agent Gateway, Traefik, WSO2, Merge Gateway, NanoGPT, OpenAI-compatible: theopenco/llmgateway | varies |

**Choosing (rule-of-thumb from multiple sources):**
- Self-host, open-source ownership → **LiteLLM** (or Bifrost for Go/low-latency)
- Managed governance + guardrails + dashboards → **Portkey** / **TrueFoundry**
- Already on Kong → **Kong AI Gateway**
- Already on Cloudflare/Workers → **Cloudflare AI Gateway**
- Broad exploration & simplest unified billing → **OpenRouter**
- Agent/tool governance → add an **MCP/agent gateway** (Solo.io, Gravitee, or LiteLLM's built-in MCP)

---

## 5. Security, Governance & Compliance

The shift from **metadata-based** API security to **content-level** inspection is why standard API gateways fall short for LLMs — a prompt-injection payload rides through metadata checks untouched, and responses can leak data a network proxy was never built to inspect.

**Key gateway-layer controls:**
- **Prompt-injection defense** (maps to OWASP LLM01) — direct and indirect (e.g., malicious instructions in retrieved RAG content)
- **PII/PHI detection & redaction**, secrets detection, content moderation, jailbreak detection
- **Authentication & authorization** — OAuth 2.1, OIDC/JWT, RBAC, SSO/SCIM; scoped/virtual keys; vault-managed secrets & rotation
- **Immutable audit logging** and retention to satisfy SOC 2 Type II, GDPR, HIPAA, ISO 27001
- **Compliance-aware routing** — pin sensitive/regulated workloads to compliant providers (e.g., **EU data residency / Frankfurt routing**), fail-closed provider policy enforcement ("no training on prompts," "no prompt logging")
- Data Loss Prevention (DLP) scanning

**Caveats sources emphasize:** guardrail classifiers are **defense-in-depth, not proofs** — they can miss attacks or block legitimate input. Application-level authorization must still be enforced outside the gateway; data-handling depends on configuration; and you must define retention, residency, consent, and provider-processing rules separately.

---

## 6. Market & Adoption

- **LiteLLM** is the most widely deployed open-source gateway: **~53K+ GitHub stars** (up from ~12–40K in older snapshots — rapid growth), **1,000+ contributors**, **240M+ Docker pulls**, **1B+ requests served**; production users cited include **Stripe, Netflix, Adobe, Google ADK, Rocket Money, Samsara, Lemonade**.
- **Enterprise AI Gateway market** projections (multiple analysts, differing scopes):
  - SNS Insider: US **$0.32B (2025) → $3.52B (2035)**, ~**27% CAGR**; global **$11.32B by 2035**; large enterprises ~78.6% share (2025), SMes fastest-growing (~33.8% CAGR); APAC highest regional CAGR (~26.3%)
  - 360iResearch: global **$4.31B (2025) → $11.86B (2032)**, ~15.5% CAGR
  - Valuates: global **$3.9B (2024) → $9.8B (2031)**, ~14.3% CAGR
- Growth drivers named: generative-AI adoption, **AI agents**, cloud-native AI apps, **multi-model strategies**, and demand for secure AI governance/compliance.
- Notable consolidation: one gateway vendor's roadmap reportedly quieted after a May 2026 acquisition — a reminder to check project ownership/maintenance health when picking OSS.

---

## 7. Key Takeaways

1. **The gateway is becoming standard AI infrastructure** — the "hard cross-cutting concerns" (routing, caching, resilience, governance, spend) live there, not in app code.
2. **OpenAI's API format is the de-facto interop standard**, which makes gateways effectively drop-in (often a one-line `base_url` change).
3. **The core decision is delivery model**: self-hosted OSS (control, no markup, you operate it) vs. managed (governance/observability bundled, vendor in the request path).
4. **Differentiation is shifting from routing to governance** — guardrails, PII, audit, compliance routing, and MCP/agent governance are where vendors now compete.
5. **Security is content-level and defense-in-depth** — no gateway makes an app automatically secure or compliant.
6. **Gateways are multiplying into layers** (API + LLM + MCP/agent) — mature agent platforms run all three.
7. **Cost models vary**: free OSS + infra cost, flat % markup (OpenRouter ~5.5%, Requesty ~5%, Cloudflare ~5% on credits), per-log/subscription (Portkey), or usage-sized enterprise contracts (LiteLLM Enterprise).

---

## Sources

- TrueFoundry — What Is an LLM Gateway / Guide to AI Gateways 2026 / observability / LiteLLM pricing & enterprise
- Portkey — What is an LLM Gateway; Best AI Gateway Solutions
- Braintrust — 6 best LLM gateways for developers
- OpenRouter Blog — LLM Gateway: What It Is and How to Choose One
- LLM Gateway (llmgateway.io / theopenco) — product, guardrails, SOC 2 Type II
- Kong — AI Gateway Benchmark (Kong vs Portkey vs LiteLLM); GitHub benchmark repo; Kong AI Gateway launch
- API7.ai — Kong AI Gateway vs LiteLLM; AI Gateway security
- Spheron — AI Gateway Setup 2026 (LiteLLM, Portkey, Kong)
- Contabo — LiteLLM vs Portkey, Kong, Cloudflare
- Orq.ai — 9 Best LLM Gateways; GetMaxim — architecture/features, Bifrost, gateway security
- Virtido — AI Gateway Patterns; DigitalApplied — LLM Gateway Architecture 2026; AppScale — Enterprise LLM Gateway Architecture
- LiteLLM (litellm.ai, GitHub BerriAI/litellm, docs) — features, pricing, adopters
- Medium (Adnan Masood) — Using LiteLLM as an Open-Source LLM Proxy
- Cloudflare — AI Gateway docs & pricing; Workers AI pricing
- Vercel — AI Gateway vs Cloudflare AI Gateway
- Lyzr — feature comparison; TECHSY — 10 tools ranked; Respan — LLM gateways & LiteLLM market map
- Requesty — routing platforms compared; security/compliance checklist
- Composio — MCP Gateway vs LLM Gateway vs API Gateway; Cequence — LLM Proxy vs MCP Gateway; Traefik — API vs AI vs MCP Gateway; Gravitee — AI Gateway vs Agent Gateway; Solo.io — MCP/Agent Gateway
- SNS Insider / 360iResearch / Valuates (via GlobeNewswire, PR Newswire, Yahoo) — market sizing
