# Campaign Management System

AI-assisted brief-to-execution-plan workflow with clarification dialog, plan QA, and multi-channel consistency checking.

**Status:** P1 Foundation. See `../CLAUDE.md` for live status. See `../claude_plan.md` for the full execution plan.

## Quick start

```bash
# 1. Provision .env (request keys from organizers)
cp .env.example .env
# edit .env with your Azure OpenAI credentials

# 2. Start the storage stack (postgres, qdrant, redis from provided compose)
docker compose up -d postgres qdrant redis

# 3. Install Python deps
pip install -e ".[dev]"

# 4. Run migrations + seed
alembic upgrade head
python scripts/seed_db.py

# 5. Run API + UI
uvicorn api.main:app --reload --port 8000
# in separate terminal:
streamlit run ui/app.py --server.port 8501
```

Open http://localhost:8501 — landing page should show "API: OK" once both services are up.

## Project layout

```
campaign_mgr/
├── core/        # config, schemas, db, llm, embeddings, prompts, rules
├── agents/      # 16 stateless agents (Brief Normalizer, Clarifier, Planner, ...)
├── orchestrator/# LangGraph graph, nodes, conditions, interrupts
├── knowledge/   # channel specs, term dictionary, brand voice, exemplars
├── tools/       # Python primitives (a subset exposed as MCP in Tier 1)
├── export/      # JSON/Markdown/Gantt/PDF/PPTX
├── observability/ # trace, cost meter, replay
├── eval/        # golden set, metrics, runner
├── api/         # FastAPI: routes/, middleware/
├── ui/          # Streamlit: pages/, components/
├── prompts/     # versioned Jinja2 templates per agent
├── rules/       # YAML rule catalog
├── seeds/       # seed data: channel_specs, term_dictionary, exemplar_briefs, ...
├── scripts/     # one-shot CLIs (seed_db, build_brand_voice_fingerprint, run_eval, ...)
└── tests/       # unit, integration, eval
```

## Workflows

- **W1** — paste brief → ask clarifying questions → generate plan → critic → ledger → export
- **W2** — paste brief + plan → validation report
- **W3** — drop assets → terminology + CTA consistency report

## Out of scope

Live ad-platform integration · autonomous publishing · A/B test infra · CRM/MAP OAuth · real-time budget optimization · multi-tenancy · auth.
