"""[.mark] Le juge v1 : la forme d'un verdict et sa vérification (pure, aucune lecture de base).

Gabarit du marché : une question par critère, réponse fermée, preuve obligatoire. Les mêmes règles valent pour le juge sur clé
d'API (``passes.py``) et pour Claude Code (``juge_ecrire``) : un verdict hors forme est REFUSÉ avec la raison, jamais corrigé.

* ``verdict`` : ``reussi`` | ``rate`` | ``non_verifiable`` (compte comme raté) ;
* ``replique`` : le numéro (à partir de 1) d'une réplique de la transcription ; ``preuve`` : une citation EXACTE de cette réplique
  (casse, accents et ponctuation ignorés), obligatoire pour ``reussi`` et ``rate`` ;
* ``non_verifiable`` : la preuve dit pourquoi (une phrase), sans citation obligatoire ;
* ``confiance`` entre 0 et 1.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

VERDICTS = ("reussi", "rate", "non_verifiable")

# Les 6 critères d'un bon agent vocal (secours : la grille versée en bibliothèque, ``criteres-types/grille-du-juge-v1``).
GRILLE_SECOURS = (
    "Suit le parcours sans erreur",
    "Respecte les consignes données",
    "Paraît naturel tout en respectant les consignes",
    "Sait agir avec les outils mis à sa disposition",
    "Extrait des données propres et utilisables",
    "Sort lui-même de son bug (impasse, boucle, hallucination) sans perdre l'appel entier",
)

PREUVE_MAX = 600


class VerdictRefuse(ValueError):
    """Un verdict hors forme : le message dit lequel et pourquoi (rendu tel quel à celui qui juge)."""


def normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFD", texte or "")
    sans_accents = "".join(c for c in sans_accents if unicodedata.category(c) != "Mn")
    return re.sub(r"\W+", " ", sans_accents.lower()).strip()


def verifier_un(brut: Any, lignes: list[tuple[str, str]], criteres: list[str]) -> dict[str, Any]:
    if not isinstance(brut, dict):
        raise VerdictRefuse("A verdict is an object {critere, verdict, replique, preuve, confiance}.")
    critere = str(brut.get("critere") or "").strip()
    if critere not in criteres:
        raise VerdictRefuse(f"Unknown criterion: {critere[:80]!r}. Judge only the criteria given.")
    verdict = brut.get("verdict")
    if verdict not in VERDICTS:
        raise VerdictRefuse(f"{critere!r}: verdict must be one of {', '.join(VERDICTS)}.")
    preuve = str(brut.get("preuve") or "").strip()
    if not preuve:
        raise VerdictRefuse(f"{critere!r}: the proof is required.")
    try:
        confiance = float(brut.get("confiance", 0.5))
    except (TypeError, ValueError):
        raise VerdictRefuse(f"{critere!r}: confidence is a number between 0 and 1.") from None
    if not 0 <= confiance <= 1:
        raise VerdictRefuse(f"{critere!r}: confidence is a number between 0 and 1.")
    replique = brut.get("replique")
    base = {"critere": critere, "verdict": verdict, "preuve": preuve[:PREUVE_MAX], "confiance": confiance}
    if verdict == "non_verifiable" and replique in (None, ""):
        return {**base, "replique": None}
    if isinstance(replique, bool) or not isinstance(replique, int) or not 1 <= replique <= len(lignes):
        raise VerdictRefuse(f"{critere!r}: the quoted line must exist (1 to {len(lignes)}).")
    if verdict != "non_verifiable" and normaliser(preuve) not in normaliser(lignes[replique - 1][1]):
        raise VerdictRefuse(f"{critere!r}: the proof is not an exact quote of line {replique}.")
    return {**base, "replique": replique}


def verifier(brut: Any, lignes: list[tuple[str, str]], criteres: list[str]) -> list[dict[str, Any]]:
    """Les verdicts vérifiés, un par critère, dans l'ordre de la grille. ``VerdictRefuse`` avec la raison sinon."""
    if not isinstance(brut, list) or not brut:
        raise VerdictRefuse("Send one verdict per criterion.")
    vus: dict[str, dict[str, Any]] = {}
    for entree in brut:
        v = verifier_un(entree, lignes, criteres)
        if v["critere"] in vus:
            raise VerdictRefuse(f"{v['critere']!r}: judged twice.")
        vus[v["critere"]] = v
    manquants = [c for c in criteres if c not in vus]
    if manquants:
        raise VerdictRefuse(f"Missing verdict for: {'; '.join(m[:80] for m in manquants)}.")
    return [vus[c] for c in criteres]


def reussi(verdicts: list[dict[str, Any]]) -> bool:
    """« non vérifiable » compte comme raté."""
    return bool(verdicts) and all(v["verdict"] == "reussi" for v in verdicts)


def numerotee(lignes: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [{"n": i + 1, "role": "agent" if r == "agent" else "appelant", "texte": t} for i, (r, t) in enumerate(lignes)]
