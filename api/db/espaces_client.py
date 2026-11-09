"""[.mark] Les espaces : le Labo, les noms d'affichage, l'appartenance, et la vue de l'équipe sur toutes les organisations ouvertes."""

from __future__ import annotations

from sqlalchemy import delete, func, or_, select

from api.db import appels_liste
from api.db.base_client import BaseDBClient
from api.db.models import (
    OrganizationConfigurationModel,
    WorkflowModel,
    WorkflowRunModel,
    organization_users_association,
)
from api.services import resume_appel


class EspacesClient(BaseDBClient):
    async def organisation_marquee_labo(self, cle_espace: str) -> int | None:
        """L'organisation marquée Labo ; la plus ancienne si, par accident, il y en a plusieurs."""
        async with self.async_session() as session:
            lignes = (
                await session.execute(
                    select(OrganizationConfigurationModel)
                    .where(OrganizationConfigurationModel.key == cle_espace)
                    .order_by(OrganizationConfigurationModel.organization_id)
                )
            ).scalars().all()
            for ligne in lignes:
                if isinstance(ligne.value, dict) and ligne.value.get("espace") == "labo":
                    return ligne.organization_id
            return None

    async def marquer_labo(self, cle_espace: str, organization_id: int) -> None:
        """Marque l'organisation comme Labo et retire le marquage de toute autre : un seul Labo, dans une transaction."""
        async with self.async_session() as session:
            await session.execute(
                delete(OrganizationConfigurationModel).where(
                    OrganizationConfigurationModel.key == cle_espace,
                    OrganizationConfigurationModel.organization_id != organization_id,
                )
            )
            ligne = (
                await session.execute(
                    select(OrganizationConfigurationModel).where(
                        OrganizationConfigurationModel.key == cle_espace,
                        OrganizationConfigurationModel.organization_id == organization_id,
                    )
                )
            ).scalars().first()
            if ligne is None:
                session.add(
                    OrganizationConfigurationModel(
                        organization_id=organization_id, key=cle_espace, value={"espace": "labo"}
                    )
                )
            else:
                ligne.value = {"espace": "labo"}
            await session.commit()

    async def demarquer_labo(self, cle_espace: str, organization_id: int) -> None:
        async with self.async_session() as session:
            await session.execute(
                delete(OrganizationConfigurationModel).where(
                    OrganizationConfigurationModel.key == cle_espace,
                    OrganizationConfigurationModel.organization_id == organization_id,
                )
            )
            await session.commit()

    async def noms_d_affichage(self, cle_nom: str, organisations: list[int]) -> dict[int, str]:
        if not organisations:
            return {}
        async with self.async_session() as session:
            lignes = (
                await session.execute(
                    select(OrganizationConfigurationModel).where(
                        OrganizationConfigurationModel.key == cle_nom,
                        OrganizationConfigurationModel.organization_id.in_(organisations),
                    )
                )
            ).scalars().all()
            return {
                ligne.organization_id: ligne.value["nom"]
                for ligne in lignes
                if isinstance(ligne.value, dict) and ligne.value.get("nom")
            }

    async def organisations_du_compte(self, user_id: int) -> list[int]:
        async with self.async_session() as session:
            return list(
                (
                    await session.execute(
                        select(organization_users_association.c.organization_id).where(
                            organization_users_association.c.user_id == user_id
                        )
                    )
                ).scalars()
            )

    async def retirer_du_compte_les_organisations(self, user_id: int, organisations: list[int]) -> None:
        if not organisations:
            return
        async with self.async_session() as session:
            await session.execute(
                delete(organization_users_association).where(
                    organization_users_association.c.user_id == user_id,
                    organization_users_association.c.organization_id.in_(organisations),
                )
            )
            await session.commit()

    async def lister_conversations_des_organisations(
        self,
        *,
        organisations: list[int] | None,
        limit: int,
        offset: int,
        motif: str | None = None,
        recherche: str | None = None,
        organisations_nommees: list[int] | None = None,
    ) -> tuple[list[dict], int]:
        """Les conversations (runs) des organisations données (``None`` = toutes), les plus récentes d'abord.

        Clôture SA-5 (É8) : chaque ligne porte motif, résumé, issue, durée, « jugé par » et note (lus du run, une seule requête) ; ``motif``
        est exact, ``recherche`` lit motif, issue, résumés et nom de l'agent (``organisations_nommees`` : les clients dont le NOM contient
        le terme, trouvés par l'appelant qui connaît les noms). Filtre et recherche sont dans la requête, après le cloisonnement."""
        async with self.async_session() as session:
            filtre = []
            if organisations is not None:
                if not organisations:
                    return [], 0
                filtre.append(WorkflowModel.organization_id.in_(organisations))
            portee = list(filtre)  # le cloisonnement seul : la borne de la recherche ne lit que ces organisations
            terme_motif = " ".join((motif or "").split())[: appels_liste.RECHERCHE_MAX]
            if terme_motif:
                filtre.append(appels_liste.filtre_motif(terme_motif))
            terme = appels_liste.terme_de_recherche(recherche)
            if terme is not None:
                recents = (
                    select(WorkflowRunModel.id)
                    .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                    .where(*portee)
                    .order_by(WorkflowRunModel.created_at.desc())
                    .limit(appels_liste.RECHERCHE_APPELS_MAX)
                )
                texte = appels_liste.filtre_recherche(terme, WorkflowModel.name)
                if organisations_nommees:
                    texte = or_(texte, WorkflowModel.organization_id.in_(organisations_nommees))
                filtre.append(WorkflowRunModel.id.in_(recents.scalar_subquery()))
                filtre.append(texte)
            total = (
                await session.execute(
                    select(func.count())
                    .select_from(WorkflowRunModel)
                    .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                    .where(*filtre)
                )
            ).scalar_one()
            lignes = (
                await session.execute(
                    select(
                        WorkflowRunModel.id,
                        WorkflowRunModel.name,
                        WorkflowRunModel.workflow_id,
                        WorkflowModel.name,
                        WorkflowModel.organization_id,
                        WorkflowRunModel.mode,
                        WorkflowRunModel.is_completed,
                        WorkflowRunModel.created_at,
                        WorkflowRunModel.gathered_context,
                        WorkflowRunModel.annotations,
                        WorkflowRunModel.note_juge,
                        WorkflowRunModel.usage_info,
                        WorkflowRunModel.cost_info,
                    )
                    .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                    .where(*filtre)
                    .order_by(WorkflowRunModel.created_at.desc(), WorkflowRunModel.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
            sortie = []
            for i, nom, wf, wf_nom, org, mode, fini, cree, fiche, annotations, note, usage, cout in lignes:
                duree = (usage or {}).get("call_duration_seconds")
                if duree is None:
                    duree = (cout or {}).get("call_duration_seconds")
                sortie.append(
                    {
                        "id": i,
                        "name": nom,
                        "workflow_id": wf,
                        "workflow_name": wf_nom,
                        "organization_id": org,
                        "mode": mode,
                        "is_completed": bool(fini),
                        "created_at": cree,
                        "motif": appels_liste.motif_de_la_fiche(fiche),
                        "issue": str((fiche or {}).get("mapped_call_disposition") or "").strip() or None,
                        "duree": int(round(duree)) if isinstance(duree, (int, float)) else None,
                        "note_juge": note,
                        "juge_par": appels_liste.juge_par(annotations),
                        **resume_appel.champs(annotations),
                    }
                )
            return sortie, int(total)

    async def lister_motifs_des_organisations(self, organisations: list[int], limite: int = 100) -> list[str]:
        """Clôture SA-5 (É8) : les motifs proposés au filtre « Tous les motifs » (un par motif, casse et espaces réunis), des seules
        organisations données."""
        if not organisations:
            return []
        async with self.async_session() as session:
            lignes = await session.execute(
                select(func.min(func.trim(appels_liste.motif())))
                .select_from(WorkflowRunModel)
                .join(WorkflowModel, WorkflowModel.id == WorkflowRunModel.workflow_id)
                .where(WorkflowModel.organization_id.in_(organisations), appels_liste.motif().is_not(None))
                .group_by(appels_liste.motif_replie())
                .order_by(func.min(func.trim(appels_liste.motif())))
                .limit(limite)
            )
            return [m for (m,) in lignes.all() if m]
