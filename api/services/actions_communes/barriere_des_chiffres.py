"""[.mark] Chantier Partie 1, lot 6 : la barrière des chiffres sur toute phrase libre du modèle (B10 point 3, B11 point 4, B12 décision 1).

Les chiffres sont dits par le code (D5, D33). Une phrase du modèle (``a_dire`` comprise) qui porte un chiffre n'est jamais dite : elle est retenue et
le modèle repasse, avec dans l'état « Ta réponse précédente portait un chiffre : elle n'a pas été dite, et rien n'est changé. Les chiffres sont dits
par le code. » Règle de VALEUR, jamais de sens. Trois exemptions, chacune une règle nommée :

- les mots du code de remise de la même fiche (B10 point 3) : « le code VINGT » n'est pas un prix ;
- les valeurs que portent les faits du retour de CE tour (``valeurs_des_faits`` : montants, heures, quantités) : le code les donne au modèle, il peut les dire ;
- une valeur qu'elle a dite pendant l'appel (B12, ``valeur_dite_par_elle``, la SEULE fonction « elle l'a dit », D57) : de l'argent seulement si elle
  l'a dit en argent (« un billet de cinquante » couvre « cinquante euros » ; « deux reines » ne couvre jamais « deux euros ») ; un nombre, sous
  n'importe quel genre (« vers vingt heures » couvre « 20 heures »).

``sans_balisage`` (B10 point 4) : une phrase dite n'a ni balise, ni astérisque, ni retour à la ligne.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from api.services.actions_communes.forme import (
    CASE_D_UN_NOMBRE,
    CASE_DE_L_ARGENT,
    DIZAINES,
    UNITES,
    norm,
    valeur_dite_par_elle,
    valeurs,
    valeurs_et_places,
)

RAPPEL_DU_CHIFFRE = (
    "- Ta réponse précédente portait un chiffre : elle n'a pas été dite, et rien n'est changé. Les chiffres sont dits par le code."
)
CHIFFRE = re.compile(r"\d|€|\beuros?\b|centimes?", re.I)


def a_un_chiffre(texte: Any) -> bool:
    return bool(CHIFFRE.search(str(texte or "")))


# P1 : les valeurs que le CODE dit (une heure, une durée, un prix, un pourcentage) : dites en lettres elles sont retenues comme en chiffres. Un compte d'articles en lettres
# (« vos deux Margherita ») reste dit : le banc l'a prouvé tel quel (égalité banc et fork, L06-41) et le code répète les quantités à la relecture.
UNITES_QUE_LE_CODE_DIT = frozenset({"heure", "heures", "h", "minute", "minutes", "seconde", "secondes"})
_DUREE_EN_MOTS = re.compile(r"(?<![a-z0-9])(?:(?:un|le|trois)\s+quarts?\s+d\s*heure|demi\s*heure|une?\s+(?:heure|minute|seconde)s?)(?![a-z0-9])")
_POURCENTAGE = re.compile(r"(?<!\w)pour\s*cent(?!\w)|%", re.I)


def a_un_nombre_en_lettres_que_le_code_dit(texte: Any) -> bool:
    """P1 (lot 19 bis) : un nombre dit EN LETTRES que le code doit dire : un prix (suivi d'une unité d'argent, ou deux nombres collés qui ne font pas un nombre : « douze cinquante »),
    une heure ou une durée (« vingt heures quinze », « trente minutes »), un pourcentage (« dix pour cent »). Même lecteur de nombres que « elle l'a dit »
    (``forme.valeurs_et_places``, une seule norme, méthode § 12.2) : le prompt impose les heures en lettres, et la garde ne voyait que les chiffres."""
    texte = str(texte or "")
    if _DUREE_EN_MOTS.search(norm(texte)):
        return True  # Pierre 12 (P1) : « dans un quart d'heure », « une demi-heure », « dans une heure » : une durée que le code dit ; « une » seul n'est pas un nombre pour la lecture des valeurs
    if _POURCENTAGE.search(norm(texte).replace("pour cent", " pour cent ")) and valeurs_et_places(texte)[0]:
        return True
    places, mots = valeurs_et_places(texte)
    for debut, fin, _valeur, genre in places:
        if genre == "argent":
            return True
        if fin + 1 < len(mots) and mots[fin + 1] in UNITES_QUE_LE_CODE_DIT:
            return True
        groupe = mots[debut:fin + 1]
        if any(a in UNITES and UNITES[a] >= 2 and b in DIZAINES and not (a == "quatre" and b in ("vingt", "vingts")) for a, b in zip(groupe, groupe[1:])):
            return True  # « douze cinquante » : ce n'est pas un nombre, c'est un prix ou une heure dite à la française
    return False


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


def valeurs_des_faits(faits: Any) -> list[str]:
    """Les valeurs que portent des faits, écrites comme une parole que ``valeurs_et_places`` sait lire : un entier est une quantité ET un montant en centimes (``montant_en_lettres``),
    un texte se lit tel quel. Le même lecteur que pour « elle l'a dit » (une seule norme) : ce que les faits portent peut être dit par le modèle, rien d'autre."""
    from api.services.mots_dits import montant_en_lettres

    if isinstance(faits, bool) or faits is None:
        return []
    if isinstance(faits, int):
        return [str(faits), montant_en_lettres(faits)] if faits >= 0 else []
    if isinstance(faits, float):
        return valeurs_des_faits(round(faits))
    if isinstance(faits, str):
        return [faits] if any(c.isdigit() for c in faits) or valeurs_et_places(faits)[0] else []
    if isinstance(faits, dict):
        return [v for x in faits.values() for v in valeurs_des_faits(x)]
    if isinstance(faits, (list, tuple)):
        return [v for x in faits for v in valeurs_des_faits(x)]
    return []


def chiffre_dans_la_phrase(texte: Any, fiches: Iterable[dict] = (), paroles: Iterable[str] = (), faits: Any = ()) -> bool:
    """Vrai si la phrase du modèle porte un chiffre que le code doit dire : retenue (B11 point 4, B12 décision 1). ``faits`` : les faits du retour de ce tour, dont les valeurs
    sont dites sans être retenues (constat 0.1 du lot 7b)."""
    reste = sans_valeurs_dites(str(texte or ""), [*(paroles or ()), *valeurs_des_faits(faits)])
    for fiche in fiches or ():
        code = fiche.get("code_de_remise") if isinstance(fiche, dict) else None
        if isinstance(code, str) and code_lu(code):
            reste = sans_le_code(reste, code_lu(code))
    return (a_un_chiffre(reste) or a_un_nombre_en_lettres_que_le_code_dit(reste))


def porte_les_chiffres(phrase: Any, attendus: Mapping[str, Any]) -> bool:
    """C6 (P2, décision d'Evan 25/11) : la phrase du modèle porte-t-elle chacune des valeurs que le code vérifie (la réservation : ``personnes`` et ``heure``) ? Une valeur
    attendue est dite comme les faits la donnent (« quatre personnes », « vingt heures ») ; ses nombres se lisent avec le même lecteur que « elle l'a dit » (``forme.valeurs``),
    une valeur sans nombre (« midi ») se cherche telle quelle. Une valeur attendue vide n'est pas exigée. Règle de VALEUR, jamais de sens."""
    dites = valeurs(phrase)
    net = norm(phrase)
    for attendu in attendus.values():
        if attendu is None or not str(attendu).strip():
            continue
        voulues = valeurs(attendu)
        if voulues and not all(v in {valeur for valeur, _ in dites} for v, _ in voulues):
            return False
        if not voulues and norm(attendu) not in net:
            return False
    return True


def sans_balisage(texte: str) -> str:
    """B10 point 4 : ni balise, ni astérisque, ni retour à la ligne dans une phrase dite."""
    t = re.sub(r"<[^>]{0,40}>", " ", str(texte or ""))
    t = re.sub(r"[*_#`]+", "", t)
    return re.sub(r"\s+", " ", t).strip()
