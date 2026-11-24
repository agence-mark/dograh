"""[.mark] Chantier Partie 1, lot 17 : les trous d'un gabarit (D11) et la façon de les remplir.

Deux sortes de ``{{nom}}`` dans les textes d'un gabarit, jamais confondues :

* les **trous** : remplis UNE fois, à l'installation, depuis le formulaire (``donnee``) ou par un calcul nommé (``calcul``) ;
* les **variables d'appel** : laissées telles quelles ; le code les pose à chaque appel (date, ouverture, adresse, zones…).

Un calcul est une fonction nommée et testée de ce module ; ses libellés sont des phrases du lieu, jamais un texte écrit pour l'occasion.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

MOTIF = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

# Le lieu où l'on mange (liste fermée du formulaire, niveau C) ; la valeur par défaut est la salle.
LIEUX_DES_TABLES = ("salle", "terrasse", "salle_et_terrasse", "aucun")
LIEU_PAR_DEFAUT = "salle"


class TrouManquant(Exception):
    """Un trou du gabarit sans valeur après le remplissage (jamais un texte envoyé avec un trou)."""


def noms_cites(texte: str) -> list[str]:
    """Les noms cités par ``{{…}}`` dans un texte, dans l'ordre, sans doublon."""
    vus: list[str] = []
    for m in MOTIF.finditer(texte or ""):
        if m.group(1) not in vus:
            vus.append(m.group(1))
    return vus


def remplir(texte: str, valeurs: Mapping[str, str], *, trous: set[str]) -> str:
    """Remplace chaque trou de ``trous`` par sa valeur ; une variable d'appel reste telle quelle. Un trou sans valeur : ``TrouManquant``."""

    def un(m: re.Match) -> str:
        nom = m.group(1)
        if nom not in trous:
            return m.group(0)
        if nom not in valeurs or valeurs[nom] is None:
            raise TrouManquant(nom)
        return str(valeurs[nom])

    return MOTIF.sub(un, texte)


# --------------------------------------------------------------------------- les calculs nommés


def _lieu(formulaire: Mapping[str, Any]) -> str:
    lieu = formulaire.get("lieu_des_tables") or LIEU_PAR_DEFAUT
    return lieu if lieu in LIEUX_DES_TABLES else LIEU_PAR_DEFAUT


def phrase_du_lieu(formulaire: Mapping[str, Any]) -> str:
    """Où l'on mange et ce qu'on commande, d'après les services ouverts (A), les missions et le lieu des tables (C). La partie « ce qu'on
    commande » reste la variable d'appel ``{{commande_types_ouverts}}`` : le code la dit d'après les types ouverts du moment."""
    services = set(formulaire.get("services") or ())
    sur_reservation = "prise_de_reservation" in set(formulaire.get("missions") or ())
    commande = bool(services & {"emporter", "livraison"})
    lieu = _lieu(formulaire)
    if "sur_place" not in services or lieu == "aucun":
        debut = "On ne mange pas sur place"
        return f"{debut} : on commande {{{{commande_types_ouverts}}}}." if commande else f"{debut}."
    debut = {
        "terrasse": "Pas de salle : on mange sur la terrasse",
        "salle": "On mange en salle",
        "salle_et_terrasse": "On mange en salle ou sur la terrasse",
    }[lieu]
    if sur_reservation:
        debut += ", sur réservation"
    return f"{debut}, ou on commande {{{{commande_types_ouverts}}}}." if commande else f"{debut}."


def places_du_lieu(formulaire: Mapping[str, Any]) -> str:
    return {
        "terrasse": "les places de la terrasse",
        "salle": "les places de la salle",
        "salle_et_terrasse": "les places de la salle et de la terrasse",
        "aucun": "les places",
    }[_lieu(formulaire)]


def une_table_du_lieu(formulaire: Mapping[str, Any]) -> str:
    return {
        "terrasse": "une table sur la terrasse",
        "salle": "une table",
        "salle_et_terrasse": "une table, en salle ou sur la terrasse",
        "aucun": "une table",
    }[_lieu(formulaire)]


CALCULS = {"phrase_du_lieu": phrase_du_lieu, "places_du_lieu": places_du_lieu, "une_table_du_lieu": une_table_du_lieu}


def _donnee(formulaire: Mapping[str, Any], chemin: str) -> Any:
    valeur: Any = formulaire
    for morceau in chemin.split("."):
        valeur = valeur.get(morceau) if isinstance(valeur, Mapping) else None
    return valeur


def valeurs_des_trous(definitions: Mapping[str, Mapping[str, str]], formulaire: Mapping[str, Any], textes_des_styles: Mapping[str, str]) -> dict[str, str]:
    """La valeur de chaque trou du gabarit pour ce formulaire (déjà complété de ses valeurs par défaut). Le style est le PARAGRAPHE de la
    bibliothèque, jamais le nom du style ni une prose libre (D23)."""
    sortie: dict[str, str] = {}
    for nom, d in definitions.items():
        if "constante" in d:
            sortie[nom] = d["constante"]  # un texte écrit UNE fois dans le gabarit, cité par plusieurs textes
        elif "calcul" in d:
            sortie[nom] = CALCULS[d["calcul"]](formulaire)
        elif d.get("liste_fermee") == "styles-agent":
            from api.services.gabarits import styles

            sortie[nom] = textes_des_styles[styles.valider(_donnee(formulaire, d["donnee"]))]
        else:
            valeur = _donnee(formulaire, d["donnee"])
            if valeur is not None:
                sortie[nom] = str(valeur)
    return sortie
