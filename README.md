# Mock GEICO Policy and Claims API

A standalone local FastAPI service for voice-agent HTTP integration tests. It has 15 fabricated policyholders, immutable policy profiles, and an in-memory draft-to-claim lifecycle. Every profile deliberately uses the supplied test phone number, **628-268-8763**. The service never sends SMS or places calls. There is no authentication, identity verification, coverage decision, investigation, or payout logic.

## Run

Python 3.10+ and uv:

```bash
cd '/Users/pranavsharma/Files/personal projects/GEICO Claims Mock API'
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Use **one worker**: all state lives inside that process, resets on restart, and is not shared between processes. Startup seeds a fresh independent store. This project does not use the voice-agent project's environment or dependencies.

Interactive API docs: http://127.0.0.1:8000/docs (also `/redoc`); machine-readable schema: `/openapi.json`.

## Endpoints

| Method | Path | Success |
| --- | --- | --- |
| GET | `/policies` | 200; all policy numbers and names |
| GET | `/policies/{policy_number}` | 200; full profile, submitted `claims`, `open_draft` or null, `claims_against` |
| POST | `/policies/{policy_number}/claims/draft` | 201 when created; 200 when updating the current draft |
| POST | `/policies/{policy_number}/claims/draft/submit` | 201; submitted claim with generated claim number |

The GET endpoints and submit endpoint have no request body. The upsert body is a loss-report object, **not** a policy profile or a wrapper named `loss`.

### Read policies

```bash
curl -sS http://127.0.0.1:8000/policies
curl -sS http://127.0.0.1:8000/policies/GEC-0015
```

The listing returns an array such as `[{"policy_number":"GEC-0001","name":"Avery Morgan"}, ...]`; the complete actual 15-entry response is in `completion-output.txt`.

Example full profile response:

```json
{"policy_number":"GEC-0015","name":"Sage Turner","phone":"628-268-8763","vehicles":[{"vehicle_id":"V15-1","year":2021,"make":"Toyota","model":"Camry"}],"drivers":[{"driver_id":"D15-1","name":"Sage Turner","relationship":"policyholder"}],"beneficiaries":[],"claims":[],"open_draft":null,"claims_against":[]}
```

A policy referenced by a submitted claim includes, for example:

```json
{"claims_against":[{"claim_number":"CLM-SEED-0001","filed_under_policy":"GEC-0001","status":"submitted"}]}
```

This indicates that a claim names the policy as the other party; it does not determine fault or coverage. Naming another policy in an unsubmitted draft does not create a `claims_against` entry.

### Create or update a draft

```bash
curl -sS -X POST http://127.0.0.1:8000/policies/GEC-0015/claims/draft \
  -H 'Content-Type: application/json' \
  -d '{"occurred_at":"2026-10-31T10:00:00-07:00","location":"Test parking lot","description":"Test scrape while parked.","vehicle_id":"V15-1","other_party":{"policy_number":"GEC-0014"}}'
