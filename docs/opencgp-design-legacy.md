# OpenCGP · Early System Design (Archived)

> Version: v1.0
> Date: 2026-11-02
> Status: Requirements confirmed, implementation details pending (next step: M0 minimal implementation plan)

---

## 0. About this document

This document records the complete system design of the "AI Series Studio" project and is the single source of truth for development, module breakdown, database modeling, and deployment planning. All confirmed decisions are listed in Chapter 9, Decision Log.

---

## 1. Project overview

### 1.1 Positioning

> In one sentence: **an independent web workbench that is conversation-centric and treats the series as a living document — the AI acts as author and teaching assistant, the human makes the calls at key moments, and the output is a coherent illustrated knowledge series.**

Three defining traits:

| Dimension | Conventional generator (e.g. vibe-blog) | This project |
|---|---|---|
| Way of working | One-shot pipeline | **Continuous conversation + a living document that can be revised repeatedly** |
| Role of the human | Just clicks "confirm" | **The AI asks questions proactively; the human can follow up, pause, or amend at any time** |
| Output | One article | **A series with structure, narrative flow, and room to grow** |

### 1.2 How it fundamentally differs from vibe-blog

This project **is not a clone of vibe-blog**. The clearest evidence of differentiation is its unique capabilities:

1. **Ask & Amend**: after generation you can keep asking about any unit/passage/figure/code block, patch it locally, and fold the result back in — with diff and rollback. vibe-blog has none of this.
2. **An author that asks questions**: the AI stops at key forks and asks the user instead of generating blindly from start to finish.
3. **A living document rather than a task artifact**: series, glossary, learning path, and conversation threads are first-class objects that can be edited explicitly, not intermediate states of a pipeline.

### 1.3 Core value proposition

- Turn "a coherent knowledge series" from "requires a professional author + months" into "a conversation + continuous refinement".
- The user is both a consumer of the series and a co-creator and reviewer of it.

---

## 2. Product shape

### 2.1 Two modes: SaaS studio / self-hosted private instance

| Mode | Description | Deployment shape |
|---|---|---|
| SaaS studio | Multi-tenant platform, each organization = one studio | One distributed cluster with tenant isolation |
| Self-use / private | Single tenant, single machine or even local | One-command Docker Compose |

One codebase, switched by configuration (multi-tenant vs single-tenant mode). Self-hosting must stay lightweight; distributed deployment must not make the single-machine setup complicated.

### 2.2 Applicable domain: any knowledge domain

**Not limited to technology.** Concepts such as glossary, learning path, and chapter units are all domain-agnostic; "execute the code for real" is downgraded to an **optional domain plugin** (enabled for technical courses, disabled for humanities/popular-science courses). Neither the data model nor the agent flow assumes "there is always code".

---

## 3. Core capabilities

### 3.1 Coherent generation

Take a topic as input → produce a well-structured series that progresses from easy to advanced with text and figures. During generation the AI asks questions at key forks:

- "Do you want this more theoretical or more hands-on?"
- "The outline splits into 12 units — should the 'caching' chapter use Redis or a generic abstraction?"
- "Code samples default to Python; do you want TypeScript instead?"

The generation cadence is **human-in-the-loop**: each unit must pass human review before the next one starts.

### 3.2 Ask & Amend

Every course and every unit is an entity that can sustain a conversation. After generation you do not "re-run"; instead you:

- **Ask**: "Why cover A before B?", "How does this concept relate to X in my project?"
- **Amend locally**: "Change the unit 3 code from Python to Go", "Split this diagram into two", "Add a real-world case", "This passage is too wordy, tighten it"
- **Drill down**: "Fold the explanation you just gave into unit 3's further reading"

Every change is diffable and reversible (document history), git-style.

### 3.3 Knowledge sources and retrieval (RAG)

Three kinds of knowledge sources feed one retrieval pipeline:

```
KnowledgeSource
 ├─ Uploaded knowledge base: PDF / Markdown / docx / web pages / code repos…
 ├─ Web search: aggregation of multiple search providers (pluggable)
 └─ Existing series / glossaries in the platform (reusable across series)
        ↓
parse → chunk → index (hybrid vector + keyword) → retrieve → rerank → cite and trace
```

- After a knowledge base is uploaded: parse (documents/tables/image OCR) → chunk → embed and store, forming the series' private knowledge foundation.
- Web search is triggered on demand and its results also go through citation tracing; search results are never handed to the LLM raw.

### 3.4 Hallucination control (hard requirement, four mechanisms)

