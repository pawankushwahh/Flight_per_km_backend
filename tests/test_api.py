"""Smoke tests for Flight Cost Intelligence API."""

import json
import pytest

from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_root(client):
    r = client.get('/')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'ok'


def test_ping(client):
    r = client.get('/api/ping')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'ok'


def test_airports(client):
    r = client.get('/api/airports')
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert len(data['data']) > 0
    assert 'code' in data['data'][0]


def test_compare(client):
    r = client.post('/api/compare', json={
        'routes': [{'origin': 'DEL', 'destination': 'BOM'}]
    })
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert len(data['data']) == 1
    assert data['data'][0]['cost_per_km'] > 0


def test_compare_not_found(client):
    r = client.post('/api/compare', json={
        'routes': [{'origin': 'DEL', 'destination': 'XXX'}]
    })
    data = r.get_json()
    assert data['success'] is True
    assert data['data'] == []
    assert len(data['not_found']) == 1


def test_predict(client):
    r = client.post('/api/predict', json={'origin': 'DEL', 'destination': 'BOM'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['data']['current_price'] > 1000


def test_raw_compare_enriched(client):
    r = client.get('/api/raw-compare-data?limit=5')
    assert r.status_code == 200
    routes = r.get_json()['data']['routes']
    assert len(routes) == 5
    assert 'distance' in routes[0]
    assert 'cost_per_km' in routes[0]


def test_heatmap_flat_routes(client):
    r = client.get('/api/heatmap')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert 'routes' in data
    assert len(data['routes']) > 0
    assert 'origin' in data['routes'][0] or 'from' in str(data['routes'][0])


def test_visualizations(client):
    r = client.get('/api/visualizations?limit=5')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert len(data['topCheapestRoutes']) == 5


def test_route_find(client):
    r = client.post('/api/route-find', json={'findBestRoutes': True, 'origin': 'DEL'})
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert all(row['origin'] == 'DEL' for row in data['data'])


def test_nearby_airports(client):
    r = client.get('/api/nearby-airports?origin=DEL&destination=BOM')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert 'nearby' in data['origin']


def test_class_layover(client):
    r = client.get('/api/class-layover?origin=DEL&destination=BOM')
    assert r.status_code == 200
    data = r.get_json()['data']
    assert 'direct_flight' in data
    assert 'economy' in data['direct_flight']
