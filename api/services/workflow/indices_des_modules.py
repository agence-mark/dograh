"""[.mark] Plan postscriptum-note-d-abord (S2) : les indices des modules de donnée.

Sur la dernière parole de l'appelant, avant le modèle, nos modules repèrent ce qui est
dit ; une ligne est ajoutée à l'état de la fiche montré au modèle :

    Repéré dans sa dernière phrase (indices, rien n'est noté) : appareil = insert ; marque_appareil = Jøtul

🔑 Rien n'est écrit dans la fiche (Q3) : c'est le modèle qui note. L'indice l'aide à voir,
au tour même, ce que la personne vient de dire (cause du banc du 07/10 : redemandes).

⛔ Aucun mot de métier : les valeurs viennent des listes de la fiche, les noms du lexique
de l'organisation, les communes, nombres et épellations des traces que les modules de
lecture de l'appelant ont déjà écrites pour ce tour (``tour`` = tour de l'appelant).
⛔ Ne lève jamais : un indice manquant ne coûte pas l'appel.
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from api.schemas.lexique_metier import normaliser_terme

ENTETE_INDICES = "Repéré dans sa dernière phrase (indices, rien n'est noté) : "
# Une valeur de liste trop courte (« oui », « non ») se lit dans toute réponse : jamais un indice.
LONGUEUR_MIN_VALEUR = 4
# Les traces des modules de lecture de l'appelant (``lecture_appelant.py``).
CLE_COMMUNES, CLE_NOMBRES, CLE_EPELLATIONS = (
    "communes_verifiees",
    "nombres_lus",
    "epellations_lues",
)
# Les nombres dont la lecture est un indice (les autres restent dans la parole annotée).
TYPES_DE_NOMBRES = {"telephone": "téléphone", "code_postal": "code postal"}


def _trouve(forme: str, texte: str) -> list[tuple[int, int]]:
    """Où ``forme`` (normalisée) apparaît en mots entiers dans ``texte`` (normalisé)."""
    if not forme:
        return []
    return [
        (m.start(), m.end())
        for m in re.finditer(rf"(?<![a-z0-9]){re.escape(forme)}(?![a-z0-9])", texte)
    ]


def _plus_longues(candidats: list[tuple[int, int, str]]) -> list[str]:
    """Les valeurs trouvées, la plus longue d'abord, sans chevauchement (« poêle à
    granulés » l'emporte sur « poêle »), dans l'ordre de la phrase."""
    pris: list[tuple[int, int, str]] = []
    for debut, fin, valeur in sorted(candidats, key=lambda c: c[0] - c[1]):
        if all(fin <= d or debut >= f for d, f, _ in pris):
            pris.append((debut, fin, valeur))
    return list(dict.fromkeys(v for _, _, v in sorted(pris)))


def _valeurs_des_listes(reglages: Any, texte: str) -> list[str]:
    indices = []
    for champ in reglages.champs:
        candidats = [
            (d, f, valeur)
            for valeur in champ.valeurs or []
            if len(normaliser_terme(valeur)) >= LONGUEUR_MIN_VALEUR
            for d, f in _trouve(normaliser_terme(valeur), texte)
        ]
        valeurs = _plus_longues(candidats)
        if valeurs:
            indices.append(f"{champ.nom} = {' ou '.join(valeurs)}")
    return indices


def _termes_du_lexique(reglages: Any, texte: str) -> list[str]:
    """Les noms du lexique dits (type « nom », jamais un mot du métier), rangés au
    champ que le lexique lit (s'il n'y en a qu'un), hors valeurs de liste."""
    valeurs = {
        normaliser_terme(v) for champ in reglages.champs for v in champ.valeurs or []
    }
    candidats = [
        (d, f, officiel)
        for forme, officiel in (reglages.termes_du_lexique or {}).items()
        if forme not in valeurs
        and len(forme) >= LONGUEUR_MIN_VALEUR
        and officiel in (getattr(reglages, "noms_du_lexique", None) or ())
        for d, f in _trouve(forme, texte)
    ]
    termes = _plus_longues(candidats)
    if not termes:
        return []
    lecteurs = [c.nom for c in reglages.champs if c.lecteur_effectif == "lexique"]
    cle = lecteurs[0] if len(lecteurs) == 1 else "nom du lexique"
    return [f"{cle} = {' ou '.join(termes)}"]


def _traces_du_tour(fiche: dict, tour: Any) -> list[str]:
    """Ce que les modules de lecture ont trouvé à ce tour de l'appelant."""
    if tour is None:
        return []
    indices = []
    for trace in fiche.get(CLE_COMMUNES) or []:
        retenue = trace.get("commune_retenue") if trace.get("tour") == tour else None
        if retenue:
            codes = "/".join(retenue.get("codes_postaux") or [])
            indices.append(f"commune = {retenue['nom']}" + (f" ({codes})" if codes else ""))
    for trace in fiche.get(CLE_NOMBRES) or []:
        nom = TYPES_DE_NOMBRES.get(trace.get("type"))
        if trace.get("tour") == tour and nom and trace.get("ecrit"):
            indices.append(f"{nom} = {trace['ecrit']}")
    for trace in fiche.get(CLE_EPELLATIONS) or []:
        if trace.get("tour") == tour and trace.get("epele"):
            indices.append(f"épelé = {trace['epele']}")
    return indices


def indices_des_modules(
    reglages: Any, parole: str | None, fiche: dict, tour: Any = None
) -> str | None:
    """La ligne d'indices pour la dernière parole de l'appelant, ou ``None``."""
    try:
        if not getattr(reglages, "indices_des_modules", False) or not parole:
            return None
        texte = normaliser_terme(parole)
        indices = list(
            dict.fromkeys(
                [
                    *_valeurs_des_listes(reglages, texte),
                    *_termes_du_lexique(reglages, texte),
                    *_traces_du_tour(fiche, tour),
                ]
            )
        )
        return ENTETE_INDICES + " ; ".join(indices) if indices else None
    except Exception as erreur:  # noqa: BLE001 -- un indice ne coûte jamais l'appel
        logger.warning(f"[fiche] indices des modules non calculés : {erreur!r}")
        return None
