"""[.mark] Un verrou par organisation dans la base de Dograh (cloture-code-avant-migration, constat 28).

Sert aux écritures par élément d'une organisation SANS base du client (le miroir est alors la source) :
lire la fiche, poser les champs envoyés, réécrire le tout ne doit pas se faire à deux en même temps.
Un verrou consultatif de transaction (``pg_advisory_xact_lock``) : pris à l'ouverture, rendu à la sortie
(validation ou annulation), jamais oublié. Module à part : le moins de fichiers amont touchés possible.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text

from api.db.base_client import BaseDBClient

# Espace de noms du verrou (premier entier), l'organisation en est le second : deux organisations ne
# s'attendent jamais, deux écritures de la même organisation oui.
ESPACE_DES_ECRITURES_PAR_ELEMENT = 7_301


class VerrouClient(BaseDBClient):
    @asynccontextmanager
    async def verrou_des_ecritures_par_element(self, organization_id: int) -> AsyncIterator[None]:
        async with self.async_session() as session:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:espace, :organisation)"),
                {"espace": ESPACE_DES_ECRITURES_PAR_ELEMENT, "organisation": organization_id},
            )
            # Le verrou vit autant que la transaction de la session : la fermer (sortie du ``async with``,
            # sans rien valider) le rend, même sur une erreur.
            yield
