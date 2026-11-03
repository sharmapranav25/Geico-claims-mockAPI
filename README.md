# Mock GEICO Policy and Claims API

A standalone local FastAPI service for voice-agent HTTP integration tests. It has 15 fabricated policyholders, immutable policy profiles, and an in-memory draft-to-claim lifecycle. Each profile has its own fake phone number in the 628-555-01xx range, such as **628-555-0115** for policy 1015. The service never sends SMS or places calls. There is no authentication, identity verification, coverage decision, investigation, or payout logic.

## Run

Python 3.10+ and uv:

```bash
git clone https://github.com/sharmapranav25/Geico-claims-mockAPI.git
cd Geico-claims-mockAPI
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Use **one worker**: all state lives inside that process, resets on restart, and is not shared between processes. Startup seeds a fresh independent store. This project does not use the voice-agent project's environment or dependencies.

Policy page: http://127.0.0.1:8000/ shows each policy's owner, phone number, vehicles, drafts and claims. Refresh it after a call to see what changed.

Interactive API docs: http://127.0.0.1:8000/docs (also `/redoc`); machine-readable schema: `/openapi.json`.

## Simulating failures

The service has no setting to force an error, so stop the server to simulate an outage:

- **API down at the start of a call:** press Ctrl+C in the server terminal before the call begins.
- **API goes down mid-call:** press Ctrl+C while the call is in progress. To test an uncertain filing, do this during the agent's claim read-back, before approving the claim.

Restart the server afterwards. Restarting clears all drafts and claims.

## Endpoints

| Method | Path | Success |
| --- | --- | --- |
| GET | `/availability` | 200; representative availability (false in this demo) |
| POST | `/callbacks` | 201; callback time, phone, session ID and generated callback ID; no policy required |
| GET | `/policies` | 200; all policy numbers and names |
| GET | `/policies/{policy_number}` | 200; full profile, submitted `claims`, `open_draft` or null, `claims_against` |
| GET | `/policies/{policy_number}/claims/by-reference/{reference}` | 200 with the submitted claim; 404 if the policy or submission reference is not found |
| POST | `/policies/{policy_number}/claims/draft` | 201 when created; 200 when updating the current draft |
| POST | `/policies/{policy_number}/claims/draft/submit` | Optional `submission_reference` body; 201 for a new claim, 200 with the same claim on reference replay for that policy, even after draft deletion |

The GET endpoints have no request body. Submit accepts an optional `{ "submission_reference": "sub-example" }` body; repeating the reference for the same policy returns the original claim with HTTP 200, even after its draft is deleted. Omitting the body keeps the existing submission behavior. The upsert body is a loss-report object, **not** a policy profile or a wrapper named `loss`.

### Read policies

```bash
curl -sS http://127.0.0.1:8000/policies
curl -sS http://127.0.0.1:8000/policies/1015
```

The listing returns an array such as `[{"policy_number":"1001","name":"Michael Johnson"}, ...]`; the complete actual 15-entry response is in `completion-output.txt`.

Example full profile response:

```json
{"policy_number":"1015","name":"Daniel Young","phone":"628-555-0115","vehicles":[{"vehicle_id":"V15-1","year":2021,"make":"Toyota","model":"Camry"}],"drivers":[{"driver_id":"D15-1","name":"Daniel Young","relationship":"policyholder"}],"beneficiaries":[],"claims":[],"open_draft":null,"claims_against":[]}
```

A policy referenced by a submitted claim includes, for example:

```json
{"claims_against":[{"claim_number":"CLM-SEED-0001","filed_under_policy":"1001","status":"submitted"}]}
```

This indicates that a claim names the policy as the other party; it does not determine fault or coverage. Naming another policy in an unsubmitted draft does not create a `claims_against` entry.

### Create or update a draft

```bash
curl -sS -X POST http://127.0.0.1:8000/policies/1015/claims/draft \
  -H 'Content-Type: application/json' \
  -d '{"reporting_intent":"A","caller_role":"representative","represented_person":{"name":"Daniel Young","relationship":"parent"},"caller_name":"Jamie Turner","caller_phone":"628-555-0190","occurred_at":"2026-10-31T10:00:00-07:00","discovered_at":"2026-10-31T11:00:00-07:00","location":"Test parking lot","description":"Test scrape while parked.","vehicle_id":"V15-1","loss_type":"collision","other_party":{"name":"Lisa Hall","phone":"628-555-0114","insurer":"GEICO","policy_number":"1014","vehicle_description":"2021 Toyota Camry"},"police_report":{"filed":true,"report_number":"MOCK-123","department":"Mock Police"},"witnesses":[{"name":"Alex Sample","phone":"628-555-0191"}],"evidence_link_sent":false}'
