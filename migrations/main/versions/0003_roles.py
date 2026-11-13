"""Rôles gérables avec des permissions (remplace les trois rôles écrits dans le code).

Crée la table roles avec superadmin (verrouillé), admin et user : chaque compte garde son rôle.
users.role n'a pas de clé étrangère : l'ajouter recréerait la table (mode batch), ce qui perd
COLLATE NOCASE / AUTOINCREMENT sur SQLite. Le dépôt (libs/models/roles.py) vérifie qu'un rôle
existe avant de l'attribuer, et refuse de supprimer un rôle encore utilisé.

Révision : 0003
Précédente : 0002
"""
import time

from alembic import op
import sqlalchemy as sa

from libs.db.migrations import has_table

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Copie figée des rôles de départ (une migration ne doit pas dépendre du code qui évolue)
ALL = ["chat", "act", "personas", "settings", "users", "roles"]
ROLES = [
    ("superadmin", "Superadmin", "Tout, y compris les rôles et les utilisateurs. Il en reste toujours au moins un.", ALL, True),
    ("admin", "Admin", "Rosalie agit pour lui (outils, souvenirs, code), sur le chat web et sur Discord.", ["chat", "act"], False),
    ("user", "Utilisateur", "Discute avec Rosalie, comme un invité : discussion et recherche seulement.", ["chat"], False),
]


def upgrade() -> None:
    if has_table("roles"):
        return
    roles = op.create_table(
        "roles",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("locked", sa.Boolean(), nullable=False),
        sa.Column("created", sa.Float(), nullable=False),
    )
    now = time.time()
    op.bulk_insert(roles, [{"name": n, "label": l, "description": d, "permissions": p, "locked": k, "created": now}
                           for n, l, d, p, k in ROLES])


def downgrade() -> None:
    op.drop_table("roles")
