"""[.mark] Module Restauration, lot 24 : le « chiffre sans source » et le « fait avant le résultat » (W15), deux signes de plus pour la VÉRITÉ DES ACTIONS.

Sans mot du métier : un MONTANT (« treize euros quarante et un », « 12,90 € ») ou une HEURE (« à vingt heures trente », « à 20 h ») que l'agent dit, et
qu'aucun résultat d'outil de l'appel, aucune parole de la personne ni aucune consigne ne donne, est retenu ; le modèle est relancé UNE fois avec la
consigne de ce qu'il a fait (même mécanisme que la date inconnue, ``verite_des_actions``). Seuls les chiffres qu'un outil de l'appel aurait dû rendre sont
contrôlés ; une QUANTITÉ l'est aussi (« vous avez trois pizzas »), mais prudemment : deux ou plus, devant un nom qui n'est pas une unité de temps, de
somme ou de date (« deux minutes », « le 14 novembre » ne sont pas contrôlés), et un nombre qui apparaît n'importe où dans les sources compte comme donné.

Deux clés d'agent, ÉTEINTES par défaut (seul ``True`` allume ; le modèle de réglages Restauration les allume) :

- ``garde_chiffre_sans_source`` : une réplique de texte seul qui dit un montant ou une heure sans source est retenue ;
- ``garde_fait_avant_outil`` : quand le modèle parle PUIS appelle un outil dans la même réponse, ce texte ne peut être qu'une phrase d'attente ; un montant ou
  une heure sans source, ou un fait accompli (« c'est enregistré ») dit avant le résultat de l'outil, est retenu.

Conditions G1 à G5 : mécanique, sans mot de métier, un interrupteur, zéro déclenchement sur un appel sain (les chiffres que l'agent redit sont ceux du
résultat). ⛔ Ne lève jamais : dans le doute, la réplique passe.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from loguru import logger

CLE_CHIFFRE_SANS_SOURCE = "garde_chiffre_sans_source"
CLE_FAIT_AVANT_OUTIL = "garde_fait_avant_outil"

RAISON_CHIFFRE = "chiffre_sans_source"
RAISON_FAIT_AVANT = "fait_avant_le_resultat"

CONSIGNE_CHIFFRE = (
    "Tu viens de dire un chiffre qu'aucun résultat d'outil de cet appel, ni aucune parole de la personne, ne donne : {detail}. Redis ta réponse avec le chiffre "
    "EXACT lu dans le résultat de l'outil, ou rappelle l'outil pour l'obtenir. N'invente ni ne calcule aucun montant ni aucune heure."
)
CONSIGNE_FAIT_AVANT = (
    "Tu parles avant d'appeler un outil : ce que tu dis ne peut être qu'une phrase d'attente. Tu viens de dire un fait ({detail}) avant d'en avoir le résultat. "
    "Appelle l'outil, attends son résultat, puis dis ce qu'il rend."
)

_MONTANT = re.compile(
    r"(?<![\d,.])(\d{1,6})(?:[.,](\d{1,2}))?\s*(?:€|euros?)(?:\s*(?:et\s+)?(\d{1,2})(?!\d|[,.]\d|\s*(?:h\b|heure|euro|€|%|minute)))?", re.IGNORECASE
)
_HEURE_H = re.compile(r"(?<![\d,.])(\d{1,2})\s*h\s*(\d{2})?(?![\d\w])", re.IGNORECASE)
_HEURE_MOTS = re.compile(
    r"\b(?:à|vers|pour|dès|jusqu'à|entre|de|et)\s+(\d{1,2})\s*heures?\b(?:\s*(?:et\s+)?(\d{2}(?!\s*(?:h\b|heure))|quart|demie?|\d(?!\s*[\w€%]))\b)?", re.IGNORECASE
)
_MINUIT = re.compile(r"\b(?:à|vers|pour|dès|jusqu'à|entre|de|et)\s+minuit\b", re.IGNORECASE)
# Un centime d'euro ou une minute dits en toutes lettres (« treize euros un », « vingt heures neuf »), un montant sous l'euro (« cinquante centimes ») et « deux » seul : le lecteur de nombres
# en lettres (``text_to_num``) laisse « un » et « deux » isolés, que le code, lui, écrit en lettres (``mots_dits``).
_CENTIME_UN = re.compile(r"(\b(?:euros?|heures?))\s+(?:et\s+)?(un|neuf)(?=\s*(?:[.!?;]|$))", re.IGNORECASE)
_CENTIMES = re.compile(r"(?<![\d,.])(\d{1,2})\s*centimes?\b", re.IGNORECASE)
_UN_CENTIME = re.compile(r"(?<![\d,.])(?:un|une)\s+centimes?", re.IGNORECASE)
_DEUX = re.compile(r"\bdeux\b(?![-'])", re.IGNORECASE)
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})")
_UN_EURO = re.compile(r"\b(?:un|une)\s+euro\b", re.IGNORECASE)


_UNITES = (
    "euro|€|cent|centime|%|pour|h|heure|minute|min|seconde|sec|jour|semaine|mois|an|année|fois|ème|eme|e|er|ère|"
    "janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|"
    "lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|km|m|kg|g|cl|l|ml|degrés?|°"
)
_QUANTITE = re.compile(
    rf"(?<![\d,.:/-])(\d{{1,3}})\s+(?!(?:{_UNITES})s?\b)([a-zàâçéèêëîïôûùüÿœ][a-zàâçéèêëîïôûùüÿœ'-]{{2,}})", re.IGNORECASE
)
_NOMBRE = re.compile(r"(?<![\d,.])(\d{1,3})(?!\d)")


def _en_chiffres(texte: str) -> str:
    """Les nombres écrits en lettres passent en chiffres (M34) : « vingt-cinq euros », « trois pizzas », mais aussi « deux pizzas » et « treize euros un »."""
    try:
        from api.services.commande import lecture

        converti = lecture.en_chiffres(_UN_EURO.sub("1 euro", texte))
    except Exception:  # noqa: BLE001
        converti = texte
    # Ce qui reste en lettres après le lecteur est un « deux » ou un « un » isolé : jamais le début d'un nombre composé (déjà converti).
    converti = _CENTIME_UN.sub(lambda m: f"{m.group(1)} {1 if m.group(2).lower() == 'un' else 9}", _DEUX.sub("2", converti))
    return _UN_CENTIME.sub("1 centime", converti)


def montants_dits(texte: Any) -> set[int]:
    """Les montants (en centimes) écrits dans ``texte`` : « 12,90 € », « 13 euros 41 », « treize euros quarante et un ». ⛔ Ne lève jamais."""
    try:
        if not isinstance(texte, str):
            texte = json.dumps(texte, ensure_ascii=False, default=str)
        texte = _UN_EURO.sub("1 euro", _en_chiffres(texte))
        trouves: set[int] = set()
        for m in _CENTIMES.finditer(_MONTANT.sub(" ", texte)):  # « cinquante centimes » : un montant sous l'euro
            trouves.add(int(m.group(1)))
        for m in _MONTANT.finditer(texte):
            euros = int(m.group(1))
            if m.group(2) is not None:
                cents = int(m.group(2).ljust(2, "0"))
            elif m.group(3) is not None:
                cents = int(m.group(3))
            else:
                cents = 0
            trouves.add(euros * 100 + cents)
        return trouves
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[chiffres] montants illisibles : {erreur!r}")
        return set()


def heures_dites(texte: Any) -> set[tuple[int, int]]:
    """Les heures ``(h, m)`` écrites dans ``texte`` : « à 20 h 30 », « à vingt heures et quart », « 20h », ou un moment ISO. ⛔ Ne lève jamais."""
    try:
        if not isinstance(texte, str):
            texte = json.dumps(texte, ensure_ascii=False, default=str)
        brut = texte
        texte = _en_chiffres(texte)
        trouvees: set[tuple[int, int]] = set()
        for m in _HEURE_H.finditer(texte):
            h, mn = int(m.group(1)), int(m.group(2) or 0)
            if h < 24 and mn < 60:
                trouvees.add((h, mn))
        for m in _HEURE_MOTS.finditer(texte):
            h = int(m.group(1))
            suite = (m.group(2) or "").casefold()
            mn = {"quart": 15, "demi": 30, "demie": 30}.get(suite, int(suite) if suite.isdigit() else 0)
            if h < 24 and mn < 60:
                trouvees.add((h, mn))
        if _MINUIT.search(texte):
            trouvees.add((0, 0))
        for m in _ISO.finditer(brut):
            trouvees.add((int(m.group(4)), int(m.group(5))))
        return trouvees
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[chiffres] heures illisibles : {erreur!r}")
        return set()


def _sans_montants_ni_heures(texte: str) -> str:
    """Le texte sans ses montants, heures et dates ISO (déjà contrôlés à part) : il ne reste que les quantités possibles."""
    for motif in (_MONTANT, _CENTIMES, _HEURE_H, _HEURE_MOTS, _ISO):
        texte = motif.sub(" ", texte)
    return texte


def quantites_dites(texte: Any) -> dict[int, str]:
    """Les quantités ``n nom`` (n de 2 à 999) dites dans ``texte``, hors unités de temps, de somme et de date : ``{2: "pizzas"}``. ⛔ Ne lève jamais."""
    try:
        if not isinstance(texte, str):
            texte = json.dumps(texte, ensure_ascii=False, default=str)
        texte = _sans_montants_ni_heures(_UN_EURO.sub("1 euro", _en_chiffres(texte)))
        return {int(m.group(1)): m.group(2) for m in _QUANTITE.finditer(texte) if int(m.group(1)) >= 2}
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[chiffres] quantités illisibles : {erreur!r}")
        return {}


def nombres_de(texte: Any) -> set[int]:
    """Tout nombre écrit dans un texte donné comme source (en chiffres ou en lettres) : il compte comme une quantité possible."""
    try:
        if not isinstance(texte, str):
            texte = json.dumps(texte, ensure_ascii=False, default=str)
        return {int(m.group(1)) for m in _NOMBRE.finditer(_en_chiffres(texte))}
    except Exception:  # noqa: BLE001
        return set()


def _entiers_de(valeur: Any, dans: set[int]) -> None:
    """Tout entier d'un résultat d'outil (des centimes, par la règle du classeur) compte comme un montant possible."""
    if isinstance(valeur, bool):
        return
    if isinstance(valeur, int):
        if 0 < valeur < 10_000_000:
            dans.add(valeur)
    elif isinstance(valeur, Mapping):
        for v in valeur.values():
            _entiers_de(v, dans)
    elif isinstance(valeur, (list, tuple)):
        for v in valeur:
            _entiers_de(v, dans)
    elif isinstance(valeur, str) and valeur[:1] in "{[":
        try:
            _entiers_de(json.loads(valeur), dans)
        except ValueError:
            pass


class Sources:
    """Ce que la réplique a le droit de dire : tout ce que les résultats d'outils, la personne et les consignes (messages qui ne sont pas une réplique de
    l'agent) donnent, plus ce que le journal des actions de l'appel a retenu."""

    def __init__(self) -> None:
        self.montants: set[int] = set()
        self.heures: set[tuple[int, int]] = set()
        self.nombres: set[int] = set()  # lot 24 : toute quantité que les sources donnent, où que ce soit

    def ajouter_un_texte(self, texte: Any) -> None:
        self.montants |= montants_dits(texte)
        self.heures |= heures_dites(texte)
        self.nombres |= nombres_de(texte)

    def ajouter_un_resultat(self, resultat: Any) -> None:
        _entiers_de(resultat, self.montants)
        self.ajouter_un_texte(resultat)


def sources_de(messages: Any, journal: Any = ()) -> Sources:
    """Les sources d'une réplique : messages qui ne sont pas de l'agent (personne, outil, consigne, prompt) et résultats du journal des actions."""
    sources = Sources()
    for message in messages or []:
        if not isinstance(message, Mapping) or message.get("role") == "assistant":
            continue
        contenu = message.get("content")
        if isinstance(contenu, list):
            contenu = " ".join(p.get("text", "") for p in contenu if isinstance(p, Mapping) and isinstance(p.get("text"), str))
        if isinstance(contenu, str):
            sources.ajouter_un_resultat(contenu) if message.get("role") == "tool" else sources.ajouter_un_texte(contenu)
    for vue in journal or ():
        resultat = getattr(vue, "resultat", None)
        if resultat is not None:
            sources.ajouter_un_resultat(resultat)
    return sources


def chiffres_sans_source(texte: str, sources: Sources) -> list[str]:
    """Les montants et heures dits dans ``texte`` qu'aucune source ne donne, écrits comme on les dit (« 13,41 euros », « 20 h 30 »)."""
    inconnus: list[str] = []
    for cents in sorted(montants_dits(texte) - sources.montants):
        if cents == 0:
            continue
        euros, reste = divmod(cents, 100)
        inconnus.append(f"{euros} euros" + (f" {reste:02d}" if reste else ""))
    for h, mn in sorted(heures_dites(texte) - sources.heures):
        inconnus.append(f"{h} h" + (f" {mn:02d}" if mn else ""))
    for n, nom in sorted(quantites_dites(texte).items()):
        if n not in sources.nombres and n not in sources.montants:
            inconnus.append(f"{n} {nom}")
    return inconnus


def allumee(reglages: Any, cle: str) -> bool:
    """Éteinte par défaut : seul ``True`` allume. ⛔ Ne lève jamais."""
    try:
        return isinstance(reglages, Mapping) and reglages.get(cle) is True
    except Exception:  # noqa: BLE001
        return False
