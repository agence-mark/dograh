"""[.mark] Mécanisme commun : ce que le moteur de commande demande à son catalogue (le protocole d'une SOURCE et le registre des sources).

Le moteur ne lit jamais une base : il parle à une source. La source dit ce qui est vrai (articles, prix, ruptures, ouverture, zone,
total, enregistrement) ; le moteur fait la conversation (un manque à la fois, aucun article perdu). Une source s'ouvre pour UN geste
d'outil (``ouvrir``) et se referme avec lui. La restauration en est la première (``services/restauration/source_commande.py``) ;
n'importe quel catalogue fermé (pièces, forfaits…) s'ajoute en inscrivant la sienne, sans toucher au moteur.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from api.services.commande.resultat import Resultat


class Source(Protocol):
    """Les gestes que le moteur attend d'un catalogue. Tout rend des données vraies ; rien n'est inventé par le moteur."""

    modes: tuple[str, ...]
    libelles_des_modes: dict[str, str]  # le mot que l'appelant entend pour chaque mode

    def exige_une_zone(self, mode: str) -> bool: ...

    async def etat(self, mode: str) -> dict[str, Any]:
        """``{ouvert, statut, raison, reprise, prochaine_ouverture, delai_minutes, planifiee_permise}`` ; ``statut`` : le statut fermé
        à rendre quand ``ouvert`` est faux (``FERME``, ``PAUSE_TYPE``…)."""

    async def chercher(self, texte: str) -> Resultat:
        """Dans le catalogue : ``RETENU`` (``faits.retenu`` = l'article, ``faits.options`` = taille ou contenant lus), ``AMBIGU``, ``INTROUVABLE``."""

    async def article(self, ref: str, mode: str) -> dict[str, Any] | None:
        """La fiche d'un article à cet instant (déclinaisons, groupes de choix, retirables), ou ``None``."""

    async def chiffrer(self, mode: str, lignes: list[dict[str, Any]], zone_id: int | None, regles: dict[str, Any]) -> Resultat:
        """Le panier chiffré depuis le catalogue : ``OK`` (lignes, sous_total, frais, total) ou le refus fermé du premier défaut."""

    async def reglages(self) -> dict[str, Any]:
        """``{moyens_paiement: [...], plafond_titre: int | None}`` : ce que l'établissement accepte."""

    async def client(self, telephone: str) -> dict[str, Any] | None: ...

    async def consigne(self, telephone: str, texte: str) -> Resultat: ...

    async def enregistrer(self, brouillon: dict[str, Any], jeton: str) -> Resultat:
        """L'enregistrement DÉFINITIF (recalcule tout, refuse l'incomplet, anti-doublon) ; lance l'envoi après coup."""

    def statut_de_l_enregistrement(self) -> str:
        """``ENREGISTREE``, ou ``TRANSMISE`` quand la destination ne sait pas dire « acceptée »."""

    async def annonce(self, mode: str, zone_id: int | None) -> dict[str, Any] | None:
        """L'heure que le code annoncerait maintenant (lot 6) : ``{prete, texte}``, ou ``None`` si la source ne sait pas."""


FabriqueDeSource = Callable[..., AbstractAsyncContextManager[Source]]

_SOURCES: dict[str, FabriqueDeSource] = {}
SOURCE_PAR_DEFAUT = "classeur"


def enregistrer_source(nom: str, fabrique: FabriqueDeSource) -> None:
    """Inscrit une source. ``fabrique(ctx)`` rend un gestionnaire de contexte asynchrone qui produit la source pour un geste."""
    _SOURCES[nom] = fabrique


def ouvrir(nom: str | None, ctx: Any) -> AbstractAsyncContextManager[Source]:
    """La source nommée (celle de l'outil, à défaut ``classeur``) pour UN geste de l'outil. Inconnue : ``KeyError`` (une erreur de montage)."""
    return _SOURCES[nom or SOURCE_PAR_DEFAUT](ctx)
