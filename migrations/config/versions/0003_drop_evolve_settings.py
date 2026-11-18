"""Retrait de l'évolution du code et des conteneurs : leurs réglages enregistrés sont effacés
(dont le jeton GitHub, qui n'a plus à rester en base).

Révision : 0003
Précédente : 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text(
        "DELETE FROM settings WHERE key IN ('code_model', 'github_token') "
        "OR key = 'containers' OR key LIKE 'containers\\_%' ESCAPE '\\' "
        "OR key = 'evolve' OR key LIKE 'evolve\\_%' ESCAPE '\\'"))


def downgrade() -> None:
    pass   # fonctionnalité retirée : rien à recréer
