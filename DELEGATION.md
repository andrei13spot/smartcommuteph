# SmartCommute PH — Prototype Sprint: Delegation & Timeline

**Group 11 · BSCS · PUP CCIS**
Companion to `Group11_Delegation_Timeline.xlsx` (the full sheet).

- **Goal:** a working prototype for the panel — revised target **end of August (Jul 13 – Aug 31)**.
- **Start:** Monday, **July 13, 2026** (kickoff meeting).
- **Weekly check-in:** every **Saturday** — remaining gates: **Aug 22, Aug 29**.
- **Hard deadline:** Monday, **August 31, 2026** (defense-ready, end of month).
- **Revision note (Aug 15):** original Aug 15 deadline moved — engine/data/statistics are done,
  but the frontend live-wiring, AHP survey weights, and full QA still need the extra two weeks.
- **Discipline:** strict. A task is not *done* until QA (Dave) signs off.

---

## Git workflow (everyone follows this)

**Branches**
- `main` — release / defense-ready. Only updated at Saturday gates, after QA sign-off.
- `dev` — integration branch. Everything merges here first.
- feature branches — **one per task**, always branched off `dev`.

**Before you start any task — always:**
```bash
git checkout dev
git pull origin dev
git checkout -b <branch>      # branch off the latest dev
```

**Branch naming** (`<area>/<short-task>`):
- Front end → `fe/route-query`, `fe/compare-view`
- Backend / algorithm → `be/astar-core`, `be/compare-endpoint`
- ML → `ml/ahp-weights`, `ml/lstm-ridership`
- QA / tests → `qa/comparison-check`

**While working:** commit small and often (lowercase messages); push your branch with `git push -u origin <branch>`.

**To merge:** open a Pull Request into `dev`. **Dave (QA) reviews and signs off before it merges into `dev`.** Delete the feature branch after merge.

**Releases:** `dev` → `main` only at the Saturday check-in gates, once QA has signed off. **Never commit directly to `main` or `dev` — always a feature branch + PR.**

---

## Roles

### Luis — Full Front End (Figma + Bootstrap 5)
Owns everything the user sees. Finalize the Figma from mockup v4, then build in Bootstrap 5.
- Network map render — 10 anchors, 3 rail lines, legend, stat chips (reused as base layer everywhere).
- Route query screen — origin/destination dropdowns (10 anchors), profile selector (4), submit, loading. **Validation:** origin ≠ destination, and both fields + a profile required before submit.
- Result view — selected-route map, "why this route", criteria rings, four headline stats (time, distance, fare, transfers).
- Comparison view — four profile cards, active-card highlight, transparency frame with the cost equation + metrics. **This is the money shot — polish it.**
- Design system — locked color tokens in one palette, all interactive states (default/hover/active/disabled/loading/empty/error), responsive mobile + desktop.
- **Copy fixes:** drop "reimagined" and "live PAGASA" → use **"PAGASA TenDay Forecast"** (feed is ten-day, not live). Framework voice, not app voice.
- **Handoff:** agree the API request/response shape with Andrei **before** wiring anything.

### Andrei — Backend Lead (Node + Express + A* core)
Owns the routing service and the algorithm contribution, **and the API contract** (finalize with Luis, document for Dave).
- Routing service — `POST /route` returns one route + KPIs; `POST /compare` runs all four profiles **plus baseline** → five results.
- Graph layer — load static attributes (fare, base travel time, distance, transfer flags) at startup; refresh dynamic edges (ridership, flood) at the start of each benchmark run.
- LSTM ridership model (TensorFlow + Keras) — 24-month window, eFOI contingency; input query timestamp → crowding per edge.
- RFR flood-risk model (scikit-learn) — input PAGASA TenDay Forecast → flood-risk score per edge.
- Multi-criteria A* — weighted cost from Equation 3; heuristic v_max = 60 km/h; mode speeds 40/60/30/20; penalty multiplier bounded **1.0–2.0**.
- Node-expansion counter inside the loop — **the pruning evidence**.
- Distance-based A* baseline — the locked comparison target (not the HAZMAT study).
- Transfer friction — TF′ from the 5×5 adjacency matrix.
- Benchmark harness — 45 OD × 4 profiles × 2 algorithms = **360 rows**.

