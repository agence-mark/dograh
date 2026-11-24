"""[.mark] Plan final Partie 1, lot 10 (A4) : un refus DÉFINITIF de HubRise est reconnu comme tel et prévient le restaurant tout de suite.

Accès retiré (401), droits manquants (403), point de vente ou adresse disparus (404) : rejouer cinq fois ne change rien, et le restaurant n'est prévenu qu'au cinquième essai (trente minutes plus
tard). Un 503 reste une panne qu'on réessaie, sans déranger personne. Le refus définitif met la commande en ``echec`` (cause ``caisse``), UNE alerte avec la commande jointe, plus aucun envoi.
"""

from __future__ import annotations

import httpx
import pytest

from api.services.restauration.caisse import envoi_caisse as ec
from api.tests.mark import equipe_commun as _equipe
from api.tests.mark import test_contacts_portail as _contacts
from api.tests.mark import test_restauration_caisse_routes as _routes
from api.tests.mark.test_restauration_envoi_caisse import Secours, _commande, _etablissement_branche, _etat

sans_preparation_des_organisations = _equipe.sans_preparation_des_organisations
seconde_base = _contacts.seconde_base
application_configuree = _routes.application_configuree


def _transport(code: int) -> httpx.MockTransport:
    return httpx.MockTransport(lambda r: httpx.Response(code, json={}))


@pytest.mark.parametrize("code", [401, 403, 404])
async def test_un_refus_definitif_de_hubrise_previent_le_restaurant_au_premier_essai(code, db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    secours = Secours()
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=_transport(code), secours=secours)
    assert (await _etat(cas.base_a, numero))["statut"] == "echec"  # avant : « envoyee », réessayée cinq fois
    assert len(secours.messages) == 1 and "C7" in secours.messages[0][1]


async def test_une_panne_de_hubrise_reste_une_panne_reessayee_sans_deranger_personne(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    secours = Secours()
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=_transport(503), secours=secours)
    assert (await _etat(cas.base_a, numero))["statut"] == "envoyee" and secours.messages == []
