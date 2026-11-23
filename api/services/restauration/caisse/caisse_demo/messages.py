"""[.mark] Module Restauration, lot 20 : les MESSAGES SIGNÉS que la caisse de démo rend à notre adresse de réception, comme HubRise.

Un message (``order``, ``inventory``, ``catalog``, ``location``) est d'abord ÉCRIT dans la table des messages, puis rendu : ``POST`` vers l'adresse de rappel
posée par la prise, corps JSON compact, signature ``X-HubRise-Hmac-SHA256`` (HMAC-SHA256 du corps brut avec le secret de notre application, le même que la
réception vérifie). Sans réponse 2xx : nouvelle tentative après 1, 2, 4, 8, 16 puis 32 minutes (six tentatives, comme HubRise), puis abandon, dit sur la
ligne. Sans adresse de rappel (mode passif) : le message est GARDÉ, la prise le relit (``GET /callback/events``) et l'acquitte (``DELETE``).

SSRF (D4) : l'adresse de rappel n'est acceptée que si elle est celle de NOTRE réception (``hubrise_liaison.adresse_de_rappel``) ; la caisse de démo ne
parle jamais à une autre adresse. Le corps ne porte aucun secret. Heures : la source d'heure de l'organisation du restaurant (D6).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from loguru import logger

from api.db import db_client
from api.db.bases_clients.horloge import horloge
from api.services.restauration.caisse.prises import hubrise_liaison

ATTENTES_MIN = (1, 2, 4, 8, 16, 32)  # après chaque échec ; le sixième échec abandonne
DELAI_ENVOI_S = 20.0  # HubRise attend la réponse à un message 20 secondes au plus : la caisse de démo aussi
EVENEMENTS_PAR_RELEVE = 100


def url_de_rappel_permise(url: str | None) -> bool:
    """Seule NOTRE adresse de réception est permise (jamais une adresse libre : un appel sortant se limite à une liste fermée)."""
    if not url or not isinstance(url, str) or any(c in url for c in ("\\", "\r", "\n", "\t", " ")):
        return False
    permise = hubrise_liaison.adresse_de_rappel()
    return url == permise or url.startswith(permise + "?")


def signer(corps: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), corps, hashlib.sha256).hexdigest()


def corps_du_message(restaurant: dict[str, Any], ressource: str, evenement: str, *, identifiant: str, quand: str, **plus: Any) -> dict[str, Any]:
    compte = restaurant["point_de_vente"].rsplit("-", 1)[0]
    message = {
        "id": identifiant, "created_at": quand, "resource_type": ressource, "event_type": evenement,
        "location_id": restaurant["point_de_vente"], "account_id": compte,
    }
    message.update({k: v for k, v in plus.items() if v is not None})
    return message


async def poster(restaurant: dict[str, Any], ressource: str, evenement: str, **plus: Any) -> str:
    """Écrit un message à rendre à la prise ; rend son identifiant. Gardé (mode passif) quand la prise n'a posé aucune adresse."""
    maintenant = horloge(restaurant["organization_id"]).maintenant()
    identifiant = secrets.token_hex(8)
    corps = corps_du_message(restaurant, ressource, evenement, identifiant=identifiant, quand=maintenant.isoformat(), **plus)
    await db_client.ajouter_message_de_demo(restaurant["id"], identifiant, corps, maintenant)
    if not restaurant.get("callback_url"):
        await db_client.noter_message_de_demo(identifiant, "garde", 0, None)
    return identifiant


