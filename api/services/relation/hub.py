"""[.mark] Le Hub « Relation clients » : qui y entre, les noms, et le lien d'entrée signé dans un portail (E78).

* Le Hub est réservé aux membres de l'équipe .mark, par une SESSION : une clé d'API (le portail, un script) n'y entre
  jamais, quelle que soit son organisation.
* Le lien d'entrée : un jeton aléatoire, valable ``DUREE_LIEN_S`` secondes, à usage unique, pour UN client et UN membre.
  Seule son empreinte SHA-256 est écrite ; le jeton n'est rendu qu'une fois, à celui qui l'a demandé.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from loguru import logger

from api.db import db_client
from api.services.equipe_mark.acces import acces_de

DUREE_LIEN_S = 60


def empreinte(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def est_une_cle_d_api(x_api_key: str | None) -> bool:
    """La requête vient d'une clé d'API quand l'en-tête est là (``get_user`` lui donne alors la priorité sur toute session)."""
    return bool(x_api_key)


async def exiger_equipe(user, x_api_key: str | None) -> None:
    """403 pour une clé d'API ou pour un compte sans rôle d'équipe."""
    if est_une_cle_d_api(x_api_key):
        raise HTTPException(status_code=403, detail="The Relation hub is not open to an API key")
    if await acces_de(user) is None:
        raise HTTPException(status_code=403, detail="Reserved to the .mark team")


def nom_affiche(membre: dict, repli_id: int | None = None) -> str:
    """Le nom d'un membre de l'équipe : prénom et nom, sinon la partie locale de son adresse, jamais l'adresse entière."""
    nom = " ".join(p for p in (membre.get("prenom"), membre.get("nom")) if p)
    return nom or (membre.get("email") or f"membre {membre.get('user_id', repli_id)}").split("@")[0]


async def nom_du_membre(user) -> str:
    membre = await db_client.obtenir_membre(user.id) or {}
    nom = " ".join(p for p in (membre.get("prenom"), membre.get("nom")) if p)
    return nom or (user.email or f"membre {user.id}").split("@")[0]


async def membres_a_suivre() -> list[dict]:
    """V4 : les membres de l'équipe .mark à qui on peut confier le suivi d'un fil (id et nom seulement, jamais une adresse)."""
    lignes, _total = await db_client.lister_membres(limit=100, offset=0)
    return [{"id": m["user_id"], "nom": nom_affiche(m)} for m in lignes]


async def clients_ouverts(user) -> dict[int, str]:
    """Les clients (jamais le Labo) que le rôle du compte ouvre : id -> nom affiché."""
    from api.services.equipe_mark.espaces import lister_espaces

    return {e["id"]: e["nom"] for e in await lister_espaces(user) if e["espace"] == "client"}


async def client_ouvert(user, organization_id: int) -> str:
    """Le nom du client, ou 404 : un client que le rôle n'ouvre pas n'existe pas pour ce compte."""
    nom = (await clients_ouverts(user)).get(organization_id)
    if nom is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return nom


async def creer_lien(user, organization_id: int, motif: str | None) -> dict:
    jeton = secrets.token_urlsafe(32)
    expire_le = datetime.now(UTC) + timedelta(seconds=DUREE_LIEN_S)
    auteur = await nom_du_membre(user)
    entree = await db_client.creer_entree_relation(
        organization_id, user.id, auteur, motif, empreinte(jeton), expire_le
    )
    return {"entree_id": entree["id"], "jeton": jeton, "expire_le": expire_le, "valable_secondes": DUREE_LIEN_S}


async def consommer_lien(organization_id: int, jeton: str) -> dict | None:
    """Le lien d'UN client, une seule fois ; ``None`` si inconnu, rejoué, expiré ou d'un autre client."""
    return await db_client.consommer_entree_relation(organization_id, empreinte(jeton), datetime.now(UTC))


async def stats_avis(organization_id: int) -> dict:
    """Note moyenne et nombre d'avis lus dans la base du client ; vide sans base, ou base injoignable."""
    from api.db.bases_clients.connexion import connecter
    from api.services.base_client import rattachement

    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        return {"note": None, "avis": 0}
    try:
        connexion = await connecter(nom)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Reviews of organization {organization_id} not read: {type(erreur).__name__}")
        return {"note": None, "avis": 0}
    try:
        ligne = await connexion.fetchrow("SELECT count(*) AS n, avg(etoiles) AS moyenne FROM avis")
        n = int(ligne["n"]) if ligne else 0
        return {"note": round(float(ligne["moyenne"]), 1) if n else None, "avis": n}
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Reviews of organization {organization_id} not read: {type(erreur).__name__}")
        return {"note": None, "avis": 0}
    finally:
        await connexion.close()
