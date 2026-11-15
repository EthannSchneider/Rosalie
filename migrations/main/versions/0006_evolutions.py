"""Évolution du code : historique des opérations (demande, pull request, mise à jour).

Révision : 0006
Précédente : 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("evolutions",
                    sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("title", sa.Text(), nullable=False),
                    sa.Column("reason", sa.Text(), nullable=False),
                    sa.Column("brief", sa.JSON(), nullable=False),
                    sa.Column("author", sa.Text(), nullable=False),
                    sa.Column("conversation", sa.Text()),
                    sa.Column("status", sa.Text(), nullable=False),
                    sa.Column("detail", sa.Text(), nullable=False),
                    sa.Column("branch", sa.Text(), nullable=False),
                    sa.Column("pr_number", sa.Integer()),
                    sa.Column("pr_url", sa.Text(), nullable=False),
                    sa.Column("base_sha", sa.Text(), nullable=False),
                    sa.Column("head_sha", sa.Text(), nullable=False),
                    sa.Column("merged_sha", sa.Text(), nullable=False),
                    sa.Column("previous_sha", sa.Text(), nullable=False),
                    sa.Column("deployed_sha", sa.Text(), nullable=False),
                    sa.Column("checks", sa.JSON(), nullable=False),
                    sa.Column("checks_ok", sa.Boolean()),
                    sa.Column("summary", sa.Text(), nullable=False),
                    sa.Column("error", sa.Text(), nullable=False),
                    sa.Column("events", sa.JSON(), nullable=False),
                    sa.Column("created", sa.Float(), nullable=False),
                    sa.Column("updated", sa.Float(), nullable=False),
                    sqlite_autoincrement=True)
    op.create_index("ix_evolutions_status", "evolutions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_evolutions_status", table_name="evolutions")
    op.drop_table("evolutions")