async def _rendre(restaurant: dict[str, Any], message: dict[str, Any], secret: str, transport: httpx.AsyncBaseTransport | None) -> bool:
    corps = json.dumps(message["corps"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    entetes = {"Content-Type": "application/json", "X-HubRise-Hmac-SHA256": signer(corps, secret)}
    fois = 2 if (restaurant.get("comportement") or {}).get("doublon") else 1  # « le message reçu deux fois » : même identifiant, rendu deux fois
    try:
        async with httpx.AsyncClient(transport=transport, timeout=DELAI_ENVOI_S) as http:
            for _ in range(fois):
                reponse = await http.post(restaurant["callback_url"], content=corps, headers=entetes)
                if not 200 <= reponse.status_code < 300:
                    return False
    except (httpx.TimeoutException, httpx.TransportError) as erreur:
        logger.warning(f"[.mark] Demo till message {message['id']}: {type(erreur).__name__}")
        return False
    return True


async def envoyer_les_messages_dus(*, transport: httpx.AsyncBaseTransport | None = None, limite: int = 50, restaurant_id: int | None = None) -> dict[str, int]:
    """Rend les messages dus (premier essai ou nouvelle tentative), ceux d'un seul restaurant si ``restaurant_id`` est donné. Rejouable sans effet double : un message
    rendu ne l'est plus. Tâche planifiée."""
    bilan = {"rendus": 0, "reportes": 0, "abandonnes": 0, "ignores": 0}
    try:
        secret = hubrise_liaison.secret_de_signature()
    except hubrise_liaison.NonConfiguree:
        return bilan  # sans secret : rien ne part (jamais un message signé avec un secret de substitution)
    restaurants: dict[int, dict | None] = {}
    # La date « due » vient de la source d'heure : celle de chaque organisation ; on lit large puis on contrôle chaque message.
    due = datetime.max.replace(tzinfo=UTC)
    for message in await db_client.messages_de_demo_dus(due, limite):
        rid = message["restaurant_id"]
        if restaurant_id is not None and rid != restaurant_id:
            continue
        if rid not in restaurants:
            restaurants[rid] = await _restaurant_par_id(rid)
        restaurant = restaurants[rid]
        if restaurant is None or not restaurant.get("callback_url") or not url_de_rappel_permise(restaurant["callback_url"]):
            bilan["ignores"] += 1
            continue
        maintenant = horloge(restaurant["organization_id"]).maintenant()
        if message["prochaine_le"] and message["prochaine_le"] > maintenant:
            continue
        if await _rendre(restaurant, message, secret, transport):
            await db_client.noter_message_de_demo(message["id"], "envoye", message["tentatives"] + 1, None)
            bilan["rendus"] += 1
            continue
        essais = message["tentatives"] + 1
        if essais >= len(ATTENTES_MIN):
            await db_client.noter_message_de_demo(message["id"], "abandonne", essais, None)
            bilan["abandonnes"] += 1
        else:
            await db_client.noter_message_de_demo(message["id"], "a_envoyer", essais, maintenant + timedelta(minutes=ATTENTES_MIN[essais - 1]))
            bilan["reportes"] += 1
    return bilan


async def _restaurant_par_id(restaurant_id: int) -> dict[str, Any] | None:
    return await db_client.lire_restaurant_de_demo_par_id(restaurant_id)


async def evenements_gardes(restaurant: dict[str, Any]) -> list[dict[str, Any]]:
    """Les messages gardés (mode passif) de CE restaurant, du plus ancien au plus récent."""
    tous = await db_client.lister_messages_de_demo(restaurant["id"], 500)
    return [m["corps"] for m in reversed(tous) if m["statut"] == "garde"][:EVENEMENTS_PAR_RELEVE]


async def acquitter(restaurant: dict[str, Any], identifiant: str) -> bool:
    """``DELETE /callback/events/:id`` : le message gardé n'est plus rendu. Faux s'il n'est pas à CE restaurant ou pas gardé."""
    message = await db_client.lire_message_de_demo(identifiant)
    if message is None or message["restaurant_id"] != restaurant["id"] or message["statut"] != "garde":
        return False
    await db_client.noter_message_de_demo(identifiant, "acquitte", message["tentatives"], None)
    return True


async def rendre_les_messages_de_la_caisse_de_demo(_ctx=None) -> dict[str, int]:
    """La tâche planifiée (toutes les 5 secondes) : rend les messages signés dus. Interrupteur éteint : rien (aucune lecture de la base)."""
    from api.services.restauration.caisse.caisse_demo import garde

    if not garde.interrupteur_allume():
        return {"rendus": 0, "reportes": 0, "abandonnes": 0, "ignores": 0}
    return await envoyer_les_messages_dus()
