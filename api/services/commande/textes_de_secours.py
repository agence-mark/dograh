"""[.mark] Plan final Partie 1, lot 7b-C1 : les textes de secours de la commande, un par refus du moteur.

Quand le modèle se tait deux fois sur un refus, le repli du code dit le refus (R = A, Evan, 25/11). Ce texte n'est JAMAIS donné au modèle : le modèle reçoit les faits du refus et
le dit avec ses mots. Chaque fonction ne lit que les faits publics du refus (ceux que la porte montre au modèle) : si le texte a besoin d'une valeur, c'est qu'un fait manque au refus,
jamais qu'il faut la lire ailleurs. Le module qui refuse écrit ses faits, puis ``_r(statut, faits, TS.nom(faits), manque)``.

Aucune règle du métier ici : un texte de secours ne fait que mettre des faits en mots.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from api.services.mots_dits import liste_dite, nombre_en_lettres

Faits = Mapping[str, Any]

_UNITE_DITE = re.compile(r"(?<![\w,.])(\d+(?:[,.]\d+)?)\s*(cl|ml|l|g|kg)(?![\w])", re.IGNORECASE)
_UNITES_EN_MOTS = {"cl": "centilitre", "ml": "millilitre", "l": "litre", "g": "gramme", "kg": "kilo"}


def _unites_dites(texte: str) -> str:
    """« 33 cl » -> « 33 centilitres », « 1,5 l » -> « 1,5 litre » : une unité abrégée n'est pas une parole (SA-52, appel 2604)."""
    def dite(m: re.Match) -> str:
        valeur = float(m.group(1).replace(",", "."))
        mot = _UNITES_EN_MOTS[m.group(2).casefold()]
        return f"{m.group(1)} {mot}{'s' if valeur >= 2 else ''}"

    return _UNITE_DITE.sub(dite, texte or "")


def _noms(valeurs: list[Any]) -> list[str]:
    """Les noms d'une liste de faits : une chaîne telle quelle, ou le ``nom`` d'un petit dictionnaire (« plus proches » : nom et prix)."""
    return [str(v["nom"] if isinstance(v, Mapping) else v) for v in valeurs]


# --------------------------------------------------------------------------- #
# articles.py : choisir, ajouter, retirer
# --------------------------------------------------------------------------- #


def question_d_un_choix(faits: Faits) -> str:
    """SA-52 (appel 2604) : la question d'un choix est une PHRASE à dire, jamais une étiquette (« taille pour X : 33 cl… ») : « Quelle taille pour votre X : 33 centilitres,
    1,5 litre ou 2 litres ? ». Sans accord deviné (« comme » ne dépend pas du genre du nom du groupe). Faits : ``question`` et ``article_de_la_carte``."""
    q, article_nom = faits["question"], faits["article_de_la_carte"]
    if not q["options"]:
        return f"Il faut préciser : {q['nom']}."
    options = liste_dite([_unites_dites(o) for o in q["options"]])
    if q["type"] == "declinaison":
        return f"{q.get('libelle') or 'Quel choix'} pour votre {article_nom} : {options} ?"
    nom = re.sub(r"\s*\([^)]*\)", "", q["nom"]).strip() or q["nom"]
    nom = _unites_dites(nom[:1].lower() + nom[1:])
    combien = ""
    if q.get("max", 1) > 1:
        combien = f", {nombre_en_lettres(q['max'])} au choix" if q.get("min") == q["max"] else f", jusqu'à {nombre_en_lettres(q['max'])}"
    return f"Pour votre {article_nom}, qu'est-ce que vous prenez comme {nom}{combien} : {options} ?"


def n_est_plus_disponible(faits: Faits) -> str:
    """Un choix, une taille : ce que dit son nom."""
    return f"{faits['nom']} n'est plus disponible."


def maximum_atteint(faits: Faits) -> str:
    """Faits : ``groupe``, ``option`` et ``maximum_atteint`` (le nombre dit : le maximum du groupe, ou celui de l'option)."""
    return f"{faits['groupe']} : pas plus de {nombre_en_lettres(faits['maximum_atteint'])} ; {faits['option']} n'est pas pris."


def ne_se_prend_pas_avec_des_choix(faits: Faits) -> str:
    return f"{faits['article']} ne se prend pas avec des choix."


def vous_voulez_dire(faits: Faits) -> str:
    return "Vous voulez dire : " + liste_dite(list(faits["candidats"])) + " ?"


def option_hors_carte(faits: Faits) -> str:
    """L'option dite n'existe pas pour l'article : la plus proche (``plus_proches``) ou, à défaut, ce qui se choisit (``choix_possibles``, au plus quatre noms)."""
    proches = _noms(faits.get("plus_proches") or [])
    debut = f"Je n'ai pas « {faits['dit']} » pour {faits['article']}."
    if proches:
        return f"{debut} Le plus proche : {liste_dite(proches)}."
    possibles = list(faits.get("choix_possibles") or [])
    return f"{debut} Ce qui se choisit : {liste_dite(possibles)}." if possibles else debut


def pour_quelle_etape(faits: Faits) -> str:
    return f"Pour quelle étape : {liste_dite(list(faits['etapes']))} ?"


def pas_dans_la_formule(faits: Faits) -> str:
    return f"Je n'ai pas « {faits['valeur']} » dans {faits['article']}."


def sur_lequel(faits: Faits) -> str:
    return "Sur lequel : " + liste_dite(list(faits["candidats"])) + " ?"
