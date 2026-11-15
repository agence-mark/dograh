"""[.mark] Module Restauration, lot 2 : ce que toute la couche d'accès partage (contrat comptoir ↔ classeur, § 1 et 5).

La couche d'accès est le seul endroit qui ouvre une requête sur les tables ``resto_*`` (le contrat : « aucune session
SQL hors de la couche »). Elle est coupée en fichiers par sujet (carte, commande, clients, conservation) et
exposée par ``restauration.py``, qui porte exactement les fonctions du contrat.

- ``Resultat`` : le retour fermé de toute fonction appelée par un outil.
- l'heure vient TOUJOURS de ``horloge`` (D6), jamais d'un appel direct.
- ``source_et_auteur`` : pose ``mark.source`` / ``mark.auteur`` pour le journal des changements (déclencheurs, 028).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import asyncpg

from api.db.bases_clients.horloge import horloge

# § 5 du contrat : la liste fermée des statuts rendus aux outils.
STATUTS = frozenset(
    {
        "OK", "RETENU", "AMBIGU", "INTROUVABLE", "INCOMPLETE", "ENREGISTREE", "TRANSMISE", "REFUSEE", "DEJA_FAIT",
        "FERME", "PAUSE_TYPE", "LIVRAISON_TERMINEE", "HORS_ZONE", "MINIMUM_NON_ATTEINT", "RUPTURE", "CHOIX_OBLIGATOIRE",
        "MAXIMUM_ATTEINT", "HORS_CARTE", "MOYEN_NON_ACCEPTE", "PLAFOND_TITRE_RESTAURANT", "INDISPONIBLE",
        "ARGUMENT_INVALIDE",
        # Résultat de ``changer_statut`` (§ 4) : « OK / DEJA_FAIT / INTERDIT ».
        "INTERDIT",
    }
)
# Raisons de REFUSEE (liste fermée) : jamais un texte de fournisseur rendu au modèle ni à l'écran.
RAISONS_REFUS = frozenset({"produit_inconnu", "prix_different", "restaurant_ferme", "remise_inconnue", "caisse_injoignable", "autre"})
SOURCES = frozenset({"caisse", "portail", "mark", "agent", "import"})
TYPES = frozenset({"emporter", "livraison", "sur_place", "reservation"})
MODES = frozenset({"emporter", "livraison", "sur_place"})


class EtablissementInconnu(LookupError):
    """L'établissement n'existe pas dans cette base (jamais rendu à un modèle : une erreur de programmation)."""


@dataclass(frozen=True)
class Resultat:
    """Le retour fermé d'une fonction appelée par un outil : un statut de la liste, des faits vrais, une phrase proposée."""

    statut: str
    faits: dict[str, Any] = field(default_factory=dict)
    suggestion: str = ""
    manque: str | None = None

    def __post_init__(self):
        if self.statut not in STATUTS:
            raise ValueError(f"Statut hors de la liste fermée : {self.statut!r}")


async def maintenant(connexion: asyncpg.Connection) -> datetime:
    """L'heure de l'organisation (une base de client = une organisation), par la source d'heure (D6)."""
    base = await connexion.fetchval("SELECT current_database()")
    return horloge(base).maintenant()


async def fuseau_de(connexion: asyncpg.Connection, etablissement_id: int) -> str:
    fuseau = await connexion.fetchval("SELECT fuseau FROM mark.site WHERE id = $1", etablissement_id)
    if fuseau is None:
        raise EtablissementInconnu(etablissement_id)
    return fuseau


async def poser_session(connexion: asyncpg.Connection, source: str, auteur: str) -> None:
    """Dans la transaction en cours : le journal des changements saura la source et l'auteur (déclencheurs de la 028)."""
    if source not in SOURCES:
        raise ValueError(f"Source inconnue : {source!r}")
    await connexion.execute(
        "SELECT set_config('mark.source', $1, true), set_config('mark.auteur', $2, true)", source, auteur
    )
