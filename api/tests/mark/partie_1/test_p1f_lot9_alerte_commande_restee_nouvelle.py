"""[.mark] Plan final Partie 1, lot 9 : l'alerte « commande restée nouvelle » part à la plus courte de deux échéances.

Scénario : arrivée en caisse à 19 h 00, heure promise 19 h 10, délai réglé à 15 minutes, personne ne lit la commande. Avant, l'alerte partait à 19 h 15, cinq minutes après l'heure
promise. Maintenant elle part dès 19 h 00 (heure promise moins la marge ``MARGE_AVANT_L_HEURE``), une seule fois. Une commande promise plus tard garde le délai réglé.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.horloge import remplacer
from api.services.restauration.caisse import rattrapage as rat
from api.tests.mark import equipe_commun as _equipe
from api.tests.mark import test_contacts_portail as _contacts
from api.tests.mark import test_restauration_caisse_routes as _routes
from api.tests.mark.test_restauration_envoi_caisse import Secours, _commande
from api.tests.mark.test_restauration_rattrapage import _branche

# Les fixtures du dossier sont reprises par nom (pytest les trouve sur le module), sans import de nom ni rustine de lint.
sans_preparation_des_organisations = _equipe.sans_preparation_des_organisations
seconde_base = _contacts.seconde_base
application_configuree = _routes.application_configuree

DIX_NEUF_HEURES = datetime(2026, 11, 12, 19, 0, tzinfo=ZoneInfo("Europe/Paris"))


async def _arrivee_en_caisse(base: str, numero: str, *, a: datetime, promise: datetime | None) -> None:
    c = await schema.connecter(base)
    try:
        await c.execute(
            "UPDATE mark.resto_commande SET statut = 'envoyee', ref_fournisseur = $2, envoyee_le = $3, maj_le = $3, heure_annoncee = $4 WHERE numero = $1",
            uuid.UUID(numero), "r-" + numero[:6], a, promise,
        )
    finally:
        await c.close()


async def _regler_le_delai(base: str, etab: int, minutes: int) -> None:
    c = await schema.connecter(base)
    try:
        await c.execute("UPDATE mark.resto_liaison SET alerte_sans_reponse_min = $2 WHERE site_id = $1", etab, minutes)
    finally:
        await c.close()


async def _passer(cas, secours, quand: datetime) -> dict:
    with remplacer(cas.base_a, quand):
        return await rat.alerte_des_commandes_sans_reponse(None, bases=[(cas.a, cas.base_a)], secours=secours)


async def test_l_heure_promise_proche_previent_avant_le_delai_regle_et_une_seule_fois(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    cas, etab, _ = await _branche(db_session, seconde_base)
    await _regler_le_delai(cas.base_a, etab, 15)
    numero = await _commande(cas.base_a, etab, statut="envoyee")
    await _arrivee_en_caisse(cas.base_a, numero, a=DIX_NEUF_HEURES, promise=DIX_NEUF_HEURES + timedelta(minutes=10))
    secours = Secours()
    assert await _passer(cas, secours, DIX_NEUF_HEURES) == {str(cas.a): 1}
    assert len(secours.messages) == 1 and "C7" in secours.messages[0][1]
    assert await _passer(cas, secours, DIX_NEUF_HEURES + timedelta(minutes=16)) == {str(cas.a): 0}  # une seule fois
    assert len(secours.messages) == 1


async def test_une_heure_promise_lointaine_garde_le_delai_regle(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    cas, etab, _ = await _branche(db_session, seconde_base)
    await _regler_le_delai(cas.base_a, etab, 15)
    numero = await _commande(cas.base_a, etab, statut="envoyee")
    await _arrivee_en_caisse(cas.base_a, numero, a=DIX_NEUF_HEURES, promise=DIX_NEUF_HEURES + timedelta(minutes=60))
    secours = Secours()
    assert await _passer(cas, secours, DIX_NEUF_HEURES + timedelta(minutes=14)) == {str(cas.a): 0}
    assert await _passer(cas, secours, DIX_NEUF_HEURES + timedelta(minutes=15)) == {str(cas.a): 1}
    assert len(secours.messages) == 1


async def test_sans_heure_promise_le_delai_regle_decide_seul(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):
    cas, etab, _ = await _branche(db_session, seconde_base)
    await _regler_le_delai(cas.base_a, etab, 15)
    numero = await _commande(cas.base_a, etab, statut="envoyee")
    await _arrivee_en_caisse(cas.base_a, numero, a=DIX_NEUF_HEURES, promise=None)
    secours = Secours()
    assert await _passer(cas, secours, DIX_NEUF_HEURES + timedelta(minutes=14)) == {str(cas.a): 0}
    assert await _passer(cas, secours, DIX_NEUF_HEURES + timedelta(minutes=15)) == {str(cas.a): 1}
