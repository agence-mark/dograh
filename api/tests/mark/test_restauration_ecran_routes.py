"""[.mark] Module Restauration, lot 12 : les routes des écrans du fork (module, carte, livraison, réglages, historique).

Vraie authentification (session d'un compte de l'équipe, clé d'API), vraies bases de clients, vrai Redis. Aucun appel à un tiers.

| Test | Ce qu'il prouve |
|---|---|
| module | allumer écrit une ligne par établissement, retirer n'efface RIEN (la carte reste) et le remettre la retrouve ; une clé lit, n'écrit pas |
| carte | rendue avec la portée de chaque objet ; étoile et synonymes (actifs tout de suite) ; relecture des propositions ; import d'un fichier idempotent, invalide refusé sans rien écrire |
| carte lue par la caisse | quand la prise lit la carte, la liaison est ``ok``, la carte est en lecture seule (étoile et synonymes restent possibles) |
| livraison | communes trouvées avec distance et zone ; zones écrites (créées, mises à jour, retirées) ; commune refusée ; plus de cinq zones refusé |
| réglages | types, paiement, envoi : écrits, relus, journalisés ; seuils sans caisse refusés ; valeurs hors bornes refusées |
| historique | les écritures de l'écran y figurent avec leur auteur et leur source, paginées |
| cloisonnement | l'établissement d'une autre organisation : 404 partout, rien n'est écrit chez elle |
| permissions | chaque route est au registre ; lire = voir les conversations ; écrire = ``agents.modifier`` (jamais par clé) |
"""

from __future__ import annotations

import copy
import uuid

import pytest

from api.db.bases_clients import connexion as schema
from api.services.equipe_mark import registre_routes as registre
from api.tests.mark.equipe_commun import client_http, creer_compte, entetes, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE
from api.tests.mark.test_restauration_flux import _deux_organisations_avec_des_etablissements

RACINE = "/api/v1/restauration"
BEAUVAIS = "60057"
# Un nom entre parenthèses : le moteur en propose le nom court comme synonyme « à relire » (la carte de référence n'en donne aucun).
CARTE_A_PROPOSER = copy.deepcopy(CARTE)
CARTE_A_PROPOSER["produits"][0]["nom"] = "Margarita Maison (grande)"


async def _cas(db_session, seconde_base):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    _, jeton = await creer_compte(db_session, f"ecran-{uuid.uuid4().hex[:8]}@example.com", role="Administrateur", organisations=[cas.a])
    cas.session = entetes(jeton)
    c = await schema.connecter(cas.base_a)
    try:
        await c.execute("UPDATE mark.site SET adresse_insee = $2 WHERE id = $1", cas.sites_a[0], BEAUVAIS)
    finally:
        await c.close()
    return cas


async def _donnees(base: str, requete: str, *args):
    c = await schema.connecter(base)
    try:
        return await c.fetch(requete, *args)
    finally:
        await c.close()


async def _importer(c, cas, carte=None):
    return await c.post(f"{RACINE}/etablissements/{cas.sites_a[0]}/carte/import", json={"source": "fichier", "carte": carte or CARTE}, headers=cas.session)


# --------------------------------------------------------------------------- le module


