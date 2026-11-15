"""[.mark] Module Restauration, lot 10, étape 3 : l'heure changée par la caisse (temps de préparation allongé).

| Test | Ce qu'il prouve |
|---|---|
| message pendant l'appel | la caisse confirme une autre heure : le classeur la reprend (relue par ``statut_commande``, ce que l'outil et le Rush lisent), ``commande.heure`` est émis, la source du journal est « caisse » |
| rejeu | le même message, ou la même heure dite par un autre message : rien de changé, aucun second événement |
| l'appelant est prévenu | envoi « heure changée » allumé : le module d'envoi est appelé UNE fois avec la nouvelle heure ; éteint (par défaut) : jamais ; allumé sans module branché : faux, dit au journal |
| à l'envoi | une caisse qui répond avec sa propre heure (prise débordée) : reprise dans le classeur et événement émis |
| cloisonnement | l'heure d'un message ne change que la commande de SON établissement |
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as lia
from api.services.restauration import envoi_caisse as ec
from api.services.restauration import heure_caisse as hc
from api.services.restauration.prises import hubrise_reception as hr
from api.services.restauration.prises.prise import poser_prise_de_test
from api.services.restauration.prises.prise_essai import MINUTES_DEBORDE, PriseTest
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import (  # noqa: F401
    _brancher,
    _caisse_enregistree,
    _etablissements_propres,
    _evenements,
    application_configuree,
)
from api.tests.mark.test_restauration_envoi_caisse import Secours, _commande
from api.tests.mark.test_restauration_hubrise_reception import _message, _ordre

VINGT_HEURES = datetime(2026, 11, 20, 19, 0, tzinfo=UTC)


async def _commande_a_vingt_heures(base: str, etab: int) -> str:
    numero = await _commande(base, etab, statut="acceptee")
    c = await schema.connecter(base)
    try:
        await c.execute("UPDATE mark.resto_commande SET heure_annoncee = $2, ref_fournisseur = '8qknnxn' WHERE numero = $1", uuid.UUID(numero), VINGT_HEURES)
    finally:
        await c.close()
    return numero


async def _branche(db_session, seconde_base):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    pdv = "pdv-heure-" + uuid.uuid4().hex[:6]
    await _brancher(cas, cas.sites_a[0], cas.a, cas.base_a, _caisse_enregistree(pdv=pdv), cas.admin.id)
    return cas, cas.sites_a[0], pdv


def _confirmee(numero: str, quand: datetime) -> dict:
    return {"8qknnxn": _ordre("21-commande-acceptee.json", private_ref=numero, confirmed_time=quand.isoformat())}


async def test_la_caisse_change_l_heure_pendant_l_appel_le_classeur_et_le_flux_la_reprennent(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab, pdv = await _branche(db_session, seconde_base)
    numero = await _commande_a_vingt_heures(cas.base_a, etab)
    nouvelle = VINGT_HEURES + timedelta(minutes=15)
    caisse = _caisse_enregistree(pdv=pdv, ordres=_confirmee(numero, nouvelle))
    assert (await hr.traiter_le_message(None, _message("m-heure-1", location_id=pdv), transport=caisse))["effet"] == "heure"
    c = await schema.connecter(cas.base_a)
    try:
        vue = (await restauration.statut_commande(c, etab, numero=numero)).faits["commandes"][0]  # ce que l'outil de l'agent, le Rush et Commandes lisent
        assert vue["heure_annoncee"] == nouvelle
        journal = await c.fetchrow("SELECT source FROM mark.resto_journal WHERE objet = 'resto_commande' AND ligne_id = $1 ORDER BY id DESC LIMIT 1", numero)
        assert journal["source"] == "caisse"
    finally:
        await c.close()
    assert [d for t, d in await _evenements(cas.a, etab) if t == "commande.heure"] == [{"numero": numero, "heure_annoncee": nouvelle.isoformat()}]
    # le même message rejoué, puis la même heure dite par un AUTRE message : rien de plus
    await hr.traiter_le_message(None, _message("m-heure-1", location_id=pdv), transport=caisse)
    assert (await hr.traiter_le_message(None, _message("m-heure-2", location_id=pdv), transport=caisse))["effet"] == "inchange"
    assert len([1 for t, _ in await _evenements(cas.a, etab) if t == "commande.heure"]) == 1


async def test_l_appelant_n_est_prevenu_que_si_l_envoi_est_allume_et_le_module_branche(db_session, seconde_base, sans_preparation_des_organisations, application_configuree, monkeypatch):  # noqa: F811
    cas, etab, pdv = await _branche(db_session, seconde_base)
    appels = []

    async def envoyeur(connexion, etablissement_id, numero, envoi, heure):
        appels.append((etablissement_id, numero, envoi["texte"], heure))

    monkeypatch.setattr(hc, "ENVOYEUR", envoyeur)
    numero = await _commande_a_vingt_heures(cas.base_a, etab)
    c = await schema.connecter(cas.base_a)
    try:
        envoi_id = await c.fetchval("INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte) VALUES ($1, 'sms', 'heure_changee', 'Votre commande sera prête à {heure}') RETURNING id", etab)
        # éteint par défaut : personne n'est prévenu
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, VINGT_HEURES + timedelta(minutes=5)) is True and appels == []
        await c.execute("UPDATE mark.resto_envoi SET actif = true WHERE id = $1", envoi_id)
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, VINGT_HEURES + timedelta(minutes=10)) is True
        assert appels == [(etab, numero, "Votre commande sera prête à {heure}", VINGT_HEURES + timedelta(minutes=10))]
        # la même heure : rien, personne n'est prévenu une seconde fois
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, VINGT_HEURES + timedelta(minutes=10)) is False and len(appels) == 1
        # une heure sans fuseau est refusée
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, datetime(2026, 11, 20, 21, 0)) is False
        monkeypatch.setattr(hc, "ENVOYEUR", None)
        assert await hc.prevenir_l_appelant(c, etab, numero, VINGT_HEURES) is False  # allumé mais aucun module : dit au journal, jamais simulé
        # l'envoi allumé d'un AUTRE établissement ne prévient pas pour celui-ci
        await c.execute("UPDATE mark.resto_envoi SET site_id = $2 WHERE id = $1", envoi_id, cas.sites_a[1])
        monkeypatch.setattr(hc, "ENVOYEUR", envoyeur)
        assert await hc.prevenir_l_appelant(c, etab, numero, VINGT_HEURES) is False and len(appels) == 1
    finally:
        await c.close()


async def test_une_caisse_qui_repond_avec_sa_propre_heure_est_reprise_a_l_envoi(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    c = await schema.connecter(cas.base_a)
    try:
        await c.execute("INSERT INTO mark.resto_liaison (site_id, prise) VALUES ($1, 'test')", etab)
    finally:
        await c.close()
    numero = await _commande(cas.base_a, etab)
    c = await schema.connecter(cas.base_a)
    try:
        await c.execute("UPDATE mark.resto_commande SET heure_annoncee = $2 WHERE numero = $1", uuid.UUID(numero), VINGT_HEURES)
    finally:
        await c.close()
    poser_prise_de_test(PriseTest("deborde"))
    try:
        issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, secours=Secours())
    finally:
        poser_prise_de_test(None)
    assert issue.issue == "envoyee"
    c = await schema.connecter(cas.base_a)
    try:
        assert (await lia.etat_de_la_commande(c, etab, numero))["heure_annoncee"] == VINGT_HEURES + timedelta(minutes=MINUTES_DEBORDE)
    finally:
        await c.close()
    assert [d["heure_annoncee"] for t, d in await _evenements(cas.a, etab) if t == "commande.heure"] == [(VINGT_HEURES + timedelta(minutes=MINUTES_DEBORDE)).isoformat()]


async def test_l_heure_d_un_message_ne_change_que_la_commande_de_son_etablissement(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab, pdv = await _branche(db_session, seconde_base)
    voisine = await _commande_a_vingt_heures(cas.base_a, cas.sites_a[1])  # l'autre établissement de la même organisation
    caisse = _caisse_enregistree(pdv=pdv, ordres=_confirmee(voisine, VINGT_HEURES + timedelta(minutes=30)))
    await hr.traiter_le_message(None, _message("m-heure-croise", location_id=pdv), transport=caisse)
    c = await schema.connecter(cas.base_a)
    try:
        assert (await lia.etat_de_la_commande(c, cas.sites_a[1], voisine))["heure_annoncee"] == VINGT_HEURES
    finally:
        await c.close()
