from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
import json
import csv
import os
import math

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# ── Startup data cache ────────────────────────────────────────
# Files are loaded ONCE at startup, not on every request.
# This saves 50-200ms per API call and reduces disk I/O.
_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
_cache = {}

def _load_json(filename):
    path = os.path.join(_DATA_DIR, filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _load_csv(filename):
    path = os.path.join(_DATA_DIR, filename)
    data = []
    with open(path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            for key in ['Distance', 'Price', 'CostPerKm']:
                if key in row and row[key]:
                    try:
                        row[key] = float(row[key])
                    except ValueError:
                        pass
            data.append(row)
    return data

def _init_cache():
    """Load all data files into memory at startup."""
    files = {
        'compare_csv':    ('csv',  'compare_data_new.csv'),
        'merged_csv':     ('csv',  'merged_flight_data.csv'),
        'compare_json':   ('json', 'compare_data.json'),
        'trend_json':     ('json', 'trend_data.json'),
        'nearby_json':    ('json', 'nearby_airports.json'),
        'layover_json':   ('json', 'class_layover_data.json'),
        'heatmap_json':   ('json', 'heatmap_data.json'),
    }
    for key, (fmt, filename) in files.items():
        try:
            _cache[key] = _load_csv(filename) if fmt == 'csv' else _load_json(filename)
            print(f'[cache] loaded {filename}')
        except Exception as e:
            print(f'[cache] WARNING: could not load {filename}: {e}')
            _cache[key] = [] if fmt == 'csv' else {}

# Load at import time so gunicorn workers share the benefit
_init_cache()

# ── Input validation helpers ──────────────────────────────────

def _valid_iata(code):
    """Return True if code is a 3-letter uppercase IATA code."""
    return isinstance(code, str) and len(code) == 3 and code.isalpha() and code == code.upper()

def _safe_error(e):
    """Return a sanitised error message — never leak file paths."""
    msg = str(e)
    # Strip anything that looks like a file path
    if os.sep in msg or msg.startswith('/') or ('\\' in msg):
        return 'An internal error occurred. Please try again.'
    return msg

# ── Haversine ─────────────────────────────────────────────────

def calculate_distance(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 2 * math.asin(math.sqrt(a)) * 6371

# ── Health / ping ─────────────────────────────────────────────

@app.route('/api/ping', methods=['GET'])
def ping():
    """Lightweight endpoint for uptime monitors.
    Point UptimeRobot (free) at this URL every 10 minutes
    to prevent Render free-tier cold starts."""
    return jsonify({'status': 'ok', 'timestamp': datetime.utcnow().isoformat()})

# ── /api/compare ──────────────────────────────────────────────

@app.route('/api/compare', methods=['POST'])
def compare_routes():
    try:
        body = request.get_json(silent=True) or {}
        routes = body.get('routes', [])

        # Validate
        if not routes:
            return jsonify({'success': False, 'error': 'routes array is required'}), 400
        if not isinstance(routes, list):
            return jsonify({'success': False, 'error': 'routes must be an array'}), 400

        compare_data = _cache.get('compare_csv', [])
        results = []

        for route in routes:
            origin      = (route.get('origin') or '').strip().upper()
            destination = (route.get('destination') or '').strip().upper()

            if not _valid_iata(origin) or not _valid_iata(destination):
                continue
            if origin == destination:
                continue

            row = next((r for r in compare_data
                        if r['Start'] == origin and r['End'] == destination), None)
            if row:
                results.append({
                    'origin':      origin,
                    'destination': destination,
                    'distance':    row['Distance'],
                    'price':       row['Price'],
                    'cost_per_km': row['CostPerKm'],
                })

        results.sort(key=lambda x: x['cost_per_km'])
        return jsonify({'success': True, 'data': results})

    except Exception as e:
        return jsonify({'success': False, 'error': _safe_error(e)}), 500

# ── /api/predict ──────────────────────────────────────────────

@app.route('/api/predict', methods=['POST'])
def predict_prices():
    try:
        body = request.get_json(silent=True) or {}
        origin      = (body.get('origin') or '').strip().upper()
        destination = (body.get('destination') or '').strip().upper()

        # Validate
        if not _valid_iata(origin) or not _valid_iata(destination):
            return jsonify({'success': False, 'error': 'Valid 3-letter IATA codes required'}), 400
        if origin == destination:
            return jsonify({'success': False, 'error': 'Origin and destination must differ'}), 400

        trend_data   = _cache.get('trend_json', {})
        route_trends = next((t for t in trend_data.get('routes', [])
                             if t['origin'] == origin and t['destination'] == destination), None)

        if not route_trends:
            return jsonify({
                'success': False,
                'error': f'No trend data found for {origin} to {destination}'
            }), 404

        monthly_prices = route_trends.get('monthly_trends', [])
        weekly_prices  = route_trends.get('weekly_trends', [])

        if not monthly_prices:
            return jsonify({'success': False, 'error': 'No monthly trend data available'}), 404

        prices        = [m['avg_price'] for m in monthly_prices]
        lowest_price  = min(prices)
        highest_price = max(prices)

        # FIX: use the actual current month instead of hardcoded "November"
        current_month = datetime.now().strftime('%B')
        current_price = next(
            (m['avg_price'] for m in monthly_prices if m['month'] == current_month),
            prices[0]
        )

        best_month = next(
            (m['month'] for m in monthly_prices if m['avg_price'] == lowest_price),
            'Unknown'
        )

        best_time_to_book = 'Book 1-2 months in advance for best prices'
        if weekly_prices:
            best_week = min(weekly_prices, key=lambda x: x['avg_price'])
            best_time_to_book = f'Book {best_week["week"]} for the best price (\u20b9{best_week["avg_price"]})'

        price_variance = max(0.1, (highest_price - lowest_price) / highest_price)
        confidence = 'High' if price_variance < 0.15 else 'Medium' if price_variance < 0.3 else 'Low'

        # FIX: clamp savings to 0 — never show negative savings
        raw_savings = ((current_price - lowest_price) / current_price) * 100
        savings_pct = round(max(0.0, raw_savings), 1)

        return jsonify({
            'success': True,
            'data': {
                'origin':           origin,
                'destination':      destination,
                'current_month':    current_month,
                'current_price':    current_price,
                'lowest_price':     lowest_price,
                'highest_price':    highest_price,
                'price_confidence': confidence,
                'best_time_to_book': f'Travel in {best_month} and {best_time_to_book}',
                'monthly_prices':   monthly_prices,
                'savings_percentage': savings_pct,
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': _safe_error(e)}), 500

# ── /api/nearby-airports ──────────────────────────────────────

@app.route('/api/nearby-airports', methods=['GET'])
def nearby_airports():
    try:
        origin      = (request.args.get('origin') or '').strip().upper()
        destination = (request.args.get('destination') or '').strip().upper()

        if not _valid_iata(origin) or not _valid_iata(destination):
            return jsonify({'success': False, 'error': 'Valid 3-letter IATA codes required'}), 400

        nearby_data      = _cache.get('nearby_json', {})
        airports_list    = nearby_data.get('airports', [])
        origin_data      = next((a for a in airports_list if a['code'] == origin), None)
        destination_data = next((a for a in airports_list if a['code'] == destination), None)

        if not origin_data or not destination_data:
            return jsonify({'success': False, 'error': 'Airport not found in nearby-airports dataset'}), 404

        return jsonify({'success': True, 'data': {'origin': origin_data, 'destination': destination_data}})

    except Exception as e:
        return jsonify({'success': False, 'error': _safe_error(e)}), 500

# ── /api/class-layover ────────────────────────────────────────

@app.route('/api/class-layover', methods=['GET'])
def class_layover():
    try:
        origin      = (request.args.get('origin') or '').strip().upper()
        destination = (request.args.get('destination') or '').strip().upper()

        if not _valid_iata(origin) or not _valid_iata(destination):
            return jsonify({'success': False, 'error': 'Valid 3-letter IATA codes required'}), 400

        layover_data = _cache.get('layover_json', {})
        route_data   = next((c for c in layover_data.get('routes', [])
                             if c['origin'] == origin and c['destination'] == destination), None)

        if not route_data:
            return jsonify({'success': False, 'error': f'No class/layover data for {origin} to {destination}'}), 404

        return jsonify({'success': True, 'data': route_data})

    except Exception as e:
        return jsonify({'success': False, 'error': _safe_error(e)}), 500

# ── /api/heatmap ──────────────────────────────────────────────

@app.route('/api/heatmap', methods=['GET'])
def heatmap():
    try:
        data = _cache.get('heatmap_json', {})
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': _safe_error(e)}), 500

# ── /api/visualizations ───────────────────────────────────────

@app.route('/api/visualizations', methods=['GET'])
def visualizations():
    try:
        limit        = request.args.get('limit', default=10, type=int)
        compare_data = _cache.get('compare_csv', [])

        # FIX: guard against empty dataset (was a division-by-zero risk)
        if not compare_data:
            return jsonify({'success': False, 'error': 'No route data available'}), 503

        cheapest_routes = sorted(compare_data, key=lambda x: float(x['CostPerKm']))
        expensive_routes = sorted(compare_data, key=lambda x: float(x['CostPerKm']), reverse=True)

        avg_cost_per_km = sum(float(r['CostPerKm']) for r in compare_data) / len(compare_data)

        cities_data = {}
        for route in compare_data:
            origin = route['Start']
            cities_data.setdefault(origin, []).append(float(route['CostPerKm']))

        city_averages = sorted(
            [{'city': c, 'avgCostPerKm': sum(v)/len(v), 'routeCount': len(v)}
             for c, v in cities_data.items()],
            key=lambda x: x['avgCostPerKm']
        )

        return jsonify({
            'success': True,
            'data': {
                'topCheapestRoutes':  cheapest_routes[:limit],
                'topExpensiveRoutes': expensive_routes[:limit],
                'averageCostPerKm':   avg_cost_per_km,
                'cityAverages':       city_averages,
            }
        })

    except Exception as e:
        return jsonify({'success': False, 'error': _safe_error(e)}), 500

# ── /api/airports ─────────────────────────────────────────────

@app.route('/api/airports', methods=['GET'])
def get_airports():
    try:
        flight_data     = _cache.get('merged_csv', [])
        unique_airports = {}

        for row in flight_data:
            for prefix in [('Start_IATA', 'Start_Airport', 'Start_City', 'Start_Lat', 'Start_Lon'),
                           ('End_IATA',   'End_Airport',   'End_City',   'End_Lat',   'End_Lon')]:
                code_key, name_key, city_key, lat_key, lon_key = prefix
                code = row.get(code_key, '').strip()
                if not code or code in unique_airports:
                    continue
                lat = row.get(lat_key, '').strip()
                lon = row.get(lon_key, '').strip()
                if not lat or not lon:
                    continue
                try:
                    unique_airports[code] = {
                        'code':    code,
                        'name':    row.get(name_key) or 'Unknown',
                        'city':    row.get(city_key) or 'Unknown',
                        'country': 'India',
                        'lat':     float(lat),
                        'lon':     float(lon),
                    }
                except ValueError:
                    continue

        airports_list = sorted(unique_airports.values(), key=lambda x: x['city'])
        return jsonify({'success': True, 'data': airports_list})

    except Exception as e:
        return jsonify({'success': False, 'error': _safe_error(e)}), 500

# ── /api/raw-compare-data ─────────────────────────────────────

@app.route('/api/raw-compare-data', methods=['GET'])
def raw_compare_data():
    try:
        limit        = request.args.get('limit', type=int)
        compare_data = _cache.get('compare_json', {})

        # Work on a shallow copy so we don't mutate the cached object
        result = dict(compare_data)
        if limit and limit > 0:
            result['routes'] = compare_data.get('routes', [])[:limit]

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        return jsonify({'success': False, 'error': _safe_error(e)}), 500

# ── /api/route-find ───────────────────────────────────────────

@app.route('/api/route-find', methods=['POST'])
def best_routes_finder():
    try:
        body = request.get_json(silent=True) or {}

        if body.get('findBestRoutes'):
            origin = (body.get('origin') or '').strip().upper()
            if not origin:
                return jsonify({'success': False, 'error': 'origin is required'}), 400
            if not _valid_iata(origin):
                return jsonify({'success': False, 'error': 'origin must be a valid 3-letter IATA code'}), 400

            compare_data  = _cache.get('compare_csv', [])
            trend_data    = _cache.get('trend_json', {})
            origin_routes = [r for r in compare_data if r['Start'] == origin]

            routes_with_trends = []
            for route in origin_routes:
                route_obj = {
                    'origin':      route['Start'],
                    'destination': route['End'],
                    'distance':    route['Distance'],
                    'price':       route['Price'],
                    'cost_per_km': route['CostPerKm'],
                }
                trend = next((t for t in trend_data.get('routes', [])
                              if t['origin'] == route['Start'] and t['destination'] == route['End']), None)
                if trend:
                    route_obj['best_travel_month'] = trend.get('best_travel_month', '')
                    route_obj['best_booking_time'] = trend.get('best_booking_time', '')
                    route_obj['monthly_trends']    = trend.get('monthly_trends', [])

                routes_with_trends.append(route_obj)

            return jsonify({'success': True, 'data': routes_with_trends})

        # Fallback: return full compare CSV
        compare_data = _cache.get('compare_csv', [])
        return jsonify({'success': True, 'data': compare_data})

    except Exception as e:
        return jsonify({'success': False, 'error': _safe_error(e)}), 500


if __name__ == '__main__':
    app.run(debug=True)
