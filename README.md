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
  -d '{"reporting_intent":"A","caller_role":"representative","represented_person":{"name":"Sage Turner","relationship":"parent"},"caller_name":"Jamie Turner","caller_phone":"628-268-8763","occurred_at":"2026-10-31T10:00:00-07:00","discovered_at":"2026-10-31T11:00:00-07:00","location":"Test parking lot","description":"Test scrape while parked.","vehicle_id":"V15-1","loss_type":"collision","other_party":{"name":"Riley Nguyen","phone":"628-268-8763","insurer":"GEICO","policy_number":"GEC-0014","vehicle_description":"2021 Toyota Camry"},"police_report":{"filed":true,"report_number":"MOCK-123","department":"Mock Police"},"witnesses":[{"name":"Alex Sample","phone":"628-268-8763"}],"evidence_link_sent":false}'
```

Example 201 response (identifiers vary):

```json
{"draft_id":"draft-example","policy_number":"GEC-0015","status":"draft","loss":{"reporting_intent":"A","caller_role":"representative","represented_person":{"name":"Sage Turner","relationship":"parent"},"caller_name":"Jamie Turner","caller_phone":"628-268-8763","occurred_at":"2026-10-31T10:00:00-07:00","discovered_at":"2026-10-31T11:00:00-07:00","location":"Test parking lot","description":"Test scrape while parked.","vehicle_id":"V15-1","loss_type":"collision","other_party":{"name":"Riley Nguyen","phone":"628-268-8763","insurer":"GEICO","policy_number":"GEC-0014","vehicle_description":"2021 Toyota Camry"},"police_report":{"filed":true,"report_number":"MOCK-123","department":"Mock Police"},"witnesses":[{"name":"Alex Sample","phone":"628-268-8763"}],"evidence_link_sent":false}}
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
curl -sS -X POST http://127.0.0.1:8000/policies/GEC-0015/claims/draft/submit
```

Example 201 response (identifiers and submission timestamp vary):

```json
{"draft_id":"draft-example","policy_number":"GEC-0015","status":"submitted","loss":{"reporting_intent":"A","caller_role":"representative","represented_person":{"name":"Sage Turner","relationship":"parent"},"caller_name":"Jamie Turner","caller_phone":"628-268-8763","occurred_at":"2026-10-31T10:00:00-07:00","discovered_at":"2026-10-31T11:00:00-07:00","location":"Test parking lot","description":"Test scrape while parked.","vehicle_id":"V15-1","loss_type":"collision","other_party":{"name":"Riley Nguyen","phone":"628-268-8763","insurer":"GEICO","policy_number":"GEC-0014","vehicle_description":"2021 Toyota Camry"},"police_report":{"filed":true,"report_number":"MOCK-123","department":"Mock Police"},"witnesses":[{"name":"Alex Sample","phone":"628-268-8763"}],"evidence_link_sent":false},"claim_number":"CLM-EXAMPLE","submitted_at":"2026-11-01T20:00:00+00:00"}
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

The six seeded report bodies exercise the expanded template:

| Policy | Intent / caller | Loss and optional details |
| --- | --- | --- |
| GEC-0001 | A / policyholder | Collision; other party GEC-0007; police report and witness |
| GEC-0002 | B / affected_person | Collision; other party GEC-0008; no police filing; mock evidence flag true |
| GEC-0003 | A / policyholder | Weather / hail; optional objects null |
| GEC-0004 | A / representative | Taylor Patel reports for parent Devon Patel; theft, later discovery, police report |
| GEC-0005 | A / policyholder | Other / shopping cart damage |
| GEC-0006 | A / policyholder | Weather / fallen branch |

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

`smoke_check.py` uses Python's standard-library HTTP client. It prints exact methods, URLs, request bodies, status codes, and response bodies and asserts expected status codes. `completion-output.txt` is the historical initial run (before the expanded claim template), including all 15 policy selections, all four seeded activity states, unknown-policy 404, create/update/submit, missing/incomplete draft failures, read-only-field rejection, and the new other-party linkage.

The demonstration changes GEC-0015 and GEC-0014; restart the server before rerunning it to restore the documented seed states. Unit tests use isolated stores and cover immutability, partial updates, null clearing, bad references, and concurrent submission. The tested dependency combination emits a Starlette warning about future TestClient HTTP transport changes; the suite covers the expanded template in addition to the original checks.
