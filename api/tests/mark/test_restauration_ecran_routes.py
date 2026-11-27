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
| produit | ingrédients et allergènes : en surcouche quand la caisse ou un fichier porte le produit (un réimport ne l'écrase pas), en direct sinon ; inconnu et aucun distincts |
| sources et pause | interrupteur de source par objet et pause du téléphone écrits, relus, journalisés ; la carte tenue ici n'est plus en lecture seule |
| fermetures | une fermeture exceptionnelle s'écrit, se remplace, se retire ; l'agent la dit (``etat_combine``) |
| permissions | chaque route est au registre ; lire = voir les conversations ; écrire = ``agents.modifier`` (jamais par clé) |
"""

from __future__ import annotations

import copy
import uuid
from datetime import timedelta

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.services.equipe_mark import registre_routes as registre
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    entetes,
    sans_preparation_des_organisations,
)
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import CARTE
from api.tests.mark.test_restauration_flux import (
    _deux_organisations_avec_des_etablissements,
)

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



async def test_le_module_dit_la_cle_de_la_fiche_de_chaque_etablissement(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    """SA-29 (M59) : la fiche (Entreprise › Établissements) a une clé, le classeur un numéro ; l'écran les relie par ``cle``.
    Sans elle, la section « Caisse de cet établissement » de la fiche ne s'affichait jamais."""
    cas = await _cas(db_session, seconde_base)
    attendu = {r["id"]: r["cle"] for r in await _donnees(cas.base_a, "SELECT id, cle FROM mark.site")}
    async with client_http() as c:
        lu = (await c.get(f"{RACINE}/module", headers=cas.session)).json()
    assert {e["id"]: e["cle"] for e in lu["etablissements"]} == attendu and len(attendu) == len(cas.sites_a)


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
            "reglage": {
                "prefixe_numero_court": "CB", "moyens_paiement": ["carte", "titre_restaurant"], "plafond_titre_restaurant": 2500,
                "numero_mode": "moyen", "prefixe_mixte": "XX", "notes_libres": False, "titre_sans_rendu": False,
            },
            "envoi_heure_changee": {"texte": "Votre commande est décalée à {heure}.", "actif": True},
        }
        assert (await c.put(url, json=corps, headers=_cle(cas.cle_a))).status_code == 403
        rendu = await c.put(url, json=corps, headers=cas.session)
        assert rendu.status_code == 200
        lu = (await c.get(url, headers=cas.session)).json()
        emporter = lu["types"][0]
        assert (emporter["ouvert"], emporter["fin_par_jour"], emporter["planifiee_permise"], emporter["delai_minimal"], emporter["annonce"]) == (False, {"1": "22:00"}, True, 30, "heure_fixe")
        assert lu["types"][1]["ouvert"] is True  # les autres types ne bougent pas
        assert lu["reglage"] == {
            "prefixe_numero_court": "CB", "moyens_paiement": ["carte", "titre_restaurant"], "plafond_titre_restaurant": 2500, "conservation_client_mois": 12,
            "numero_mode": "moyen", "prefixe_mixte": "XX", "notes_libres": False, "titre_alcool_exclu": True, "titre_sans_rendu": False, "pause_caisse_pause_telephone": True,
            "filet_retenue_min": 2,  # lot 8b-1b : le délai du filet, réglage visible (refus 18 ; audit 8b-1a, remarque 3)
        }
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
        assert (await c.get(url, headers=cas.session)).json()["seuils"] == {"alerte_sans_reponse_min": 5, "releve_messages_min": 5}  # lot 16 : cinq minutes par défaut (note de Pierre, Evan 20/11)
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
        ("PUT", "carte/etoile", {"ref": "x", "etoile": True}), ("PUT", "carte/produit", {"ref": "x", "allergenes": []}), ("PUT", "carte/synonymes", {"ref": "x", "synonymes": []}), ("POST", "carte/synonymes/relus", {"ref": "x"}),
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
        "/restauration/module", *(f"/restauration/etablissements/{{etablissement_id}}/{p}" for p in ("carte/etoile", "carte/produit", "carte/synonymes", "carte/synonymes/relus", "carte/import", "livraison/zones", "reglages")),
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


