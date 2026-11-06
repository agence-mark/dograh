"""[.mark] Partie 3, sous-lot 9 (SE-5) : la couche de données de l'installation d'un nouveau client.

Chaque lecture et chaque écriture filtre par organisation DANS la requête. Les changements d'état d'une étape sont des
``UPDATE ... WHERE etat IN (...) RETURNING`` atomiques : deux requêtes simultanées (un double clic) ne prennent jamais la
même étape ; une seule s'exécute, l'autre lit l'état laissé par la première. Les lectures rendent des dictionnaires (jamais
un objet lié à une session fermée).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert

from api.db.base_client import BaseDBClient
from api.db.models_installation import EtapeInstallationModel, InstallationClientModel

NOMBRE_D_ETAPES = 9
ETATS_CLOS = ("faite", "passee")


class InstallationDejaOuverte(Exception):
    """Le client a déjà une installation ouverte (contrainte en base)."""


def _etape(e: EtapeInstallationModel) -> dict[str, Any]:
    return {
        "numero": int(e.numero),
        "etat": e.etat,
        "par": e.par,
        "le": e.le,
        "debut": e.debut,
        "derniere_erreur": e.derniere_erreur,
        "resultat": dict(e.resultat or {}),
    }


def _installation(i: InstallationClientModel, etapes: list[EtapeInstallationModel]) -> dict[str, Any]:
    return {
        "id": i.id,
        "organization_id": i.organization_id,
        "nom": i.nom,
        "etat": i.etat,
        "cree_par": i.cree_par,
        "cree_le": i.cree_le,
        "terminee_le": i.terminee_le,
        "etapes": [_etape(e) for e in sorted(etapes, key=lambda e: e.numero)],
    }


class InstallationClientClient(BaseDBClient):
    async def creer_installation(self, organization_id: int, nom: str, user_id: int | None) -> dict[str, Any]:
        """L'installation et ses neuf étapes ; l'étape 1 (l'organisation) est faite par construction."""
        maintenant = datetime.now(UTC)
        async with self.async_session() as session:
            # La contrainte en base tranche (deux requêtes simultanées) : la seconde n'insère rien.
            installation_id = await session.scalar(
                insert(InstallationClientModel)
                .values(organization_id=organization_id, nom=nom, etat="ouverte", cree_par=user_id)
                .on_conflict_do_nothing(index_elements=["organization_id"], index_where=text("etat = 'ouverte'"))
                .returning(InstallationClientModel.id)
            )
            if installation_id is None:
                await session.commit()
                raise InstallationDejaOuverte(str(organization_id))
            for numero in range(1, NOMBRE_D_ETAPES + 1):
                fait = numero == 1
                session.add(
                    EtapeInstallationModel(
                        installation_id=installation_id,
                        organization_id=organization_id,
                        numero=numero,
                        etat="faite" if fait else "a_faire",
                        par=user_id if fait else None,
                        le=maintenant if fait else None,
                        resultat={"organisation_id": organization_id} if fait else None,
                    )
                )
            await session.commit()
        return await self.installation_ouverte(organization_id, installation_id=installation_id)  # type: ignore[return-value]

    async def installation_ouverte(self, organization_id: int, *, installation_id: int | None = None) -> dict[str, Any] | None:
        """L'installation ouverte de l'organisation (ou celle désignée, ouverte ou non, mais de CETTE organisation)."""
        async with self.async_session() as session:
            requete = select(InstallationClientModel).where(InstallationClientModel.organization_id == organization_id)
            if installation_id is None:
                requete = requete.where(InstallationClientModel.etat == "ouverte")
            else:
                requete = requete.where(InstallationClientModel.id == installation_id)
            installation = await session.scalar(requete)
            if installation is None:
                return None
            etapes = (
                await session.scalars(
                    select(EtapeInstallationModel).where(
                        EtapeInstallationModel.organization_id == organization_id,
                        EtapeInstallationModel.installation_id == installation.id,
                    )
                )
            ).all()
            return _installation(installation, list(etapes))

    async def installations_ouvertes(self, organisations: list[int]) -> list[dict[str, Any]]:
        """Les installations ouvertes de ces organisations (filtre dans la requête), sans leurs étapes, plus récentes d'abord."""
        if not organisations:
            return []
        async with self.async_session() as session:
            lignes = (
                await session.scalars(
                    select(InstallationClientModel)
                    .where(
                        InstallationClientModel.organization_id.in_(organisations),
                        InstallationClientModel.etat == "ouverte",
                    )
                    .order_by(InstallationClientModel.cree_le.desc())
                    .limit(200)
                )
            ).all()
            ids = [l.id for l in lignes]
            etapes = (
                await session.scalars(
                    select(EtapeInstallationModel).where(
                        EtapeInstallationModel.organization_id.in_(organisations),
                        EtapeInstallationModel.installation_id.in_(ids or [-1]),
                    )
                )
            ).all()
            par_installation: dict[int, list[EtapeInstallationModel]] = {}
            for e in etapes:
                par_installation.setdefault(e.installation_id, []).append(e)
            return [_installation(l, par_installation.get(l.id, [])) for l in lignes]

    async def prendre_etape(
        self, organization_id: int, installation_id: int, numero: int, user_id: int | None, *, bail_s: int
    ) -> bool:
        """Passe l'étape à « en cours » si elle est à faire, en erreur, ou en cours depuis plus que le bail (coupure), ET si toutes
        les étapes d'avant sont faites ou passées. Atomique : ``True`` pour une seule des requêtes simultanées."""
        maintenant = datetime.now(UTC)
        precedentes_ouvertes = (
            select(EtapeInstallationModel.id)
            .where(
                EtapeInstallationModel.installation_id == installation_id,
                EtapeInstallationModel.organization_id == organization_id,
                EtapeInstallationModel.numero < numero,
                EtapeInstallationModel.etat.notin_(ETATS_CLOS),
            )
            .exists()
        )
        installation_ouverte = (
            select(InstallationClientModel.id)
            .where(
                InstallationClientModel.id == installation_id,
                InstallationClientModel.organization_id == organization_id,
                InstallationClientModel.etat == "ouverte",
            )
            .exists()
        )
        async with self.async_session() as session:
            pris = await session.scalar(
                update(EtapeInstallationModel)
                .where(
                    EtapeInstallationModel.installation_id == installation_id,
                    EtapeInstallationModel.organization_id == organization_id,
                    EtapeInstallationModel.numero == numero,
                    or_(
                        EtapeInstallationModel.etat.in_(("a_faire", "erreur")),
                        and_(
                            EtapeInstallationModel.etat == "en_cours",
                            EtapeInstallationModel.debut < maintenant - timedelta(seconds=bail_s),
                        ),
                    ),
                    ~precedentes_ouvertes,
                    installation_ouverte,
                )
                .values(etat="en_cours", par=user_id, debut=maintenant)
                .returning(EtapeInstallationModel.id)
            )
            await session.commit()
            return pris is not None

    async def finir_etape(
        self,
        organization_id: int,
        installation_id: int,
        numero: int,
        *,
        etat: str,
        user_id: int | None,
        erreur: str | None = None,
        resultat: dict[str, Any] | None = None,
    ) -> None:
        """Ferme une étape prise (« faite » ou « erreur »). Une étape qui n'est plus « en cours » n'est pas touchée."""
        valeurs: dict[str, Any] = {"etat": etat, "par": user_id, "le": datetime.now(UTC), "derniere_erreur": (erreur or None)}
        if resultat is not None:
            valeurs["resultat"] = resultat
        async with self.async_session() as session:
            await session.execute(
                update(EtapeInstallationModel)
                .where(
                    EtapeInstallationModel.installation_id == installation_id,
                    EtapeInstallationModel.organization_id == organization_id,
                    EtapeInstallationModel.numero == numero,
                    EtapeInstallationModel.etat == "en_cours",
                )
                .values(**valeurs)
            )
            await session.commit()

    async def noter_resultat(
        self, organization_id: int, installation_id: int, numero: int, resultat: dict[str, Any]
    ) -> None:
        """Range ce qu'une étape en cours a déjà produit (une coupure ensuite ne le refait pas)."""
        async with self.async_session() as session:
            await session.execute(
                update(EtapeInstallationModel)
                .where(
                    EtapeInstallationModel.installation_id == installation_id,
                    EtapeInstallationModel.organization_id == organization_id,
                    EtapeInstallationModel.numero == numero,
                    EtapeInstallationModel.etat == "en_cours",
                )
                .values(resultat=resultat)
            )
            await session.commit()

    async def passer_etape(self, organization_id: int, installation_id: int, numero: int, user_id: int | None) -> bool:
        """Marque l'étape « passée » (à faire ou en erreur seulement)."""
        async with self.async_session() as session:
            passe = await session.scalar(
                update(EtapeInstallationModel)
                .where(
                    EtapeInstallationModel.installation_id == installation_id,
                    EtapeInstallationModel.organization_id == organization_id,
                    EtapeInstallationModel.numero == numero,
                    EtapeInstallationModel.etat.in_(("a_faire", "erreur")),
                )
                .values(etat="passee", par=user_id, le=datetime.now(UTC), derniere_erreur=None)
                .returning(EtapeInstallationModel.id)
            )
            await session.commit()
            return passe is not None

    async def terminer_installation(self, organization_id: int, installation_id: int) -> None:
        async with self.async_session() as session:
            await session.execute(
                update(InstallationClientModel)
                .where(
                    InstallationClientModel.id == installation_id,
                    InstallationClientModel.organization_id == organization_id,
                    InstallationClientModel.etat == "ouverte",
                )
                .values(etat="terminee", terminee_le=datetime.now(UTC))
            )
            await session.commit()
