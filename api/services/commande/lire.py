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
from api.services.commande.resultat import Resultat

CLE_DU_PRIX_A_DIRE = "prix_a_dire"
CLE_DU_SUFFIXE = "suffixe_du_code"  # retirée par la porte avant le retour : jamais vue du modèle
SUJETS_DU_PANIER = ("panier", "frais")
SUJETS_DE_LA_CARTE = ("carte", "article", "allergenes")
SUJETS_PRATIQUES = ("horaires", "paiement", "acces")


def lecture_sur_une_copie(p: dict[str, Any]) -> dict[str, Any]:
    """La copie sur laquelle une lecture s'exécute : jamais le panier de l'appel (E16)."""
    return copy.deepcopy(p)


async def _resultat_de_la_lecture(source: Any, copie: dict[str, Any], regles: Any, sujet: str, article: str | None, a_eviter: str | None, appel_id: str | None):
    if sujet in SUJETS_DU_PANIER:
        return await moteur.voir_commande(source, copie, regles)
    if sujet == "carte" and not article:
        return await moteur.voir_la_carte(source, copie, regles)  # la liste fermée offre « carte » : sans article, elle rend les rubriques de la carte, jamais une erreur
    if sujet in SUJETS_DE_LA_CARTE:
        voir = moteur.METIER.voir_un_article
        if voir is None:
            return Resultat("INDISPONIBLE", {}, "")  # aucun module de métier n'a branché la lecture d'un article
        return await voir(source, copie, regles, article, a_eviter if sujet == "allergenes" or a_eviter else None)
    if sujet == "delai":
        return await moteur.heure_annoncee(source, copie, regles, None)
    if sujet == "offres":
        r = await moteur.remises_disponibles(source, copie, regles, demande=True, presse=False, refus=False, appel_id=appel_id)
        # lot 11 (conversation FOR2-B) : les formules sont des offres de la carte ; rendues avec les remises, jamais « rien » quand la carte en a
        lister = getattr(source, "formules_de_la_carte", None)
        formules = await lister() if lister is not None else []
        return Resultat(r.statut, {**r.faits, "formules": formules}, r.suggestion, r.manque) if formules else r
    if sujet in SUJETS_PRATIQUES:
        return await moteur.etat_ouverture(source, copie, regles, None) if sujet == "horaires" else None
    return None


async def lire(source: Any, p: dict[str, Any], regles: Any, arguments: dict[str, Any], appel_id: str | None = None) -> dict[str, Any]:
    """Lit ``sujet`` (et l'article, ce qu'elle doit éviter) sans rien changer ; rend l'enveloppe, statut ``LU`` (ou ``INTROUVABLE``)."""
    sujet = str(arguments.get("sujet") or "").strip()
    article = (str(arguments.get("article") or "").strip() or None)
    a_eviter = (str(arguments.get("a_eviter") or "").strip() or None)
    copie = lecture_sur_une_copie(p)
    r = await _resultat_de_la_lecture(source, copie, regles, sujet, article, a_eviter, appel_id)
    # B5 (D11) : seul le journal de ce qui est dit revient au panier de l'appel (de la tenue, pas une donnée de la commande) : ce que la lecture a
    # rendu au modèle (ce qui est servi avec) n'est pas redit par le code à l'ajout
    from api.services.actions_communes import journal_du_dit as J

    if copie.get(J.CLE) != p.get(J.CLE) and isinstance(copie.get(J.CLE), dict):
        p[J.CLE] = copie[J.CLE]
    if r is None:
        return Enveloppe("INTROUVABLE", resultats=[{"operation": "lire", "sujet": sujet}], faits={"sujet": sujet}, raison="rien_a_faire").vers_json()
    faits = {k: v for k, v in (r.faits or {}).items() if k not in ("panier", CLE_DU_PRIX_A_DIRE)}
    statut = "LU" if r.statut in ("OK", "RETENU", "TROUVE", "LU") else ("INTROUVABLE" if r.statut == "INTROUVABLE" else "LU")
    retour = Enveloppe(statut, resultats=[{"operation": "lire", "sujet": sujet, "statut_du_module": r.statut}], faits=faits).vers_json()
    prix_a_dire = (r.faits or {}).get(CLE_DU_PRIX_A_DIRE)
    if prix_a_dire:
        # PRX5 (D33) : le prix de l'article est dit par le code après la phrase du modèle ; la phrase n'est jamais montrée au modèle, la porte la range dans les textes du code
        retour[CLE_DU_SUFFIXE] = prix_a_dire
        retour["prix_dit_par_le_code_apres_ta_phrase"] = True
    return retour
