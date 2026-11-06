"""[.mark] Builder, revue R2 (suite) : un nœud webhook ne peut pas nommer la clé du cerveau du builder.

Refusé à l'enregistrement du parcours (création, mise à jour, validation du builder) ; l'envoi et la résolution d'un transfert la
refusent aussi au moment de s'en servir (``webhook_delivery``, ``transfer_resolver``)."""

from __future__ import annotations

from typing import Any

from api.db import db_client
from api.services.builder.cerveau.marque import REFUS, est_la_cle_du_cerveau
from api.services.workflow.errors import ItemKind, WorkflowError


async def erreurs_cle_reservee_des_webhooks(workflow_definition: dict[str, Any] | None, organization_id: int | None) -> list[WorkflowError]:
    if not workflow_definition or not organization_id:
        return []
    erreurs: list[WorkflowError] = []
    for noeud in workflow_definition.get("nodes") or []:
        if not isinstance(noeud, dict) or noeud.get("type") != "webhook":
            continue
        donnees = noeud.get("data") if isinstance(noeud.get("data"), dict) else {}
        identifiant = donnees.get("credential_uuid")
        if not identifiant:
            continue
        credential = await db_client.get_credential_by_uuid(identifiant, organization_id)
        if credential is not None and est_la_cle_du_cerveau(credential):
            erreurs.append(
                WorkflowError(kind=ItemKind.node, id=noeud.get("id"), field="data.credential_uuid", message=REFUS)
            )
    return erreurs
