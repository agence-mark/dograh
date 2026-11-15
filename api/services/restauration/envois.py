"""[.mark] Module Restauration, lot 7 (E-18, T-20) : les ENVOIS après une action (SMS), par le mécanisme d'envoi existant du fork.

Une commande enregistrée, une réservation faite, changée ou annulée, la carte ou le lien d'avis demandés par l'appelant : si l'établissement a ALLUMÉ
l'envoi correspondant, un SMS part. **Éteints par défaut** (E-18) : une ligne de la table des envois n'existe pas, ou existe avec ``actif`` faux, et rien ne part.
Configuration à UN SEUL endroit : la table des envois (portail, Réglages › Envois : le type, le déclencheur, le texte à trous) ; le fournisseur reste
celui de « Téléphonie » (``sms_restauration``), qui ne reprend jamais les textes.

Le texte n'est jamais celui du modèle : ses trous (``{{prenom}}``, ``{{numero_court}}``, ``{{quand}}``) sont remplis par le code. Le même SMS pour la même
action n'est jamais envoyé deux fois (clé à usage unique). Un envoi qui ne part pas rend ``False`` et se dit au journal : il ne lève jamais, il ne défait
jamais l'action déjà faite.
"""

from __future__ import annotations

from typing import Any

import asyncpg
from loguru import logger

from api.db.bases_clients import restauration_liaison as liaison_db
from api.services.restauration import sms_restauration as sms_resto

COMMANDE_ENREGISTREE = "commande_enregistree"
RESERVATION_ENREGISTREE = "reservation_enregistree"
RESERVATION_MODIFIEE = "reservation_modifiee"
RESERVATION_ANNULEE = "reservation_annulee"
CARTE = "carte"
AVIS = "avis"
# La liste fermée des déclencheurs de ce module (le portail n'en propose pas d'autres) ; ``heure_changee`` est celui du lot 10 (``heure_caisse.py``).
DECLENCHEURS = (COMMANDE_ENREGISTREE, RESERVATION_ENREGISTREE, RESERVATION_MODIFIEE, RESERVATION_ANNULEE, CARTE, AVIS, "heure_changee")
# Ceux que l'appelant peut demander lui-même par l'outil ``envoyer_un_message``.
A_LA_DEMANDE = (CARTE, AVIS)


async def envoyer_apres(
    connexion: asyncpg.Connection, organisation_id: int | None, etablissement_id: int, declencheur: str, telephone: str | None, fiche: dict[str, Any], cle_unique: str
) -> bool:
    """Un SMS si l'envoi de CET établissement pour ``declencheur`` est allumé. ``True`` si parti. Faux : éteint (le défaut), pas d'organisation, pas de mobile
    français, pas de compte, déjà envoyé. ⛔ Ne lève jamais."""
    if declencheur not in DECLENCHEURS or organisation_id is None or not telephone:
        return False
    try:
        envoi = await liaison_db.envoi_actif(connexion, etablissement_id, "sms", declencheur)
        if envoi is None:
            return False
        return await sms_resto.envoyer_un_sms(organisation_id, telephone, envoi["texte"], fiche, f"{declencheur}:{etablissement_id}:{cle_unique}")
    except Exception as erreur:  # noqa: BLE001 -- ne défait jamais l'action : dit au journal
        logger.error(f"[.mark] Message '{declencheur}' not sent: {type(erreur).__name__}")
        return False
