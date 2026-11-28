"""[.mark] Mécanisme commun : ce que le moteur de commande demande à son catalogue (le protocole d'une SOURCE et le registre des sources).

Le moteur ne lit jamais une base : il parle à une source. La source dit ce qui est vrai (articles, prix, ruptures, ouverture, zone,
total, enregistrement) ; le moteur fait la conversation (un manque à la fois, aucun article perdu). Une source s'ouvre pour UN geste
d'outil (``ouvrir``) et se referme avec lui. La restauration en est la première (``services/restauration/source_commande.py``) ;
n'importe quel catalogue fermé (pièces, forfaits…) s'ajoute en inscrivant la sienne, sans toucher au moteur.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable

from api.services.commande.resultat import Resultat


@runtime_checkable
class Source(Protocol):
    """Les gestes que le moteur attend d'un catalogue. Tout rend des données vraies ; rien n'est inventé par le moteur."""

    modes: tuple[str, ...]
    libelles_des_modes: dict[str, str]  # le mot que l'appelant entend pour chaque mode
    libelles_des_moyens: dict[str, str]  # le mot que l'appelant entend pour chaque moyen de règlement (« en espèces »)
    moyens_reserves_au_mode: dict[str, Any]  # M90 : {moyen: modes} ; un moyen absent vaut pour tous les modes (vide si la source n'en réserve aucun)
    champs_du_greffier: dict[str, tuple[str, ...]]  # les champs de la fiche que la commande joint à sa note (``{"note": (...)}``) ; vide sinon

    def exige_une_zone(self, mode: str) -> bool: ...

    async def etat(self, mode: str) -> dict[str, Any]:
        """``{ouvert, statut, raison, reprise, reprise_dite, prochaine_ouverture, delai_minutes, planifiee_permise, en_pause}`` ; ``statut`` : le statut fermé
        à rendre quand ``ouvert`` est faux (``FERME``, ``PAUSE_TYPE``…). Aucune phrase : le modèle dit la fermeture d'après ces faits (lot 7b-C7)."""

    async def chercher(self, texte: str) -> Resultat:
        """Dans le catalogue : ``RETENU`` (``faits.retenu`` = l'article, ``faits.options`` = taille ou contenant lus), ``AMBIGU``, ``INTROUVABLE``."""

    async def article(self, ref: str, mode: str, servi_le: datetime | None = None) -> dict[str, Any] | None:
        """La fiche d'un article à cet instant (déclinaisons, groupes de choix, retirables), ou ``None``."""

    async def carte_a_lire(self, mode: str) -> dict[str, Any]:
        """La carte vendable à cet instant, à lire (``lire`` avec ``sujet: carte``) : ``{rubriques: [{nom, articles: [noms]}], du_moment: [{article, renseigne, texte_du_jour}]}``
        (``du_moment`` seulement s'il y a un produit du moment) ; lue dans la carte chargée à l'appel, jamais devinée."""

    async def catalogue(self, mode: str) -> dict[str, Any]:
        """M104 : la carte vendable à cet instant en UNE lecture (``articles`` : catégorie, signalements, choix obligatoires ; ``libelles`` des allergènes), pour chercher ce qui est « sans » une chose."""

    def codes_d_un_nom(self, nom: str) -> list[str]:
        """Les signalements que le NOM d'un ingrédient affirme (« thon » : poissons)."""

    def regime_dit(self, texte: str) -> str | None:
        """Le régime que le texte nomme (« végétarien », « halal »), ou ``None``."""

    def regime_code(self, texte: str) -> str | None:
        """Le code de l'étiquette du régime dit, ``None`` si la carte ne l'étiquette pas."""

    async def regles_d_information(self) -> dict[str, Any]:
        """Ce que l'établissement a écrit pour répondre sur les allergies et le halal (``{}`` pour une source qui n'en a pas)."""

    async def verifier_un_creneau(self, mode: str, voulue: datetime) -> Resultat | None:
        """Le refus de l'heure voulue (fermé, trop tôt, créneau plein), ou ``None`` si elle passe."""

    async def quand_dit(self, voulue: datetime) -> str:
        """L'heure voulue en mots (le jour d'abord quand ce n'est pas aujourd'hui)."""

    async def signaler_une_regle_inconnue(self, produit_ref: str, texte: str) -> bool:
        """Une règle d'article dite que la carte ne connaît pas : signalée à l'équipe ; rend si elle l'a été."""

    def signalement_dit(self, texte: str) -> str | None:
        """Le code du signalement que l'appelant nomme (la source connaît ses mots), ou ``None`` (lot 7)."""

    def signalements_dits(self, texte: str) -> tuple[list[str], bool]:
        """A1 (lot 19 bis) : TOUS les signalements que le texte nomme, et si une partie du texte n'est pas reconnue. """

    async def chiffrer(self, mode: str, lignes: list[dict[str, Any]], zone_id: int | None, regles: dict[str, Any]) -> Resultat:
        """Le panier chiffré depuis le catalogue : ``OK`` (lignes, sous_total, frais, total) ou le refus fermé du premier défaut."""

    async def formules_de_la_carte(self) -> list[str]:
        """Les noms des formules à la carte maintenant (lot 11) ; la lecture des offres les rend avec les remises."""
        ...

    async def remises_en_cours(self) -> list[dict[str, Any]]:
        """Les remises valables maintenant, sans regarder le panier : ``{ref, nom, mecanisme, phrase, minimum}`` (lot 7)."""

    async def codes_de_remise(self) -> list[dict[str, Any]]:
        """Lot 14 (OFF3) : les remises À CODE valables maintenant, ``{code, ref, nom, phrase}``, pour vérifier un code dit ; jamais pour l'annoncer."""

    async def noter_une_offre_dite(self, ref: str, appel_id: str | None) -> None:
        """M38 : l'agent vient de dire cette offre (pour la colonne « Dite » de l'écran des remises)."""

    async def offres_a_portee(self, mode: str, lignes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Les offres que ces lignes chiffrées atteignent ou presque (lot 26, M25) : ``{ref, nom, phrase, etat: "atteinte"|"presque", manque, proposition, choix}``.
        Une source qui n'en a pas rend une liste vide."""

    async def proposer_en_plus(self, mode: str, lignes: list[dict[str, Any]], avec_offre: bool = True) -> dict[str, Any] | None:
        """UN article précis à proposer en plus (lot 26, M25) : ``{nom, prix, raison, choix, ...}`` ou ``None`` : jamais une phrase générique."""

    async def retrouver(self, numero: str | None = None, telephone: str | None = None) -> Resultat:
        """Retrouve des commandes passées (lot 7) : ``OK`` (``faits.commandes`` ``[{numero, numero_court, statut, mode, quand_dit, total}]``,
        les plus récentes d'abord) ou ``INTROUVABLE``. Seulement celles de CE lieu, du jour."""

    async def envoyer(self, quoi: str, telephone: str | None, cle_unique: str, organisation: int | None) -> Resultat:
        """Un message demandé par l'appelant (lot 7) : ``OK``, ``DEJA_FAIT`` ou ``INDISPONIBLE`` (éteint, sans mobile, sans compte)."""

    async def reglages(self) -> dict[str, Any]:
        """``{moyens_paiement: [...], plafond_titre: int | None, titre_alcool_exclu, titre_sans_rendu, notes_libres}`` : ce que l'établissement accepte (clés absentes : permis, valeurs de la 030)."""

    async def client(self, telephone: str) -> dict[str, Any] | None: ...

    async def consigne(self, telephone: str, texte: str) -> Resultat:
        """Retient une habitude du client. ``ARGUMENT_INVALIDE`` avec ``faits.raison = "pour_la_commande"`` : la source refuse d'en faire une habitude
        (donnée sensible), le moteur la note alors sur la commande seulement."""

    async def enregistrer(self, brouillon: dict[str, Any], jeton: str) -> Resultat:
        """L'enregistrement DÉFINITIF (recalcule tout, refuse l'incomplet, anti-doublon) ; rien ne part pendant l'appel : l'envoi part à sa fin (§ 17)."""

    async def reecrire_la_commande(self, numero: str, brouillon: dict[str, Any], jeton: str, *, rouvrir: bool = False) -> Resultat:
        """Lot 8b-1b (E4) : la commande ``numero`` de l'appel, changée après le « oui », est réécrite à sa place (même numéro), contrôlée comme ``enregistrer`` (tout ou rien) ;
        rien ne part pendant l'appel (§ 17 l.404). ``ENREGISTREE`` ou le refus. Lot 8b-2 (§ 17 l.407) : ``rouvrir`` reprend aussi la ligne que cet appel a annulée (annuler = vider,
        on recommande dans le même appel) ; sans elle (introuvable, ou plus rouvrable), ``INTROUVABLE`` ou ``INTERDIT``."""

    async def annuler_une_commande(self, numero: str) -> Resultat:
        """La commande ``numero`` de CET appel passe à « annulée » ; une commande que la caisse n'a pas reçue (« retenue », § 17) s'annule sans elle.
        ``OK``, ``DEJA_FAIT``, ``INTERDIT`` ou ``INTROUVABLE``."""

    def statut_de_l_enregistrement(self) -> str:
        """``ENREGISTREE``, ou ``TRANSMISE`` quand la destination ne sait pas dire « acceptée »."""

    async def verifier_adresse(self, texte: str) -> Resultat:
        """La zone de l'adresse dite (lot 6) : ``RETENU`` (``faits.zone`` : id, nom, frais, minimum, délai ; ``faits.commune``), ``HORS_ZONE``, ``AMBIGU``
        (``faits.candidats``) ou ``INTROUVABLE`` (la commune manque). Jamais une zone pour un doute."""

    async def resoudre_une_date(self, texte: str, heure: str | None) -> Resultat:
        """La date et l'heure dites, résolues vers l'avenir au jour et au fuseau du lieu : ``RETENU`` (``faits.heure_voulue`` ISO aware), ``AMBIGU``
        (candidats), ``INCOMPLETE`` (l'heure manque) ou ``INTROUVABLE``."""

    async def annonce(self, mode: str, zone_id: int | None) -> dict[str, Any] | None:
        """L'heure que le code annoncerait maintenant (lot 6) : ``{prete, texte, minutes}``, ou ``None`` si la source ne sait pas."""


FabriqueDeSource = Callable[..., AbstractAsyncContextManager[Source]]

# Lot 8c-2 (106) : pour CET appel, la source n'écrit dans le système d'aucun client (``Connecteur.sans_tiers``, lu au seul essai au clavier) ; même forme
# que ``reservation/source.py``. Reçoit le contexte de l'appel. Une source sans réponse : faux.
SansTiers = Callable[[Any], Awaitable[bool]]

_SOURCES: dict[str, FabriqueDeSource] = {}
_SANS_TIERS: dict[str, SansTiers] = {}
SOURCE_PAR_DEFAUT = "classeur"


def enregistrer_source(nom: str, fabrique: FabriqueDeSource, *, sans_tiers: SansTiers | None = None) -> None:
    """Inscrit une source. ``fabrique(ctx)`` rend un gestionnaire de contexte asynchrone qui produit la source pour un geste."""
    _SOURCES[nom] = fabrique
    if sans_tiers is None:
        _SANS_TIERS.pop(nom, None)
    else:
        _SANS_TIERS[nom] = sans_tiers


async def sans_tiers(nom: str | None, ctx: Any) -> bool:
    """La source nommée (à défaut ``classeur``) n'écrit, dans cet appel, chez aucun client. Faux quand elle ne le dit pas."""
    lire = _SANS_TIERS.get(nom or SOURCE_PAR_DEFAUT)
    return bool(lire is not None and (await lire(ctx)) is True)


def ouvrir(nom: str | None, ctx: Any, **options: Any) -> AbstractAsyncContextManager[Source]:
    """La source nommée (celle de l'outil, à défaut ``classeur``) pour UN geste de l'outil. ``options`` : ce que la source accepte en plus
    (les réglages de recherche de l'agent). Inconnue : ``KeyError`` (une erreur de montage)."""
    return _SOURCES[nom or SOURCE_PAR_DEFAUT](ctx, **options)
