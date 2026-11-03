"""[.mark] Le builder en tables : lectures et écritures des conversations et de leurs événements (``models_builder``).

Chaque lecture et chaque écriture d'une conversation est bornée à l'organisation (R0). Les événements se lisent par
l'identifiant croissant : c'est l'ordre du flux rejoué à l'écran.
"""

from __future__ import annotations

from typing import Any

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update

from api.db.base_client import BaseDBClient
from api.db.models_builder import MarkBuilderConversationModel, MarkBuilderEvenementModel, MarkModificationModel

CHAMPS_MODIFIABLES = frozenset(
    {"titre", "etat", "historique", "jetons", "cout", "jauge", "changements", "workflow_id", "demarrage"}
    | {"genre", "delegation_id", "usage", "tache", "modele", "resultat", "sous_agents_actifs"}
    | {"session_externe", "auteur"}
)
MODIFICATIONS_GARDEES_JOURS = 3


class BuilderFilClient(BaseDBClient):
    async def creer_fil(
        self,
        organization_id: int,
        user_id: int | None,
        workflow_id: int | None,
        titre: str,
        demarrage: str | None = None,
        parent_id: int | None = None,
        **sous_agent: Any,
    ) -> MarkBuilderConversationModel:
        async with self.async_session() as session:
            fil = MarkBuilderConversationModel(
                organization_id=organization_id,
                user_id=user_id,
                workflow_id=workflow_id,
                parent_id=parent_id,
                titre=titre[:200],
                demarrage=demarrage,
                historique={},
                **sous_agent,
            )
            session.add(fil)
            await session.commit()
            await session.refresh(fil)
            return fil

    async def lire_fil(self, organization_id: int, fil_id: int) -> MarkBuilderConversationModel | None:
        async with self.async_session() as session:
            resultat = await session.execute(
                select(MarkBuilderConversationModel)
                .where(
                    MarkBuilderConversationModel.id == fil_id,
                    MarkBuilderConversationModel.organization_id == organization_id,
                )
                .execution_options(populate_existing=True)
            )
            return resultat.scalar_one_or_none()

    async def lister_fils(
        self, organization_id: int, workflow_id: int | None = None, limite: int = 100
    ) -> list[MarkBuilderConversationModel]:
        async with self.async_session() as session:
            requete = select(MarkBuilderConversationModel).where(
                MarkBuilderConversationModel.organization_id == organization_id,
                MarkBuilderConversationModel.parent_id.is_(None),
            )
            if workflow_id is not None:
                requete = requete.where(MarkBuilderConversationModel.workflow_id == workflow_id)
            requete = (
                requete.order_by(MarkBuilderConversationModel.modifie_le.desc(), MarkBuilderConversationModel.id.desc())
                .limit(limite)
                .execution_options(populate_existing=True)
            )
            return list((await session.execute(requete)).scalars().all())

    async def modifier_fil(self, organization_id: int, fil_id: int, **champs: Any) -> None:
        inconnus = set(champs) - CHAMPS_MODIFIABLES
        if inconnus:
            raise ValueError(f"Unknown conversation field(s): {sorted(inconnus)}")
        async with self.async_session() as session:
            await session.execute(
                update(MarkBuilderConversationModel)
                .where(
                    MarkBuilderConversationModel.id == fil_id,
                    MarkBuilderConversationModel.organization_id == organization_id,
                )
                .values(**champs)
            )
            await session.commit()

    async def somme_des_couts_depuis(self, depuis: datetime) -> float:
        """K7 : la dépense du builder depuis ``depuis``, toutes organisations (le coût du builder est celui de .mark). Les conversations
        de premier niveau seulement : un sous-agent est déjà compté dans son parent. Une conversation compte en entier dès qu'elle a
        bougé dans la période (on surestime plutôt que de laisser passer un plafond)."""
        async with self.async_session() as session:
            total = (
                await session.execute(
                    select(func.coalesce(func.sum(MarkBuilderConversationModel.cout), 0.0)).where(
                        MarkBuilderConversationModel.parent_id.is_(None),
                        MarkBuilderConversationModel.modifie_le >= depuis,
                    )
                )
            ).scalar_one()
            return float(total or 0.0)

    async def supprimer_fil(self, organization_id: int, fil_id: int) -> bool:
        """Supprime la conversation et, par cascade de la base, ses événements et ses sous-agents. Bornée à l'organisation (R0)."""
        async with self.async_session() as session:
            resultat = await session.execute(
                delete(MarkBuilderConversationModel)
                .where(
                    MarkBuilderConversationModel.id == fil_id,
                    MarkBuilderConversationModel.organization_id == organization_id,
                )
                .returning(MarkBuilderConversationModel.id)
            )
            supprimee = resultat.first() is not None
            await session.commit()
            return supprimee

    async def ajouter_evenement(self, fil_id: int, genre: str, donnees: dict[str, Any]) -> int:
        async with self.async_session() as session:
            ligne = MarkBuilderEvenementModel(conversation_id=fil_id, type=genre[:40], donnees=donnees)
            session.add(ligne)
            await session.commit()
            await session.refresh(ligne)
            return int(ligne.id)

    async def evenements_apres(
        self, fil_id: int, apres: int = 0, limite: int = 500
    ) -> list[MarkBuilderEvenementModel]:
        async with self.async_session() as session:
            resultat = await session.execute(
                select(MarkBuilderEvenementModel)
                .where(MarkBuilderEvenementModel.conversation_id == fil_id, MarkBuilderEvenementModel.id > apres)
                .order_by(MarkBuilderEvenementModel.id)
                .limit(limite)
            )
            return list(resultat.scalars().all())

    async def arreter_les_fils_en_cours(self) -> list[tuple[int, int]]:
        """Au démarrage du serveur : toute conversation restée « en_cours » n'a plus de tâche derrière elle. Elle passe à
        « arretee » (« Reprendre » la relance depuis le disque). Rend les (organisation, identifiant) touchés."""
        async with self.async_session() as session:
            resultat = await session.execute(
                update(MarkBuilderConversationModel)
                .where(MarkBuilderConversationModel.etat == "en_cours")
                .values(etat="arretee")
                .returning(MarkBuilderConversationModel.organization_id, MarkBuilderConversationModel.id)
            )
            touches = [(int(o), int(i)) for o, i in resultat.all()]
            await session.commit()
            return touches

    async def lister_les_enfants(self, organization_id: int, parent_id: int) -> list[MarkBuilderConversationModel]:
        """Les sous-agents d'une conversation, dans l'ordre de création."""
        async with self.async_session() as session:
            resultat = await session.execute(
                select(MarkBuilderConversationModel)
                .where(
                    MarkBuilderConversationModel.organization_id == organization_id,
                    MarkBuilderConversationModel.parent_id == parent_id,
                )
                .order_by(MarkBuilderConversationModel.id)
                .execution_options(populate_existing=True)
            )
            return list(resultat.scalars().all())

    # --- U12 : le miroir des conversations Claude Code -------------------------------------------------------------

    async def fil_de_la_session(self, organization_id: int, session_externe: str) -> MarkBuilderConversationModel | None:
        async with self.async_session() as session:
            resultat = await session.execute(
                select(MarkBuilderConversationModel)
                .where(
                    MarkBuilderConversationModel.organization_id == organization_id,
                    MarkBuilderConversationModel.genre == "claude_code",
                    MarkBuilderConversationModel.session_externe == session_externe,
                )
                .order_by(MarkBuilderConversationModel.id.desc())
                .limit(1)
                .execution_options(populate_existing=True)
            )
            return resultat.scalar_one_or_none()

    # --- U12 : la mise à jour en direct ----------------------------------------------------------------------------

    async def ajouter_modification(
        self, organization_id: int, objet: str, action: str, source: str, auteur: str | None
    ) -> int:
        async with self.async_session() as session:
            ligne = MarkModificationModel(
                organization_id=organization_id, objet=objet[:80], action=action[:80], source=source[:20], auteur=(auteur or None)
            )
            session.add(ligne)
            await session.flush()
            identifiant = int(ligne.id)
            if identifiant % 50 == 0:  # l'élagage se fait de temps en temps, jamais à chaque écriture
                await session.execute(
                    delete(MarkModificationModel).where(
                        MarkModificationModel.organization_id == organization_id,
                        MarkModificationModel.cree_le < datetime.now(UTC) - timedelta(days=MODIFICATIONS_GARDEES_JOURS),
                    )
                )
            await session.commit()
            return identifiant

    async def modifications_apres(
        self, organization_id: int, apres: int = 0, objet: str | None = None, limite: int = 200
    ) -> list[MarkModificationModel]:
        async with self.async_session() as session:
            requete = select(MarkModificationModel).where(
                MarkModificationModel.organization_id == organization_id, MarkModificationModel.id > apres
            )
            if objet is not None:
                requete = requete.where(MarkModificationModel.objet == objet)
            resultat = await session.execute(requete.order_by(MarkModificationModel.id).limit(limite))
            return list(resultat.scalars().all())

    async def derniere_modification(self, organization_id: int) -> int:
        async with self.async_session() as session:
            resultat = await session.execute(
                select(MarkModificationModel.id)
                .where(MarkModificationModel.organization_id == organization_id)
                .order_by(MarkModificationModel.id.desc())
                .limit(1)
            )
            return int(resultat.scalar_one_or_none() or 0)
