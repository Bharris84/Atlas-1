"""Authentication and authorization.

The property under test that matters most: one account cannot reach another
account's pipeline, ever.
"""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
import pytest
from fastapi import HTTPException

from atlas_api.auth import (
    AuthConfigurationError,
    CurrentUser,
    get_current_user,
    verify_startup_configuration,
)
from atlas_api.config import Settings
from atlas_api.main import app

SECRET = "test-jwt-secret-value"


def _settings(**overrides) -> Settings:
    base = {
        "supabase_jwt_secret": SECRET,
        "environment": "test",
        "atlas_database_url": "sqlite:///./ignored.db",
    }
    base.update(overrides)
    return Settings(**base)


def _token(secret: str = SECRET, **claims) -> str:
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "investor@example.com",
        "aud": "authenticated",
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1),
    }
    payload.update(claims)
    return jwt.encode(payload, secret, algorithm="HS256")


class _Credentials:
    def __init__(self, token: str) -> None:
        self.credentials = token
        self.scheme = "Bearer"


class TestStartupGuard:
    def test_production_without_a_jwt_secret_refuses_to_start(self):
        """An open production API would expose every user's pipeline."""
        with pytest.raises(AuthConfigurationError):
            verify_startup_configuration(
                _settings(environment="production", supabase_jwt_secret=None)
            )

    def test_production_with_a_jwt_secret_starts(self):
        verify_startup_configuration(_settings(environment="production"))

    def test_development_without_a_secret_is_allowed(self):
        verify_startup_configuration(
            _settings(environment="development", supabase_jwt_secret=None)
        )


class TestTokenVerification:
    def test_valid_token_is_accepted(self):
        user_id = str(uuid.uuid4())
        user = get_current_user(
            request=None,
            credentials=_Credentials(_token(sub=user_id)),
            settings=_settings(),
        )
        assert str(user.id) == user_id
        assert user.email == "investor@example.com"
        assert user.is_development_identity is False

    def test_missing_token_is_rejected_when_auth_is_configured(self):
        with pytest.raises(HTTPException) as exc:
            get_current_user(request=None, credentials=None, settings=_settings())
        assert exc.value.status_code == 401

    def test_token_signed_with_the_wrong_secret_is_rejected(self):
        with pytest.raises(HTTPException) as exc:
            get_current_user(
                request=None,
                credentials=_Credentials(_token(secret="a-different-secret")),
                settings=_settings(),
            )
        assert exc.value.status_code == 401

    def test_expired_token_is_rejected(self):
        expired = _token(exp=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1))
        with pytest.raises(HTTPException) as exc:
            get_current_user(
                request=None, credentials=_Credentials(expired), settings=_settings()
            )
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    def test_token_for_the_wrong_audience_is_rejected(self):
        with pytest.raises(HTTPException) as exc:
            get_current_user(
                request=None,
                credentials=_Credentials(_token(aud="some-other-service")),
                settings=_settings(),
            )
        assert exc.value.status_code == 401

    def test_non_uuid_subject_is_rejected(self):
        with pytest.raises(HTTPException) as exc:
            get_current_user(
                request=None,
                credentials=_Credentials(_token(sub="not-a-uuid")),
                settings=_settings(),
            )
        assert exc.value.status_code == 401

    def test_rejection_does_not_explain_why_the_token_failed(self):
        """Telling a caller exactly what was wrong helps them forge a better one."""
        with pytest.raises(HTTPException) as exc:
            get_current_user(
                request=None,
                credentials=_Credentials(_token(secret="wrong")),
                settings=_settings(),
            )
        assert exc.value.detail == "Invalid authentication token."

    def test_development_mode_returns_the_local_identity(self):
        user = get_current_user(
            request=None, credentials=None, settings=_settings(supabase_jwt_secret=None)
        )
        assert user.is_development_identity is True


class TestOwnershipIsolation:
    """Two accounts, one database. Neither may see the other's records."""

    @pytest.fixture
    def as_user(self, client):
        def _set(user_id: uuid.UUID, email: str = "user@example.com"):
            app.dependency_overrides[get_current_user] = lambda: CurrentUser(
                id=user_id, email=email
            )
            return client

        yield _set
        app.dependency_overrides.pop(get_current_user, None)

    def test_a_property_is_invisible_to_another_account(self, as_user, property_payload):
        alice, bob = uuid.uuid4(), uuid.uuid4()

        created = as_user(alice).post("/api/properties", json=property_payload).json()
        assert as_user(alice).get(f"/api/properties/{created['id']}").status_code == 200

        # Bob gets 404, not 403: the API does not confirm the id exists.
        assert as_user(bob).get(f"/api/properties/{created['id']}").status_code == 404
        assert as_user(bob).get("/api/properties").json() == []

    def test_another_account_cannot_modify_or_delete(self, as_user, property_payload):
        alice, bob = uuid.uuid4(), uuid.uuid4()
        created = as_user(alice).post("/api/properties", json=property_payload).json()

        assert (
            as_user(bob)
            .patch(f"/api/properties/{created['id']}", json={"city": "Somewhere Else"})
            .status_code
            == 404
        )
        assert as_user(bob).delete(f"/api/properties/{created['id']}").status_code == 404
        assert as_user(alice).get(f"/api/properties/{created['id']}").status_code == 200

    def test_another_account_cannot_read_a_saved_analysis(
        self, as_user, property_payload, analysis_payload
    ):
        alice, bob = uuid.uuid4(), uuid.uuid4()
        prop = as_user(alice).post("/api/properties", json=property_payload).json()
        analysis = (
            as_user(alice)
            .post(f"/api/properties/{prop['id']}/analyses", json=analysis_payload)
            .json()
        )
        assert as_user(bob).get(f"/api/analyses/{analysis['id']}").status_code == 404
        assert as_user(bob).get(f"/api/analyses/{analysis['id']}/audit").status_code == 404

    def test_another_account_cannot_attach_records_to_the_property(
        self, as_user, property_payload
    ):
        alice, bob = uuid.uuid4(), uuid.uuid4()
        prop = as_user(alice).post("/api/properties", json=property_payload).json()
        response = as_user(bob).post(
            f"/api/properties/{prop['id']}/comps", json={"address": "somewhere"}
        )
        assert response.status_code == 404

    def test_settings_are_per_account(self, as_user):
        alice, bob = uuid.uuid4(), uuid.uuid4()
        as_user(alice).put(
            "/api/settings",
            json={"default_assumptions": {"flip": {"minimum_net_profit": "75000"}}},
        )
        bob_settings = as_user(bob).get("/api/settings").json()
        assert bob_settings["default_assumptions"]["flip"]["minimum_net_profit"] == "30000"

    def test_dashboards_do_not_bleed_between_accounts(self, as_user, property_payload):
        alice, bob = uuid.uuid4(), uuid.uuid4()
        as_user(alice).post("/api/properties", json=property_payload)
        assert as_user(bob).get("/api/dashboard").json()["property_count"] == 0
        assert as_user(alice).get("/api/dashboard").json()["property_count"] == 1
