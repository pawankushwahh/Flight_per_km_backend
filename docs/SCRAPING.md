# Scraping Guide — Flight Cost Intelligence Backend

This document describes **what data to scrape**, **from where**, and **in which format** so every frontend feature works on real data instead of synthetic placeholders.

For exact field schemas and API response shapes, see [DATA.md](DATA.md). For copy-paste output templates, see [../data/templates/](../data/templates/).

**After updating data:** run `python scripts/generate_data.py`, push to GitHub, wait for Render redeploy.

---

## How the data layer works

There is **no database**. All API responses come from static files in `data/`, loaded into memory at server startup.

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

**Units everywhere:**

| Field | Unit | Typical range |
|-------|------|---------------|
| `Price`, `avg_price` | INR (₹) | 3,000 – 70,000 |
| `Distance`, `distance_km` | kilometres | 200 – 3,000 |
| `CostPerKm`, `cost_per_km` | ₹/km | 4 – 30 |
| `lat` / `lon` | decimal degrees | India: lat 8–35, lon 68–97 |
| IATA codes | 3 uppercase letters | `DEL`, `BOM`, `BLR` |

---

## Priority order

| Priority | File | Scrape? | Powers |
|----------|------|---------|--------|
| **1** | `compare_data_new.csv` | **Yes — required** | Compare, Route Finder, Visualizations, Home stats |
| **2** | `merged_flight_data.csv` | **Yes — required** | Airport dropdowns, maps, heatmap grouping |
| **3** | `trend_data.json` | **Yes for real Predictor** | Price Predictor, Route Finder “best month” |
| **4** | `class_layover_data.json` | **Yes for real Optimizer** | Cabin classes + layover tab |
| **5** | `nearby_airports.json` | **Yes for real Optimizer** | Nearby airports tab |
| **6** | `compare_data.json` | Partial | Map airline labels (coords come from merged CSV) |
| **7** | `heatmap_data.json` | Optional | Auto-generated from CSV — no scrape needed |

After updating the two CSVs, regenerate derived files:

```bash
cd backend
python scripts/generate_data.py
```

Overwrite individual JSON files with scraped data as you collect it.

---

## Feature → scrape mapping

| Frontend page | API endpoint | Data file | Scrape required? |
|---------------|--------------|-----------|------------------|
| Airport dropdowns (all pages) | `GET /api/airports` | `merged_flight_data.csv` | Yes |
| Route Compare | `POST /api/compare` | `compare_data_new.csv` | Yes |
| Compare map | (merged API response) | `compare_data.json` | Partial (airline) |
| Home popular routes | `GET /api/raw-compare-data` | CSV + JSON | Yes |
| Price Predictor | `POST /api/predict` | `trend_data.json` | Yes |
| Route Finder | `POST /api/route-find` | CSV + `trend_data.json` | Yes |
| Optimizer — Nearby | `GET /api/nearby-airports` | `nearby_airports.json` | Yes |
| Optimizer — Classes/Layovers | `GET /api/class-layover` | `class_layover_data.json` | Yes |
| Heatmap | `GET /api/heatmap` | `heatmap_data.json` | No (auto-generated) |
| Visualizations | `GET /api/visualizations` | `compare_data_new.csv` | Yes |
| FAQ / 404 | — | — | No (static HTML) |

---

## 1. Airport metadata (all pages)

**API:** `GET /api/airports`  
**File:** `merged_flight_data.csv`  
**Template:** `data/templates/merged_flight_data.template.csv`

### What to scrape

Airport metadata for every IATA code that appears in any route.

