"""[.mark] Module Restauration, lot 10, étape 2 : le rattrapage, les alertes et la santé des liaisons (tâches planifiées), sur de vraies bases et une caisse ENREGISTRÉE.

| Test | Ce qu'il prouve |
|---|---|
| rattrapage des envois | une commande dont l'envoi est à reprendre repart (une seule fois, la caisse qui l'a déjà n'en reçoit pas une seconde) ; une commande trop récente attend ; une autre base n'est pas touchée |
| sans réponse | une commande reçue par la caisse mais pas prise en charge après le seuil prévient UNE personne, une fois ; la commande trop récente, déjà prise ou jamais arrivée à la caisse ne prévient personne |
| mode passif | les messages gardés par la caisse sont relus et traités comme ceux reçus ; acquittés une fois traités ; un échec reste à la caisse |
| filet | en mode normal, la relève ne se fait qu'au seuil réglable (5 min) ; une liaison rompue n'est pas relevée |
| 401 | un jeton refusé à la relève rompt la liaison ; on ne relève plus |
| nuit | la relecture complète remet la carte, les ruptures et l'état d'aplomb ; une liaison rompue n'est pas relue |
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import httpx

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration
from api.db.bases_clients import restauration_liaison as lia
from api.db.bases_clients.horloge import horloge
from api.services.restauration.caisse import rattrapage as rat
from api.services.restauration.caisse.prises import hubrise_reception as hr
from api.tests.mark.equipe_commun import sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import (  # noqa: F401
    _brancher,
    _caisse_enregistree,
    _corps,
    _etablissements_propres,
    _evenements,
    application_configuree,
)
from api.tests.mark.test_restauration_envoi_caisse import CaisseQuiRegistre, Secours, _commande, _etat
from api.tests.mark.test_restauration_hubrise_reception import _ordre


async def _branche(db_session, seconde_base):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    pdv = "pdv-rat-" + uuid.uuid4().hex[:6]
    await _brancher(cas, cas.sites_a[0], cas.a, cas.base_a, _caisse_enregistree(pdv=pdv), cas.admin.id)
    return cas, cas.sites_a[0], pdv


async def _vieillir(base: str, numero: str, minutes: int) -> None:
    c = await schema.connecter(base)
    try:
        await c.execute("UPDATE mark.resto_commande SET maj_le = $2 WHERE numero = $1", uuid.UUID(numero), horloge(base).maintenant() - timedelta(minutes=minutes))
    finally:
        await c.close()


async def test_le_rattrapage_reprend_une_commande_a_reprendre_une_seule_fois(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab, _ = await _branche(db_session, seconde_base)
    a_reprendre = await _commande(cas.base_a, etab, statut="envoyee", tentatives=1)
    trop_recente = await _commande(cas.base_a, etab, statut="envoyee", tentatives=1)
    chez_b = await _commande(cas.base_b, cas.sites_b[0])  # l'autre organisation, pas dans les bases données
    await _vieillir(cas.base_a, a_reprendre, 10)
    caisse = CaisseQuiRegistre()
    secours = Secours()
    bilan = await rat.rattrapage_des_envois(None, bases=[(cas.a, cas.base_a)], transport=caisse.transport, secours=secours)
    assert bilan == {str(cas.a): 1}
    assert caisse.posts() == 1 and list(caisse.recues) == [a_reprendre]
    assert (await _etat(cas.base_a, a_reprendre))["ref_fournisseur"] == "caisse-" + a_reprendre[:8]
    assert (await _etat(cas.base_a, trop_recente))["ref_fournisseur"] is None  # attend son tour
    assert (await _etat(cas.base_b, chez_b))["statut"] == "nouvelle"
    # un second passage : la commande a sa référence et vient d'être touchée, rien ne repart
    await rat.rattrapage_des_envois(None, bases=[(cas.a, cas.base_a)], transport=caisse.transport, secours=secours)
    assert caisse.posts() == 1


async def test_une_commande_sans_reponse_previent_une_fois_et_seulement_quand_il_le_faut(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab, _ = await _branche(db_session, seconde_base)
    c = await schema.connecter(cas.base_a)
    try:
        sans_reponse = await _commande(cas.base_a, etab, statut="envoyee")
        recente = await _commande(cas.base_a, etab, statut="envoyee")
        prise = await _commande(cas.base_a, etab, statut="acceptee")
        jamais_arrivee = await _commande(cas.base_a, etab, statut="envoyee")
        for numero in (sans_reponse, recente, prise, jamais_arrivee):
            await c.execute("UPDATE mark.resto_commande SET ref_fournisseur = $2 WHERE numero = $1", uuid.UUID(numero), None if numero == jamais_arrivee else "r-" + numero[:6])
    finally:
        await c.close()
    await _vieillir(cas.base_a, sans_reponse, 10)
    await _vieillir(cas.base_a, prise, 10)
    await _vieillir(cas.base_a, jamais_arrivee, 10)
    secours = Secours()
    assert await rat.alerte_des_commandes_sans_reponse(None, bases=[(cas.a, cas.base_a)], secours=secours) == {str(cas.a): 1}
    assert len(secours.messages) == 1 and "C7" in secours.messages[0][1] and secours.messages[0][0] == cas.a
    await rat.alerte_des_commandes_sans_reponse(None, bases=[(cas.a, cas.base_a)], secours=secours)
    assert len(secours.messages) == 1  # une seule fois par commande


def _caisse_passive(pdv: str, evenements: list[dict], *, ordres: dict, jeton_faux: bool = False, etat: str = "08-point-de-vente-normal.json"):
    """La caisse de la relève : ses messages gardés (``GET /callback/events``), leur acquittement (``DELETE``), le reste comme la caisse enregistrée."""
    base = _caisse_enregistree(pdv=pdv, ordres=ordres, etat=etat)
    journal = {"acquittes": [], "relevees": 0}

    def repondre(r: httpx.Request) -> httpx.Response:
        if r.url.path == "/v1/callback/events" and r.method == "GET":
            journal["relevees"] += 1
            if jeton_faux:
                return httpx.Response(401, json=_corps("18-erreur-jeton-faux.json"))
            return httpx.Response(200, json=[e for e in evenements if e["id"] not in journal["acquittes"]])
        if r.url.path.startswith("/v1/callback/events/") and r.method == "DELETE":
            journal["acquittes"].append(r.url.path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={})
        return base.handler(r)

    transport = httpx.MockTransport(repondre)
    transport.journal = journal
    return transport


async def _passif(base: str, etab: int, passif: bool, releve_il_y_a_min: int | None) -> None:
    c = await schema.connecter(base)
    try:
        derniere = None if releve_il_y_a_min is None else horloge(base).maintenant() - timedelta(minutes=releve_il_y_a_min)
        await c.execute("UPDATE mark.resto_liaison SET mode_passif = $2, derniere_releve = $3 WHERE site_id = $1", etab, passif, derniere)
    finally:
        await c.close()


async def test_le_mode_passif_releve_les_messages_gardes_et_ne_les_acquitte_qu_une_fois_traites(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab, pdv = await _branche(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab, statut="envoyee")
    await _passif(cas.base_a, etab, True, None)
    evenements = [
        {"id": "ev-passif-1", "resource_type": "order", "event_type": "update", "order_id": "8qknnxn"},
        {"id": "ev-passif-2", "resource_type": "order", "event_type": "update", "order_id": "introuvable"},  # la caisse ne connaît plus cette commande : le traitement échoue
    ]
    caisse = _caisse_passive(pdv, evenements, ordres={"8qknnxn": _ordre("21-commande-acceptee.json", private_ref=numero)})
    bilan = await hr.releve_des_messages_hubrise(None, bases=[(cas.a, cas.base_a)], transport=caisse)
    assert bilan[f"{cas.a}:{etab}"] == {"lus": 2, "traites": 1, "restent": 1}
    assert (await _etat(cas.base_a, numero))["statut"] == "acceptee"
    assert caisse.journal["acquittes"] == ["ev-passif-1"]  # celui qui a échoué reste à la caisse
    # relève suivante : le premier n'est plus rendu (acquitté), le second est retenté ; la commande n'est pas retraitée
    bilan = await hr.releve_des_messages_hubrise(None, bases=[(cas.a, cas.base_a)], transport=caisse)
    assert bilan[f"{cas.a}:{etab}"]["lus"] == 1 and caisse.journal["acquittes"] == ["ev-passif-1"]
    assert len([1 for t, d in await _evenements(cas.a, etab) if t == "commande.statut" and d["numero"] == numero]) == 1


async def test_en_mode_normal_la_releve_attend_son_seuil_et_une_liaison_rompue_n_est_pas_relevee(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab, pdv = await _branche(db_session, seconde_base)
    caisse = _caisse_passive(pdv, [], ordres={})
    await _passif(cas.base_a, etab, False, 1)  # relevée il y a une minute : pas encore (seuil 5 min)
    assert await hr.releve_des_messages_hubrise(None, bases=[(cas.a, cas.base_a)], transport=caisse) == {}
    assert caisse.journal["relevees"] == 0
    await _passif(cas.base_a, etab, False, 6)
    assert f"{cas.a}:{etab}" in await hr.releve_des_messages_hubrise(None, bases=[(cas.a, cas.base_a)], transport=caisse) and caisse.journal["relevees"] == 1
    c = await schema.connecter(cas.base_a)
    try:
        await c.execute("UPDATE mark.resto_liaison SET etat = 'rompue', derniere_erreur = 'jeton_refuse', mode_passif = true WHERE site_id = $1", etab)
    finally:
        await c.close()
    assert await hr.releve_des_messages_hubrise(None, bases=[(cas.a, cas.base_a)], transport=caisse) == {}
    assert caisse.journal["relevees"] == 1


async def test_un_jeton_refuse_a_la_releve_rompt_la_liaison(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab, pdv = await _branche(db_session, seconde_base)
    await _passif(cas.base_a, etab, True, None)
    caisse = _caisse_passive(pdv, [], ordres={}, jeton_faux=True)
    bilan = await hr.releve_des_messages_hubrise(None, bases=[(cas.a, cas.base_a)], transport=caisse)
    assert bilan[f"{cas.a}:{etab}"] == {"erreur": "jeton_refuse"}
    c = await schema.connecter(cas.base_a)
    try:
        assert (await lia.liaison(c, etab))["etat"] == "rompue"
    finally:
        await c.close()
    await hr.releve_des_messages_hubrise(None, bases=[(cas.a, cas.base_a)], transport=caisse)
    assert caisse.journal["relevees"] == 1  # plus de relève : on ne harcèle pas une caisse qui refuse


async def test_la_relecture_de_nuit_remet_ruptures_et_etat_d_aplomb_et_saute_une_liaison_rompue(db_session, seconde_base, sans_preparation_des_organisations, application_configuree):  # noqa: F811
    cas, etab, pdv = await _branche(db_session, seconde_base)
    c = await schema.connecter(cas.base_a)
    try:
        for code in ("TIRA-1", "SUPP-OEUF"):
            await restauration.poser_rupture(c, etab, code, True, None, "caisse")
        await lia.poser_etat_de_la_caisse(c, etab, {"mode": "pause", "minutes_en_plus": 0, "reprise": None, "temps_preparation": None})
        base_avant = len(await restauration.ruptures_du_restaurant(c, etab))
    finally:
        await c.close()
    assert base_avant == 0
    caisse = _caisse_enregistree(pdv=pdv, etat="07-point-de-vente-deborde.json")
    bilan = await rat.relecture_de_nuit(None, bases=[(cas.a, cas.base_a)], transport=caisse)
    assert bilan[str(cas.a)][str(etab)]["erreur"] is None
    c = await schema.connecter(cas.base_a)
    try:
        assert {"TIRA-1", "SUPP-OEUF"} & {r["code_caisse"] for r in await restauration.ruptures_du_restaurant(c, etab)}
        assert (await restauration.etat_caisse(c, etab))["mode"] == "deborde"
        assert (await lia.liaison(c, etab))["etat"] == "ok"
        await c.execute("UPDATE mark.resto_liaison SET etat = 'rompue', derniere_erreur = 'jeton_refuse' WHERE site_id = $1", etab)
    finally:
        await c.close()
    muette = _caisse_enregistree(pdv=pdv)
    assert (await rat.relecture_de_nuit(None, bases=[(cas.a, cas.base_a)], transport=muette))[str(cas.a)] == {}
    assert muette.demandes == []
