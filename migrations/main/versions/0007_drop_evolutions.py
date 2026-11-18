"""Retrait de l'évolution du code et des conteneurs : la table `evolutions` est supprimée (si
elle existe) et les permissions `evolve` et `act.containers` sont retirées des rôles.

Révision : 0007
Précédente : 0006
"""
import json

from alembic import op
import sqlalchemy as sa

from libs.db.migrations import has_table

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

REMOVED = ("evolve", "act.containers")


def upgrade() -> None:
    if has_table("evolutions"):
        op.drop_table("evolutions")   # son index part avec elle
    bind = op.get_bind()
    for name, raw in bind.execute(sa.text("SELECT name, permissions FROM roles")).fetchall():
        permissions = json.loads(raw) if isinstance(raw, str) else raw
        kept = [p for p in permissions if p not in REMOVED]
        if kept != permissions:
            bind.execute(sa.text("UPDATE roles SET permissions = :p WHERE name = :n"),
                         {"p": json.dumps(kept), "n": name})


def downgrade() -> None:
    pass   # fonctionnalité retirée : rien à recréer
