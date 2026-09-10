"""Add user_profiles.investor_profile.

The investor's stated capital position and buy-box constraints, saved as
defaults for new analyses. Introduced in the calibration phase (commit
77507e2).

Under the hand-applied scheme this migration never did anything: the same
commit that added it also regenerated ``0001_initial_schema.sql`` from the
models, so the column was already in the file every fresh database was built
from, and ``ADD COLUMN IF NOT EXISTS`` found nothing to do. It was a no-op that
looked like a migration for months.

Here it is a real step. Revision 0001 does not create the column, so this one
adds it — on a fresh database and on one that stopped at 0001 alike.

Revision ID: 0003_investor_profile
Revises: 0002_row_level_security
Create Date: 2026-09-10
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_investor_profile"
down_revision: Union[str, Sequence[str], None] = "0002_row_level_security"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable with no default: an unstated investor profile is unknown, and
    # Atlas reports it as unknown rather than substituting an illustration.
    op.add_column(
        "user_profiles", sa.Column("investor_profile", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "investor_profile")
