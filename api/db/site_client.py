"""[.mark] Le widget public : sites, chemins par agent, usage mensuel (``models_site``). Builder partie 2, U10.

Chaque lecture ou écriture d'un site est bornée à l'organisation. Le plafond par mois (D177) est réservé en UNE requête
atomique ``INSERT ... ON CONFLICT ... DO UPDATE ... WHERE`` : deux visiteurs qui se disputent la dernière place
n'en passent jamais deux.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import Text, cast, delete, select, text, update
from sqlalchemy.exc import IntegrityError

from api.db.base_client import BaseDBClient
from api.db.models import EmbedTokenModel, WorkflowModel, WorkflowRunModel
from api.db.models_site import (
    MarkEmbedCheminModel,
    MarkEmbedSiteModel,
    MarkEmbedUsageMensuelModel,
)


class CheminDejaPris(Exception):
    def __init__(self, chemin: str):
        super().__init__(chemin)
        self.chemin = chemin


def mois_de(instant: datetime | None = None) -> str:
    return (instant or datetime.now(UTC)).strftime("%Y-%m")


_RESERVER = text(
    """
    INSERT INTO mark_embed_usage_mensuel (embed_token_id, mois, conversations, secondes)
    VALUES (:t, :m, 1, 0)
    ON CONFLICT (embed_token_id, mois) DO UPDATE
       SET conversations = mark_embed_usage_mensuel.conversations + 1
     WHERE mark_embed_usage_mensuel.conversations < :pc
       AND mark_embed_usage_mensuel.secondes < :ps
    RETURNING conversations
    """
)


class SiteClient(BaseDBClient):
    # ------------------------------------------------------------------ sites
    async def creer_site(
        self, organization_id: int, nom: str, allowed_domains: list[str] | None
    ) -> MarkEmbedSiteModel:
        async with self.async_session() as session:
            site = MarkEmbedSiteModel(
                organization_id=organization_id,
                cle=f"site_{secrets.token_urlsafe(24)}",
                nom=nom,
                allowed_domains=allowed_domains,
            )
            session.add(site)
            await session.commit()
            await session.refresh(site)
            return site

    async def lire_site_par_cle(self, cle: str) -> MarkEmbedSiteModel | None:
        async with self.async_session() as session:
            r = await session.execute(select(MarkEmbedSiteModel).where(MarkEmbedSiteModel.cle == cle))
            return r.scalar_one_or_none()

    async def lire_site(self, site_id: int, organization_id: int) -> MarkEmbedSiteModel | None:
        async with self.async_session() as session:
            r = await session.execute(
                select(MarkEmbedSiteModel).where(
                    MarkEmbedSiteModel.id == site_id,
                    MarkEmbedSiteModel.organization_id == organization_id,
                )
            )
            return r.scalar_one_or_none()

    async def lister_sites(self, organization_id: int) -> list[MarkEmbedSiteModel]:
        async with self.async_session() as session:
            r = await session.execute(
                select(MarkEmbedSiteModel)
                .where(MarkEmbedSiteModel.organization_id == organization_id)
                .order_by(MarkEmbedSiteModel.id)
            )
            return list(r.scalars().all())

    async def regler_site(
        self,
        site_id: int,
        organization_id: int,
        *,
        nom: str | None = None,
        allowed_domains: list[str] | None = None,
    ) -> MarkEmbedSiteModel | None:
        async with self.async_session() as session:
            r = await session.execute(
                select(MarkEmbedSiteModel).where(
                    MarkEmbedSiteModel.id == site_id,
                    MarkEmbedSiteModel.organization_id == organization_id,
                )
            )
            site = r.scalar_one_or_none()
            if site is None:
                return None
            if nom is not None:
                site.nom = nom
            if allowed_domains is not None:
                site.allowed_domains = allowed_domains
            await session.commit()
            await session.refresh(site)
            return site

    async def regenerer_cle_du_site(self, site_id: int, organization_id: int) -> MarkEmbedSiteModel | None:
        """Pose une nouvelle clé au site : l'ancien script cesse de marcher, la page doit recevoir le nouveau."""
        async with self.async_session() as session:
            site = (
                await session.execute(
                    select(MarkEmbedSiteModel).where(
                        MarkEmbedSiteModel.id == site_id, MarkEmbedSiteModel.organization_id == organization_id
                    )
                )
            ).scalar_one_or_none()
            if site is None:
                return None
            site.cle = f"site_{secrets.token_urlsafe(24)}"
            await session.commit()
            await session.refresh(site)
            return site

    async def noter_chargement(self, site_id: int) -> None:
        async with self.async_session() as session:
            await session.execute(
                update(MarkEmbedSiteModel)
                .where(MarkEmbedSiteModel.id == site_id)
                .values(dernier_chargement=datetime.now(UTC))
            )
            await session.commit()

    # ------------------------------------------------------------------ chemins
    async def lire_chemins_du_site(self, site_id: int) -> list[MarkEmbedCheminModel]:
        async with self.async_session() as session:
            r = await session.execute(
                select(MarkEmbedCheminModel)
                .where(MarkEmbedCheminModel.site_id == site_id)
                .order_by(MarkEmbedCheminModel.id)
            )
            return list(r.scalars().all())

    async def lire_chemins_du_jeton(self, embed_token_id: int) -> list[MarkEmbedCheminModel]:
        async with self.async_session() as session:
            r = await session.execute(
                select(MarkEmbedCheminModel)
                .where(MarkEmbedCheminModel.embed_token_id == embed_token_id)
                .order_by(MarkEmbedCheminModel.id)
            )
            return list(r.scalars().all())

    async def poser_emplacement(
        self, organization_id: int, embed_token_id: int, site_id: int | None, chemins: list[str]
    ) -> None:
        """Pose (remplace) l'emplacement d'un jeton : un site et une liste de chemins déjà normalisés.

        Tout ou rien : un chemin déjà servi par un autre agent du site lève ``CheminDejaPris`` et rien ne change."""
        async with self.async_session() as session:
            jeton = (
                await session.execute(
                    select(EmbedTokenModel).where(
                        EmbedTokenModel.id == embed_token_id,
                        EmbedTokenModel.organization_id == organization_id,
                    )
                )
            ).scalar_one_or_none()
            if jeton is None:
                raise LookupError("embed token not found")
            if site_id is not None:
                site = (
                    await session.execute(
                        select(MarkEmbedSiteModel).where(
                            MarkEmbedSiteModel.id == site_id,
                            MarkEmbedSiteModel.organization_id == organization_id,
                        )
                    )
                ).scalar_one_or_none()
                if site is None:
                    raise LookupError("site not found")
            courant = None
            try:
                # Un point de sauvegarde : un chemin pris annule TOUT le remplacement (tout ou rien), sans toucher au reste.
                async with session.begin_nested():
                    await session.execute(
                        delete(MarkEmbedCheminModel).where(MarkEmbedCheminModel.embed_token_id == embed_token_id)
                    )
                    jeton.site_id = site_id
                    if site_id is not None:
                        for courant in dict.fromkeys(chemins):
                            session.add(
                                MarkEmbedCheminModel(site_id=site_id, embed_token_id=embed_token_id, chemin=courant)
                            )
                            await session.flush()
            except IntegrityError:
                raise CheminDejaPris(courant or "") from None
            await session.commit()

    # ------------------------------------------------------------------ usage mensuel (D177, D185)
    async def reserver_une_conversation(
        self, embed_token_id: int, mois: str, plafond_conversations: int, plafond_secondes: int
    ) -> bool:
        async with self.async_session() as session:
            r = await session.execute(
                _RESERVER,
                {"t": embed_token_id, "m": mois, "pc": plafond_conversations, "ps": plafond_secondes},
            )
            reserve = r.scalar_one_or_none() is not None
            await session.commit()
            return reserve

    async def rendre_une_conversation(self, embed_token_id: int, mois: str) -> None:
        async with self.async_session() as session:
            await session.execute(
                text(
                    "UPDATE mark_embed_usage_mensuel SET conversations = GREATEST(conversations - 1, 0) "
                    "WHERE embed_token_id = :t AND mois = :m"
                ),
                {"t": embed_token_id, "m": mois},
            )
            await session.commit()

    async def ajouter_secondes(self, embed_token_id: int, mois: str, secondes: int) -> None:
        if secondes <= 0:
            return
        async with self.async_session() as session:
            await session.execute(
                text(
                    "INSERT INTO mark_embed_usage_mensuel (embed_token_id, mois, conversations, secondes) "
                    "VALUES (:t, :m, 0, :s) ON CONFLICT (embed_token_id, mois) DO UPDATE "
                    "SET secondes = mark_embed_usage_mensuel.secondes + :s"
                ),
                {"t": embed_token_id, "m": mois, "s": int(secondes)},
            )
            await session.commit()

    async def lire_usage_mensuel(self, embed_token_id: int, mois: str) -> MarkEmbedUsageMensuelModel | None:
        async with self.async_session() as session:
            r = await session.execute(
                select(MarkEmbedUsageMensuelModel).where(
                    MarkEmbedUsageMensuelModel.embed_token_id == embed_token_id,
                    MarkEmbedUsageMensuelModel.mois == mois,
                )
            )
            return r.scalar_one_or_none()

    async def lire_jetons(self, ids: list[int]) -> dict[int, EmbedTokenModel]:
        if not ids:
            return {}
        async with self.async_session() as session:
            r = await session.execute(select(EmbedTokenModel).where(EmbedTokenModel.id.in_(ids)))
            return {j.id: j for j in r.scalars().all()}

    async def lire_emplacements(self, organization_id: int, workflow_ids: list[int]) -> dict[int, dict]:
        """Pour chaque agent : son jeton, son site, ses chemins, l'état du widget. Toujours sous l'organisation."""
        if not workflow_ids:
            return {}
        async with self.async_session() as session:
            jetons = (
                await session.execute(
                    select(EmbedTokenModel)
                    .where(
                        EmbedTokenModel.organization_id == organization_id,
                        EmbedTokenModel.workflow_id.in_(workflow_ids),
                    )
                    .order_by(EmbedTokenModel.id)
                )
            ).scalars().all()
            if not jetons:
                return {}
            site_ids = {j.site_id for j in jetons if j.site_id}
            sites = {}
            if site_ids:
                sites = {
                    s.id: s
                    for s in (
                        await session.execute(
                            select(MarkEmbedSiteModel).where(
                                MarkEmbedSiteModel.id.in_(site_ids),
                                MarkEmbedSiteModel.organization_id == organization_id,
                            )
                        )
                    ).scalars().all()
                }
            chemins = (
                await session.execute(
                    select(MarkEmbedCheminModel)
                    .where(MarkEmbedCheminModel.embed_token_id.in_([j.id for j in jetons]))
                    .order_by(MarkEmbedCheminModel.id)
                )
            ).scalars().all()
        par_jeton: dict[int, list[str]] = {}
        for c in chemins:
            par_jeton.setdefault(c.embed_token_id, []).append(c.chemin)
        sortie: dict[int, dict] = {}
        for j in jetons:
            if j.workflow_id in sortie and not j.is_active:
                continue
            site = sites.get(j.site_id) if j.site_id else None
            dernier = site.dernier_chargement.isoformat() if site and site.dernier_chargement else None
            sortie[j.workflow_id] = {
                "site_id": site.id if site else None,
                "site_cle": site.cle if site else None,
                "chemins": par_jeton.get(j.id, []),
                "widget_actif": bool(j.is_active),
                "dernier_chargement": dernier,
            }
        return sortie

    async def regler_jeton_mark(
        self, embed_token_id: int, organization_id: int, *, reglages_mark: dict | None = None,
        allowed_domains: list[str] | None = None,
        expires_at: datetime | None = None,
        sans_expiration: bool = False,
        is_active: bool | None = None,
    ) -> EmbedTokenModel | None:
        """Écrit les réglages posés par .mark d'un jeton (domaines, fin de validité, affichage), sous l'organisation."""
        async with self.async_session() as session:
            jeton = (
                await session.execute(
                    select(EmbedTokenModel).where(
                        EmbedTokenModel.id == embed_token_id,
                        EmbedTokenModel.organization_id == organization_id,
                    )
                )
            ).scalar_one_or_none()
            if jeton is None:
                return None
            if reglages_mark is not None:
                jeton.reglages_mark = reglages_mark
            if allowed_domains is not None:
                jeton.allowed_domains = allowed_domains
            if sans_expiration:
                jeton.expires_at = None
            elif expires_at is not None:
                jeton.expires_at = expires_at
            if is_active is not None:
                jeton.is_active = is_active
            jeton.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(jeton)
            return jeton

    # ------------------------------------------------------------------ l'avis, une seule fois (revue serveur, mineur 3)
    async def reserver_avis(self, run_id: int, organization_id: int) -> bool:
        """Prend, sous verrou de ligne, la place de l'avis de cette conversation : ``False`` si un avis y est déjà (ou en
        cours d'écriture). Deux envois simultanés : un seul passe. Le run est lu AVEC l'organisation."""
        async with self.async_session() as session:
            run = (
                await session.execute(
                    select(WorkflowRunModel)
                    .join(WorkflowModel, WorkflowRunModel.workflow_id == WorkflowModel.id)
                    .where(WorkflowRunModel.id == run_id, WorkflowModel.organization_id == organization_id)
                    .with_for_update(of=WorkflowRunModel)
                )
            ).scalars().first()
            if run is None:
                return False
            annotations = dict(run.annotations or {})
            embed = dict(annotations.get("embed") or {})
            from api.services.site_mark.conversations import reservation_expiree

            existant = embed.get("avis")
            if isinstance(existant, dict) and not reservation_expiree(existant):
                return False
            embed["avis"] = {"en_cours": True, "le": datetime.now(UTC).isoformat()}
            run.annotations = {**annotations, "embed": embed}
            await session.commit()
            return True

    async def rendre_avis(self, run_id: int, organization_id: int) -> None:
        """Libère la place prise par ``reserver_avis`` quand l'écriture a échoué (le visiteur peut renvoyer)."""
        async with self.async_session() as session:
            run = (
                await session.execute(
                    select(WorkflowRunModel)
                    .join(WorkflowModel, WorkflowRunModel.workflow_id == WorkflowModel.id)
                    .where(WorkflowRunModel.id == run_id, WorkflowModel.organization_id == organization_id)
                    .with_for_update(of=WorkflowRunModel)
                )
            ).scalars().first()
            if run is None:
                return
            annotations = dict(run.annotations or {})
            embed = dict(annotations.get("embed") or {})
            if isinstance(embed.get("avis"), dict) and embed["avis"].get("en_cours") is True:
                embed.pop("avis")
                run.annotations = {**annotations, "embed": embed}
                await session.commit()

    async def reduire_avis_gardes_en_entier(self, avant: datetime, limite: int = 500) -> int:
        """Réduit à l'avis sans coordonnées ni texte libre tout avis gardé en entier sur un run depuis avant ``avant``
        (revue de contrôle, point 8). Rend le nombre d'avis réduits ; la purge de nuit le rejoue jusqu'à zéro."""
        from api.services.site_mark.conversations import avis_garde_trop_longtemps, avis_sans_donnees_personnelles

        reduits = 0
        async with self.async_session() as session:
            runs = (
                await session.execute(
                    select(WorkflowRunModel)
                    .where(cast(WorkflowRunModel.annotations, Text).like('%"garde_le"%'))
                    .limit(limite)
                    .with_for_update()
                )
            ).scalars().all()
            for run in runs:
                annotations = dict(run.annotations or {})
                embed = dict(annotations.get("embed") or {})
                if avis_garde_trop_longtemps(embed.get("avis"), avant):
                    embed["avis"] = avis_sans_donnees_personnelles(embed["avis"])
                    run.annotations = {**annotations, "embed": embed}
                    reduits += 1
            await session.commit()
        return reduits

    # ------------------------------------------------------------------ événements anonymes (lot S3)
    async def compter_evenement(self, embed_token_id: int, jour, evenement: str, plafond_du_jour: int) -> bool:
        """Ajoute 1 au compteur ``affiche`` ou ``ouvert`` du jour. Refuse (``False``) au-delà du plafond du jour :
        un script qui boucle ne gonfle pas les chiffres sans fin. Aucune donnée sur le visiteur."""
        if evenement not in ("affiche", "ouvert"):
            raise ValueError(evenement)
        async with self.async_session() as session:
            r = await session.execute(
                text(
                    f"INSERT INTO mark_embed_evenements_jour (embed_token_id, jour, {evenement}) "
                    "VALUES (:t, :j, 1) ON CONFLICT (embed_token_id, jour) DO UPDATE "
                    f"SET {evenement} = mark_embed_evenements_jour.{evenement} + 1 "
                    f"WHERE mark_embed_evenements_jour.{evenement} < :p RETURNING {evenement}"
                ),
                {"t": embed_token_id, "j": jour, "p": plafond_du_jour},
            )
            compte = r.scalar_one_or_none() is not None
            await session.commit()
            return compte

    async def lire_evenements(self, organization_id: int, du, au) -> list[dict]:
        """Les compteurs des agents de CETTE organisation entre deux jours inclus : jamais ceux d'une autre."""
        async with self.async_session() as session:
            r = await session.execute(
                text(
                    "SELECT e.embed_token_id, t.workflow_id, e.jour, e.affiche, e.ouvert "
                    "FROM mark_embed_evenements_jour e JOIN embed_tokens t ON t.id = e.embed_token_id "
                    "WHERE t.organization_id = :o AND e.jour BETWEEN :du AND :au "
                    "ORDER BY e.jour, t.workflow_id"
                ),
                {"o": organization_id, "du": du, "au": au},
            )
            return [dict(ligne._mapping) for ligne in r.all()]

    # ------------------------------------------------------------------ conservation (lot S3)
    async def purger_sessions_du_widget(self, avant: datetime) -> int:
        """Efface les sessions de widget (adresse IP, navigateur) créées avant ``avant``. Le run, lui, suit la
        conservation des appels."""
        async with self.async_session() as session:
            r = await session.execute(
                text("DELETE FROM embed_sessions WHERE created_at < :a"), {"a": avant}
            )
            await session.commit()
            return r.rowcount or 0
