# ReadRabbit

A personal article discovery app that helps you go down rabbit holes on topics you care about. Replace mindless social media scrolling with intentional long-form reading.

Articles flow through a 4-layer ingestion pipeline, get quality-scored by an LLM, and are ranked into a personalized "For You" feed using semantic embeddings and interest clustering.

## Features

- **For You feed** — personalized recommendations built from your saves, powered by Voyage AI embeddings and cosine similarity with MMR diversity reranking
- **Discovery Agent** — search any topic, get AI-curated article suggestions (Groq + Serper)
- **4-layer ingestion pipeline** — RSS crawl → link graph → aggregator taps (HN, Lobsters, Reddit) → probation source evaluation, all running automatically on a schedule
- **Quality scoring** — hard gates (word count, link density, domain blacklist) + Groq LLM scoring composite
- **Chrome extension** — save any article to ReadRabbit with one click
- **Admin panel** — review queue with approve/reject, pipeline controls, eval metrics, embedding status
- **Email notifications** — Resend API notifications after each pipeline layer completes
- **Auth** — Clerk JWT authentication with guest read access and contextual sign-in prompts
- **YouTube support** — transcripts extracted and scored alongside text articles

## Quick Start

### Backend (Python + FastAPI)

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # fill in your keys
python main.py
```

Backend runs at: http://localhost:8000

**Required environment variables:**

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (e.g. Neon or local Postgres) |
| `CLERK_JWT_ISSUER` | Your Clerk frontend API URL |
| `GROQ_API_KEY` | Groq API key (LLM quality scoring + metadata extraction) |
| `VOYAGE_API_KEY` | Voyage AI key for embeddings (free tier: 200M tokens/month) |
| `RESEND_API_KEY` | Resend key for pipeline email notifications |
| `SERPER_API_KEY` | Serper API key for Discovery Agent web search |
| `OPENAI_API_KEY` | Optional fallback embedding provider |
| `ADMIN_SECRET` | Secret header value for admin endpoints |

### Frontend (React + Vite + Tailwind)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:5173

### Chrome Extension

Load unpacked from the `extension/` directory in Chrome (`chrome://extensions` → Developer mode → Load unpacked). The extension points to the production backend at `readrabbit.onrender.com` by default.

## Project Structure

```
readrabbit/
├── backend/
│   ├── main.py                    # FastAPI app, all API routes, Clerk auth
│   ├── database.py                # SQLAlchemy models (Article, Source, User, etc.)
│   ├── scheduler.py               # APScheduler — runs pipeline layers on intervals
│   ├── feed_crawler.py            # Layer 1: RSS/Atom feed ingestion
│   ├── link_graph.py              # Layer 2: Outbound link extraction + domain discovery
│   ├── aggregator_tap.py          # Layer 3: HN, Lobsters, Reddit taps
│   ├── probation.py               # Layer 4: Promote/prune probation sources
│   ├── quality_pipeline.py        # Hard gates + composite quality scoring
│   ├── quality_pipeline_service.py
│   ├── recommendation_engine.py   # Interest clusters + cosine similarity + MMR
│   ├── admin_recommendation.py    # Admin queue generation with MMR reranking
│   ├── ai_service.py              # Groq LLM + Voyage/OpenAI/HF embedding providers
│   ├── discovery_agent.py         # Topic search via Serper + Groq
│   ├── youtube_service.py         # YouTube transcript extraction
│   ├── seed_sources.py            # Initial source seeding
│   ├── migrations/                # Alembic DB migrations
│   ├── tests/                     # pytest test suite
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── App.jsx                # Root app, routing, auth state
│       ├── components/
│       │   ├── ArticleCard.jsx    # Article card with save/dismiss actions
│       │   ├── AdminPage.jsx      # Admin panel (queue, pipeline, eval metrics)
│       │   ├── DiscoverAgent.jsx  # Topic discovery UI
│       │   └── App.jsx            # (legacy, see src/App.jsx)
│       └── index.css
├── extension/
│   ├── manifest.json              # Chrome extension manifest v3
│   ├── popup.html
│   └── popup.js                  # Save current tab to ReadRabbit
└── data/                         # Seed data / static assets
```

## API Reference

