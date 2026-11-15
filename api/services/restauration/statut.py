"""[.mark] Module Restauration, lot 15 : le geste « changer le statut d'une commande » venu du portail (Rush : étape suivante, « Annuler » 5 s).

Un seul geste, trois temps, dans cet ordre (contrat portail ↔ fork § 1) :
1. le chemin fermé du classeur (``changer_statut``, source ``portail``) : ``OK`` / ``DEJA_FAIT`` / ``INTERDIT`` / ``INTROUVABLE`` ;
2. si ça a passé : la caisse est informée **quand la fiche de sa prise sait le faire** (une annulation ; ``annulation`` dans les capacités),
   sinon rien, jamais une erreur ; un échec de la prise s'écrit au journal d'erreur (R1) et ne défait pas le geste ;
3. si ça a passé : l'événement ``commande.statut`` (source ``portail``) entre dans le flux, le portail relit la base.

La prise d'un établissement n'est pas connue du classeur avant le lot 9 (liaison à la caisse) : ``poser_resolveur_de_prise`` est la couture
qu'il branche ; sans résolveur, aucune caisse n'est informée (c'est vrai : aucune n'est liée).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

import asyncpg
from loguru import logger

from api.db.bases_clients import restauration
from api.db.bases_clients.restauration_commun import Resultat
from api.services.restauration import flux
from api.services.restauration.prises.prise import GesteNonPermis, Prise

SOURCE = "portail"

# (organisation, établissement) -> la prise liée à cet établissement, ou ``None``. Posé par le lot 9.
ResolveurDePrise = Callable[[int, int], Awaitable[Prise | None]]
_resolveur: ResolveurDePrise | None = None


def poser_resolveur_de_prise(resolveur: ResolveurDePrise | None) -> None:
    global _resolveur
    _resolveur = resolveur


async def _informer_la_caisse(organisation_id: int, etablissement_id: int, numero: str, vers: str) -> bool:
    """Vrai si la caisse a été informée. Seule l'annulation a un geste côté prise ; les autres étapes sont lues sur la caisse."""
    if vers != "annulee" or _resolveur is None:
        return False
    try:
        prise = await _resolveur(organisation_id, etablissement_id)
        if prise is None or not prise.capacites.annulation:
            return False
        await prise.annuler_commande(numero)
        return True
    except GesteNonPermis:
        return False
    except Exception as erreur:  # noqa: BLE001 -- R1 : la caisse en panne ne défait pas le geste, le rattrapage la rejoint ; on le voit ici
        logger.error(f"[.mark] Order {numero}: telling the till about the cancellation failed: {erreur!r}")
        return False


async def changer_le_statut(
    organisation_id: int, connexion: asyncpg.Connection, etablissement_id: int, numero: str | uuid.UUID, de: str, vers: str
) -> tuple[Resultat, bool]:
    """Rend ``(resultat, caisse_informee)``. L'événement n'est émis que si le statut a réellement changé."""
    resultat = await restauration.changer_statut(connexion, etablissement_id, numero, de, vers, SOURCE)
    if resultat.statut != "OK":
        return resultat, False
    numero_s = str(resultat.faits["numero"])
    informee = await _informer_la_caisse(organisation_id, etablissement_id, numero_s, vers)
    await flux.emettre(organisation_id, etablissement_id, "commande.statut", {"numero": numero_s, "de": de, "vers": vers, "source": SOURCE})
    return resultat, informee
