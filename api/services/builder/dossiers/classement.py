"""[.mark] Builder, lot 3 (B47, B48) : où va chaque fait de la fiche ?

Trois places, jamais deux :

* ``objet``  : petit, critique, que l'agent peut devoir citer à tout moment, que le client voudra modifier lui-même
  (horaires, zone, marques, tarifs, numéros). Toujours injecté dans « Ce que tu sais » par ``{{nom}}`` : un fait doit
  TOUJOURS être présent, sinon le modèle peut ne pas le demander et inventer. Pas d'objet à déclencheur ;
* ``base``   : gros, rarement demandé (FAQ, catalogue, conditions). Consulté par l'outil de la base de connaissances ;
* ``regle``  : ce qui décide de la conduite de l'agent (étapes, conditions, interdits). Reste dans le prompt.

Le classement est choisi par le builder (ou corrigé par une personne) et s'affiche dans la carte de la fiche ; le CODE
tient les bornes : un fait trop gros n'est pas un objet (il dépasserait le plafond de l'objet), et un fait déjà dans la
base de connaissances ne devient pas aussi un objet (un fait, une place).

⛔ Les champs ci-dessous sont ceux de la structure de la fiche (``05-architecture.md`` § 4), pas du métier d'un client.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Literal

Classement = Literal["objet", "base", "regle"]
CLASSEMENTS: tuple[str, ...] = ("objet", "base", "regle")

# Au-delà, un fait ne peut pas être un objet : le plafond d'un objet est de 3 000 caractères (rendu compris).
OBJET_MAX_CARACTERES = 2500
# Sous cette taille, un fait classé « base » est un petit fait critique : on le signale (il devrait être un objet).
BASE_PETIT_SEUIL = 400

# Le classement par défaut des champs de la structure de la fiche (§ 4), quand le builder n'a rien choisi.
PAR_DEFAUT: dict[str, str] = {
    "motifs_d_appel": "regle",
    "regles": "regle",
    "regles_qui_decident": "regle",
    "horaires": "objet",
    "etablissements": "objet",
    "zone": "objet",
    "marques": "objet",
    "tarifs": "objet",
    "numeros": "objet",
    "numeros_et_transferts": "objet",
    "urgences": "regle",
    "urgences_et_dangers": "regle",
    "ne_dit_jamais": "regle",
    "outils": "regle",
    "outils_a_connecter": "regle",
    "lexique": "regle",
    "vocabulaire": "regle",
}


def taille_du_fait(valeur: Any) -> int:
    if isinstance(valeur, str):
        return len(valeur)
    return len(str(valeur))


def classement_effectif(nom: str, classement: str | None, valeur: Any) -> str:
    """Le classement posé, sinon celui du champ standard, sinon selon la taille (petit = objet, gros = base)."""
    if classement in CLASSEMENTS:
        return classement
    if nom in PAR_DEFAUT:
        return PAR_DEFAUT[nom]
    return "objet" if taille_du_fait(valeur) <= BASE_PETIT_SEUIL else "base"


def verifier(nom: str, classement: str | None, valeur: Any) -> str | None:
    """Une phrase de refus si le classement posé est impossible, ``None`` sinon."""
    if classement == "objet" and taille_du_fait(valeur) > OBJET_MAX_CARACTERES:
        return (
            f"« {nom} » is too large to be an object ({taille_du_fait(valeur)} characters, at most "
            f"{OBJET_MAX_CARACTERES}): put it in the knowledge base."
        )
    return None


def nom_d_objet(champ: str) -> str:
    """Le nom technique d'un objet (``^[a-z][a-z0-9_]{0,62}$``) tiré du nom d'une ligne de la fiche."""
    ascii_ = unicodedata.normalize("NFKD", champ).encode("ascii", "ignore").decode("ascii").lower()
    propre = re.sub(r"[^a-z0-9_]+", "_", ascii_).strip("_")
    if not propre or not propre[0].isalpha():
        propre = "f_" + propre
    return propre[:63]


def en_objet(champ: str, valeur: Any, libelle: str | None = None) -> dict[str, Any]:
    """Le fait en objet de l'agent (format de ``ObjetEnvoye``) : une valeur texte, ou une liste si la ligne en est une."""
    base: dict[str, Any] = {"nom": nom_d_objet(champ), "libelle": (libelle or champ.replace("_", " ").capitalize())[:200]}
    if isinstance(valeur, list) and valeur and all(isinstance(ligne, dict) for ligne in valeur):
        colonnes: list[str] = []
        for ligne in valeur:
            for cle in ligne:
                if str(cle) not in colonnes:
                    colonnes.append(str(cle))
        return {
            **base,
            "forme": "liste",
            "colonnes": [{"libelle": c[:100], "type": "texte", "ordre": i} for i, c in enumerate(colonnes[:50])],
            "lignes": [{"ordre": i, "valeurs": {str(k)[:100]: str(v) for k, v in ligne.items()}} for i, ligne in enumerate(valeur[:2000])],
        }
    if isinstance(valeur, list):
        texte = "\n".join(str(v) for v in valeur)
    elif isinstance(valeur, dict):
        texte = "\n".join(f"{k} : {v}" for k, v in valeur.items())
    else:
        texte = str(valeur)
    return {**base, "forme": "valeur", "type": "texte", "valeur": texte}
