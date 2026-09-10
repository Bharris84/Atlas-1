-- Record which generation of assumption semantics a stored analysis was
-- written under.
--
-- Operating expenses became tri-state in engine version 0.3: a number is a
-- known figure, an explicit 0 means the expense does not apply, and NULL means
-- nobody has found out yet. Before that, taxes, insurance and HOA defaulted to
-- 0, and that 0 was how "unfilled" was represented.
--
-- Without this column, reading an old analysis back turns every one of them
-- into a confident claim that the property has no tax bill. The analysis would
-- not merely be stale — it would assert something false, with the same
-- confidence label it always had.
--
-- So: existing rows get 0 and are read back with the old meaning (a stored 0
-- for taxes or insurance becomes UNKNOWN, and holding utilities keep the $150
-- they were actually computed with, so the saved figures still reproduce).
-- New rows are written with the current version by the API.
--
-- The version also travels inside assumptions_json. It is duplicated here so
-- legacy analyses can be found with a WHERE clause rather than a JSON scan.

BEGIN;

ALTER TABLE deal_analyses
    ADD COLUMN IF NOT EXISTS assumptions_schema_version INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN deal_analyses.assumptions_schema_version IS
    'Generation of assumption semantics for assumptions_json. '
    '0 = pre-tri-state, where a stored 0 for taxes/insurance/HOA meant unknown.';

COMMIT;
