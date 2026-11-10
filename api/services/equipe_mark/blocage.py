"""[.mark] Clôture, lot A (D22) : bloquer un membre de l'équipe en un clic, sans date.

Un membre « Accès actif » éteint est refusé à CHAQUE requête : sa session, mais aussi toutes les clés d'API qu'il a créées (la clé se présente
comme son créateur), et la connexion. Ses permissions et son rôle ne bougent pas : rétabli, il retrouve tout. Le message montré est réglé à
l'écran (deux langues) ; le défaut est celui d'Evan.
"""

from __future__ import annotations

from fastapi import HTTPException

from api.db import db_client

CLE_MESSAGE = "MARK_MESSAGE_ACCES_BLOQUE"
MESSAGE_PAR_DEFAUT = {
    "fr": "Votre accès est bloqué jusqu'à votre prochaine mission.",
    "en": "Your access is blocked until your next assignment.",
}
MESSAGE_MAX = 300


def _propre(texte) -> str:
    return " ".join("".join(c for c in str(texte or "") if c.isprintable()).split())[:MESSAGE_MAX]


async def message_de_blocage(langue: str = "fr") -> str:
    """Le message réglé à l'écran, dans la langue demandée (``fr`` ou ``en``) ; le défaut si rien n'est réglé."""
    langue = "en" if (langue or "").lower().startswith("en") else "fr"
    try:
        regle = await db_client.lire_reglage_equipe(CLE_MESSAGE) or {}
    except Exception:  # noqa: BLE001 -- un message illisible ne doit pas ouvrir l'accès : on retombe sur le défaut
        regle = {}
    return _propre(regle.get(langue)) or MESSAGE_PAR_DEFAUT[langue]


async def reglages_du_message() -> dict:
    """Les deux textes réglés (vide = défaut) et les défauts, pour l'écran."""
    regle = await db_client.lire_reglage_equipe(CLE_MESSAGE) or {}
    return {
        "fr": _propre(regle.get("fr")),
        "en": _propre(regle.get("en")),
        "defaut": dict(MESSAGE_PAR_DEFAUT),
    }


async def regler_le_message(fr: str | None, en: str | None, user_id: int | None) -> dict:
    await db_client.poser_reglage_equipe(CLE_MESSAGE, {"fr": _propre(fr), "en": _propre(en)}, user_id)
    return await reglages_du_message()


async def exiger_acces_actif(user_id: int, langue: str = "fr") -> None:
    """403 avec le message réglé si le compte est un membre bloqué."""
    if not await db_client.acces_est_actif(user_id):
        raise HTTPException(status_code=403, detail=await message_de_blocage(langue))
