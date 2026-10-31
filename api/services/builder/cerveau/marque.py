"""[.mark] Builder, revue R2 : la clé du cerveau du builder ne sert qu'au cerveau.

La clé est rangée comme un identifiant ``BEARER_TOKEN`` de l'organisation .mark, marqué ``mark_builder_cerveau`` dans ses données.
Rien d'autre ne doit pouvoir s'en servir : ni la liste des identifiants (HTTP et MCP), ni un outil HTTP qui la nommerait
(``create_tool`` puis un essai), ni une récupération avant l'appel, ni un outil MCP. Ce module est PUR (aucune base, aucun import
lourd) pour être lu de partout.
"""

from __future__ import annotations

from typing import Any

MARQUE_CLE_DU_CERVEAU = "mark_builder_cerveau"
REFUS = "This credential is reserved and cannot be used by a tool."


def est_la_cle_du_cerveau(identifiant: Any) -> bool:
    """Vrai si ``identifiant`` (une ligne de ``organization_credentials``) est la clé du cerveau du builder. ⛔ Ne lève jamais."""
    try:
        donnees = getattr(identifiant, "credential_data", None)
        return isinstance(donnees, dict) and donnees.get(MARQUE_CLE_DU_CERVEAU) is True
    except Exception:  # noqa: BLE001
        return False
