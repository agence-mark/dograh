"""[.mark] Clôture, É36 : « Par » et « Tests » de la page Versions d'un agent, pour une page de versions, sans requête par ligne.

* **Par** : le type d'auteur est rangé sur la version (``auteur_type``) ; le prénom de la personne se lit en UNE requête pour toute la
  page (``prenoms_des_comptes``). Une version d'avant la migration n'a pas d'auteur : « – » à l'écran.
* **Tests** : le résultat de la dernière exécution de chaque test POUR CETTE version (``reussis`` sur ``total``, additionnés), lu en
  UNE requête, bornée à l'organisation, sur les résultats gardés (les 3 dernières exécutions de chaque test). Une version sans
  exécution gardée n'a pas de compte : « – ».
"""

from __future__ import annotations

from typing import Any

from api.db import db_client
from api.services.builder import stock
from api.services.builder.constantes import PREFIXE_RESULTATS


def compte_des_tests(lignes: list[dict[str, Any]], numeros: set[int]) -> dict[int, tuple[int, int]]:
    """Pur. ``lignes`` : une valeur par test (``{"executions": [la plus récente d'abord, ...]}``). Pour chaque numéro de version, la plus
    récente exécution de chaque test jouée sur cette version, additionnée : ``{numéro: (réussis, total)}``."""
    comptes: dict[int, list[int]] = {}
    for ligne in lignes:
        vus: set[int] = set()
        for execution in (ligne or {}).get("executions") or []:
            numero = execution.get("version")
            if not isinstance(numero, int) or numero not in numeros or numero in vus:
                continue
            vus.add(numero)
            total = execution.get("total")
            reussis = execution.get("reussis")
            if not isinstance(total, int) or not isinstance(reussis, int) or total <= 0:
                continue
            cumul = comptes.setdefault(numero, [0, 0])
            cumul[0] += reussis
            cumul[1] += total
    return {n: (c[0], c[1]) for n, c in comptes.items()}


async def tests_par_version(organization_id: int, workflow_id: int, numeros: set[int]) -> dict[int, tuple[int, int]]:
    if not numeros:
        return {}
    lignes = await stock.lister(organization_id, f"{PREFIXE_RESULTATS}{workflow_id}:")
    return compte_des_tests([valeur for _cle, valeur in lignes], numeros)


async def prenoms(versions: list[Any]) -> dict[int, str]:
    ids = [v.auteur_user_id for v in versions if v.auteur_type == "personne" and v.auteur_user_id]
    ids += [v.accepte_par_user_id for v in versions if v.accepte_par_user_id]
    return await db_client.prenoms_des_comptes(ids)
