-- Investor profile.
--
-- Separate from the buy box in `default_assumptions` because the two describe
-- different things: the buy box describes how a DEAL is underwritten, this
-- describes the INVESTOR — capital available, return requirements, risk
-- tolerance. A deal can be excellent and still be one this investor cannot fund.
--
-- Idempotent, so it is safe to run against a database created from the current
-- 0001 (which already includes the column) or from an earlier copy that does not.

BEGIN;

ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS investor_profile JSONB;

COMMENT ON COLUMN user_profiles.investor_profile IS
    'Investor capital constraints and return requirements. NULL means unstated, '
    'which is not the same as zero.';

COMMIT;
