"""[.mark] Couche 2 : ce que l'agent ne dit jamais (U3 quinquies, `reference/29` § XXIX.5).

Deux garde-fous mécaniques sur une réplique du MODÈLE, juste avant la voix, dans le passage des filtres du nom et de la civilité :

* **noms d'outils et syntaxe** : le nom d'un outil de l'agent, une accolade, un crochet, un ``{{...}}`` sont retirés ;
* **consigne récitée** : une réplique qui recopie au moins N mots consécutifs des consignes de l'agent est remplacée par la phrase de
  confidentialité. Sont exclus du texte comparé : les variables injectées, la première réplique, les phrases que le prompt cite
  entre guillemets pour être dites, les phrases du code (elles ne passent pas par ici : ``modele=False``). Sans cette exclusion,
  l'accueil récité déclencherait le garde-fou à chaque appel.

Comparaison de texte pure : aucune compréhension de l'agent, zéro latence, aucun mot du métier (G4). R9 : Pipecat n'offre pas de
filtre de sortie de ce genre (vérifié dans ``pipecat/`` : seuls des filtres de balises et de markdown pour la voix existent).
⛔ Ne lève jamais : en cas de pépin, la réplique passe telle quelle.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable

from loguru import logger

from api.schemas.securite_conversation import SecuriteConversation
from api.services.securite import textes

_VARIABLE = re.compile(r"\{\{[^{}]{0,200}\}\}")
_GUILLEMETS = re.compile(r"«[^»]{0,600}»|\"[^\"\n]{0,600}\"|“[^”]{0,600}”")
_SYNTAXE = re.compile(r"\{\{[^{}\n]{0,200}\}\}|\{[^{}\n]{0,200}\}|\[[^\[\]\n]{0,200}\]")
_MOT = re.compile(r"[^\W_]+", re.UNICODE)
COUPURE = "\x00"


@dataclass
class Contexte:
    """Ce que le garde sait de l'agent à cet instant (relu à chaque réplique : l'étape change)."""

    noms_d_outils: Iterable[str] = field(default_factory=list)
    consignes: str = ""
    exclusions: Iterable[str] = field(default_factory=list)  # valeurs injectées, première réplique


@dataclass
class Resultat:
    texte: str
    declenchements: list[dict[str, Any]] = field(default_factory=list)


def _normaliser(texte: str) -> str:
    s = unicodedata.normalize("NFKD", texte or "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold().replace("’", "'")


def _mots(texte: str) -> list[str]:
    return _MOT.findall(_normaliser(texte).replace("'", " "))


@lru_cache(maxsize=64)
def _fenetres(consignes: str, exclusions: tuple[str, ...], n: int) -> frozenset[tuple[str, ...]]:
    """Les suites de ``n`` mots des consignes, hors exclusions (une coupure casse la suite)."""
    corpus = _VARIABLE.sub(COUPURE, consignes)
    corpus = _GUILLEMETS.sub(COUPURE, corpus)
    for e in sorted((e for e in exclusions if e and len(e.strip()) >= 3), key=len, reverse=True):
        corpus = re.sub(re.escape(e.strip()), COUPURE, corpus, flags=re.IGNORECASE)
    fenetres: set[tuple[str, ...]] = set()
    for morceau in corpus.split(COUPURE):
        mots = _mots(morceau)
        for i in range(len(mots) - n + 1):
            fenetres.add(tuple(mots[i : i + n]))
    return frozenset(fenetres)


def passage_recite(texte: str, consignes: str, exclusions: Iterable[str], n: int) -> str | None:
    """Le premier passage de ``n`` mots de ``texte`` identique aux consignes (rendu en clair), ou ``None``."""
    fenetres = _fenetres(consignes, tuple(sorted(set(exclusions))), n)
    if not fenetres:
        return None
    mots = _mots(texte)
    for i in range(len(mots) - n + 1):
        if tuple(mots[i : i + n]) in fenetres:
            return " ".join(mots[i : i + n])
    return None


def _retirer_les_noms(texte: str, noms: Iterable[str]) -> tuple[str, list[str]]:
    trouves: list[str] = []
    for nom in sorted({n for n in noms if n and len(n) >= 2}, key=len, reverse=True):
        motif = re.compile(rf"(?<![\w-]){re.escape(nom)}(?![\w-])", re.IGNORECASE)
        if motif.search(texte):
            trouves.append(nom)
            texte = motif.sub("", texte)
    return texte, trouves


def _recoudre(texte: str) -> str:
    texte = re.sub(r"[ \t]{2,}", " ", texte)
    texte = re.sub(r"\s+([,.;])", r"", texte)
    texte = re.sub(r",\s*(?=[.!?…])", "", texte)
    return texte.strip()


def nettoyer(texte: str, reglages: SecuriteConversation, contexte: Contexte) -> Resultat:
    """La réplique après les deux garde-fous, avec la liste de ce qui s'est déclenché. ⛔ Ne lève jamais."""
    try:
        sortie = Resultat(texte)
        if not texte or not (reglages.jamais.outils or reglages.jamais.recitation):
            return sortie
        courant = texte
        if reglages.jamais.outils:
            courant, outils = _retirer_les_noms(courant, contexte.noms_d_outils)
            sans_syntaxe = _SYNTAXE.sub("", courant)
            sans_syntaxe = re.sub(r"[{}\[\]]", "", sans_syntaxe)
            syntaxe = sans_syntaxe != courant
            courant = sans_syntaxe
            if outils or syntaxe:
                courant = _recoudre(courant)
                sortie.declenchements.append(
                    {"garde": "outils", "detail": ", ".join(outils) if outils else "syntaxe", "extrait": texte[:120]}
                )
                if not re.search(r"[^\W_]", courant):  # il ne reste rien à dire
                    courant = ""
        if reglages.jamais.recitation and courant:
            passage = passage_recite(courant, contexte.consignes, contexte.exclusions, reglages.jamais.mots)
            if passage:
                sortie.declenchements.append({"garde": "recitation", "detail": passage[:160], "extrait": texte[:120]})
                courant = (reglages.jamais.phrase or "").strip() or textes.PHRASE_DE_CONFIDENTIALITE
        sortie.texte = courant
        return sortie
    except Exception as erreur:  # noqa: BLE001 -- la réplique passe telle quelle
        logger.warning(f"[securite] garde de sortie en échec, réplique gardée : {erreur!r}")
        return Resultat(texte)
