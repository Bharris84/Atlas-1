-- Row-level security for Supabase.
--
-- The API already scopes every query by owner_id. This is the second lock:
-- if a query is ever written without that filter, or if someone connects to
-- the database directly with an end-user token, PostgreSQL still refuses to
-- return another account's rows.
--
-- Defence in depth is the point. Application-level authorization and
-- database-level authorization protect against different mistakes.

BEGIN;

-- --------------------------------------------------------------------------
-- Tables owned directly by a user
-- --------------------------------------------------------------------------

ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY user_profiles_self ON user_profiles
    USING (id = auth.uid())
    WITH CHECK (id = auth.uid());

ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
CREATE POLICY properties_owner ON properties
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
CREATE POLICY leads_owner ON leads
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE deal_analyses ENABLE ROW LEVEL SECURITY;
CREATE POLICY deal_analyses_owner ON deal_analyses
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE offers ENABLE ROW LEVEL SECURITY;
CREATE POLICY offers_owner ON offers
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE communications ENABLE ROW LEVEL SECURITY;
CREATE POLICY communications_owner ON communications
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE rehab_projects ENABLE ROW LEVEL SECURITY;
CREATE POLICY rehab_projects_owner ON rehab_projects
    USING (owner_id = auth.uid())
    WITH CHECK (owner_id = auth.uid());

ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY activity_log_actor ON activity_log
    USING (actor_id = auth.uid())
    WITH CHECK (actor_id = auth.uid());

-- --------------------------------------------------------------------------
-- Tables that inherit ownership through their property
-- --------------------------------------------------------------------------

ALTER TABLE owners ENABLE ROW LEVEL SECURITY;
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

CREATE POLICY assumption_audit_read ON assumption_audit
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM deal_analyses a
            WHERE a.id = assumption_audit.analysis_id AND a.owner_id = auth.uid()
        )
    );

CREATE POLICY assumption_audit_insert ON assumption_audit
    FOR INSERT
    WITH CHECK (
        changed_by = auth.uid()
        AND EXISTS (
            SELECT 1 FROM deal_analyses a
            WHERE a.id = assumption_audit.analysis_id AND a.owner_id = auth.uid()
        )
    );

COMMIT;
