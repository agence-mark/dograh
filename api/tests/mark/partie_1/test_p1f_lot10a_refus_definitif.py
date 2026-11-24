"""[.mark] Plan final Partie 1, lot 10 (A4) : un refus DÉFINITIF de HubRise est reconnu comme tel et prévient le restaurant tout de suite.

Accès retiré (401), droits manquants (403), point de vente ou adresse disparus (404) : rejouer cinq fois ne change rien, et le restaurant n'est prévenu qu'au cinquième essai (trente minutes plus
tard). Un 503 reste une panne qu'on réessaie, sans déranger personne. Le refus définitif met la commande en ``echec`` (cause ``caisse``), UNE alerte avec la commande jointe, plus aucun envoi.
"""

from __future__ import annotations

import httpx
import pytest

from api.services.restauration.caisse import envoi_caisse as ec
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import application_configuree  # noqa: F401
from api.tests.mark.test_restauration_envoi_caisse import Secours, _commande, _etablissement_branche, _etat


def _transport(code: int) -> httpx.MockTransport:
    return httpx.MockTransport(lambda r: httpx.Response(code, json={}))


@pytest.mark.parametrize("code", [401, 403, 404])
async def test_un_refus_definitif_de_hubrise_previent_le_restaurant_au_premier_essai(code, db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    secours = Secours()
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=_transport(code), secours=secours)
    assert (await _etat(cas.base_a, numero))["statut"] == "echec"  # avant : « envoyee », réessayée cinq fois
    assert len(secours.messages) == 1 and "C7" in secours.messages[0][1]


async def test_une_panne_de_hubrise_reste_une_panne_reessayee_sans_deranger_personne(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    secours = Secours()
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=_transport(503), secours=secours)
    assert (await _etat(cas.base_a, numero))["statut"] == "envoyee" and secours.messages == []
