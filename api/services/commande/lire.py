"""[.mark] La lecture de la commande (chantier Partie 1, lot 2, étape 3 ; E16) : un seul outil pour tout ce qui se lit, qui n'écrit JAMAIS rien.

Règle nommée ``lecture_sur_une_copie`` : chaque lecture s'exécute sur une copie profonde du panier ; le panier de l'appel est rendu identique
(une fonction de lecture du moteur qui tiendrait un compteur, comme ``remises_disponibles``, ne change donc rien). ``vider_le_panier`` n'est plus
caché dans la lecture (A26, S7) : c'est une case de la fiche.

Chaque sujet de la liste fermée de la version finale a sa fonction ; « autre » (E27) rend ce qui se lit, sans rien deviner.
"""

from __future__ import annotations

import copy
from typing import Any

from api.services.actions_communes.enveloppe import Enveloppe
from api.services.commande import moteur

SUJETS_DU_PANIER = ("panier", "frais")
SUJETS_DE_LA_CARTE = ("carte", "article", "allergenes")
SUJETS_PRATIQUES = ("horaires", "paiement", "acces")


def lecture_sur_une_copie(p: dict[str, Any]) -> dict[str, Any]:
    """La copie sur laquelle une lecture s'exécute : jamais le panier de l'appel (E16)."""
    return copy.deepcopy(p)


async def _resultat_de_la_lecture(source: Any, copie: dict[str, Any], regles: Any, sujet: str, article: str | None, a_eviter: str | None, appel_id: str | None):
    if sujet in SUJETS_DU_PANIER:
        return await moteur.voir_commande(source, copie, regles)
    if sujet in SUJETS_DE_LA_CARTE:
        return await moteur.voir_produit(source, copie, regles, article, a_eviter if sujet == "allergenes" or a_eviter else None)
    if sujet == "delai":
        return await moteur.heure_annoncee(source, copie, regles, None)
    if sujet == "offres":
        return await moteur.remises_disponibles(source, copie, regles, demande=True, presse=False, refus=False, appel_id=appel_id)
    if sujet in SUJETS_PRATIQUES:
        return await moteur.etat_ouverture(source, copie, regles, None) if sujet == "horaires" else None
    return None


async def lire(source: Any, p: dict[str, Any], regles: Any, arguments: dict[str, Any], appel_id: str | None = None) -> dict[str, Any]:
    """Lit ``sujet`` (et l'article, ce qu'elle doit éviter) sans rien changer ; rend l'enveloppe, statut ``LU`` (ou ``INTROUVABLE``)."""
    sujet = str(arguments.get("sujet") or "").strip()
    article = (str(arguments.get("article") or "").strip() or None)
    a_eviter = (str(arguments.get("a_eviter") or "").strip() or None)
    r = await _resultat_de_la_lecture(source, lecture_sur_une_copie(p), regles, sujet, article, a_eviter, appel_id)
    if r is None:
        return Enveloppe("INTROUVABLE", resultats=[{"operation": "lire", "sujet": sujet}], faits={"sujet": sujet}, raison="rien_a_faire").vers_json()
    faits = {k: v for k, v in (r.faits or {}).items() if k != "panier"}
    statut = "LU" if r.statut in ("OK", "RETENU", "TROUVE", "LU") else ("INTROUVABLE" if r.statut == "INTROUVABLE" else "LU")
    return Enveloppe(statut, resultats=[{"operation": "lire", "sujet": sujet, "statut_du_module": r.statut}], faits=faits).vers_json()
