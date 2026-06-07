# Data Guide — Flight Cost Intelligence Backend

This document describes every data file the backend uses: what each feature needs, exact field formats, units, and how to replace dummy data with scraped originals. For a full scraping guide (sources, formats, phased rollout), see [SCRAPING.md](SCRAPING.md).

**Related docs:**

| Document | Purpose |
|----------|---------|
| [../README.md](../README.md) | API reference and local setup |
| [SCRAPING.md](SCRAPING.md) | **What to scrape, from where, and in which format** |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Push to GitHub → Render auto-deploy |
| [../data/templates/README.md](../data/templates/README.md) | Scraper output templates |

**After updating data:** run `python scripts/generate_data.py`, push to GitHub, wait for Render redeploy.

---

## Architecture (no database)

The backend has **no database or external API calls at runtime**. All responses come from static files in `data/`, loaded into an in-memory cache when the server starts.

```
Canonical CSVs (scrape these first)
  compare_data_new.csv
  merged_flight_data.csv
        │
        ▼  python scripts/generate_data.py
Derived JSON (scrape individually, or auto-generate as placeholders)
  compare_data.json
  trend_data.json
  class_layover_data.json
  nearby_airports.json
  heatmap_data.json
        │
        ▼  Flask app.py (cached at startup)
  /api/* endpoints → frontend pages
```

**Current dataset:** ~118 directed routes, ~26 airports. The two CSVs are the canonical pricing source. Most JSON files are **synthetic** (seasonal multipliers, cabin multipliers, nearest-airport math) until replaced with scraped data.

---

## Overview

```
data/
├── compare_data_new.csv      ← CANONICAL: scrape/update this first
├── merged_flight_data.csv    ← CANONICAL: airport names + coordinates
├── compare_data.json         ← derived (coords + airline for maps)
├── trend_data.json           ← derived (monthly/weekly price trends)
├── class_layover_data.json   ← derived (cabin classes + layovers)
├── heatmap_data.json         ← derived (regional cost aggregates)
├── nearby_airports.json      ← derived (geographic airport alternatives)
└── templates/                ← empty templates for your scraper output
```

**Units (always):**

| Field | Unit | Typical range |
|-------|------|---------------|
| `Price`, `avg_price` | INR (₹) | 3,000 – 70,000 |
| `Distance`, `distance_km` | kilometres | 200 – 3,000 |
| `CostPerKm`, `cost_per_km` | ₹/km | 4 – 30 |
| `lat` / `lon` | decimal degrees | India: lat 8–35, lon 68–97 |
| IATA codes | 3 uppercase letters | `DEL`, `BOM`, `BLR` |

---

## Feature → data mapping

| Frontend page | API endpoint | Primary data file |
|---------------|--------------|-------------------|
| Airport dropdowns (all pages) | `GET /api/airports` | `merged_flight_data.csv` |
| Route Compare | `POST /api/compare` | `compare_data_new.csv` |
| Compare map | (same + coords) | `compare_data.json` |
| Home popular routes | `GET /api/raw-compare-data` (fallback: `/api/visualizations`) | CSV + JSON merged by API |
| Price Predictor | `POST /api/predict` | `trend_data.json` |
| Route Finder | `POST /api/route-find` | `compare_data_new.csv` + `trend_data.json` |
| Optimizer — Nearby | `GET /api/nearby-airports` | `nearby_airports.json` |
| Optimizer — Classes/Layovers | `GET /api/class-layover` | `class_layover_data.json` |
| Heatmap | `GET /api/heatmap` | `heatmap_data.json` |
| Visualizations | `GET /api/visualizations` | `compare_data_new.csv` |

---

## 1. `compare_data_new.csv` (canonical routes)

**One row per directed route.** This is the single source of truth for pricing.

### Columns

| Column | Type | Required | Example | Notes |
|--------|------|----------|---------|-------|
| `Start` | string | yes | `DEL` | Origin IATA (3 letters, uppercase) |
| `End` | string | yes | `BOM` | Destination IATA |
| `Distance` | float | yes | `1290.5` | Great-circle or route distance in km |
| `CostPerKm` | float | yes | `8.86` | Should equal `Price / Distance` |
| `Price` | float | yes | `11435` | Economy ticket price in INR |

### Example

```csv
Start,End,Distance,CostPerKm,Price
DEL,BOM,1290.5,8.86,11435
BOM,DEL,1285.2,9.12,11720
```

### Used by

- `/api/compare` — sorts routes by `cost_per_km`
- `/api/visualizations` — cheapest/expensive rankings, city averages
- `/api/route-find` — all destinations from an origin
- `/api/raw-compare-data` — merged with JSON for home page

---

## 2. `merged_flight_data.csv` (airports + route metadata)

Same routes as compare CSV, but with full airport details for maps and dropdowns.

### Columns

