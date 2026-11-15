"""[.mark] Module Restauration, lot 20 : l'accès aux tables de la CAISSE DE DÉMO (Labo seulement).

Tout ce qui lit ou écrit un restaurant de test passe ici, borné à l'organisation (``organization_id``) ; seul le jeton présenté à la caisse (en empreinte)
et le point de vente d'un message retrouvent un restaurant sans l'organisation, et rendent alors son ``organization_id`` pour que l'appelant le contrôle
(la caisse de démo n'est servie qu'au Labo). Les dates sont posées par l'appelant (source d'heure, D6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select, update

from api.db.base_client import BaseDBClient
from api.db.models_caisse_demo import CaisseDemoCommandeModel, CaisseDemoMessageModel, CaisseDemoRestaurantModel

CHAMPS_MODIFIABLES = frozenset(
    {"nom", "etat", "minutes_en_plus", "carte", "stocks", "clients", "reglages", "comportement", "scenario", "callback_url", "callback_evenements", "jeton_empreinte"}
)


def _restaurant(r: CaisseDemoRestaurantModel) -> dict[str, Any]:
    return {
        "id": r.id, "organization_id": r.organization_id, "nom": r.nom, "point_de_vente": r.point_de_vente, "jeton_empreinte": r.jeton_empreinte,
        "etat": r.etat, "minutes_en_plus": r.minutes_en_plus, "carte": r.carte or {}, "stocks": r.stocks or [], "clients": r.clients or [],
        "reglages": r.reglages or {}, "comportement": r.comportement or {}, "scenario": r.scenario, "callback_url": r.callback_url,
        "callback_evenements": r.callback_evenements, "cree_le": r.cree_le, "maj_le": r.maj_le,
    }


def _commande(c: CaisseDemoCommandeModel) -> dict[str, Any]:
    return {"id": c.id, "restaurant_id": c.restaurant_id, "ref": c.ref, "private_ref": c.private_ref, "statut": c.statut, "corps": c.corps, "cree_le": c.cree_le, "maj_le": c.maj_le}


def _message(m: CaisseDemoMessageModel) -> dict[str, Any]:
    return {"id": m.id, "restaurant_id": m.restaurant_id, "corps": m.corps, "statut": m.statut, "tentatives": m.tentatives, "prochaine_le": m.prochaine_le, "cree_le": m.cree_le}


class CaisseDemoClient(BaseDBClient):
    # ---- restaurants de test
    async def creer_restaurant_de_demo(self, organization_id: int, nom: str, point_de_vente: str, maintenant: datetime, **champs: Any) -> dict[str, Any]:
        inconnus = set(champs) - CHAMPS_MODIFIABLES
        if inconnus:
            raise ValueError(f"Champs inconnus : {sorted(inconnus)}")
        async with self.async_session() as session:
            r = CaisseDemoRestaurantModel(organization_id=organization_id, nom=nom, point_de_vente=point_de_vente, cree_le=maintenant, maj_le=maintenant, **champs)
            r.etat = r.etat or "ouvert"
            r.minutes_en_plus = r.minutes_en_plus or 0
            r.carte, r.stocks, r.clients = r.carte or {}, r.stocks or [], r.clients or []
            r.reglages, r.comportement = r.reglages or {}, r.comportement or {}
            session.add(r)
            await session.commit()
            await session.refresh(r)
            return _restaurant(r)

    async def lister_restaurants_de_demo(self, organization_id: int) -> list[dict[str, Any]]:
        async with self.async_session() as session:
            lignes = (await session.execute(select(CaisseDemoRestaurantModel).where(CaisseDemoRestaurantModel.organization_id == organization_id).order_by(CaisseDemoRestaurantModel.id))).scalars()
            return [_restaurant(r) for r in lignes]

    async def lire_restaurant_de_demo(self, organization_id: int, restaurant_id: int) -> dict[str, Any] | None:
        async with self.async_session() as session:
            r = (await session.execute(select(CaisseDemoRestaurantModel).where(CaisseDemoRestaurantModel.id == restaurant_id, CaisseDemoRestaurantModel.organization_id == organization_id))).scalar_one_or_none()
            return None if r is None else _restaurant(r)

    async def lire_restaurant_de_demo_par_jeton(self, empreinte: str) -> dict[str, Any] | None:
        async with self.async_session() as session:
            r = (await session.execute(select(CaisseDemoRestaurantModel).where(CaisseDemoRestaurantModel.jeton_empreinte == empreinte))).scalars().first()
            return None if r is None else _restaurant(r)

    async def lire_restaurant_de_demo_par_point_de_vente(self, point_de_vente: str) -> dict[str, Any] | None:
        async with self.async_session() as session:
            r = (await session.execute(select(CaisseDemoRestaurantModel).where(CaisseDemoRestaurantModel.point_de_vente == point_de_vente))).scalar_one_or_none()
            return None if r is None else _restaurant(r)

    async def modifier_restaurant_de_demo(self, organization_id: int, restaurant_id: int, champs: dict[str, Any], maintenant: datetime) -> dict[str, Any] | None:
        inconnus = set(champs) - CHAMPS_MODIFIABLES
        if inconnus:
            raise ValueError(f"Champs inconnus : {sorted(inconnus)}")
        async with self.async_session() as session:
            res = await session.execute(
                update(CaisseDemoRestaurantModel)
                .where(CaisseDemoRestaurantModel.id == restaurant_id, CaisseDemoRestaurantModel.organization_id == organization_id)
                .values(**champs, maj_le=maintenant)
            )
            await session.commit()
        return await self.lire_restaurant_de_demo(organization_id, restaurant_id) if res.rowcount else None

    async def supprimer_restaurant_de_demo(self, organization_id: int, restaurant_id: int) -> bool:
        async with self.async_session() as session:
            res = await session.execute(delete(CaisseDemoRestaurantModel).where(CaisseDemoRestaurantModel.id == restaurant_id, CaisseDemoRestaurantModel.organization_id == organization_id))
            await session.commit()
            return bool(res.rowcount)

    # ---- commandes reçues (bornées au restaurant déjà contrôlé par l'appelant)
    async def ajouter_commande_de_demo(self, restaurant_id: int, ref: str, private_ref: str | None, statut: str, corps: dict, maintenant: datetime) -> dict[str, Any]:
        async with self.async_session() as session:
            c = CaisseDemoCommandeModel(restaurant_id=restaurant_id, ref=ref, private_ref=private_ref, statut=statut, corps=corps, cree_le=maintenant, maj_le=maintenant)
            session.add(c)
            await session.commit()
            await session.refresh(c)
            return _commande(c)

    async def lister_commandes_de_demo(self, restaurant_id: int, *, private_ref: str | None = None, limite: int = 100) -> list[dict[str, Any]]:
        requete = select(CaisseDemoCommandeModel).where(CaisseDemoCommandeModel.restaurant_id == restaurant_id)
        if private_ref is not None:
            requete = requete.where(CaisseDemoCommandeModel.private_ref == private_ref)
        async with self.async_session() as session:
            lignes = (await session.execute(requete.order_by(CaisseDemoCommandeModel.id.desc()).limit(max(1, min(limite, 500))))).scalars()
            return [_commande(c) for c in lignes]

    async def lire_commande_de_demo(self, restaurant_id: int, ref: str) -> dict[str, Any] | None:
        async with self.async_session() as session:
            c = (await session.execute(select(CaisseDemoCommandeModel).where(CaisseDemoCommandeModel.restaurant_id == restaurant_id, CaisseDemoCommandeModel.ref == ref))).scalar_one_or_none()
            return None if c is None else _commande(c)

    async def modifier_commande_de_demo(self, restaurant_id: int, ref: str, statut: str, corps: dict, maintenant: datetime) -> bool:
        async with self.async_session() as session:
            res = await session.execute(
                update(CaisseDemoCommandeModel).where(CaisseDemoCommandeModel.restaurant_id == restaurant_id, CaisseDemoCommandeModel.ref == ref).values(statut=statut, corps=corps, maj_le=maintenant)
            )
            await session.commit()
            return bool(res.rowcount)

    # ---- messages signés à rendre
    async def ajouter_message_de_demo(self, restaurant_id: int, identifiant: str, corps: dict, maintenant: datetime) -> None:
        async with self.async_session() as session:
            session.add(CaisseDemoMessageModel(id=identifiant, restaurant_id=restaurant_id, corps=corps, statut="a_envoyer", tentatives=0, prochaine_le=maintenant, cree_le=maintenant))
            await session.commit()

    async def messages_de_demo_dus(self, maintenant: datetime, limite: int = 50) -> list[dict[str, Any]]:
        async with self.async_session() as session:
            lignes = (
                await session.execute(
                    select(CaisseDemoMessageModel).where(CaisseDemoMessageModel.statut == "a_envoyer", CaisseDemoMessageModel.prochaine_le <= maintenant).order_by(CaisseDemoMessageModel.cree_le).limit(limite)
                )
            ).scalars()
            return [_message(m) for m in lignes]

    async def lire_message_de_demo(self, identifiant: str) -> dict[str, Any] | None:
        async with self.async_session() as session:
            m = (await session.execute(select(CaisseDemoMessageModel).where(CaisseDemoMessageModel.id == identifiant))).scalar_one_or_none()
            return None if m is None else _message(m)

    async def lister_messages_de_demo(self, restaurant_id: int, limite: int = 100) -> list[dict[str, Any]]:
        async with self.async_session() as session:
            lignes = (await session.execute(select(CaisseDemoMessageModel).where(CaisseDemoMessageModel.restaurant_id == restaurant_id).order_by(CaisseDemoMessageModel.cree_le.desc()).limit(limite))).scalars()
            return [_message(m) for m in lignes]

    async def noter_message_de_demo(self, identifiant: str, statut: str, tentatives: int, prochaine_le: datetime | None) -> None:
        async with self.async_session() as session:
            await session.execute(update(CaisseDemoMessageModel).where(CaisseDemoMessageModel.id == identifiant).values(statut=statut, tentatives=tentatives, prochaine_le=prochaine_le))
            await session.commit()
