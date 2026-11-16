"""[.mark] Module Restauration, lot 20 : les SCÉNARIOS NOMMÉS de la caisse de démo (mettre en place, enregistrer les réglages en cours, supprimer).

Un scénario est un jeu de réglages d'un restaurant de test : son état, son comportement, ses minutes en plus, son délai annoncé. Les neuf scénarios LIVRÉS (six du plan, trois de la maquette) sont versés par un module
IDEMPOTENT (``livrer``) qui n'écrase jamais ce qu'une personne a enregistré ni modifié ; ceux qu'on enregistre à l'écran s'ajoutent. Un scénario livré se supprime comme un autre
(il revient à la prochaine livraison seulement s'il n'existe pas : jamais de réécriture). Rangés par organisation du Labo, dans ses lignes de configuration.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from api.services.builder import stock
from api.services.restauration.caisse_demo import restaurants

CLE = "MARK_CAISSE_DEMO_SCENARIOS"
MAX_SCENARIOS = 60

LIVRES: dict[str, dict[str, Any]] = {
    "tout-va-bien": {"nom": "Tout va bien", "etat": "ouvert", "minutes_en_plus": 0, "comportement": {"reponse": "accepte", "acceptation": "auto", "delai_s": 0.4}, "delai": 20},
    "restaurant-deborde": {"nom": "Restaurant débordé", "etat": "deborde", "minutes_en_plus": 20, "comportement": {"reponse": "accepte", "acceptation": "auto", "delai_s": 0.4}, "delai": 20},
    "restaurant-ferme": {"nom": "Restaurant fermé", "etat": "ferme", "minutes_en_plus": 0, "comportement": {"reponse": "controle", "controles": ["ferme"]}, "delai": 20},
    "caisse-stricte": {
        "nom": "Caisse stricte", "etat": "ouvert", "minutes_en_plus": 0,
        "comportement": {"reponse": "controle", "controles": ["produit_inconnu", "prix_different", "ferme", "remise_inconnue"], "acceptation": "auto", "delai_s": 0.4}, "delai": 20,
    },
    "caisse-lente": {"nom": "Caisse lente", "etat": "ouvert", "minutes_en_plus": 0, "comportement": {"reponse": "accepte", "delai_s": 6, "acceptation": "auto"}, "delai": 20},
    "caisse-muette": {"nom": "Caisse muette", "etat": "ouvert", "minutes_en_plus": 0, "comportement": {"reponse": "silence"}, "delai": 20},
    # Les trois de la maquette (E-53) : les imprévus pendant l'appel, déclenchés tout seuls par la caisse (``imprevus.py``).
    "rupture-en-plein-appel": {
        "nom": "Rupture en plein appel", "etat": "ouvert", "minutes_en_plus": 0, "delai": 20,
        "comportement": {"reponse": "accepte", "acceptation": "auto", "delai_s": 0.4, "rupture_plein_appel": "auto"},
    },
    "refus-prix-different": {
        "nom": "Refus : prix différent", "etat": "ouvert", "minutes_en_plus": 0, "delai": 20,
        "comportement": {"reponse": "controle", "controles": ["prix_different"], "acceptation": "auto", "delai_s": 0.4, "carte_changee": True},
    },
    "commande-recue-deux-fois": {
        "nom": "Commande reçue deux fois", "etat": "ouvert", "minutes_en_plus": 0, "delai": 20,
        "comportement": {"reponse": "accepte", "acceptation": "auto", "delai_s": 0.4, "commande_deux_fois": True},
    },
}


# Ce qui fait le CONTENU d'un scénario (le reste de la ligne : ``livre``, ``empreinte``, ``scenario`` retenu ailleurs, n'en fait pas partie).
CHAMPS = ("nom", "etat", "minutes_en_plus", "comportement", "delai")


def _contenu(ligne: dict[str, Any]) -> dict[str, Any]:
    return {c: ligne.get(c) for c in CHAMPS}


def _empreinte(ligne: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(_contenu(ligne), sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


class ScenarioRefuse(ValueError):
    """Un scénario refusé (nom vide, trop nombreux, inconnu) : le texte dit quoi."""


def _slug(nom: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", nom.lower().translate(str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc"))).strip("-")
    return base[:50] or "scenario"


async def lire(organization_id: int) -> dict[str, dict[str, Any]]:
    return dict((await stock.lire(organization_id, CLE)) or {})


def _livre(valeur: dict[str, Any]) -> dict[str, Any]:
    """La ligne d'un scénario livré : son contenu, ``livre`` et l'empreinte du contenu LIVRÉ (elle dit plus tard si une personne l'a changé)."""
    return {**valeur, "livre": True, "empreinte": _empreinte(valeur)}


def _a_mettre_a_niveau(actuel: dict[str, Any], livre: dict[str, Any]) -> bool:
    """Une ligne livrée dont le contenu a changé dans le code, et qu'AUCUNE personne n'a modifiée : son contenu est toujours celui de sa livraison (l'empreinte
    posée à la livraison le dit ; une ligne livrée avant les empreintes n'a pas d'empreinte, et se modifie nulle part à l'écran : elle est la livraison telle quelle).
    Une ligne enregistrée à la main (``livre`` faux), même du même nom, n'est JAMAIS touchée."""
    if actuel.get("livre") is not True or _contenu(actuel) == _contenu(livre):
        return False
    return actuel.get("empreinte") in (None, _empreinte(actuel))


async def livrer(organization_id: int) -> dict[str, dict[str, Any]]:
    """Verse les scénarios livrés qui manquent et met à niveau ceux que le code a fait évoluer depuis leur livraison (M21), tant qu'aucune personne ne les a
    modifiés ; n'écrase jamais un scénario enregistré à la main. Idempotent, même en cas d'écritures simultanées (une seule écriture, sur la ligne relue)."""

    def ajouter(courant):
        courant = dict(courant or {})
        changes = {k: _livre(v) for k, v in LIVRES.items() if k not in courant or _a_mettre_a_niveau(courant[k], v)}
        return {**courant, **changes} if changes else None

    return dict((await stock.modifier(organization_id, CLE, ajouter)) or {})


async def au_demarrage() -> list[str] | None:
    """Au déploiement : les scénarios livrés d'une base du Labo qui existait déjà sont mis à niveau (sans attendre le premier écran). ``None`` : la caisse de
    démo est éteinte ou il n'y a pas de Labo ; sinon les clés mises à niveau ou ajoutées."""
    from api.services.restauration.caisse_demo import garde

    if not garde.interrupteur_allume():
        return None
    labo = await garde.id_du_labo()
    if labo is None:
        return None
    avant = await lire(labo)
    apres = await livrer(labo)
    return sorted(k for k, v in apres.items() if avant.get(k) != v)


async def enregistrer(organization_id: int, restaurant_id: int, nom: str) -> str:
    """Enregistre les réglages EN COURS du restaurant de test sous ce nom (un nom déjà pris est remplacé s'il a été enregistré à la main, jamais un livré)."""
    from api.db import db_client

    r = await db_client.lire_restaurant_de_demo(organization_id, restaurant_id)
    if r is None:
        raise ScenarioRefuse("Restaurant de test introuvable.")
    propre = " ".join((nom or "").split())[:80]
    if not propre:
        raise ScenarioRefuse("Un nom est nécessaire.")
    cle = _slug(propre)
    ligne = {
        "nom": propre, "etat": r["etat"], "minutes_en_plus": r["minutes_en_plus"], "comportement": r["comportement"], "delai": r["reglages"].get("delai", 20), "livre": False,
    }

    def ecrire(courant):
        courant = dict(courant or {})
        if courant.get(cle, {}).get("livre"):
            raise ScenarioRefuse("Ce nom est celui d'un scénario livré : choisir un autre nom.")
        if cle not in courant and len(courant) >= MAX_SCENARIOS:
            raise ScenarioRefuse("Trop de scénarios : en supprimer un.")
        courant[cle] = ligne
        return courant

    await stock.modifier(organization_id, CLE, ecrire)
    return cle


async def supprimer(organization_id: int, cle: str) -> bool:
    trouve = []

    def retirer(courant):
        if not courant or cle not in courant:
            return None
        trouve.append(True)
        return {k: v for k, v in courant.items() if k != cle}

    await stock.modifier(organization_id, CLE, retirer)
    return bool(trouve)


async def mettre_en_place(organization_id: int, restaurant_id: int, cle: str) -> dict[str, Any] | None:
    """Applique un scénario au restaurant de test (état, comportement, minutes, délai) et le retient. ``None`` : restaurant ou scénario inconnu."""
    scenario = (await lire(organization_id)).get(cle)
    if scenario is None:
        return None
    return await restaurants.regler(
        organization_id, restaurant_id,
        {"etat": scenario["etat"], "minutes_en_plus": scenario.get("minutes_en_plus", 0), "comportement": scenario["comportement"], "reglages": {"delai": scenario.get("delai", 20)}},
    ) and await _retenir(organization_id, restaurant_id, cle)


async def _retenir(organization_id: int, restaurant_id: int, cle: str) -> dict[str, Any] | None:
    from api.db import db_client
    from api.db.bases_clients.horloge import horloge

    return await db_client.modifier_restaurant_de_demo(organization_id, restaurant_id, {"scenario": cle}, horloge(organization_id).maintenant())
