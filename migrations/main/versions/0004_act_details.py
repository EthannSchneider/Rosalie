"""« Faire agir Rosalie » en détail : la permission act devient act.memory, act.followups,
act.images, act.discord_read, act.discord_write, act.discord_manage, act.discord_moderate et
act.code. Un rôle qui avait act les reçoit toutes (mêmes droits qu'avant).

Révision : 0004
Précédente : 0003
"""
import json

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# Copie figée (une migration ne dépend pas du code qui évolue)
ACT = ["act.memory", "act.followups", "act.images", "act.discord_read", "act.discord_write",
       "act.discord_manage", "act.discord_moderate", "act.code"]


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
        if "act" not in permissions:
            return permissions
        rest = [p for p in permissions if p != "act"]
        return rest[:1] + ACT + rest[1:] if rest[:1] == ["chat"] else ACT + rest
    _rewrite(convert)


def downgrade() -> None:
    def convert(permissions):
        if not any(p in ACT for p in permissions):
            return permissions
        return [p for p in permissions if p not in ACT] + ["act"]
    _rewrite(convert)