```

Example 201 response (identifiers vary):

```json
{"draft_id":"draft-example","policy_number":"1015","status":"draft","loss":{"reporting_intent":"A","caller_role":"representative","represented_person":{"name":"Daniel Young","relationship":"parent"},"caller_name":"Jamie Turner","caller_phone":"628-555-0190","occurred_at":"2026-10-31T10:00:00-07:00","discovered_at":"2026-10-31T11:00:00-07:00","location":"Test parking lot","description":"Test scrape while parked.","vehicle_id":"V15-1","loss_type":"collision","other_party":{"name":"Lisa Hall","phone":"628-555-0114","insurer":"GEICO","policy_number":"1014","vehicle_description":"2021 Toyota Camry"},"police_report":{"filed":true,"report_number":"MOCK-123","department":"Mock Police"},"witnesses":[{"name":"Alex Sample","phone":"628-555-0191"}],"evidence_link_sent":false}}
```

All request fields are optional on each update. `{}` creates an empty draft or leaves an existing draft unchanged. Omitted fields retain their current values. Explicit `null` clears nullable fields; clear `witnesses` with `[]` and reset `evidence_link_sent` with `false` (neither accepts null). Nested objects and lists, when supplied, replace the entire previous object/list rather than merging individual sub-fields. These partial-update semantics retain `exclude_unset`.

All text values below are nonblank, stripped, and at most 2,000 characters when supplied. Phone fields are text, with no added formatting restriction. Except for `witnesses` and `evidence_link_sent`, fields default to null.

| Field | Validation / meaning |
| --- | --- |
| `reporting_intent` | `"A"` (own/relevant GEICO policy) or `"B"` (damage allegedly caused by a GEICO insured), or null |
| `caller_role` | `"policyholder"`, `"representative"`, `"affected_person"`, or null |
| `represented_person` | Object with optional nullable text `name`, `relationship`, or null; relationship describes the represented person's relationship to the caller |
| `caller_name`, `caller_phone` | Nullable text describing the actual caller, independent of read-only profile name/phone |
| `occurred_at` | ISO 8601 timestamp with timezone, or null |
| `discovered_at` | ISO 8601 timestamp with timezone, or null; may differ from loss time |
| `location`, `description` | Nullable text |
| `vehicle_id` | ID from this policy's vehicles, or null (existing validation retained for both intents) |
| `loss_type` | `"collision"`, `"theft"`, `"weather"`, `"other"`, or null |
| `other_party` | Object with optional nullable text `name`, `phone`, `insurer`, `policy_number`, `vehicle_description`, or null |
| `police_report` | Object with optional nullable `filed` (JSON boolean), `report_number`, `department` (text), or null |
| `witnesses` | List of objects with optional nullable text `name`, `phone`; defaults to `[]` |
| `evidence_link_sent` | JSON boolean, defaults to `false`; records a supplied flag only and does not send a message |

An other-party `policy_number` must reference a different seeded policy. For an external insurer, omit that field and use the other optional fields. The former nested `other_party.description` field is replaced by `vehicle_description` and is now rejected. Unknown fields are forbidden in every nested object as well as the top-level update.

`represented_person` is intended for representative callers, but this mock does not impose cross-field role/intent gates while collecting partial reports. Nested sub-fields can be collected incompletely. No new fields are required for submission; the existing four remain the only required fields.

Profile identity (`name`), `phone`, `policy_number`, `beneficiaries`, `vehicles`, and `drivers` cannot be changed; editable `caller_name` and `caller_phone` only belong to the claim report. Unknown request fields, including `claim_number`, `status`, and `draft_id`, are rejected rather than silently ignored. There are no profile-update or submitted-claim-update routes.

### Submit

```bash
curl -sS -X POST http://127.0.0.1:8000/policies/1015/claims/draft/submit
```

Example 201 response (identifiers and submission timestamp vary):

```json
{"draft_id":"draft-example","policy_number":"1015","status":"submitted","loss":{"reporting_intent":"A","caller_role":"representative","represented_person":{"name":"Daniel Young","relationship":"parent"},"caller_name":"Jamie Turner","caller_phone":"628-555-0190","occurred_at":"2026-10-31T10:00:00-07:00","discovered_at":"2026-10-31T11:00:00-07:00","location":"Test parking lot","description":"Test scrape while parked.","vehicle_id":"V15-1","loss_type":"collision","other_party":{"name":"Lisa Hall","phone":"628-555-0114","insurer":"GEICO","policy_number":"1014","vehicle_description":"2021 Toyota Camry"},"police_report":{"filed":true,"report_number":"MOCK-123","department":"Mock Police"},"witnesses":[{"name":"Alex Sample","phone":"628-555-0191"}],"evidence_link_sent":false},"claim_number":"CLM-EXAMPLE","submitted_at":"2026-11-01T20:00:00+00:00"}
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
| Multiple beneficiaries (2–3 beyond policyholder) | 1001, 1002, 1003, 1004, 1005 |
| Multiple vehicles (2–3 total) | 1004, 1005, 1006, 1007, 1008 |
| Multiple additional listed drivers (2–3 beyond policyholder) | 1008, 1009, 1010, 1011, 1012 |
| Submitted claim filed by policyholder | 1001, 1002, 1003 |
| Open draft | 1004, 1005, 1006 |
| Named as other party in a submitted claim | 1007 (filed under 1001), 1008 (filed under 1002) |
| No claim activity | 1009, 1010, 1011, 1012, 1013, 1014, 1015 |

