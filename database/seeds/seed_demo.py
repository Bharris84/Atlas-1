"""Seed a few properties so a fresh install has something to look at.

Every property here is fictional and every number is invented. They exist to
exercise the interface, not to represent real deals — the addresses are not
real listings and nothing here should be treated as market data.

    python database/seeds/seed_demo.py
"""

from __future__ import annotations

import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from atlas_financial_engine import ASSUMPTIONS_SCHEMA_VERSION  # noqa: E402

from atlas_api.auth import CurrentUser  # noqa: E402
from atlas_api.config import get_settings  # noqa: E402
from atlas_api.db import SessionLocal, init_db  # noqa: E402
from atlas_api.models import Comp, DealAnalysis, Lead, Owner, Property  # noqa: E402
from atlas_api.services.analysis import (  # noqa: E402
    apply_to_model,
    build_deal_inputs,
    run_analysis,
)
from atlas_api.services.audit import record_assumption_changes  # noqa: E402

# Spread across the initial focus states. Nothing in the codebase is
# specialised to any of them; the geography is data, not logic.
DEMO_PROPERTIES = [
    {
        "address": "412 Magnolia Street",
        "city": "Chattanooga",
        "state": "TN",
        "zip_code": "37402",
        "county": "Hamilton",
        "property_type": "single_family",
        "bedrooms": "3",
        "bathrooms": "2",
        "square_feet": "1450",
        "year_built": 1998,
        "property_status": "analyzing",
        "analysis": {
            "purchase_price": "150000",
            "arv": "250000",
            "rehab": "45000",
            "monthly_rent": "1800",
            "evidence": {
                "arv_basis": "comparable_sales",
                "comp_count": 5,
                "average_comp_similarity": "0.85",
                "average_comp_age_days": 75,
                "rehab_basis": "contractor_bid",
                "rent_basis": "rental_comps",
                "property_visited": True,
                "title_reviewed": True,
                "inspection_completed": True,
            },
            # schema_version is declared explicitly: an assumptions blob
            # without it is read with pre-tri-state semantics, where a 0 for
            # taxes or insurance meant "unfilled" rather than "none".
            "assumptions": {
                "schema_version": ASSUMPTIONS_SCHEMA_VERSION,
                "rental": {
                    "annual_taxes": "2400",
                    "annual_insurance": "1800",
                    "monthly_hoa": "0",
                },
                "holding": {
                    "annual_taxes": "2400",
                    "annual_insurance": "1800",
                    "monthly_hoa": "0",
                    "monthly_utilities": "150",
                },
            },
        },
        "lead_type": "long_DOM",
        "comps": [
            {"address": "418 Magnolia Street", "sale_price": "248000", "similarity_score": "0.93"},
            {"address": "1207 Oak Avenue", "sale_price": "255000", "similarity_score": "0.81"},
        ],
    },
    {
        "address": "88 Pinecrest Road",
        "city": "Greenville",
        "state": "SC",
        "zip_code": "29601",
        "property_type": "single_family",
        "bedrooms": "4",
        "bathrooms": "2",
        "square_feet": "1850",
        "year_built": 1974,
        "property_status": "prospect",
        # Deliberately thin evidence: this one should land in human review, and
        # demonstrates that a good-looking score does not equal a green light.
        "analysis": {
            "purchase_price": "119000",
            "arv": "215000",
            "rehab": "38000",
            "monthly_rent": "1650",
            "evidence": {"arv_basis": "automated_valuation", "rehab_basis": "per_sqft_estimate"},
            # No assumptions at all: this property demonstrates the unknown
            # operating expense flag alongside the thin valuation evidence.
        },
        "lead_type": "absentee",
        "comps": [],
    },
    {
        "address": "3390 Belmont Drive",
        "city": "Little Rock",
        "state": "AR",
        "zip_code": "72204",
        "property_type": "single_family",
        "bedrooms": "3",
        "bathrooms": "1",
        "square_feet": "1120",
        "year_built": 1955,
        "property_status": "prospect",
        "analysis": {
            "purchase_price": "72000",
            "arv": "145000",
            "rehab": "32000",
            "monthly_rent": "1250",
            "evidence": {
                "arv_basis": "comparable_sales",
                "comp_count": 4,
                "average_comp_similarity": "0.78",
                "average_comp_age_days": 120,
                "rehab_basis": "walkthrough",
                "rent_basis": "rental_comps",
                "property_visited": True,
            },
            "assumptions": {
                "schema_version": ASSUMPTIONS_SCHEMA_VERSION,
                "rental": {
                    "annual_taxes": "1100",
                    "annual_insurance": "1400",
                    "monthly_hoa": "0",
                },
                "holding": {
                    "annual_taxes": "1100",
                    "annual_insurance": "1400",
                    "monthly_hoa": "0",
                    "monthly_utilities": "120",
                },
            },
        },
        "lead_type": "vacant",
        "comps": [
            {"address": "3402 Belmont Drive", "sale_price": "142000", "similarity_score": "0.88"},
        ],
    },
]


def seed() -> None:
    settings = get_settings()
    init_db()
    user = CurrentUser(id=uuid.UUID(settings.dev_user_id), email=settings.dev_user_email)

    with SessionLocal() as db:
        existing = db.query(Property).filter(Property.owner_id == user.id).count()
        if existing:
            print(f"{existing} propert(ies) already present for the demo user; nothing seeded.")
            return

        for spec in DEMO_PROPERTIES:
            analysis_spec = spec.pop("analysis")
            lead_type = spec.pop("lead_type", None)
            comps = spec.pop("comps", [])

            row = Property(owner_id=user.id, **{
                k: (Decimal(v) if k in {"bedrooms", "bathrooms", "square_feet"} else v)
                for k, v in spec.items()
            })
            db.add(row)
            db.flush()

            for comp in comps:
                db.add(
                    Comp(
                        property_id=row.id,
                        address=comp["address"],
                        sale_price=Decimal(comp["sale_price"]),
                        similarity_score=Decimal(comp["similarity_score"]),
                        source="seed",
                    )
                )

            if lead_type:
                db.add(
                    Lead(
                        property_id=row.id,
                        owner_id=user.id,
                        lead_type=lead_type,
                        source="seed data",
                        status="new",
                    )
                )

            db.add(
                Owner(
                    property_id=row.id,
                    owner_name="Fictional Owner",
                    entity_type="individual",
                    occupancy_indicator="unknown",
                )
            )

            inputs = build_deal_inputs(analysis_spec, None, row)
            comparison, scoring, _ = run_analysis(inputs, include_ai=False, settings=settings)
            analysis = DealAnalysis(
                property_id=row.id, owner_id=user.id, name="Seed analysis"
            )
            apply_to_model(analysis, inputs, comparison, scoring, None)
            db.add(analysis)
            db.flush()
            record_assumption_changes(
                db, analysis, user, None, analysis.inputs_json, "Seeded analysis"
            )

            print(
                f"  {row.address:28} {scoring.verdict.value:24} "
                f"{analysis.recommended_strategy or '-'}"
            )

        db.commit()
    print(f"\nSeeded {len(DEMO_PROPERTIES)} demo properties.")


if __name__ == "__main__":
    seed()
