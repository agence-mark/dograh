"""[.mark] Lot 8 de cloture-code-avant-migration (22/10/2026) : le découpage en phrases de la voix, en français.

Pipecat 1.12 découpe le texte envoyé à la voix avec ``sentencex``, dans la langue de
``TTSSettings.language``. En ``fr``, ``sentencex`` 1.0.31 coupe après « M. », « Dr. », « St. » :
« Très bien M. » puis « Dupont, … ». Le texte vient des réponses de l'agent, écrites par le modèle,
donc ces formes arrivent à coup sûr. Ce module remplace le découpage pour toute voix d'un agent
français (``langue_agent_francaise``), sans toucher à ``pipecat/``.

Règle, simple et lisible :

1. une phrase finit à ``.`` ``!`` ``?`` ``…`` (suite de signes et guillemets fermants compris), suivi d'un
   espace puis d'un texte ;
2. ``!``, ``?`` et ``…`` coupent toujours ;
3. un point ne coupe PAS après une abréviation usuelle (M., Mme, Dr, St, av., etc., p. ex.), après une
   initiale (« J. Dupont »), ni quand le texte suivant commence par une minuscule ;
4. un nombre ou une heure restent entiers : « 3 h 30 », « 12,50 € », « 1.5 » (un point collé au chiffre
   suivant n'est jamais une fin).

⛔ Elle ne dépend pas de ``sentencex`` : seule la langue (``fr``) est posée sur la voix, pour le fournisseur.
La mécanique d'attente (un caractère de plus, puis le mot entier) reste celle de Pipecat, reprise telle quelle.
"""

from __future__ import annotations

import functools

from pipecat.utils.string import SENTENCE_ENDING_PUNCTUATION
from pipecat.utils.text.base_text_aggregator import Aggregation, AggregationType
from pipecat.utils.text.simple_text_aggregator import SimpleTextAggregator, _LookaheadState

from api.services.pipecat.conversion_nombres import langue_agent_francaise

_FINS = frozenset(".!?…")
_FERMANTS = frozenset("\"'»”’)]")

# Écrites avec leur casse : « Me » (maître) n'est pas le pronom « me », « M » n'est pas le mètre « m ».
_TITRES_EXACTS = frozenset(
    {"M", "MM", "Mme", "Mmes", "Mlle", "Mlles", "Me", "Mes", "Dr", "Drs", "Pr", "Prs", "Mgr", "St", "Ste"}
)
# Comparées en minuscules.
_ABREVIATIONS = frozenset(
    {
        "mme", "mmes", "mlle", "mlles", "dr", "drs", "pr", "prs", "mgr", "st", "ste",
        "av", "bd", "bld", "pl", "fg", "etc", "ex", "p", "d", "cf", "env", "approx", "tél", "tel", "cie", "sté",
    }
)  # fmt: skip


def _mot_avant(texte: str, fin: int) -> str:
    """Le mot collé juste avant la position ``fin`` (exclue), sans ponctuation ; vide s'il n'y en a pas."""
    debut = fin
    while debut > 0 and (texte[debut - 1].isalnum() or texte[debut - 1] in "-'’°"):
        debut -= 1
    return texte[debut:fin]


def _abreviation(mot: str) -> bool:
    if not mot:
        return False
    if mot in _TITRES_EXACTS or mot.lower() in _ABREVIATIONS:
        return True
    # Une initiale : « J. Dupont », « A.-M. Martin ».
    return len(mot) == 1 and mot.isalpha() and mot.isupper()


def fin_de_phrase(texte: str) -> int:
    """Position de la fin de la première phrase complète de ``texte``, ou 0 s'il n'y en a pas encore.

    « Complète » veut dire : un signe de fin, puis un espace, puis du texte (le début de la phrase suivante).
    """
    i, n = 0, len(texte)
    while i < n:
        if texte[i] not in _FINS:
            i += 1
            continue
        debut_suite = i
        while i < n and texte[i] in _FINS:
            i += 1
        fin_signes = i
        while i < n and texte[i] in _FERMANTS:
            i += 1
        fin = i
        if fin >= n or not texte[fin].isspace():
            continue
        suivant = fin
        while suivant < n and texte[suivant].isspace():
            suivant += 1
        if suivant >= n:
            continue
        seulement_un_point = texte[debut_suite:fin_signes] == "."
        if seulement_un_point:
            if _abreviation(_mot_avant(texte, debut_suite)) or texte[suivant].islower():
                continue
        return fin
    return 0


class AgregateurDePhrasesFrancais(SimpleTextAggregator):
    """``SimpleTextAggregator`` de Pipecat, avec ``fin_de_phrase`` à la place de ``sentencex``."""

    async def _check_sentence_with_lookahead(self, char: str) -> Aggregation | None:
        est_un_signe = char in SENTENCE_ENDING_PUNCTUATION
        resultat = None
        if self._advance_lookahead(char, is_punctuation=est_un_signe):
            # Même précaution que l'amont : un « ? » qui vient d'arriver ne compte pas dans la vérification
            # du signe précédent, il attend son propre mot suivant.
            candidat = self._text[:-1] if est_un_signe else self._text
            fin = fin_de_phrase(candidat)
            if fin:
                resultat = Aggregation(text=self._text[:fin].strip(" "), type=AggregationType.SENTENCE)
                self._text = self._text[fin:]
                self._lookahead_state = _LookaheadState.IDLE
        if est_un_signe:
            self._lookahead_state = _LookaheadState.AWAITING_CHARACTER
        return resultat


def poser_le_decoupage_francais(service) -> None:
    """Met l'agrégateur français sur une voix, en gardant son mode d'envoi (phrase ou mot à mot)."""
    if not hasattr(service, "_text_aggregator"):
        return
    service._text_aggregator = AgregateurDePhrasesFrancais(
        aggregation_type=service._text_aggregation_mode,
        language="fr",
    )


def decoupage_francais_si_agent_francais(fabrique):
    """Décorateur de la fabrique de voix : un agent français reçoit le découpage français, quel que soit le fournisseur."""

    @functools.wraps(fabrique)
    def enveloppe(user_config, *args, **kwargs):
        service = fabrique(user_config, *args, **kwargs)
        if langue_agent_francaise(getattr(user_config, "stt", None)):
            poser_le_decoupage_francais(service)
        return service

    return enveloppe
