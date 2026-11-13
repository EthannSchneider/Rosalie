"""Schéma initial : comptes, sessions, historique du chat, fichiers.

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
    if not has_table("users"):
        op.create_table("users",
                        sa.Column("id", sa.Integer(), primary_key=True),
                        sa.Column("username", sa.String(collation="NOCASE"), nullable=False, unique=True),
                        sa.Column("password", sa.Text(), nullable=False),
                        sa.Column("role", sa.Text(), nullable=False),
                        sa.Column("created", sa.Float(), nullable=False),
                        sa.Column("last_login", sa.Float()),
                        sqlite_autoincrement=True)
    if not has_table("sessions"):
        op.create_table("sessions",
                        sa.Column("token_hash", sa.Text(), primary_key=True),
                        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                                  nullable=False),
                        sa.Column("expires", sa.Float(), nullable=False))
    if not has_table("messages"):
        op.create_table("messages",
                        sa.Column("id", sa.Integer(), primary_key=True),
                        sa.Column("conversation", sa.Text(), nullable=False),
                        sa.Column("author", sa.Text(), nullable=False),
                        sa.Column("text", sa.Text(), nullable=False),
                        sa.Column("kind", sa.Text(), nullable=False),
                        sa.Column("meta", sa.JSON(), nullable=False),
                        sa.Column("created", sa.Float(), nullable=False),
                        sqlite_autoincrement=True)
        op.create_index("messages_conversation", "messages", ["conversation", "id"])
    if not has_table("files"):
        op.create_table("files",
                        sa.Column("id", sa.Text(), primary_key=True),
                        sa.Column("conversation", sa.Text(), nullable=False),
                        sa.Column("name", sa.Text(), nullable=False),
                        sa.Column("type", sa.Text(), nullable=False),
                        sa.Column("path", sa.Text(), nullable=False))


def downgrade() -> None:
    op.drop_table("files")
    op.drop_index("messages_conversation", table_name="messages")
    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("users")
