"""[.mark] La voix ne dit jamais un appel de fonction écrit en texte (C14, PB14).

Run 852 (banc de sortie de la fiche, 25/09/2026) : le modèle a ÉCRIT sa porte
au lieu de l'appeler -- « D'accord. … •demande_entretien() » -- trois fois, et la
voix l'a dit trois fois. L'appel est resté 14 tours à l'accueil ; client perdu.

Ce que fait ce module : avant la voix, tout morceau de texte qui a la forme d'un
appel de fonction (``nom_de_fonction()``, avec ou sans puce ``•``, ``*``, ``-``
devant) est retiré, et le retrait est journalisé
(``[.mark] appel de fonction retiré de la voix``).

⛔ Ce qu'il ne fait jamais
- **Exécuter** la fonction à la place du modèle : ce texte n'est pas un appel,
  et en faire un serait décider à la place du modèle.
- Toucher à l'historique ou à la transcription : c'est une TRANSFORMATION de
  Pipecat (``text_transforms``), qui ne change que le texte envoyé à la voix ; le
  contexte et la transcription gardent ce que le modèle a écrit (même choix que
  ``nombres_pour_la_voix.py``, qui l'explique).
- Coûter la phrase : Pipecat jette tout l'audio d'une phrase quand une
  transformation lève une exception. Toute erreur rend le texte intact.

⚠️ Une phrase qui n'est RIEN d'autre qu'un appel (au 852, « •demande_entretien() »
arrivait seule, après le point) passe par un FILTRE, pas par la transformation :
vidée par une transformation, elle partirait quand même à la voix, réduite à un
espace, et Pipecat attendrait un son qui ne vient pas ; vidée par un filtre, elle
est sautée proprement. Contrepartie : cette phrase-là ne reste pas dans
l'historique ni dans la transcription -- le journal garde le nom retiré.

⚠️ Une parenthèse ordinaire reste dite : « (10 h) », « le poêle (à bois) ». Seul
un nom collé à des parenthèses est pris : un nom de fonction (avec un « _ »), ou
n'importe quel nom suivi de parenthèses VIDES.
⚠️ Agrégation par phrase seulement : mot à mot, « demande » et « _entretien() »
arrivent séparément et ne se reconnaissent pas.
"""

from __future__ import annotations

import re

from loguru import logger

from pipecat.utils.text.base_text_filter import BaseTextFilter

# Un nom de fonction collé à ses parenthèses, et la puce qui le précède.
_APPEL = re.compile(
    r"(?:(?<=\s)|^)[•*\-–]?\s*"
    r"(?P<nom>[A-Za-z_][A-Za-z0-9_]*)\((?P<arguments>[^()]*)\)"
)


def _est_un_appel(correspondance: re.Match[str]) -> bool:
    return "_" in correspondance["nom"] or not correspondance["arguments"].strip()


def retirer_les_appels(texte: str) -> str:
    """``texte`` sans les appels de fonction écrits, espaces resserrés."""
    retires: list[str] = []

    def _remplacer(correspondance: re.Match[str]) -> str:
        if not _est_un_appel(correspondance):
            return correspondance.group(0)
        retires.append(correspondance["nom"])
        return ""

    propre = _APPEL.sub(_remplacer, texte)
    if not retires:
        return texte
    logger.warning(
        f"[.mark] appel de fonction retiré de la voix : {', '.join(retires)}"
    )
    return re.sub(r"[ \t]{2,}", " ", propre).strip()


async def retirer_appels_de_fonction(texte: str, _type: str = "*") -> str:
    """Transformation de Pipecat : ``texte`` sans appel de fonction. Jamais d'exception."""
    try:
        return retirer_les_appels(texte)
    except Exception as erreur:  # noqa: BLE001 -- la voix doit continuer
        logger.warning(f"[.mark] appels de fonction non retirés : {erreur!r}")
        return texte


class PhraseQuiNEstQuUnAppel(BaseTextFilter):
    """Filtre de la voix : une phrase qui n'est qu'un appel de fonction écrit est
    sautée (rendue vide) ; toute autre phrase passe intacte. Jamais d'exception."""

    async def filter(self, text: str) -> str:
        try:
            reste = retirer_les_appels(text)
            # Rien qu'un appel, ponctuation comprise (« •demande_entretien(). »).
            if reste != text and not re.search(r"[^\W_]", reste):
                return ""
        except Exception as erreur:  # noqa: BLE001 -- la voix doit continuer
            logger.warning(f"[.mark] appels de fonction non retirés : {erreur!r}")
        return text

    async def handle_interruption(self):
        pass

    async def reset_interruption(self):
        pass
