"""Row-level security validation against a real PostgreSQL server.

Revision `0002_row_level_security` calls `auth.uid()`, which Supabase provides
and vanilla PostgreSQL does not. The revision therefore skips itself where that
function is absent, which is every developer machine. These tests install
`tests/sql/supabase_auth_shim.sql` first — a test fixture recreating
`auth.uid()` from `request.jwt.claims`, the mechanism Supabase documents — so
the revision runs for real, and then exercise the policies it created.

Read that file before trusting these results. In short:

    PROVES     the policy SQL is valid, attaches to the right tables, and its
               USING / WITH CHECK predicates isolate rows by owner.

    DOES NOT   validate Supabase's own auth: JWT verification, how the claim
    PROVE      reaches the connection, or Supabase's role grants.

Skipped automatically unless ATLAS_TEST_POSTGRES_URL points at a server:

    ATLAS_TEST_POSTGRES_URL=postgresql://atlas:atlas@127.0.0.1:5432/postgres \
        pytest tests/test_rls.py
"""

from __future__ import annotations

import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from pg_support import (  # noqa: E402
    POSTGRES_URL,
    alembic_config,
    install_auth_shim,
    server_reachable,
    throwaway_database,
)

pytestmark = pytest.mark.skipif(
    not POSTGRES_URL, reason="ATLAS_TEST_POSTGRES_URL is not set"
)

USER_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_B = uuid.UUID("22222222-2222-2222-2222-222222222222")

# Every table 0002 protects, and the role that end users connect as under
# Supabase. Neither owns the tables, which is what makes the policies bite.
END_USER_ROLE = "atlas_rls_enduser"


def _as_user(conn, user_id: uuid.UUID) -> None:
    """Become an end user: assume the non-owning role and set the JWT claim.

    Both halves matter. Without SET ROLE the connection is still the table
    owner, and PostgreSQL exempts a table's owner from its own policies —
    see test_the_table_owner_bypasses_rls_entirely.
    """
    conn.execute(f"SET ROLE {END_USER_ROLE}")
    conn.execute(
        "SELECT set_config('request.jwt.claims', %s, false)",
        (f'{{"sub": "{user_id}"}}',),
    )


def _as_owner(conn) -> None:
    conn.execute("RESET ROLE")
    conn.execute("SELECT set_config('request.jwt.claims', '', false)")


@pytest.fixture(scope="module")
def rls_db():
    """A database with the full schema, the auth shim, and RLS enabled.

    The shim goes in BEFORE the migrations run. Revision 0002 checks for
    auth.uid() and skips when it is absent, so installing the shim afterwards
    would produce a database with no policies and no error — which is exactly
    the silent gap these tests exist to rule out.
    """
    if not server_reachable():
        pytest.skip("PostgreSQL is not reachable")
    from alembic import command

    with throwaway_database("atlas_rls") as url:
        install_auth_shim(url)
        command.upgrade(alembic_config(url), "head")

        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(
                f"""
                DO $$ BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_roles WHERE rolname = '{END_USER_ROLE}'
                    ) THEN
                        CREATE ROLE {END_USER_ROLE} NOLOGIN;
                    END IF;
                END $$
                """
            )
            conn.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA"
                f" public TO {END_USER_ROLE}"
            )
            conn.execute(f"GRANT USAGE ON SCHEMA public, auth TO {END_USER_ROLE}")
            # So the test connection can SET ROLE into it.
            conn.execute(f"GRANT {END_USER_ROLE} TO CURRENT_USER")
        yield url

    # Outside the with-block on purpose: the database is dropped when it exits,
    # and the role cannot be dropped while grants inside that database still
    # depend on it.
    with psycopg.connect(POSTGRES_URL, autocommit=True) as admin:
        admin.execute(f"DROP ROLE IF EXISTS {END_USER_ROLE}")


@pytest.fixture
def conn(rls_db):
    with psycopg.connect(rls_db, autocommit=True) as connection:
        yield connection


