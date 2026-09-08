"""API test fixtures.

Each test gets its own SQLite database file, so tests are isolated and can run
in any order.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from typing import Iterator

import pytest

# Configure the environment before the app module reads it.
_tmpdir = tempfile.mkdtemp(prefix="atlas-test-")
os.environ.setdefault("ATLAS_DATABASE_URL", f"sqlite:///{_tmpdir}/atlas-test.db")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("ATLAS_AI_PROVIDER", "null")
os.environ.pop("SUPABASE_JWT_SECRET", None)
os.environ.pop("RENTCAST_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

from atlas_api.db import SessionLocal, engine  # noqa: E402
from atlas_api.main import app  # noqa: E402
from atlas_api.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database() -> Iterator[None]:
    Base.metadata.create_all(bind=engine)
    yield
    with SessionLocal() as session:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def property_payload() -> dict:
    return {
        "address": "412 Magnolia Street",
        "city": "Chattanooga",
        "state": "TN",
        "zip_code": "37402",
        "property_type": "single_family",
        "bedrooms": "3",
        "bathrooms": "2",
        "square_feet": "1450",
        "year_built": 1998,
    }


@pytest.fixture
def created_property(client, property_payload) -> dict:
    response = client.post("/api/properties", json=property_payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def analysis_payload() -> dict:
    return {
        "purchase_price": "150000",
        "arv": "250000",
        "rehab": "45000",
        "monthly_rent": "1800",
        "evidence": {
            "arv_basis": "comparable_sales",
            "comp_count": 5,
            "average_comp_similarity": "0.85",
            "average_comp_age_days": 90,
            "rehab_basis": "contractor_bid",
            "rent_basis": "rental_comps",
            "property_visited": True,
            "title_reviewed": True,
            "inspection_completed": True,
        },
        "assumptions": {
            "rental": {"annual_taxes": "2400", "annual_insurance": "1800"},
            "holding": {"annual_taxes": "2400", "annual_insurance": "1800"},
        },
    }
