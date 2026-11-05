"""[.mark] Partie 3, N3b : le résumé d'un appel (une ou deux phrases), dans la liste des appels et sur la page d'un appel.

Deux sources, dans cet ordre :

1. la **synthèse de l'après-appel** (``annotations['mark_apres_appel']['synthese']``) quand elle existe : on la réduit à ses deux
   premières phrases, aucun appel de modèle de plus ;
2. à défaut, un **résumé court écrit par un modèle** (``annotations['resume_appel']``), seulement quand le réglage « Résumé
   d'appel » est allumé (ÉTEINT par défaut) ; sa dépense se range dans la dépense du mois des rôles (``budget_roles``, rôle
   ``resume``), jamais dans un second compteur.

La lecture (``lire``) est pure : elle ne fait aucune requête et ne lève jamais. La production est dans ``generation``.
"""

from __future__ import annotations

import re
from typing import Any

CLE_ANNOTATION = "resume_appel"
CLE_SYNTHESE = "mark_apres_appel"  # voir ``db/apres_appel_client.CLE_ANNOTATION`` (même bloc, champ « synthese »)
PHRASES_MAX = 2
CARACTERES_MAX = 260

# Une fin de phrase : un signe fort, des espaces, puis une majuscule (ou un guillemet ouvrant) : « M. Dupont » ne coupe pas.
_FIN_DE_PHRASE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-ÖØ-Þ«\"“(])")


_ABREVIATIONS = {"m", "mme", "mlle", "mr", "dr", "me", "pr", "st", "ste", "n", "tel", "tél", "cf", "etc"}


def _phrases(texte: str) -> list[str]:
    """Le texte coupé en phrases ; un point après une abréviation (« M. », « Mme. ») ou une initiale ne finit pas la phrase."""
    morceaux: list[str] = []
    debut = 0
    for coupure in _FIN_DE_PHRASE.finditer(texte):
        precedent = texte[debut : coupure.start()].rsplit(" ", 1)[-1].rstrip(".!?…").lower()
        if texte[coupure.start() - 1] == "." and (precedent in _ABREVIATIONS or len(precedent) == 1):
            continue
        morceaux.append(texte[debut : coupure.start()])
        debut = coupure.end()
    morceaux.append(texte[debut:])
    return morceaux


def resume_court(texte: Any, *, phrases: int = PHRASES_MAX, caracteres: int = CARACTERES_MAX) -> str | None:
    """Les ``phrases`` premières phrases du texte, coupées au mot près si elles dépassent ``caracteres`` ; ``None`` si vide. Pur."""
    brut = " ".join(str(texte or "").split())
    if not brut:
        return None
    court = " ".join(_phrases(brut)[:phrases])
    if len(court) > caracteres:
        court = court[:caracteres].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return court


def lire(annotations: Any) -> dict[str, str] | None:
    """Le résumé d'un appel d'après ses annotations : ``{"texte", "source"}`` (source « synthese » ou « modele »), ou ``None``. Pur."""
    if not isinstance(annotations, dict):
        return None
    bloc = annotations.get(CLE_SYNTHESE)
    texte = resume_court(bloc.get("synthese")) if isinstance(bloc, dict) else None
    if texte:
        return {"texte": texte, "source": "synthese"}
    propre = annotations.get(CLE_ANNOTATION)
    texte = resume_court(propre.get("texte")) if isinstance(propre, dict) else None
    return {"texte": texte, "source": "modele"} if texte else None


def champs(annotations: Any) -> dict[str, str | None]:
    """Les deux champs que rendent la liste et la page d'un appel : ``resume`` et ``resume_source`` (``None`` sans résumé). Pur."""
    lu = lire(annotations)
    return {"resume": lu["texte"], "resume_source": lu["source"]} if lu else {"resume": None, "resume_source": None}
