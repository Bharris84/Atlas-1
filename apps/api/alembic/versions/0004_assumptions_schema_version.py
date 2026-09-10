"""Add deal_analyses.assumptions_schema_version.

Records which generation of assumption semantics a stored analysis was written
under.

Operating expenses became tri-state in engine 0.3: a number is a known figure,
an explicit 0 means the expense does not apply, and NULL means nobody has found
out yet. Before that, taxes, insurance and HOA defaulted to 0, and that 0 was
how "unfilled" was represented.

Without this column, reading an old analysis back under the new rules turns
every one of them into a confident claim that the property has no tax bill —
not merely stale, but asserting something false at unchanged confidence.

**The server default of 0 is the entire mechanism.** Rows that already exist
when this runs were written under the old semantics, so they must come back as
version 0 and be read with the old meaning. Only rows the API writes afterwards
carry the current version. Changing this default to the current version would
silently reinterpret every historical analysis, which is precisely the failure
the column exists to prevent.

Revision ID: 0004_assumptions_schema_version
Revises: 0003_investor_profile
Create Date: 2026-09-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_assumptions_schema_version"
down_revision: Union[str, Sequence[str], None] = "0003_investor_profile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "deal_analyses",
        sa.Column(
            "assumptions_schema_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
            # Declared on the model too. Alembic's `check` compares comments,
            # so a comment that lives only here reads as permanent drift.
            comment=(
                "Generation of assumption semantics for assumptions_json. 0 = pre-tri-state, where a stored 0 for taxes/insurance/HOA meant unknown."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("deal_analyses", "assumptions_schema_version")
