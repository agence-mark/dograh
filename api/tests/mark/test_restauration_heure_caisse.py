"""[.mark] Module Restauration, lot 10, étape 3 : l'heure changée par la caisse (temps de préparation allongé).

| Test | Ce qu'il prouve |
|---|---|
| message pendant l'appel | la caisse confirme une autre heure : le classeur la reprend (relue par ``statut_commande``, ce que l'outil et le Rush lisent), ``commande.heure`` est émis, la source du journal est « caisse » |
| rejeu | le même message, ou la même heure dite par un autre message : rien de changé, aucun second événement |
| l'appelant est prévenu | envoi « heure changée » ÉTEINT par défaut : rien ; allumé : UN SMS part (SMS existant du fork, Twilio enregistré) avec la nouvelle heure, une fois par heure ; sans mobile français ou sans compte de téléphonie : rien |
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
from api.services.restauration.caisse import envoi_caisse as ec
from api.services.restauration.caisse import heure_caisse as hc
from api.services.restauration.caisse.prises import hubrise_reception as hr
from api.services.restauration.caisse.prises.prise import poser_prise_de_test
from api.services.restauration.caisse.prises.prise_essai import MINUTES_DEBORDE, PriseTest
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


def _faux_twilio(monkeypatch, envoyes: list, *, compte: bool = True):
    """Le SMS du fork (``apres_appel/sms.py``) sur un Twilio ENREGISTRÉ : aucun appel réel ; le compte de « Téléphonie » est donné (ou absent)."""
    from urllib.parse import parse_qs

    import httpx

    from api.services.apres_appel import sms
    from api.services.restauration.envois_et_sms import sms_restauration as sms_resto

    def repondre(r: httpx.Request) -> httpx.Response:
        envoyes.append({k: v[0] for k, v in parse_qs(r.content.decode()).items()})
        return httpx.Response(201, json={"sid": "SM" + uuid.uuid4().hex[:8]})

    monkeypatch.setattr(sms, "nouveau_client", lambda **options: httpx.AsyncClient(transport=httpx.MockTransport(repondre), **options))

    async def identifiants(organisation):
        return ("ACessai", "jeton-essai", "+33700000000") if compte else None

    monkeypatch.setattr(sms_resto, "identifiants_d_envoi", identifiants)


async def test_l_appelant_n_est_prevenu_que_si_l_envoi_est_allume(db_session, seconde_base, sans_preparation_des_organisations, application_configuree, monkeypatch):  # noqa: F811
    cas, etab, pdv = await _branche(db_session, seconde_base)
    envoyes: list = []
    _faux_twilio(monkeypatch, envoyes)
    numero = await _commande_a_vingt_heures(cas.base_a, etab)
    c = await schema.connecter(cas.base_a)
    try:
        envoi_id = await c.fetchval("INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte) VALUES ($1, 'sms', 'heure_changee', 'Votre commande sera prête à {{heure}}') RETURNING id", etab)
        # ÉTEINT par défaut : l'heure est reprise, personne n'est prévenu
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, VINGT_HEURES + timedelta(minutes=5)) is True and envoyes == []
        await c.execute("UPDATE mark.resto_envoi SET actif = true WHERE id = $1", envoi_id)
        # ALLUMÉ : un SMS part, avec la NOUVELLE heure (19 h 10 UTC = 20 h 10 à Paris), au numéro de la commande, de l'expéditeur de « Téléphonie »
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, VINGT_HEURES + timedelta(minutes=10)) is True
        assert len(envoyes) == 1 and envoyes[0]["To"] == "+33600000001" and envoyes[0]["From"] == "+33700000000" and envoyes[0]["Body"] == "Votre commande sera prête à 20:10"
        # la même heure relue : rien de plus ; une nouvelle heure : un nouveau SMS
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, VINGT_HEURES + timedelta(minutes=10)) is False and len(envoyes) == 1
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, VINGT_HEURES + timedelta(minutes=20)) is True and envoyes[-1]["Body"].endswith("20:20")
        # une heure sans fuseau est refusée
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, datetime(2026, 11, 20, 21, 0)) is False and len(envoyes) == 2
        # l'envoi allumé d'un AUTRE établissement ne prévient pas pour celui-ci
        await c.execute("UPDATE mark.resto_envoi SET site_id = $2 WHERE id = $1", envoi_id, cas.sites_a[1])
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, VINGT_HEURES + timedelta(minutes=30)) is True and len(envoyes) == 2
        await c.execute("UPDATE mark.resto_envoi SET site_id = $2 WHERE id = $1", envoi_id, etab)
        # un client sans mobile français : pas de SMS (D4)
        await c.execute("UPDATE mark.resto_commande SET telephone = '+33140000000' WHERE numero = $1", uuid.UUID(numero))
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, VINGT_HEURES + timedelta(minutes=40)) is True and len(envoyes) == 2
    finally:
        await c.close()


async def test_sans_compte_de_telephonie_l_heure_est_reprise_et_rien_ne_part(db_session, seconde_base, sans_preparation_des_organisations, application_configuree, monkeypatch):  # noqa: F811
    cas, etab, pdv = await _branche(db_session, seconde_base)
    envoyes: list = []
    _faux_twilio(monkeypatch, envoyes, compte=False)
    numero = await _commande_a_vingt_heures(cas.base_a, etab)
    c = await schema.connecter(cas.base_a)
    try:
        await c.execute("INSERT INTO mark.resto_envoi (site_id, type, declencheur, texte, actif) VALUES ($1, 'sms', 'heure_changee', 'Prête à {{heure}}', true)", etab)
        assert await hc.appliquer_l_heure(c, cas.a, etab, numero, VINGT_HEURES + timedelta(minutes=5)) is True  # l'heure est reprise quand même
        assert envoyes == [] and await hc.prevenir_l_appelant(c, cas.a, etab, numero, VINGT_HEURES) is False
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