| Column | Type | Required | Example |
|--------|------|----------|---------|
| `Start_IATA` | string | yes | `DEL` |
| `Start_Airport` | string | yes | `Indira Gandhi International Airport` |
| `Start_Lat` | float | yes | `28.5665` |
| `Start_Lon` | float | yes | `77.1031` |
| `End_IATA` | string | yes | `BOM` |
| `End_Airport` | string | yes | `Chhatrapati Shivaji International Airport` |
| `End_Lat` | float | yes | `19.0887` |
| `End_Lon` | float | yes | `72.8679` |
| `Distance` | float | yes | `1290.5` |
| `CostPerKm` | float | yes | `8.86` |
| `Price` | float | yes | `11435` |
| `Start_City` | string | yes | `Delhi` |
| `End_City` | string | yes | `Mumbai` |

### Used by

- `/api/airports` — deduplicates all unique IATA codes with lat/lon
- Data generation script — builds coords for `compare_data.json` and heatmap regions

---

## 3. `compare_data.json` (map coordinates + airline)

**Derived from CSV + merged CSV.** Provides lat/lon for Leaflet map polylines.

### Schema

```json
{
  "routes": [
    {
      "origin": "DEL",
      "destination": "BOM",
      "origin_lat": 28.5665,
      "origin_lon": 77.1031,
      "destination_lat": 19.0887,
      "destination_lon": 72.8679,
      "price": 11435,
      "airline": "IndiGo"
    }
  ]
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `origin`, `destination` | yes | Must match CSV `Start`/`End` |
| `origin_lat`, `origin_lon`, `destination_lat`, `destination_lon` | yes for maps | From merged CSV |
| `price` | yes | Integer INR |
| `airline` | optional | e.g. `IndiGo`, `Air India`, `SpiceJet` |

When you scrape real data, update coords and airline here (or re-run the generator).

### `/api/raw-compare-data` — enriched API response

The API does **not** return `compare_data.json` as-is. It merges CSV metrics with JSON coords via `_enriched_routes()` in `app.py`:

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

**Required for home page Popular Routes:** `distance`, `price`, `cost_per_km`.

**Frontend fallback:** If `cost_per_km` is missing (older deployed API), the home page in the [frontend repo](https://github.com/pawankushwahh/Flight_per_km_cost) calls `/api/visualizations?limit=12` and uses `topCheapestRoutes` instead.

---

## 4. `trend_data.json` (price predictor)

One entry per route. Powers monthly trends, booking advice, and savings %.

### Schema

```json
{
  "routes": [
    {
      "origin": "DEL",
      "destination": "BOM",
      "monthly_trends": [
        { "month": "January",  "avg_price": 10524, "avg_cost_per_km": 8.15 },
        { "month": "February", "avg_price": 10072, "avg_cost_per_km": 7.80 }
      ],
      "weekly_trends": [
        { "week": "31-60 days before", "avg_price": 10290, "avg_cost_per_km": 7.97 }
      ],
      "best_travel_month": "February",
      "best_booking_time": "31-60 days before"
    }
  ]
}
```

| Field | Notes |
|-------|-------|
| `month` | Full English name: `"January"` not `"Jan"` |
| `avg_price` | INR — same scale as CSV `Price` |
| `avg_cost_per_km` | `avg_price / route_distance` |
| `weekly_trends[].week` | Free-text label, e.g. `"8-14 days before"` |
| `best_travel_month` | Month with lowest `avg_price` |
| `best_booking_time` | Week with lowest `avg_price` |

**Coverage:** Every route in compare CSV should have a matching entry, or `/api/predict` returns 404.

**Current dummy data:** Seasonal multipliers applied to CSV base price. Replace with scraped historical fares when available.

---

## 5. `class_layover_data.json` (optimizer)

One entry per route. Powers cabin-class comparison and layover options.

### Schema

```json
{
  "routes": [
    {
      "origin": "DEL",
      "destination": "BOM",
      "distance_km": 1290.5,
      "direct_flight": {
        "economy":         { "price": 11435, "cost_per_km": 8.86,  "duration_hours": 1.7 },
        "premium_economy": { "price": 17152, "cost_per_km": 13.29, "duration_hours": 1.7 },
        "business":        { "price": 33161, "cost_per_km": 25.69, "duration_hours": 1.7 },
        "first":           { "price": 57175, "cost_per_km": 44.32, "duration_hours": 1.7 }
      },
      "layover_options": [
        {
          "via": "JAI",
          "economy": {
            "price": 10520,
            "cost_per_km": 8.08,
            "duration_hours": 3.2,
            "layover_hours": 1.0
          },
          "premium_economy": { "..." : "..." },
          "business": { "..." : "..." },
          "first": { "..." : "..." }
        }
      ]
    }
  ]
}
```

| Field | Notes |
|-------|-------|
| `direct_flight` | Object keyed by cabin — **not** an array |
| Cabin keys | `economy`, `premium_economy`, `business`, `first` |
| `layover_options[].via` | Hub airport IATA |
| `layover_hours` | Only on layover cabin objects |

**Current dummy data:** Economy from CSV; other cabins use multipliers. Replace with scraped class fares.

---

## 6. `nearby_airports.json` (optimizer — nearby tab)

Airport-centric (not route-centric). Both origin and destination must exist here.

### Schema

```json
{
  "airports": [
    {
      "code": "DEL",
      "name": "Indira Gandhi International Airport",
      "city": "Delhi",
      "country": "India",
      "lat": 28.5665,
      "lon": 77.1031,
      "nearby": [
        {
          "code": "IXC",
          "name": "Chandigarh Airport",
          "city": "Chandigarh",
          "country": "India",
          "lat": 30.6735,
          "lon": 76.7885,
          "distance": 260,
          "avg_cost_difference": 2.3
        }
      ]
    }
  ]
}
```

| Field | Notes |
|-------|-------|
| `nearby` | Array key name (not `nearby_airports`) |
| `distance` | km between airports (not `distance_km`) |
| `avg_cost_difference` | ₹/km difference vs using the main airport |

**Current dummy data:** 2–4 geographically nearest airports per code. Replace with scraped alternative-airport analysis.

---

## 7. `heatmap_data.json` (cost heatmap)

Nested regional structure. API flattens to `data.routes[]` for the frontend map.

### Schema

```json
{
  "regions": [
    {
      "name": "North India",
      "avg_cost_per_km": 12.5,
      "states": [
        {
          "name": "Delhi",
          "code": "DE",
          "avg_cost_per_km": 11.2,
          "routes": [
            { "from": "DEL", "to": "BOM", "cost_per_km": 8.86 }
          ]
        }
      ]
    }
  ]
}
```

| Field | Notes |
|-------|-------|
| `from`, `to` | IATA codes in stored file |
| `cost_per_km` | ₹/km — map colour scale expects ~4–28 |

**Current dummy data:** Grouped by origin city from merged CSV. Replace or keep — auto-regenerated from CSV.

---

## Workflow: replacing dummy data with scraped data

> **Full scraping guide:** See [SCRAPING.md](SCRAPING.md) for per-feature scrape requirements, suggested sources, phased rollout, and coverage rules.

### Step 1 — Scrape and update canonical CSVs

1. Fill `data/templates/compare_data_new.template.csv` format → save as `compare_data_new.csv`
2. Fill `data/templates/merged_flight_data.template.csv` → save as `merged_flight_data.csv`

Ensure every route in compare CSV has a matching row in merged CSV with coordinates.

### Step 2 — Regenerate derived JSON

```bash
cd backend
python scripts/generate_data.py
```

This rebuilds all five JSON files from the CSVs with realistic dummy trends, classes, nearby airports, and heatmap data.

### Step 3 — Optionally replace derived JSON with scraped originals

As you scrape real data, overwrite individual JSON files:

| File | Scrape from |
|------|-------------|
| `trend_data.json` | Historical monthly fares per route |
| `class_layover_data.json` | Airline booking sites (economy/business prices) |
| `nearby_airports.json` | Alternative airport cost analysis |
| `compare_data.json` | Update `airline` field from booking data |
| `heatmap_data.json` | Can stay auto-generated from CSV |

### Step 4 — Restart the server

Data is cached at startup. After any file change:

```bash
# Development
python app.py

