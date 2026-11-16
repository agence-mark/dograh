"""[.mark] Module Restauration, lot 10 : l'HEURE changée par la caisse (temps de préparation allongé).

Quand la caisse confirme une autre heure que celle de notre commande, le classeur la reprend (source « caisse », journal), l'événement ``commande.heure`` part (le Rush
et Commandes l'affichent sans recharger), et l'appelant est PRÉVENU PAR SMS si l'envoi « heure changée » de l'établissement est allumé (table des envois du classeur, type ``sms``,
déclencheur ``heure_changee`` : ÉTEINT par défaut, E-18). Rejouable : la même heure relue ne change rien, n'émet rien et ne renvoie rien.

Le SMS passe par l'envoi de SMS existant du fork (``sms_restauration``, compte Twilio de « Téléphonie » de l'organisation) : le texte de l'envoi, ses trous (``{{heure}}``,
``{{numero_court}}``) remplis par le code, jamais par le modèle ; au numéro de la commande si c'est un mobile français. Un SMS qui ne peut pas partir se dit au journal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger

from api.db.bases_clients import restauration_liaison as liaison_db
from api.db.bases_clients.restauration_commande import commande_complete
from api.db.bases_clients.restauration_commun import Connexion, fuseau_de
from api.services.restauration import flux
from api.services.restauration import sms_restauration as sms_resto

DECLENCHEUR = "heure_changee"


async def prevenir_l_appelant(connexion: Connexion, organization_id: int | None, etablissement_id: int, numero: str, heure: datetime) -> bool:
    """Vrai si un SMS est parti. Faux : l'envoi est éteint (par défaut), le client n'a pas de mobile français, ou le SMS n'a pas pu partir (dit au journal)."""
    envoi = await liaison_db.envoi_actif(connexion, etablissement_id, "sms", DECLENCHEUR)
    if envoi is None or organization_id is None:
        return False
    try:
        commande = await commande_complete(connexion, etablissement_id, numero)
        if commande is None:
            return False
        local = heure.astimezone(ZoneInfo(await fuseau_de(connexion, etablissement_id)))
        fiche = {"heure": local.strftime("%H:%M"), "numero_court": commande.get("numero_court") or ""}
        return await sms_resto.envoyer_un_sms(
            organization_id, (commande.get("client") or {}).get("telephone") or "", envoi["texte"], fiche, f"heure:{etablissement_id}:{numero}:{heure.isoformat()}"
        )
    except Exception as erreur:  # noqa: BLE001 -- ne casse jamais la reprise de l'heure
        logger.error(f"[.mark] Order {numero}: the 'time changed' SMS failed: {type(erreur).__name__}")
        return False


async def appliquer_l_heure(
    connexion: Connexion, organization_id: int | None, etablissement_id: int, numero: str | uuid.UUID, heure: datetime | None
) -> bool:
    """Reprend l'heure confirmée par la caisse pour CETTE commande de CET établissement. Rend ``True`` si elle a changé (``commande.heure`` émis, appelant prévenu si l'envoi est allumé)."""
    if heure is None or heure.tzinfo is None:
        return False
    if not await liaison_db.poser_l_heure_annoncee(connexion, etablissement_id, numero, heure, "caisse"):
        return False
    if organization_id is not None:
        await flux.emettre(organization_id, etablissement_id, "commande.heure", {"numero": str(numero), "heure_annoncee": heure})
    await prevenir_l_appelant(connexion, organization_id, etablissement_id, str(numero), heure)
    return True
