"""[.mark] Mécanisme commun : ce que le moteur de réservation demande à sa capacité (protocole d'une SOURCE et registre des sources).

Le moteur ne lit jamais une base : il parle à une source. La source dit ce qui est vrai (créneaux libres, règles, place) et enregistre ;
le moteur fait la conversation (un manque à la fois, relecture avant d'écrire, annulation en deux temps).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import date
from typing import Any, Protocol

from api.services.actions_communes.resultat import Resultat


class Source(Protocol):
    async def resoudre_une_date(self, texte: str, heure: str | None) -> Resultat:
        """Le jour et l'heure dits, vers l'avenir, au fuseau du lieu : ``RETENU`` (``faits.heure_voulue`` ISO aware), ``INCOMPLETE`` (``faits.jour``
        quand seule l'heure manque), ``AMBIGU`` (candidats), ``INTROUVABLE`` ou ``ARGUMENT_INVALIDE`` (heure passée)."""

    async def disponibilites(self, jour: date, personnes: int) -> Resultat:
        """Les créneaux libres du jour, les plus tôt d'abord : ``OK`` (``faits.creneaux`` ``[{debut, fin}]``) ou un refus fermé (``REFUSEE``, ``INCOMPLETE``)."""

    async def creer(self, brouillon: dict[str, Any]) -> Resultat:
        """Enregistre (place revérifiée) : ``ENREGISTREE``, ``DEJA_FAIT``, ``INCOMPLETE``, ``REFUSEE`` (``faits.detail`` + propositions)."""

    async def modifier(self, numero: str, changements: dict[str, Any]) -> Resultat: ...

    async def annuler(self, numero: str) -> Resultat: ...

    async def retrouver(self, **criteres: Any) -> Resultat:
        """``OK`` (``faits.reservations``) ou ``INTROUVABLE`` ; critères : ``numero``, ``telephone``, ``prenom``, ``jour`` ;
        chaque réservation dit ``personnes`` (un seul nom du modèle à la source, B07)."""

    async def horaires(self) -> list[dict[str, Any]]:
        """Les services où l'on réserve : ``[{nom, jours, debut, fin}]`` (heures du lieu), pour que ``lire`` dise les horaires."""

    async def apres_le_geste(self, geste: str, r: Resultat, ctx: Any) -> None:
        """Ce que le portail apprend en direct après un geste réussi (facultatif)."""


FabriqueDeSource = Callable[..., AbstractAsyncContextManager[Source]]
# Point de contrôle du lot 7 : pour CET appel, la source n'écrit dans le système d'aucun client (``Connecteur.sans_tiers``, lu au seul essai au
# clavier : vrai, la fiche y est jouée pour de vrai ; faux, simulée, B42). Reçoit le contexte de l'appel. Une source sans réponse : faux.
SansTiers = Callable[[Any], Awaitable[bool]]

_SOURCES: dict[str, FabriqueDeSource] = {}
_SANS_TIERS: dict[str, SansTiers] = {}
SOURCE_PAR_DEFAUT = "classeur"


def enregistrer_source(nom: str, fabrique: FabriqueDeSource, *, sans_tiers: SansTiers | None = None) -> None:
    _SOURCES[nom] = fabrique
    if sans_tiers is None:
        _SANS_TIERS.pop(nom, None)
    else:
        _SANS_TIERS[nom] = sans_tiers


async def sans_tiers(nom: str | None, ctx: Any) -> bool:
    """La source nommée (à défaut ``classeur``) n'écrit, dans cet appel, chez aucun client. Faux quand elle ne le dit pas."""
    lire = _SANS_TIERS.get(nom or SOURCE_PAR_DEFAUT)
    return bool(lire is not None and (await lire(ctx)) is True)


def ouvrir(nom: str | None, ctx: Any) -> AbstractAsyncContextManager[Source]:
    """La source nommée (à défaut ``classeur``) pour UN geste d'outil. Inconnue : ``KeyError`` (une erreur de montage)."""
    return _SOURCES[nom or SOURCE_PAR_DEFAUT](ctx)