# Production — redeploy or restart gunicorn workers
```

### Step 5 — Verify coverage

```bash
python scripts/generate_data.py --check
pytest tests/ -v
```

---

## Templates

See `data/templates/` for copy-paste starter files:

- `compare_data_new.template.csv`
- `merged_flight_data.template.csv`
- `compare_data.template.json`
- `trend_data.template.json`
- `class_layover.template.json`
- `nearby_airports.template.json`
- `heatmap_data.template.json`

---

## API response shapes (for scraper validation)

After loading your data, these curl commands should return `success: true`:

```bash
# Health
curl http://localhost:5000/api/ping

# Compare
curl -X POST -H "Content-Type: application/json" \
  -d '{"routes":[{"origin":"DEL","destination":"BOM"}]}' \
  http://localhost:5000/api/compare

# Predict (needs trend_data entry)
curl -X POST -H "Content-Type: application/json" \
  -d '{"origin":"DEL","destination":"BOM"}' \
  http://localhost:5000/api/predict

# Nearby (both airports must be in nearby_airports.json)
curl "http://localhost:5000/api/nearby-airports?origin=DEL&destination=BOM"

# Class/layover (route must be in class_layover_data.json)
curl "http://localhost:5000/api/class-layover?origin=DEL&destination=BOM"

# Heatmap
curl http://localhost:5000/api/heatmap

# Enriched routes (home page)
curl "http://localhost:5000/api/raw-compare-data?limit=10"
```