| Column | Type | Example | Source |
|--------|------|---------|--------|
| `Start_IATA` / `End_IATA` | string | `DEL` | IATA registry, [OurAirports](https://ourairports.com/data/), OpenFlights |
| `Start_Airport` / `End_Airport` | string | `Indira Gandhi International Airport` | Same |
| `Start_Lat`, `Start_Lon`, `End_Lat`, `End_Lon` | float | `28.5665`, `77.1031` | Same |
| `Start_City` / `End_City` | string | `Delhi` | Same |
| `Distance`, `CostPerKm`, `Price` | float | per route | From route price scrape (see §2) |

### Format

```csv
Start_IATA,Start_Airport,Start_Lat,Start_Lon,End_IATA,End_Airport,End_Lat,End_Lon,Distance,CostPerKm,Price,Start_City,End_City
DEL,Indira Gandhi International Airport,28.5665,77.1031,BOM,Chhatrapati Shivaji International Airport,19.0887,72.8679,1290.5,8.86,11435,Delhi,Mumbai
```

**Coverage:** Every airport in `compare_data_new.csv` must have coordinates in this file.

---

## 2. Route prices (Compare, Home, Visualizations, Route Finder)

**APIs:** `POST /api/compare`, `GET /api/visualizations`, `GET /api/raw-compare-data`, `POST /api/route-find`  
**File:** `compare_data_new.csv`  
**Template:** `data/templates/compare_data_new.template.csv`

### What to scrape per route

| Field | What it means | How to get it |
|-------|---------------|---------------|
| `Start` | Origin IATA | Route query |
| `End` | Destination IATA | Route query |
| `Price` | Cheapest **economy** fare in INR | Lowest across major airlines |
| `Distance` | Route distance in km | Haversine from airport coords, or scraped |
| `CostPerKm` | ₹/km | **Must equal** `Price / Distance` |

### Format

```csv
Start,End,Distance,CostPerKm,Price
DEL,BOM,1290.5,8.86,11435
BOM,DEL,1285.2,9.12,11720
```

**Notes:**

- One row per **directed** route (`DEL→BOM` and `BOM→DEL` are separate rows).
- Use a consistent booking window (e.g. 30–45 days before departure).
- Suggested sources: Google Flights, Skyscanner, MakeMyTrip, Cleartrip, Kayak. Respect site ToS; prefer official APIs where available.

### Map airline label (`compare_data.json`)

Scrape the airline offering the lowest fare for each route.

```json
{
  "routes": [{
    "origin": "DEL",
    "destination": "BOM",
    "origin_lat": 28.5665,
    "origin_lon": 77.1031,
    "destination_lat": 19.0887,
    "destination_lon": 72.8679,
    "price": 11435,
    "airline": "IndiGo"
  }]
}
```

Coords come from `merged_flight_data.csv` — only `airline` needs a separate scrape (or re-run `generate_data.py` for a placeholder).

---

## 3. Price trends (Predictor)

**API:** `POST /api/predict`  
**File:** `trend_data.json`  
**Template:** `data/templates/trend_data.template.json`

### What to scrape per route

| Field | Format | What to scrape |
|-------|--------|----------------|
| `monthly_trends[]` | 12 entries | Avg economy price per calendar month |
| `monthly_trends[].month` | `"January"` … `"December"` | Full English name, not `Jan` |
| `monthly_trends[].avg_price` | INR | Avg fare that month |
| `monthly_trends[].avg_cost_per_km` | ₹/km | `avg_price / route_distance` |
| `weekly_trends[]` | 4–6 entries | Price vs booking lead time |
| `weekly_trends[].week` | `"31-60 days before"` | Free-text label |
| `best_travel_month` | `"February"` | Month with lowest `avg_price` |
| `best_booking_time` | `"31-60 days before"` | Week with lowest `avg_price` |

### Scrape strategy

1. **Monthly trends:** For each route, query prices across 12 months (same day-of-week, ~30 days out).
2. **Booking windows:** For one reference month, query at 1–7, 8–14, 15–21, 22–30, 31–60, and 61–90 days before departure.

### Format

```json
{
  "routes": [{
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
  }]
}
```

**Coverage:** Every route in `compare_data_new.csv` needs a matching entry, or `/api/predict` returns **404**.

**Suggested sources:** Skyscanner “whole month” view, Google Flights calendar, Hopper-style price APIs.

---

## 4. Nearby airports (Optimizer)

**API:** `GET /api/nearby-airports?origin=DEL&destination=BOM`  
**File:** `nearby_airports.json`  
**Template:** `data/templates/nearby_airports.template.json`

### What to scrape per airport

This file is **airport-centric**, not route-centric.

| Field | Example | What to scrape |
|-------|---------|----------------|
| `code`, `name`, `city`, `country`, `lat`, `lon` | `DEL`, Delhi… | Airport metadata |
| `nearby[]` | 2–4 alternatives | Airports within ~300 km |
| `nearby[].code`, `name`, `city`, `lat`, `lon` | `IXC` | Alternative airport |
| `nearby[].distance` | `260` | km to main airport (key is `distance`, not `distance_km`) |
| `nearby[].avg_cost_difference` | `2.3` | ₹/km savings vs using the main airport |

### Computing `avg_cost_difference`

1. Scrape price for main airport route (e.g. `DEL→BOM`).
2. Scrape price for alternative route (e.g. `IXC→BOM`).
3. `avg_cost_difference = cost_per_km(main) - cost_per_km(alternative)`.

### Format

```json
{
  "airports": [{
    "code": "DEL",
    "name": "Indira Gandhi International Airport",
    "city": "Delhi",
    "country": "India",
    "lat": 28.5665,
    "lon": 77.1031,
    "nearby": [{
      "code": "IXC",
      "name": "Chandigarh Airport",
      "city": "Chandigarh",
      "country": "India",
      "lat": 30.6735,
      "lon": 76.7885,
      "distance": 260,
      "avg_cost_difference": 2.3
    }]
  }]
}
```

**Coverage:** Both **origin and destination** must exist in this file, or the API returns **404**.

---

## 5. Cabin classes and layovers (Optimizer)

**API:** `GET /api/class-layover?origin=DEL&destination=BOM`  
**File:** `class_layover_data.json`  
**Template:** `data/templates/class_layover.template.json`

### What to scrape per route

**Direct flight** — object keyed by cabin (not an array):

| Cabin key | Fields | Example |
|-----------|--------|---------|
| `economy` | `price`, `cost_per_km`, `duration_hours` | `11435`, `8.86`, `1.7` |
| `premium_economy` | same | |
| `business` | same | |
| `first` | same | |

**Layover options** (1-stop):

| Field | Example | What to scrape |
|-------|---------|----------------|
| `via` | `JAI` | Hub/stopover airport IATA |
| `economy.price` | `10520` | 1-stop economy fare |
| `economy.duration_hours` | `3.2` | Total flight time |
| `economy.layover_hours` | `1.0` | Wait time at hub |
| `economy.cost_per_km` | `8.08` | `price / distance_km` |
| Same for `premium_economy`, `business`, `first` | | |

### Format

```json
{
  "routes": [{
    "origin": "DEL",
    "destination": "BOM",
    "distance_km": 1290.5,
    "direct_flight": {
      "economy":         { "price": 11435, "cost_per_km": 8.86,  "duration_hours": 1.7 },
      "premium_economy": { "price": 17152, "cost_per_km": 13.29, "duration_hours": 1.7 },
      "business":        { "price": 33161, "cost_per_km": 25.69, "duration_hours": 1.7 },
      "first":           { "price": 57175, "cost_per_km": 44.32, "duration_hours": 1.7 }
    },
    "layover_options": [{
      "via": "JAI",
      "economy": {
        "price": 10520,
        "cost_per_km": 8.08,
        "duration_hours": 3.2,
        "layover_hours": 1.0
      }
    }]
  }]
}
```

**Suggested sources:** Airline sites (IndiGo, Air India, Vistara) or aggregators with cabin and stop filters.

**Coverage:** One entry per route in compare CSV, or `/api/class-layover` returns **404**.

---

## 6. Heatmap (no scrape needed)

**API:** `GET /api/heatmap`  
**File:** `heatmap_data.json`

Auto-generated by `generate_data.py` from the canonical CSVs. Groups routes by region (North/West/South/East/Central India). Only scrape manually if you need custom regional groupings.

---

## Suggested data sources

| Data needed | Good sources | Notes |
|-------------|--------------|-------|
| Airport IATA, name, lat/lon | [OurAirports](https://ourairports.com/data/), OpenFlights | Free, stable |
| Route distance | Haversine from coords | No scrape if you have coordinates |
| Current economy price | Skyscanner, Google Flights, MakeMyTrip, Cleartrip, Kayak | Respect ToS |
| Monthly historical prices | Skyscanner “whole month”, Google Flights calendar | 12 points per route |
| Booking lead-time prices | Same route at different departure offsets | 6 windows per route |
| Cabin class prices | Airline sites, Kayak cabin filter | 4 cabins × direct + layover |
| Layover routes | “1 stop” filter on aggregators | Record `via`, duration, layover time |
| Airline name | Site returning the lowest fare | One per route |
| Nearby airports | OurAirports + price comparison | Geographic + economic analysis |

---

## Minimum scrape scope

For the current **118 routes / ~26 airports**:

| Dataset | Volume | Effort |
|---------|--------|--------|
| Airport metadata | ~26 airports | Low (one-time) |
| Route prices (CSV) | 118 routes × 1 price | Medium |
| Monthly trends | 118 routes × 12 months | High |
| Booking windows | 118 routes × 6 windows | High |
| Cabin classes (direct) | 118 routes × 4 cabins | High |
| Layover options | 118 routes × 2–3 hubs × 4 cabins | Very high |
| Nearby airports | ~26 airports × 3 alternatives | Medium–high |

### Phased approach

1. **Phase 1** — Scrape `compare_data_new.csv` + `merged_flight_data.csv` → run `generate_data.py` (unblocks Compare, Home, Visualizations, Route Finder base).
2. **Phase 2** — Scrape `trend_data.json` for top 20–30 busiest routes (real Predictor).
3. **Phase 3** — Scrape `class_layover_data.json` + `nearby_airports.json` for same routes (real Optimizer).
4. **Phase 4** — Expand coverage route by route.

---

## Coverage rules

| Rule | Consequence if violated |
|------|-------------------------|
| Every `Start`/`End` in compare CSV exists in merged CSV with coords | Maps and dropdowns break |
| Every compare route has `trend_data.json` entry | Predictor returns 404 |
| Every compare route has `class_layover_data.json` entry | Optimizer class/layover returns 404 |
| Both origin and destination in `nearby_airports.json` | Nearby tab returns 404 |
| `CostPerKm = Price / Distance` | Sorting and rankings wrong |
| IATA codes: exactly 3 uppercase letters | API validation rejects input |
| Month names: full English (`"February"`) | Predictor chart labels break |

---

## Workflow after scraping

### Step 1 — Save canonical CSVs

1. Scraper output in `compare_data_new.template.csv` format → `data/compare_data_new.csv`
2. Scraper output in `merged_flight_data.template.csv` format → `data/merged_flight_data.csv`

### Step 2 — Regenerate derived JSON

```bash
cd backend
python scripts/generate_data.py
```

### Step 3 — Overwrite JSON with scraped data (optional)

| File | Replace when you have… |
|------|------------------------|
| `trend_data.json` | Historical monthly + booking-window fares |
| `class_layover_data.json` | Cabin and layover prices |
| `nearby_airports.json` | Alternative airport analysis |
| `compare_data.json` | Real airline names from booking data |
| `heatmap_data.json` | Can stay auto-generated |

### Step 4 — Restart the server

Data is cached at startup. After any file change:

```bash
python app.py                    # development
# or redeploy / restart gunicorn on Render
```

### Step 5 — Verify

```bash
python scripts/generate_data.py --check
pytest tests/ -v
```

### Step 6 — Validate endpoints

```bash
curl http://localhost:5000/api/ping

curl -X POST -H "Content-Type: application/json" \
  -d '{"routes":[{"origin":"DEL","destination":"BOM"}]}' \
  http://localhost:5000/api/compare

curl -X POST -H "Content-Type: application/json" \
  -d '{"origin":"DEL","destination":"BOM"}' \
  http://localhost:5000/api/predict

curl "http://localhost:5000/api/nearby-airports?origin=DEL&destination=BOM"
curl "http://localhost:5000/api/class-layover?origin=DEL&destination=BOM"
curl http://localhost:5000/api/heatmap
curl "http://localhost:5000/api/raw-compare-data?limit=10"
```

All should return `"success": true` for routes present in your data files.

---

## What you do not need to scrape

| Item | Reason |
|------|--------|
| Frontend images | Static assets in the frontend repo |
| FAQ / testimonial text | Hardcoded HTML |
| Static airport fallback in frontend JS | Only used when API is down |
| Heatmap colour thresholds | Hardcoded in frontend JS |
| `/api/ping` | No data file |

---

## Related docs

| Document | Purpose |
|----------|---------|
| [DATA.md](DATA.md) | Full schema reference, units, API response shapes |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Push to GitHub → Render auto-deploy |
| [../README.md](../README.md) | API reference and local setup |
| [../data/templates/README.md](../data/templates/README.md) | Scraper output templates |
