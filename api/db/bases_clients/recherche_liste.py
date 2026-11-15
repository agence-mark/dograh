"""[.mark] Mécanisme commun : chercher un texte dans une liste fermée (module Restauration, lot 2).

Moteur MINIMAL et SÛR : ``RETENU`` seulement quand UN SEUL élément a, après nettoyage (casse, accents, ponctuation,
pluriel), exactement le même libellé ou le même synonyme que le texte. Rien d'approché n'est jamais « retenu » : il n'y a
donc aucun faux sûr. Deux éléments identiques après nettoyage : ``AMBIGU``. Sinon ``INTROUVABLE`` avec les plus proches.
Le moteur du lot 4 (rapidfuzz, son proche, synonymes, banc de dictées à zéro faux sûr) se branche à la place via
``poser_moteur`` ; la fonction ``chercher`` ne change pas de forme.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class Element:
    id: str
    libelle: str
    synonymes: tuple[str, ...] = ()
    categorie: str = ""  # le rangement de l'élément : dit QUEL élément quand deux portent le même nom
    variantes: tuple[str, ...] = ()  # ses déclinaisons (taille, contenant) : ce qui est dit se lit comme une option


def normaliser(texte: str) -> str:
    sans_accent = "".join(c for c in unicodedata.normalize("NFKD", texte.lower()) if not unicodedata.combining(c))
    mots = re.sub(r"[^a-z0-9]+", " ", sans_accent).split()
    return " ".join(m[:-1] if len(m) > 3 and m[-1] in "sx" else m for m in mots)


def _minimal(elements: Sequence[Element], texte: str, nb_candidats: int = 3) -> dict:
    voulu = normaliser(texte)
    if not voulu:
        return {"statut": "INTROUVABLE", "retenu": None, "candidats": []}
    egaux = [e for e in elements if voulu in {normaliser(e.libelle), *(normaliser(s) for s in e.synonymes)}]
    if len(egaux) == 1:
        return {"statut": "RETENU", "retenu": egaux[0].id, "candidats": [{"id": egaux[0].id, "libelle": egaux[0].libelle, "score": 1.0}]}
    if len(egaux) > 1:
        return {"statut": "AMBIGU", "retenu": None, "candidats": [{"id": e.id, "libelle": e.libelle, "score": 1.0} for e in egaux[:nb_candidats]]}
    proches = sorted(
        (
            {"id": e.id, "libelle": e.libelle, "score": round(max(SequenceMatcher(None, voulu, normaliser(n)).ratio() for n in (e.libelle, *e.synonymes)), 3)}
            for e in elements
        ),
        key=lambda c: -c["score"],
    )
    return {"statut": "INTROUVABLE", "retenu": None, "candidats": [c for c in proches if c["score"] >= 0.6][:nb_candidats]}


_moteur: Callable[[Sequence[Element], str], dict] = _minimal


def poser_moteur(moteur: Callable[[Sequence[Element], str], dict]) -> None:
    """Le lot 4 branche son moteur ici (même forme de retour)."""
    global _moteur
    _moteur = moteur


def chercher(elements: Sequence[Element], texte: str) -> dict:
    return _moteur(elements, texte)