### Public endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/articles` | GET | List articles (with filters) |
| `/api/articles/random` | GET | Get random articles |
| `/api/articles/{id}` | GET | Get article by ID |
| `/api/articles/{id}/dismiss` | POST | Dismiss an article |
| `/api/articles/{id}/save` | POST | Save an article |
| `/api/articles/{id}/similar` | GET | Semantic similar articles |
| `/api/articles/reset` | POST | Reset dismissed articles |
| `/api/save-article` | POST | Save article by URL (used by extension) |
| `/api/recommendations` | GET | Personalized recommendations |
| `/api/recommendations/for-you` | POST | For You feed (MMR-ranked) |
| `/api/reading-history` | POST | Log reading activity |
| `/api/users/me` | POST | Create/update user after Clerk sign-in |
| `/api/health` | GET | Health check |

### Discovery Agent

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agent/discover` | POST | Search + curate articles on a topic |
| `/api/agent/for-you` | POST | Agent-powered For You feed |
| `/api/agent/save-recommendation` | POST | Save an agent-recommended article |
| `/api/agent/reading-profile` | GET | Get user reading profile |

### Admin (requires `X-Admin-Secret` header)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/admin/stats` | GET | Pipeline and corpus stats |
| `/api/admin/eval` | GET | Eval event log |
| `/api/admin/queue` | GET | Review queue |
| `/api/admin/queue/generate` | POST | Generate new review queue (MMR) |
| `/api/admin/queue/review` | POST | Approve or reject a queued article |
| `/api/admin/queue/review/bulk` | POST | Bulk approve/reject |
| `/api/admin/queue/stats` | GET | Queue health metrics |
| `/api/admin/pipeline/crawl` | POST | Manually trigger feed crawl |
| `/api/admin/pipeline/test-notify` | POST | Send test pipeline email |
| `/api/admin/candidates` | POST | Run candidate generation |
| `/api/admin/candidates/approve` | POST | Approve a candidate article |
| `/api/admin/suggest` | POST | AI-suggest sources for a topic |
| `/api/admin/add-article-smart` | POST | Add article by URL with AI enrichment |
| `/api/admin/generate-embeddings` | POST | Backfill embeddings |
| `/api/admin/enhance-summaries` | POST | Backfill AI summaries |
| `/api/admin/embedding-status` | GET | Embedding coverage report |
| `/api/admin/migrate-db` | POST | Run DB migrations |
| `/api/admin/run-tests` | GET | Run test suite remotely |

## Ingestion Pipeline

The pipeline runs automatically via APScheduler on startup. Each layer is independently scheduled:

| Layer | Module | Default interval | What it does |
|-------|--------|-----------------|--------------|
| 1 | `feed_crawler.py` | Every 6 hours | Fetches RSS/Atom feeds, extracts full content via trafilatura, quality-scores, stores raw articles |
| 2 | `link_graph.py` | Every 2 hours | Parses outbound links from stored HTML, discovers new domains, adds them as probation sources |
| 3 | `aggregator_tap.py` | Every 4 hours | Taps Hacker News, Lobsters, Reddit for top stories; quality-gates and ingests passing articles |
| 4 | `probation.py` | Every 24 hours | Promotes probation sources that accumulate enough quality citations; prunes stale ones |

Override intervals with env vars: `CRAWLER_INTERVAL_HRS`, `LINK_GRAPH_INTERVAL_HRS`, `AGGREGATOR_INTERVAL_HRS`, `PROBATION_INTERVAL_HRS`.

## Quality Scoring

Every article passes through hard gates first:
- Word count >= 1500
- Link density < 0.15 (links / words)
- Domain not in blacklist

Passing articles get a composite quality score (0.0–1.0):

| Signal | Weight | Source |
|--------|--------|--------|
| Groq LLM quality score | 0.4 | `llama-3.3-70b-versatile` |
| Freshness | 0.3 | Exponential decay by age |
| Aggregator boost | 0.2 | HN/Lobsters/Reddit score |
| Source tier | 0.1 | static=1.0, dynamic=0.9, probation=0.7 |

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, Vite, Tailwind CSS, Clerk React |
| Backend | Python, FastAPI, SQLAlchemy, APScheduler |
| Database | PostgreSQL (Neon), pgvector |
| Auth | Clerk (RS256 JWT verification) |
| Embeddings | Voyage AI (primary), OpenAI (fallback), HuggingFace (free fallback) |
| LLM | Groq (`llama-3.3-70b-versatile`) |
| Content extraction | trafilatura, readability-lxml |
| Feed parsing | feedparser |
| Telemetry | PostHog |
| Email | Resend |
| Hosting | Render (backend), Vite build (frontend) |
