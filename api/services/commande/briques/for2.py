"""[.mark] Brique FOR2 : la formule à étapes au choix (inventaire, famille 5 ; 12 cartes sur 44).

Une étape à la fois : la première étape encore à choisir ouvre UNE question numérotée de type ``etape`` (``formule_b12.py`` ``_ouvrir_etape``) ; c'est le modèle qui
la pose, avec ses mots ; sa réponse va dans ``reponse.valeurs`` (``sens`` caché) et se range sur l'étape de la question, et sur elle seule. Une étape facultative
(``obligatoire`` faux) n'est jamais demandée.
"""

from __future__ import annotations

from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

TYPE_DE_LA_QUESTION = "etape"
RAISON = "etape_a_choisir"
A_FAIRE = "demande-lui ce choix en une question, avec tes mots"
REPONSES = ("son choix, dans valeurs",)  # banc B10 (``etape_forme``) : pas d'accepte ni de refuse, son choix dans valeurs


def brique_for2_une_etape_a_la_fois(groupe: dict[str, Any], chemin: list[str]) -> dict[str, Any]:
    """La question de l'étape encore à choisir (la première, dans l'ordre de la formule) : ses choix sont les options vendables et pas en rupture."""
    return {
        "type": TYPE_DE_LA_QUESTION, "groupe": groupe["id"], "nom": groupe["nom"], "min": groupe["min"], "max": groupe["max"], "chemin": list(chemin),
        "options": [o["nom"] for o in groupe["options"] if o["vendable"] and not o["rupture"]], "raison": RAISON,
    }


def _sans(carte: dict) -> dict:
    for f in carte["formules"]:
        for ligne in f["lignes"]:
            ligne["obligatoire"] = False
    return carte


enregistrer(Brique(
    "FOR2", "formules", "C", (("formules", "lignes"),), brique_for2_une_etape_a_la_fois,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/FOR2",
    phrase="la question numérotée d'une étape à choisir ; sa réponse dans valeurs",
))
