"""Deterministic fictitious profiles and initial claim activity."""

NAMES = [
    "Avery Morgan", "Blair Chen", "Casey Rivera", "Devon Patel", "Emery Brooks",
    "Finley Kim", "Harper Singh", "Jordan Ellis", "Kai Bennett", "Logan Reed",
    "Morgan Hayes", "Parker Diaz", "Quinn Foster", "Riley Nguyen", "Sage Turner",
]


def make_seed():
    policies, drafts, claims = {}, {}, {}
    # Groups 1–5, 4–8, and 8–12 overlap while covering 12/15 policies.
    # This gives both combined and isolated reference-data cases in a small pool.
    for i, name in enumerate(NAMES, 1):
        number = f"GEC-{i:04d}"
        vehicles = [
            {"vehicle_id": f"V{i:02d}-{j}", "year": 2020 + j,
             "make": "Toyota" if j == 1 else "Honda",
             "model": "Camry" if j == 1 else "Civic"}
            for j in range(1, (2 + i % 2 if 4 <= i <= 8 else 1) + 1)
        ]
        drivers = [{"driver_id": f"D{i:02d}-1", "name": name, "relationship": "policyholder"}]
        if 8 <= i <= 12:
            drivers.extend(
                {"driver_id": f"D{i:02d}-{j + 1}", "name": f"{name} Driver {j}",
                 "relationship": "household member"}
                for j in range(1, 3 + i % 2)
            )
        beneficiaries = [
            {"name": f"{name} Beneficiary {j}", "relationship": "family member"}
            for j in range(1, (2 + i % 2 if i <= 5 else 0) + 1)
        ]
        policies[number] = {
            "policy_number": number, "name": name, "phone": "628-268-8753",
            "vehicles": vehicles, "drivers": drivers, "beneficiaries": beneficiaries,
        }
        if i <= 6:
            report = {
                "draft_id": f"seed-draft-{i:04d}", "policy_number": number,
                "status": "submitted" if i <= 3 else "draft",
                "loss": {
                    "reporting_intent": "B" if i == 2 else "A",
                    "caller_role": "representative" if i == 4 else "affected_person" if i == 2 else "policyholder",
                    "represented_person": {"name": name, "relationship": "parent"} if i == 4 else None,
                    "caller_name": "Taylor Patel" if i == 4 else name,
                    "caller_phone": "628-268-8753",
                    "occurred_at": "2026-10-20T14:30:00-07:00",
                    "discovered_at": "2026-10-20T17:00:00-07:00" if i == 4 else None,
                    "location": "Mock parking lot",
                    "loss_type": ("collision", "collision", "weather", "theft", "other", "weather")[i - 1],
                    "description": (
                        "Another vehicle scraped the parked car.",
                        "A vehicle insured under the other policy struck my parked car.",
                        "Hail dented the parked car.",
                        "Reporting for my parent: their parked car was stolen.",
                        "A shopping cart scratched the parked car.",
                        "A storm-damaged branch fell onto the parked car.",
                    )[i - 1],
                    "vehicle_id": vehicles[0]["vehicle_id"],
                    "other_party": {
                        "policy_number": f"GEC-{i + 6:04d}", "name": NAMES[i + 5],
                        "phone": "628-268-8753", "insurer": "GEICO",
                        "vehicle_description": "2021 Toyota Camry",
                    } if i <= 2 else None,
                    "police_report": {
                        "filed": True, "report_number": f"MOCK-REPORT-{i:04d}",
                        "department": "Mock City Police",
                    } if i in (1, 4) else {"filed": False} if i == 2 else None,
                    "witnesses": [{"name": "Alex Sample", "phone": "628-268-8753"}] if i == 1 else [],
                    # A recorded mock flag only; no message is actually sent.
                    "evidence_link_sent": i == 2,
                },
            }
            if i <= 3:
                report.update(claim_number=f"CLM-SEED-{i:04d}", submitted_at="2026-10-21T12:00:00+00:00")
                claims[report["claim_number"]] = report
            else:
                drafts[number] = report
    return policies, drafts, claims