def _seed_property(conn, owner_id: uuid.UUID, address: str) -> uuid.UUID:
    """Insert as the table owner, so the fixture is not itself under test."""
    _as_owner(conn)
    pid = uuid.uuid4()
    conn.execute(
        "INSERT INTO properties (id, owner_id, address, property_status,"
        " created_at, updated_at) VALUES (%s,%s,%s,'prospect',now(),now())",
        (pid, owner_id, address),
    )
    return pid


class TestThePoliciesInstall:
    def test_without_supabase_the_upgrade_succeeds_and_applies_no_policies(self):
        """The honest version of "RLS is implemented": it is implemented for
        Supabase specifically.

        Revision 0002 must not abort an upgrade on a database that has no
        auth.uid() — every developer machine is one — but it must not pretend
        to have protected it either. So: upgrade reaches head, and zero
        policies exist.
        """
        if not server_reachable():
            pytest.skip("PostgreSQL is not reachable")
        from alembic import command

        with throwaway_database("atlas_noshim") as url:
            command.upgrade(alembic_config(url), "head")
            with psycopg.connect(url) as conn:
                version = conn.execute(
                    "SELECT version_num FROM alembic_version"
                ).fetchone()[0]
                policies = conn.execute(
                    "SELECT count(*) FROM pg_policies WHERE schemaname='public'"
                ).fetchone()[0]
        assert version == "0004_assumptions_schema_version"
        assert policies == 0, "policies applied without auth.uid() — how?"

    def test_every_protected_table_has_rls_enabled(self, conn):
        enabled = {
            row[0]
            for row in conn.execute(
                "SELECT relname FROM pg_class c JOIN pg_namespace n"
                " ON n.oid = c.relnamespace"
                " WHERE n.nspname='public' AND c.relrowsecurity"
            ).fetchall()
        }
        assert enabled == {
            "user_profiles", "properties", "leads", "deal_analyses", "offers",
            "communications", "rehab_projects", "activity_log", "owners",
            "comps", "data_sources", "assumption_audit",
        }

    def test_all_thirteen_policies_are_present(self, conn):
        policies = {
            row[0]
            for row in conn.execute(
                "SELECT policyname FROM pg_policies WHERE schemaname='public'"
            ).fetchall()
        }
        assert policies == {
            "user_profiles_self", "properties_owner", "leads_owner",
            "deal_analyses_owner", "offers_owner", "communications_owner",
            "rehab_projects_owner", "activity_log_actor", "owners_via_property",
            "comps_via_property", "data_sources_via_property",
            "assumption_audit_read", "assumption_audit_insert",
        }


class TestOwnershipIsolation:
    def test_a_user_sees_only_their_own_properties(self, conn):
        _seed_property(conn, USER_A, "10 A Street")
        _seed_property(conn, USER_B, "10 B Street")

        _as_user(conn, USER_A)
        visible = conn.execute("SELECT address FROM properties").fetchall()
        assert [r[0] for r in visible] == ["10 A Street"]

        _as_user(conn, USER_B)
        visible = conn.execute("SELECT address FROM properties").fetchall()
        assert [r[0] for r in visible] == ["10 B Street"]

    def test_a_user_cannot_read_another_users_row_by_id(self, conn):
        """Knowing the primary key is not access. Guessing an id, or receiving
        one from a shared link, must not defeat the policy."""
        pid = _seed_property(conn, USER_A, "11 A Street")
        _as_user(conn, USER_B)
        found = conn.execute(
            "SELECT count(*) FROM properties WHERE id = %s", (pid,)
        ).fetchone()[0]
        assert found == 0

    def test_a_user_cannot_update_another_users_row(self, conn):
        pid = _seed_property(conn, USER_A, "12 A Street")
        _as_user(conn, USER_B)
        result = conn.execute(
            "UPDATE properties SET address = 'stolen' WHERE id = %s", (pid,)
        )
        assert result.rowcount == 0

        _as_owner(conn)
        address = conn.execute(
            "SELECT address FROM properties WHERE id = %s", (pid,)
        ).fetchone()[0]
        assert address == "12 A Street"

    def test_a_user_cannot_delete_another_users_row(self, conn):
        pid = _seed_property(conn, USER_A, "13 A Street")
        _as_user(conn, USER_B)
        result = conn.execute("DELETE FROM properties WHERE id = %s", (pid,))
        assert result.rowcount == 0

    def test_a_user_cannot_insert_a_row_owned_by_someone_else(self, conn):
        """WITH CHECK, not just USING. Without it a user could write rows into
        another account even while unable to read them back."""
        _as_user(conn, USER_B)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO properties (id, owner_id, address, property_status,"
                " created_at, updated_at) VALUES (%s,%s,'14 A Street','prospect',"
                "now(),now())",
                (uuid.uuid4(), USER_A),
            )

    def test_a_user_cannot_hand_their_row_to_another_account(self, conn):
        """The row is theirs to edit, but not theirs to reassign."""
        pid = _seed_property(conn, USER_A, "15 A Street")
        _as_user(conn, USER_A)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "UPDATE properties SET owner_id = %s WHERE id = %s", (USER_B, pid)
            )


