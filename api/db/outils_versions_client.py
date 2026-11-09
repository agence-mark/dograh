"""[.mark] Partie 3, SA-L3d (décision 21) : lire les versions d'un outil, qui les utilise, et passer un agent à une nouvelle version.

Chaque lecture et chaque écriture est bornée à l'organisation DANS la requête. « Passer à la v5 » écrit dans le BROUILLON de l'agent
(celui de la branche ouverte, ou de la principale) : jamais dans une version publiée, jamais dans un autre agent ; la personne teste
et publie ensuite comme d'habitude.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB

from api.db import outils_epingles as pins
from api.db.base_client import BaseDBClient
from api.db.models import ToolModel, WorkflowDefinitionModel, WorkflowModel
from api.db.models_builder import ToolVersionModel, WorkflowBranchModel


class ErreurOutilVersion(Exception):
    """Un refus normal (outil ou version inconnus) : le message est en anglais, l'écran le traduit."""

    def __init__(self, message: str, code: str = "introuvable"):
        super().__init__(message)
        self.code = code


class OutilsVersionsClient(BaseDBClient):
    async def _outil(self, session, organization_id: int, tool_uuid: str) -> ToolModel:
        outil = await session.scalar(
            select(ToolModel).where(ToolModel.tool_uuid == tool_uuid, ToolModel.organization_id == organization_id)
        )
        if outil is None:
            raise ErreurOutilVersion("Tool not found")
        return outil

    async def versions_d_un_outil(self, organization_id: int, tool_uuid: str) -> tuple[ToolModel, list[ToolVersionModel]]:
        """L'outil et ses versions, la plus récente d'abord (en UNE session, bornée à l'organisation)."""
        async with self.async_session() as session:
            outil = await self._outil(session, organization_id, tool_uuid)
            lignes = await session.scalars(
                select(ToolVersionModel)
                .where(ToolVersionModel.organization_id == organization_id, ToolVersionModel.tool_id == outil.id)
                .order_by(ToolVersionModel.version.desc())
            )
            return outil, list(lignes.all())

    async def usage_d_un_outil(self, organization_id: int, tool_uuid: str, user_id: int | None = None) -> list[dict[str, Any]]:
        """Qui utilise quelle version : les versions d'agent EN LIGNE (publiée de la principale, tête d'une branche) et les
        brouillons qui citent l'outil, en UNE requête. ``en_ligne`` : jouée par de vrais appels ; sinon un brouillon (celui de la
        principale, ou celui de ``user_id`` sur une branche : le brouillon d'une autre personne ne se montre pas)."""
        async with self.async_session() as session:
            await self._outil(session, organization_id, tool_uuid)
            lignes = (
                await session.execute(
                    select(
                        WorkflowDefinitionModel.id,
                        WorkflowDefinitionModel.workflow_id,
                        WorkflowDefinitionModel.branch_id,
                        WorkflowDefinitionModel.status,
                        WorkflowDefinitionModel.version_number,
                        WorkflowDefinitionModel.outils_epingles,
                        WorkflowDefinitionModel.draft_owner_id,
                        WorkflowModel.name,
                        WorkflowBranchModel.nom,
                    )
                    .join(WorkflowModel, WorkflowModel.id == WorkflowDefinitionModel.workflow_id)
                    .outerjoin(WorkflowBranchModel, WorkflowBranchModel.id == WorkflowDefinitionModel.branch_id)
                    .where(
                        WorkflowModel.organization_id == organization_id,
                        WorkflowModel.status != "archived",
                        cast(WorkflowDefinitionModel.outils_epingles, JSONB).has_key(tool_uuid),
                    )
                    .order_by(WorkflowModel.name, WorkflowDefinitionModel.id)
                )
            ).all()
            en_tete = set(
                (
                    await session.scalars(
                        select(WorkflowBranchModel.head_definition_id).where(
                            WorkflowBranchModel.organization_id == organization_id,
                            WorkflowBranchModel.statut == "active",
                            WorkflowBranchModel.head_definition_id.is_not(None),
                        )
                    )
                ).all()
            )
            sortie = []
            for identifiant, workflow_id, branch_id, statut, numero, epingles, proprietaire, nom_agent, nom_branche in lignes:
                brouillon = statut == "draft"
                if brouillon and branch_id is not None and proprietaire != user_id:
                    continue
                en_ligne = statut == "published" or identifiant in en_tete
                if not (brouillon or en_ligne):
                    continue
                sortie.append(
                    {
                        "workflow_id": workflow_id,
                        "agent": nom_agent,
                        "branche": nom_branche or "Principale",
                        "branche_id": branch_id,
                        "version_agent": numero,
                        "version_outil": epingles.get(tool_uuid),
                        "en_ligne": en_ligne,
                        "brouillon": brouillon,
                    }
                )
            return sortie

    async def outils_epingles_de_l_agent(self, organization_id: int, workflow_id: int) -> dict[str, Any]:
        """Les outils cités par l'agent ouvert (le brouillon de la branche ouverte s'il existe, sinon sa version en ligne) avec la
        version épinglée et la courante. Un outil sans épingle (ajouté depuis la dernière publication) suit la courante."""
        async with self.async_session() as session:
            agent = await session.scalar(
                select(WorkflowModel).where(WorkflowModel.id == workflow_id, WorkflowModel.organization_id == organization_id)
            )
            if agent is None:
                raise ErreurOutilVersion("Agent not found")
            cible = await self._cible(session, workflow_id)
            source = await self._definition_ouverte(session, workflow_id, cible, agent)
            if source is None:
                return {"source": None, "outils": []}
            uuids = pins.uuids_du_graphe(source.workflow_json)
            outils = (
                (
                    await session.scalars(
                        select(ToolModel).where(ToolModel.tool_uuid.in_(uuids), ToolModel.organization_id == organization_id)
                    )
                ).all()
                if uuids
                else []
            )
            epingles = pins.sans_blocs(source.outils_epingles)
            return {
                "source": "brouillon" if source.status == "draft" else "en_ligne",
                "blocs": pins.seulement_blocs(source.outils_epingles),  # D17 : version figée de chaque bloc réutilisable
                "outils": [
                    {
                        "tool_uuid": o.tool_uuid,
                        "nom": o.name,
                        "epinglee": epingles.get(o.tool_uuid) or (o.version_courante or 1),
                        "courante": o.version_courante or 1,
                        "figee": o.tool_uuid in epingles,
                    }
                    for o in sorted(outils, key=lambda o: o.name)
                ],
            }

    async def _definition_ouverte(self, session, workflow_id: int, cible, agent: WorkflowModel) -> WorkflowDefinitionModel | None:
        brouillon = await session.scalar(
            select(WorkflowDefinitionModel).where(
                WorkflowDefinitionModel.workflow_id == workflow_id,
                WorkflowDefinitionModel.status == "draft",
                WorkflowDefinitionModel.branch_id.is_(None)
                if cible.branch_id is None
                else (WorkflowDefinitionModel.branch_id == cible.branch_id) & (WorkflowDefinitionModel.draft_owner_id == cible.user_id),
            )
        )
        if brouillon is not None:
            return brouillon
        if cible.branch_id is not None:
            branche = await session.get(WorkflowBranchModel, cible.branch_id)
            tete = branche.head_definition_id if branche else None
        else:
            tete = agent.released_definition_id
        return await session.get(WorkflowDefinitionModel, tete) if tete else None

    async def passer_un_outil_a_la_version(
        self, organization_id: int, workflow_id: int, tool_uuid: str, version: int
    ) -> dict[str, Any]:
        """« Passer à la v5 » : écrit l'épingle dans le BROUILLON de l'agent ouvert (le crée, copie de la version en ligne, s'il n'y
        en a pas). La version doit exister pour cet outil. Une version publiée ne change jamais."""
        async with self.async_session() as session:
            outil = await self._outil(session, organization_id, tool_uuid)
            existe = await session.scalar(
                select(ToolVersionModel.id).where(
                    ToolVersionModel.organization_id == organization_id,
                    ToolVersionModel.tool_id == outil.id,
                    ToolVersionModel.version == version,
                )
            )
            if existe is None:
                raise ErreurOutilVersion("This tool has no such version")
            courante = outil.version_courante or 1
        # Le brouillon : celui de la branche ouverte (ou de la principale), créé au besoin avec les règles habituelles
        # (principale protégée refusée, organisation de l'agent contrôlée plus haut par la route).
        brouillon = await self.get_draft_version(workflow_id)
        if brouillon is None:
            brouillon = await self.save_workflow_draft(workflow_id)
        async with self.async_session() as session:
            ligne = await session.scalar(
                select(WorkflowDefinitionModel)
                .join(WorkflowModel, WorkflowModel.id == WorkflowDefinitionModel.workflow_id)
                .where(WorkflowDefinitionModel.id == brouillon.id, WorkflowModel.organization_id == organization_id)
                .with_for_update()
            )
            if ligne is None:
                raise ErreurOutilVersion("Agent not found")
            if tool_uuid not in pins.uuids_du_graphe(ligne.workflow_json):
                raise ErreurOutilVersion("This agent does not use this tool", "pas_utilise")
            epingles = pins.copie(ligne.outils_epingles) or {}
            epingles[tool_uuid] = version
            ligne.outils_epingles = epingles
            identifiant = ligne.id  # lu AVANT le commit : la session de production expire les objets au commit
            await session.commit()
            return {"tool_uuid": tool_uuid, "version": version, "courante": courante, "brouillon": identifiant}

    async def remplacer_les_epingles_du_brouillon(self, organization_id: int, workflow_id: int, epingles: dict[str, int]) -> None:
        """« Revenir avant » : les épingles du BROUILLON de l'agent ouvert redeviennent celles de l'instantané (celles qui citent un outil
        de l'organisation et une version qui existe ; le reste est ignoré). Écrit dans le brouillon seulement, jamais une version publiée."""
        brouillon = await self.get_draft_version(workflow_id)
        if brouillon is None:
            return
        async with self.async_session() as session:
            ligne = await session.scalar(
                select(WorkflowDefinitionModel)
                .join(WorkflowModel, WorkflowModel.id == WorkflowDefinitionModel.workflow_id)
                .where(WorkflowDefinitionModel.id == brouillon.id, WorkflowModel.organization_id == organization_id)
                .with_for_update()
            )
            if ligne is None:
                return
            blocs = {f"{pins.PREFIXE_BLOC}{s}": n for s, n in pins.seulement_blocs(epingles).items()}  # D17 : les blocs gardent leur version
            valides = pins.sans_blocs(epingles)
            if valides:
                connues = (
                    await session.execute(
                        select(ToolModel.tool_uuid, ToolVersionModel.version)
                        .join(ToolVersionModel, ToolVersionModel.tool_id == ToolModel.id)
                        .where(ToolModel.organization_id == organization_id, ToolModel.tool_uuid.in_(list(valides)))
                    )
                ).all()
                existantes = {(u, v) for u, v in connues}
                valides = {u: v for u, v in valides.items() if (u, v) in existantes}
            valides.update(blocs)
            ligne.outils_epingles = valides or None
            await session.commit()
