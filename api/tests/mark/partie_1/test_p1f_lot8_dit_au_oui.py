"""[.mark] Plan final Partie 1, lot 8b-1a (E10 ; décision d'Evan du 24/11, plan § 17 l.405) : au « oui », ce que le modèle reçoit dit ce qui est vrai.

La commande est enregistrée (en base), elle part en caisse à la fin de l'appel : le résultat porte ``envoi: a_la_fin_de_l_appel`` et jamais « transmise » (même quand la
caisse ne sait pas dire « acceptée ») ; le fait accompli reste « enregistrée ».

Client : « Oui, c'est bon. » / Avant : le modèle recevait « TRANSMISE » (une caisse sans « acceptée »), comme si la cuisine l'avait déjà. / Après : « enregistrée », envoi à la fin.
"""

from __future__ import annotations

import json

import pytest

from api.services.commande.porte import CLE_TEXTES_DU_CODE
from api.services.restauration.caisse.prises.fiches import TEST, TEST_SANS_ACCEPTEE
from api.tests.mark.partie_1 import combinaisons as C


@pytest.mark.parametrize("capacites", [pytest.param(TEST, id="caisse-qui-accepte"), pytest.param(TEST_SANS_ACCEPTEE, id="caisse-sans-acceptee")])
async def test_au_oui_le_modele_recoit_enregistree_envoi_a_la_fin_de_l_appel(faire_monde, monkeypatch, capacites):
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    partie.e.source.capacites = capacites
    assert await partie.recette("E16")
    retour = json.dumps(partie.e.retours[-1], ensure_ascii=False, default=str)
    assert "TRANSMISE" not in retour.upper() and "envoy" not in retour.casefold(), retour
    assert '"envoi": "a_la_fin_de_l_appel"' in retour, retour
    assert partie.p["enregistree"]["envoi"] == "a_la_fin_de_l_appel"
    assert (partie.e.fiche_de_l_appel[CLE_TEXTES_DU_CODE].get("fait_accompli") or {}).get("fait") == "enregistree"
