"""[.mark] Chantier Partie 1, lot 19 bis, étape A : la caisse (HubRise), rejouée sur les VRAIES réponses du 20/11 (``reponses_hubrise/19bis/``).

Aucun test n'appelle HubRise : le transport est enregistré (``httpx.MockTransport``) et ne rend que ce que HubRise a rendu en réel.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from api.services.restauration.prises import hubrise_traduction as ht
from api.services.restauration.prises.hubrise_client import ClientHubrise
from api.services.restauration.prises.prise_hubrise import PriseHubrise

DOSSIER = Path(__file__).parents[1] / "reponses_hubrise" / "19bis"


def _f(nom: str) -> dict:
    """Un fichier enregistré : ``{"demande": ..., "reponse": {"code", "corps"}}``."""
    return json.loads((DOSSIER / f"{nom}.json").read_text(encoding="utf-8"))


def _rendue(nom: str):
    """La réponse enregistrée, prête à être rendue par un transport simulé."""
    r = _f(nom)["reponse"]
    return httpx.Response(r["code"], json=r["corps"])


def _prise(rendre) -> PriseHubrise:
    return PriseHubrise(ClientHubrise("jeton-de-test", point_de_vente="w8xvp-0", transport=httpx.MockTransport(rendre)))


# --------------------------------------------------------------------------- K2


def test_quantite_decimale_relue_de_la_caisse():
    """K2 : HubRise relit ``"0.25"``, ``"1.0"`` et ``"0.123457"`` (01b, 03, 206c) : la lecture ne les refuse plus."""
    assert ht._quantite("0.25") == ht.Decimal("0.25")
    assert ht._quantite("1.0") == 1 and ht._quantite("0.123457") == ht.Decimal("0.123457")
    lue = ht.commande_de_hubrise(_f("01b-poids-relu")["reponse"]["corps"])
    # 16,00 x 0,25 = 4,00 ; 12,00 x 0,333333 = 3,999996 tronqué à 3,99 (la caisse a compté 7,99) : la lecture rend la valeur de la ligne, jamais une erreur
    assert [(l["prix_unitaire"], l["quantite"], l["quantite_lue"]) for l in lue["lignes"]] == [(400, 1, "0.25"), (399, 1, "0.333333")]
    assert lue["total"] == 799


async def test_reponse_illisible_apres_envoi_reussi_jamais_echec():
    """K2 : le POST a réussi (200, ``quantity "0.25"``, 01b) : une lecture qui échoue ensuite ne fait JAMAIS un échec, la commande est en caisse (``ENVOYEE``, ``id`` brut)."""
    vraie = _f("01b-poids-relu")["reponse"]["corps"]
    # une réponse que notre lecture ne sait pas lire (un montant mal écrit), mais que HubRise a bien acceptée
    illisible = {**vraie, "total": "7,99 EUR"}
    prise = _prise(lambda r: httpx.Response(200, json=illisible))
    commande = {"numero": "mark-19bis-poids", "mode": "emporter", "lignes": [{"nom": "Mozzarella", "code_caisse": "MOZ", "prix_unitaire": 400, "quantite": 1}]}
    resultat = await prise.faire_envoyer(commande)
    assert (resultat.statut, resultat.ref_fournisseur) == ("ENVOYEE", vraie["id"])
