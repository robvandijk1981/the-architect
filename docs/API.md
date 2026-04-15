# ModellenWerk Workforce Intelligence API

REST API voor Het Datalab — workforce analytics, benchmarks, business cases en AI-interpretaties voor de Nederlandse arbeidsmarkt.

**Base URL:** `https://web-production-9324.up.railway.app/api/v1`
**Auth:** `Authorization: Bearer mw-architect-2026` (op alle endpoints behalve `/health`)
**Sector slugs (canoniek):** `zorg` · `overheid` · `bouw` · `energie` · `onderwijs` · `transport` · `financieel` · `retail` · `techniek`

---

## Endpoint-overzicht

| Category | Endpoint | Purpose |
|---|---|---|
| **Conversational** | `POST /chat` | Vrije vraag aan de workforce intelligence |
| **Analysis** | `POST /analyze` | Start een volledige workforce-analyse (async) |
|  | `GET /analyze/{id}` | Poll voor status/resultaat |
|  | `POST /risk` | 6-risk matrix (deterministisch) |
|  | `POST /businesscase` | 5-categorie business case |
| **Benchmarks** | `GET /benchmark/{sector}` | Statistische benchmarks uit 60 organisaties |
|  | `GET /sectors` | Overzicht van sectoren + AI-impact |
|  | `GET /sector/{slug}` | Volledig sectorprofiel |
|  | `GET /sector-profiles` | Alle sectorprofielen in één call |
| **Calculations** | `POST /calculate/vacancy-cost` | Kosten openstaande vacatures |
|  | `POST /calculate/turnover-cost` | Kosten personeelsverloop |
|  | `POST /calculate/absenteeism-cost` | Kosten ziekteverzuim + burnout |
|  | `POST /calculate/cost-of-inaction` | Integrale kosten + projectie |
|  | `POST /calculate/reskilling-roi` | ROI op omscholing |
|  | `POST /calculate/automation-roi` | ROI op procesautomatisering |
|  | `POST /calculate/scenario-compare` | Vergelijk twee scenario's |
|  | `POST /calculate/benchmark-score` | KPI-scores vs sector-median |
| **AI Interpretations** | `POST /ai/interpret` | Duidt calculatieresultaten in tekst |
|  | `POST /ai/narrative` | Verhaal-vorm voor CHRO/bestuur |
|  | `POST /ai/workforce-gap` | FTE-gap projectie |
|  | `POST /ai/cost-trajectory` | Kostenprojectie meerjaren |
|  | `POST /ai/detect-anomalies` | Detecteer afwijkingen in KPIs |
| **Data** | `GET /organizations` | Lijst 60 organisaties |
|  | `GET /organization/{name}` | Details per organisatie |
|  | `GET /functions` | Functies per sector |
|  | `GET /function/{sector}/{functie}` | Detail per functie |
|  | `GET /data-freshness` | Hoe up-to-date is de kennisbank |
|  | `GET /stats` | RAG statistieken |
| **Health** | `GET /health` | Liveness (geen auth) |

---

## `/chat` — conversational

```http
POST /chat
Content-Type: application/json

{
  "message": "Hoeveel vacatures zijn er in de bouwsector?",
  "context": {"sector": "bouw"}                    // optional
}
```

**Response:** `{"response": "...", "sources": [...], "suggested_actions": []}`

Retrieval pipeline: structured data (sector_profiles) → RAG (vector search met sector-filter, threshold 0.30, Voyage rerank-2) → Claude synthesis.

---

## `/analyze` — full workforce analysis

```http
POST /analyze

{
  "organization_profile": {
    "name": "Erasmus MC",
    "sector": "zorg",                             // sector kan ook op top-level (optional, overrides profile.sector)
    "employee_count": 14000,
    "turnover_rate": 12.5,                        // optional
    "absence_rate": 6.8,                          // optional
    "revenue": 2500000000,                        // optional, EUR
    "strategic_priorities": ["AI adoption", "..."] // optional
  }
}
```

**Response:** `{"analysis_id": "...", "status": "processing"}` — poll `/analyze/{id}` tot status `completed`.

---

## `/calculate/*` — parametric cost calculations

Alle `/calculate/*` endpoints hebben sector-specifieke defaults uit `sector_benchmarks`. Velden die je **niet** meestuurt, vallen terug op die defaults; stuur ze wel mee om je eigen parameters te overschrijven.

### `/calculate/vacancy-cost`

