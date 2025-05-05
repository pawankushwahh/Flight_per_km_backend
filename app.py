from flask import Flask, jsonify, request
from flask_cors import CORS
import json
import csv
import os
import math


app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Helper function to load JSON data
def load_json_data(filename):
    data_path = os.path.join(os.path.dirname(__file__), 'data', filename)
    with open(data_path, 'r') as file:
        return json.load(file)

# Helper function to load CSV data
def load_csv_data(filename):
    data_path = os.path.join(os.path.dirname(__file__), 'data', filename)
    data = []
    with open(data_path, 'r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            # Convert string values to appropriate types
            for key in ['Distance', 'Price', 'CostPerKm']:
                if key in row:
                    row[key] = float(row[key])
            data.append(row)
    return data

# Calculate distance between two airports using Haversine formula
def calculate_distance(lat1, lon1, lat2, lon2):
    # Convert latitude and longitude from degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r

# Route for per-kilometer cost comparison
@app.route('/api/compare', methods=['POST'])
def compare_routes():
    try:
        data = request.get_json()
        routes = data.get('routes', [])
        
        # Load CSV data
        compare_data = load_csv_data('compare_data_new.csv')
        
        results = []
        for route in routes:
            origin = route.get('origin')
            destination = route.get('destination')
            
            # Find route in CSV data
            route_data = next((r for r in compare_data 
                              if r['Start'] == origin and r['End'] == destination), None)
            
            if route_data:
                # Create result with focus on departure, arrival, cost per km, and distance
                results.append({
                    'origin': origin,
                    'destination': destination,
                    'distance': route_data['Distance'],
                    'price': route_data['Price'],
                    'cost_per_km': route_data['CostPerKm']
                })
        
        # Sort results by cost per km (lowest first)
        results.sort(key=lambda x: x['cost_per_km'])
        
        return jsonify({
            'success': True,
            'data': results
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



# Route for price prediction
@app.route('/api/predict', methods=['POST'])
def predict_prices():
    try:
        data = request.get_json()
        origin = data.get('origin')
        destination = data.get('destination')
        
        # Load trend data
        trend_data = load_json_data('trend_data.json')
        
        # Find trend data for the requested route
        route_trends = next((t for t in trend_data['routes'] 
                            if t['origin'] == origin and t['destination'] == destination), None)
        
        # If route not found, return not found response
        if not route_trends:
            return jsonify({
                'success': False,
                'error': f'Route data not found for {origin} to {destination}'
            }), 404
        
        # Extract monthly price trends
        monthly_prices = route_trends['monthly_trends']
        weekly_prices = route_trends.get('weekly_trends', [])
        
        # Calculate lowest and highest prices from monthly trends
        prices = [month['avg_price'] for month in monthly_prices]
        lowest_price = min(prices)
        highest_price = max(prices)
        
        # Get current price (using November as 'current' for demonstration)
        current_month = 'November'  # This would be the current month in a real app
        current_price = next((month['avg_price'] for month in monthly_prices if month['month'] == current_month), prices[0])
        
        # Find best month to travel (lowest price)
        best_month = next((month['month'] for month in monthly_prices if month['avg_price'] == lowest_price), 'Unknown')
        
        # Determine best time to book from weekly trends if available
        best_time_to_book = 'Book 1-2 months in advance for best prices'
        if weekly_prices:
            # Find the week with the lowest price
            best_week = min(weekly_prices, key=lambda x: x['avg_price'])
            best_time_to_book = f'Book {best_week["week"]} for the best price (₹{best_week["avg_price"]})'
        
        # Calculate price confidence based on variance in prices
        price_variance = max(0.1, (highest_price - lowest_price) / highest_price)
        if price_variance < 0.15:
            confidence = 'High'
        elif price_variance < 0.3:
            confidence = 'Medium'
        else:
            confidence = 'Low'
        
        # Prepare prediction result
        prediction_data = {
            'origin': origin,
            'destination': destination,
            'current_price': current_price,
            'lowest_price': lowest_price,
            'highest_price': highest_price,
            'price_confidence': confidence,
            'best_time_to_book': f'Travel in {best_month} and {best_time_to_book}',
            'monthly_prices': monthly_prices,
            'savings_percentage': round(((current_price - lowest_price) / current_price) * 100, 1)
        }
        
        return jsonify({
            'success': True,
            'data': prediction_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Route for nearby airports
@app.route('/api/nearby-airports', methods=['GET'])
def nearby_airports():
    try:
        origin = request.args.get('origin')
        destination = request.args.get('destination')
        
        # Load nearby airports data
        nearby_data = load_json_data('nearby_airports.json')
        
        # Find nearby airports for origin and destination
        origin_nearby = next((a for a in nearby_data['airports'] if a['code'] == origin), None)
        destination_nearby = next((a for a in nearby_data['airports'] if a['code'] == destination), None)
        
        if not origin_nearby or not destination_nearby:
            return jsonify({
                'success': False,
                'error': 'Airport not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'origin': origin_nearby,
                'destination': destination_nearby
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Route for class and layover comparison
@app.route('/api/class-layover', methods=['GET'])
def class_layover():
    try:
        origin = request.args.get('origin')
        destination = request.args.get('destination')
        
        # Load class and layover data
        class_layover_data = load_json_data('class_layover_data.json')
        
        # Find class and layover data for the requested route
        route_data = next((c for c in class_layover_data['routes'] 
                          if c['origin'] == origin and c['destination'] == destination), None)
        
        if not route_data:
            return jsonify({
                'success': False,
                'error': 'Route not found'
            }), 404
        
        return jsonify({
            'success': True,
            'data': route_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Route for heatmap data
@app.route('/api/heatmap', methods=['GET'])
def heatmap():
    try:
        # Load heatmap data
        heatmap_data = load_json_data('heatmap_data.json')
        
        return jsonify({
            'success': True,
            'data': heatmap_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Route for visualization data (top routes by cost per km)
@app.route('/api/visualizations', methods=['GET'])
def visualizations():
    try:
        # Get the number of top routes to return (default to 10)
        limit = request.args.get('limit', default=10, type=int)
        
        # Load route comparison data
        compare_data = load_csv_data('compare_data_new.csv')
        
        # Sort data by cost per km (both ascending and descending)
        cheapest_routes = sorted(compare_data, key=lambda x: float(x['CostPerKm']))
        most_expensive_routes = sorted(compare_data, key=lambda x: float(x['CostPerKm']), reverse=True)
        
        # Get the top N routes based on limit parameter
        top_cheapest = cheapest_routes[:limit]
        top_expensive = most_expensive_routes[:limit]
        
        # Calculate average cost per km across all routes
        avg_cost_per_km = sum(float(route['CostPerKm']) for route in compare_data) / len(compare_data)
        
        # Group routes by origin to analyze which cities have better overall value
        cities_data = {}
        for route in compare_data:
            origin = route['Start']
            if origin not in cities_data:
                cities_data[origin] = []
            cities_data[origin].append(float(route['CostPerKm']))
        
        # Calculate average cost per km for each origin city
        city_averages = []
        for city, costs in cities_data.items():
            avg_cost = sum(costs) / len(costs)
            city_averages.append({
                'city': city,
                'avgCostPerKm': avg_cost,
                'routeCount': len(costs)
            })
        
        # Sort cities by average cost per km
        city_averages = sorted(city_averages, key=lambda x: x['avgCostPerKm'])
        
        # Return the visualization data
        return jsonify({
            'success': True,
            'data': {
                'topCheapestRoutes': top_cheapest,
                'topExpensiveRoutes': top_expensive,
                'averageCostPerKm': avg_cost_per_km,
                'cityAverages': city_averages
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Route for airport data
@app.route('/api/airports', methods=['GET'])
def get_airports():
    try:
        # Load flight data from CSV
        flight_data = load_csv_data('merged_flight_data.csv')
        
        # Extract unique airports with their details
        unique_airports = {}
        for row in flight_data:
            # Add origin airport if not already in the list
            if row['Start_IATA'] and row['Start_IATA'] not in unique_airports:
                try:
                    # Skip if lat/lon values are missing
                    if not row['Start_Lat'] or not row['Start_Lon']:
                        continue
                        
                    unique_airports[row['Start_IATA']] = {
                        'code': row['Start_IATA'],
                        'name': row['Start_Airport'] or 'Unknown',
                        'city': row['Start_City'] or 'Unknown',
                        'country': 'India',  # Assuming all are in India
                        'lat': float(row['Start_Lat']),
                        'lon': float(row['Start_Lon'])
                    }
                except (ValueError, KeyError):
                    continue
            
            # Add destination airport if not already in the list
            if row['End_IATA'] and row['End_IATA'] not in unique_airports:
                try:
                    # Skip if lat/lon values are missing
                    if not row['End_Lat'] or not row['End_Lon']:
                        continue
                        
                    unique_airports[row['End_IATA']] = {
                        'code': row['End_IATA'],
                        'name': row['End_Airport'] or 'Unknown',
                        'city': row['End_City'] or 'Unknown',
                        'country': 'India',  # Assuming all are in India
                        'lat': float(row['End_Lat']),
                        'lon': float(row['End_Lon'])
                    }
                except (ValueError, KeyError):
                    continue
        
        # Convert dictionary to list
        airports_list = list(unique_airports.values())
        
        # Sort by city name for better usability
        airports_list.sort(key=lambda x: x['city'])
        
        return jsonify({
            'success': True,
            'data': airports_list
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Route for raw compare data from JSON file
@app.route('/api/raw-compare-data', methods=['GET'])
def raw_compare_data():
    try:
        # Get optional limit parameter (default to all routes)
        limit = request.args.get('limit', type=int)
        
        # Load compare data from JSON file
        compare_data = load_json_data('compare_data.json')
        
        # If limit is specified, return only that many routes
        if limit and limit > 0:
            compare_data['routes'] = compare_data['routes'][:limit]
        
        return jsonify({
            'success': True,
            'data': compare_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Route for best routes from an origin airport
@app.route('/api/route-find', methods=['POST'])
def best_routes_finder():
    try:
        # Get request data
        data = request.get_json()
        
        # Check if this is a best routes request
        if data and data.get('findBestRoutes'):
            origin = data.get('origin')
            if not origin:
                return jsonify({
                    'success': False,
                    'error': 'Origin airport is required'
                }), 400
                
            # Load compare data
            compare_data = load_csv_data('compare_data_new.csv')
            
            # Filter routes for the specified origin
            origin_routes = [r for r in compare_data if r['Start'] == origin]
            
            # Load trend data to get best travel months
            trend_data = load_json_data('trend_data.json')
            routes_with_trends = []
            
            # Enhance route data with trend information when available
            for route in origin_routes:
                # Create a base route object
                route_obj = {
                    'origin': route['Start'],
                    'destination': route['End'],
                    'distance': route['Distance'],
                    'price': route['Price'],
                    'cost_per_km': route['CostPerKm']
                }
                
                # Look for trend data for this route
                route_trend = next((t for t in trend_data['routes'] 
                                  if t['origin'] == route['Start'] and 
                                  t['destination'] == route['End']), None)
                
                # Add best travel month if available
                if route_trend and 'best_travel_month' in route_trend:
                    route_obj['best_travel_month'] = route_trend['best_travel_month']
                    route_obj['monthly_trends'] = route_trend.get('monthly_trends', [])
                    route_obj['best_booking_time'] = route_trend.get('best_booking_time', '')
                
                routes_with_trends.append(route_obj)
            
            return jsonify({
                'success': True,
                'data': routes_with_trends
            })
        
        # Regular compare data request
        compare_data = load_csv_data('compare_data_new.csv')
        
        # Return the data
        return jsonify({
            'success': True,
            'data': compare_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True)

