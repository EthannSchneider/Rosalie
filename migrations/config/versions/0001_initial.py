"""Schéma initial : réglages, personnalités, méta.

Les bases créées avant Alembic ont déjà ces tables : on ne crée que ce qui manque.

Révision : 0001
"""
from alembic import op
import sqlalchemy as sa

from libs.db.migrations import has_table

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not has_table("settings"):
        op.create_table("settings",
                        sa.Column("key", sa.Text(), primary_key=True),
                        sa.Column("value", sa.JSON(), nullable=False))
    if not has_table("personas"):
        op.create_table("personas",
                        sa.Column("name", sa.Text(), primary_key=True),
                        sa.Column("text", sa.Text(), nullable=False),
                        sa.Column("updated", sa.Float(), nullable=False))
    if not has_table("meta"):
        op.create_table("meta",
                        sa.Column("key", sa.Text(), primary_key=True),
                        sa.Column("value", sa.String(), nullable=False))


def downgrade() -> None:
    op.drop_table("meta")
    op.drop_table("personas")
    op.drop_table("settings")
