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
# une suite de nombres consécutifs écrits de la même façon (tout en lettres ou tout en
# chiffres), de sept à onze chiffres, à au plus deux chiffres changés, ajoutés ou retirés
# du numéro de référence (distance d'édition). Revue du 18/10 : la plus longue suite commune
# laissait passer un autre numéro du même secteur ; le point menait à la phrase suivante.
CHIFFRES_MIN_ABIMEE = 7
CHIFFRES_MAX_ABIMEE = 11
ECARTS_MAX_ABIMEE = 2
# Entre deux nombres d'une même relecture : espaces, virgules, tirets. Jamais un point.
_ENTRE_DEUX = re.compile(r"[\s,;\-]*")


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


def _distance(a: str, b: str) -> int:
    """Chiffres à changer, ajouter ou retirer pour passer de ``a`` à ``b``."""
    precedente = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        ligne = [i]
        for j, y in enumerate(b, 1):
            ligne.append(
                min(precedente[j] + 1, ligne[j - 1] + 1, precedente[j - 1] + (x != y))
            )
        precedente = ligne
    return precedente[-1]


def _en_lettres(texte: str) -> bool:
    return any(c.isalpha() for c in texte)


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
            if not _ENTRE_DEUX.fullmatch(
                texte[fin_avant : phrase.jetons[n.debut].debut]
            ) or _en_lettres(n.entendu) != _en_lettres(suite[-1].entendu):
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
        # Le début de la suite le plus proche du numéro ; à égalité, le plus court.
        meilleur = None
        for k in range(1, len(suite) + 1):
            relu = "".join(morceaux[:k])
            if len(relu) > CHIFFRES_MAX_ABIMEE:
                break
            if len(relu) < CHIFFRES_MIN_ABIMEE or not relu.startswith("0"):
                continue
            ecarts = _distance(relu, reference)
            if meilleur is None or ecarts < meilleur[0]:
                meilleur = (ecarts, k, relu)
        if meilleur is None:
            continue
        ecarts, k, relu = meilleur
        if ecarts > ECARTS_MAX_ABIMEE or relu == reference or relu in dictes:
            continue
        trouvees.append(
            (
                phrase.jetons[suite[0].debut].debut,
                phrase.jetons[suite[k - 1].fin - 1].fin,
            )
        )
    return trouvees


# 🆕 fiabilite-orchestration (lot 7, R16, run 1466) : un numéro relu chiffre par chiffre, séparé par des
# virgules (« sept, sept, huit, cinq, deux, sept, trois, quatre, neuf », sans le zéro), n'est pas
# lu comme un téléphone par le module des nombres (le premier « sept » y est une référence) :
# une relecture abîmée de plus. Une suite de sept à onze chiffres dits un par un (en lettres ou en
# chiffres), à au plus deux chiffres changés, ajoutés ou retirés du numéro de référence.
_CHIFFRES_DITS = {
    "zéro": "0", "zero": "0", "un": "1", "deux": "2", "trois": "3", "quatre": "4",
    "cinq": "5", "six": "6", "sept": "7", "huit": "8", "neuf": "9",
}  # fmt: skip
_UN_CHIFFRE = r"(?<![\w])(?:\d|" + "|".join(_CHIFFRES_DITS) + r")(?![\w])"
_SUITE_DE_CHIFFRES = re.compile(
    rf"{_UN_CHIFFRE}(?:[\s,;\-]+{_UN_CHIFFRE})+", re.IGNORECASE
)


def _relectures_chiffre_par_chiffre(texte: str, reference: str, dictes: set[str]):
    """Les relectures de ``reference`` dites un chiffre à la fois : [(début, fin) en caractères]."""
    trouvees = []
    for suite in _SUITE_DE_CHIFFRES.finditer(texte):
        relu = "".join(
            _CHIFFRES_DITS.get(jeton.lower(), jeton)
            for jeton in re.findall(_UN_CHIFFRE, suite.group(), re.IGNORECASE)
        )
        if not CHIFFRES_MIN_ABIMEE <= len(relu) <= CHIFFRES_MAX_ABIMEE:
            continue
        if relu == reference or relu in dictes:
            continue
        if _distance(relu, reference) > ECARTS_MAX_ABIMEE:
            continue
        trouvees.append((suite.start(), suite.end()))
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
            a_corriger.append(
                (phrase.jetons[n.debut].debut, phrase.jetons[n.fin - 1].fin)
            )
        # M6 : les relectures que le module ne lit plus comme un téléphone.
        hors_telephones = [n for n in tous if n.type != TELEPHONE]
        a_corriger += _relectures_abimees(
            texte, phrase, hors_telephones, reference, dictes
        )
        a_corriger += _relectures_chiffre_par_chiffre(texte, reference, dictes)
        sortie, curseur = [], 0
        for debut, fin in sorted(a_corriger):
            if debut < curseur:
                continue
            original = texte[debut:fin]
            if _en_lettres(original):
                juste = _par_paires_en_mots(reference)
            else:
                juste = " ".join(reference[i : i + 2] for i in range(0, 10, 2))
            logger.info(
                "[.mark] Read-back of a phone number corrected before the voice"
            )
            sortie += [texte[curseur:debut], juste]
            curseur = fin
        if not sortie:
            return texte
        return "".join(sortie) + texte[curseur:]
    except Exception as erreur:  # noqa: BLE001 -- l'appel doit continuer
        logger.warning(f"[.mark] Read-back check failed, sentence kept: {erreur!r}")
        return texte
