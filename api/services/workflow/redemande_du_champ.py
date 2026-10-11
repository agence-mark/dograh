"""[.mark] Chantier postscriptum-et-communes, B5 : la phrase pose-t-elle la question d'un champ ?

En « porte, note, phrase », la note du tour écrit un champ, et la phrase peut en poser la question
de nouveau (runs 1048, 1051). Ce module ne dit qu'une chose : parmi les champs que la note vient
d'écrire, lequel la phrase redemande-t-elle ? Réponse ``None`` au moindre doute (un faux positif
coûte une phrase utile).

Le rapprochement ne vient que des données de l'agent : le NOM du champ et sa DESCRIPTION, tels que
le formulaire les déclare. Jamais une liste de mots d'un métier. Un champ est redemandé si une
phrase qui se termine par « ? » contient TOUS les mots de son nom (« commune_garage » : commune et
garage), ou, à défaut, TOUS les mots de sa description quand elle en compte trois au plus. Un mot
manquant : le rapprochement est incertain, la phrase reste dite. Rien n'existait déjà pour
rapprocher une question d'un champ (``derniere_question`` rend la réplique de l'agent, pas un
champ ; les étiquettes des étapes ne parlent qu'au modèle).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from api.services.workflow.fiche_au_fil_de_leau import _mots, _singulier

# Mots de liaison de la langue française, jamais d'un métier : ils ne départagent aucun champ.
_MOTS_DE_LIAISON = frozenset(
    "des les une aux par sur pour dans avec sans que qui quoi est sont votre vos mon "
    "ton son nos vous nous mes tes ses cet cette ces".split()
)
# Une description plus longue qu'un nom propre à un champ est une consigne, pas un nom : on ne
# l'exige pas mot à mot.
_MOTS_MAX_DE_LA_DESCRIPTION = 3


def _utiles(texte: str) -> set[str]:
    return {
        _singulier(m)
        for m in _mots(texte.replace("_", " "))
        if len(m) >= 3 and m not in _MOTS_DE_LIAISON
    }


def _questions(phrase: str) -> list[str]:
    """Les propositions qui se terminent par « ? » (une question posée, pas un mot cité) :
    « Merci pour le kilométrage, quelle est la marque ? » ne pose que la question de la marque."""
    return [q.strip() for q in re.findall(r"([^.!…?\n,;:]+)\?", phrase or "") if q.strip()]


def champ_redemande(
    phrase: str,
    champs_ecrits: Iterable[str],
    descriptions: Mapping[str, str],
) -> str | None:
    """Le premier des ``champs_ecrits`` (écrits par la note de ce tour) dont ``phrase`` pose
    la question, ou ``None``. ``descriptions`` : nom du champ -> description déclarée."""
    questions = [_utiles(q) for q in _questions(phrase)]
    if not questions:
        return None
    for champ in champs_ecrits:
        if champ not in descriptions:
            continue
        nom = _utiles(champ)
        description = _utiles(descriptions[champ] or "")
        candidats = []
        if nom:
            candidats.append(nom)
        if description and len(description) <= _MOTS_MAX_DE_LA_DESCRIPTION:
            candidats.append(description)
        if any(candidat <= question for candidat in candidats for question in questions):
            return champ
    return None