| Mechanism | Approach |
|---|---|
| Grounded citation | The writing agent may only write from retrieved evidence, and every paragraph carries a citation pointing at its source. **No evidence, no writing** |
| Fact checking (FactChecker) | Every key claim is re-retrieved and verified, and labelled "verified / doubtful / unsupported" |
| Uncertainty labelling | Doubtful content is explicitly labelled, or triggers "the AI asks the user" |
| Retrieval quality guardrails | Hybrid retrieval + rerank + dedup to reduce the chance of "fabricate when retrieval fails" |

**Source priority**: user-uploaded knowledge base > authoritative sources > general search, weighted at retrieval time.

### 3.5 Fault tolerance / parallelism / end-to-end control

- **Fault tolerance**: retries with exponential backoff and timeouts at every step; task granularity down to a single unit (one failed unit does not break the whole course); degradation chains (switch to a backup provider on failure, degrade to pure generation when retrieval fails but label it "not grounded in retrieval"); resume from checkpoints.
- **Parallelism**: multiple units in parallel (constrained by learning-path dependencies); overlapping retrieval/generation pipelines; concurrent multi-provider calls; naturally supported by the task queue, with concurrency limits to control cost.
- **End-to-end control**: human review gates (Gate: outline confirmation → per-unit review → pre-publish review, each gate configurable as "human required / may be automatic"); full observability (inputs/outputs/evidence/latency/tokens of every agent are queryable); intervention (pause, inject edits, re-run a single step); rollback (version history + review records).

---

## 4. Multi-tenancy and permissions

```
Organization (studio/tenant)
 ├─ Membership ── roles: Owner / Admin / Editor / Reviewer / Viewer
 ├─ Series (owned by an organization)
 │    └─ series-level collaborators (can narrow an organization role down to a single course)
 └─ organization-level resources: Glossary, model/API key configuration, quota
```

- **Data isolation**: every table carries `org_id`; middleware injects it mandatorily, preventing cross-tenant leaks.
- **LLM key custody**: the platform manages keys centrally (users never see them) and bills against the organization quota; self-hosted scenarios support BYOK.
- **Personal self-use** = a single-member Organization, and the UI automatically hides team/member entry points.

---

## 5. Data model (multi-tenant edition)

```
organizations          org metadata + quota + model configuration
memberships            org↔user role relationships
users / invites        users, invitations
series                title, language policy, status, org_id
chapters               chapters
units                content (multilingual JSONB), learning objectives, prerequisites, version number
unit_versions        document history (git-like, rollback-able)
glossary               glossary (Chinese/English pairs, org/series level)
learning_path          concept nodes + dependency edges
assets                 images/code/cover (object storage metadata)
threads / messages     ask/amend conversation threads (series level + unit level)
tasks / runs           generation/export tasks (consumed by workers)
usage_records          token metering (quota/billing)

knowledge_sources      uploaded knowledge base / search sources / references to existing series
documents / chunks     parsed documents and chunks (including vectors)
citations              paragraph → evidence source citation relationships
fact_checks            fact-check records (verified/doubtful/unsupported)
gates                  human review gates (status: pending/approved/rejected)
```

---

## 6. System architecture

### 6.1 Architecture overview

```
                Browser
                       │
        ┌──────────────▼─────┐
        │  Next.js frontend  │  outline tree editing · reader · chat panel · review gates · knowledge base management
        └──────────────┬─────┘
        ┌──────────────▼───────────────────────────────┐
        │  FastAPI API (stateless, multiple replicas)  │
        └──────────────┬───────────────────────────────┘
            │  Ports & Adapters (dependency injection, fully pluggable)
   ┌────────┼──────────────┬───────────────────┐
   │ DB (PG/pgvector)  object storage (rustfs/OSS/S3)  cache/messaging (Redis/Kafka)
   └────────┼──────────────┴───────────────────┘
                       │
   ┌───────────────────▼───────────────────────────────┐
   │  Knowledge source layer: knowledge base parsing,  │
   │  web search, RAG retrieval, citation tracing      │
   └───────────────────┬───────────────────────────────┘
                       │
   ┌───────────────────▼─────────────────────────────────┐
   │  Orchestration layer: agent loop (fault tolerance,  │
   │  parallelism, human gates, observability)           │
   │  writing → code (optional) → illustration →         │
   │  fact check → consistency check                     │
   └───────────────────┬─────────────────────────────────┘
                       │
   ┌───────────────────▼──────┐
   │  Worker pool / Executor  │
   └──────────────────────────┘
```

### 6.2 Pluggable design (Ports & Adapters)

**First architectural principle: every piece of infrastructure and every business capability is pluggable.**

