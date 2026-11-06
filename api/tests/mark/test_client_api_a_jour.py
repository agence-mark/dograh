"""[.mark] Builder partie 2, prérequis 6 : le client d'API généré (``ui/src/client``) colle au schéma du serveur.

| Test | Ce qu'il prouve |
|---|---|
| schéma sans serveur | ``scripts.mark.generer_openapi`` rend le même schéma que ``/api/v1/openapi.json`` |
| client complet | chaque opération du schéma (chemin + méthode) existe dans ``sdk.gen.ts``, et aucune n'y reste qui n'existe plus |

Rouge = le client n'a pas été régénéré après une fusion : ``python -m scripts.mark.generer_openapi`` puis, dans ``ui/``,
``npm run generate-client:fichier``.
"""

from __future__ import annotations

import re
from pathlib import Path

RACINE = Path(__file__).resolve().parents[3]
SDK = RACINE / "ui" / "src" / "client" / "sdk.gen.ts"
METHODES = {"get", "post", "put", "patch", "delete"}


def _operations_du_schema() -> set[tuple[str, str]]:
    from scripts.mark.generer_openapi import schema

    return {(m.upper(), chemin) for chemin, ops in schema()["paths"].items() for m in ops if m in METHODES}


def _operations_du_client() -> set[tuple[str, str]]:
    texte = SDK.read_text(encoding="utf-8")
    trouvees = set()
    # hey-api : « (options.client ?? client).get<…>({ … url: '/api/v1/…', … }) »
    for bloc in re.finditer(r"\)\.(get|post|put|patch|delete)<[\s\S]*?url: '([^']+)'", texte):
        trouvees.add((bloc.group(1).upper(), bloc.group(2)))
    return trouvees


def test_le_schema_sans_serveur_est_celui_que_sert_l_api():
    from api.app import app
    from scripts.mark.generer_openapi import schema

    assert schema() == app.openapi()


def test_le_client_genere_colle_au_schema_du_serveur():
    schema, client = _operations_du_schema(), _operations_du_client()
    assert client, "aucune opération lue dans sdk.gen.ts : le format du générateur a changé"
    manquantes = sorted(schema - client)
    perimees = sorted(client - schema)
    assert not manquantes and not perimees, f"à régénérer : manquantes {manquantes[:10]}, périmées {perimees[:10]}"
