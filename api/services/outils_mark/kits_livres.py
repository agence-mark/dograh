"""[.mark] Module Restauration, lot 11 (E-22) : les kits d'outils livrés avec le fork (§ 3.3 du plan).

Trois kits, construits d'après le catalogue des connecteurs (jamais recopiés : le texte d'une action ne vieillit pas ici) :

| Kit | Connecteur et actions |
|---|---|
| Commande (catalogue) | ``commande`` : toutes les actions SAUF ``envoyer_un_message`` |
| Réservation (capacité) | ``reservation`` : toutes les actions |
| Envois (SMS) | ``service.envoyer_un_sms`` (éteint par défaut, E-18) |

Un kit est posé au démarrage du serveur s il manque ; ses outils qui manquent sont ajoutés ; ce qu'une personne a changé n'est jamais réécrit.
Le mécanisme (dossiers, kits, versions) ne connaît aucun métier : seuls ces trois noms de kit le font, comme des données.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.integrations.connectors.catalogue import connecteur

ENVOI = ("service", "envoyer_un_sms")  # V5 (lot 19 bis) : l'envoi vit au connecteur « service » depuis le lot 2 (``commande.envoyer_un_message`` est retiré)

# (nom du kit, description, connecteur, actions retenues ; ``None`` = toutes sauf l'envoi)
KITS_LIVRES: tuple[tuple[str, str, str, tuple[str, ...] | None], ...] = (
    ("Commande", "Prendre une commande sur un catalogue : ouverture, zone, panier, remises, enregistrement.", "commande", None),
    ("Réservation", "Réserver, modifier et annuler selon la capacité.", "reservation", ()),
    ("Envois", "Envoyer un message à l'appelant (éteint tant que le lieu ne l'allume pas).", ENVOI[0], (ENVOI[1],)),
)


def _outil(nom_connecteur: str, action) -> dict[str, Any]:
    return {
        "name": action.nom,
        "description": action.description,
        "category": "integration",
        "definition": {"schema_version": 1, "type": "integration", "config": {"connecteur": nom_connecteur, "action": action.nom}},
    }


def outils_du_kit(nom_connecteur: str, retenues: tuple[str, ...] | None) -> list[dict[str, Any]]:
    c = connecteur(nom_connecteur)
    if c is None:
        return []
    if retenues is None:
        actions = [a for a in c.actions if (c.nom, a.nom) != ENVOI]
    elif retenues == ():
        actions = list(c.actions)
    else:
        actions = [a for a in c.actions if a.nom in retenues]
    return [_outil(c.nom, a) for a in actions]


def outil_mort(definition: dict[str, Any]) -> bool:
    """V5 : un outil d'un kit livré dont l'action n'existe plus au catalogue : il disparaîtrait de la requête du modèle avec une ligne de journal (``outil.schema``), jamais signalé."""
    from api.services.integrations.connectors.outil import config_de, trouver

    config = config_de(type("Outil", (), {"definition": definition})())
    return trouver(config.get("connecteur", ""), config.get("action", "")) is None


async def poser_les_kits_livres() -> dict[str, dict[str, int]]:
    """Au démarrage : ne lève jamais (un kit absent n'empêche pas le serveur de répondre)."""
    from api.db import db_client

    bilan: dict[str, dict[str, int]] = {}
    for nom, description, nom_connecteur, retenues in KITS_LIVRES:
        try:
            bilan[nom] = await db_client.poser_un_kit_livre(nom, description, outils_du_kit(nom_connecteur, retenues), outil_mort)
        except Exception as erreur:  # noqa: BLE001 -- fail-open : le serveur démarre sans le kit, il est reposé au prochain démarrage
            logger.warning(f"[.mark] Kit {nom} not installed ({type(erreur).__name__}): {erreur}")
    return bilan
