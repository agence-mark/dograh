"""[.mark] Plan final Partie 1, lot 10 (A3, reprise 2e audit) : une commande DÉJÀ arrivée chez HubRise n'est jamais mise en « echec » par la règle de la marge.

Scénario : envoyée sans souci à 19 h 00, promise 19 h 20 ; à 19 h 10 le calendrier la reprend et cherche la commande chez la caisse avant de renvoyer ; la recherche tombe sur une panne passagère (503). Avant :
« echec » et alerte « saisissez-la » : le restaurant la saisissait alors qu'elle était déjà en caisse (deux préparations). Maintenant elle reste « envoyee » (l'alerte « restée nouvelle » veille sur elle).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.db.bases_clients.horloge import horloge, remplacer
from api.services.restauration.caisse import envoi_caisse as ec
from api.services.restauration.caisse import rattrapage as rat
from api.tests.mark import equipe_commun as _equipe
from api.tests.mark import test_contacts_portail as _contacts
from api.tests.mark import test_restauration_caisse_routes as _routes
from api.tests.mark.test_restauration_envoi_caisse import CaisseQuiRegistre, Secours, _commande, _etablissement_branche, _etat

sans_preparation_des_organisations = _equipe.sans_preparation_des_organisations
seconde_base = _contacts.seconde_base
application_configuree = _routes.application_configuree

PANNE = httpx.MockTransport(lambda r: httpx.Response(503, json={}))


async def _promettre(base: str, numero: str, heure) -> None:
    c = await schema.connecter(base)
    try:
        await c.execute("UPDATE mark.resto_commande SET heure_annoncee = $2 WHERE numero = $1", uuid.UUID(numero), heure)
    finally:
        await c.close()


async def test_une_commande_deja_en_caisse_ne_passe_pas_en_echec_quand_la_recherche_tombe_en_panne_dans_la_marge(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    debut = horloge(cas.base_a).maintenant()
    await _promettre(cas.base_a, numero, debut + timedelta(minutes=20))
    secours = Secours()
    with remplacer(cas.base_a, debut):
        await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=CaisseQuiRegistre().transport, secours=secours)
    assert (await _etat(cas.base_a, numero))["ref_fournisseur"] is not None  # elle est arrivée chez la caisse
    for minute in range(1, 16):  # la caisse tombe en panne : dont le moment de la marge (19 h 10)
        with remplacer(cas.base_a, debut + timedelta(minutes=minute)):
            await rat.rattrapage_des_envois(None, bases=[(cas.a, cas.base_a)], transport=PANNE, secours=secours)
    assert (await _etat(cas.base_a, numero))["statut"] == "envoyee"  # avant : « echec »
    assert secours.messages == []  # avant : « la caisse ne répond pas, saisissez-la »


async def test_le_calendrier_ne_reveille_a_la_marge_que_les_commandes_pas_encore_arrivees_en_caisse(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    """La marge sert à prévenir pour une commande que la caisse n'a pas : celle qui a sa référence chez la caisse n'a pas de raison d'être réveillée pour elle."""
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    sans_ref, avec_ref = await _commande(cas.base_a, etab), await _commande(cas.base_a, etab)
    debut = horloge(cas.base_a).maintenant()
    c = await schema.connecter(cas.base_a)
    try:
        for numero, ref in ((sans_ref, None), (avec_ref, "ref-caisse")):
            await c.execute(
                "UPDATE mark.resto_commande SET statut = 'envoyee', tentatives = 5, ref_fournisseur = $2, heure_annoncee = $3, maj_le = $4 WHERE numero = $1",
                uuid.UUID(numero), ref, debut + timedelta(minutes=15), debut,
            )  # cinq essais : la reprise espacée attend 15 min ; seule la marge (promise - 10 min) peut réveiller à la 10e
        with remplacer(cas.base_a, debut + timedelta(minutes=10)):
            assert await lia.commandes_a_reprendre(c, etab) == [sans_ref]
    finally:
        await c.close()
