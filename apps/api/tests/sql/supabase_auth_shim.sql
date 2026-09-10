-- TEST FIXTURE ONLY — NOT PART OF THE PRODUCTION SCHEMA.
--
-- Atlas's RLS policies (database/migrations/0002_row_level_security.sql) call
-- auth.uid(), which is provided by Supabase, not by PostgreSQL. On vanilla
-- PostgreSQL applying 0002 fails with: schema "auth" does not exist.
--
-- This file recreates auth.uid() using the same mechanism Supabase documents:
-- the current user id is read from the `request.jwt.claims` setting, which
-- Supabase populates per-connection from the verified JWT.
--
-- What this proves and does not prove:
--
--   PROVES    the policy SQL is syntactically valid, the policies attach to
--             the right tables, and the USING/WITH CHECK predicates actually
--             isolate rows by owner.
--
--   DOES NOT  validate Supabase's own auth semantics — that a JWT is verified
--   PROVE     correctly, that the claim is populated on the right connection,
--             or that Supabase's role grants match ours. Those are Supabase's
--             behaviour and can only be confirmed against a real project.
--
-- Deliberately kept out of database/migrations so it can never be applied to
-- a production database.

CREATE SCHEMA IF NOT EXISTS auth;

CREATE OR REPLACE FUNCTION auth.uid()
RETURNS uuid
LANGUAGE sql
STABLE
AS $$
    -- An unset or empty claim is an anonymous connection, not an error:
    -- auth.uid() returns NULL and every policy predicate then fails closed.
    SELECT NULLIF(
        NULLIF(current_setting('request.jwt.claims', true), '')::json ->> 'sub',
        ''
    )::uuid;
$$;