```

Example 201 response (identifiers vary):

```json
{"draft_id":"draft-example","policy_number":"GEC-0015","status":"draft","loss":{"occurred_at":"2026-10-31T10:00:00-07:00","location":"Test parking lot","description":"Test scrape while parked.","vehicle_id":"V15-1","other_party":{"policy_number":"GEC-0014"}}}
```

All request fields are optional while drafting. `{}` creates an empty draft or leaves an existing draft unchanged. Omitted fields retain their current values; explicit `null` clears a field. `other_party`, when supplied, replaces the entire nested object. These partial-update semantics use Pydantic's `exclude_unset`, following [FastAPI's partial-update guidance](https://fastapi.tiangolo.com/tutorial/body-updates/).

| Field | Validation |
| --- | --- |
| `occurred_at` | ISO 8601 timestamp with timezone, or null |
| `location` | Nonblank text, maximum 2,000 characters, or null |
| `description` | Nonblank text, maximum 2,000 characters, or null |
| `vehicle_id` | ID from this policy's vehicles, or null |
| `other_party` | Object with optional `policy_number`, `name`, `insurer`, `description`, or null |

Other-party text fields are also nonblank and at most 2,000 characters if present. An other-party `policy_number` must reference a different seeded policy. For an external insurer, omit that field and use the optional `name`, `insurer`, and `description` fields instead.

Identity, phone, policy number, beneficiaries, vehicles, and listed drivers cannot be changed. Unknown request fields, including `claim_number`, `status`, and `draft_id`, are rejected rather than silently ignored. There are no profile-update or submitted-claim-update routes.

### Submit

```bash
curl -sS -X POST http://127.0.0.1:8000/policies/GEC-0015/claims/draft/submit
```

Example 201 response (identifiers and submission timestamp vary):

```json
{"draft_id":"draft-example","policy_number":"GEC-0015","status":"submitted","loss":{"occurred_at":"2026-10-31T10:00:00-07:00","location":"Test parking lot","description":"Test scrape while parked.","vehicle_id":"V15-1","other_party":{"policy_number":"GEC-0014"}},"claim_number":"CLM-EXAMPLE","submitted_at":"2026-11-01T20:00:00+00:00"}
```

Submission requires `occurred_at`, `location`, `description`, and `vehicle_id`. It atomically copies the draft to a locked submitted claim and removes the open draft. The generated claim number is returned only after that succeeds. Concurrent submissions of one draft create one claim; the other request receives 400. There is no durable idempotency across restarts.

A later upsert creates a **new** draft for a separate report, with a new draft ID, without modifying any submitted claim. Repeating submit without a new draft returns 400. Each policy has at most one open draft, but can have multiple submitted claims.

### Errors

| Status | Meaning | Example response |
| --- | --- | --- |
| 404 | Unknown target policy | `{"detail":"Policy not found"}` |
| 400 | No open draft to submit | `{"detail":"No open draft to submit"}` |
| 400 | Missing submission fields | `{"detail":{"message":"Draft is incomplete","missing_fields":["location"]}}` |
| 400 | Vehicle not on this policy | `{"detail":"vehicle_id must reference a vehicle on this policy"}` |
| 400 | Invalid other-party reference | `{"detail":"Other-party policy number is unknown"}` or `{"detail":"Other-party policy must differ from filing policy"}` |
| 422 | Invalid JSON/schema, blank strings, invalid timestamp, or forbidden fields | `{"detail":[{"type":"extra_forbidden","loc":["body","name"],"msg":"Extra inputs are not permitted","input":"Changed"}]}` |
| 405 | Unsupported method on an existing route | `{"detail":"Method Not Allowed"}` |

Invalid requests leave existing data unchanged. FastAPI validates request bodies before route execution, so a malformed body can produce 422 even if its target policy is unknown.

## Seed breakdown

| Category | Policy numbers |
| --- | --- |
| Multiple beneficiaries (2–3 beyond policyholder) | GEC-0001, GEC-0002, GEC-0003, GEC-0004, GEC-0005 |
| Multiple vehicles (2–3 total) | GEC-0004, GEC-0005, GEC-0006, GEC-0007, GEC-0008 |
| Multiple additional listed drivers (2–3 beyond policyholder) | GEC-0008, GEC-0009, GEC-0010, GEC-0011, GEC-0012 |
| Submitted claim filed by policyholder | GEC-0001, GEC-0002, GEC-0003 |
| Open draft | GEC-0004, GEC-0005, GEC-0006 |
| Named as other party in a submitted claim | GEC-0007 (filed under GEC-0001), GEC-0008 (filed under GEC-0002) |
| No claim activity | GEC-0009, GEC-0010, GEC-0011, GEC-0012, GEC-0013, GEC-0014, GEC-0015 |

The reference-data groups intentionally overlap at 0004/0005 and 0008. Their union covers 12 of 15 policies, leaving three simple baseline profiles. Each profile always has its policyholder listed as a driver and at least one vehicle. Outside the beneficiary group, the beneficiary list is empty. These mock beneficiary labels do not establish authority or imply real product terms.

## Tests and actual HTTP demonstration

```bash
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

With a freshly started server in another terminal:

```bash
.venv/bin/python smoke_check.py > completion-output.txt
cat completion-output.txt
```

`smoke_check.py` uses Python's standard-library HTTP client. It prints exact methods, URLs, request bodies, status codes, and response bodies and asserts expected status codes. `completion-output.txt` is the captured actual run, including all 15 policy selections, all four seeded activity states, unknown-policy 404, create/update/submit, missing/incomplete draft failures, read-only-field rejection, and the new other-party linkage.

The demonstration changes GEC-0015 and GEC-0014; restart the server before rerunning it to restore the documented seed states. Unit tests use isolated stores and cover immutability, partial updates, null clearing, bad references, and concurrent submission. The tested dependency combination emits a Starlette warning about future TestClient HTTP transport changes; all 22 tests pass.