```json
{
  "sector": "zorg",                                 // REQUIRED (enum)
  "open_vacancies": 1500,                           // REQUIRED (≥0)
  "time_to_fill_days": 65,                          // optional — default: sector benchmark (zorg: 65)
  "cost_per_hire": 4200,                            // optional — default: sector benchmark (zorg: €4200)
  "include_monte_carlo": false                      // optional
}
```

### `/calculate/turnover-cost`

```json
{
  "sector": "zorg",
  "fte_count": 14000,                               // REQUIRED (≥1)
  "turnover_rate": 14.2,                            // optional — default: sector benchmark %
  "avg_salary": 52000,                              // optional — default: sector avg_labour_cost_fte
  "include_monte_carlo": false
}
```

### `/calculate/absenteeism-cost`

```json
{
  "sector": "zorg",
  "fte_count": 14000,                               // REQUIRED
  "absenteeism_rate": 6.1,                          // optional — default: sector benchmark %
  "avg_salary": 52000,                              // optional
  "burnout_prevalence": 22.0,                       // optional — default: sector benchmark %
  "include_monte_carlo": false
}
```

### `/calculate/cost-of-inaction`

Integrale kosten + projectie over 1-10 jaar.

```json
{
  "sector": "zorg",
  "fte_count": 14000,                               // REQUIRED
  "open_vacancies": 1500,                           // optional
  "turnover_rate": 14.2,                            // optional
  "absenteeism_rate": 6.1,                          // optional
  "avg_salary": 52000,                              // optional
  "burnout_prevalence": 22.0,                       // optional
  "projection_years": 3,                            // optional, default 3, range 1-10
  "include_societal_costs": false,                  // optional
  "include_monte_carlo": false
}
```

### `/calculate/reskilling-roi`

```json
{
  "sector": "zorg",
  "num_employees": 500,                             // REQUIRED (≥1)
  "investment_per_person": 5000,                    // REQUIRED (≥0)
  "expected_productivity_gain_pct": 15,             // REQUIRED (0-100)
  "avg_salary": 52000,                              // optional
  "time_horizon_years": 3,                          // optional, default 3
  "discount_rate": 0.08                             // optional, default 0.08
}
```

### `/calculate/automation-roi`

```json
{
  "sector": "zorg",
  "current_fte_allocated": 200,                     // REQUIRED (FTE currently on the process)
  "implementation_cost": 500000,                    // REQUIRED (EUR, one-time)
  "expected_fte_reduction": 60,                     // REQUIRED (FTE saved)
  "avg_salary": 52000,                              // optional
  "time_horizon_years": 3,                          // optional
  "failure_rate_adjustment": 1.0                    // optional, 0.5-2.0
}
```

### `/calculate/scenario-compare`

Vergelijk twee scenario's (bijv. huidig vs. na-interventie).

```json
{
  "scenario_a": {"name": "Huidig", "fte_count": 14000, "open_vacancies": 1500, "turnover_rate": 14.2, "absenteeism_rate": 6.1, "avg_salary": 52000},
  "scenario_b": {"name": "Na AI-implementatie", "fte_count": 14000, "open_vacancies": 800, "turnover_rate": 11.0, "absenteeism_rate": 5.5, "avg_salary": 52000},
  "time_horizon_years": 3                           // optional
}
```

### `/calculate/benchmark-score`

Organisatie-KPIs scoren tegen sector-median.

```json
{
  "sector": "zorg",
  "organisation_name": "Erasmus MC",                // REQUIRED
  "kpis": {                                         // REQUIRED — dict van KPI → jouw waarde
    "verzuim_pct": 7.2,
    "turnover_rate": 16.0
  }
}
```

---

## `/ai/*` — AI-powered interpretation

### `/ai/interpret`

Verklaart calculatieresultaten in lopende tekst met risico-flags en aanbevelingen.

```json
{
  "calculation_type": "vacancy_cost",               // REQUIRED
  "results": {"total_annual_cost": 24000000, "...": "..."}, // REQUIRED
  "sector": "zorg",                                 // REQUIRED
  "confidence_level": "medium"                      // optional, default medium
}
```

### `/ai/narrative`

Zelfde data, maar verhaal-vorm voor een specifieke doelgroep.

```json
{
  "results": {"total_annual_cost": 24000000, "...": "..."},
  "audience": "chro"                                // default chro; ook: "workshop", "default"
}
```

### `/ai/workforce-gap`

FTE-gap projectie.

