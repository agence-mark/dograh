"""[.mark] Plan postscriptum-note-d-abord (C10, Q4) : la relecture d'un numéro, corrigée par le code.

Banc du 07/10, run 1043 : l'agent relit « zéro six… » pour un numéro dicté en 07 ; c'est Pierre qui
corrige. Un modèle qui recopie dix chiffres se trompe ; le code, non. Comme pour le nom
(`filtre_nom_civilite.py`), la règle tient à l'endroit de l'action : juste avant la voix, sur la
phrase recomposée, le numéro relu est comparé au dernier numéro de téléphone que le module des
nombres a lu dans la parole de l'appelant ; s'ils diffèrent, les chiffres de l'appelant remplacent
ceux du modèle, écrits comme le modèle les avait écrits (en lettres par paires, ou en chiffres).

⛔ Ne touche que les numéros de téléphone (dix chiffres, deux lectures complètes) ; jamais un montant,
un code postal ni une référence. ⛔ Ne lève jamais : une relecture non corrigée ne coûte pas l'appel.
Option par agent (`relecture_des_numeros`), éteinte par défaut.

Revue du 08/10 : seule une relecture PROCHE du numéro de référence (un ou deux chiffres de
différence) est corrigée, et jamais un numéro que l'appelant a dicté (un mobile puis un fixe :
relire le mobile ne fait jamais dire le fixe ; le numéro du magasin n'est jamais touché).
"""

from __future__ import annotations

import re

from loguru import logger

from api.services.nombres.lecture import _Phrase, lire_nombres
from api.services.nombres.voix import en_mots

CLE_RELECTURE_DES_NUMEROS = "relecture_des_numeros"
CLE_NOMBRES_LUS = "nombres_lus"
TELEPHONE = "telephone"


def _chiffres(texte: str) -> str:
    return re.sub(r"\D", "", texte or "")


# Au-delà, ce n'est plus une relecture fautive du même numéro, c'est un autre numéro.
ECARTS_MAX = 2


def numeros_dictes(contexte: dict | None) -> set[str]:
    """Tous les numéros de téléphone (dix chiffres) lus dans la parole de l'appelant."""
    return {
        chiffres
        for trace in (contexte or {}).get(CLE_NOMBRES_LUS) or []
        if trace.get("type") == TELEPHONE
        and len(chiffres := _chiffres(trace.get("ecrit"))) == 10
    }


def numero_de_reference(contexte: dict | None) -> str | None:
    """Le dernier numéro de téléphone lu dans la parole de l'appelant (dix chiffres)."""
    for trace in reversed((contexte or {}).get(CLE_NOMBRES_LUS) or []):
        if trace.get("type") == TELEPHONE:
            chiffres = _chiffres(trace.get("ecrit"))
            if len(chiffres) == 10:
                return chiffres
    return None


def _par_paires_en_mots(chiffres: str) -> str:
    """« 0712 » → « zéro sept, douze » : chaque paire, « zéro » devant un chiffre seul."""
    paires = [chiffres[i : i + 2] for i in range(0, len(chiffres), 2)]
    mots = []
    for paire in paires:
        if paire.startswith("0"):
            mots.append(f"zéro {en_mots(paire[1])}")
        else:
            mots.append(en_mots(paire))
    return ", ".join(mots)


def corriger_relecture(
    texte: str, reference: str | None, contexte: dict | None = None
) -> str:
    """``texte`` dont le numéro de téléphone relu, s'il diffère de ``reference`` d'un
    ou deux chiffres et n'est aucun numéro dicté, porte les chiffres de ``reference``.
    Sinon ``texte`` tel quel."""
    if not texte or not reference or len(reference) != 10:
        return texte
    try:
        dictes = numeros_dictes(contexte)
        nombres = [n for n in lire_nombres(texte) if n.type == TELEPHONE]
        if not nombres:
            return texte
        phrase = _Phrase(texte)
        sortie, curseur = [], 0
        for n in nombres:
            relu = _chiffres(n.ecrit)
            if len(relu) != 10 or relu == reference or relu in dictes:
                continue
            if sum(a != b for a, b in zip(relu, reference)) > ECARTS_MAX:
                continue
            debut, fin = phrase.jetons[n.debut].debut, phrase.jetons[n.fin - 1].fin
            original = texte[debut:fin]
            if any(c.isalpha() for c in original):
                juste = _par_paires_en_mots(reference)
            else:
                juste = " ".join(reference[i : i + 2] for i in range(0, 10, 2))
            logger.info("[.mark] Read-back of a phone number corrected before the voice")
            sortie += [texte[curseur:debut], juste]
            curseur = fin
        if not sortie:
            return texte
        return "".join(sortie) + texte[curseur:]
    except Exception as erreur:  # noqa: BLE001 -- l'appel doit continuer
        logger.warning(f"[.mark] Read-back check failed, sentence kept: {erreur!r}")
        return texte
