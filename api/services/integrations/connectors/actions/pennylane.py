"""[.mark] Pennylane (compta): the state of an invoice, for a reminder or after-sales call (U3 sexies, point 8, F3).

State « À essayer ». Documentation read on 03/11/2026: https://pennylane.readme.io/reference/
getcustomerinvoices (``GET https://app.pennylane.com/api/external/v2/customer_invoices``; query
``filter`` = JSON array of ``{field, operator, value}``, ``invoice_number`` takes ``eq``; ``limit`` 1 to
100; items hold ``id``, ``invoice_number``, ``status`` (paid, partially_paid, late, upcoming, draft,
credit_note, cancelled), ``paid``, ``remaining_amount_with_tax``, ``deadline``; scope
``customer_invoices:readonly``). ⚠️ The guide on filters spells the parameter ``filters`` (plural) where
the reference says ``filter``: the reference is followed, to check on a test company. The path is
relative to the host the relay knows (``/api/external/v2``). Through Nango's relay (integration
``pennylane``).

- ``read_invoice`` (reads, may be anticipated): by the invoice number the caller gives. It reads
  nothing else of the books: no amount of another invoice, no list.
"""

from __future__ import annotations

import json
from typing import Any

from api.services.integrations.connectors.catalogue import (
    Action,
    Connecteur,
    ContexteAction,
    Parametre,
    declarer,
)
from api.services.integrations.connectors.nango import Requete

LONGUEUR_NUMERO = 40


def _preparer(params: dict, _ctx: ContexteAction) -> Requete:
    numero = str(params["numero"]).strip()
    if not numero or len(numero) > LONGUEUR_NUMERO:
        raise ValueError("Pennylane: the invoice number is not usable.")
    filtre = [{"field": "invoice_number", "operator": "eq", "value": numero}]
    return Requete(
        "GET",
        "/api/external/v2/customer_invoices",
        params={"filter": json.dumps(filtre, separators=(",", ":")), "limit": 1},
    )


def _resultat(reponse: Any, _params: dict, _ctx: ContexteAction) -> dict:
    items = (reponse or {}).get("items") or []
    if not items:
        return {"facture": None, "aucune": True}
    f = items[0]
    sortie = {
        "numero": f.get("invoice_number"),
        "etat": f.get("status"),
        "payee": bool(f.get("paid")),
        "reste_a_payer": f.get("remaining_amount_with_tax"),
        "echeance": f.get("deadline"),
    }
    return {"facture": {k: v for k, v in sortie.items() if v is not None}}


PENNYLANE = declarer(
    Connecteur(
        nom="pennylane",
        libelle="Pennylane",
        integration="pennylane",
        actions=(
            Action(
                nom="read_invoice",
                description="Read the state of a customer invoice from its number: paid or not, what remains, the due date.",
                parametres=(Parametre("numero", description="The invoice number, as the caller reads it (for example F20230001)."),),
                ecrit=False,
                anticipable_permis=True,
                preparer=_preparer,
                resultat=_resultat,
            ),
        ),
    )
)