class TestInheritedOwnership:
    def test_child_rows_follow_the_property(self, conn):
        """`comps` has no owner_id of its own; it inherits through property_id.
        A join-based policy is easy to get subtly wrong, so it is tested
        directly rather than assumed to work like the owner_id ones."""
        pid_a = _seed_property(conn, USER_A, "20 A Street")
        pid_b = _seed_property(conn, USER_B, "20 B Street")
        _as_owner(conn)
        for pid, address in ((pid_a, "comp for A"), (pid_b, "comp for B")):
            conn.execute(
                "INSERT INTO comps (id, property_id, address, created_at,"
                " updated_at) VALUES (%s,%s,%s,now(),now())",
                (uuid.uuid4(), pid, address),
            )

        _as_user(conn, USER_A)
        visible = [r[0] for r in conn.execute("SELECT address FROM comps").fetchall()]
        assert visible == ["comp for A"]

    def test_a_user_cannot_attach_a_child_to_another_users_property(self, conn):
        pid_a = _seed_property(conn, USER_A, "21 A Street")
        _as_user(conn, USER_B)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO comps (id, property_id, address, created_at,"
                " updated_at) VALUES (%s,%s,'smuggled',now(),now())",
                (uuid.uuid4(), pid_a),
            )

    def test_unattached_data_sources_stay_readable(self, conn):
        """data_sources allows property_id IS NULL for market-wide records.
        That branch of the policy is deliberate, so it is pinned here: it is
        the one place a row is visible to everyone."""
        _as_owner(conn)
        conn.execute(
            "INSERT INTO data_sources (id, provider, field_name, retrieved_at)"
            " VALUES (%s,'rentcast','market_rent',now())",
            (uuid.uuid4(),),
        )
        _as_user(conn, USER_B)
        count = conn.execute(
            "SELECT count(*) FROM data_sources WHERE field_name='market_rent'"
        ).fetchone()[0]
        assert count == 1


