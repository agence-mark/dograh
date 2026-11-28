"""[.mark] Module Restauration, lot 15 : le geste « changer le statut d'une commande » venu du portail (Rush : étape suivante, « Annuler » 5 s).

Un seul geste, trois temps, dans cet ordre (contrat portail ↔ fork § 1) :
1. le chemin fermé du classeur (``changer_statut``, source ``portail``) : ``OK`` / ``DEJA_FAIT`` / ``INTERDIT`` / ``INTROUVABLE`` ;
2. si ça a passé : la caisse est informée **quand la fiche de sa prise sait le faire** (une annulation ; ``annulation`` dans les capacités),
   sinon rien, jamais une erreur ; un échec de la prise s'écrit au journal d'erreur (R1) et ne défait pas le geste ;
3. si ça a passé : l'événement ``commande.statut`` (source ``portail``) entre dans le flux, le portail relit la base.

La prise est celle de la fiche de liaison de l'établissement (lot 9, ``prise_de_l_etablissement``) : sans liaison, c'est le portail, qui n'a rien
à informer. Un essai pose une prise sans fiche de liaison par le paramètre ``resolveur`` du geste (lot 8a, 157 : jamais un réglage global qui reste d'un test à l'autre).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from loguru import logger

from api.db.bases_clients import restauration
from api.db.bases_clients.restauration_commun import Connexion, Resultat
from api.services.restauration.appel_et_memoire import flux
from api.services.restauration.caisse.prises.prise import (
    ContexteDePrise,
    Prise,
    prise_de_l_etablissement,
)

SOURCE = "portail"

# (organisation, établissement) -> la prise liée à cet établissement, ou ``None``. Tests seulement : sans lui, la fiche de liaison fait foi.
ResolveurDePrise = Callable[[int, int], Awaitable[Prise | None]]


async def _prise_de(
    organisation_id: int, connexion: Connexion, etablissement_id: int, nom_base: str | None, resolveur: ResolveurDePrise | None = None
) -> Prise | None:
    if resolveur is not None:
        return await resolveur(organisation_id, etablissement_id)
    return await prise_de_l_etablissement(ContexteDePrise(connexion, organisation_id, etablissement_id, nom_base))


async def informer_la_caisse(
    organisation_id: int, connexion: Connexion, etablissement_id: int, nom_base: str | None, numero: str, vers: str, resolveur: ResolveurDePrise | None = None
) -> bool:
    """Vrai si la caisse a été informée. Seule l'annulation a un geste côté prise ; les autres étapes sont lues sur la caisse."""
    if vers != "annulee":
        return False
    from api.db.bases_clients import restauration_liaison as liaison_db
    from api.services.restauration.caisse.annulation_caisse import dire_l_annulation

    try:
        prise = await _prise_de(organisation_id, connexion, etablissement_id, nom_base, resolveur)
    except Exception as erreur:  # noqa: BLE001 -- R1 : la prise ne se construit pas : l'annulation reste GARDÉE « à dire » (lot 19 bis, K5), le rattrapage la rejoue
        logger.error(f"[.mark] Order {numero}: no till socket to tell about the cancellation: {type(erreur).__name__}")
        await liaison_db.garder_l_annulation_a_dire(connexion, etablissement_id, numero)
        return False
    # Lot 19 bis (K5) : l'annulation est gardée « à dire » avant d'être tentée ; une caisse en panne ne la perd plus, le rattrapage la rejoue (alerte au 5e essai raté).
    return await dire_l_annulation(connexion, organisation_id, etablissement_id, prise, numero)


async def changer_le_statut(
    organisation_id: int,
    connexion: Connexion,
    etablissement_id: int,
    numero: str | uuid.UUID,
    de: str,
    vers: str,
    nom_base: str | None = None,
    *,
    resolveur: ResolveurDePrise | None = None,
) -> tuple[Resultat, bool]:
    """Rend ``(resultat, caisse_informee)``. L'événement n'est émis que si le statut a réellement changé. Une commande ``retenue`` appartient à l'appel en cours
    (§ 17, C-1) : elle part ou s'annule à la fin de l'appel, jamais par le portail."""
    if de == "retenue":
        return Resultat("INTERDIT", {"raison": "appel_en_cours", "statut_actuel": de, "vers": vers}), False
    resultat = await restauration.changer_statut(connexion, etablissement_id, numero, de, vers, SOURCE)
    if resultat.statut != "OK":
        return resultat, False
    numero_s = str(resultat.faits["numero"])
    informee = await informer_la_caisse(organisation_id, connexion, etablissement_id, nom_base, numero_s, vers, resolveur)
    await flux.emettre(organisation_id, etablissement_id, "commande.statut", {"numero": numero_s, "de": de, "vers": vers, "source": SOURCE})
    return resultat, informee
