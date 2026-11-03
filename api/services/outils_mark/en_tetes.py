"""[.mark] U3 sexies point 2 : les en-têtes texte, variable ou secret.

Un secret vit dans un identifiant chiffré de l'organisation (``external_credentials``) : la définition de l'outil ne
garde que sa référence. Sa valeur n'est lue qu'au moment d'envoyer la requête, jamais renvoyée ni journalisée ; un
aperçu la montre masquée.
"""

from __future__ import annotations

from typing import Any

from api.db import db_client
from api.services.builder.cerveau.marque import est_la_cle_du_cerveau
from api.services.configuration.masking import mask_key
from api.utils.template_renderer import render_template

_CLES_DE_VALEUR = ("header_value", "api_key", "token", "password")


class SecretIntrouvable(ValueError):
    pass


def valeur_du_secret(donnees: dict[str, Any]) -> str:
    for cle in _CLES_DE_VALEUR:
        if donnees.get(cle):
            return str(donnees[cle])
    return ""


async def resoudre(
    entrees: list[dict[str, Any]] | None, contexte: dict[str, Any], organization_id: int | None
) -> tuple[dict[str, str], set[str]]:
    """(en-têtes prêts à partir, noms des en-têtes secrets). Lève ``SecretIntrouvable`` si un secret n'est plus là."""
    entetes: dict[str, str] = {}
    secrets: set[str] = set()
    for e in entrees or []:
        nom = str(e.get("nom") or "").strip()
        if not nom:
            continue
        sorte = e.get("sorte") or "texte"
        if sorte == "secret":
            credential = None
            if organization_id and e.get("identifiant_uuid"):
                credential = await db_client.get_credential_by_uuid(e["identifiant_uuid"], organization_id)
            if credential is None or est_la_cle_du_cerveau(credential):
                raise SecretIntrouvable(f"The secret of the header '{nom}' no longer exists.")
            entetes[nom] = valeur_du_secret(credential.credential_data or {})
            secrets.add(nom)
        elif sorte == "variable":
            entetes[nom] = str(render_template(str(e.get("valeur") or ""), contexte) or "")
        else:
            entetes[nom] = str(e.get("valeur") or "")
    return entetes, secrets


def apercu(entetes: dict[str, str], secrets: set[str]) -> dict[str, str]:
    """Les en-têtes pour l'écran : les secrets masqués."""
    return {n: (mask_key(v) if n in secrets else v) for n, v in entetes.items()}
