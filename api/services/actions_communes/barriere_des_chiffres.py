"""[.mark] Chantier Partie 1, lot 6 : la barrière des chiffres sur toute phrase libre du modèle (B10 point 3, B11 point 4, B12 décision 1).

Les chiffres sont dits par le code (D5, D33). Une phrase du modèle (``a_dire`` comprise) qui porte un chiffre n'est jamais dite : elle est retenue et
le modèle repasse, avec dans l'état « Ta réponse précédente portait un chiffre : elle n'a pas été dite, et rien n'est changé. Les chiffres sont dits
par le code. » Règle de VALEUR, jamais de sens. Deux exemptions, chacune une règle nommée :

- les mots du code de remise de la même fiche (B10 point 3) : « le code VINGT » n'est pas un prix ;
- une valeur qu'elle a dite pendant l'appel (B12, ``valeur_dite_par_elle``, la SEULE fonction « elle l'a dit », D57) : de l'argent seulement si elle
  l'a dit en argent (« un billet de cinquante » couvre « cinquante euros » ; « deux reines » ne couvre jamais « deux euros ») ; un nombre, sous
  n'importe quel genre (« vers vingt heures » couvre « 20 heures »).

``sans_balisage`` (B10 point 4) : une phrase dite n'a ni balise, ni astérisque, ni retour à la ligne.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from api.services.actions_communes.forme import (
    CASE_D_UN_NOMBRE,
    CASE_DE_L_ARGENT,
    UNITES,
    norm,
    valeur_dite_par_elle,
    valeurs_et_places,
)

RAPPEL_DU_CHIFFRE = (
    "- Ta réponse précédente portait un chiffre : elle n'a pas été dite, et rien n'est changé. Les chiffres sont dits par le code."
)
CHIFFRE = re.compile(r"\d|€|\beuros?\b|centimes?", re.I)


def a_un_chiffre(texte: Any) -> bool:
    return bool(CHIFFRE.search(str(texte or "")))


def code_lu(texte: Any) -> str:
    """Un code dit ou écrit, sous une seule forme (``briques_b12.lire_code``) : majuscules, nombres en chiffres, sans séparateur."""
    s = norm(texte).upper()
    for mot, n in UNITES.items():
        s = re.sub(r"\b" + mot.upper() + r"\b", str(n), s)
    return re.sub(r"[^A-Z0-9]", "", s)


def sans_le_code(texte: str, code: str) -> str:
    """Le texte sans les mots qui forment ``code`` (au plus huit mots de suite)."""
    mots = (texte or "").split()
    i = 0
    while i < len(mots):
        for j in range(min(len(mots), i + 8), i, -1):
            if code_lu(" ".join(mots[i:j])) == code:
                del mots[i:j]
                break
        else:
            i += 1
    return " ".join(mots)


def sans_valeurs_dites(texte: str, paroles: Iterable[str]) -> str:
    """Le texte sans les valeurs qu'elle a dites (``valeur_dite_par_elle``) : ce qui reste passe la barrière."""
    paroles = [str(p) for p in paroles or () if p]
    places, mots = valeurs_et_places(texte)
    if not places:
        return texte
    garder = [True] * len(mots)
    for i, k, valeur, genre in places:
        case = CASE_DE_L_ARGENT if genre == "argent" else CASE_D_UN_NOMBRE
        if valeur_dite_par_elle(valeur, case, paroles):
            for x in range(i, k + 1):
                garder[x] = False
    if all(garder):
        return texte
    return " ".join(m for m, g in zip(mots, garder) if g)


def chiffre_dans_la_phrase(texte: Any, fiches: Iterable[dict] = (), paroles: Iterable[str] = ()) -> bool:
    """Vrai si la phrase du modèle porte un chiffre que le code doit dire : retenue (B11 point 4, B12 décision 1)."""
    reste = sans_valeurs_dites(str(texte or ""), paroles)
    for fiche in fiches or ():
        code = fiche.get("code_de_remise") if isinstance(fiche, dict) else None
        if isinstance(code, str) and code_lu(code):
            reste = sans_le_code(reste, code_lu(code))
    return a_un_chiffre(reste)


def sans_balisage(texte: str) -> str:
    """B10 point 4 : ni balise, ni astérisque, ni retour à la ligne dans une phrase dite."""
    t = re.sub(r"<[^>]{0,40}>", " ", str(texte or ""))
    t = re.sub(r"[*_#`]+", "", t)
    return re.sub(r"\s+", " ", t).strip()
