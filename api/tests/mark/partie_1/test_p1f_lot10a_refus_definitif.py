"""[.mark] Plan final Partie 1, lot 10 (A4) : un refus DÉFINITIF de HubRise est reconnu comme tel et prévient le restaurant tout de suite.

Accès retiré (401), droits manquants (403), point de vente ou adresse disparus (404) : rejouer cinq fois ne change rien, et le restaurant n'est prévenu qu'au cinquième essai (trente minutes plus
tard). Un 503 reste une panne qu'on réessaie, sans déranger personne. Le refus définitif met la commande en ``echec`` (cause ``caisse``), UNE alerte avec la commande jointe, plus aucun envoi.
"""

from __future__ import annotations

import httpx
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.services.restauration.caisse import envoi_caisse as ec
from api.services.restauration.caisse import rattrapage as rat
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


async def _etat_de_la_liaison(base: str, etab: int) -> str:
    c = await schema.connecter(base)
    try:
        return (await lia.liaison(c, etab))["etat"]
    finally:
        await c.close()


@pytest.mark.parametrize("code", [401, 403, 404])
async def test_tout_refus_definitif_rompt_la_liaison_et_pas_seulement_le_401(code, db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    """Reprise 4 de l'audit : la liaison n'était rompue que sur 401 ; sur 403 ou 404 elle restait « branchée » alors que la commande était en échec."""
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=_transport(code), secours=Secours())
    assert await _etat_de_la_liaison(cas.base_a, etab) == "rompue"


@pytest.mark.parametrize("code", [401, 403, 404])
async def test_un_acces_retire_entre_le_premier_envoi_et_le_renvoi_previent_tout_de_suite(code, db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    """Reprise 3 de l'audit : premier envoi en panne passagère (503), puis accès retiré ; au renvoi, la RECHERCHE avant renvoi reçoit le refus : c'est définitif, pas une panne (avant :
    cinq essais, alerte au dernier)."""
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    secours = Secours()
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=_transport(503), secours=secours)
    assert (await _etat(cas.base_a, numero))["statut"] == "envoyee" and secours.messages == []
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=_transport(code), secours=secours)
    assert (await _etat(cas.base_a, numero))["statut"] == "echec"
    assert len(secours.messages) == 1 and "C7" in secours.messages[0][1]


async def test_un_404_sur_une_commande_precise_ne_rompt_pas_la_liaison(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    """Un 404 sur UNE commande (annulée côté caisse, effacée) n'est pas la perte de l'accès : la liaison reste branchée."""
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    secours = Secours()
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=_transport(503), secours=secours)
    c = await schema.connecter(cas.base_a)
    try:
        prise = await rat.prise_de_l_etablissement(rat.ContexteDePrise(c, cas.a, etab, cas.base_a, _transport(404)))
        with pytest.raises(Exception) as erreur:
            await prise.relire_la_commande("ref-effacee")
        assert getattr(erreur.value, "definitif", False) is False
    finally:
        await c.close()
    assert await _etat_de_la_liaison(cas.base_a, etab) != "rompue"