# --------------------------------------------------------------------------- les soirs toujours chargés (temps récurrents)


def _soir(**plus):
    return {"type": "emporter", "jours": [2], "debut": "19:00", "fin": "22:00", "minutes_ajoutees": 10, **plus}


async def test_les_soirs_charges_s_ecrivent_se_remplacent_et_refusent_l_invalide(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    url = f"{RACINE}/etablissements/{etab}/reglages"
    async with client_http() as c:
        assert (await c.get(url, headers=cas.session)).json()["recurrents"] == []
        r = await c.put(url, json={"recurrents": [_soir(), _soir(type="livraison", jours=[5, 6], minutes_ajoutees=15)]}, headers=cas.session)
        assert r.status_code == 200, r.text
        lus = r.json()["recurrents"]
        assert [(x["type"], x["jours"], x["debut"], x["fin"], x["minutes_ajoutees"]) for x in lus] == [("emporter", [2], "19:00", "22:00", 10), ("livraison", [5, 6], "19:00", "22:00", 15)]
        # remplacement : une ligne gardée par son id, l'autre retirée, une neuve
        garde = {**lus[0], "minutes_ajoutees": 20}
        r = await c.put(url, json={"recurrents": [garde, _soir(jours=[1, 3], debut="12:00", fin="13:30")]}, headers=cas.session)
        assert [(x["minutes_ajoutees"], x["jours"]) for x in r.json()["recurrents"]] == [(10, [1, 3]), (20, [2])] and r.json()["recurrents"][1]["id"] == lus[0]["id"]
        # absent : intact ; vide : tout retiré
        assert len((await c.put(url, json={"reglage": {"notes_libres": True}}, headers=cas.session)).json()["recurrents"]) == 2
        assert (await c.put(url, json={"recurrents": []}, headers=cas.session)).json()["recurrents"] == []
        for mauvais in (
            [_soir(minutes_ajoutees=0)], [_soir(minutes_ajoutees=241)], [_soir(jours=[])], [_soir(jours=[8])], [_soir(type="reservation")],
            [_soir(debut="22:00", fin="19:00")], [_soir(debut="19:00", fin="19:00")], [_soir(debut="7h")], [{**_soir(), "en_trop": 1}],
        ):
            assert (await c.put(url, json={"recurrents": mauvais}, headers=cas.session)).status_code == 422, mauvais
        assert (await c.put(url, json={"recurrents": [{**_soir(), "id": 999999}]}, headers=cas.session)).status_code == 404
        assert (await c.put(url, json={"recurrents": [_soir()]}, headers=_cle(cas.cle_a))).status_code == 403
    # une ligne d'un autre établissement ne se prend pas par son identifiant
    async with client_http() as c:
        await c.put(url, json={"recurrents": [_soir()]}, headers=cas.session)
        autre = (await c.put(f"{RACINE}/etablissements/{cas.sites_a[1]}/reglages", json={"recurrents": [_soir(minutes_ajoutees=30)]}, headers=cas.session)).json()["recurrents"][0]
        vole = (await c.get(url, headers=cas.session)).json()["recurrents"][0]["id"]
        assert autre["id"] != vole
        assert (await c.put(f"{RACINE}/etablissements/{cas.sites_a[1]}/reglages", json={"recurrents": [{**_soir(), "id": vole}]}, headers=cas.session)).status_code == 404


async def test_un_soir_charge_ajoute_ses_minutes_a_l_annonce_et_seulement_dans_sa_plage(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    from datetime import UTC, datetime

    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    corps = {"recurrents": [_soir(minutes_ajoutees=10), _soir(debut="20:00", fin="21:00", minutes_ajoutees=25), _soir(type="livraison", minutes_ajoutees=15)]}

    async def annonce(c, heure_locale: datetime, type_="emporter"):
        r = await c.get(f"{RACINE}/etablissements/{etab}/temps", headers=cas.session)
        ligne = next(t for t in r.json()["types"] if t["type"] == type_)
        return ligne["ajout_actif"], (ligne["annonce"] or {}).get("minutes"), ligne["par_zone"]

    # novembre : Paris est à UTC+1 ; le mardi 17 novembre 2026 à 19 h 30 locales = 18 h 30 UTC
    def paris(jour, h, m):
        return datetime(2026, 11, jour, h - 1, m, tzinfo=UTC)

    async with client_http() as c:
        assert (await c.put(f"{RACINE}/etablissements/{etab}/reglages", json=corps, headers=cas.session)).status_code == 200
        with horloge.remplacer(cas.base_a, paris(17, 19, 30)):
            assert (await annonce(c, None))[:2] == (10, 10)  # un mardi soir chargé annonce +10
        with horloge.remplacer(cas.base_a, paris(17, 20, 30)):
            assert (await annonce(c, None))[:2] == (25, 25)  # deux plages qui se recouvrent : la plus grande, jamais la somme
        with horloge.remplacer(cas.base_a, paris(17, 22, 0)):
            assert (await annonce(c, None))[:2] == (0, 0)  # la fin de la plage est exclue
        with horloge.remplacer(cas.base_a, paris(17, 18, 59)):
            assert (await annonce(c, None))[:2] == (0, 0)  # avant la plage
        with horloge.remplacer(cas.base_a, paris(18, 20, 0)):
            assert (await annonce(c, None))[:2] == (0, 0)  # un mercredi
        with horloge.remplacer(cas.base_a, paris(17, 19, 30)):
            assert (await annonce(c, None, "sur_place"))[:2] == (0, 0)  # un autre type ne bouge pas
            ajout, _, zones = await annonce(c, None, "livraison")
            assert ajout == 15  # l'annonce de la livraison compte aussi le soir chargé
        # il s'ajoute à la puce, il ne la remplace pas
        with horloge.remplacer(cas.base_a, paris(17, 19, 30)):
            await c.put(f"{RACINE}/etablissements/{etab}/temps", json={"type": "emporter", "minutes_ajoutees": 5}, headers=cas.session)
            assert (await annonce(c, None))[:2] == (15, 15)


# --------------------------------------------------------------------------- ingrédients et allergènes (surcouche), sources, fermetures


async def _produit(c, cas, ref):
    carte = (await c.get(f"{RACINE}/etablissements/{cas.sites_a[0]}/carte", headers=cas.session)).json()
    return next(p for p in carte["produits"] if p["id"] == ref)


async def test_ingredients_et_allergenes_s_ecrivent_en_surcouche_quand_la_caisse_porte_le_produit_et_en_direct_sinon(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    url = f"{RACINE}/etablissements/{etab}/carte/produit"
    async with client_http() as c:
        assert (await _importer(c, cas)).status_code == 200
        carte = (await c.get(f"{RACINE}/etablissements/{etab}/carte", headers=cas.session)).json()
        ref, autre = carte["produits"][0]["id"], carte["produits"][1]["id"]
        ingredients = [{"nom": "tomate", "retirable": False}, {"nom": "basilic", "retirable": True}]
        # une clé lit, elle n'écrit pas ; rien à écrire, un code d'allergène inconnu, un produit inconnu : refusés
        assert (await c.put(url, json={"ref": ref, "allergenes": []}, headers=_cle(cas.cle_a))).status_code == 403
        assert (await c.put(url, json={"ref": ref}, headers=cas.session)).status_code == 422
        assert (await c.put(url, json={"ref": ref, "allergenes": ["cacahuete"]}, headers=cas.session)).status_code == 422
        assert (await c.put(url, json={"ref": "inconnu", "allergenes": []}, headers=cas.session)).status_code == 404
        # le produit vient d'un fichier importé : l'écrit va en surcouche, source et date mises à jour
        avant = await _produit(c, cas, ref)
        assert (await c.put(url, json={"ref": ref, "ingredients": ingredients, "allergenes": []}, headers=cas.session)).json() == {"ok": True}
        ecrit = await _produit(c, cas, ref)
        assert ecrit["ingredients"] == ingredients and ecrit["allergenes"] == [] and ecrit["source"] == "mark"
        assert ecrit["maj_le"] > avant["maj_le"]
        assert len(await _donnees(cas.base_a, "SELECT 1 FROM mark.resto_surcouche WHERE site_id = $1 AND ref = $2 AND allergenes_ecrits", etab, ref)) == 1
        # inconnu (null) et aucun ([]) restent distincts, un champ absent reste intact
        assert (await c.put(url, json={"ref": ref, "allergenes": None}, headers=cas.session)).status_code == 200
        inconnu = await _produit(c, cas, ref)
        assert inconnu["allergenes"] is None and inconnu["ingredients"] == ingredients
        assert (await c.put(url, json={"ref": ref, "allergenes": ["gluten", "lait"]}, headers=cas.session)).status_code == 200
        assert (await _produit(c, cas, ref))["allergenes"] == ["gluten", "lait"]
        # un réimport du fichier ne l'écrase pas (W31)
        assert (await _importer(c, cas)).status_code == 200
        reimporte = await _produit(c, cas, ref)
        assert reimporte["allergenes"] == ["gluten", "lait"] and reimporte["ingredients"] == ingredients
        # un produit propre à l'établissement et tenu ici (source portail) : écrit en direct sur sa ligne, sans surcouche
        await _donnees(cas.base_a, "UPDATE mark.resto_produit SET source = 'portail' WHERE site_id = $1 AND ref = $2 RETURNING 1", etab, autre)
        assert (await c.put(url, json={"ref": autre, "allergenes": []}, headers=cas.session)).status_code == 200
        direct = await _produit(c, cas, autre)
        assert direct["allergenes"] == [] and direct["source"] == "mark"
        assert (await _donnees(cas.base_a, "SELECT allergenes FROM mark.resto_produit WHERE site_id = $1 AND ref = $2", etab, autre))[0]["allergenes"] == []
        assert await _donnees(cas.base_a, "SELECT 1 FROM mark.resto_surcouche WHERE site_id = $1 AND ref = $2 AND allergenes_ecrits", etab, autre) == []
        # l'alcool : un drapeau de la surcouche
        assert (await c.put(url, json={"ref": ref, "alcool": True}, headers=cas.session)).status_code == 200
        assert (await _produit(c, cas, ref))["alcool"] is True
    # rien n'a été écrit chez l'autre organisation
    assert await _donnees(cas.base_b, "SELECT 1 FROM mark.resto_surcouche") == []


async def test_les_sources_par_objet_et_la_pause_du_telephone_se_reglent_et_la_carte_tenue_ici_n_est_plus_en_lecture_seule(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    url = f"{RACINE}/etablissements/{etab}/reglages"
    c_base = await schema.connecter(cas.base_a)
    try:
        await c_base.execute("INSERT INTO mark.resto_liaison (site_id, prise, etat) VALUES ($1, 'hubrise', 'ok')", etab)
    finally:
        await c_base.close()
    async with client_http() as c:
        lu = (await c.get(url, headers=cas.session)).json()
        sources = {s["objet"]: s for s in lu["sources"]}
        assert [s["objet"] for s in lu["sources"]] == ["carte", "ruptures", "etat", "horaires", "remises", "clients"]
        assert sources["carte"]["mode"] == "caisse" and sources["carte"]["reglable"] is True and sources["remises"]["reglable"] is False
        assert lu["reglage"]["pause_caisse_pause_telephone"] is True
        assert (await c.put(url, json={"reglage": {"sources": {"carte": "ici"}}}, headers=_cle(cas.cle_a))).status_code == 403
        assert (await c.put(url, json={"reglage": {"sources": {"remises": "ici"}}}, headers=cas.session)).status_code == 422
        assert (await c.put(url, json={"reglage": {"sources": {"carte": "autre"}}}, headers=cas.session)).status_code == 422
        assert (await c.get(f"{RACINE}/etablissements/{etab}/carte", headers=cas.session)).json()["lecture_seule"] is True
        corps = {"reglage": {"sources": {"carte": "ici"}, "pause_caisse_pause_telephone": False}}
        assert (await c.put(url, json=corps, headers=cas.session)).status_code == 200
        # un second objet s'ajoute sans défaire le premier
        assert (await c.put(url, json={"reglage": {"sources": {"etat": "ici"}}}, headers=cas.session)).status_code == 200
        lu = (await c.get(url, headers=cas.session)).json()
        modes = {s["objet"]: s["mode"] for s in lu["sources"]}
        assert (modes["carte"], modes["etat"], modes["ruptures"]) == ("ici", "ici", "caisse") and lu["reglage"]["pause_caisse_pause_telephone"] is False
        assert (await c.get(f"{RACINE}/etablissements/{etab}/carte", headers=cas.session)).json()["lecture_seule"] is False
        # remis sur la caisse, l'objet suit la caisse de nouveau
        assert (await c.put(url, json={"reglage": {"sources": {"carte": "caisse"}}}, headers=cas.session)).status_code == 200
        assert {s["objet"]: s["mode"] for s in (await c.get(url, headers=cas.session)).json()["sources"]}["carte"] == "caisse"
        # le journal garde le changement
        histo = (await c.get(f"{RACINE}/etablissements/{etab}/historique", headers=cas.session)).json()
        assert any(h["objet"] == "resto_reglage" for h in histo["lignes"])


async def test_une_fermeture_exceptionnelle_s_ecrit_se_remplace_se_retire_et_l_agent_la_dit(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    from datetime import UTC, datetime

    from api.db.bases_clients.restauration_carte import etat_combine

    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    url = f"{RACINE}/etablissements/{etab}/reglages"
    jeudi_midi = datetime(2026, 11, 12, 11, 0, tzinfo=UTC)  # 12 h à Paris
    avant = jeudi_midi - timedelta(days=2)
    async with client_http() as c:
        assert (await c.get(url, headers=cas.session)).json()["fermetures"] == []
        corps = {"fermetures": [{"du": "2026-11-12", "au": "2026-11-13", "motif": "Mariage"}]}
        assert (await c.put(url, json=corps, headers=_cle(cas.cle_a))).status_code == 403
        assert (await c.put(url, json={"fermetures": [{"du": "2026-11-13", "au": "2026-11-12"}]}, headers=cas.session)).status_code == 422
        with horloge.remplacer(cas.base_a, avant):
            assert (await c.put(url, json=corps, headers=cas.session)).status_code == 200
            lu = (await c.get(url, headers=cas.session)).json()["fermetures"]
            assert [(f["du"], f["au"], f["motif"]) for f in lu] == [("2026-11-12", "2026-11-13", "Mariage")] and lu[0]["id"]
        c_base = await schema.connecter(cas.base_a)
        try:
            # le jeudi 12 et le vendredi 13 sont fermés (jour de fin INCLUS), le samedi 14 non
            assert (await etat_combine(c_base, etab, "emporter", jeudi_midi))["raison"] == "fermeture_exceptionnelle"
            assert (await etat_combine(c_base, etab, "emporter", jeudi_midi + timedelta(days=1)))["raison"] == "fermeture_exceptionnelle"
            assert (await etat_combine(c_base, etab, "emporter", jeudi_midi + timedelta(days=2)))["ouvert"] is True
        finally:
            await c_base.close()
        # remplacer : la même ligne (id gardé) raccourcie, une autre ajoutée ; un id inconnu : 404
        with horloge.remplacer(cas.base_a, avant):
            id_ = lu[0]["id"]
            nouveau = {"fermetures": [{"id": id_, "du": "2026-11-12", "au": "2026-11-12"}, {"du": "2026-12-24", "au": "2026-12-25", "motif": "Noël"}]}
            assert (await c.put(url, json=nouveau, headers=cas.session)).status_code == 200
            assert (await c.put(url, json={"fermetures": [{"id": id_ + 1000, "du": "2026-12-01", "au": "2026-12-01"}]}, headers=cas.session)).status_code == 404
            rendu = (await c.get(url, headers=cas.session)).json()["fermetures"]
            assert [(f["id"] == id_, f["du"], f["au"]) for f in rendu] == [(True, "2026-11-12", "2026-11-12"), (False, "2026-12-24", "2026-12-25")]
            # une liste absente ne touche à rien ; une liste vide les retire toutes
            assert (await c.put(url, json={"envoi_heure_changee": {"actif": False}}, headers=cas.session)).status_code == 200
            assert len((await c.get(url, headers=cas.session)).json()["fermetures"]) == 2
            assert (await c.put(url, json={"fermetures": []}, headers=cas.session)).status_code == 200
            assert (await c.get(url, headers=cas.session)).json()["fermetures"] == []
