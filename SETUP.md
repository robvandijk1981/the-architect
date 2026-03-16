# The Architect — Setup Guide

Stap-voor-stap handleiding voor de complete ModellenWerk Workforce Intelligence stack.

## Productie-stack

```
┌─────────────────────────────────────────────────────┐
│  Vercel (free)         → Portal frontend (Next.js)  │
│  Railway (Hobby $5)    → Architect API (FastAPI)     │
│  Railway Cron          → Wekelijkse kennisbasis-update│
│  Neon (free)           → Postgres + pgvector         │
│  Claude API            → Analyse-engine              │
│  Voyage AI             → Embeddings                  │
└─────────────────────────────────────────────────────┘
```

## Kostenoverzicht

| Service | Kosten/maand |
|---------|-------------|
| Neon Postgres (free tier) | $0 |
| Railway Hobby | $5 |
| Vercel Hobby (frontend) | $0 |
| Claude API (~50 analyses) | ~$3-5 |
| Voyage AI embeddings | ~$1-2 |
| **Totaal** | **~$9-12/maand** |

---

## Stap 1: Neon Database

### 1a: Project aanmaken
1. Ga naar [neon.tech](https://neon.tech) → Sign Up → Create Project
2. Regio: **EU (Frankfurt)** of **EU (Ireland)**
3. Projectnaam: `modellenwerk-architect`
4. Neon maakt automatisch database `neondb` aan

### 1b: Connection string ophalen
Dashboard → **Connection Details** → kopieer de connection string:
```
postgresql://neondb_owner:xxxxxxxx@ep-cool-name-123456.eu-west-1.aws.neon.tech/neondb?sslmode=require
```
Dit is je `DATABASE_URL`.

### 1c: Schema aanmaken
1. Ga naar **SQL Editor** in Neon dashboard
2. Plak de inhoud van `migrations/001_initial_schema.sql` → **Run**
3. Plak de inhoud van `migrations/002_functions.sql` → **Run**

Neon heeft pgvector standaard geïnstalleerd — de `CREATE EXTENSION vector;` werkt direct.

---

## Stap 2: AI Provider Keys

### Anthropic (Claude)
1. [console.anthropic.com](https://console.anthropic.com) → API key aanmaken
2. Laad minimaal $5 tegoed (pay-per-use)
3. Bewaar als `ANTHROPIC_API_KEY`

### Voyage AI (Embeddings)
1. [dash.voyageai.com](https://dash.voyageai.com) → Account + API key
2. Free tier: 200M tokens/maand (ruim voldoende)
3. Bewaar als `VOYAGE_API_KEY`

---

## Stap 3: Railway — Architect API

### 3a: Project aanmaken
1. Push `the-architect/` naar een GitHub repository
2. Ga naar [railway.app](https://railway.app) → New Project → **Deploy from GitHub repo**
3. Selecteer de repo — Railway detecteert `railway.toml` automatisch

### 3b: Environment variables
Ga naar je Railway service → **Variables** en voeg toe:

| Variable | Waarde |
|----------|--------|
| `DATABASE_URL` | Je Neon connection string |
| `ANTHROPIC_API_KEY` | `sk-ant-...` |
| `VOYAGE_API_KEY` | `pa-...` |
| `API_SECRET_KEY` | Genereer een random string |
| `ARCHITECT_API_KEY` | `mw-architect-<sterk-wachtwoord>` |
| `ENVIRONMENT` | `production` |
| `LOG_LEVEL` | `INFO` |

### 3c: Deploy
Railway deployt automatisch. Check:
```bash
curl https://your-app.up.railway.app/api/v1/health
```

### 3d: Cron job (wekelijkse updates)
1. In Railway project → **Add Service** → **Cron Job**
2. Dezelfde GitHub repo
3. Schedule: `0 7 * * 1` (maandag 07:00 UTC)
4. Start command: `python -m app.pipeline.orchestrator`
5. Kopieer dezelfde environment variables
6. Railway Hobby cron jobs zijn gratis bij je $5/maand

---

## Stap 4: Kennisbasis vullen (eenmalig)

### Eigen research laden
```bash
# Lokaal (met .env in project root)
pip install .
python -m app.pipeline.seed --data-dir ~/OneDrive\ -\ OrgVision/Workspace
```

Dit laadt je 4 bestaande MW-onderzoeksbestanden:
- MW_Sectorale_Analyse_8x5_Dimensies.md
- MW_Organisatie_Analyse_40_Organisaties.md
- MW_Workforce_Intelligence_Report_2026.md
- MW_Workforce_Agent_Training_Blueprint.md

### Eerste collector run
```bash
python -m app.pipeline.orchestrator
```
Dit haalt CBS, UWV en AZW data op en embedt het in de kennisbasis.

---

## Stap 5: Testen

### Knowledge stats
```bash
curl -H "Authorization: Bearer mw-architect-xxx" \
  https://your-app.up.railway.app/api/v1/stats
```

### Chat met The Architect
```bash
curl -X POST https://your-app.up.railway.app/api/v1/chat \
  -H "Authorization: Bearer mw-architect-xxx" \
  -H "Content-Type: application/json" \
  -d '{"message": "Wat is het gemiddelde verzuimpercentage in de zorgsector?", "context": {"sector": "zorg"}}'
```

### Risk matrix
```bash
curl -X POST https://your-app.up.railway.app/api/v1/risk \
  -H "Authorization: Bearer mw-architect-xxx" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Ziekenhuis", "sector": "zorg", "employee_count": 2500, "average_age": 44, "turnover_rate": 14, "absence_rate": 7.2}'
```

### Business case
```bash
curl -X POST https://your-app.up.railway.app/api/v1/businesscase \
  -H "Authorization: Bearer mw-architect-xxx" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Ziekenhuis", "sector": "zorg", "employee_count": 2500, "turnover_rate": 14, "absence_rate": 7.2}'
```

---

## Stap 6: Vercel — Portal Frontend (later, door Manus)

De portal wordt een apart Next.js project dat Manus bouwt. De koppeling:

1. Manus maakt een Next.js repo met de 28 prompts uit `MW_Portal_Manus_Prompts_v2.md`
2. Deploy naar Vercel (gratis, automatisch bij GitHub push)
3. Vercel environment variable: `ARCHITECT_API_URL=https://your-app.up.railway.app`
4. Portal roept The Architect API aan via de `ArchitectClient` class

Vercel + Railway communiceren via HTTPS. CORS is al geconfigureerd in `app/main.py`.

---

## Architectuur

```
the-architect/
├── app/
│   ├── api/           → FastAPI routes + auth
│   ├── core/          → Config, database (asyncpg), logging
│   ├── models/        → Pydantic models (intake, risk, BC)
│   ├── services/      → RAG, risk calculator, business case
│   ├── collectors/    → CBS StatLine, UWV, AZW Monitor
│   ├── processors/    → Diff detection
│   ├── pipeline/      → Orchestrator + seed script
│   └── main.py        → App entry point + lifespan
├── migrations/        → Neon SQL (pgvector schema + functions)
├── config/            → sources.yaml (collector schedules)
├── railway.toml       → Railway deploy config
├── Procfile           → web + worker process types
└── pyproject.toml     → Python dependencies (asyncpg, no ORM)
```

## Vendor lock-in

Nul. Standaard Postgres + Python:
- **Neon** → vervangbaar door elke Postgres met pgvector
- **Railway** → vervangbaar door elke Python hosting
- **Vercel** → vervangbaar door elke Next.js hosting
- **asyncpg** → standaard Postgres driver, geen ORM
- **Voyage AI** → vervangbaar door OpenAI embeddings (1 config regel)
