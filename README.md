# Flight Cost Analysis Backend

A small Flask backend that provides flight-cost analysis, price-per-km comparisons and simple price-prediction utilities based on precomputed CSV / JSON dataset files. The service is intended to be used by a frontend or other services to fetch routes, compare cost-per-km, get airport lists, and retrieve simple trend / visualization data.

This README documents how the project is organized, how to run it locally and the API surface exposed by the app.

## Key features

- Compare routes by cost-per-km (/api/compare)
- Predict price/trend insights for a route (/api/predict)
- List nearby airports for origin/destination (/api/nearby-airports)
- Return class and layover data for a route (/api/class-layover)
- Heatmap and visualization endpoints exposing aggregated statistics (/api/heatmap, /api/visualizations)
- Return list of airports extracted from flight CSVs (/api/airports)
- Raw compare data and best-route finder (/api/raw-compare-data, /api/route-find)
- Simple Haversine-based distance calculation and CSV/JSON loading helpers

## Tech stack

- Python 3.9 (project configured to run with Python 3.9 in render.yaml)
- Flask (web framework)
- flask-cors (CORS support)
- Gunicorn + gevent for production (Procfile + gunicorn_config.py)
- Data files are loaded from the `data/` directory (CSV and JSON)

Dependencies are listed in `requirements.txt`.

## Repository layout

- app.py — main Flask application with all API routes
- requirements.txt — Python dependencies
- Procfile — process declaration (for platforms like Heroku / Render)
- gunicorn_config.py — Gunicorn configuration used in production
- render.yaml — configuration for Render deployments
- data/ — directory containing CSV and JSON data files used by the API
  - compare_data_new.csv
  - merged_flight_data.csv
  - compare_data.json
  - trend_data.json
  - nearby_airports.json
  - class_layover_data.json
  - heatmap_data.json

## Installation

1. Clone the repo:
   git clone https://github.com/pawankushwahh/Flight_per_km_backend.git
   cd Flight_per_km_backend

2. Create and activate virtual environment:
   python3 -m venv venv
   source venv/bin/activate

3. Install dependencies:
   pip install -r requirements.txt

4. Ensure the `data/` directory contains the required CSV/JSON files used by the app. The app expects specific filenames (see "Repository layout" above).

## Running

Development:
- Run directly with Flask (includes debug mode set in app.py):
  python app.py
- By default the app runs on http://127.0.0.1:5000

Production (Gunicorn):
- The project includes a Procfile and gunicorn_config.py. Start with:
  gunicorn -c gunicorn_config.py app:app
- The included gunicorn_config binds to 0.0.0.0:10000 and uses gevent workers.

Deploy configuration:
- A `render.yaml` file is included and configures the service for Render. It sets Python 3.9 and runs `gunicorn -c gunicorn_config.py app:app`.


## Data expectations (CSV / JSON formats)

CSV loader (used in `app.py`) expects CSVs with header names containing at least the following for `compare_data_new.csv`:
- Start, End, Distance, Price, CostPerKm
All numeric fields are parsed (Distance, Price, CostPerKm) to float.

`merged_flight_data.csv` is expected to contain airport columns used by `/api/airports`:
- Start_IATA, Start_Airport, Start_City, Start_Lat, Start_Lon
- End_IATA, End_Airport, End_City, End_Lat, End_Lon

JSON files:
- `trend_data.json` should contain route objects with `origin`, `destination`, `monthly_trends` (list of {month, avg_price}) and optional `weekly_trends`, `best_travel_month`, `best_booking_time`
- `nearby_airports.json` should contain an `airports` array with objects having `code`, `name`, `lat`, `lon`, etc.
- `class_layover_data.json` should have `routes` array with `origin`, `destination` and class/layover info
- `heatmap_data.json` should contain the structure used by your frontend for heatmap visualizations
- `compare_data.json` is a JSON representation of compare routes (used by `/api/raw-compare-data`)

If you add or rename files, update the filenames in `app.py` accordingly.

## API reference

All responses are JSON with a `success` boolean and either `data` or `error`.

1. POST /api/compare
- Body:
  { "routes": [ { "origin": "DEL", "destination": "BOM" }, ... ] }
- Returns sorted routes by cost_per_km (lowest first) with structure:
  { "origin", "destination", "distance", "price", "cost_per_km" }

2. POST /api/predict
- Body:
  { "origin": "DEL", "destination": "BOM" }
- Returns trend/prediction data:
  current_price, lowest_price, highest_price, price_confidence, best_time_to_book, monthly_prices, savings_percentage

3. GET /api/nearby-airports?origin=DEL&destination=BOM
- Returns nearby airports entries for both origin and destination (lookup by airport code)

4. GET /api/class-layover?origin=DEL&destination=BOM
- Returns class and layover related information for the requested route

5. GET /api/heatmap
- Returns heatmap data JSON as-is from data/heatmap_data.json

6. GET /api/visualizations?limit=10
- Returns top cheapest and most expensive routes, average cost per km, and per-origin city averages

7. GET /api/airports
- Extracts unique airport entries from `merged_flight_data.csv` and returns a sorted list of airports:
  { code, name, city, country, lat, lon }

8. GET /api/raw-compare-data?limit=50
- Returns `compare_data.json` contents, optionally limited

9. POST /api/route-find
- If payload contains `findBestRoutes: true` and `origin`, filters `compare_data_new.csv` for routes from origin and enhances with trend info from trend_data.json.
- Otherwise returns the entire compare CSV contents

## Examples (curl)

Compare:
curl -X POST -H "Content-Type: application/json" -d '{"routes":[{"origin":"DEL","destination":"BOM"}]}' http://localhost:5000/api/compare

Predict:
curl -X POST -H "Content-Type: application/json" -d '{"origin":"DEL","destination":"BOM"}' http://localhost:5000/api/predict

Airports:
curl 'http://localhost:5000/api/airports'

## Notes, limitations and assumptions

- The app loads data from local files on each request (no database). For large datasets or production usage consider caching (Redis) or a proper database.
- Some route logic assumes all airports are in India (see `/api/airports` country field).
- Price prediction is a simple heuristic over monthly/weekly averages included in `trend_data.json`. It is not a machine-learning model.
- The app uses CORS enabled globally.

## Deployment

- For simple deployment, use Gunicorn as defined in the Procfile and gunicorn_config.py:
  gunicorn -c gunicorn_config.py app:app
- `render.yaml` is included for deploying on Render. It runs pip install -r requirements.txt then gunicorn as startCommand.

## Contributing

- Add or update data files inside `data/`.
- Keep API contracts stable or document breaking changes.
- Open issues or PRs for bugfixes and improvements.
