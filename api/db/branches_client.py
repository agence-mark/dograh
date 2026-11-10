"""[.mark] Partie 3, SA-L3b (05 § 12) : les branches d'agent (``models_builder.WorkflowBranchModel``) et leurs versions.

Chaque lecture et chaque écriture est bornée à l'organisation DANS la requête (la branche, l'agent, l'organisation vont ensemble).
Une version d'une branche non principale est une ligne de ``workflow_definitions`` au statut ``archived`` (jamais ``published`` :
ce statut est réservé à la version en ligne de la principale, que tout le code d'avant sait lire) ; la version en ligne de la
branche est ``head_definition_id``. Les parts de trafic changent toutes ensemble, sous verrou, et font toujours 100.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from api.db import auteur_de_version
from api.db import outils_epingles as pins
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
                outils_epingles=pins.copie(source.outils_epingles) if source else None,  # SA-L3d
                **auteur_de_version.colonnes(),  # [.mark] Clôture, É36
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
            # [.mark] Clôture, É36 : « Ce qui change » contre la version que la branche servait jusque-là.
            ancienne_tete = await session.get(WorkflowDefinitionModel, branche.head_definition_id) if branche.head_definition_id else None
            if ancienne_tete is not None:
                from api.services.publication import resume_version

                brouillon.resume_changements = resume_version.resumer(
                    brouillon.workflow_json,
                    ancienne_tete.workflow_json,
                    brouillon.workflow_configurations,
                    ancienne_tete.workflow_configurations,
                )
            brouillon.status = "archived"
            brouillon.is_current = False
            brouillon.published_at = datetime.now(UTC)
            await pins.figer(session, brouillon, organization_id)  # SA-L3d (décision 21)
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

    # --- fusion et mise à jour (SA-L3c) ---------------------------------------------------------------------------------------------

    @staticmethod
    def _contenu(definition: WorkflowDefinitionModel | None) -> dict[str, Any] | None:
        if definition is None:
            return None
        return {
            "id": definition.id,
            "numero": definition.version_number,
            "graphe": definition.workflow_json or {},
            "reglages": definition.workflow_configurations or {},
            "variables": definition.template_context_variables or {},
            "outils": definition.outils_epingles or {},
        }

    async def lire_pour_la_fusion(self, organization_id: int, workflow_id: int, branch_id: int, user_id: int | None) -> dict[str, Any]:
        """Tout ce qu'il faut pour fusionner ou mettre à jour une branche, en UNE session et bornée à l'organisation : la branche, la
        principale, la version de départ (base), les versions en ligne des deux, le brouillon de la personne sur la branche et la
        présence d'un brouillon sur la principale. Aucune écriture."""
        async with self.async_session() as session:
            agent = await self._agent_de_l_organisation(session, organization_id, workflow_id)
            principale = await self._principale(session, organization_id, workflow_id)
            branche = await session.scalar(
                select(WorkflowBranchModel).where(
                    WorkflowBranchModel.id == branch_id,
                    WorkflowBranchModel.workflow_id == workflow_id,
                    WorkflowBranchModel.organization_id == organization_id,
                )
            )
            if branche is None or branche.est_principale or branche.statut != "active":
                raise ErreurDeBranche("Branch not found", "introuvable")

            async def definition(identifiant: int | None):
                if identifiant is None:
                    return None
                return await session.scalar(
                    select(WorkflowDefinitionModel).where(
                        WorkflowDefinitionModel.id == identifiant, WorkflowDefinitionModel.workflow_id == workflow_id
                    )
                )

            tete_principale = principale.head_definition_id or agent.released_definition_id
            brouillon = None
            if user_id is not None:
                brouillon = await session.scalar(
                    select(WorkflowDefinitionModel).where(
                        WorkflowDefinitionModel.workflow_id == workflow_id,
                        WorkflowDefinitionModel.status == "draft",
                        WorkflowDefinitionModel.branch_id == branch_id,
                        WorkflowDefinitionModel.draft_owner_id == user_id,
                    )
                )
            brouillon_principale = await session.scalar(
                select(WorkflowDefinitionModel.id).where(
                    WorkflowDefinitionModel.workflow_id == workflow_id,
                    WorkflowDefinitionModel.status == "draft",
                    WorkflowDefinitionModel.branch_id.is_(None),
                )
            )
            return {
                "branche": {"id": branche.id, "nom": branche.nom, "part": branche.part_trafic, "base": branche.base_definition_id, "tete": branche.head_definition_id},
                "principale": {"id": principale.id, "part": principale.part_trafic, "tete": tete_principale},
                "base": self._contenu(await definition(branche.base_definition_id)),
                "tete_branche": self._contenu(await definition(branche.head_definition_id)),
                "tete_principale": self._contenu(await definition(tete_principale)),
                "mon_brouillon": self._contenu(brouillon),
                "brouillon_de_la_principale": brouillon_principale is not None,
            }

    async def appliquer_la_fusion(
        self,
        organization_id: int,
        workflow_id: int,
        branch_id: int,
        *,
        graphe: dict[str, Any],
        reglages: dict[str, Any],
        variables: dict[str, Any],
        outils_epingles: dict[str, int] | None = None,
        attendu_source: int,
        attendu_cible: int,
    ) -> dict[str, Any]:
        """La fusion, d'un seul bloc : une version PUBLIÉE sur la principale (l'ancienne passe en archivée), la part de la branche
        reprise par la principale, la branche archivée. Les verrous sont pris AVANT les contrôles : si la branche ou la principale ont
        bougé depuis l'aperçu, rien n'est écrit (``perime``). Rend de quoi défaire."""
        async with self.async_session() as session:
            agent = await session.scalar(
                select(WorkflowModel)
                .where(WorkflowModel.id == workflow_id, WorkflowModel.organization_id == organization_id)
                .with_for_update()
            )
            if agent is None:
                raise ErreurDeBranche("Agent not found", "introuvable")
            principale = await self._principale(session, organization_id, workflow_id)
            verrouillees = (
                await session.scalars(
                    select(WorkflowBranchModel)
                    .where(
                        WorkflowBranchModel.workflow_id == workflow_id,
                        WorkflowBranchModel.organization_id == organization_id,
                        WorkflowBranchModel.id.in_([branch_id, principale.id]),
                    )
                    .order_by(WorkflowBranchModel.id)
                    .with_for_update()
                )
            ).all()
            par_id = {b.id: b for b in verrouillees}
            branche, principale = par_id.get(branch_id), par_id[principale.id]
            if branche is None or branche.est_principale or branche.statut != "active":
                raise ErreurDeBranche("Branch not found", "introuvable")
            tete_principale = principale.head_definition_id or agent.released_definition_id
            if branche.head_definition_id != attendu_source or tete_principale != attendu_cible:
                raise ErreurDeBranche("The branch or the main branch changed since the preview: read it again", "perime")
            brouillon_principale = await session.scalar(
                select(WorkflowDefinitionModel.id).where(
                    WorkflowDefinitionModel.workflow_id == workflow_id,
                    WorkflowDefinitionModel.status == "draft",
                    WorkflowDefinitionModel.branch_id.is_(None),
                )
            )
            if brouillon_principale is not None:
                raise ErreurDeBranche("The main branch has an unpublished draft: publish or discard it first", "brouillon_en_attente")

            # [.mark] Clôture, É36 : « Ce qui change » contre la version en ligne qu'elle remplace ; l'auteur est la personne qui a
            # ouvert la branche, la personne qui fusionne (la requête) est celle qui a ACCEPTÉ.
            from api.services.publication import resume_version

            en_ligne = await session.get(WorkflowDefinitionModel, agent.released_definition_id) if agent.released_definition_id else None
            resume = (
                resume_version.resumer(graphe, en_ligne.workflow_json, reglages, en_ligne.workflow_configurations) if en_ligne is not None else None
            )
            auteur_fusion = auteur_de_version.Auteur(
                auteur_de_version.PERSONNE if branche.cree_par else None, branche.cree_par, None, auteur_de_version.courant().user_id
            )
            await session.execute(
                update(WorkflowDefinitionModel)
                .where(WorkflowDefinitionModel.workflow_id == workflow_id, WorkflowDefinitionModel.status == "published")
                .values(status="archived", is_current=False)
            )
            version = WorkflowDefinitionModel(
                workflow_id=workflow_id,
                workflow_json=graphe,
                workflow_configurations=reglages,
                template_context_variables=variables,
                status="published",
                version_number=await self._next_version_number(session, workflow_id),
                is_current=True,
                published_at=datetime.now(UTC),
                branch_id=None,
                draft_owner_id=None,
                outils_epingles=pins.copie(outils_epingles),
                resume_changements=resume,
                **auteur_de_version.colonnes(auteur_fusion),
            )
            await pins.figer(session, version, organization_id, choix=outils_epingles, garder_les_blocs=True)  # SA-L3d (décision 21)
            session.add(version)
            await session.flush()
            defaire = {
                "version_creee": version.id,
                "ancienne_en_ligne": agent.released_definition_id,
                "ancienne_tete_principale": principale.head_definition_id,
                "part_de_la_branche": branche.part_trafic,
                "part_de_la_principale": principale.part_trafic,
            }
            agent.released_definition_id = version.id
            agent.workflow_definition = graphe
            agent.workflow_configurations = reglages
            agent.template_context_variables = variables
            principale.head_definition_id = None  # la principale suit de nouveau la version en ligne
            principale.part_trafic = principale.part_trafic + branche.part_trafic
            branche.part_trafic = 0
            branche.statut = "archived"
            await session.commit()
            await session.refresh(version)
            return {"version_id": version.id, "version_number": version.version_number, "defaire": defaire, "part_reprise": defaire["part_de_la_branche"]}

    async def defaire_la_fusion(self, organization_id: int, workflow_id: int, branch_id: int, defaire: dict[str, Any]) -> int:
        """Remet les choses comme avant la fusion, tant que la version qu'elle a créée est encore la version en ligne."""
        async with self.async_session() as session:
            agent = await session.scalar(
                select(WorkflowModel)
                .where(WorkflowModel.id == workflow_id, WorkflowModel.organization_id == organization_id)
                .with_for_update()
            )
            if agent is None:
                raise ErreurDeBranche("Agent not found", "introuvable")
            if agent.released_definition_id != defaire["version_creee"]:
                raise ErreurDeBranche("The agent was published again since this merge: it cannot be undone any more", "depassee")
            principale = await self._principale(session, organization_id, workflow_id)
            branche = await session.scalar(
                select(WorkflowBranchModel)
                .where(
                    WorkflowBranchModel.id == branch_id,
                    WorkflowBranchModel.workflow_id == workflow_id,
                    WorkflowBranchModel.organization_id == organization_id,
                )
                .with_for_update()
            )
            if branche is None:
                raise ErreurDeBranche("Branch not found", "introuvable")
            creee = await session.get(WorkflowDefinitionModel, defaire["version_creee"])
            ancienne = await session.get(WorkflowDefinitionModel, defaire["ancienne_en_ligne"]) if defaire.get("ancienne_en_ligne") else None
            creee.status = "archived"
            creee.is_current = False
            if ancienne is not None:
                ancienne.status = "published"
                ancienne.is_current = True
                agent.workflow_definition = ancienne.workflow_json
                agent.workflow_configurations = ancienne.workflow_configurations
                agent.template_context_variables = ancienne.template_context_variables
            agent.released_definition_id = defaire.get("ancienne_en_ligne")
            principale.head_definition_id = defaire.get("ancienne_tete_principale")
            principale.part_trafic = defaire["part_de_la_principale"]
            branche.part_trafic = defaire["part_de_la_branche"]
            branche.statut = "active"
            numero = creee.version_number  # lu avant le commit, qui expire l'objet
            await session.commit()
            return numero

    async def ecrire_le_brouillon_de_branche(
        self,
        organization_id: int,
        workflow_id: int,
        branch_id: int,
        user_id: int | None,
        *,
        graphe: dict[str, Any],
        reglages: dict[str, Any],
        variables: dict[str, Any],
        outils_epingles: dict[str, int] | None = None,
        attendu_base: int | None,
        nouvelle_base: int,
    ) -> WorkflowDefinitionModel:
        """La mise à jour depuis la principale : écrit le brouillon DE LA PERSONNE sur la branche (le crée au besoin) et avance la base
        de la branche. Refusé (``perime``) si la base a bougé depuis l'aperçu. Une autre personne garde son brouillon intact."""
        async with self.async_session() as session:
            await self._agent_de_l_organisation(session, organization_id, workflow_id)
            branche = await session.scalar(
                select(WorkflowBranchModel)
                .where(
                    WorkflowBranchModel.id == branch_id,
                    WorkflowBranchModel.workflow_id == workflow_id,
                    WorkflowBranchModel.organization_id == organization_id,
                )
                .with_for_update()
            )
            if branche is None or branche.est_principale or branche.statut != "active":
                raise ErreurDeBranche("Branch not found", "introuvable")
            if branche.base_definition_id != attendu_base:
                raise ErreurDeBranche("The branch changed since the preview: read it again", "perime")
            brouillon = await session.scalar(
                select(WorkflowDefinitionModel).where(
                    WorkflowDefinitionModel.workflow_id == workflow_id,
                    WorkflowDefinitionModel.status == "draft",
                    WorkflowDefinitionModel.branch_id == branch_id,
                    WorkflowDefinitionModel.draft_owner_id == user_id,
                )
            )
            if brouillon is None:
                brouillon = WorkflowDefinitionModel(
                    workflow_id=workflow_id,
                    status="draft",
                    version_number=await self._next_version_number(session, workflow_id),
                    is_current=False,
                    branch_id=branch_id,
                    draft_owner_id=user_id,
                    workflow_json=graphe,
                    workflow_configurations=reglages,
                    template_context_variables=variables,
                    outils_epingles=pins.copie(outils_epingles),
                    **auteur_de_version.colonnes(),  # [.mark] Clôture, É36 : qui a lancé la mise à jour depuis la principale
                )
                session.add(brouillon)
            else:
                brouillon.workflow_json = graphe
                brouillon.workflow_configurations = reglages
                brouillon.template_context_variables = variables
                brouillon.outils_epingles = pins.copie(outils_epingles)
            branche.base_definition_id = nouvelle_base
            await session.commit()
            await session.refresh(brouillon)
            return brouillon

    async def contenus_de_definitions(self, organization_id: int, workflow_id: int, ids: list[int]) -> dict[int, dict[str, Any]]:
        """Le contenu (graphe, réglages, variables) de ces versions, en UNE requête bornée à l'organisation. Pour comparer."""
        async with self.async_session() as session:
            lignes = (
                await session.scalars(
                    select(WorkflowDefinitionModel)
                    .join(WorkflowModel, WorkflowModel.id == WorkflowDefinitionModel.workflow_id)
                    .where(
                        WorkflowModel.organization_id == organization_id,
                        WorkflowDefinitionModel.workflow_id == workflow_id,
                        WorkflowDefinitionModel.id.in_(ids),
                        WorkflowDefinitionModel.status.in_(("published", "archived")),
                    )
                )
            ).all()
            return {d.id: self._contenu(d) for d in lignes}

    async def protection_de_la_principale(self, organization_id: int, workflow_id: int) -> tuple[bool, bool]:
        """(protégée en fait, protégée par la règle seule). La règle : agent client en ligne (voir ``protection_principale``). Le
        drapeau ne lève que ce que la règle n'impose pas."""
        from api.db import protection_principale

        async with self.async_session() as session:
            await self._agent_de_l_organisation(session, organization_id, workflow_id)
            principale = await self._principale(session, organization_id, workflow_id)
            en_fait = await protection_principale.est_protegee(session, workflow_id)
            return en_fait, en_fait and not principale.protegee and principale.protection_choisie is None

    async def regler_la_protection_de_la_principale(self, organization_id: int, workflow_id: int, protegee: bool | None) -> None:
        """Clôture, lot B (D5) : le réglage par agent. ``True`` / ``False`` : le choix de l'équipe ; ``None`` : retour à la règle par défaut."""
        async with self.async_session() as session:
            await self._agent_de_l_organisation(session, organization_id, workflow_id)
            principale = await self._principale(session, organization_id, workflow_id)
            principale.protection_choisie = protegee
            await session.commit()

    async def protection_reglee_de_la_principale(self, organization_id: int, workflow_id: int) -> bool | None:
        """Le choix de l'équipe pour cet agent (``None`` : la règle par défaut joue)."""
        async with self.async_session() as session:
            await self._agent_de_l_organisation(session, organization_id, workflow_id)
            principale = await self._principale(session, organization_id, workflow_id)
            return principale.protection_choisie

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

    async def agents_et_branches_pour_le_pilotage(self, organization_id: int) -> list[dict[str, Any]]:
        """Partie 3, L5b (page de pilotage d'un client) : les agents actifs de l'organisation avec leurs branches actives, la version
        en ligne de chacune et sa part de trafic. DEUX requêtes pour tous les agents (jamais une par agent), toutes deux filtrées par
        l'organisation. Un agent jamais publié a ``version_publiee = None`` ; la principale sert sa version épinglée, sinon la publiée."""
        async with self.async_session() as session:
            agents = (
                await session.execute(
                    select(WorkflowModel.id, WorkflowModel.name, WorkflowDefinitionModel.version_number)
                    .outerjoin(WorkflowDefinitionModel, WorkflowDefinitionModel.id == WorkflowModel.released_definition_id)
                    .where(WorkflowModel.organization_id == organization_id, WorkflowModel.status == "active")
                    .order_by(WorkflowModel.name, WorkflowModel.id)
                )
            ).all()
            branches = (
                await session.execute(
                    select(
                        WorkflowBranchModel.workflow_id,
                        WorkflowBranchModel.nom,
                        WorkflowBranchModel.est_principale,
                        WorkflowBranchModel.part_trafic,
                        WorkflowDefinitionModel.version_number,
                    )
                    .outerjoin(WorkflowDefinitionModel, WorkflowDefinitionModel.id == WorkflowBranchModel.head_definition_id)
                    .where(WorkflowBranchModel.organization_id == organization_id, WorkflowBranchModel.statut == "active")
                    .order_by(WorkflowBranchModel.est_principale.desc(), WorkflowBranchModel.id)
                )
            ).all()
        par_agent: dict[int, list[dict[str, Any]]] = {}
        for wf, nom, principale, part, version in branches:
            par_agent.setdefault(wf, []).append({"nom": nom, "principale": bool(principale), "part": int(part or 0), "version": version})
        resultat = []
        for wf, nom, publiee in agents:
            lignes = par_agent.get(wf, [])
            resultat.append({"id": wf, "nom": nom, "version_publiee": publiee, "branches": lignes})
        return resultat
