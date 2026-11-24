"""[.mark] Module Restauration, routes : l'ouverture de la base d'une organisation, écrite une seule fois pour tous les routeurs du module.

Une route ouvre la base de CETTE organisation, relit l'établissement dedans (inconnu d'elle : 404 sans dire lequel), joue son geste dans un schéma à jour
(une base en retard répond 409 avec la marche à suivre) et ferme, sur toute issue. Une base injoignable répond 503 sans jamais montrer le texte interne.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import HTTPException

from api.db.bases_clients.connexion import BaseClientIndisponible, connecter
from api.db.bases_clients.restauration_commun import etablissements_existants
from api.routes.base_client import schema_a_jour
from api.services.base_client import rattachement

BASE_INDISPONIBLE = "The client database is unavailable. Try again in a moment."


def refus(code: int, message: str) -> HTTPException:
    return HTTPException(status_code=code, detail=message)


async def connexion_de_l_organisation(organization_id: int):
    """La connexion à la base de l'organisation (409 sans base rattachée, 503 base injoignable)."""
    nom = await rattachement.nom_de_la_base(organization_id)
    if not nom:
        raise refus(409, "Attach a client database first: the establishments live there.")
    try:
        return await connecter(nom)
    except BaseClientIndisponible:
        raise refus(503, BASE_INDISPONIBLE) from None


async def connexion_de_l_etablissement(organization_id: int, etablissement_id: int):
    """La connexion, après avoir relu l'établissement dedans : un identifiant inconnu d'elle (d'une autre organisation, ou qui n'existe pas) est un 404 sans dire lequel."""
    connexion = await connexion_de_l_organisation(organization_id)
    try:
        if await etablissements_existants(connexion, [etablissement_id]) != {etablissement_id}:
            raise refus(404, "Establishment not found.")
    except BaseException:
        await connexion.close()
        raise
    return connexion


@asynccontextmanager
async def base_de_l_organisation(organization_id: int) -> AsyncIterator:
    connexion = await connexion_de_l_organisation(organization_id)
    try:
        async with schema_a_jour(connexion):
            yield connexion
    finally:
        await connexion.close()


@asynccontextmanager
async def base_de_l_etablissement(organization_id: int, etablissement_id: int) -> AsyncIterator:
    connexion = await connexion_de_l_etablissement(organization_id, etablissement_id)
    try:
        async with schema_a_jour(connexion):
            yield connexion
    finally:
        await connexion.close()
