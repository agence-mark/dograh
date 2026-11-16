"""[.mark] Module Restauration, lot 9 : le lien « point de vente d'une caisse -> établissement » (table ``mark_point_de_vente``, lot 1).

Un point de vente d'une prise ne sert qu'UN établissement (index unique) : un message signé de la caisse retrouve ainsi son organisation et son
établissement sans ambiguïté. Chaque écriture est bornée à l'organisation ; la date de création est posée par l'appelant (source d'heure, D6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from api.db.base_client import BaseDBClient
from api.db.models_restauration import MarkPointDeVenteModel


class PointDeVenteDejaPris(ValueError):
    """Ce point de vente de cette prise sert déjà un autre établissement (ou une autre organisation) : jamais deux."""


class PointDeVenteClient(BaseDBClient):
    async def lier_point_de_vente(self, organization_id: int, prise: str, point_de_vente: str, etablissement_cle: str, cree_le: datetime) -> None:
        async with self.async_session() as session:
            existant = (
                await session.execute(select(MarkPointDeVenteModel).where(MarkPointDeVenteModel.prise == prise, MarkPointDeVenteModel.point_de_vente == point_de_vente))
            ).scalar_one_or_none()
            if existant is not None:
                if (existant.organization_id, existant.etablissement_cle) != (organization_id, etablissement_cle):
                    raise PointDeVenteDejaPris(prise)
                return
            # Un établissement n'a qu'un point de vente par prise : le précédent est remplacé.
            await session.execute(
                delete(MarkPointDeVenteModel).where(
                    MarkPointDeVenteModel.organization_id == organization_id, MarkPointDeVenteModel.prise == prise,
                    MarkPointDeVenteModel.etablissement_cle == etablissement_cle,
                )
            )
            session.add(
                MarkPointDeVenteModel(organization_id=organization_id, prise=prise, point_de_vente=point_de_vente, etablissement_cle=etablissement_cle, cree_le=cree_le)
            )
            await session.commit()

    async def retrouver_le_point_de_vente(self, prise: str, point_de_vente: str) -> dict[str, Any] | None:
        """``{organization_id, etablissement_cle}`` du point de vente d'un message reçu ; ``None`` : inconnu (journalisé, jamais traité)."""
        async with self.async_session() as session:
            r = (
                await session.execute(select(MarkPointDeVenteModel).where(MarkPointDeVenteModel.prise == prise, MarkPointDeVenteModel.point_de_vente == point_de_vente))
            ).scalar_one_or_none()
            return None if r is None else {"organization_id": r.organization_id, "etablissement_cle": r.etablissement_cle}

    async def delier_le_point_de_vente(self, organization_id: int, prise: str, etablissement_cle: str) -> int:
        async with self.async_session() as session:
            res = await session.execute(
                delete(MarkPointDeVenteModel).where(
                    MarkPointDeVenteModel.organization_id == organization_id, MarkPointDeVenteModel.prise == prise,
                    MarkPointDeVenteModel.etablissement_cle == etablissement_cle,
                )
            )
            await session.commit()
            return res.rowcount or 0
