"""[.mark] Module Restauration, lot 10 : les SMS du module, par l'envoi de SMS EXISTANT du fork (``services/apres_appel/sms.py``) : jamais un second moyen d'envoi.

Le compte Twilio est celui de « Téléphonie » de l'organisation (son fournisseur par défaut) ; l'expéditeur est celui du fournisseur. Les règles du module SMS d'après-appel
valent ici : le texte n'est jamais celui du modèle (trous remplis, une ligne, 160 caractères, ``sms.remplir``), un numéro qui n'est pas un mobile français n'est pas écrit (D4),
un même SMS n'est envoyé qu'une fois (clé à usage unique dans Redis). Un SMS qui ne peut pas partir (pas de compte, pas d'expéditeur, refus) rend ``False`` et se dit au journal :
il ne lève jamais (dire une panne ne doit pas en faire une seconde).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from loguru import logger

from api.db.bases_clients.restauration_commun import Connexion
from api.schemas.apres_appel import est_un_mobile, numero_e164
from api.services.apres_appel import sms
from api.services.restauration.envois_et_sms.une_fois import oublier_une_fois, une_seule_fois

CLE_UNIQUE = "mark:resto:sms:"


class Envoi(Enum):
    """Ce qu'est devenu un SMS demandé : ``PARTI``, ``DEJA_FAIT`` (il est déjà parti, même clé) ou ``REFUSEE`` (il ne peut pas partir : pas un mobile, pas de compte, panne).
    Lu comme un booléen (« est-il parti ? »), comme avant : seul ``PARTI`` est vrai."""

    PARTI = "parti"
    DEJA_FAIT = "deja_fait"
    REFUSEE = "refusee"

    def __bool__(self) -> bool:
        return self is Envoi.PARTI


async def identifiants_d_envoi(organization_id: int) -> tuple[str, str, str] | None:
    """``(account_sid, auth_token, expéditeur)`` du compte de « Téléphonie » de l'organisation, ou ``None`` (aucun compte, ou aucun expéditeur)."""
    from api.services.telephony.factory import get_default_telephony_provider

    try:
        fournisseur = await get_default_telephony_provider(organization_id)
    except Exception as erreur:  # noqa: BLE001 -- pas de téléphonie réglée : pas de SMS, dit au journal
        logger.warning(f"[.mark] Restaurant SMS: no telephony account for organization {organization_id} ({type(erreur).__name__})")
        return None
    sid, jeton = getattr(fournisseur, "account_sid", None), getattr(fournisseur, "auth_token", None)
    expediteur = getattr(fournisseur, "default_from_number", None) or next(iter(getattr(fournisseur, "from_numbers", None) or []), None)
    return (sid, jeton, expediteur) if sid and jeton and expediteur else None


async def numeros_du_gerant(connexion: Connexion, etablissement_id: int) -> list[str]:
    """Les mobiles français des personnes de l'équipe marquées « destinataire par défaut » pour CET établissement (ou pour toute l'entreprise), actives. Sans doublon."""
    from api.db.bases_clients.restauration_commun import telephones_des_destinataires

    sortie: list[str] = []
    for telephone in await telephones_des_destinataires(connexion, etablissement_id):
        numero = numero_e164(telephone)
        if est_un_mobile(numero) and numero not in sortie:
            sortie.append(numero)
    return sortie


async def envoyer_un_sms(organization_id: int, destinataire: str, modele: str, fiche: dict[str, Any], cle_unique: str) -> Envoi:
    """Un SMS à ``destinataire`` (``modele`` rempli par ``fiche``). ``cle_unique`` : le même SMS n'est jamais envoyé deux fois (``DEJA_FAIT``). ``PARTI`` s'il est parti."""
    numero = numero_e164(destinataire)
    if not est_un_mobile(numero):
        return Envoi.REFUSEE
    identifiants = await identifiants_d_envoi(organization_id)
    if identifiants is None:
        return Envoi.REFUSEE
    cle = f"{CLE_UNIQUE}{organization_id}:{cle_unique}:{numero}"
    if not await une_seule_fois(cle):
        return Envoi.DEJA_FAIT
    texte, _ = sms.remplir(modele, fiche)
    try:
        await sms.envoyer(*identifiants[:2], identifiants[2], numero, texte)
    except sms.EchecTwilio as erreur:
        logger.warning(f"[.mark] Restaurant SMS not sent: {erreur}")
        await oublier_une_fois(cle)  # rien n'est parti : une reprise pourra le renvoyer
        return Envoi.REFUSEE
    return Envoi.PARTI
