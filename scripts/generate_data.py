#!/usr/bin/env python3
"""
Generate or refresh all derived JSON datasets from canonical CSV files.

Canonical sources (replace these when you scrape real data):
  - data/compare_data_new.csv   route prices and ₹/km
  - data/merged_flight_data.csv airport names, cities, coordinates

Derived outputs (safe to regenerate anytime):
  - data/compare_data.json
  - data/trend_data.json
  - data/class_layover_data.json
  - data/heatmap_data.json
  - data/nearby_airports.json

Usage:
  python scripts/generate_data.py          # regenerate all derived files
  python scripts/generate_data.py --check  # print coverage report only
"""

import argparse
import csv
import json
import math
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]
MONTH_MULT = {
    'January': 0.92, 'February': 0.88, 'March': 0.95, 'April': 1.00,
    'May': 1.05, 'June': 1.10, 'July': 1.15, 'August': 1.12,
    'September': 1.02, 'October': 0.98, 'November': 0.90, 'December': 1.08,
}
WEEKS = [
    ('1-7 days before', 1.12),
    ('8-14 days before', 1.05),
    ('15-21 days before', 1.00),
    ('22-30 days before', 0.95),
    ('31-60 days before', 0.90),
    ('61-90 days before', 0.93),
]
HUBS = ['DEL', 'BOM', 'BLR', 'HYD', 'CCU', 'MAA']
CABIN_MULT = {
    'economy': 1.0,
    'premium_economy': 1.5,
    'business': 2.9,
    'first': 5.0,
}
AIRLINES = ['IndiGo', 'Air India', 'SpiceJet', 'Vistara', 'Akasa Air']
REGION_MAP = {
    'Delhi': 'North India', 'Chandigarh': 'North India', 'Jaipur': 'North India',
    'Lucknow': 'North India', 'Amritsar': 'North India', 'Srinagar': 'North India',
    'Mumbai': 'West India', 'Pune': 'West India', 'Ahmedabad': 'West India',
    'Goa': 'West India', 'Nagpur': 'West India', 'Surat': 'West India',
    'Bangalore': 'South India', 'Chennai': 'South India', 'Hyderabad': 'South India',
    'Kochi': 'South India', 'Cochin': 'South India', 'Thiruvananthapuram': 'South India',
    'Kolkata': 'East India', 'Bhubaneswar': 'East India', 'Guwahati': 'East India',
    'Patna': 'East India', 'Bagdogra': 'East India', 'Visakhapatnam': 'East India',
    'Agartala': 'East India', 'Imphal': 'East India', 'Ranchi': 'East India',
    'Raipur': 'Central India', 'Bhopal': 'Central India',
}


def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * math.asin(math.sqrt(a)) * 6371


def load_compare_csv():
    path = os.path.join(DATA_DIR, 'compare_data_new.csv')
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rows.append({
                'origin': row['Start'],
                'destination': row['End'],
                'distance': float(row['Distance']),
                'price': float(row['Price']),
                'cost_per_km': float(row['CostPerKm']),
            })
    return rows


