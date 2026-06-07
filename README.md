# Flight Cost Intelligence — Backend API

Flask REST API for Indian domestic flight **cost-per-km** analysis.

| | |
|---|---|
| **Live API** | https://flight-cost-intelligence-api.onrender.com |
| **This repo** | https://github.com/pawankushwahh/Flight_per_km_backend |
| **Frontend** | https://pawankushwahh.github.io/Flight_per_km_cost/ |
| **Frontend repo** | https://github.com/pawankushwahh/Flight_per_km_cost |

This is a **standalone backend repo**. It is deployed on Render and serves the frontend on GitHub Pages.

---

## About

Exposes JSON REST endpoints for comparing Indian domestic routes by **₹ per kilometre**. Data comes from static CSV/JSON files loaded into memory at startup — no database.

Current dataset: ~118 routes, 26 airports. Trend and class data are synthetic until replaced with scraped fares.

---

## How it connects to the frontend

```
GitHub Pages (static HTML/JS)
        │
        ▼  fetch JSON (CORS enabled)
This API on Render
        │
        ▼  read once at worker startup
data/*.csv + data/*.json
```

The frontend reads `API_BASE_URL` from its own `config.js` and points to this API in production. CORS is enabled for all origins so GitHub Pages can call the API.

---

## Quick start (local)

```bash
git clone https://github.com/pawankushwahh/Flight_per_km_backend.git
cd Flight_per_km_backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

- API: http://127.0.0.1:5000
- Health: `GET /api/ping`
- Data cached at startup (restart after file changes)

To test with the UI, also clone and serve the [frontend repo](https://github.com/pawankushwahh/Flight_per_km_cost) on port 5500.

---

## Documentation in this repo

| File | Contents |
|------|----------|
| [README.md](README.md) | This file — API reference, setup, deploy |
| [docs/DATA.md](docs/DATA.md) | Data schemas, units, feature mapping |
| [docs/SCRAPING.md](docs/SCRAPING.md) | What to scrape, sources, formats, phased rollout |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Render deploy from GitHub, post-push checklist |
| [data/templates/](data/templates/) | CSV/JSON templates for scraper output |

---

## Deploy to Render

Push to this repo's `main` branch — Render auto-deploys if the service is linked.

```bash
git add .
git commit -m "Describe your changes"
git push origin main
```

Render runs `pip install -r requirements.txt` then `gunicorn -c gunicorn_config.py app:app`.

| Setting | Value |
|---------|-------|
| Health check | `/api/ping` |
| Port | `10000` (`gunicorn_config.py`) |
| Config | `render.yaml` |

Full guide: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

**After data changes:** push → wait for Render redeploy (~2–5 min) → workers reload cache.

### Coordinating with the frontend repo

| You changed… | Push this backend repo? | Push frontend repo? |
|--------------|:-----------------------:|:-------------------:|
| `app.py`, data files, `generate_data.py` | Yes | No |
| HTML, CSS, JS only | No | Yes |
| API + UI together | Yes (first) | Yes (after backend deploys) |

---

## Data files

```
data/
├── compare_data_new.csv      ← UPDATE FIRST (canonical route prices)
├── merged_flight_data.csv    ← UPDATE FIRST (airport coords + names)
├── compare_data.json         ← auto-generated
├── trend_data.json           ← auto-generated
├── class_layover_data.json   ← auto-generated
├── heatmap_data.json         ← auto-generated
└── nearby_airports.json      ← auto-generated
```

### Regenerate derived JSON

```bash
python scripts/generate_data.py          # write all JSON files
python scripts/generate_data.py --check  # coverage report only
```

### Replace dummy data with scraped data

1. Update `compare_data_new.csv` and `merged_flight_data.csv`
2. Run `python scripts/generate_data.py`
3. Optionally overwrite JSON with real scraped trends/class/nearby data
4. Push to GitHub → Render redeploys
5. Run `pytest tests/ -v`

See [docs/DATA.md](docs/DATA.md) for field specifications.

---

## API reference

All responses: `{ "success": true, "data": ... }` or `{ "success": false, "error": "..." }`.

| Method | Endpoint | Data source | Frontend page |
|--------|----------|-------------|---------------|
| `GET` | `/` | — | — |
| `GET` | `/api/ping` | — | All (warm-up) |
| `GET` | `/api/airports` | `merged_flight_data.csv` | All dropdowns |
| `POST` | `/api/compare` | `compare_data_new.csv` | Compare |
| `POST` | `/api/predict` | `trend_data.json` | Predictor |
| `POST` | `/api/route-find` | CSV + `trend_data.json` | Route Finder |
| `GET` | `/api/nearby-airports` | `nearby_airports.json` | Optimizer |
| `GET` | `/api/class-layover` | `class_layover_data.json` | Optimizer |
| `GET` | `/api/heatmap` | `heatmap_data.json` | Heatmap |
| `GET` | `/api/visualizations` | `compare_data_new.csv` | Visualizations, Home |
| `GET` | `/api/raw-compare-data` | CSV + JSON merged | Home popular routes |

`POST /api/compare` also returns `skipped` and `not_found` arrays for invalid or missing routes.

### Example requests

```bash
# Health
curl https://flight-cost-intelligence-api.onrender.com/api/ping

# Compare
curl -X POST -H "Content-Type: application/json" \
  -d '{"routes":[{"origin":"DEL","destination":"BOM"}]}' \
  http://127.0.0.1:5000/api/compare

# Enriched routes (home page)
curl "http://127.0.0.1:5000/api/raw-compare-data?limit=5"

# Predict
curl -X POST -H "Content-Type: application/json" \
  -d '{"origin":"DEL","destination":"BOM"}' \
  http://127.0.0.1:5000/api/predict

# Route finder
curl -X POST -H "Content-Type: application/json" \
  -d '{"findBestRoutes":true,"origin":"DEL"}' \
  http://127.0.0.1:5000/api/route-find
```

### `/api/raw-compare-data` response

Each route merges CSV pricing with JSON coordinates:

```json
{
  "success": true,
  "data": {
    "routes": [{
      "origin": "DEL",
      "destination": "BOM",
      "distance": 1290.5,
      "price": 11435,
      "cost_per_km": 8.86,
      "origin_lat": 28.5665,
      "origin_lon": 77.1031,
      "destination_lat": 19.0887,
      "destination_lon": 72.8679,
      "airline": "IndiGo"
    }]
  }
}
```

---

## Project layout

```
├── app.py
├── gunicorn_config.py
├── Procfile
├── render.yaml
├── requirements.txt
├── scripts/
│   └── generate_data.py
├── docs/
│   ├── DATA.md
│   └── DEPLOYMENT.md
├── data/
│   ├── *.csv / *.json
│   └── templates/
└── tests/
    ├── conftest.py
    └── test_api.py
```

---

## Tech stack

- Python 3.9+
- Flask + flask-cors
- Gunicorn + gevent (production)
- No database — in-memory cache at startup

---

## Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

12 smoke tests cover all endpoints.

---

## Notes

- All prices in INR (₹); `cost_per_km` in ₹/km
- Predictor uses trend averages from `trend_data.json` — not machine learning
- CORS enabled for all origins (required for GitHub Pages frontend)
- Country hardcoded to `"India"` in `/api/airports`
- Render free tier may cold-start (30–60 s on first request after idle)

---

## Team

| Name | GitHub |
|------|--------|
| Pawan Kushwah | [@pawankushwahh](https://github.com/pawankushwahh) |
| Rakshita | [@Rakshita-0206](https://github.com/Rakshita-0206) |
| Shalini | — |

Lucknow, India
