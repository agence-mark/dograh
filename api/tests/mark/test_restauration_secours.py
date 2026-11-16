"""[.mark] Module Restauration, lot 10 : l'échelle de secours (note de Pierre du 11/11, § 10) quand l'envoi à la caisse échoue pour de bon, et la liste fermée d'adresses de la prise HubRise.

| Test | Ce qu'il prouve |
|---|---|
| échelle | refus de la caisse : ticket sur l'imprimante liée, SMS au gérant (mobiles français de l'équipe, destinataires par défaut, actifs, de CET établissement), mail en plus ; « appel au restaurant » dit NON FAIT |
| une fois | rejouer le secours n'envoie pas un second SMS ni un second ticket |
| sans moyen | sans imprimante ni compte de téléphonie : rien ne part, rien ne casse, le bilan le dit |
| liste fermée | une adresse hors de la liste de la fiche n'atteint jamais le réseau (adresse étrangère, schéma, port, identifiants, machine interne, métadonnées) ; la garde mord : retirée, les mêmes adresses partent |
"""

from __future__ import annotations

import uuid

import httpx
import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.services.restauration import envoi_caisse as ec
from api.services.restauration import secours as sc
from api.services.restauration.prises import hubrise_client as hc
from api.services.restauration.prises.adresses import AdresseRefusee
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import application_configuree  # noqa: F401
from api.tests.mark.test_restauration_envoi_caisse import CaisseQuiRegistre, Secours, _commande, _etablissement_branche
from api.tests.mark.test_restauration_heure_caisse import _faux_twilio


async def _equipe(base: str, etab: int, autre_etab: int) -> None:
    c = await schema.connecter(base)
    try:
        for prenom, tel, defaut, actif, site in (
            ("Gérant", "+33611111111", True, True, etab),  # le bon
            ("Associé", "+33622222222", True, True, None),  # toute l'entreprise : aussi
            ("Fixe", "+33140000000", True, True, etab),  # pas un mobile : jamais
            ("Parti", "+33633333333", True, False, etab),  # désactivé
            ("Pas défaut", "+33644444444", False, True, etab),  # pas destinataire par défaut
            ("Voisin", "+33655555555", True, True, autre_etab),  # un autre établissement
        ):
            await c.execute("INSERT INTO mark.personne (site_id, prenom, telephone, destinataire_defaut, actif) VALUES ($1, $2, $3, $4, $5)", site, prenom, tel, defaut, actif)
    finally:
        await c.close()


async def test_l_echelle_pose_le_ticket_envoie_le_sms_au_gerant_une_seule_fois_et_dit_que_l_appel_n_est_pas_fait(db_session, seconde_base, sans_preparation_des_organisations, application_configuree, monkeypatch):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    envoyes: list = []
    _faux_twilio(monkeypatch, envoyes)
    await _equipe(cas.base_a, etab, cas.sites_a[1])
    async with client_http() as c:  # une imprimante à côté de la caisse : le premier échelon
        assert (await c.post(f"/api/v1/restauration/etablissements/{etab}/imprimante", json={}, headers={"X-API-Key": cas.cle_a})).status_code == 200
    numero = await _commande(cas.base_a, etab)
    mail = Secours()
    issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=CaisseQuiRegistre(mode="refus").transport, secours=mail)
    assert issue.issue == "refusee" and len(mail.messages) == 1  # le mail part en plus
    base = await schema.connecter(cas.base_a)
    try:
        assert (await lia.le_ticket(base, etab, numero))["statut"] == "en_file"  # 1. ticket sur l'imprimante
        assert (await lia.liaison(base, etab))["prise"] == "hubrise"  # la caisse reste la liaison
        commande = {"numero": numero, "numero_court": "C7", "lignes": [{"quantite": 1, "nom": "Reine"}], "client": {"telephone": "+33600000001"}}
        # le secours rejoué : ni second ticket, ni second SMS
        bilan = await sc.secours_de_la_commande(base, cas.a, etab, commande, "refus de la caisse")
    finally:
        await base.close()
    assert sorted(m["To"] for m in envoyes) == ["+33611111111", "+33622222222"]  # 2. les deux mobiles du gérant et de l'associé, seulement
    assert all("C7" in m["Body"] and "Reine" in m["Body"] and "+33600000001" in m["Body"] and len(m["Body"]) <= 160 for m in envoyes)
    assert bilan == {"ticket": "deja_la", "sms": 0, "appel": "non_fait"}  # 3. l'appel au restaurant n'est pas fait, et le dit


async def test_sans_imprimante_ni_compte_de_telephonie_rien_ne_part_et_rien_ne_casse(db_session, seconde_base, sans_preparation_des_organisations, application_configuree, monkeypatch):  # noqa: F811
    cas, etab = await _etablissement_branche(db_session, seconde_base)
    envoyes: list = []
    _faux_twilio(monkeypatch, envoyes, compte=False)
    await _equipe(cas.base_a, etab, cas.sites_a[1])
    numero = await _commande(cas.base_a, etab)
    mail = Secours()
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, transport=CaisseQuiRegistre(mode="refus").transport, secours=mail)
    assert envoyes == [] and len(mail.messages) == 1  # seul le mail part
    base = await schema.connecter(cas.base_a)
    try:
        assert await lia.le_ticket(base, etab, numero) is None
        bilan = await sc.secours_de_la_commande(base, cas.a, etab, {"numero": numero, "lignes": [], "client": {}}, "essai")
    finally:
        await base.close()
    assert bilan == {"ticket": "aucune_imprimante", "sms": 0, "appel": "non_fait"}


# --------------------------------------------------------------------------- la liste fermée d'adresses de la prise HubRise

HOSTILES = (
    "https://evil.example/v1",  # une machine étrangère
    "http://api.hubrise.com/v1",  # le mauvais schéma
    "https://api.hubrise.com:8443/v1",  # le mauvais port
    "https://api.hubrise.com@evil.example/v1",  # des identifiants qui cachent la vraie machine
    "https://api.hubrise.com.evil.example/v1",  # un nom qui commence comme le bon
    "https://127.0.0.1/v1",  # la machine elle-même
    "http://169.254.169.254/latest/meta-data",  # les métadonnées du nuage
    "https://api.hubrise.com/v10",  # un dossier voisin
)


async def _tenter(base: str, transport) -> str:
    try:
        await hc.ClientHubrise("jeton", transport=transport, base=base).requete("GET", "/location")
    except AdresseRefusee:
        return "refusee"
    except hc.ErreurHubrise:
        return "partie"
    return "partie"


async def test_une_adresse_hors_de_la_liste_fermee_n_atteint_jamais_le_reseau_et_la_garde_mord(monkeypatch):
    vues: list = []
    transport = httpx.MockTransport(lambda r: (vues.append(str(r.url)), httpx.Response(200, json={}))[1])
    for adresse in HOSTILES:
        assert await _tenter(adresse, transport) == "refusee", adresse
    assert vues == []  # aucune demande n'est sortie
    # la garde MORD : si on la retire (mutation), les mêmes adresses partent, et ce test le voit
    monkeypatch.setattr(hc, "verifier_adresse", lambda prise, adresse, labo=False: adresse)
    parties = [await _tenter(adresse, transport) for adresse in HOSTILES]
    assert parties == ["partie"] * len(HOSTILES) and len(vues) == len(HOSTILES)
    # et le bon chemin n'est pas refusé par excès de zèle
    monkeypatch.undo()
    assert await _tenter("https://api.hubrise.com/v1", transport) == "partie"
