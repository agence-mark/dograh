"""[.mark] Mécanisme commun : la taille dite en mots usuels, rapprochée des déclinaisons d'un article (M118, appel 2598).

« deux grandes », « en petite », « la grande », « XL » : aucun de ces mots n'est le nom d'une déclinaison, mais chacun dit un RANG dans
l'ordre des déclinaisons de l'article. La table des mots est une DONNÉE standard (``mots_de_taille.json``), réglable par agent (une
surcouche ``{mot: rang}``, ``None`` retire un mot). Aucun mot n'est jugé dans le code : on lit la table.

L'ordre des déclinaisons est celui de leur prix (de la moins chère à la plus chère) ; deux déclinaisons au même prix : aucun ordre sûr,
rien n'est rapproché. Jamais un rapprochement deviné : ``milieu`` seulement quand il y a exactement trois déclinaisons, un rang avec une
seule déclinaison n'a pas de sens, deux rangs différents dans la même phrase : rien.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from api.db.bases_clients.recherche_liste import normaliser

PLUS_PETITE, MILIEU, PLUS_GRANDE = "plus_petite", "milieu", "plus_grande"
RANGS = frozenset({PLUS_PETITE, MILIEU, PLUS_GRANDE})
# Les mots qui annoncent une taille sans en être une (« grande taille », « format XL ») : retirés avec le mot de taille.
_ANNONCES = frozenset({"taille", "format"})


def _charger() -> dict[str, str]:
    brut = json.loads(Path(__file__).with_name("mots_de_taille.json").read_text(encoding="utf-8"))
    return {normaliser(mot): rang for mot, rang in brut.items() if not mot.startswith("_") and rang in RANGS}


MOTS_STANDARD: dict[str, str] = _charger()


def table(surcouche: Mapping[str, Any] | None = None) -> dict[str, str]:
    """La table standard, avec la surcouche de l'agent par-dessus (un rang inconnu est ignoré, ``None`` retire le mot)."""
    mots = dict(MOTS_STANDARD)
    for mot, rang in (surcouche or {}).items():
        if not isinstance(mot, str) or not normaliser(mot):
            continue
        if rang is None:
            mots.pop(normaliser(mot), None)
        elif rang in RANGS:
            mots[normaliser(mot)] = rang
    return mots


def rang_dit(texte: str | None, surcouche: Mapping[str, Any] | None = None, *, hors: frozenset[str] = frozenset()) -> str | None:
    """Le rang que le texte dit, s'il en dit un seul ; ``hors`` : des mots à ne pas lire (ceux du nom de l'article)."""
    mots = table(surcouche)
    rangs = {mots[m] for m in normaliser(texte or "").split() if m in mots and m not in hors}
    return rangs.pop() if len(rangs) == 1 else None


def sans_les_mots_de_taille(texte: str | None, surcouche: Mapping[str, Any] | None = None) -> str:
    """Le texte sans ses mots de taille (et sans « taille », « format » qui les annoncent). Sans mot de taille : le texte tel quel."""
    mots = table(surcouche)
    dits = (texte or "").split()
    if not any(normaliser(m) in mots for m in dits):
        return (texte or "").strip()
    return " ".join(m for m in dits if normaliser(m) not in mots and normaliser(m) not in _ANNONCES).strip(" ,")


def declinaison_par_rang(declinaisons: Sequence[dict], rang: str | None) -> dict | None:
    """La déclinaison (vendable) à ce rang dans l'ordre des prix ; ``None`` quand le rang ne désigne pas sûrement une seule déclinaison."""
    vendables = [d for d in declinaisons if d.get("vendable", True)]
    if rang not in RANGS or len(vendables) < 2:
        return None
    ordre = sorted(vendables, key=lambda d: d.get("prix") or 0)
    prix = [d.get("prix") or 0 for d in ordre]
    if len(set(prix)) != len(prix):
        return None  # deux déclinaisons au même prix : aucun ordre sûr
    if rang == PLUS_PETITE:
        return ordre[0]
    if rang == PLUS_GRANDE:
        return ordre[-1]
    return ordre[1] if len(ordre) == 3 else None


def declinaison_par_mot(declinaisons: Sequence[dict], texte: str | None, surcouche: Mapping[str, Any] | None = None, *, hors: frozenset[str] = frozenset()) -> dict | None:
    """La déclinaison que le mot de taille dit (« grande » : la plus chère), ou ``None`` s'il n'en désigne pas une seule."""
    return declinaison_par_rang(declinaisons, rang_dit(texte, surcouche, hors=hors))
