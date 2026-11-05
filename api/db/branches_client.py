"""[.mark] Partie 3, SA-L3b (05 § 12) : les branches d'agent (``models_builder.WorkflowBranchModel``) et leurs versions.

Chaque lecture et chaque écriture est bornée à l'organisation DANS la requête (la branche, l'agent, l'organisation vont ensemble).
Une version d'une branche non principale est une ligne de ``workflow_definitions`` au statut ``archived`` (jamais ``published`` :
ce statut est réservé à la version en ligne de la principale, que tout le code d'avant sait lire) ; la version en ligne de la
branche est ``head_definition_id``. Les parts de trafic changent toutes ensemble, sous verrou, et font toujours 100.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from api.db.base_client import BaseDBClient
from api.db.models import WorkflowDefinitionModel, WorkflowModel
from api.db.models_builder import WorkflowBranchModel

NOM_DE_LA_PRINCIPALE = "Principale"


class ErreurDeBranche(Exception):
    """Un refus normal (nom pris, part invalide, branche inconnue) : le message est en anglais, l'écran le traduit."""

    def __init__(self, message: str, code: str = "refus"):
        super().__init__(message)
        self.code = code


class BranchesClient(BaseDBClient):
    async def _agent_de_l_organisation(self, session, organization_id: int, workflow_id: int) -> WorkflowModel:
        agent = await session.scalar(
            select(WorkflowModel).where(WorkflowModel.id == workflow_id, WorkflowModel.organization_id == organization_id)
        )
        if agent is None:
            raise ErreurDeBranche("Agent not found", "introuvable")
        return agent

    async def _principale(self, session, organization_id: int, workflow_id: int) -> WorkflowBranchModel:
        """La principale de l'agent ; posée ici si l'agent est plus récent que la migration (une seule par agent : index unique)."""
        requete = select(WorkflowBranchModel).where(
            WorkflowBranchModel.organization_id == organization_id,
            WorkflowBranchModel.workflow_id == workflow_id,
            WorkflowBranchModel.est_principale.is_(True),
        )
        principale = await session.scalar(requete)
        if principale is None:
            await session.execute(
                insert(WorkflowBranchModel)
                .values(
                    organization_id=organization_id,
                    workflow_id=workflow_id,
                    nom=NOM_DE_LA_PRINCIPALE,
                    est_principale=True,
                    statut="active",
                    part_trafic=100,
                )
                .on_conflict_do_nothing()
            )
            principale = await session.scalar(requete)
        return principale

    async def obtenir_la_principale(self, organization_id: int, workflow_id: int) -> WorkflowBranchModel:
        async with self.async_session() as session:
            await self._agent_de_l_organisation(session, organization_id, workflow_id)
            await self._principale(session, organization_id, workflow_id)
            await session.commit()
            # Relue APRÈS le commit : une session de production expire les objets au commit (jamais un objet détaché illisible).
            return await self._principale(session, organization_id, workflow_id)

    async def lister_les_branches(
        self, organization_id: int, workflow_id: int, *, avec_archivees: bool = False
    ) -> list[WorkflowBranchModel]:
        """La principale d'abord, puis les autres par ancienneté."""
        async with self.async_session() as session:
            await self._agent_de_l_organisation(session, organization_id, workflow_id)
            await self._principale(session, organization_id, workflow_id)
            await session.commit()  # la principale posée est écrite ; la lecture suivante rend des objets qui restent lisibles
            requete = select(WorkflowBranchModel).where(
                WorkflowBranchModel.organization_id == organization_id, WorkflowBranchModel.workflow_id == workflow_id
            )
            if not avec_archivees:
                requete = requete.where(WorkflowBranchModel.statut == "active")
            lignes = (
                await session.scalars(requete.order_by(WorkflowBranchModel.est_principale.desc(), WorkflowBranchModel.id))
            ).all()
            return list(lignes)

    async def obtenir_une_branche(self, organization_id: int, workflow_id: int, branch_id: int) -> WorkflowBranchModel | None:
        async with self.async_session() as session:
            return await session.scalar(
                select(WorkflowBranchModel).where(
                    WorkflowBranchModel.id == branch_id,
                    WorkflowBranchModel.workflow_id == workflow_id,
                    WorkflowBranchModel.organization_id == organization_id,
                )
            )

    async def creer_une_branche(
        self,
        organization_id: int,
        workflow_id: int,
        nom: str,
        *,
        depuis_definition_id: int | None,
        user_id: int | None,
        protegee: bool = False,
    ) -> tuple[WorkflowBranchModel, WorkflowDefinitionModel]:
        """Crée la branche (0 % du trafic : les appels en cours ne bougent pas) et le brouillon de son auteur, copie de la version
        de départ (par défaut la version en ligne de la principale)."""
        async with self.async_session() as session:
            agent = await self._agent_de_l_organisation(session, organization_id, workflow_id)
            await self._principale(session, organization_id, workflow_id)
            identifiant = depuis_definition_id or agent.released_definition_id
            source = None
            if identifiant is not None:
                source = await session.scalar(
                    select(WorkflowDefinitionModel).where(
                        WorkflowDefinitionModel.id == identifiant,
                        WorkflowDefinitionModel.workflow_id == workflow_id,
                        WorkflowDefinitionModel.status.in_(("published", "archived")),
                    )
                )
                if source is None:
                    raise ErreurDeBranche("Published or archived agent version not found", "introuvable")
            branche = WorkflowBranchModel(
                organization_id=organization_id,
                workflow_id=workflow_id,
                nom=nom,
                est_principale=False,
                statut="active",
                part_trafic=0,
                head_definition_id=source.id if source is not None else None,
                base_definition_id=source.id if source is not None else None,
                protegee=protegee,
                cree_par=user_id,
            )
            session.add(branche)
            try:
                await session.flush()
            except IntegrityError:
                await session.rollback()
                raise ErreurDeBranche("A branch with this name already exists", "nom_pris") from None
            brouillon = WorkflowDefinitionModel(
                workflow_id=workflow_id,
                workflow_json=source.workflow_json if source else (agent.workflow_definition or {}),
                workflow_configurations=source.workflow_configurations if source else (agent.workflow_configurations or {}),
                template_context_variables=source.template_context_variables if source else (agent.template_context_variables or {}),
                status="draft",
                version_number=await self._next_version_number(session, workflow_id),
                is_current=False,
                branch_id=branche.id,
                draft_owner_id=user_id,
            )
            session.add(brouillon)
            await session.commit()
            await session.refresh(branche)
            await session.refresh(brouillon)
            return branche, brouillon  # rafraîchis après le commit : lisibles même une fois la session fermée

    async def publier_le_brouillon_de_branche(
        self, organization_id: int, workflow_id: int, branch_id: int, user_id: int | None
    ) -> WorkflowDefinitionModel:
        """Le brouillon de cette personne devient une version IMMUABLE de la branche, qui devient sa version en ligne.

        Statut ``archived`` en base (voir l'en-tête) ; le pointeur de la principale n'est jamais touché."""
        async with self.async_session() as session:
            branche = await session.scalar(
                select(WorkflowBranchModel)
                .where(
                    WorkflowBranchModel.id == branch_id,
                    WorkflowBranchModel.workflow_id == workflow_id,
                    WorkflowBranchModel.organization_id == organization_id,
                )
                .with_for_update()
            )
            if branche is None or branche.statut != "active":
                raise ErreurDeBranche("Branch not found", "introuvable")
            if branche.est_principale:
                raise ErreurDeBranche("The main branch is published with the agent's own Publish", "principale")
            brouillon = await session.scalar(
                select(WorkflowDefinitionModel).where(
                    WorkflowDefinitionModel.workflow_id == workflow_id,
                    WorkflowDefinitionModel.status == "draft",
                    WorkflowDefinitionModel.branch_id == branch_id,
                    WorkflowDefinitionModel.draft_owner_id == user_id,
                )
            )
            if brouillon is None:
                raise ErreurDeBranche("No draft exists on this branch for you", "sans_brouillon")
            brouillon.status = "archived"
            brouillon.is_current = False
            brouillon.published_at = datetime.now(UTC)
            branche.head_definition_id = brouillon.id
            await session.commit()
            await session.refresh(brouillon)
            return brouillon

    async def version_en_ligne_de_la_branche_ouverte(self, workflow_id: int) -> WorkflowDefinitionModel | None:
        """La version en ligne de la branche non principale que la requête a ouverte (``None`` : la principale est ouverte, ou la
        branche n'a pas de version). Sert à montrer la bonne version quand la branche n'a pas de brouillon."""
        async with self.async_session() as session:
            cible = await self._cible(session, workflow_id)
            if cible.branch_id is None:
                return None
            branche = await session.get(WorkflowBranchModel, cible.branch_id)
            if branche is None or branche.head_definition_id is None:
                return None
            return await session.get(WorkflowDefinitionModel, branche.head_definition_id)

    async def versions_des_branches(self, organization_id: int, workflow_id: int) -> list[dict[str, Any]]:
        """Les versions immuables des branches non principales (les plus récentes d'abord), sans leur graphe, en UNE requête."""
        async with self.async_session() as session:
            lignes = await session.execute(
                select(
                    WorkflowDefinitionModel.branch_id,
                    WorkflowDefinitionModel.id,
                    WorkflowDefinitionModel.version_number,
                    WorkflowDefinitionModel.published_at,
                )
                .join(WorkflowModel, WorkflowModel.id == WorkflowDefinitionModel.workflow_id)
                .where(
                    WorkflowModel.organization_id == organization_id,
                    WorkflowDefinitionModel.workflow_id == workflow_id,
                    WorkflowDefinitionModel.branch_id.is_not(None),
                    WorkflowDefinitionModel.status == "archived",
                )
                .order_by(WorkflowDefinitionModel.version_number.desc())
            )
            return [dict(ligne) for ligne in lignes.mappings()]

    async def brouillons_de_l_agent(self, organization_id: int, workflow_id: int) -> list[dict[str, Any]]:
        """Les brouillons de l'agent (``branch_id`` NULL : celui de la principale), sans leur graphe."""
        async with self.async_session() as session:
            lignes = await session.execute(
                select(
                    WorkflowDefinitionModel.id,
                    WorkflowDefinitionModel.branch_id,
                    WorkflowDefinitionModel.draft_owner_id,
                    WorkflowDefinitionModel.version_number,
                )
                .join(WorkflowModel, WorkflowModel.id == WorkflowDefinitionModel.workflow_id)
                .where(
                    WorkflowModel.organization_id == organization_id,
                    WorkflowDefinitionModel.workflow_id == workflow_id,
                    WorkflowDefinitionModel.status == "draft",
                )
                .order_by(WorkflowDefinitionModel.id)
            )
            return [dict(ligne) for ligne in lignes.mappings()]

    async def regler_la_repartition(
        self, organization_id: int, workflow_id: int, parts: dict[int, int]
    ) -> list[WorkflowBranchModel]:
        """Écrit les parts de TOUTES les branches actives d'un coup (sous verrou) : le total est exigé à 100, une branche non
        principale reçoit 0 à 99, la principale garde au moins 1 (tout envoyer sur une branche se fait par une fusion)."""
        async with self.async_session() as session:
            await self._agent_de_l_organisation(session, organization_id, workflow_id)
            await self._principale(session, organization_id, workflow_id)
            branches = (
                await session.scalars(
                    select(WorkflowBranchModel)
                    .where(
                        WorkflowBranchModel.organization_id == organization_id,
                        WorkflowBranchModel.workflow_id == workflow_id,
                        WorkflowBranchModel.statut == "active",
                    )
                    .order_by(WorkflowBranchModel.id)
                    .with_for_update()
                )
            ).all()
            actives = {b.id: b for b in branches}
            if set(parts) != set(actives):
                raise ErreurDeBranche("The shares must name every active branch of the agent, and only those", "branches")
            if any(not isinstance(v, int) or isinstance(v, bool) for v in parts.values()):
                raise ErreurDeBranche("A share is a whole number", "part")
            if sum(parts.values()) != 100:
                raise ErreurDeBranche("The shares must add up to 100", "total")
            for identifiant, part in parts.items():
                branche = actives[identifiant]
                if branche.est_principale and not 1 <= part <= 100:
                    raise ErreurDeBranche("The main branch keeps at least 1% of the calls", "part")
                if not branche.est_principale and not 0 <= part <= 99:
                    raise ErreurDeBranche("A branch takes 0 to 99% of the calls", "part")
            for identifiant, part in parts.items():
                actives[identifiant].part_trafic = part
            await session.commit()
            relues = await session.scalars(
                select(WorkflowBranchModel)
                .where(WorkflowBranchModel.workflow_id == workflow_id, WorkflowBranchModel.organization_id == organization_id)
                .order_by(WorkflowBranchModel.id)
            )
            return [b for b in relues.all() if b.id in parts]

    async def repartition_en_cours(self, organization_id: int, workflow_id: int) -> list[dict[str, Any]]:
        """Pour la création d'un appel : les branches actives avec leur part et leur version, les non principales d'abord (par
        identifiant), la principale en dernier. Une seule requête, filtrée par l'organisation."""
        async with self.async_session() as session:
            lignes = await session.execute(
                select(
                    WorkflowBranchModel.id,
                    WorkflowBranchModel.est_principale,
                    WorkflowBranchModel.part_trafic,
                    WorkflowBranchModel.head_definition_id,
                )
                .where(
                    WorkflowBranchModel.organization_id == organization_id,
                    WorkflowBranchModel.workflow_id == workflow_id,
                    WorkflowBranchModel.statut == "active",
                )
                .order_by(WorkflowBranchModel.est_principale, WorkflowBranchModel.id)
            )
            return [
                {"branche": r["id"], "principale": r["est_principale"], "part": r["part_trafic"], "definition": r["head_definition_id"]}
                for r in lignes.mappings()
            ]

    async def epingler_la_principale(self, organization_id: int, workflow_id: int, definition_id: int | None) -> None:
        """La principale sert ``definition_id`` (NULL : la version publiée de l'agent, qui suit les publications)."""
        async with self.async_session() as session:
            await self._agent_de_l_organisation(session, organization_id, workflow_id)
            principale = await self._principale(session, organization_id, workflow_id)
            principale.head_definition_id = definition_id
            await session.commit()

    async def protection_de_la_principale(self, organization_id: int, workflow_id: int) -> tuple[bool, bool]:
        """(protégée en fait, protégée par la règle seule). La règle : agent client en ligne (voir ``protection_principale``). Le
        drapeau ne lève que ce que la règle n'impose pas."""
        from api.db import protection_principale

        async with self.async_session() as session:
            await self._agent_de_l_organisation(session, organization_id, workflow_id)
            principale = await self._principale(session, organization_id, workflow_id)
            en_fait = await protection_principale.est_protegee(session, workflow_id)
            return en_fait, en_fait and not principale.protegee

    async def regler_la_protection_de_la_principale(self, organization_id: int, workflow_id: int, protegee: bool) -> None:
        async with self.async_session() as session:
            await self._agent_de_l_organisation(session, organization_id, workflow_id)
            principale = await self._principale(session, organization_id, workflow_id)
            principale.protegee = protegee
            await session.commit()

    async def compter_les_branches(self, organization_id: int, workflow_ids: list[int]) -> dict[int, int]:
        if not workflow_ids:
            return {}
        async with self.async_session() as session:
            lignes = await session.execute(
                select(WorkflowBranchModel.workflow_id, func.count())
                .where(
                    WorkflowBranchModel.organization_id == organization_id,
                    WorkflowBranchModel.workflow_id.in_(workflow_ids),
                    WorkflowBranchModel.statut == "active",
                )
                .group_by(WorkflowBranchModel.workflow_id)
            )
            return dict(lignes.all())