class TestAuditTrailImmutability:
    """An audit trail that its subject can edit is not an audit trail.

    `assumption_audit` grants SELECT and INSERT only. There is no UPDATE or
    DELETE policy, and a table with RLS enabled denies anything no policy
    permits — so the absence of a policy is the enforcement mechanism.
    """

    def _seed_audit_row(self, conn, owner_id: uuid.UUID) -> uuid.UUID:
        _as_owner(conn)
        pid = _seed_property(conn, owner_id, f"audit {uuid.uuid4().hex[:6]}")
        analysis_id, entry_id = uuid.uuid4(), uuid.uuid4()
        conn.execute(
            "INSERT INTO deal_analyses (id, property_id, owner_id,"
            " requires_human_review, created_at, updated_at)"
            " VALUES (%s,%s,%s,false,now(),now())",
            (analysis_id, pid, owner_id),
        )
        conn.execute(
            "INSERT INTO assumption_audit (id, analysis_id, field_path,"
            " previous_value, new_value, changed_by, changed_at) VALUES"
            " (%s,%s,'flip.holding_months','6','9',%s,now())",
            (entry_id, analysis_id, owner_id),
        )
        return entry_id

    def test_the_owner_can_read_their_audit_trail(self, conn):
        entry_id = self._seed_audit_row(conn, USER_A)
        _as_user(conn, USER_A)
        found = conn.execute(
            "SELECT count(*) FROM assumption_audit WHERE id = %s", (entry_id,)
        ).fetchone()[0]
        assert found == 1

    def test_nobody_can_rewrite_an_audit_entry(self, conn):
        entry_id = self._seed_audit_row(conn, USER_A)
        _as_user(conn, USER_A)
        result = conn.execute(
            "UPDATE assumption_audit SET new_value = '999' WHERE id = %s",
            (entry_id,),
        )
        assert result.rowcount == 0

    def test_nobody_can_delete_an_audit_entry(self, conn):
        entry_id = self._seed_audit_row(conn, USER_A)
        _as_user(conn, USER_A)
        result = conn.execute(
            "DELETE FROM assumption_audit WHERE id = %s", (entry_id,)
        )
        assert result.rowcount == 0

    def test_an_entry_cannot_be_attributed_to_someone_else(self, conn):
        """changed_by = auth.uid() in the WITH CHECK. Forging authorship would
        make the trail worse than useless."""
        _as_owner(conn)
        pid = _seed_property(conn, USER_A, "30 A Street")
        analysis_id = uuid.uuid4()
        conn.execute(
            "INSERT INTO deal_analyses (id, property_id, owner_id,"
            " requires_human_review, created_at, updated_at)"
            " VALUES (%s,%s,%s,false,now(),now())",
            (analysis_id, pid, USER_A),
        )
        _as_user(conn, USER_A)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "INSERT INTO assumption_audit (id, analysis_id, field_path,"
                " previous_value, new_value, changed_by, changed_at)"
                " VALUES (%s,%s,'flip.holding_months','6','9',%s,now())",
                (uuid.uuid4(), analysis_id, USER_B),
            )


class TestKnownLimitations:
    """Findings recorded as tests so they cannot quietly stop being true."""

    def test_the_table_owner_bypasses_rls_entirely(self, conn):
        """PostgreSQL exempts a table's owner from its own policies unless the
        table is set to FORCE ROW LEVEL SECURITY. Atlas does not set it.

        This is correct for the deployment Atlas targets and wrong for another:

          - Under Supabase, end users arrive through PostgREST as the
            `authenticated` role, which does not own the tables. The policies
            apply. The API's own service connection is *supposed* to see
            everything; it scopes by owner_id in application code.

          - Point Atlas's API at a plain PostgreSQL database using the role
            that created the tables, and RLS contributes nothing at all. The
            application-level owner_id filter is the only protection.

        Recorded here so the limitation is visible rather than assumed away.
        Adding FORCE would break the API's own connection, which never sets
        request.jwt.claims, so it is a deployment decision, not a one-line fix.
        """
        pid = _seed_property(conn, USER_A, "40 A Street")

        # As the table owner, while claiming to be a *different* user.
        _as_owner(conn)
        conn.execute(
            "SELECT set_config('request.jwt.claims', %s, false)",
            (f'{{"sub": "{USER_B}"}}',),
        )
        found = conn.execute(
            "SELECT count(*) FROM properties WHERE id = %s", (pid,)
        ).fetchone()[0]
        assert found == 1, "owner bypass no longer applies — re-read this test"

        forced = conn.execute(
            "SELECT relforcerowsecurity FROM pg_class c JOIN pg_namespace n"
            " ON n.oid = c.relnamespace"
            " WHERE n.nspname='public' AND c.relname='properties'"
        ).fetchone()[0]
        assert forced is False

    def test_an_absent_claim_shows_nothing_rather_than_everything(self, conn):
        """A connection with no JWT claim makes auth.uid() NULL, and every
        predicate compares against NULL. Failing closed is the behaviour we
        want; failing open would be the dangerous one."""
        _seed_property(conn, USER_A, "41 A Street")
        conn.execute(f"SET ROLE {END_USER_ROLE}")
        conn.execute("SELECT set_config('request.jwt.claims', '', false)")
        count = conn.execute("SELECT count(*) FROM properties").fetchone()[0]
        assert count == 0
