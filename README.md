# SmartCommute PH

ML-driven multi-criteria A* for personalized commute routing in the Metro
Manila Cubao quadrant. Thesis prototype of Group 11 · BSCS · CCIS ·
Polytechnic University of the Philippines · 2026.

Four commuter profiles (Uncrowded, Cheapest, Safest, Convenient) weight four
criteria — ridership, fare, flood risk, transfer friction — inside a
constraint-aware A* over a 264-node transit graph (10 anchor stations + 300m
street-snapped jeepney stops), benchmarked against a distance-based A* baseline.

- **Setup guide:** [SETUP.md](SETUP.md) — step-by-step for every teammate
- **API contract:** [docs/api-contract.md](docs/api-contract.md)
- **Engine internals:** [backend/README.md](backend/README.md)
- **Team plan:** [DELEGATION.md](DELEGATION.md)

Quick run (two terminals):

```bash
cd backend && .venv\Scripts\activate && uvicorn app.main:app --port 8000
```

```bash
node gateway/server.js
```

Then open <http://127.0.0.1:8080>.