def load_merged_csv():
    path = os.path.join(DATA_DIR, 'merged_flight_data.csv')
    with open(path, 'r', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def extract_airports(merged_rows):
    """Build airport lookup from merged CSV."""
    airports = {}
    for row in merged_rows:
        for keys in [
            ('Start_IATA', 'Start_Airport', 'Start_City', 'Start_Lat', 'Start_Lon'),
            ('End_IATA', 'End_Airport', 'End_City', 'End_Lat', 'End_Lon'),
        ]:
            code = row[keys[0]].strip()
            if not code or code in airports:
                continue
            try:
                airports[code] = {
                    'code': code,
                    'name': row[keys[1]] or f'{code} Airport',
                    'city': row[keys[2]] or code,
                    'country': 'India',
                    'lat': float(row[keys[3]]),
                    'lon': float(row[keys[4]]),
                }
            except (ValueError, TypeError):
                continue
    return airports


def pick_airline(origin, destination):
    idx = (ord(origin[0]) + ord(destination[1])) % len(AIRLINES)
    return AIRLINES[idx]


def pick_via(origin, destination):
    for hub in HUBS:
        if hub not in (origin, destination):
            return hub
    return 'DEL'


def flight_hours(distance_km):
    return max(1.0, round(distance_km / 750, 1))


def _safe_float(val, fallback=None):
    try:
        return float(val) if val not in (None, '') else fallback
    except (ValueError, TypeError):
        return fallback


def generate_compare_json(routes, merged_rows, airports):
    """Full compare_data.json with coords and airline for every CSV route."""
    coord_lookup = {}
    for row in merged_rows:
        key = (row['Start_IATA'], row['End_IATA'])
        o_lat = _safe_float(row['Start_Lat'], airports.get(row['Start_IATA'], {}).get('lat'))
        o_lon = _safe_float(row['Start_Lon'], airports.get(row['Start_IATA'], {}).get('lon'))
        d_lat = _safe_float(row['End_Lat'], airports.get(row['End_IATA'], {}).get('lat'))
        d_lon = _safe_float(row['End_Lon'], airports.get(row['End_IATA'], {}).get('lon'))
        coord_lookup[key] = {
            'origin_lat': o_lat,
            'origin_lon': o_lon,
            'destination_lat': d_lat,
            'destination_lon': d_lon,
        }

    json_routes = []
    for r in routes:
        key = (r['origin'], r['destination'])
        coords = coord_lookup.get(key, {})
        json_routes.append({
            'origin': r['origin'],
            'destination': r['destination'],
            'origin_lat': coords.get('origin_lat'),
            'origin_lon': coords.get('origin_lon'),
            'destination_lat': coords.get('destination_lat'),
            'destination_lon': coords.get('destination_lon'),
            'price': round(r['price']),
            'airline': pick_airline(r['origin'], r['destination']),
        })
    return {'routes': json_routes}


def generate_nearby_airports(airports, routes):
    """Realistic nearby-airport suggestions based on geographic distance."""
    route_cpk = {(r['origin'], r['destination']): r['cost_per_km'] for r in routes}
    origin_avg = {}
    for r in routes:
        origin_avg.setdefault(r['origin'], []).append(r['cost_per_km'])

    codes = list(airports.keys())
    result = []

    for code in sorted(codes):
        main = airports[code]
        others = []
        for other_code in codes:
            if other_code == code:
                continue
            other = airports[other_code]
            dist = round(haversine(main['lat'], main['lon'], other['lat'], other['lon']))
            others.append((dist, other_code, other))
        others.sort(key=lambda x: x[0])

        nearby = []
        for dist, other_code, other in others[:4]:
            direct_cpk = route_cpk.get((code, other_code))
            if direct_cpk and code in origin_avg:
                avg_from_main = sum(origin_avg[code]) / len(origin_avg[code])
                diff = round(abs(direct_cpk - avg_from_main), 2)
            else:
                diff = round(1.5 + (dist % 500) / 200, 2)

            nearby.append({
                'code': other_code,
                'name': other['name'],
                'city': other['city'],
                'country': 'India',
                'lat': other['lat'],
                'lon': other['lon'],
                'distance': dist,
                'avg_cost_difference': diff,
            })

        result.append({**main, 'nearby': nearby})

    return {'airports': result}


def generate_trend_data(routes):
    trend_routes = []
    for r in routes:
        base, dist = r['price'], r['distance']
        monthly = [
            {
                'month': month,
                'avg_price': round(base * MONTH_MULT[month]),
                'avg_cost_per_km': round(base * MONTH_MULT[month] / dist, 2),
            }
            for month in MONTHS
        ]
        weekly = [
            {
                'week': label,
                'avg_price': round(base * mult),
                'avg_cost_per_km': round(base * mult / dist, 2),
            }
            for label, mult in WEEKS
        ]
        lowest = min(monthly, key=lambda m: m['avg_price'])
        best_week = min(weekly, key=lambda w: w['avg_price'])
        trend_routes.append({
            'origin': r['origin'],
            'destination': r['destination'],
            'monthly_trends': monthly,
            'weekly_trends': weekly,
            'best_travel_month': lowest['month'],
            'best_booking_time': best_week['week'],
        })
    return {'routes': trend_routes}


def cabin_entry(price, distance, duration, layover_hours=0):
    entry = {
        'price': round(price),
        'cost_per_km': round(price / distance, 2),
        'duration_hours': duration,
    }
    if layover_hours:
        entry['layover_hours'] = layover_hours
    return entry


def generate_class_layover(routes):
    layover_routes = []
    for r in routes:
        dist, base = r['distance'], r['price']
        direct = {
            cabin: cabin_entry(base * mult, dist, flight_hours(dist))
            for cabin, mult in CABIN_MULT.items()
        }
        via = pick_via(r['origin'], r['destination'])
        layover_dist = dist * 1.15
        layover_dur = flight_hours(dist) + 1.5
        layover_option = {'via': via}
        for cabin, mult in CABIN_MULT.items():
            layover_option[cabin] = cabin_entry(
                base * mult * 0.92, layover_dist, layover_dur, layover_hours=1.0
            )
        layover_routes.append({
            'origin': r['origin'],
            'destination': r['destination'],
            'distance_km': dist,
            'direct_flight': direct,
            'layover_options': [layover_option],
        })
    return {'routes': layover_routes}


def generate_heatmap(merged_rows):
    regions = {}
    for row in merged_rows:
        city = row.get('Start_City', 'Unknown')
        region = REGION_MAP.get(city, 'Other India')
        regions.setdefault(region, {}).setdefault(city, []).append({
            'from': row['Start_IATA'],
            'to': row['End_IATA'],
            'cost_per_km': float(row['CostPerKm']),
        })

    region_list = []
    for region_name in sorted(regions.keys()):
        states = []
        for city_name in sorted(regions[region_name].keys()):
            city_routes = regions[region_name][city_name]
            avg = sum(r['cost_per_km'] for r in city_routes) / len(city_routes)
            states.append({
                'name': city_name,
                'code': city_name[:2].upper(),
                'avg_cost_per_km': round(avg, 2),
                'routes': city_routes,
            })
        region_avg = sum(s['avg_cost_per_km'] for s in states) / len(states)
        region_list.append({
            'name': region_name,
            'avg_cost_per_km': round(region_avg, 2),
            'states': states,
        })
    return {'regions': region_list}


def coverage_report(routes, airports, outputs):
    route_pairs = {(r['origin'], r['destination']) for r in routes}
    print('\n=== Data coverage report ===')
    print(f'CSV routes:           {len(routes)}')
    print(f'Unique airports:      {len(airports)}')
    print(f'compare_data.json:    {len(outputs["compare"]["routes"])} routes')
    print(f'trend_data.json:      {len(outputs["trend"]["routes"])} routes')
    print(f'class_layover_data:   {len(outputs["layover"]["routes"])} routes')
    print(f'nearby_airports:      {len(outputs["nearby"]["airports"])} airports')
    print(f'heatmap regions:      {len(outputs["heatmap"]["regions"])}')

    json_pairs = {(r['origin'], r['destination']) for r in outputs['compare']['routes']}
    missing = route_pairs - json_pairs
    if missing:
        print(f'WARNING: {len(missing)} CSV routes missing from compare_data.json')
    else:
        print('All CSV routes present in compare_data.json')

    no_coords = [
        r for r in outputs['compare']['routes']
        if not all(r.get(k) for k in ('origin_lat', 'origin_lon', 'destination_lat', 'destination_lon'))
    ]
    if no_coords:
        print(f'WARNING: {len(no_coords)} routes missing coordinates')
    else:
        print('All routes have map coordinates')


def write_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    count = len(data.get('routes', data.get('airports', data.get('regions', []))))
    print(f'Wrote {filename} ({count} entries)')


def main():
    parser = argparse.ArgumentParser(description='Generate derived flight data files')
    parser.add_argument('--check', action='store_true', help='Print coverage report only')
    args = parser.parse_args()

    routes = load_compare_csv()
    merged = load_merged_csv()
    airports = extract_airports(merged)

    outputs = {
        'compare': generate_compare_json(routes, merged, airports),
        'nearby': generate_nearby_airports(airports, routes),
        'trend': generate_trend_data(routes),
        'layover': generate_class_layover(routes),
        'heatmap': generate_heatmap(merged),
    }

    coverage_report(routes, airports, outputs)

    if args.check:
        return

    write_json('compare_data.json', outputs['compare'])
    write_json('nearby_airports.json', outputs['nearby'])
    write_json('trend_data.json', outputs['trend'])
    write_json('class_layover_data.json', outputs['layover'])
    write_json('heatmap_data.json', outputs['heatmap'])
    print('\nDone. Restart the Flask server to reload the cache.')


if __name__ == '__main__':
    main()
