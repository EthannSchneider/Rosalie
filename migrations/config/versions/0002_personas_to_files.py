"""Les personnalités personnalisées deviennent des fichiers : storages/personas/<nom>.md.

Celles qui étaient en base sont exportées (sans écraser un fichier existant), puis la table
est supprimée.

Révision : 0002
Précédente : 0001
"""
from pathlib import Path

from alembic import op
import sqlalchemy as sa

from libs.db.migrations import has_table

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not has_table("personas"):
        return
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT name, text FROM personas")).fetchall()
    if rows:
        database = next((row[2] for row in bind.execute(sa.text("PRAGMA database_list")) if row[1] == "main"), "")
        if not database:   # base en mémoire : nulle part où écrire, on garde la table
            return
        folder = Path(database).parent / "personas"
        folder.mkdir(parents=True, exist_ok=True)
        for name, text in rows:
            target = folder / f"{name}.md"
            if not target.exists():
                target.write_text(text, encoding="utf-8")
    op.drop_table("personas")


def downgrade() -> None:
    # Les fichiers restent dans storages/personas/ ; on recrée seulement la table (vide)
    op.create_table("personas",
                    sa.Column("name", sa.Text(), primary_key=True),
                    sa.Column("text", sa.Text(), nullable=False),
                    sa.Column("updated", sa.Float(), nullable=False))
