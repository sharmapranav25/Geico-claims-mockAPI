"""Standalone in-memory policy reference and claim-intake mock."""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, StringConstraints, AwareDatetime, Field, StrictBool

from seed import make_seed

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class OtherParty(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_number: Text | None = None
    name: Text | None = None
    phone: Text | None = None
    insurer: Text | None = None
    vehicle_description: Text | None = None


class RepresentedPerson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Text | None = None
    relationship: Text | None = None


class PoliceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filed: StrictBool | None = None
    report_number: Text | None = None
    department: Text | None = None


class Witness(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Text | None = None
    phone: Text | None = None


class DraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reporting_intent: Literal["A", "B"] | None = None
    caller_role: Literal["policyholder", "representative", "affected_person"] | None = None
    represented_person: RepresentedPerson | None = None
    caller_name: Text | None = None
    caller_phone: Text | None = None
    occurred_at: AwareDatetime | None = None
    discovered_at: AwareDatetime | None = None
    location: Text | None = None
    description: Text | None = None
    vehicle_id: Text | None = None
    loss_type: Literal["collision", "theft", "weather", "other"] | None = None
    other_party: OtherParty | None = None
    police_report: PoliceReport | None = None
    witnesses: list[Witness] = Field(default_factory=list)
    evidence_link_sent: StrictBool = False


class SubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission_reference: Text


def create_app():
    @asynccontextmanager
    async def lifespan(application):
        application.state.policies, application.state.drafts, application.state.claims = make_seed()
        application.state.references = {}
        application.state.lock = Lock()
        yield

    application = FastAPI(title="Mock GEICO Policy and Claims API", version="1.0.0", lifespan=lifespan)

    @application.get("/", response_class=HTMLResponse)
    def policy_browser():
        return Path(__file__).with_name("index.html").read_text(encoding="utf-8")

    def policy_or_404(number):
        policy = application.state.policies.get(number)
        if policy is None:
            raise HTTPException(404, detail="Policy not found")
        return policy

    @application.get("/policies")
    def list_policies():
        with application.state.lock:
            return [{"policy_number": p["policy_number"], "name": p["name"]}
                    for p in application.state.policies.values()]

    @application.get("/policies/{policy_number}")
    def get_policy(policy_number: str):
        with application.state.lock:
            profile = deepcopy(policy_or_404(policy_number))
            claims = list(application.state.claims.values())
            profile["claims"] = deepcopy([c for c in claims if c["policy_number"] == policy_number])
            profile["open_draft"] = deepcopy(application.state.drafts.get(policy_number))
            # A draft naming another policy is not yet a claim opened against it.
            profile["claims_against"] = [
                {"claim_number": c["claim_number"], "filed_under_policy": c["policy_number"],
                 "status": c["status"]}
                for c in claims
                if (c["loss"].get("other_party") or {}).get("policy_number") == policy_number
            ]
            return profile

    @application.post("/policies/{policy_number}/claims/draft")
    def upsert_draft(policy_number: str, update: DraftUpdate, response: Response):
        with application.state.lock:
            policy = policy_or_404(policy_number)
            changes = update.model_dump(mode="json", exclude_unset=True)
            if changes.get("vehicle_id") is not None and changes["vehicle_id"] not in {
                v["vehicle_id"] for v in policy["vehicles"]
            }:
                raise HTTPException(400, detail="vehicle_id must reference a vehicle on this policy")
            other = changes.get("other_party")
            if other and other.get("policy_number"):
                if other["policy_number"] == policy_number:
                    raise HTTPException(400, detail="Other-party policy must differ from filing policy")
                if other["policy_number"] not in application.state.policies:
                    raise HTTPException(400, detail="Other-party policy number is unknown")
            draft = application.state.drafts.get(policy_number)
            if draft is None:
                draft = {"draft_id": f"draft-{uuid4().hex}", "policy_number": policy_number,
                         "status": "draft", "loss": DraftUpdate().model_dump()}
                application.state.drafts[policy_number] = draft
                response.status_code = 201
            draft["loss"].update(changes)
            return deepcopy(draft)

    @application.post("/policies/{policy_number}/claims/draft/submit", status_code=201)
    def submit_draft(policy_number: str, response: Response, request: SubmitRequest | None = None):
        with application.state.lock:
            policy_or_404(policy_number)
            reference = request.submission_reference if request is not None else None
            key = (policy_number, reference)
            if reference is not None and key in application.state.references:
                response.status_code = 200
                return deepcopy(application.state.claims[application.state.references[key]])
            draft = application.state.drafts.get(policy_number)
            if draft is None:
                raise HTTPException(400, detail="No open draft to submit")
            required = ("occurred_at", "location", "description", "vehicle_id")
            missing = [field for field in required if not draft["loss"].get(field)]
            if missing:
                raise HTTPException(400, detail={"message": "Draft is incomplete", "missing_fields": missing})
            claim = deepcopy(draft)
            claim.update(status="submitted", claim_number=f"CLM-{uuid4().hex[:8].upper()}",
                         submission_reference=reference,
                         submitted_at=datetime.now(timezone.utc).isoformat())
            application.state.claims[claim["claim_number"]] = claim
            if reference is not None:
                application.state.references[key] = claim["claim_number"]
            del application.state.drafts[policy_number]
            return deepcopy(claim)

    @application.get("/policies/{policy_number}/claims/by-reference/{reference}")
    def get_claim_by_reference(policy_number: str, reference: str):
        with application.state.lock:
            policy_or_404(policy_number)
            claim_number = application.state.references.get((policy_number, reference))
            if claim_number is None:
                raise HTTPException(404, detail="Submission not found")
            return deepcopy(application.state.claims[claim_number])

    return application


app = create_app()
