"""Row-level security policies (Supabase only).

The API already scopes every query by owner_id. These policies are the second
lock: if a query is ever written without that filter, or someone connects with
an end-user token, PostgreSQL still refuses to return another account's rows.

**This revision is conditional, and that is not a shortcut.** The policies call
``auth.uid()``, which Supabase provides and PostgreSQL does not. Running them
unconditionally would abort ``alembic upgrade head`` with `schema "auth" does
not exist` on every plain-PostgreSQL and SQLite database — which is every
development machine and the whole test suite. A migration runner that cannot
reach head on a developer's laptop does not get used, and an unused runner is
the problem this whole change exists to fix.

So the revision applies the policies where ``auth.uid()`` exists and records a
loud skip where it does not. The skip is a real gap, not a formality: **Atlas
pointed at a database without auth.uid() has no row-level security at all**,
only the application's own owner_id filter. That is documented in
docs/database-validation.md and pinned by tests in apps/api/tests/test_rls.py.

Revision ID: 0002_row_level_security
Revises: 0001_initial_schema
Create Date: 2026-09-10
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_row_level_security"
down_revision: Union[str, Sequence[str], None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

PROTECTED_TABLES = (
    "user_profiles",
    "properties",
    "leads",
    "deal_analyses",
    "offers",
    "communications",
    "rehab_projects",
    "activity_log",
    "owners",
    "comps",
    "data_sources",
    "assumption_audit",
)

POLICIES = (
    "user_profiles_self",
    "properties_owner",
    "leads_owner",
    "deal_analyses_owner",
    "offers_owner",
    "communications_owner",
    "rehab_projects_owner",
    "activity_log_actor",
    "owners_via_property",
    "comps_via_property",
    "data_sources_via_property",
    "assumption_audit_read",
    "assumption_audit_insert",
)

RLS_SQL = """\

-- --------------------------------------------------------------------------
-- Tables owned directly by a user
-- --------------------------------------------------------------------------

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_profiles_self ON user_profiles;
CREATE POLICY user_profiles_self ON user_profiles
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());

ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS properties_owner ON properties;
CREATE POLICY properties_owner ON properties
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS leads_owner ON leads;
CREATE POLICY leads_owner ON leads
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE deal_analyses ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS deal_analyses_owner ON deal_analyses;
CREATE POLICY deal_analyses_owner ON deal_analyses
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE offers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS offers_owner ON offers;
CREATE POLICY offers_owner ON offers
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE communications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS communications_owner ON communications;
CREATE POLICY communications_owner ON communications
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE rehab_projects ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS rehab_projects_owner ON rehab_projects;
CREATE POLICY rehab_projects_owner ON rehab_projects
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS activity_log_actor ON activity_log;
CREATE POLICY activity_log_actor ON activity_log
    USING (actor_id = auth.uid())
    WITH CHECK (actor_id = auth.uid());

-- --------------------------------------------------------------------------
-- Tables that inherit ownership through their property
-- --------------------------------------------------------------------------

ALTER TABLE owners ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS owners_via_property ON owners;
CREATE POLICY owners_via_property ON owners
    USING (
        EXISTS (
            SELECT 1 FROM properties p
            WHERE p.id = owners.property_id AND p.owner_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM properties p
            WHERE p.id = owners.property_id AND p.owner_id = auth.uid()
        )
    );

ALTER TABLE comps ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS comps_via_property ON comps;
CREATE POLICY comps_via_property ON comps
    USING (
        EXISTS (
            SELECT 1 FROM properties p
            WHERE p.id = comps.property_id AND p.owner_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM properties p
            WHERE p.id = comps.property_id AND p.owner_id = auth.uid()
        )
    );

ALTER TABLE data_sources ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS data_sources_via_property ON data_sources;
CREATE POLICY data_sources_via_property ON data_sources
    USING (
        property_id IS NULL
        OR EXISTS (
            SELECT 1 FROM properties p
            WHERE p.id = data_sources.property_id AND p.owner_id = auth.uid()
        )
    )
    WITH CHECK (
        property_id IS NULL
        OR EXISTS (
            SELECT 1 FROM properties p
            WHERE p.id = data_sources.property_id AND p.owner_id = auth.uid()
        )
    );

-- --------------------------------------------------------------------------
-- Audit trail
-- --------------------------------------------------------------------------
--
-- Readable by the owner of the analysis, insertable by them, and deliberately
-- NOT updatable or deletable by anyone. An audit trail that can be edited is
-- not an audit trail.

ALTER TABLE assumption_audit ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS assumption_audit_read ON assumption_audit;
CREATE POLICY assumption_audit_read ON assumption_audit
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM deal_analyses a
            WHERE a.id = assumption_audit.analysis_id AND a.owner_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS assumption_audit_insert ON assumption_audit;
CREATE POLICY assumption_audit_insert ON assumption_audit
    FOR INSERT
    WITH CHECK (
        changed_by = auth.uid()
        AND EXISTS (
            SELECT 1 FROM deal_analyses a
            WHERE a.id = assumption_audit.analysis_id AND a.owner_id = auth.uid()
        )
    );

"""


def _supabase_auth_available(connection) -> bool:
    """True when auth.uid() exists and is callable.

    Checking for the function rather than for "am I on Supabase" keeps the test
    honest: the test suite installs a shim that provides auth.uid() on vanilla
    PostgreSQL, and these policies should apply there too.
    """
    if connection.dialect.name != "postgresql":
        return False
    return bool(
        connection.execute(
            sa.text(
                "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
                " WHERE n.nspname = 'auth' AND p.proname = 'uid'"
            )
        ).scalar()
    )


def upgrade() -> None:
    connection = op.get_bind()
    if not _supabase_auth_available(connection):
        logger.warning(
            "SKIPPING row-level security: auth.uid() is not available on this "
            "database (dialect=%s). The policies in this revision are "
            "Supabase-specific. This database has NO row-level security; the "
            "application's owner_id filter is the only protection.",
            connection.dialect.name,
        )
        return
    op.execute(RLS_SQL)
    logger.info("row-level security applied: %d policies", len(POLICIES))


def downgrade() -> None:
    connection = op.get_bind()
    if not _supabase_auth_available(connection):
        return
    # Policies first, then the table flag: dropping in the other order leaves a
    # table with RLS disabled but policies still attached, which reads as
    # protected in pg_policies and protects nothing.
    for policy, table in zip(POLICIES, _POLICY_TABLES):
        op.execute(f'DROP POLICY IF EXISTS {policy} ON {table}')
    for table in PROTECTED_TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


# Each policy's table, positionally matched to POLICIES above.
_POLICY_TABLES = (
    "user_profiles",
    "properties",
    "leads",
    "deal_analyses",
    "offers",
    "communications",
    "rehab_projects",
    "activity_log",
    "owners",
    "comps",
    "data_sources",
    "assumption_audit",
    "assumption_audit",
)