Each module defines an interface (Port) and ships concrete implementations as Adapters, selected through dependency injection plus configuration switches. The same codebase runs both on a single machine and on K8s:

```
Single-machine self-host: Docker Compose bundles every dependency (works out of the box)
   ↓ same code, configuration only
K8s production: switch every dependency category to a managed external service (RDS / OSS / cloud Redis / Kafka…)
```

Implementation mechanics:
1. Abstract interfaces: Python `Protocol`/ABC defines every port.
2. Adapter implementations: `builtin_*` (single machine) paired with `external_*` (production).
3. Dependency injection: business code depends only on interfaces and never imports concrete implementations.
4. Health checks + probes: every adapter checks connectivity at startup, failing fast with a clear error.
5. Configuration-driven: a single file declares which adapter and parameters each module uses; under K8s this maps to ConfigMap/Secret.

### 6.3 Infrastructure pluggability matrix

| Module | Built-in implementation (single-machine default) | External implementation (K8s production) | How to switch |
|---|---|---|---|
| Database | Bundled PostgreSQL container | Cloud RDS / self-managed PG | Configure DSN |
| Object storage | **rustfs** | OSS / S3 / Azure / GCS | Configure endpoint + credentials |
| Vector search | pgvector (lives with the primary DB) | Qdrant / Milvus / Weaviate | Configure backend type |
| Cache | Bundled Redis | Cloud Redis | Configure address |
| Messaging/streaming | Redis Streams | Kafka (larger scale) | Configure broker type |
| Task queue | Celery + bundled Redis | Celery + cloud Redis / other brokers | Configure broker URL |
| LLM | OpenAI-compatible adapter | Any provider (DeepSeek/Doubao/Qwen/Claude/local vLLM) | Configure provider |
| Embedding | Bundled default model | OpenAI / Qwen / local bge | Configure provider |
| Illustration | Text-to-image API / image search | Switch between multiple providers | Configure provider |
| Sandbox execution | Local Docker containers | K8s Job/Pod, or a dedicated Executor cluster | Configure executor backend |
| Export engine | Built-in (pandoc/weasyprint) | Replaceable dedicated rendering service | Configure exporter |
| Auth | JWT + email | OAuth / OIDC / SAML / SSO | Configure auth provider |
| Observability | Local logs + Prometheus | OTel Collector / Langfuse | Configure tracing backend |

**Business capabilities are pluginized the same way** (registry mechanism):
- Export formats: `Exporter` interface → PDF/EPUB/HTML/MD; a new format is a new plugin.
- Reviewers/validators: `Reviewer` interface → deep review, fact checking, code validation (L1 static/L2 sandbox) can all be added or removed.
- Content language policies: `Localizer` interface → native monolingual / primary + translation / Chinese-English side by side, extensible.
- Figure types: `AssetProducer` interface → Mermaid / text-to-image / image search, each extended independently.

---

## 7. Key technical points

### 7.1 Streaming output under distribution (SSE)

While generating, workers publish events to Redis Pub/Sub / Streams (channel `org:{id}:series:{id}:events`); all API replicas subscribe to the same channel and forward events to the browsers connected to them. → The API stays stateless and can scale out, and the streaming experience does not depend on the number of replicas.

### 7.2 A safe way to "run code for real" as much as possible

Arbitrary code execution is the riskiest part of production, so it is tiered:
- **L1 static review (default)**: AST parsing + syntax/dependency checks; fast and risk-free.
- **L2 sandboxed execution**: a dedicated Executor running in a strongly isolated container (K8s Pod + seccomp/AppArmor, no external network, CPU/memory limits, timeouts); microVMs (Firecracker/gVisor) can be used for higher requirements.
- Results are written back to that unit's "code verified" flag.

### 7.3 Multi-author collaboration (pragmatic trade-offs)

**No Google-Docs-style real-time cursor collaboration (CRDT)**. Instead:
- Soft locks + presence within a series: show "who is editing which unit".
- Writes use optimistic locking (version number); on conflict, offer a diff to merge.
- Every generation/amendment creates a UnitVersion (document history) that can be diffed and rolled back.

Rationale: collaboration here is "AI author + several people reviewing/asking/amending", so conflicts are far rarer than in plain text documents.

### 7.4 Chinese-English bilingual

- UI i18n follows standard internationalization.
- Content language policy (configurable per series) has three modes: native monolingual / primary + translation / Chinese-English side by side.
- Each unit's content is stored as `{zh, en, bilingual}`, and exports pick the matching version according to the policy.

### 7.5 Hallucination control details

