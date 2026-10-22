"""[.mark] Lot F3 : les cases des listes de valeurs, dans la base du client.

Lecture des listes qui portent une case, et écriture des cases d'une valeur. L'auteur est posé dans
``mark.auteur`` (comme ``referentiel.py``) : le déclencheur ``liste_valeur_referentiel`` (017) écrit alors
l'auteur réel au journal, et non le compte technique de la connexion.
"""

from __future__ import annotations

import asyncpg

from api.schemas.listes_valeurs import (
    CASES_PAR_LISTE,
    ListeDeValeurs,
    ListesValeurs,
    ValeurDeListe,
)

_CASES = ("regle_seul", "opportunite", "urgent")


class ValeurInconnue(ValueError):
    """A value the list does not hold. Safe to show."""


async def lire_listes(connexion: asyncpg.Connection) -> ListesValeurs:
    lignes = await connexion.fetch(
        "SELECT liste, code, libelle, ordre, actif, regle_seul, opportunite, urgent "
        "FROM mark.liste_valeur WHERE liste = ANY($1::text[]) ORDER BY liste, ordre, code",
        list(CASES_PAR_LISTE),
    )
    return ListesValeurs(
        listes=[
            ListeDeValeurs(
                liste=liste,
                cases=list(cases),
                valeurs=[
                    ValeurDeListe(**{k: r[k] for k in r.keys() if k != "liste"})
                    for r in lignes
                    if r["liste"] == liste
                ],
            )
            for liste, cases in CASES_PAR_LISTE.items()
        ]
    )


async def ecrire_cases(connexion: asyncpg.Connection, modifications: list[dict], auteur: str) -> None:
    """Set the boxes sent, value by value, in ONE transaction. An unknown value: nothing is written."""
    async with connexion.transaction():
        await connexion.execute("SELECT set_config('mark.auteur', $1, true)", auteur[:200])
        for m in modifications:
            envoyees = {c: m[c] for c in _CASES if c in m and m[c] is not None}
            existe = await connexion.fetchval(
                "SELECT true FROM mark.liste_valeur WHERE liste = $1 AND code = $2", m["liste"], m["code"]
            )
            if not existe:
                raise ValeurInconnue(f"« {m['code']} » is not a value of the list « {m['liste']} ».")
            if not envoyees:
                continue
            sets = ", ".join(f"{c} = ${i + 3}" for i, c in enumerate(envoyees))
            await connexion.execute(
                f"UPDATE mark.liste_valeur SET {sets} WHERE liste = $1 AND code = $2",
                m["liste"],
                m["code"],
                *envoyees.values(),
            )
