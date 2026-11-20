import pytest


def test_dashboard_and_auth_routes(client):
    # GET /login returns 200
    res_login = client.get('/login')
    assert res_login.status_code == 200
    assert b"Sign In to Dashboard" in res_login.data

    # GET / with demo mode active returns 200
    res_home = client.get('/')
    assert res_home.status_code == 200
    assert b"Payment Reconciliation" in res_home.data


def test_api_metrics_endpoint(client):
    res = client.get('/api/metrics')
    assert res.status_code == 200
    data = res.get_json()
    assert 'total_records' in data
    assert 'match_rate' in data
    assert 'amount_at_risk' in data
    assert 'actual_recovered_amount' in data


def test_api_seed_demo_endpoint(auth_client):
    res = auth_client.post('/api/seed-demo', headers={'X-CSRFToken': 'test-valid-csrf-token-123'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'SUCCESS'
    assert 'inserted_counts' in data
