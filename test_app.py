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
    assert all(p['phone'] == '628-268-8753' and p['vehicles'] and p['drivers'] for p in policies.values())
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


def test_expanded_template_round_trip_and_profile_unchanged(client):
    base = '/policies/GEC-0015'
    before = client.get(base).json()
    payload = {
        'reporting_intent': 'A', 'caller_role': 'representative',
        'represented_person': {'name': 'Sage Turner', 'relationship': 'parent'},
        'caller_name': 'Jamie Turner', 'caller_phone': '628-268-8753',
        'occurred_at': '2026-10-31T10:00:00-07:00',
        'discovered_at': '2026-10-31T11:00:00-07:00',
        'location': 'Test lot', 'description': 'A vehicle scraped the parked car.',
        'vehicle_id': 'V15-1', 'loss_type': 'collision',
        'other_party': {'name': 'Riley Nguyen', 'phone': '628-268-8753',
                        'insurer': 'GEICO', 'policy_number': 'GEC-0014',
                        'vehicle_description': '2021 Toyota Camry'},
        'police_report': {'filed': True, 'report_number': 'MOCK-123', 'department': 'Mock Police'},
        'witnesses': [{'name': 'Alex Sample', 'phone': '628-268-8753'}],
        'evidence_link_sent': True,
    }
    response = client.post(base + '/claims/draft', json=payload)
    assert response.status_code == 201
    assert response.json()['loss'] == payload
    assert client.get(base).json()['open_draft']['loss'] == payload
    changed = client.post(base + '/claims/draft', json={'description': 'Updated account.'})
    payload['description'] = 'Updated account.'
    assert changed.status_code == 200 and changed.json()['loss'] == payload
    submitted = client.post(base + '/claims/draft/submit')
    assert submitted.status_code == 201 and submitted.json()['loss'] == payload
    after = client.get(base).json()
    assert after['claims'][0]['loss'] == payload
    for field in ('policy_number', 'name', 'phone', 'vehicles', 'drivers', 'beneficiaries'):
        assert after[field] == before[field]


@pytest.mark.parametrize('payload', [
    {'reporting_intent': 'C'}, {'caller_role': 'owner'}, {'loss_type': 'fire'},
    {'represented_person': {'policy_number': 'GEC-0001'}},
    {'police_report': {'unknown': True}}, {'witnesses': [{'unknown': 'value'}]},
    {'other_party': {'description': 'Old field is no longer supported'}},
    {'discovered_at': 'not-a-date'}, {'discovered_at': '2026-10-31T10:00:00'},
    {'police_report': {'filed': 'yes'}}, {'evidence_link_sent': 'true'},
    {'witnesses': None}, {'evidence_link_sent': None},
])
def test_expanded_template_rejects_invalid_fields(client, payload):
    before = client.get('/policies/GEC-0004').json()
    assert client.post('/policies/GEC-0004/claims/draft', json=payload).status_code == 422
    assert client.get('/policies/GEC-0004').json() == before


def test_new_defaults_and_partial_object_replacement(client):
    path = '/policies/GEC-0015/claims/draft'
    loss = client.post(path, json={}).json()['loss']
    assert loss['witnesses'] == [] and loss['evidence_link_sent'] is False
    assert loss['reporting_intent'] is None and loss['police_report'] is None
    client.post(path, json={
        'police_report': {'filed': True, 'department': 'Mock Police'},
        'represented_person': {'name': 'Sage Turner'},
        'witnesses': [{'name': 'Alex Sample'}], 'evidence_link_sent': True,
    })
    loss = client.post(path, json={'police_report': {'filed': False}}).json()['loss']
    assert loss['police_report'] == {'filed': False}
    assert loss['witnesses'] == [{'name': 'Alex Sample'}]
    assert loss['evidence_link_sent'] is True
    loss = client.post(path, json={
        'police_report': None, 'represented_person': None,
        'witnesses': [], 'evidence_link_sent': False,
    }).json()['loss']
    assert loss['police_report'] is None and loss['represented_person'] is None
    assert loss['witnesses'] == [] and loss['evidence_link_sent'] is False
    assert client.post('/policies/GEC-0013/claims/draft', json={}).json()['loss']['witnesses'] == []


def test_seed_claims_match_expanded_template():
    from app import DraftUpdate

    _, drafts, claims = make_seed()
    losses = [record['loss'] for record in [*drafts.values(), *claims.values()]]
    for loss in losses:
        DraftUpdate.model_validate(loss)
        assert set(loss) == set(DraftUpdate.model_fields)
    assert {loss['reporting_intent'] for loss in losses} == {'A', 'B'}
    assert {loss['caller_role'] for loss in losses} == {'policyholder', 'representative', 'affected_person'}
    assert {loss['loss_type'] for loss in losses} == {'collision', 'theft', 'weather', 'other'}


def test_submission_reference_replays_deleted_draft(client):
    import re

    path = '/policies/GEC-0004/claims/draft/submit'
    before = len(client.get('/policies/GEC-0004').json()['claims'])
    first = client.post(path, json={'submission_reference': 'sub-test'})
    assert first.status_code == 201
    claim = first.json()
    assert claim['submission_reference'] == 'sub-test'
    assert re.fullmatch(r'CLM-[0-9A-F]{8}', claim['claim_number'])
    assert client.get('/policies/GEC-0004').json()['open_draft'] is None
    replay = client.post(path, json={'submission_reference': 'sub-test'})
    assert replay.status_code == 200
    assert replay.json() == claim
    assert len(client.get('/policies/GEC-0004').json()['claims']) == before + 1
    assert client.post(path, json={'submission_reference': 'sub-new'}).status_code == 400
    client.post('/policies/GEC-0004/claims/draft', json={'description': 'New draft'})
    assert client.post(path, json={'submission_reference': 'sub-test'}).json() == claim
    assert client.get('/policies/GEC-0004').json()['open_draft']['loss']['description'] == 'New draft'


def test_submission_reference_is_scoped_to_policy(client):
    payload = {'submission_reference': 'sub-shared'}
    first = client.post('/policies/GEC-0004/claims/draft/submit', json=payload)
    other = client.post('/policies/GEC-0005/claims/draft/submit', json=payload)
    assert first.status_code == other.status_code == 201
    assert first.json()['claim_number'] != other.json()['claim_number']
    assert other.json()['policy_number'] == 'GEC-0005'
    assert client.post('/policies/GEC-0015/claims/draft/submit', json=payload).status_code == 400


def test_concurrent_reference_submissions_create_one_claim(client):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post('/policies/GEC-0004/claims/draft/submit',
                            json={'submission_reference': 'sub-concurrent'}), range(2)))
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json() == results[1].json()
    assert len(client.get('/policies/GEC-0004').json()['claims']) == 1


def test_submit_without_body_and_unknown_field(client):
    path = '/policies/GEC-0004/claims/draft/submit'
    assert client.post(path, json={'submission_reference': 'sub-test', 'unknown': True}).status_code == 422
    response = client.post(path)
    assert response.status_code == 201
    assert response.json()['submission_reference'] is None
    assert client.post(path).status_code == 400
