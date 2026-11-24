"""[.mark] Plan final Partie 1, lot 10 (A3) : l'alerte d'une caisse en panne se cale sur l'HEURE PROMISE à la personne, plus seulement sur le cinquième essai.

Scénario : à 12 h 00, une commande est promise pour 12 h 08 et la caisse ne répond pas. Avant, le restaurant n'était prévenu qu'au cinquième essai (reprises espacées de 2, 4, 8 puis 15 minutes :
plus de trente minutes) ; la personne arrivait devant une commande que personne n'avait saisie. Maintenant, dès que l'heure promise est à moins de ``MARGE_AVANT_L_HEURE`` minutes (ou passée) et que la caisse
n'a pas pris la commande, le restaurant est prévenu UNE fois, avec la commande jointe. Une commande promise plus tard garde le comportement d'avant : on réessaie, personne n'est dérangé.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api.db.bases_clients import connexion as schema
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

MIDI = datetime(2026, 11, 12, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))


async def _promettre(base: str, numero: str, heure: datetime) -> None:
    c = await schema.connecter(base)
    try:
        await c.execute("UPDATE mark.resto_commande SET heure_annoncee = $2 WHERE numero = $1", uuid.UUID(numero), heure)
    finally:
        await c.close()


async def test_une_heure_promise_proche_et_une_caisse_muette_previennent_le_restaurant_tout_de_suite(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    await _promettre(cas.base_a, numero, MIDI + timedelta(minutes=8))
    caisse, secours = CaisseQuiRegistre(mode="panne"), Secours()
    with remplacer(cas.base_a, MIDI):
        await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert (await _etat(cas.base_a, numero))["statut"] == "echec"  # avant : encore « envoyee », personne prévenu avant le cinquième essai
    assert len(secours.messages) == 1 and "C7" in secours.messages[0][1]
    with remplacer(cas.base_a, MIDI + timedelta(minutes=3)):  # rejoué : plus d'envoi, plus d'alerte
        await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert len(secours.messages) == 1


async def test_une_heure_promise_lointaine_laisse_reessayer_sans_deranger_personne(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    await _promettre(cas.base_a, numero, MIDI + timedelta(minutes=90))
    caisse, secours = CaisseQuiRegistre(mode="panne"), Secours()
    with remplacer(cas.base_a, MIDI):
        await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert (await _etat(cas.base_a, numero))["statut"] == "envoyee" and secours.messages == []
    with remplacer(cas.base_a, MIDI + timedelta(minutes=85)):  # l'heure approche : cette fois la personne est prévenue
        await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    assert (await _etat(cas.base_a, numero))["statut"] == "echec" and len(secours.messages) == 1


async def test_le_calendrier_des_reprises_se_reveille_a_l_heure_promise_moins_la_marge(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    """Reprise 1 de l'audit : l'heure promise n'était lue qu'à un essai raté, que le calendrier espacé (jusqu'à 15 min) ne fait pas tomber à temps. Une caisse muette dès 19 h,
    heure promise dans 20 min, marge de 10 min : le restaurant doit être prévenu à la 10e minute au plus tard (les essais espacés tombent à 0, 1, 3, 7 puis 15)."""
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    debut = horloge(cas.base_a).maintenant()  # la base écrit « maj_le » à l'heure réelle : le calendrier part de là
    await _promettre(cas.base_a, numero, debut + timedelta(minutes=20))
    caisse, secours = CaisseQuiRegistre(mode="panne"), Secours()
    with remplacer(cas.base_a, debut):
        await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=caisse.transport, secours=secours)
    prevenu_a = None
    for minute in range(1, 31):
        with remplacer(cas.base_a, debut + timedelta(minutes=minute)):
            await rat.rattrapage_des_envois(None, bases=[(cas.a, cas.base_a)], transport=caisse.transport, secours=secours)
        if secours.messages and prevenu_a is None:
            prevenu_a = minute
    assert prevenu_a is not None and prevenu_a <= 10, prevenu_a
    assert (await _etat(cas.base_a, numero))["statut"] == "echec" and len(secours.messages) == 1
