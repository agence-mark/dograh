"""[.mark] U3 sexies point 7 : l'onglet Identifiants d'Intégrations.

Types du fork (clé d'API, jeton, identifiant et mot de passe, en-tête libre). Deux ajouts :

* « utilisé par » : les outils de l'organisation qui s'appuient sur l'identifiant (authentification d'une requête,
  d'un serveur MCP, d'un résolveur de transfert, ou en-tête secret). Calculé à l'affichage, jamais stocké ;
* remplacement d'une valeur sans jamais l'afficher : seule la partie secrète change, le nom d'en-tête et le
  nom d'utilisateur restent.
"""

from __future__ import annotations

from typing import Any

from api.db import db_client
from api.services.tool_management import _credential_uuids_from_definition

# Le champ secret de chaque type.
CHAMP_SECRET = {
    "api_key": "api_key",
    "bearer_token": "token",
    "basic_auth": "password",
    "custom_header": "header_value",
}


async def utilisation(organization_id: int) -> dict[str, list[dict[str, Any]]]:
    """``{credential_uuid: [{tool_uuid, nom, categorie}]}`` pour les outils non archivés de CETTE organisation."""
    sortie: dict[str, list[dict[str, Any]]] = {}
    for outil in await db_client.get_tools_for_organization(organization_id):
        for uuid in _credential_uuids_from_definition(outil.definition or {}):
            sortie.setdefault(uuid, []).append(
                {
                    "tool_uuid": outil.tool_uuid,
                    "nom": outil.name,
                    "categorie": str(getattr(outil.category, "value", outil.category)),
                }
            )
    return sortie


class RemplacementImpossible(ValueError):
    pass


def remplacer_la_valeur(type_identifiant: str, donnees: dict[str, Any], valeur: str) -> dict[str, Any]:
    """Les données de l'identifiant avec la seule valeur secrète remplacée."""
    champ = CHAMP_SECRET.get(type_identifiant)
    if champ is None:
        raise RemplacementImpossible("This credential holds no secret value to replace.")
    if not valeur or not valeur.strip():
        raise RemplacementImpossible("The new value is empty.")
    return {**donnees, champ: valeur}
