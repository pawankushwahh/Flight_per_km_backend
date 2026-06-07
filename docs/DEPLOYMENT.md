# Backend Deployment — Render

## Live service

| What | URL |
|------|-----|
| API base | https://flight-cost-intelligence-api.onrender.com |
| Health check | https://flight-cost-intelligence-api.onrender.com/api/ping |
| Repo | https://github.com/pawankushwahh/Flight_per_km_backend |
| Frontend (consumes this API) | https://pawankushwahh.github.io/Flight_per_km_cost/ |

---

## How auto-deploy works

```
You push to GitHub (main branch)
        │
        ▼
Render detects commit (autoDeploy: true in render.yaml)
        │
        ▼
pip install -r requirements.txt
        │
        ▼
gunicorn -c gunicorn_config.py app:app
        │
        ▼
Health check passes on GET /api/ping
        │
        ▼
API live — frontend on GitHub Pages calls it automatically
```

---

## Push updated backend

From your `Flight_per_km_backend` repo root:

```bash
git status
git add .
git commit -m "Describe your changes"
git push origin main
```

This repo is standalone — push only to https://github.com/pawankushwahh/Flight_per_km_backend

Monitor deploy in the [Render dashboard](https://dashboard.render.com) → your service → **Events**.

Typical deploy time: 2–5 minutes.

---

## Render configuration

Defined in [`render.yaml`](../render.yaml):

| Setting | Value |
|---------|-------|
| Service name | `flight-cost-intelligence-api` |
| Runtime | Python 3.9 |
| Build | `pip install -r requirements.txt` |
| Start | `gunicorn -c gunicorn_config.py app:app` |
| Health check path | `/api/ping` |
| Auto deploy | `true` |

Production server binds to `0.0.0.0:10000` (see [`gunicorn_config.py`](../gunicorn_config.py)).

---

## When you change data files

Data is cached when each Gunicorn worker starts. To load new CSV/JSON:

1. Edit files in `data/` (or run `python scripts/generate_data.py`)
2. Commit and push to GitHub
3. Wait for Render redeploy — workers restart and reload cache

No separate database migration needed.

### Recommended data update workflow

```bash
# 1. Edit canonical CSVs
vim data/compare_data_new.csv
vim data/merged_flight_data.csv

# 2. Regenerate JSON
python scripts/generate_data.py --check
python scripts/generate_data.py

# 3. Test locally
pytest tests/ -v
python app.py

# 4. Push
git add data/ scripts/
git commit -m "Update flight data"
git push origin main
```

---

## Post-deploy checklist

```bash
# Health
curl https://flight-cost-intelligence-api.onrender.com/api/ping

# Enriched routes (must include distance + cost_per_km)
curl "https://flight-cost-intelligence-api.onrender.com/api/raw-compare-data?limit=2"

# Compare
curl -X POST -H "Content-Type: application/json" \
  -d '{"routes":[{"origin":"DEL","destination":"BOM"}]}' \
  https://flight-cost-intelligence-api.onrender.com/api/compare
```

Then verify the live frontend:

- https://pawankushwahh.github.io/Flight_per_km_cost/ — Popular Routes grid loads
- Compare, Predictor, Route Finder all return data

---

## Cold starts (free tier)

Render free tier spins down after ~15 minutes of inactivity. First request after idle may take **30–60 seconds**.

Mitigations already in place:

- Frontend pings `/api/ping` on load (see [Flight_per_km_cost](https://github.com/pawankushwahh/Flight_per_km_cost) → `assets/js/common.js`)
- Render health check on `/api/ping`
- Optional: use [UptimeRobot](https://uptimerobot.com) to ping `/api/ping` every 10 minutes

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Deploy fails health check | Ensure `render.yaml` has `healthCheckPath: /api/ping` and `app.py` has the `/api/ping` route |
| 502 / timeout on first request | Cold start — wait 60 s and retry |
| Home page empty routes on live site | Push latest `app.py` with enriched `/api/raw-compare-data`; or frontend falls back to `/api/visualizations` |
| CORS errors from GitHub Pages | `flask-cors` must be installed and `CORS(app)` in `app.py` |
| Data not updating after push | Confirm Render deploy succeeded; data only reloads on worker restart |

---

## Manual deploy trigger

In Render dashboard: **Manual Deploy → Deploy latest commit**

---

## Rollback

```bash
git revert HEAD
git push origin main
```

Or in Render: **Rollback** to a previous successful deploy.
