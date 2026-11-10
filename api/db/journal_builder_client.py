"""[.mark] Partie 3, N1 (SA-N1b) : le journal des écritures du builder (``models_builder.MarkBuilderJournalModel``).

Chaque lecture et chaque écriture est bornée à l'organisation, DANS la requête. La liste est paginée (limite bornée, total). Une ligne
ne se réécrit que pour sa clôture et son annulation (``UPDATE ... WHERE statut = 'en_cours'`` et ``annule_le IS NULL`` : une annulation ne
se joue qu'une fois, même avec deux clics simultanés).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update

from api.db.base_client import BaseDBClient
from api.db.models_builder import MarkBuilderJournalModel

LIMITE_MAX = 100


def _vue(ligne: MarkBuilderJournalModel) -> dict[str, Any]:
    return {
        "id": ligne.id,
        "quand": ligne.quand,
        "workflow_id": ligne.workflow_id,
        "fil_id": ligne.fil_id,
        "user_id": ligne.user_id,
        "auteur": ligne.auteur,
        "porte": ligne.porte,
        "action": ligne.action,
        "famille": ligne.famille,
        "mode": ligne.mode,
        "autorisation": ligne.autorisation,
        "statut": ligne.statut,
        "arguments": ligne.arguments,
        "avant": ligne.avant,
        "apres": ligne.apres,
        "annulation": ligne.annulation,
        "non_annulable": ligne.non_annulable,
        "annule_le": ligne.annule_le,
        "annule_par": ligne.annule_par,
    }


class JournalBuilderClient(BaseDBClient):
    async def ecrire_journal_builder(self, organization_id: int, **champs: Any) -> int:
        async with self.async_session() as session:
            ligne = MarkBuilderJournalModel(organization_id=organization_id, **champs)
            session.add(ligne)
            await session.flush()
            identifiant = int(ligne.id)  # lu avant le commit, qui expire l'objet
            await session.commit()
            return identifiant

    async def clore_journal_builder(self, organization_id: int, ligne_id: int, **champs: Any) -> bool:
        async with self.async_session() as session:
            resultat = await session.execute(
                update(MarkBuilderJournalModel)
                .where(MarkBuilderJournalModel.id == ligne_id, MarkBuilderJournalModel.organization_id == organization_id)
                .where(MarkBuilderJournalModel.statut == "en_cours")
                .values(**champs)
            )
            await session.commit()
            return resultat.rowcount > 0

    async def lire_journal_builder(self, organization_id: int, ligne_id: int) -> dict[str, Any] | None:
        async with self.async_session() as session:
            ligne = (
                await session.execute(
                    select(MarkBuilderJournalModel).where(
                        MarkBuilderJournalModel.id == ligne_id, MarkBuilderJournalModel.organization_id == organization_id
                    )
                )
            ).scalar_one_or_none()
            return _vue(ligne) if ligne is not None else None

    async def lister_journal_builder(
        self,
        organization_id: int,
        *,
        limit: int = 25,
        offset: int = 0,
        workflow_id: int | None = None,
        fil_id: int | None = None,
        famille: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Une page, de la plus récente à la plus ancienne, et le total (mêmes filtres, dans la requête)."""
        limit = max(1, min(limit, LIMITE_MAX))
        filtre = [MarkBuilderJournalModel.organization_id == organization_id]
        if workflow_id is not None:
            filtre.append(MarkBuilderJournalModel.workflow_id == workflow_id)
        if fil_id is not None:
            filtre.append(MarkBuilderJournalModel.fil_id == fil_id)
        if famille:
            filtre.append(MarkBuilderJournalModel.famille == famille)
        async with self.async_session() as session:
            total = (await session.execute(select(func.count()).select_from(MarkBuilderJournalModel).where(*filtre))).scalar_one()
            lignes = (
                await session.execute(
                    select(MarkBuilderJournalModel)
                    .where(*filtre)
                    .order_by(MarkBuilderJournalModel.id.desc())
                    .limit(limit)
                    .offset(max(0, offset))
                )
            ).scalars().all()
            return [_vue(ligne) for ligne in lignes], int(total)

    async def une_ecriture_plus_recente_du_journal(self, organization_id: int, workflow_id: int, apres_id: int) -> bool:
        """Une écriture faite et encore en place, sur le même agent, après la ligne ``apres_id`` (« Annuler » refuse alors : défaire
        l'ancienne emporterait la récente)."""
        async with self.async_session() as session:
            trouvee = (
                await session.execute(
                    select(MarkBuilderJournalModel.id)
                    .where(
                        MarkBuilderJournalModel.organization_id == organization_id,
                        MarkBuilderJournalModel.workflow_id == workflow_id,
                        MarkBuilderJournalModel.id > apres_id,
                        MarkBuilderJournalModel.statut == "fait",
                        MarkBuilderJournalModel.non_annulable.is_(None),
                        MarkBuilderJournalModel.annule_le.is_(None),
                    )
                    .limit(1)
                )
            ).first()
            return trouvee is not None

    async def marquer_annule_journal_builder(self, organization_id: int, ligne_id: int, auteur: str) -> bool:
        async with self.async_session() as session:
            resultat = await session.execute(
                update(MarkBuilderJournalModel)
                .where(MarkBuilderJournalModel.id == ligne_id, MarkBuilderJournalModel.organization_id == organization_id)
                .where(MarkBuilderJournalModel.annule_le.is_(None))
                .values(annule_le=datetime.now(UTC), annule_par=auteur[:255])
            )
            await session.commit()
            return resultat.rowcount > 0
