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
            "policy_number": number, "name": name, "phone": "628-268-8763",
            "vehicles": vehicles, "drivers": drivers, "beneficiaries": beneficiaries,
        }
        if i <= 6:
            report = {
                "draft_id": f"seed-draft-{i:04d}", "policy_number": number,
                "status": "submitted" if i <= 3 else "draft",
                "loss": {
                    "occurred_at": "2026-10-20T14:30:00-07:00", "location": "Mock parking lot",
                    "description": "Test vehicle damage while parked.",
                    "vehicle_id": vehicles[0]["vehicle_id"],
                    "other_party": {"policy_number": f"GEC-{i + 6:04d}"} if i <= 2 else None,
                },
            }
            if i <= 3:
                report.update(claim_number=f"CLM-SEED-{i:04d}", submitted_at="2026-10-21T12:00:00+00:00")
                claims[report["claim_number"]] = report
            else:
                drafts[number] = report
    return policies, drafts, claims
