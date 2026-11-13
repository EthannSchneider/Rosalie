"""Lien entre un compte et son identifiant Discord (remplace OWNER_IDS).

Ajout simple (ALTER TABLE ADD COLUMN) + index unique, SANS recréer la table : le mode « batch »
d'Alembic la recrée à partir de la base relue, et SQLite n'y relit ni COLLATE NOCASE ni
AUTOINCREMENT (les noms de compte deviendraient sensibles à la casse).

Révision : 0002
Précédente : 0001
"""
from alembic import op
import sqlalchemy as sa

from libs.db.migrations import has_column

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if has_column("users", "discord_id"):   # base créée avant Alembic, déjà à jour
        return
    op.add_column("users", sa.Column("discord_id", sa.Text()))
    op.create_index("ix_users_discord_id", "users", ["discord_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_discord_id", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("discord_id")
