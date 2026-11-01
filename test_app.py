from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import create_app
from seed import make_seed


@pytest.fixture
def client():
    with TestClient(create_app()) as client:
        yield client


def test_seed_distribution():
    policies, drafts, claims = make_seed()
    assert len(policies) == len({p['name'] for p in policies.values()}) == 15
    assert all(p['phone'] == '628-268-8763' and p['vehicles'] and p['drivers'] for p in policies.values())
    assert sum(len(p['beneficiaries']) > 1 for p in policies.values()) == 5
    assert sum(len(p['vehicles']) > 1 for p in policies.values()) == 5
    assert sum(len(p['drivers']) > 1 for p in policies.values()) == 5
    assert all(2 <= len(p['drivers']) - 1 <= 3 for p in policies.values() if len(p['drivers']) > 1)
    active = set(drafts) | {c['policy_number'] for c in claims.values()}
    against = {(c['loss']['other_party'] or {}).get('policy_number') for c in claims.values()} - {None}
    assert len(claims) == len(drafts) == 3
    assert len(against) == 2
    assert len(set(policies) - active - against) == 7


def test_states_and_unknown(client):
    assert len(client.get('/policies').json()) == 15
    assert client.get('/policies/GEC-0001').json()['claims']
    assert client.get('/policies/GEC-0004').json()['open_draft']
    assert client.get('/policies/GEC-0007').json()['claims_against']
    empty = client.get('/policies/GEC-0015').json()
    assert empty['claims'] == empty['claims_against'] == []
    assert empty['open_draft'] is None
    for method, suffix in [('get', ''), ('post', '/claims/draft'), ('post', '/claims/draft/submit')]:
        args = {'json': {}} if suffix == '/claims/draft' else {}
        assert getattr(client, method)('/policies/UNKNOWN' + suffix, **args).status_code == 404


def test_draft_lifecycle_and_locked_claim(client):
    base = '/policies/GEC-0015'
    path = base + '/claims/draft'
    assert client.post(path + '/submit').status_code == 400
    created = client.post(path, json={'description': 'Parked car damage.'})
    assert created.status_code == 201
    assert client.post(path + '/submit').status_code == 400
    updated = client.post(path, json={
        'occurred_at': '2026-10-31T10:00:00-07:00', 'location': 'Test lot',
        'vehicle_id': 'V15-1', 'other_party': {'policy_number': 'GEC-0014'},
    })
    assert updated.status_code == 200
    assert updated.json()['draft_id'] == created.json()['draft_id']
    assert updated.json()['loss']['description'] == 'Parked car damage.'
    assert client.get('/policies/GEC-0014').json()['claims_against'] == []
    submitted = client.post(path + '/submit')
    assert submitted.status_code == 201
    claim = submitted.json()
    assert claim['status'] == 'submitted' and claim['claim_number'].startswith('CLM-')
    assert client.post(path + '/submit').status_code == 400
    assert client.get(base).json()['open_draft'] is None
    assert client.get('/policies/GEC-0014').json()['claims_against'][0]['claim_number'] == claim['claim_number']
    new = client.post(path, json={'description': 'A separate incident.'})
    assert new.status_code == 201 and new.json()['draft_id'] != claim['draft_id']
    assert client.get(base).json()['claims'] == [claim]


@pytest.mark.parametrize('payload', [
    {'name': 'Changed'}, {'phone': '123'}, {'policy_number': 'GEC-0001'},
    {'vehicles': []}, {'drivers': []}, {'beneficiaries': []},
    {'status': 'submitted'}, {'claim_number': 'fake'}, {'draft_id': 'seed-draft-0001'},
    {'other_party': {'unknown': 'field'}}, {'description': '   '},
    {'occurred_at': 'not-a-date'}, {'occurred_at': '2026-10-31T10:00:00'},
])
def test_reject_invalid_or_read_only_fields(client, payload):
    before = client.get('/policies/GEC-0015').json()
    assert client.post('/policies/GEC-0015/claims/draft', json=payload).status_code == 422
    assert client.get('/policies/GEC-0015').json() == before


@pytest.mark.parametrize('payload', [
    {'vehicle_id': 'V01-1'}, {'other_party': {'policy_number': 'UNKNOWN'}},
    {'other_party': {'policy_number': 'GEC-0015'}},
])
def test_reject_invalid_references(client, payload):
    assert client.post('/policies/GEC-0015/claims/draft', json=payload).status_code == 400
    assert client.get('/policies/GEC-0015').json()['open_draft'] is None


def test_explicit_null_clears_field(client):
    path = '/policies/GEC-0004/claims/draft'
    response = client.post(path, json={'location': None})
    assert response.json()['loss']['location'] is None
    assert response.json()['loss']['description']
    assert client.post(path + '/submit').json()['detail']['missing_fields'] == ['location']


def test_simultaneous_submission_creates_one_claim(client):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post('/policies/GEC-0004/claims/draft/submit'), range(2)))
    assert sorted(r.status_code for r in results) == [201, 400]
    assert len(client.get('/policies/GEC-0004').json()['claims']) == 1


def test_new_app_resets_state(client):
    client.post('/policies/GEC-0004/claims/draft/submit')
    with TestClient(create_app()) as fresh:
        assert fresh.get('/policies/GEC-0004').json()['open_draft'] is not None
