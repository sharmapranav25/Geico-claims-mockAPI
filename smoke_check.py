"""Exercise an already-running server; prints every request and actual response."""
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:8000'


def request(method, path, expected, body=None):
    print(f'\n{method} {BASE}{path}')
    data = None if body is None else json.dumps(body).encode()
    if body is not None:
        print('Request: ' + json.dumps(body))
    req = Request(BASE + path, data=data, method=method, headers={'Content-Type': 'application/json'})
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        result = json.load(response)
        print(f'HTTP {response.status}')
        print(json.dumps(result, ensure_ascii=False))
        assert response.status == expected, (expected, response.status, result)
    return result


if __name__ == '__main__':
    request('GET', '/policies', 200)
    for number in ('1001', '1004', '1007', '1015', 'UNKNOWN'):
        request('GET', '/policies/' + number, 404 if number == 'UNKNOWN' else 200)
    path = '/policies/1015/claims/draft'
    request('POST', path + '/submit', 400)
    request('POST', path, 201, {'description': 'Test scrape while parked.'})
    request('POST', path + '/submit', 400)
    request('POST', path, 200, {
        'occurred_at': '2026-10-31T10:00:00-07:00', 'location': 'Test parking lot',
        'vehicle_id': 'V15-1', 'other_party': {'policy_number': '1014'},
    })
    request('POST', path + '/submit', 201)
    request('POST', path + '/submit', 400)
    request('POST', path, 422, {'name': 'Cannot change identity'})
    request('GET', '/policies/1014', 200)
