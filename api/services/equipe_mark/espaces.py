"""[.mark] Les espaces : le Labo (une seule source), le nom d'affichage d'une organisation, ce que voit un compte.

* **Le Labo** : l'organisation marquée ``MARK_ESPACE`` = ``{"espace": "labo"}`` dans ``organization_configurations``.
  C'est la SEULE source ; ``MARK_BIBLIOTHEQUE_ORGANISATION_ID`` n'est que le repli tant que rien n'est marqué (C8).
  ``constantes.organisation_bibliotheque()`` est synchrone et appelée partout : elle lit ce cache, rafraîchi à chaque
  requête authentifiée quand il a plus de ``DUREE_CACHE_S`` secondes (donc au plus 30 s de retard, sur chaque
  processus) et tout de suite après une écriture. Si la lecture en base échoue, l'ancienne valeur reste et le repli sert.
* **Le nom d'affichage** : ``MARK_NOM_AFFICHAGE`` = ``{"nom": "..."}``, sinon ``provider_id``.
"""

from __future__ import annotations

import time

from loguru import logger

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.services.equipe_mark.acces import organisation_est_ouverte

DUREE_CACHE_S = 30.0
NOM_MAX = 120

_cle_espace = OrganizationConfigurationKey.MARK_ESPACE.value
_cle_nom = OrganizationConfigurationKey.MARK_NOM_AFFICHAGE.value

# (organisation marquée Labo ou None, instant de la lecture) ; None tant que rien n'a été lu.
_cache: tuple[int | None, float] | None = None


def labo_en_cache() -> int | None:
    """Le Labo marqué en base tel que lu la dernière fois, ou ``None`` (alors le repli par variable sert)."""
    return _cache[0] if _cache is not None else None


def reinitialiser_cache() -> None:
    global _cache
    _cache = None


async def rafraichir_labo(*, force: bool = False) -> int | None:
    """Relit le marquage si le cache est périmé (ou ``force``). Jamais d'exception : une panne garde l'ancienne valeur."""
    global _cache
    maintenant = time.monotonic()
    if not force and _cache is not None and maintenant - _cache[1] < DUREE_CACHE_S:
        return _cache[0]
    try:
        marque = await db_client.organisation_marquee_labo(_cle_espace)
    except Exception:
        logger.exception("Lecture du marquage du Labo impossible : l'ancienne valeur (ou le repli) sert")
        return _cache[0] if _cache is not None else None
    _cache = (marque, maintenant)
    return marque


async def definir_labo(organization_id: int, est_labo: bool) -> None:
    """Marque (ou démarque) le Labo ; un seul à la fois, le cache est rafraîchi tout de suite."""
    if est_labo:
        await db_client.marquer_labo(_cle_espace, organization_id)
    else:
        await db_client.demarquer_labo(_cle_espace, organization_id)
    await rafraichir_labo(force=True)


async def definir_nom_affichage(organization_id: int, nom: str | None) -> str | None:
    """Pose le nom affiché (texte sur une ligne, borné) ou le retire (``None`` ou vide) ; rend le nom retenu."""
    propre = " ".join("".join(c for c in (nom or "") if c.isprintable()).split())[:NOM_MAX]
    if propre:
        await db_client.upsert_configuration(organization_id, _cle_nom, {"nom": propre})
        return propre
    await db_client.delete_configuration(organization_id, _cle_nom)
    return None


async def synchroniser_appartenances(user) -> set[int]:
    """Aligne les appartenances d'un compte de l'équipe sur ce que son rôle ouvre ; rend les organisations visibles.

    Il rejoint celles que le rôle ouvre (une organisation créée après lui comprise) et quitte celles qu'il n'ouvre
    plus. Un compte sans rôle d'équipe garde ses appartenances telles quelles.
    """
    await rafraichir_labo()
    from api.services.builder.constantes import organisation_bibliotheque

    labo_id = organisation_bibliotheque()
    acces = await db_client.acces_du_compte(user.id)
    deja = set(await db_client.organisations_du_compte(user.id))
    if acces is None:
        return deja
    toutes = await db_client.lister_organisations()
    ouvertes = {i for i, _ in toutes if organisation_est_ouverte(acces, i, labo_id)}
    for i in sorted(ouvertes - deja):
        await db_client.add_user_to_organization(user.id, i)
    retirer = sorted(deja - ouvertes)
    if retirer:
        await db_client.retirer_du_compte_les_organisations(user.id, retirer)
    return ouvertes


async def lister_espaces(user) -> list[dict]:
    """Les espaces accessibles au compte : id, libellé, Labo ou client."""
    from api.services.builder.constantes import organisation_bibliotheque

    visibles = await synchroniser_appartenances(user)
    labo_id = organisation_bibliotheque()
    toutes = await db_client.lister_organisations()
    noms = await db_client.noms_d_affichage(_cle_nom, sorted(visibles))
    return [
        {
            "id": i,
            "nom": noms.get(i) or provider_id,
            "provider_id": provider_id,
            "espace": "labo" if labo_id is not None and i == labo_id else "client",
            "selectionne": i == user.selected_organization_id,
        }
        for i, provider_id in toutes
        if i in visibles
    ]
