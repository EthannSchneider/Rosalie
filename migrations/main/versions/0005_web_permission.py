"""Permission « web » (recherche web, lecture de pages, météo) : jusqu'ici ouverte à tous, elle
devient une permission. Tous les rôles la reçoivent, pour garder les mêmes droits qu'avant.

Révision : 0005
Précédente : 0004
"""
import json

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _rewrite(convert) -> None:
    bind = op.get_bind()
    for name, raw in bind.execute(sa.text("SELECT name, permissions FROM roles")).fetchall():
        permissions = json.loads(raw) if isinstance(raw, str) else raw
        updated = convert(permissions)
        if updated != permissions:
            bind.execute(sa.text("UPDATE roles SET permissions = :p WHERE name = :n"),
                         {"p": json.dumps(updated), "n": name})


def upgrade() -> None:
    def convert(permissions):
        if "web" in permissions:
            return permissions
        if permissions[:1] == ["chat"]:
            return ["chat", "web", *permissions[1:]]
        return ["web", *permissions]
    _rewrite(convert)


def downgrade() -> None:
    _rewrite(lambda permissions: [p for p in permissions if p != "web"])
