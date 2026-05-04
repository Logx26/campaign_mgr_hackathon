# Lumeo Campaign Studio

**AI Campaign Management System — turn rough campaign briefs into reviewable, multi-channel execution plans.**

A multi-agent platform built on LangGraph that takes a free-form marketing brief, surfaces gaps and ambiguities, asks targeted clarifying questions, generates a multi-channel plan with copy drafts and a timeline, and runs it through an AI Critic plus four governance scanners before export.

---

## Table of contents

- [Problem statement](#problem-statement)
- [Solution summary](#solution-summary)
- [Key features](#key-features)
- [Architecture](#architecture)
- [Setup and run](#setup-and-run)
- [How to use the system](#how-to-use-the-system)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Documentation](#documentation)
- [Notes for evaluators](#notes-for-evaluators)

---

## Documentation

This project ships three top-level docs. Read them in this order if you are
new to the codebase:

| File | What it is | Read when |
|---|---|---|
| [`README.md`](README.md) | Setup, run, demo paths, test commands, project layout | First — to get the project running |
| [`WORKFLOW.md`](WORKFLOW.md) | Engineering workflow log: snapshot, stack, ADRs, implementation notes, phase progress, conventions | Second — to understand *why* every architectural decision was made |
| [`AGENT.md`](AGENT.md) | Coding-assistant instructions: repository layout, conventions, architectural invariants ("do not break"), common tasks, security constraints | Third — before extending the codebase, or when configuring an AI coding assistant (Copilot, Cursor, Codex, etc.) for this repo |

`WORKFLOW.md` and `AGENT.md` are referenced by AI coding assistants and by
human contributors alike — both are intended to be living documents that keep
pace with the code.

---

## Problem statement

Marketing teams spend hours converting rough campaign briefs into multi-channel execution plans. The brief is usually incomplete (missing budget, vague audience, no measurable KPIs); the resulting plan often doesn't actually address the brief's objectives; and the copy across channels drifts from the brand's terminology and approved CTAs. Today this work happens in shared docs, manual reviews, and tribal knowledge — slow, inconsistent, and hard to audit.

We want to compress this from days of meetings into a 90-second AI-assisted workflow that:

- catches gaps in a brief *before* it produces a plan,
- forces the plan to address the brief's objectives,
- enforces brand consistency on the generated copy,
- and leaves a reviewable audit trail for every assumption made.

---

## Solution summary

**Lumeo Campaign Studio** is a three-workflow platform on a single backend:

1. **Plan from Brief** — paste a brief, resolve gaps with the AI, generate a reviewable multi-channel plan, and approve it. The headline workflow.
2. **Brief QA** — paste a brief and get a quality score with surfaced gaps before committing to plan generation.
3. **Asset Consistency** — drop in marketing assets and get clustered terminology drift, prohibited-CTA flags, and canonical recommendations cited from the brand dictionary.

Behind the UI there are 16 stateless agents coordinated by LangGraph, four deterministic governance scanners, an LLM Critic, an Assumption Ledger, and a full observability layer (trace events, cost meter, session replay, eval metrics).

---

## Key features

### Plan from Brief (W1)
- **Brief Normalizer** extracts a structured Brief from raw markdown / prose.
- **Completeness Checker** scores the brief against 22 rules (weighted, 0–100).
- **Ambiguity Detector** (LLM) surfaces vague-but-plausible language — e.g. "social" as a channel.
- **Clarifier** asks 3–5 typed clarifying questions; user answers are applied as overrides.
- **Planner** + parallel **Channel Specialists** (≤3 channels) + parallel **Copy Drafters** (with brand-voice scoring).
- **Timeline Synthesizer** with cross-channel dependency rules and a kickoff/launch milestone.
- **AI Critic** + 4 governance scanners (CTA-vs-spec, prohibited terms, length, mandatory inclusions) produce a severity-ranked validation report.
- **Assumption Ledger** logs every assumption made by the agents with confidence + citation.
- **Approve / Regenerate / Reject** flow with explicit acknowledgment when blockers are still open.

### Brief QA (W2)
- Quality-check a brief without generating a plan. Same Brief Normalizer + analysis pipeline, lighter-weight surface.
- Hand-off button into Plan from Brief once the brief is in good shape.

### Asset Consistency (W3)
- **Terminology Scanner** clusters variants of the same concept across assets via greedy cosine clustering (τ=0.70) over embeddings.
- **CTA Scanner** classifies every CTA as canonical / normalize / unconfigured against `rules/cta_patterns.yaml`.
- **Canonical Resolver** suggests the canonical phrasing with a citation back to the brand dictionary.
- **Consistency Report Composer** produces a single `overall_consistency_index` with redline-strikethrough deltas.

### Cross-cutting
- **Observability** — every LLM call writes a `trace_event` with cost, latency, cache hit, agent name. Full session replay supported.
- **Cost meter** — per-session live spend, summed from the authoritative trace ledger.
- **Eval harness** — `gap_catch_rate`, `plan_completeness_score`, `assumption_citation_rate` against a 8-brief golden set; quality dashboard with run-over-run delta.
- **Exports** — three primary download formats: HTML (Gantt timeline), PDF (full plan document), PPTX (16:9 slide deck for stakeholder sharing). All three carry the brand palette.
- **HITL** — human-in-the-loop at clarification (typed questions) and at approval (review report + ledger).

---

## Architecture

### High-level flow

```
                 ┌────────────────────────────────────────────────────┐
                 │              Streamlit UI (port 8501)              │
                 │  Home · Get Started · Plan from Brief · Brief QA · │
                 │  Asset Consistency · Run History · Quality Dash    │
                 └─────────────────────────┬──────────────────────────┘
                                           │ HTTPS
                                           ▼
                 ┌────────────────────────────────────────────────────┐
                 │           FastAPI (port 8000)                      │
                 │   /briefs · /plans · /qa · /consistency · /export  │
                 │   /sessions · /eval · /health                      │
                 └─────────────────────────┬──────────────────────────┘
                                           │
                                           ▼
                 ┌────────────────────────────────────────────────────┐
                 │           LangGraph Orchestrator                   │
                 │   typed CampaignState · Postgres checkpoint saver  │
                 └─────────┬─────────────────────────┬────────────────┘
                           │                         │
              ┌────────────▼──────────┐   ┌──────────▼────────────┐
              │    17 Agents          │   │   4 Governance        │
              │ (Brief Normalizer,    │   │   Scanners            │
              │  Clarifier, Planner,  │   │  (CTA, terms, length, │
              │  Channel Specialists, │   │   mandatory)          │
              │  Copy Drafters,       │   └───────────────────────┘
              │  Timeline Synth,      │
              │  Critic, Ledger,      │
              │  Terminology Scanner, │
              │  Canonical Resolver…) │
              └────────────┬──────────┘
                           │
        ┌──────────────────┼─────────────────────┬──────────────────┐
        ▼                  ▼                     ▼                  ▼
   ┌─────────┐       ┌─────────┐          ┌─────────┐         ┌──────────┐
   │ Postgres│       │ Qdrant  │          │  Redis  │         │  Azure   │
   │ (briefs,│       │(briefs, │          │(cache,  │         │  OpenAI  │
   │  plans, │       │ plans,  │          │ session,│         │ (gpt-4o, │
   │  trace, │       │ assets, │          │ budget, │         │ embed-   │
   │  eval)  │       │ terms)  │          │ drafts) │         │  3-small)│
   └─────────┘       └─────────┘          └─────────┘         └──────────┘
```

### Stack

- **Runtime:** Python 3.11+
- **Orchestrator:** LangGraph 0.2+ (typed `CampaignState`, Postgres checkpoint saver)
- **API:** FastAPI 0.111+ (async)
- **UI:** Streamlit 1.35+ (multi-page)
- **LLM:** Azure OpenAI `gpt-4o`, API version `2024-08-01-preview` (structured outputs with strict JSON Schema)
- **Embeddings:** Azure OpenAI `text-embedding-3-small-alpha` (1536-dim)
- **Structured store:** Postgres 16
- **Vector store:** Qdrant (4 collections, cosine distance)
- **Cache + session + budget:** Redis
- **Migrations:** Alembic
- **Schemas:** Pydantic v2 with `extra='forbid'` mandatory
- **Exports:** reportlab (PDF), python-pptx (PPTX), hand-rolled HTML (Gantt)

### Key design decisions

- **Single in-process orchestrator.** LangGraph runs inside the FastAPI process — no separate worker container — to keep the deploy surface small and the latency budget predictable.
- **Extraction-schema pattern.** Every LLM-bound schema with auto-generated fields (UUID, datetime) has a sibling `XxxExtraction` schema that drops those fields. Server fills `id` / `created_at` after the LLM returns. Prevents Azure strict-mode `null`-on-required-field errors.
- **Cap of 3 parallel channels.** Latency budget under 90s for the demo flow; 3 parallel LLM calls hit ~6s, 6 parallel calls risk Azure rate-limit thrash.
- **Greedy cosine clustering for terminology drift** (τ=0.70) instead of HDBSCAN — deterministic, no native-build risk on Windows/WSL, and gives the same answer for asset libraries of < 30 items.
- **Bounded revision loop.** Plan ↔ Critic loops capped at 2 revisions in code (not in prompt) to guarantee the demo always completes.
- **Eval harness baked in from day 2** so prompt regressions during development are visible immediately, not at the end.

---

## Setup and run

### Prerequisites

- Python 3.11+
- Docker (for Postgres / Qdrant / Redis containers)
- An Azure OpenAI deployment with `gpt-4o` (or compatible) and an embeddings deployment

### 1. Configure environment

```bash
cd campaign_mgr
cp .env.example .env
# edit .env and fill in:
#   AZURE_OPENAI_API_KEY
#   AZURE_OPENAI_ENDPOINT          (trailing slash required)
#   AZURE_OPENAI_DEPLOYMENT        (e.g. gpt-4o)
#   AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT
#   AZURE_OPENAI_API_VERSION       (default 2024-08-01-preview)
```

### 2. Start the storage stack

```bash
docker compose -f docker-compose.infra.yml up -d
# brings up postgres on 5432, qdrant on 6333/6334, redis on 6379
```

### 3. Install Python dependencies

```bash
python -m venv .venv
source .venv/bin/activate          # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 4. Run migrations and seed

```bash
alembic upgrade head
python scripts/seed_db.py
```

### 5. Start the API and UI

```bash
# Terminal 1
uvicorn api.main:app --reload --port 8000

# Terminal 2
streamlit run ui/Home.py --server.port 8501
```

Open <http://localhost:8501>. The landing page loads the three workflow cards.

### Ports

| Service   | Port      |
|-----------|-----------|
| Streamlit | 8501      |
| FastAPI   | 8000      |
| Postgres  | 5432      |
| Qdrant    | 6333/6334 |
| Redis     | 6379      |

---

## How to use the system

### Quickest path — sample workflows pre-filled

Open **Get Started** in the sidebar and click any of the four cards. Each opens its workflow with sample data already loaded:

- **Card A** — complete enterprise brief flowing straight to a reviewable plan.
- **Card B** — paragraph-form vague brief that surfaces 5 gaps; the clarification dialog updates the score live.
- **Card C** — Brief QA on a sample brief (quality check before plan generation).
- **Card D** — Asset Consistency on 5 sample assets that cluster `AI-powered` vs `AI-assisted`.

### Workflow 1 — Plan from Brief

1. **Paste** a campaign brief in the textarea (markdown or plain prose both work).
2. **Process brief** → the system extracts a structured Brief and renders an overview table.
3. **Run analysis** → 22 completeness rules + an ambiguity detector score the brief (0–100) and surface gaps as collapsible cards.
4. **Ask AI to clarify** → the AI generates 3–5 typed questions targeting the highest-impact gaps. Answer them; analysis re-runs and the score updates.
5. **Generate plan** → planner picks ≤3 channels from the seeded catalog, channel specialists fan out in parallel, copy drafters produce per-channel copy with brand-voice scores, timeline synthesizer schedules the work.
6. **Run review** → AI Critic + 4 governance scanners produce a severity-ranked validation report. Findings are collapsible; the Assumption Ledger lists every assumption with confidence and citation.
7. **Approve / Regenerate / Reject** → approving while blockers exist requires explicit acknowledgment.
8. **Export** → three primary buttons: **Download HTML** (Gantt timeline), **Download PDF** (full plan document), **Download PPTX** (slide deck).

### Workflow 2 — Brief QA

1. Paste a brief in the full-width textarea.
2. **Check brief quality** → the system extracts the structured brief, runs gap analysis, and displays a completeness score with collapsible gaps.
3. **Open in Plan from Brief** → carries the brief over to W1 if you want to take it forward.

### Workflow 3 — Asset Consistency

1. Add asset cards (`+ Add asset`). Each card takes Source name, Channel, Audience hint, and the asset body.
2. **Run consistency scan** → the system clusters terminology variants (e.g. `AI-powered` × 3, `AI-assisted` × 2 → cluster), flags non-canonical CTAs, and recommends canonicals from the brand dictionary.
3. The report includes an `overall_consistency_index`, terminology cluster cards, redline-strikethrough CTA drift, and per-CTA cards.

### Run History and Quality Dashboard

- **Run History** — per-session cost, calls, cache-hit rate, latency, errors. Trace timeline + replay.
- **Quality Dashboard** — gap-detection rate, plan-completeness, completion rate. Two Plotly gauges plus a trend chart once ≥ 2 eval runs exist.

---

## Testing

The project ships with a **comprehensive test suite at three levels**: unit tests for stateless logic, integration tests against live infrastructure, and an evaluation harness against a golden brief set.

### Test surface

- **Unit tests:** **188 tests** covering every agent, scanner, exporter, schema contract, and UI helper.
- **Integration tests:** **9 tests** running real Azure OpenAI + live Postgres / Qdrant / Redis through the full graph.
- **Eval golden set:** 8 reference briefs (complete / ambiguous / half-broken / contradictory) for regression detection.

### Run unit tests

Unit tests use in-memory fakes (monkeypatched `SessionLocal`, fake Redis) so they don't require any infrastructure to run.

```bash
# All unit tests (~30 seconds)
python -m pytest tests/unit -q

# A single agent's tests
python -m pytest tests/unit/test_planner.py -v

# With coverage
python -m pytest tests/unit --cov=core --cov=agents --cov-report=term-missing
```

12 unit tests are infrastructure-skipped by design (they exercise live Redis / Qdrant code paths) — they activate automatically when the storage stack is up.

### Run integration tests

Integration tests need the storage stack running and a valid `.env` with Azure credentials.

```bash
# bring up infra
docker compose -f docker-compose.infra.yml up -d

# all integration tests
python -m pytest tests/integration -q -m integration

# specific workflow
python -m pytest tests/integration/test_w1_phase6.py -v   # full W1 brief→plan→review
python -m pytest tests/integration/test_w2_qa.py -v       # W2 brief+plan audit
python -m pytest tests/integration/test_w3_consistency.py -v  # W3 asset consistency
```

What integration tests cover:

| File                               | What it verifies                                                              |
|------------------------------------|-------------------------------------------------------------------------------|
| `test_azure_structured.py`         | Live Azure structured-output call + cache hit + trace row write               |
| `test_embeddings.py`               | Embeddings deployment available, dim matches `EMBEDDING_DIM`                  |
| `test_w1_phase3.py`                | Brief → analyze produces ≥ 3 gaps including the budget hard gap               |
| `test_w1_phase5.py`                | Full plan generation with ≥ 2 channels, valid CTAs, kickoff in week 1         |
| `test_w1_phase6.py`                | End-to-end W1: brief → plan → review (Critic + governance + ledger)           |
| `test_w2_qa.py`                    | Mismatched brief+plan pair surfaces ≥ 2 findings + governance issues          |
| `test_w3_consistency.py`           | 5 sample assets produce expected `AI-powered` / `AI-assisted` cluster + CTAs  |

### Evaluation harness

Re-run the golden-set evaluation to detect prompt regressions:

```bash
# Brief Normalizer + analyze against the 8 reference briefs
python scripts/run_eval.py --tag baseline

# Include plan generation (slower but more thorough)
python scripts/run_eval.py --tag baseline --with-plan
```

Each run persists an `EvalRun` row that the **Quality Dashboard** page reads — you'll see gap-catch-rate, plan-completeness, and completion rate plotted run-over-run. The CLI exits non-zero if any item errored.

### Test status

```
tests/unit/         188 passed,  12 skipped (infra-only),   ~ 30 s
tests/integration/    9 passed                              ~ 2 m (depends on Azure latency)
```

---

## Project layout

```
campaign_mgr/
├── api/              FastAPI: routes/, main.py
├── agents/           16 stateless agents (Brief Normalizer, Clarifier, Planner, Critic, …)
├── orchestrator/     LangGraph graph, nodes, conditions, interrupts
├── core/             config, schemas (Pydantic v2), db, llm gateway, embeddings, prompts
├── knowledge/        channel specs, term dictionary, brand voice fingerprint, exemplars
├── tools/            Python primitives (completeness scoring, brand-voice scoring, …)
├── export/           HTML (Gantt), PDF (reportlab), PPTX (python-pptx), Markdown, JSON
├── observability/    trace events, cost meter, session replay
├── eval/             golden-set runner, metrics (gap catch rate, plan completeness)
├── ui/               Streamlit: Home.py, pages/, components/, styles.py
├── prompts/          versioned Jinja2 templates per agent (v1.jinja, …)
├── rules/            YAML rule catalog (completeness, CTA patterns, channel deps)
├── seeds/            seed data (channel specs, term dictionary, exemplar briefs, sample assets)
├── scripts/          one-shot CLIs (seed_db, run_eval, replay_session, build_brand_voice_fingerprint)
├── tests/            unit/, integration/, eval/, conftest.py
├── alembic/          DB migrations
├── pyproject.toml    deps + tool config
└── docker-compose.infra.yml   storage stack (postgres + qdrant + redis)
```

---

## Notes for evaluators

### What's deliberately out of scope

- Live ad-platform integration (Meta / Google / LinkedIn ads APIs)
- Autonomous publishing (everything is reviewed before it leaves the system)
- A/B test infrastructure
- CRM / MAP OAuth integrations
- Real-time budget optimization
- Multi-tenancy and authentication (single-machine demo)

These are documented in the project plan as Tier 2/3 deferrals; the foundation is in place to extend toward them.

### Key assumptions

- Azure OpenAI `gpt-4o` with structured outputs (`json_schema` + `strict: true`) is the default LLM. Other compatible deployments work with a config swap.
- The brand voice fingerprint is auto-built on first plan generation from `seeds/brand_voice_samples/{brand}_on_voice.txt` and `_off_voice.txt`. To use a different brand, drop new sample files in.
- Channel cap is 3 (configurable in code) — the seeded catalog has 6 channels but the planner respects the cap to keep latency under the demo budget.
- All copy drafts are cached in Redis under `copy_drafts:{session_id}:{plan_id}` (TTL 1 hour) — `CampaignState` is `extra='forbid'` and intentionally lean.
- Free-text answers to clarifying questions targeting list-typed Brief fields are routed to `constraints.mandatory_inclusions` as audit lines (with the `[override:field.path]` prefix preserved in storage and stripped at render time).

### Demo path (90-second walkthrough)

1. Open **Get Started** → click **Card A** → Plan from Brief loads with a complete enterprise brief.
2. Click **Process brief** → **Run analysis** → completeness score in the green band, no hard gaps.
3. Click **Generate plan** → 3 channels (Email, LinkedIn, Paid Search) with copy previews appear in ~6 seconds.
4. Click **Run review** → severity-ranked findings + Assumption Ledger.
5. Click **Approve plan** → **Download PDF** to ship a stakeholder-ready document.

For the clarification differentiator, use **Card B** instead — same workflow but with a vague brief that surfaces 5 gaps and walks through the typed-question dialog.

### Known cosmetic issue

The Streamlit sidebar's collapse-arrow positioning vs the fixed dark global header is unreliable across Streamlit minor versions. Sidebar navigation works; only the visual arrow toggle drifts. Treated as a Streamlit-internal cosmetic issue and not blocking.

### Performance notes

- End-to-end Plan from Brief on a complete brief: ~6–8 seconds for plan generation, ~3 seconds for review (cache cold). Cache hits land at $0 and < 50 ms.
- Cost per full session (brief → plan → review): typically under $0.20 with `gpt-4o`. Per-session budget cap is configurable via `SESSION_BUDGET_USD`.
- Asset Consistency on 5 assets: ~2 seconds for clustering + canonical resolution.