### Princess — ML Components + Backend Support (Python)
- AHP weight derivation (Excel 365) — matrices from 150 valid respondents on Saaty 1–9, weights via normalized column average, **reject any respondent with CR ≥ 0.10**. Output four weight vectors → hand to Andrei.
- Graph layer support — static attrs + dynamic-edge refresh.
- Transfer friction — TF′ from the 5×5 matrix.
- LSTM/RFR support + training-data prep.
- Documentation.

### Dave — QA Lead + Data Pipeline Check
Final sign-off before anything merges.
- Functional QA — every tab/button on all four screens; dropdowns list all 10 anchors; profile selector has all 4; submit blocked on identical origin/destination or empty fields; loading + error states appear; routes render matching returned geometry.
- **Comparison check** — same OD genuinely produces different routes across the four profiles. If any two profiles return the same path, **flag it loud** (it's the core claim).
- **Data pipeline** — benchmark log writes exactly **360 rows** with all **8 KPIs** per row: travel time, distance, total fare (₱, with 20% student/senior discount where it applies), transfers, flood-risk score, ridership-density score, nodes expanded, execution time.
- **Pruning check** — framework nodes expanded < baseline on pruned queries. If it doesn't prune, **flag it** (that's the whole thesis).

---

## Timeline (revised Aug 15 — extended to end of August)

**Done as of Aug 15 (weeks 1–4):** full engine (multi-criteria A*, distance baseline,
node counter, transfer friction), `/route` + `/compare`, 264-node street-snapped graph,
official LRTA anchor coords, real MMDA flood labels, trained LSTM + RFR, 360-row
benchmark with the full Chapter-4 statistics (paired t-tests, Jaccard, RM-ANOVA),
UI screens + researcher/dev dashboards, QA round 1 report delivered.

| Sprint | Dates (2026) | Focus | Saturday gate |
|---|---|---|---|
| Week 5 | Aug 17 – 22 | **Luis:** QA-round-1 fixes (require origin+destination, no silent defaults, stuck loader on back-nav, dead "Learn more" links) + wire result view to live `/route`. **Princess:** AHP survey weights (150 respondents, reject CR ≥ 0.10) → hand 4 vectors to Andrei. **Andrei:** send PAGASA API letter; drop real weights into `profiles.py`; regenerate benchmark. **Dave:** re-test round-1 fixes as they land | **Aug 22 — validation fixed; result view live; real weights in the engine** |
| Week 6 | Aug 24 – 29 | **Luis:** wire compare view to live `/compare`; finish About page; copy fixes ("PAGASA TenDay Forecast"); error states. **Princess:** documentation (methodology, model cards, data sources). **Dave:** full QA — all screens, comparison check, 360-row/8-KPI pipeline check, pruning check → **sign-off**. **All:** freeze **Wed Aug 26**, then `dev → main`; defense deck + first dry run | **Aug 29 — ★ QA sign-off; frozen; defense-ready** |
| Buffer | Aug 31 | Final rehearsal + dry run, last fixes only — no new features | **Mon Aug 31 — ★ Hard deadline (end of month)** |

---

## API contract (starter — Andrei owns; lock with Luis before wiring)

**`POST /route`**
- Request: `{ origin: <anchorId>, destination: <anchorId>, profile: 'uncrowded'|'cheapest'|'safest'|'convenient' }`
- Validation: `origin != destination`; origin, destination, profile all required.
- Response: `{ profile, origin, destination, geometry: [[lat,lng]...], kpis: {...}, why_this_route, criteria: { T, F, R, P } }`

**`POST /compare`**
- Request: `{ origin, destination }`
- Response: `{ origin, destination, results: [ {profile: 'baseline'|<4 profiles>, geometry, kpis} ] }` → **5 results** (4 profiles + distance baseline).

**The 8 KPIs** (same block on every result / benchmark row):
1. travel_time_min · 2. distance_km · 3. fare_php *(20% student/senior discount where eligible)* · 4. transfers · 5. flood_risk_score · 6. ridership_density_score · 7. nodes_expanded · 8. exec_ms

**Benchmark log:** 45 OD × 4 profiles × 2 algorithms = **360 rows**; columns = `od_pair, profile, algorithm` + the 8 KPIs.
