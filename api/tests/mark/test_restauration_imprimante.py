"""[.mark] Module Restauration, lot 10, étape 4 : la prise IMPRIMANTE (Star CloudPRNT) : le ticket, le protocole, la pose, les deux modes des commandes planifiées.

Vraie authentification (clé d'API pour poser l'imprimante), vraies bases de clients, vrai Redis. L'imprimante est jouée par le test, avec les appels du protocole (poll POST, GET du ticket,
DELETE du résultat) : aucune vraie imprimante, aucun tiers (l'essai réel se fait après le chantier, E-48).

| Test | Ce qu'il prouve |
|---|---|
| ticket | accents, cédille, « œ » et « € » intacts (markup et texte brut, UTF-8) ; le texte d'un client n'injecte jamais une balise ; paiement mixte, second numéro, retraits et notes imprimés en clair |
| pose | le jeton n'est gardé qu'en empreinte et ne se voit qu'une fois ; une autre caisse déjà reliée : 409 ; autre organisation : 404 |
| déroulé | poll -> ticket offert -> GET (la commande passe à ``recue``, événement) -> DELETE 2xx (``ticket.imprime``) -> plus rien ; un ticket n'est jamais offert deux fois une fois imprimé |
| un ticket par commande | envoyer deux fois la même commande ne fait qu'un ticket |
| erreurs | 520 : le ticket est gardé et redevient offert ; une erreur d'impression : ``erreur`` et ``ticket.erreur`` ; papier ou capot : plus de ticket offert, la liaison le dit, puis elle revient |
| cloisonnement | un jeton inconnu ou mal formé : 404 identique ; le ticket d'un autre établissement n'est jamais servi ni confirmé par ce jeton |
| commande planifiée | mode « différé » : libéré N minutes avant ; mode « immédiat » : tout de suite, « PROGRAMMÉE » ; l'heure qui approche ou « dès que possible » : tout de suite, sans marque |
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import restauration_liaison as lia
from api.db.bases_clients.horloge import horloge, remplacer
from api.services.restauration import envoi_caisse as ec
from api.services.restauration.prises import ticket as tk
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_caisse_routes import _etablissements_propres, _evenements
from api.tests.mark.test_restauration_envoi_caisse import Secours, _commande

RACINE = "/api/v1/restauration"


def _commande_type() -> dict:
    return {
        "numero": "8f0d6c64-6d62-4a42-9c0e-0c1c2c3c4c5c", "numero_court": "C12", "mode": "livraison", "statut": "envoyee",
        "heure_annoncee": datetime(2026, 11, 20, 19, 15, tzinfo=UTC), "client": {"prenom": "Zoé", "telephone": "+33612345678",
        "second_numero": {"numero": "+33698765432", "qui": "mon épouse", "pourquoi": "pour le portail"}},
        "adresse": {"voie": "12 rue de l'Église", "code_postal": "60300", "commune": "Senlis"}, "frais": 300, "total": 2750,
        "lignes": [
            {"nom": "Crème brûlée œufs", "quantite": 2, "choix": [{"nom": "Supplément fromage", "choix": [{"nom": "Chèvre"}]}], "retires": ["olives", "cœurs d'artichaut"], "note": "bien cuite [cut: feed]"},
            {"nom": "Café gourmand", "quantite": 1},
        ],
        "remises": [{"nom": "-10 % le midi", "montant": 275}],
        "paiement": {"moyens": [{"moyen": "titre_restaurant", "montant": 2000}, {"moyen": "especes", "montant": 450}], "rendu_sur": 5000},
        "note": "Sonnez deux fois\\n[magnify: width 6]",
    }


def test_le_ticket_garde_les_accents_et_n_obeit_jamais_au_texte_d_un_client():
    commande = _commande_type()
    for media in tk.MEDIAS:
        sortie = " ".join(tk.rendre(commande, media, fuseau="Europe/Paris").decode("utf-8").split())  # UTF-8 : relu sans perte (blancs et retours à la ligne mis à plat)
        for attendu in ("Crème brûlée œufs", "cœurs d'artichaut", "Zoé", "Église", "20,00 €", "Chèvre", "mon épouse", "20:15"):  # 19 h 15 UTC = 20 h 15 à Paris
            assert attendu in sortie, (media, attendu)
        assert "TR 20,00 € + ESP 4,50 € (rendre sur 50,00 €)" in sortie  # paiement mixte en clair (E-34)
        assert "2e n° : +33698765432 (mon épouse pour le portail)" in sortie and "Sans : olives, cœurs d'artichaut" in sortie and "> bien cuite" in sortie
    markup = tk.rendre(commande, tk.MEDIA_MARKUP).decode("utf-8")
    # les balises que le ticket pose lui-même : une seule coupe, la dernière ; aucune balise venue du client
    assert markup.count("[cut:") == 1 and markup.rstrip().endswith("[cut: feed; partial]")
    assert "[magnify: width 6]" not in markup and "(magnify: width 6)" in markup and "(cut: feed)" in markup
    assert "\n" not in tk.assainir("a\nb\x07c") and tk.assainir("[x]") == "(x)"
    with pytest.raises(ValueError):
        tk.rendre(commande, "application/vnd.inconnu")
    assert "PROGRAMMÉE" in tk.rendre(commande, tk.MEDIA_TEXTE, programmee=True).decode() and "PROGRAMMÉE" not in tk.rendre(commande, tk.MEDIA_TEXTE).decode()


async def _poser(client, cas, etab, **corps):
    return await client.post(f"{RACINE}/etablissements/{etab}/imprimante", json=corps, headers=_cle(cas.cle_a))


def _chemin(adresse: str) -> str:
    return adresse[adresse.index("/api/v1"):]


async def _avec_imprimante(db_session, seconde_base, **corps):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        r = await _poser(c, cas, etab, **corps)
    assert r.status_code == 200, r.text
    return cas, etab, _chemin(r.json()["adresse"])


async def test_poser_l_imprimante_ne_garde_que_l_empreinte_et_refuse_une_autre_caisse(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _etablissements_propres(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        for mauvais in ({"mode_planifiee": "jamais"}, {"minutes_avant": -1}, {"minutes_avant": 241}, {"autre": 1}):
            assert (await _poser(c, cas, etab, **mauvais)).status_code == 422
        assert (await c.post(f"{RACINE}/etablissements/{etab}/imprimante", json={})).status_code == 401
        assert (await _poser(c, cas, max(cas.sites_a + cas.sites_b) + 1000)).status_code == 404
        r = await _poser(c, cas, etab, nom="Cuisine", mode_planifiee="immediat", minutes_avant=15)
    jeton = r.json()["adresse"].rsplit("/", 1)[1]
    assert jeton.startswith(f"{cas.a}-") and len(jeton) > 40
    base = await schema.connecter(cas.base_a)
    try:
        ligne = dict(await base.fetchrow("SELECT * FROM mark.resto_imprimante WHERE site_id = $1", etab))
        assert jeton not in str(ligne) and ligne["jeton_empreinte"] == lia.empreinte(jeton) and (ligne["mode_planifiee"], ligne["minutes_avant"]) == ("immediat", 15)
        assert (await lia.liaison(base, etab))["prise"] == "imprimante"
        # un nouveau jeton remplace l'ancien : l'ancien cesse de marcher
        async with client_http() as c:
            neuf = (await _poser(c, cas, etab)).json()["adresse"].rsplit("/", 1)[1]
            assert (await c.post(f"{RACINE}/imprimante/{jeton}", json={})).status_code == 404
            assert (await c.post(f"{RACINE}/imprimante/{neuf}", json={})).status_code == 200
        # une autre caisse déjà reliée à l'établissement voisin : on ne l'écrase pas
        await lia.poser_liaison(base, cas.sites_a[1], "hubrise", "pdv-x", "ok")
    finally:
        await base.close()
    async with client_http() as c:
        assert (await _poser(c, cas, cas.sites_a[1])).status_code == 409


async def test_le_deroule_complet_interrogation_ticket_confirmation(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas, etab, chemin = await _avec_imprimante(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    c0 = await schema.connecter(cas.base_a)
    try:
        await c0.execute("UPDATE mark.resto_commande_ligne SET nom = 'Crème brûlée' WHERE numero = $1", uuid.UUID(numero))
    finally:
        await c0.close()
    secours = Secours()
    async with client_http() as c:
        # rien à imprimer
        assert (await c.post(chemin, json={"printerMAC": "00:11:62:aa:bb:cc", "statusCode": "200 OK"})).json() == {"jobReady": False}
        # la commande est envoyée : UN ticket, même envoyée deux fois
        issue = await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, secours=secours)
        assert issue.issue == "envoyee" and issue.pour_l_outil == "TRANSMISE"  # jamais « acceptée » : l'imprimante ne le dit pas
        await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, secours=secours)
        base = await schema.connecter(cas.base_a)
        try:
            assert await base.fetchval("SELECT count(*) FROM mark.resto_ticket WHERE numero = $1", uuid.UUID(numero)) == 1
        finally:
            await base.close()
        # l'imprimante interroge, vient chercher, imprime, confirme
        poll = (await c.post(chemin, json={"printerMAC": "00:11:62:aa:bb:cc", "statusCode": "200 OK"})).json()
        assert poll["jobReady"] is True and poll["jobToken"] == numero and "text/vnd.star.markup" in poll["mediaTypes"]
        ticket = await c.get(chemin, params={"type": "text/vnd.star.markup", "mac": "00:11:62:aa:bb:cc", "token": numero})
        assert ticket.status_code == 200 and ticket.headers["content-type"].startswith("text/vnd.star.markup") and "Crème brûlée" in ticket.content.decode("utf-8")
        statut = lambda: lia.etat_de_la_commande  # noqa: E731
        base = await schema.connecter(cas.base_a)
        try:
            assert (await lia.etat_de_la_commande(base, etab, numero))["statut"] == "recue"  # le ticket est entre les mains de la cuisine
        finally:
            await base.close()
        fini = await c.delete(chemin, params={"code": "200 OK", "mac": "00:11:62:aa:bb:cc", "token": numero})
        assert fini.status_code == 200 and fini.json() == {"resultat": "imprime"}
        assert (await c.delete(chemin, params={"code": "200 OK", "token": numero})).json() == {"resultat": "imprime"}  # rejoué : rien de plus
        assert (await c.post(chemin, json={"statusCode": "200 OK"})).json() == {"jobReady": False}
        assert (await c.get(chemin, params={"type": "text/plain", "token": numero})).status_code == 404  # imprimé : plus servi
    types = [(t, d.get("code") or d.get("vers")) for t, d in await _evenements(cas.a, etab)]
    assert ("commande.statut", "recue") in types and types.count(("ticket.imprime", "200")) == 1


async def test_un_telechargement_manque_est_garde_une_erreur_d_impression_alerte_et_papier_ou_capot_coupent_l_offre(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas, etab, chemin = await _avec_imprimante(db_session, seconde_base)
    numero = await _commande(cas.base_a, etab)
    await ec.envoyer_la_commande(cas.a, cas.base_a, etab, numero, secours=Secours())
    async with client_http() as c:
        await c.get(chemin, params={"type": "text/plain", "token": numero})
        assert (await c.delete(chemin, params={"code": "520 Download Timeout", "token": numero})).json() == {"resultat": "a_reprendre"}
        assert (await c.post(chemin, json={"statusCode": "200 OK"})).json()["jobToken"] == numero  # gardé : de nouveau offert
        # le papier manque : plus de ticket offert, la liaison le dit par un code
        assert (await c.post(chemin, json={"statusCode": "211 Printer Paper Empty"})).json() == {"jobReady": False}
        assert (await c.post(chemin, json={"statusCode": "212 Printer Cover Open"})).json() == {"jobReady": False}
        base = await schema.connecter(cas.base_a)
        try:
            liaison = await lia.liaison(base, etab)
            assert (liaison["etat"], liaison["derniere_erreur"]) == ("erreur", "capot")
        finally:
            await base.close()
        assert (await c.post(chemin, json={"statusCode": "200 OK"})).json()["jobReady"] is True
        base = await schema.connecter(cas.base_a)
        try:
            assert (await lia.liaison(base, etab))["etat"] == "ok"
        finally:
            await base.close()
        # une erreur d'impression : le ticket passe en erreur, l'événement part
        await c.get(chemin, params={"type": "text/plain", "token": numero})
        assert (await c.delete(chemin, params={"code": "410 Paper Jam", "token": numero})).json() == {"resultat": "erreur"}
    base = await schema.connecter(cas.base_a)
    try:
        t = await lia.le_ticket(base, etab, numero)
        assert t["statut"] == "erreur"
    finally:
        await base.close()
    evenements = await _evenements(cas.a, etab)
    assert ("ticket.erreur", {"numero": numero, "code": "410"}) in evenements
    assert ("caisse.liaison", {"etat": "erreur"}) in evenements


async def test_un_jeton_inconnu_est_un_404_et_un_ticket_d_un_autre_etablissement_n_est_jamais_servi(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas, etab, chemin = await _avec_imprimante(db_session, seconde_base)
    voisin = cas.sites_a[1]
    numero_du_voisin = await _commande(cas.base_a, voisin)
    c0 = await schema.connecter(cas.base_a)
    try:
        await lia.creer_le_ticket(c0, voisin, numero_du_voisin)
    finally:
        await c0.close()
    async with client_http() as c:
        for faux in (f"{cas.a}-" + "a" * 43, f"{cas.b}-" + "b" * 43, "n-importe-quoi", "9999999-" + "c" * 43, f"{cas.a}-court"):
            for appel in (c.post(f"{RACINE}/imprimante/{faux}", json={}), c.get(f"{RACINE}/imprimante/{faux}", params={"type": "text/plain", "token": numero_du_voisin}),
                          c.delete(f"{RACINE}/imprimante/{faux}", params={"code": "200", "token": numero_du_voisin})):
                assert (await appel).status_code == 404
        # le bon jeton de l'établissement A, le numéro d'un ticket de l'établissement voisin : ni servi, ni confirmé
        assert (await c.get(chemin, params={"type": "text/plain", "token": numero_du_voisin})).status_code == 404
        assert (await c.delete(chemin, params={"code": "200", "token": numero_du_voisin})).json() == {"resultat": "inconnu"}
        assert (await c.post(chemin, json={"statusCode": "200 OK"})).json() == {"jobReady": False}  # et le ticket du voisin n'est pas offert à cette imprimante
    base = await schema.connecter(cas.base_a)
    try:
        assert (await lia.le_ticket(base, voisin, numero_du_voisin))["statut"] == "en_file"
    finally:
        await base.close()


async def _ticket_de(base: str, etab: int, heure_voulue: datetime | None, **options):
    numero = await _commande(base, etab)
    c = await schema.connecter(base)
    try:
        await c.execute("UPDATE mark.resto_commande SET heure_voulue = $2 WHERE numero = $1", uuid.UUID(numero), heure_voulue)
    finally:
        await c.close()
    await ec.envoyer_la_commande(options["org"], base, etab, numero, secours=Secours())
    c = await schema.connecter(base)
    try:
        return dict(await c.fetchrow("SELECT liberer_le, programmee, statut FROM mark.resto_ticket WHERE numero = $1", uuid.UUID(numero))), numero
    finally:
        await c.close()


async def test_la_commande_planifiee_se_libere_avant_l_heure_ou_s_imprime_tout_de_suite_marquee(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas, etab, chemin = await _avec_imprimante(db_session, seconde_base, mode_planifiee="differe", minutes_avant=20)
    maintenant = horloge(cas.base_a).maintenant()
    demain_19h = maintenant + timedelta(hours=26)
    # différé : libéré 20 minutes avant l'heure, pas offert à l'imprimante avant
    ligne, numero = await _ticket_de(cas.base_a, etab, demain_19h, org=cas.a)
    assert ligne["liberer_le"] == demain_19h - timedelta(minutes=20) and ligne["programmee"] is False
    async with client_http() as c:
        assert (await c.post(chemin, json={"statusCode": "200 OK"})).json() == {"jobReady": False}
        with remplacer(cas.base_a, demain_19h - timedelta(minutes=19)):
            assert (await c.post(chemin, json={"statusCode": "200 OK"})).json()["jobToken"] == numero
        # l'heure qui approche, ou « dès que possible » : tout de suite, sans marque
        proche, _ = await _ticket_de(cas.base_a, etab, maintenant + timedelta(minutes=10), org=cas.a)
        assert proche["liberer_le"] is None and proche["programmee"] is False
        asap, _ = await _ticket_de(cas.base_a, etab, None, org=cas.a)
        assert asap["liberer_le"] is None and asap["programmee"] is False
        # immédiat : imprimé tout de suite, marqué « PROGRAMMÉE »
        base = await schema.connecter(cas.base_a)
        try:
            await base.execute("UPDATE mark.resto_imprimante SET mode_planifiee = 'immediat' WHERE site_id = $1", etab)
        finally:
            await base.close()
        immediat, numero_i = await _ticket_de(cas.base_a, etab, demain_19h, org=cas.a)
        assert immediat["liberer_le"] is None and immediat["programmee"] is True
        ticket = await c.get(chemin, params={"type": "text/plain", "token": numero_i})
        assert "PROGRAMMÉE" in ticket.content.decode("utf-8")
