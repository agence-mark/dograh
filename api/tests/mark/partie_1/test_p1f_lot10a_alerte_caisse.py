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
from api.db.bases_clients.horloge import remplacer
from api.services.restauration.caisse import envoi_caisse as ec
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
