"""Ce qui ne doit jamais sortir en clair des journaux techniques : le numéro de l'appelant et le jeton du flux audio.

Le numéro est gardé en entier dans la base et dans le portail du restaurateur ; seuls les
journaux le masquent (décision d'Evan, 23/11, point 1 de Tiao). On garde les deux derniers
chiffres : de quoi relier deux lignes d'un même appel, jamais de quoi rappeler la personne.
L'appel se retrouve par son identifiant (appel, canal ou exécution), écrit sur la même ligne.
"""

import logging
import re

_CHIFFRES = re.compile(r"\d")
_JETON_DU_FLUX = re.compile(r"(/telephony/ws/\d+/\d+/\d+/)[^\s\"?/]+")
_JETON_EN_REQUETE = re.compile(r"(token=)[^\s\"'&<>]+")


def masquer_numero(numero: object) -> str:
    """``+33612345678`` devient ``***78``. Vide ou inconnu : rendu tel quel, sans chiffre à cacher."""
    texte = "" if numero is None else str(numero)
    chiffres = _CHIFFRES.findall(texte)
    if not chiffres:
        return texte
    return "***" + "".join(chiffres[-2:])


def masquer_jeton_du_flux(texte: str) -> str:
    """Le jeton du flux audio d'un appel, dans le chemin d'une adresse (``.../ws/1/2/3/<jeton>``) ou en requête (``?token=``)."""
    return _JETON_EN_REQUETE.sub(r"\1***", _JETON_DU_FLUX.sub(r"\1***", texte))


class MasquerLeJetonDuFlux(logging.Filter):
    """Pour les journaux d'accès d'uvicorn, qui écrivent le chemin complet du flux audio."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masque = masquer_jeton_du_flux(message)
        if masque != message:
            record.msg, record.args = masque, ()
        return True
