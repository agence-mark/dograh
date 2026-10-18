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

from api.services.nombres.lecture import (
    CODE_POSTAL,
    MONTANT,
    REFERENCE,
    _Phrase,
    _norm_mot,
    _valeur,
    lire_nombres,
)
from api.services.nombres.voix import en_mots

CLE_RELECTURE_DES_NUMEROS = "relecture_des_numeros"
CLE_NOMBRES_LUS = "nombres_lus"
TELEPHONE = "telephone"


def _chiffres(texte: str) -> str:
    return re.sub(r"\D", "", texte or "")


# Au-delà, ce n'est plus une relecture fautive du même numéro, c'est un autre numéro.
ECARTS_MAX = 2
# 🆕 modules-et-cerveaux (M6, run 1462) : une relecture ABÎMÉE (« zéro sept, cinquante,
# quatre-vingt-cinq, sept-huit, deux ») n'est plus un téléphone pour le module des nombres :
# une suite de nombres consécutifs, au moins sept chiffres, au plus trois écarts mesurés sur
# la plus longue suite commune avec le numéro de référence.
CHIFFRES_MIN_ABIMEE = 7
ECARTS_MAX_ABIMEE = 3
# Entre deux nombres d'une même relecture : espaces, virgules, tirets, points.
_ENTRE_DEUX = re.compile(r"[\s,.;\-]*")


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


def _chiffres_du_nombre(nombre) -> str:
    """Les chiffres d'un nombre lu, y compris une forme que la conversion laisse en mots
    (« deux », « sept-huit » : 2, 78). Vide si un mot n'est pas un nombre."""
    chiffres = _chiffres(nombre.ecrit)
    if chiffres:
        return chiffres
    mots = tuple(_norm_mot(m) for m in re.split(r"[\s\-]+", nombre.entendu) if m)
    entier = _valeur(mots)
    if entier:
        return entier[1]
    morceaux = [_valeur((m,)) for m in mots]
    return "".join(m[1] for m in morceaux) if morceaux and all(morceaux) else ""


def _plus_longue_suite_commune(a: str, b: str) -> int:
    precedente = [0] * (len(b) + 1)
    for x in a:
        ligne = [0]
        for j, y in enumerate(b):
            ligne.append(precedente[j] + 1 if x == y else max(precedente[j + 1], ligne[j]))
        precedente = ligne
    return precedente[-1]


def _relectures_abimees(texte: str, phrase, nombres, reference: str, dictes: set[str]):
    """Les relectures abîmées de ``reference`` : [(début, fin) en caractères]."""
    suites, suite = [], []
    for n in nombres:
        if n.type in (MONTANT, CODE_POSTAL, REFERENCE):
            if suite:
                suites.append(suite)
            suite = []
            continue
        if suite:
            fin_avant = phrase.jetons[suite[-1].fin - 1].fin
            if not _ENTRE_DEUX.fullmatch(texte[fin_avant : phrase.jetons[n.debut].debut]):
                suites.append(suite)
                suite = []
        suite.append(n)
    if suite:
        suites.append(suite)
    trouvees = []
    for suite in suites:
        morceaux = [_chiffres_du_nombre(n) for n in suite]
        if not all(morceaux):
            continue
        relu = "".join(morceaux)
        if (
            len(relu) < CHIFFRES_MIN_ABIMEE
            or not relu.startswith("0")
            or relu == reference
            or relu in dictes
        ):
            continue
        ecarts = max(len(relu), len(reference)) - _plus_longue_suite_commune(relu, reference)
        if ecarts > ECARTS_MAX_ABIMEE:
            continue
        trouvees.append(
            (phrase.jetons[suite[0].debut].debut, phrase.jetons[suite[-1].fin - 1].fin)
        )
    return trouvees


def corriger_relecture(
    texte: str, reference: str | None, contexte: dict | None = None
) -> str:
    """``texte`` dont le numéro de téléphone relu, s'il diffère de ``reference`` d'un
    ou deux chiffres et n'est aucun numéro dicté, porte les chiffres de ``reference``.
    M6 : de même pour une relecture abîmée (``_relectures_abimees``). Sinon ``texte`` tel quel."""
    if not texte or not reference or len(reference) != 10:
        return texte
    try:
        dictes = numeros_dictes(contexte)
        tous = lire_nombres(texte)
        if not tous:
            return texte
        phrase = _Phrase(texte)
        a_corriger = []
        for n in tous:
            if n.type != TELEPHONE:
                continue
            relu = _chiffres(n.ecrit)
            if len(relu) != 10 or relu == reference or relu in dictes:
                continue
            if sum(a != b for a, b in zip(relu, reference)) > ECARTS_MAX:
                continue
            a_corriger.append((phrase.jetons[n.debut].debut, phrase.jetons[n.fin - 1].fin))
        # M6 : les relectures que le module ne lit plus comme un téléphone.
        hors_telephones = [n for n in tous if n.type != TELEPHONE]
        a_corriger += _relectures_abimees(texte, phrase, hors_telephones, reference, dictes)
        sortie, curseur = [], 0
        for debut, fin in sorted(a_corriger):
            if debut < curseur:
                continue
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
