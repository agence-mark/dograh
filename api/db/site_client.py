"""[.mark] Le widget public : sites, chemins par agent, usage mensuel (``models_site``). Builder partie 2, U10.

Chaque lecture ou écriture d'un site est bornée à l'organisation. Le plafond par mois (D177) est réservé en UNE requête
atomique ``INSERT ... ON CONFLICT ... DO UPDATE ... WHERE`` : deux visiteurs qui se disputent la dernière place
n'en passent jamais deux.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError

from api.db.base_client import BaseDBClient
from api.db.models import EmbedTokenModel
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
    ) -> EmbedTokenModel | None:
        """Écrit les réglages posés par .mark d'un jeton (et ses domaines), sous l'organisation."""
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
            jeton.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(jeton)
            return jeton