```json
{
  "sector": "zorg",
  "current_fte": 14000,                             // REQUIRED (≥1)
  "growth_rate": 2.5,                               // REQUIRED (%/jaar, 0-100)
  "retirement_rate": 4.0,                           // REQUIRED (%/jaar, 0-100)
  "attrition_rate": 12.0,                           // optional, default 12
  "years": 5                                        // optional, default 5, range 1-20
}
```

### `/ai/cost-trajectory`

Kostenprojectie.

```json
{
  "sector": "zorg",
  "current_costs": {"vacature": 24000000, "verzuim": 15000000, "verloop": 38000000}, // REQUIRED dict
  "escalation_factor": 1.08,                        // optional, 1.01-1.20
  "years": 5                                        // optional, 1-10
}
```

### `/ai/detect-anomalies`

Vindt afwijkingen.

```http
POST /ai/detect-anomalies?sector=zorg

{
  "kpis": {"verzuim_pct": 9.5, "turnover_rate": 22.0}
}
```

---

## `/benchmark/{sector}` — statistische benchmarks

Aggregatie over 60 organisaties, 12 metrics, median/min/max/p25/p75 per metric.

```http
GET /benchmark/zorg
```

**Response:**
```json
{
  "sector": "zorg",
  "organizations_count": 10,
  "benchmarks": [
    {"metric_name": "verzuim_pct", "median_value": 6.25, "min_value": 5.2, "max_value": 7.8, "p25": 5.78, "p75": 6.65, "sample_size": 10, "unit": "percentage"},
    {"metric_name": "vacatures", "median_value": 66.5, ...},
    {"metric_name": "kosten_krapte_totaal_mln", "median_value": 95.2, ...},
    // ... 9 more
  ]
}
```

**12 metrics:** `verzuim_pct`, `vacatures`, `gem_jaarsalaris`, `personeelskosten_mln`, `kosten_krapte_totaal_mln`, `kosten_verzuim_mln`, `kosten_werving_mln`, `kosten_inhuur_mln`, `ai_baten_25_mln`, `ai_baten_50_mln`, `ai_baten_75_mln`, `fte_bespaard_50`.

---

## Error responses

Alle endpoints gebruiken standaard HTTP statuscodes:

- `200` — OK
- `401` — ontbrekende/ongeldige Authorization header
- `404` — resource niet gevonden
- `422` — schema validation (Pydantic): de `detail` array vertelt welk veld ontbreekt/fout is
- `500` — backend error; `detail` bevat error type + eerste 500 chars van het bericht

Voorbeeld 422:
```json
{"detail": [{"type": "missing", "loc": ["body", "open_vacancies"], "msg": "Field required", "input": {...}}]}
```

---

## Sector default waarden

Als je in `/calculate/*` geen waarde meestuurt voor `time_to_fill_days`, `cost_per_hire`, `turnover_rate`, `absenteeism_rate`, etc., worden deze sector-benchmarks gebruikt:

| Sector | TTF (dagen) | CPH (EUR) | Turnover % | Verzuim % | Burnout % | Gem. salaris |
|---|---:|---:|---:|---:|---:|---:|
| zorg | 65 | 4.200 | 14.2 | 6.1 | 22.0 | 52.000 |
| overheid | 85 | 5.800 | 8.5 | 5.2 | 16.0 | 58.000 |
| bouw | 45 | 3.200 | 18.5 | 5.9 | 18.0 | 45.000 |
| energie | 72 | 6.500 | 7.2 | 4.8 | 12.0 | 62.000 |
| onderwijs | 58 | 3.800 | 9.1 | 5.4 | 19.0 | 48.000 |
| transport | 52 | 2.900 | 17.8 | 6.2 | 15.0 | 42.000 |

Bron: CBS Labour Statistics 2026 + sector-specifieke referenties (zie `app/pipeline/seed_benchmarks.py` voor per-sector bron).

---

## Admin endpoints (infra/maintenance)

Voor maintainer use. Allemaal bearer-auth.

- `POST /admin/seed` — seed RAG-knowledge base met ModellenWerk research
- `POST /admin/upload` — upload document (md/txt/pdf) in de kennisbank
- `GET /admin/documents` — lijst documenten met filters
- `POST /admin/collect` — draai CBS/UWV/AZW collectors
- `POST /admin/install-benchmark-v2` — (her)installeer `get_sector_benchmarks` SQL function
- `POST /admin/reseed-organizations` — re-seed 60 organisaties
- `POST /admin/reseed-functions` — re-seed functie-profielen

---

**Last updated:** 2026-04-15, phase 5d of retrieval-infra roadmap.
