"""add columns to tournaments

Revision ID: 622985fd129c
Revises: 
Create Date: 
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "622985fd129c"
down_revision = "0a15252a2255"  # <-- eğer bundan önce migration varsa, onun revision'ını buraya yaz
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in cols


def upgrade():
    if not _has_column("tournaments", "is_active"):
        op.add_column(
            "tournaments",
            sa.Column("is_active", sa.Integer(), server_default="1", nullable=False),
        )

    if not _has_column("tournaments", "created_at"):
        op.add_column(
            "tournaments",
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=True,
            ),
        )
        op.execute(sa.text("UPDATE tournaments SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

    if not _has_column("tournaments", "branch_id"):
        op.add_column("tournaments", sa.Column("branch_id", sa.Integer(), nullable=True))

    if not _has_column("tournaments", "start_date"):
        op.add_column("tournaments", sa.Column("start_date", sa.Date(), nullable=True))

    if not _has_column("tournaments", "profile_id"):
        op.add_column("tournaments", sa.Column("profile_id", sa.Integer(), nullable=True))


def downgrade():
    if _has_column("tournaments", "profile_id"):
        op.drop_column("tournaments", "profile_id")
    if _has_column("tournaments", "start_date"):
        op.drop_column("tournaments", "start_date")
    if _has_column("tournaments", "branch_id"):
        op.drop_column("tournaments", "branch_id")
    if _has_column("tournaments", "created_at"):
        op.drop_column("tournaments", "created_at")
    if _has_column("tournaments", "is_active"):
        op.drop_column("tournaments", "is_active")