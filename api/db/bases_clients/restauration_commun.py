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
from zoneinfo import ZoneInfo

import asyncpg

from api.db.bases_clients.horloge import horloge
from api.db.bases_clients.connexion import nom_de_la_base
from api.db.bases_clients.instantane import stable

# Le type de la connexion à la base d'un client, pour les services : ils le nomment d'ici, jamais en important le pilote
# (la garde amont ``test_db_layer_boundary`` : tout accès à la base vit sous ``api/db/``).
Connexion = asyncpg.Connection

# § 5 du contrat : la liste fermée des statuts rendus aux outils.
STATUTS = frozenset(
    {
        "OK", "RETENU", "AMBIGU", "INTROUVABLE", "INCOMPLETE", "ENREGISTREE", "TRANSMISE", "REFUSEE", "DEJA_FAIT",
        "FERME", "FERME_PLANIFIABLE", "PAUSE_TYPE", "LIVRAISON_TERMINEE", "HORS_ZONE", "MINIMUM_NON_ATTEINT", "RUPTURE", "CHOIX_OBLIGATOIRE",
        "MAXIMUM_ATTEINT", "HORS_CARTE", "MOYEN_NON_ACCEPTE", "PLAFOND_TITRE_RESTAURANT", "INDISPONIBLE",
        "ARGUMENT_INVALIDE",
        # Résultat de ``changer_statut`` (§ 4) : « OK / DEJA_FAIT / INTERDIT ».
        "INTERDIT",
        # Chantier Partie 1, lot 4 (M32) : un changement qui ne change rien (la taille demandée est déjà celle de la ligne).
        "RIEN_A_CHANGER",
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
    """L'heure de l'organisation (une base de client = une organisation), par la source d'heure (D6). Sans requête (lot 5, B06) : la base est
    celle que la connexion porte depuis son ouverture."""
    return horloge(nom_de_la_base(connexion)).maintenant()


def cle_du_client(etablissement_id: int, telephone: str) -> tuple:
    """La clé de la fiche d'un client dans l'instantané de l'appel (lot 5) : l'enregistrement l'oublie, la fiche ayant changé."""
    return ("client", etablissement_id, telephone)


async def fuseau_de(connexion: asyncpg.Connection, etablissement_id: int) -> str:
    async def lire() -> str | None:
        return await connexion.fetchval("SELECT fuseau FROM mark.site WHERE id = $1", etablissement_id)

    fuseau = await stable(connexion, ("fuseau", etablissement_id), lire)  # lot 5 : lu une fois par appel
    if fuseau is None:
        raise EtablissementInconnu(etablissement_id)
    return fuseau


async def etablissements_existants(connexion: asyncpg.Connection, ids: list[int]) -> set[int]:
    """Parmi ces identifiants, ceux qui sont des établissements de CETTE base (une base = une organisation). Sert à vérifier ce qu'une
    requête demande avant de lui ouvrir quoi que ce soit : un identifiant d'une autre organisation n'est pas dans cette base."""
    if not ids:
        return set()
    return {r["id"] for r in await connexion.fetch("SELECT id FROM mark.site WHERE id = ANY($1::bigint[])", ids)}


async def poser_session(connexion: asyncpg.Connection, source: str, auteur: str) -> None:
    """Dans la transaction en cours : le journal des changements saura la source et l'auteur (déclencheurs de la 028)."""
    if source not in SOURCES:
        raise ValueError(f"Source inconnue : {source!r}")
    await connexion.execute(
        "SELECT set_config('mark.source', $1, true), set_config('mark.auteur', $2, true)", source, auteur
    )


async def minutes_recurrentes(connexion: asyncpg.Connection, etablissement_id: int, type_: str, moment: datetime) -> int:
    """Les minutes ajoutées par un soir toujours chargé (``resto_temps_recurrent``) qui couvre ``moment`` (heure locale de l'établissement, jour 1 =
    lundi, plage ``[début, fin[``). Deux plages qui se recouvrent : la plus grande compte, jamais leur somme. Aucune : 0."""
    local = moment.astimezone(ZoneInfo(await fuseau_de(connexion, etablissement_id)))

    async def lire() -> list:
        return list(await connexion.fetch(
            "SELECT type, jours, debut, fin, minutes_ajoutees FROM mark.resto_temps_recurrent WHERE site_id = $1", etablissement_id
        ))

    plages = await stable(connexion, ("temps_recurrent", etablissement_id), lire)  # lot 5 : lues une fois par appel, choisies ici
    return max(
        (int(p["minutes_ajoutees"] or 0) for p in plages
         if p["type"] == type_ and local.isoweekday() in (p["jours"] or ()) and p["debut"] <= local.time() < p["fin"]),
        default=0,
    )


# --------------------------------------------------------------------------- les établissements et l'équipe (lus par les services)


async def etablissements_tries(connexion: asyncpg.Connection, actifs_seulement: bool = False) -> list[dict[str, Any]]:
    """Les établissements de la base : ``id``, ``cle``, ``nom``, triés par nom (tous) ou par identifiant (actifs seulement)."""
    if actifs_seulement:
        lignes = await connexion.fetch("SELECT id, cle, nom FROM mark.site WHERE actif ORDER BY id")
    else:
        lignes = await connexion.fetch("SELECT id, cle, nom FROM mark.site ORDER BY nom, id")
    return [{"id": r["id"], "cle": r["cle"], "nom": r["nom"]} for r in lignes]


async def identifiant_du_site(connexion: asyncpg.Connection, cle: str | None) -> int | None:
    """Le site de cette clé ; sans clé, l'UNIQUE établissement actif (aucun s'il y en a plusieurs ou aucun)."""
    if cle:
        return await connexion.fetchval("SELECT id FROM mark.site WHERE cle = $1", cle)
    sites = await connexion.fetch("SELECT id FROM mark.site WHERE actif ORDER BY id LIMIT 2")
    return sites[0]["id"] if len(sites) == 1 else None


async def telephones_des_destinataires(connexion: asyncpg.Connection, etablissement_id: int) -> list[str]:
    """Les téléphones des personnes actives marquées « destinataire par défaut » pour cet établissement ou toute l'entreprise."""
    lignes = await connexion.fetch(
        "SELECT telephone FROM mark.personne WHERE actif AND destinataire_defaut AND telephone IS NOT NULL AND (site_id IS NULL OR site_id = $1) ORDER BY id",
        etablissement_id,
    )
    return [r["telephone"] for r in lignes]
