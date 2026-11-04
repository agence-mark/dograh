"""[.mark] Partie 3, lot 12 (SE-23) : la dépense du mois de l'appelant simulé et du juge (``models_builder.MarkDepenseRoleModel``).

Chaque lecture et chaque écriture est bornée à l'organisation, dans la requête. L'ajout est atomique (``ON CONFLICT DO UPDATE``
qui additionne) : deux appels simultanés ne se perdent pas.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from api.db.base_client import BaseDBClient
from api.db.models_builder import MarkDepenseRoleModel


class DepenseRolesClient(BaseDBClient):
    async def ajouter_depense_role(
        self, organization_id: int, role: str, mois: date, *, appels: int, jetons: int, cout: float
    ) -> None:
        requete = insert(MarkDepenseRoleModel).values(
            organization_id=organization_id, role=role, mois=mois, appels=appels, jetons=jetons, cout=cout
        )
        requete = requete.on_conflict_do_update(
            constraint="uq_mark_depense_roles_org_role_mois",
            set_={
                "appels": MarkDepenseRoleModel.appels + appels,
                "jetons": MarkDepenseRoleModel.jetons + jetons,
                "cout": MarkDepenseRoleModel.cout + cout,
                "modifie_le": datetime.now(UTC),
            },
        )
        async with self.async_session() as session:
            await session.execute(requete)
            await session.commit()

    async def lire_depense_roles(self, organization_id: int, mois: date) -> dict[str, dict[str, float | int]]:
        """Par rôle, la dépense du mois de CETTE organisation : ``{"appelant": {"appels", "jetons", "cout"}, ...}`` (rôle jamais joué : absent)."""
        async with self.async_session() as session:
            lignes = (
                await session.execute(
                    select(
                        MarkDepenseRoleModel.role,
                        func.coalesce(func.sum(MarkDepenseRoleModel.appels), 0),
                        func.coalesce(func.sum(MarkDepenseRoleModel.jetons), 0),
                        func.coalesce(func.sum(MarkDepenseRoleModel.cout), 0.0),
                    )
                    .where(MarkDepenseRoleModel.organization_id == organization_id, MarkDepenseRoleModel.mois == mois)
                    .group_by(MarkDepenseRoleModel.role)
                )
            ).all()
        return {r: {"appels": int(a), "jetons": int(j), "cout": float(c)} for r, a, j, c in lignes}
