"""[.mark] Module Restauration, lot 5 : où se passe l'appel (la base du client et l'établissement servi), pour les outils de l'agent.

Un outil de l'agent ne reçoit jamais un identifiant du modèle : la base est celle de l'ORGANISATION du moteur, l'établissement est celui
que l'appel sert (la fiche choisie par l'agent, ou portée par l'appel, ou le numéro appelé : ``services/etablissements/appel.py``). Une
organisation qui n'a qu'un seul établissement dans sa base le sert par défaut. Aucune base rattachée, ou plusieurs établissements sans
celui de l'appel : ``LieuIntrouvable`` (l'outil rend ``INDISPONIBLE``, jamais un autre établissement au hasard : le cloisonnement d'abord).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger


class LieuIntrouvable(RuntimeError):
    """On ne sait pas quelle base ni quel établissement l'appel sert."""


@dataclass(frozen=True)
class Lieu:
    nom_base: str
    etablissement_id: int
    organisation_id: int


async def _workflow_de_l_appel(run_id: int | None) -> int | None:
    if not run_id:
        return None
    try:
        from api.db import db_client

        run = await db_client.get_workflow_run_by_id(run_id)
        return getattr(run, "workflow_id", None)
    except Exception:  # noqa: BLE001 -- jamais une panne pendant un appel : l'établissement se cherchera autrement
        logger.exception(f"[.mark] Call: the agent of run {run_id} could not be read")
        return None


async def base_et_cle_de_l_appel(ctx: Any) -> tuple[str, str | None]:
    """``(nom de la base du client, clé de l'établissement servi ou None)`` pour CET appel. Aucune requête sur le classeur ici.
    ``ctx`` : le contexte d'une action de connecteur (organisation du moteur, contexte d'appel, run)."""
    from api.services.base_client.rattachement import nom_de_la_base
    from api.services.etablissements.appel import etablissement_de_lappel

    organisation = ctx.organization_id
    nom_base = await nom_de_la_base(organisation) if organisation else None
    if not nom_base:
        raise LieuIntrouvable("Aucune base de client rattachée à cette organisation.")
    servi = await etablissement_de_lappel(organisation, await _workflow_de_l_appel(ctx.run_id), ctx.appel or {})
    return nom_base, (servi.etablissement.id if servi else None)


async def identifiant_de_l_etablissement(connexion: Any, cle: str | None) -> int:
    """L'identifiant du site dans la base du client : celui de la clé, sinon l'UNIQUE établissement actif. Jamais un autre au hasard."""
    from api.db.bases_clients.restauration_commun import identifiant_du_site

    identifiant = await identifiant_du_site(connexion, cle)
    if identifiant is None:
        raise LieuIntrouvable("L'établissement servi par cet appel n'est pas dans la base du client.")
    return identifiant
