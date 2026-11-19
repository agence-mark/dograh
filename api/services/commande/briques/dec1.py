"""[.mark] Brique DEC1 : la déclinaison nommée, un prix par déclinaison (inventaire, famille 2).

La question d'une déclinaison absente est numérotée par le code et porte le MOT DE LA CARTE : le libellé que le restaurateur a écrit
(``libelle_question``), sinon le mot du type que la carte dit (taille, version, pièces, contenance...), sinon « taille » (carte ancienne). Aucun mot
écrit dans la cuisine (E17) : ``types_de_declinaison.json`` est une donnée, comme ``mots_de_taille.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from api.services.commande.briques.registre import Brique, enregistrer

_TYPES: dict[str, Any] = json.loads(Path(__file__).resolve().parent.parent.joinpath("types_de_declinaison.json").read_text(encoding="utf-8"))


def mot_de_la_question(declinaisons: list[dict]) -> dict[str, str]:
    """``{"nom": ..., "question": ...}`` : le libellé de la carte d'abord (la première déclinaison qui en a un), puis le type que la carte dit (le premier
    déclaré), puis le type par défaut. Le « nom » est ce que la question appelle ce qu'elle demande (« taille », « pièces »)."""
    for d in declinaisons:
        libelle = " ".join(str(d.get("libelle_question") or "").split())
        if libelle:
            return {"nom": libelle, "question": libelle}
    genre = next((d["type"] for d in declinaisons if d.get("type") in _TYPES and d.get("type") != "defaut"), _TYPES["defaut"])
    return dict(_TYPES[genre])


def brique_dec1_demander_la_declinaison(declinaisons: list[dict]) -> dict[str, Any]:
    """La question numérotée de la déclinaison encore absente : ses choix sont les déclinaisons vendables et pas en rupture, dans l'ordre de la carte."""
    noms = [d["nom"] for d in declinaisons if d["vendable"] and not d["rupture"]]
    mot = mot_de_la_question(declinaisons)
    return {"type": "declinaison", "nom": mot["nom"], "libelle": mot["question"], "min": 1, "max": 1, "chemin": [], "options": noms}


def _sans(carte: dict) -> dict:
    for p in carte["produits"]:
        for d in p["declinaisons"]:
            d["type"], d["libelle_question"] = None, None
    return carte


enregistrer(Brique(
    "DEC1", "declinaison", "C", (("declinaisons", "type"), ("declinaisons", "libelle_question")), brique_dec1_demander_la_declinaison,
    change_la_fiche_du_modele=True, vue_sur_carte=True, sans_la_brique=_sans, carte_d_essai="briques/DEC1",
    phrase="la question numérotée d'une déclinaison absente porte le mot de la carte",
))