See 3.4. Core ideas: mandatory citations + fact checking + uncertainty labelling + retrieval quality guardrails, with source priority weighting.

### 7.6 Fault tolerance and parallelism

See 3.5. Core ideas: unit-level task granularity + retry/degradation/checkpoints + parallelism under dependency constraints + human review gates + full-chain observability.

---

## 8. Technology stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (React/TS) + Tailwind + TipTap editor |
| API | FastAPI (stateless, multiple replicas) |
| Task queue | Celery + Redis |
| Realtime | Redis Pub/Sub + SSE |
| Primary DB | PostgreSQL + pgvector (vector search, one less component) |
| Object storage | S3-compatible (**rustfs** self-hosted / OSS / S3) |
| Sandbox | Containers + seccomp/AppArmor, microVM optional |
| LLM abstraction | OpenAI-compatible adapter, multiple providers can be mixed (text/vision/illustration/embedding configured separately) |
| Illustration | Text-to-image API + image search + Mermaid vectors |
| Observability | OpenTelemetry + Prometheus/Grafana + structured logs |
| Deployment | Docker Compose (self-use) + K8s Helm (production) |
| Orchestration | Lightweight agent loop + tool calling (not hard-wired to LangGraph) |

---

## 9. Decision log (confirmed)

| # | Decision point | Conclusion |
|---|---|---|
| 1 | Delivery shape | Standalone web application |
| 2 | Relationship to vibe-blog | Not a clone; emphasize conversational/editable/follow-up-able |
| 3 | Content domain | Any knowledge domain (not only technology) |
| 4 | Language | Chinese-English bilingual (UI i18n + three optional content modes) |
| 5 | LLM | Abstracted (multiple providers; text/vision/illustration/embedding separate) |
| 6 | Figures | AI generation / image search + Mermaid vectors |
| 7 | Export | EPUB / PDF + HTML / Markdown |
| 8 | Generation cadence | Continue only after each unit passes human review (human-in-the-loop) |
| 9 | TTS | Not doing it |
| 10 | Amend/ask | Support further amendments + asking/following up (Ask & Amend) |
| 11 | Running code | Do as much as possible (L1 static + L2 sandboxed execution, degradable) |
| 12 | User scale | Multi-user, production environment, distributed deployment |
| 13 | Collaboration | Multi-author collaboration (soft locks + optimistic locks + version history, no CRDT) |
| 14 | Extensibility | Every module pluggable (Ports & Adapters); K8s can attach external DB/object storage |
| 15 | Built-in object storage | rustfs (replacing MinIO) |
| 16 | Knowledge sources | Uploaded knowledge base + web search + existing series |
| 17 | Hallucination control | Mandatory citations + fact checking + uncertainty labelling + retrieval quality |
| 18 | Reliability | Fault tolerance + parallelism + human review + end-to-end control |

---

## 10. Trade-offs made (can be revisited)

1. No CRDT; collaboration relies on soft locks + optimistic locks + version history.
2. Vector search uses pgvector: one less component and one less thing to operate.
3. PDF embeds Chinese fonts to avoid garbled text or missing glyphs in exports.
4. Orchestration uses a lightweight agent loop + tool calling, not hard-wired to LangGraph.
5. Distributed infrastructure comes later (validate the product on a single machine first, then split it out) to avoid premature complexity.

---

## 11. Implementation roadmap

Ordered from highest to lowest risk:

1. **M0**: get the core loop working on a single tenant/single machine — "generate one unit + ask + amend + document history"; **and build the minimal RAG chain first** (upload document → retrieve → write with citations), because hallucination control is a day-one hard requirement.
2. **M1**: series blueprint + per-unit human-in-the-loop + reader + glossary/learning path.
3. **M2**: multi-tenancy + RBAC + multi-author soft-lock collaboration + quota metering.
4. **M3**: task queueing + distributed SSE (Redis) + object storage → distributed deployment becomes possible.
5. **M4**: AI-generated/searched images + EPUB/PDF export (including Chinese font embedding).
6. **M5**: sandboxed execution (strongly isolated Executor) + observability + K8s Helm.

> Write against Port/Adapter from M0 onward, even with only one built-in implementation, to avoid rework later.

---

## 12. Next steps

Detailed deliverables still to be produced (pick any):
1. Detailed implementation steps for the M0 minimum viable version (recommended first).
2. Complete directory structure + module breakdown.
3. Core interface (Port) list + definitions.
4. PostgreSQL table schema.
5. Docker Compose / K8s deployment manifests.

---

*This file is the project's single source of truth; all future changes must be reflected here and in the decision log.*