async def test_le_module_s_allume_se_retire_sans_rien_effacer_et_se_remet(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    async with client_http() as c:
        assert (await c.get(f"{RACINE}/module")).status_code == 401
        lu = await c.get(f"{RACINE}/module", headers=_cle(cas.cle_a))
        assert lu.status_code == 200 and lu.json()["actif"] is False and [e["nom"] for e in lu.json()["etablissements"]] == ["deux", "un"]
        # une clé d'API lit, elle n'écrit pas
        assert (await c.put(f"{RACINE}/module", json={"actif": True}, headers=_cle(cas.cle_a))).status_code == 403
        assert (await c.put(f"{RACINE}/module", json={"actif": True, "en_trop": 1}, headers=cas.session)).status_code == 422
        allume = await c.put(f"{RACINE}/module", json={"actif": True}, headers=cas.session)
        assert allume.status_code == 200 and allume.json()["actif"] is True
        assert (await _importer(c, cas)).status_code == 200
        retire = await c.put(f"{RACINE}/module", json={"actif": False}, headers=cas.session)
        assert retire.json()["actif"] is False
        # rien n'est effacé : la carte est toujours là
        assert (await c.get(f"{RACINE}/etablissements/{cas.sites_a[0]}/carte", headers=cas.session)).json()["produits"]
        assert (await c.put(f"{RACINE}/module", json={"actif": True}, headers=cas.session)).json()["actif"] is True
    lignes = await _donnees(cas.base_a, "SELECT site_id, module_actif FROM mark.resto_reglage ORDER BY site_id")
    assert [(r["site_id"], r["module_actif"]) for r in lignes] == [(s, True) for s in sorted(cas.sites_a)]
    # l'autre organisation n'a rien vu
    assert await _donnees(cas.base_b, "SELECT 1 FROM mark.resto_reglage") == []


# --------------------------------------------------------------------------- la carte


async def test_la_carte_se_rend_avec_ses_portees_et_les_surcouches_de_l_ecran(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        assert (await _importer(c, cas)).status_code == 200
        r = await c.get(f"{RACINE}/etablissements/{etab}/carte", headers=_cle(cas.cle_a))
        assert r.status_code == 200
        carte = r.json()
        assert carte["produits"] and carte["lecture_seule"] is False and carte["prise"] == "portail"
        assert {p["portee"] for p in carte["produits"]} == {"etablissement"}
        ref = carte["produits"][0]["id"]
        # une clé lit la carte ; elle ne pose ni étoile ni synonyme
        assert (await c.put(f"{RACINE}/etablissements/{etab}/carte/etoile", json={"ref": ref, "etoile": True}, headers=_cle(cas.cle_a))).status_code == 403
        assert (await c.put(f"{RACINE}/etablissements/{etab}/carte/etoile", json={"ref": ref, "etoile": True}, headers=cas.session)).json() == {"ok": True}
        assert (await c.put(f"{RACINE}/etablissements/{etab}/carte/etoile", json={"ref": "inconnu", "etoile": True}, headers=cas.session)).status_code == 404
        mots = {"ref": ref, "synonymes": ["  la  reine ", "LA REINE", "royale"]}
        assert (await c.put(f"{RACINE}/etablissements/{etab}/carte/synonymes", json=mots, headers=cas.session)).status_code == 200
        assert (await c.put(f"{RACINE}/etablissements/{etab}/carte/synonymes", json={**mots, "synonymes": ["x"] * 11}, headers=cas.session)).status_code == 422
        produit = next(p for p in (await c.get(f"{RACINE}/etablissements/{etab}/carte", headers=cas.session)).json()["produits"] if p["id"] == ref)
        assert produit["etoile"] is True and produit["synonymes"] == ["la reine", "royale"] and produit["synonymes_a_relire"] == []


async def test_l_import_d_un_fichier_propose_des_synonymes_a_relire_ne_s_ecrase_pas_et_refuse_l_invalide(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        premier = (await _importer(c, cas, CARTE_A_PROPOSER)).json()
        assert premier["ajoutes"] > 0 and premier["synonymes_proposes"] == 1
        rejoue = (await _importer(c, cas, CARTE_A_PROPOSER)).json()
        assert rejoue["ajoutes"] == 0 and rejoue["changes"] == 0 and rejoue["synonymes_proposes"] == 0  # idempotent, rien de proposé deux fois
        carte = (await c.get(f"{RACINE}/etablissements/{etab}/carte", headers=cas.session)).json()
        a_relire = next(p for p in carte["produits"] if p["synonymes_a_relire"])
        ok = await c.post(f"{RACINE}/etablissements/{etab}/carte/synonymes/relus", json={"ref": a_relire["id"]}, headers=cas.session)
        assert ok.status_code == 200
        relu = next(p for p in (await c.get(f"{RACINE}/etablissements/{etab}/carte", headers=cas.session)).json()["produits"] if p["id"] == a_relire["id"])
        assert relu["synonymes"] == a_relire["synonymes_a_relire"] and relu["synonymes_a_relire"] == []
        assert (await c.post(f"{RACINE}/etablissements/{etab}/carte/synonymes/relus", json={"ref": a_relire["id"]}, headers=cas.session)).status_code == 404  # plus rien à relire
        # un fichier hors format n'écrit rien
        avant = len((await c.get(f"{RACINE}/etablissements/{etab}/carte", headers=cas.session)).json()["produits"])
        invalide = copy.deepcopy(CARTE)
        invalide["produits"] = [{"id": "x"}]
        r = await _importer(c, cas, invalide)
        assert r.status_code == 422
        assert len((await c.get(f"{RACINE}/etablissements/{etab}/carte", headers=cas.session)).json()["produits"]) == avant
        assert (await c.post(f"{RACINE}/etablissements/{etab}/carte/import", json={"source": "fichier"}, headers=cas.session)).status_code == 422  # sans fichier
        assert (await c.post(f"{RACINE}/etablissements/{etab}/carte/import", json={"source": "caisse"}, headers=cas.session)).status_code == 409  # aucune caisse


async def test_quand_la_caisse_lit_la_carte_elle_est_en_lecture_seule(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    c_base = await schema.connecter(cas.base_a)
    try:
        await c_base.execute("INSERT INTO mark.resto_liaison (site_id, prise, etat) VALUES ($1, 'hubrise', 'ok')", etab)
    finally:
        await c_base.close()
    async with client_http() as c:
        carte = (await c.get(f"{RACINE}/etablissements/{etab}/carte", headers=cas.session)).json()
        assert carte["lecture_seule"] is True and carte["prise"] == "hubrise"
        reglages = (await c.get(f"{RACINE}/etablissements/{etab}/reglages", headers=cas.session)).json()
        sources = {s["objet"]: s["mode"] for s in reglages["sources"]}
        assert sources["carte"] == "caisse"


# --------------------------------------------------------------------------- la livraison


def _zone(nom, forme, km, **plus):
    return {"nom": nom, "forme": forme, "cercle_km": km, "frais": 300, "minimum": 1500, "delai": 30, **plus}


async def test_la_livraison_rend_les_communes_trouvees_et_ecrit_les_zones(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    url = f"{RACINE}/etablissements/{etab}/livraison"
    async with client_http() as c:
        vide = (await c.get(url, params={"rayon_km": 15}, headers=_cle(cas.cle_a))).json()
        assert vide["centre_connu"] is True and vide["commune"] == "Beauvais" and vide["zones"] == []
        proches = vide["communes"]
        assert proches and proches[0]["nom"] == "Beauvais" and all(a["km"] <= b["km"] for a, b in zip(proches, proches[1:], strict=False))
        assert all(x["zone_id"] is None for x in proches)
        # deux cercles ; l'écriture rend l'état d'après
        zones = {"zones": [_zone("Zone 1", "rayon", 5), _zone("Zone 2", "rayon", 10, frais=500, gratuite_des=3000)]}
        ecrit = await c.put(f"{url}/zones", json=zones, headers=cas.session)
        assert ecrit.status_code == 200, ecrit.text
        rendu = ecrit.json()["zones"]
        assert [(z["nom"], z["rayon_km"], z["cercle_km"], z["frais"], z["gratuite_des"]) for z in rendu] == [("Zone 1", 5.0, 5.0, 300, None), ("Zone 2", 10.0, 10.0, 500, 3000)]
        lues = (await c.get(url, params={"rayon_km": 15}, headers=cas.session)).json()["communes"]
        assert next(x for x in lues if x["nom"] == "Beauvais")["zone_id"] == rendu[0]["id"]
        assert any(x["zone_id"] == rendu[1]["id"] for x in lues) and any(x["zone_id"] is None for x in lues)
        # mise à jour par identifiant, retrait de l'absente, zone par communes avec une commune refusée
        beauvais = next(x for x in lues if x["nom"] == "Beauvais")
        deuxieme = {"zones": [{**_zone("Centre", "communes", 6, communes=[beauvais["insee"], proches[1]["insee"]], exclues=[proches[1]["insee"]]), "id": rendu[0]["id"]}]}
        maj = (await c.put(f"{url}/zones", json=deuxieme, headers=cas.session)).json()
        assert [z["id"] for z in maj["zones"]] == [rendu[0]["id"]] and maj["zones"][0]["forme"] == "communes" and maj["zones"][0]["rayon_km"] is None
        apres = (await c.get(url, params={"rayon_km": 15}, headers=cas.session)).json()["communes"]
        assert next(x for x in apres if x["insee"] == proches[1]["insee"])["refusee"] is True
        assert next(x for x in apres if x["insee"] == beauvais["insee"])["refusee"] is False
        # limites : cinq zones au plus, un cercle obligatoire, une zone d'une autre organisation inconnue
        six = {"zones": [_zone(f"Z{i}", "rayon", i + 1) for i in range(6)]}
        assert (await c.put(f"{url}/zones", json=six, headers=cas.session)).status_code == 422
        assert (await c.put(f"{url}/zones", json={"zones": [{"nom": "Z", "forme": "rayon"}]}, headers=cas.session)).status_code == 422
        assert (await c.put(f"{url}/zones", json={"zones": [{**_zone("Z", "rayon", 3), "id": 999999}]}, headers=cas.session)).status_code == 404
        assert (await c.put(f"{url}/zones", json=zones, headers=_cle(cas.cle_a))).status_code == 403
        assert (await c.get(url, params={"rayon_km": 0}, headers=cas.session)).status_code == 422
        assert (await c.get(url, params={"rayon_km": 51}, headers=cas.session)).status_code == 422
    # la zone d'une adresse suit toujours la règle du comptoir : une commune refusée n'est jamais livrée
    from api.db.bases_clients.restauration_zone import zones_de_l_etablissement

    c_base = await schema.connecter(cas.base_a)
    try:
        assert [z["nom"] for z in await zones_de_l_etablissement(c_base, etab)] == ["Centre"]
    finally:
        await c_base.close()


# --------------------------------------------------------------------------- les réglages et l'historique


async def test_les_reglages_s_ecrivent_se_relisent_et_se_journalisent(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    url = f"{RACINE}/etablissements/{etab}/reglages"
    async with client_http() as c:
        base = (await c.get(url, headers=_cle(cas.cle_a))).json()
        assert [t["type"] for t in base["types"]] == ["emporter", "livraison", "sur_place", "reservation"]
        assert base["types"][0]["ouvert"] is True and base["types"][0]["planifiee_permise"] is False and base["seuils"] is None
        assert base["reglage"]["moyens_paiement"] == ["carte", "especes"] and base["envoi_heure_changee"] == {"texte": None, "actif": False}
        assert all(s["mode"] == "ici" for s in base["sources"]) and base["caisse_porte_l_etat"] is False
        corps = {
            "types": [{"type": "emporter", "ouvert": False, "fin_par_jour": {"1": "22:00"}, "planifiee_permise": True, "delai_minimal": 30, "annonce": "heure_fixe"}],
            "reglage": {"prefixe_numero_court": "CB", "moyens_paiement": ["carte", "titre_restaurant"], "plafond_titre_restaurant": 2500},
            "envoi_heure_changee": {"texte": "Votre commande est décalée à {heure}.", "actif": True},
        }
        assert (await c.put(url, json=corps, headers=_cle(cas.cle_a))).status_code == 403
        rendu = await c.put(url, json=corps, headers=cas.session)
        assert rendu.status_code == 200
        lu = (await c.get(url, headers=cas.session)).json()
        emporter = lu["types"][0]
        assert (emporter["ouvert"], emporter["fin_par_jour"], emporter["planifiee_permise"], emporter["delai_minimal"], emporter["annonce"]) == (False, {"1": "22:00"}, True, 30, "heure_fixe")
        assert lu["types"][1]["ouvert"] is True  # les autres types ne bougent pas
        assert lu["reglage"] == {"prefixe_numero_court": "CB", "moyens_paiement": ["carte", "titre_restaurant"], "plafond_titre_restaurant": 2500, "conservation_client_mois": 12}
        assert lu["envoi_heure_changee"] == {"texte": "Votre commande est décalée à {heure}.", "actif": True}
        # un champ seul ne touche pas les autres
        await c.put(url, json={"envoi_heure_changee": {"actif": False}}, headers=cas.session)
        assert (await c.get(url, headers=cas.session)).json()["envoi_heure_changee"] == {"texte": "Votre commande est décalée à {heure}.", "actif": False}
        # bornes et listes fermées
        for mauvais in (
            {"types": [{"type": "traiteur", "ouvert": True}]}, {"types": [{"type": "emporter", "delai_minimal": -1}]}, {"reglage": {"prefixe_numero_court": "abcdef"}},
            {"reglage": {"moyens_paiement": ["bitcoin"]}}, {"reglage": {"conservation_client_mois": 40}}, {"envoi_heure_changee": {"texte": ""}}, {"inconnu": 1},
        ):
            assert (await c.put(url, json=mauvais, headers=cas.session)).status_code == 422, mauvais
        # pas de caisse, pas de seuils ni d'imprimante
        assert (await c.put(url, json={"seuils": {"alerte_sans_reponse_min": 4}}, headers=cas.session)).status_code == 409
        assert (await c.put(url, json={"imprimante": {"minutes_avant": 10}}, headers=cas.session)).status_code == 409


async def test_les_seuils_de_la_liaison_se_reglent_quand_une_caisse_est_reliee(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    c_base = await schema.connecter(cas.base_a)
    try:
        await c_base.execute("INSERT INTO mark.resto_liaison (site_id, prise, etat) VALUES ($1, 'hubrise', 'ok')", etab)
    finally:
        await c_base.close()
    url = f"{RACINE}/etablissements/{etab}/reglages"
    async with client_http() as c:
        assert (await c.get(url, headers=cas.session)).json()["seuils"] == {"alerte_sans_reponse_min": 3, "releve_messages_min": 5}
        r = await c.put(url, json={"seuils": {"alerte_sans_reponse_min": 7}}, headers=cas.session)
        assert r.status_code == 200 and r.json()["seuils"] == {"alerte_sans_reponse_min": 7, "releve_messages_min": 5}
        assert (await c.put(url, json={"seuils": {"alerte_sans_reponse_min": 0}}, headers=cas.session)).status_code == 422
        assert (await c.put(url, json={"seuils": {"releve_messages_min": 121}}, headers=cas.session)).status_code == 422


async def test_l_historique_garde_les_ecritures_de_l_ecran_avec_leur_auteur_et_se_pagine(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        for i in range(4):
            await c.put(f"{RACINE}/etablissements/{etab}/reglages", json={"reglage": {"plafond_titre_restaurant": 1000 + i}}, headers=cas.session)
        await c.put(f"{RACINE}/etablissements/{etab}/livraison/zones", json={"zones": [_zone("Z", "rayon", 4)]}, headers=cas.session)
        page = (await c.get(f"{RACINE}/etablissements/{etab}/historique", params={"limite": 3}, headers=_cle(cas.cle_a))).json()
        assert len(page["lignes"]) == 3 and page["suite"] == page["lignes"][-1]["id"]
        assert page["lignes"][0]["objet"] == "resto_zone" and page["lignes"][0]["objet_dit"] == "Livraison · zone" and page["lignes"][0]["operation"] == "insert"
        assert page["lignes"][1]["objet"] == "resto_reglage" and page["lignes"][1]["avant"] and "plafond_titre_restaurant 1002" in page["lignes"][1]["avant"]
        assert page["lignes"][0]["source"] == "mark" and page["lignes"][0]["auteur"]
        suite = (await c.get(f"{RACINE}/etablissements/{etab}/historique", params={"limite": 3, "avant": page["suite"]}, headers=cas.session)).json()
        assert suite["lignes"] and suite["lignes"][0]["id"] < page["suite"]
        assert (await c.get(f"{RACINE}/etablissements/{etab}/historique", params={"limite": 101}, headers=cas.session)).status_code == 422
        # le journal d'un établissement ne montre jamais celui d'un autre
        autre = (await c.get(f"{RACINE}/etablissements/{cas.sites_a[1]}/historique", headers=cas.session)).json()
        assert autre["lignes"] == []


# --------------------------------------------------------------------------- cloisonnement et permissions


async def test_l_etablissement_d_une_autre_organisation_est_un_404_partout_et_rien_n_y_est_ecrit(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    c_b = await schema.connecter(cas.base_b)
    try:  # un établissement qui n'existe que chez B (les identifiants des deux bases se recouvrent sinon)
        chez_b = await c_b.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, 'trois', 'trois', 'Europe/Paris' FROM mark.entreprise LIMIT 1 RETURNING id")
    finally:
        await c_b.close()
    assert chez_b not in cas.sites_a
    inconnu = max(cas.sites_a + cas.sites_b) + 1000
    appels = [
        ("GET", "carte", None), ("GET", "livraison", None), ("GET", "reglages", None), ("GET", "historique", None),
        ("PUT", "carte/etoile", {"ref": "x", "etoile": True}), ("PUT", "carte/synonymes", {"ref": "x", "synonymes": []}), ("POST", "carte/synonymes/relus", {"ref": "x"}),
        ("POST", "carte/import", {"source": "fichier", "carte": CARTE}), ("PUT", "livraison/zones", {"zones": [_zone("Z", "rayon", 3)]}),
        ("PUT", "reglages", {"reglage": {"plafond_titre_restaurant": 1}}),
    ]
    async with client_http() as c:
        for cible in (chez_b, inconnu):
            for methode, suffixe, corps in appels:
                r = await c.request(methode, f"{RACINE}/etablissements/{cible}/{suffixe}", json=corps, headers=cas.session)
                assert r.status_code == 404, (cible, methode, suffixe)
                assert str(cible) not in r.text
    for table in ("resto_zone", "resto_produit", "resto_reglage", "resto_surcouche"):
        assert await _donnees(cas.base_b, f"SELECT 1 FROM mark.{table}") == [] and await _donnees(cas.base_a, f"SELECT 1 FROM mark.{table}") == [], table


def test_chaque_route_de_l_ecran_est_au_registre_avec_la_bonne_permission():
    lecture = {"/restauration/module", *(f"/restauration/etablissements/{{etablissement_id}}/{p}" for p in ("carte", "livraison", "reglages", "historique"))}
    ecriture = {
        "/restauration/module", *(f"/restauration/etablissements/{{etablissement_id}}/{p}" for p in ("carte/etoile", "carte/synonymes", "carte/synonymes/relus", "carte/import", "livraison/zones", "reglages")),
    }
    for chemin in lecture:
        decision, _ = registre.decision_de("GET", chemin)
        assert decision.cle == "conversations.voir" and decision.pour_cle is None, chemin
    for chemin in ecriture:
        for methode in ("PUT", "POST"):
            trouvee = registre.decision_de(methode, chemin)
            if trouvee is None:
                continue
            assert trouvee[0].cle == "agents.modifier" and trouvee[0].pour_cle is None, (methode, chemin)