The reference-data groups intentionally overlap at 1004/1005 and 1008. Their union covers 12 of 15 policies, leaving three simple baseline profiles. Each profile always has its policyholder listed as a driver and at least one vehicle. Outside the beneficiary group, the beneficiary list is empty. These mock beneficiary labels do not establish authority or imply real product terms.

The six seeded report bodies exercise the expanded template:

| Policy | Intent / caller | Loss and optional details |
| --- | --- | --- |
| 1001 | A / policyholder | Collision; other party 1007; police report and witness |
| 1002 | B / affected_person | Collision; other party 1008; no police filing; mock evidence flag true |
| 1003 | A / policyholder | Weather / hail; optional objects null |
| 1004 | A / representative | Mark Davis reports for parent Emily Davis; theft, later discovery, police report |
| 1005 | A / policyholder | Other / shopping cart damage |
| 1006 | A / policyholder | Weather / fallen branch |

These are stored intake examples, not verification of authority or claims workflow decisions.

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

`smoke_check.py` uses Python's standard-library HTTP client. It prints exact methods, URLs, request bodies, status codes, and response bodies and asserts expected status codes. `completion-output.txt` is a captured run against a freshly started server, including all 15 policy selections, all four seeded activity states, unknown-policy 404, create/update/submit, missing/incomplete draft failures, read-only-field rejection, and the new other-party linkage.

The demonstration changes 1015 and 1014; restart the server before rerunning it to restore the documented seed states. Unit tests use isolated stores and cover immutability, partial updates, null clearing, bad references, and concurrent submission. The tested dependency combination emits a Starlette warning about future TestClient HTTP transport changes; the suite covers the expanded template in addition to the original checks.
