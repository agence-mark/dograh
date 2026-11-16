"""[.mark] Module Restauration, lot 13 : les routes des écrans du fork Salle, Remises et Envois (F6, F7, M7).

Vraie authentification (session d'un compte de l'équipe, clé d'API), vraies bases de clients. Aucun appel à un tiers.

| Test | Ce qu'il prouve |
|---|---|
| plan | un plan écrit (salles, tables nouvelles, formes, décor, assemblages) se relit à l'identique ; un identifiant de table d'une autre salle ou inconnu est refusé ; une table tenue par une réservation à venir ne se retire pas (409, rien n'est écrit) |
| créneaux | créneaux, durées et règles écrits, relus, journalisés ; un créneau qui finit avant de commencer est refusé (422) |
| statut | « arrivée » s'écrit ; une réservation annulée ne change plus (404) |
| remises | créée en brouillon, allumée, mise en pause, reprise, terminée (jamais l'inverse), supprimée ; une remise de la caisse est en lecture seule ; ses résultats viennent des commandes gardées |
| envois | éteints par défaut ; un SMS allumé avec son texte se relit ; un texte trop long est refusé |
| cloisonnement | l'établissement d'une autre organisation : 404 partout, rien n'est écrit chez elle ; une clé lit, n'écrit pas |
| permissions | chaque route est au registre : lire = voir les conversations, écrire = ``agents.modifier`` |
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

from api.db.bases_clients import connexion as schema
from api.db.bases_clients.horloge import horloge
from api.services.equipe_mark import registre_routes as registre
from api.tests.mark.equipe_commun import (  # noqa: F401
    client_http,
    creer_compte,
    entetes,
    sans_preparation_des_organisations,
)
from api.tests.mark.test_base_client import base_essai  # noqa: F401
from api.tests.mark.test_contacts_portail import _cle, seconde_base  # noqa: F401
from api.tests.mark.test_restauration_flux import _deux_organisations_avec_des_etablissements

RACINE = "/api/v1/restauration/etablissements"


async def _cas(db_session, seconde_base):  # noqa: F811
    cas = await _deux_organisations_avec_des_etablissements(db_session, seconde_base)
    _, jeton = await creer_compte(db_session, f"salle-{uuid.uuid4().hex[:8]}@example.com", role="Administrateur", organisations=[cas.a])
    cas.session = entetes(jeton)
    return cas


async def _sql(base: str, requete: str, *args):
    c = await schema.connecter(base)
    try:
        return await c.fetch(requete, *args)
    finally:
        await c.close()


PLAN = {
    "salles": [
        {
            "id": "nouveau-s1", "nom": "Salle principale", "elements": [{"id": "bar0", "type": "bar", "x": 1, "y": 9, "l": 5, "h": 2}],
            "tables": [
                {"id": "nouveau-t1", "nom": "T1", "forme": "ronde", "x": 1, "y": 1, "l": 2, "h": 2, "couverts_min": 1, "couverts_max": 2, "assemblable_avec": ["nouveau-t2"]},
                {"id": "nouveau-t2", "nom": "T2", "forme": "rectangle", "x": 4, "y": 1, "l": 3, "h": 2, "couverts_min": 2, "couverts_max": 6, "assemblable_avec": ["nouveau-t1"]},
            ],
        },
        {"id": "nouveau-s2", "nom": "Terrasse", "elements": [], "tables": []},
    ]
}


def _plan_relu(salle: dict) -> dict:
    """Le plan tel que l'écran le renvoie à l'écriture suivante (identifiants réels)."""
    return {"salles": [{"id": str(s["id"]), "nom": s["nom"], "elements": s["elements"], "tables": [{**t, "id": str(t["id"]), "assemblable_avec": [str(a) for a in t["assemblable_avec"]]} for t in s["tables"]]} for s in salle["salles"]]}


async def test_le_plan_s_ecrit_se_relit_et_refuse_ce_qui_est_tenu(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        r = await c.put(f"{RACINE}/{etab}/salle/plan", json=PLAN, headers=cas.session)
        assert r.status_code == 200, r.text
        salle = r.json()
        assert [s["nom"] for s in salle["salles"]] == ["Salle principale", "Terrasse"]
        t1, t2 = salle["salles"][0]["tables"]
        assert (t1["nom"], t1["forme"], t1["l"], t2["forme"], t2["l"]) == ("T1", "ronde", 2, "rectangle", 3)
        assert t1["assemblable_avec"] == [t2["id"]] and t2["assemblable_avec"] == [t1["id"]]
        assert salle["salles"][0]["elements"][0]["type"] == "bar"
        # une table déplacée et renommée se relit
        plan = _plan_relu(salle)
        plan["salles"][0]["tables"][0].update(x=9, nom="T1 bis")
        relu = (await c.put(f"{RACINE}/{etab}/salle/plan", json=plan, headers=cas.session)).json()
        assert relu["salles"][0]["tables"][0]["x"] == 9 and relu["salles"][0]["tables"][0]["nom"] == "T1 bis"
        assert relu["salles"][0]["tables"][0]["id"] == t1["id"]  # la même table, pas une nouvelle
        # une table inconnue (d'une autre organisation, ou n'importe quel nombre) est refusée
        faux = _plan_relu(relu)
        faux["salles"][0]["tables"][0]["id"] = "999999999"
        assert (await c.put(f"{RACINE}/{etab}/salle/plan", json=faux, headers=cas.session)).status_code == 404
        # une table tenue par une réservation à venir ne se retire pas
        base = await schema.connecter(cas.base_a)
        try:
            debut = horloge(cas.base_a).maintenant() + timedelta(days=2)
            await base.execute(
                "INSERT INTO mark.resto_reservation (numero, site_id, debut, duree_minutes, couverts, prenom, table_ids, statut, cree_par) VALUES ($1, $2, $3, 90, 2, 'Leroy', $4, 'confirmee', 'portail')",
                uuid.uuid4(), etab, debut, [int(t1["id"])],
            )
        finally:
            await base.close()
        sans_t1 = _plan_relu(relu)
        sans_t1["salles"][0]["tables"] = [t for t in sans_t1["salles"][0]["tables"] if t["id"] != str(t1["id"])]
        assert (await c.put(f"{RACINE}/{etab}/salle/plan", json=sans_t1, headers=cas.session)).status_code == 409
        assert len((await c.get(f"{RACINE}/{etab}/salle", headers=cas.session)).json()["salles"][0]["tables"]) == 2  # rien n'a été écrit
        # la réservation se lit avec le nom de sa table, sans le téléphone d'une autre
        resa = (await c.get(f"{RACINE}/{etab}/salle", headers=cas.session)).json()["reservations"]
        assert len(resa) == 1 and resa[0]["tables"] == ["T1 bis"] and resa[0]["prenom"] == "Leroy"
        # une clé lit, elle n'écrit pas
        assert (await c.get(f"{RACINE}/{etab}/salle", headers=_cle(cas.cle_a))).status_code == 200
        assert (await c.put(f"{RACINE}/{etab}/salle/plan", json=PLAN, headers=_cle(cas.cle_a))).status_code == 403
        # le statut « arrivée »
        numero = resa[0]["numero"]
        assert (await c.post(f"{RACINE}/{etab}/reservations/{numero}/statut", json={"statut": "honoree"}, headers=cas.session)).status_code == 200
        assert (await c.get(f"{RACINE}/{etab}/salle", headers=cas.session)).json()["reservations"][0]["statut"] == "honoree"
        assert (await c.post(f"{RACINE}/{etab}/reservations/{numero}/statut", json={"statut": "annulee"}, headers=cas.session)).status_code == 422
        base = await schema.connecter(cas.base_a)
        try:
            await base.execute("UPDATE mark.resto_reservation SET statut = 'annulee' WHERE numero = $1::uuid", numero)
        finally:
            await base.close()
        assert (await c.post(f"{RACINE}/{etab}/reservations/{numero}/statut", json={"statut": "absente"}, headers=cas.session)).status_code == 404


async def test_les_creneaux_les_durees_et_les_regles_s_ecrivent(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    corps = {
        "services": [{"nom": "Midi", "jours": [2, 3, 4, 5, 6], "debut": "11:30", "fin": "14:00", "pas_minutes": 15}, {"nom": "Soir", "jours": [2, 3, 4, 5, 6, 7], "debut": "18:30", "fin": "22:30", "pas_minutes": 30}],
        "durees": [{"couverts_min": 1, "couverts_max": 2, "duree_minutes": 75}, {"couverts_min": 3, "couverts_max": 8, "duree_minutes": 120}],
        "regles": {"delai_minimal": 120, "jours_a_l_avance": 45, "couverts_max_groupe": 10},
    }
    async with client_http() as c:
        for faux in ({"services": [{**corps["services"][0], "fin": "11:00"}]}, {"services": [{**corps["services"][0], "jours": [8]}]}, {"durees": [{"couverts_min": 5, "couverts_max": 2, "duree_minutes": 60}]}, {}):
            assert (await c.put(f"{RACINE}/{etab}/salle/creneaux", json=faux, headers=cas.session)).status_code == 422
        r = await c.put(f"{RACINE}/{etab}/salle/creneaux", json=corps, headers=cas.session)
        assert r.status_code == 200, r.text
        lu = r.json()
        assert [(s["nom"], s["debut"], s["fin"], s["jours"]) for s in lu["services"]] == [("Midi", "11:30", "14:00", [2, 3, 4, 5, 6]), ("Soir", "18:30", "22:30", [2, 3, 4, 5, 6, 7])]
        assert [(d["couverts_min"], d["couverts_max"], d["duree_minutes"]) for d in lu["durees"]] == [(1, 2, 75), (3, 8, 120)]
        assert (lu["regles"]["delai_minimal"], lu["regles"]["jours_a_l_avance"], lu["regles"]["couverts_max_groupe"]) == (120, 45, 10)
        # seules les règles données changent ; les créneaux restent
        r = await c.put(f"{RACINE}/{etab}/salle/creneaux", json={"regles": {"jours_a_l_avance": 10}}, headers=cas.session)
        assert r.json()["regles"]["jours_a_l_avance"] == 10 and r.json()["regles"]["delai_minimal"] == 120 and len(r.json()["services"]) == 2
    journal = await _sql(cas.base_a, "SELECT auteur FROM mark.resto_journal WHERE objet IN ('resto_service', 'resto_duree_groupe')")
    assert journal and all(j["auteur"] for j in journal)


async def test_les_remises_se_gerent_d_un_etat_a_l_autre_et_celles_de_la_caisse_se_lisent_seulement(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    remise = {"nom": "Mardi pizza", "mecanisme": "deuxieme_moitie_prix", "declencheur": {"rang": 2}, "effet": {"pourcentage": 50}, "perimetre": {"categories": ["pizzas"]},
              "cumul": "exclusive", "phrase": "Ce soir, la deuxième pizza est à moitié prix.", "moment": {"jours": [2]}}
    async with client_http() as c:
        assert (await c.post(f"{RACINE}/{etab}/remises", json={**remise, "mecanisme": "inventee"}, headers=cas.session)).status_code == 422
        assert (await c.post(f"{RACINE}/{etab}/remises", json={**remise, "en_trop": 1}, headers=cas.session)).status_code == 422
        assert (await c.post(f"{RACINE}/{etab}/remises", json=remise, headers=_cle(cas.cle_a))).status_code == 403
        cree = await c.post(f"{RACINE}/{etab}/remises", json=remise, headers=cas.session)
        assert cree.status_code == 201, cree.text
        assert cree.json()["lecture_seule"] is False and cree.json()["remises"][0]["etat"] == "brouillon"
        rid = cree.json()["remises"][0]["id"]
        url = f"{RACINE}/{etab}/remises/{rid}"
        # brouillon -> active -> suspendue -> active -> terminee ; jamais l'inverse
        for vers, attendu in (("suspendue", 409), ("active", 200), ("suspendue", 200), ("active", 200), ("terminee", 200), ("active", 409)):
            assert (await c.post(url + "/etat", json={"etat": vers}, headers=cas.session)).status_code == attendu, vers
        assert (await c.put(url, json={**remise, "nom": "Autre"}, headers=cas.session)).status_code == 409  # terminée : ne change plus
        # une remise de la caisse se lit, ne se change pas
        base = await schema.connecter(cas.base_a)
        try:
            ligne = await base.fetchval(
                "INSERT INTO mark.resto_remise (site_id, nom, mecanisme, effet, etat, source, ref_caisse) VALUES ($1, 'Caisse -10', 'pourcentage', '{\"pourcentage\": 10}'::jsonb, 'active', 'caisse', 'C10') RETURNING id", etab
            )
            # une commande qui porte la remise : ses résultats viennent d'elle
            await base.execute(
                "INSERT INTO mark.resto_commande (numero, site_id, numero_court, mode, statut, total, remises) "
                "VALUES ($1, $2, 'A1', 'emporter', 'terminee', 2250, $3::jsonb)", uuid.uuid4(), etab, json.dumps([{"nom": "Caisse -10", "montant": 250, "ref_caisse": "C10"}]),
            )
        finally:
            await base.close()
        assert (await c.post(f"{RACINE}/{etab}/remises/{ligne}/etat", json={"etat": "terminee"}, headers=cas.session)).status_code == 409
        assert (await c.delete(f"{RACINE}/{etab}/remises/{ligne}", headers=cas.session)).status_code == 409
        liste = (await c.get(f"{RACINE}/{etab}/remises", headers=cas.session)).json()["remises"]
        caisse = next(x for x in liste if x["id"] == ligne)
        assert (caisse["utilisations"], caisse["ca_centimes"], caisse["remise_centimes"]) == (1, 2250, 250)
        # la nôtre se supprime ; l'historique la garde
        assert (await c.delete(url, headers=cas.session)).status_code == 200
        assert all(x["id"] != rid for x in (await c.get(f"{RACINE}/{etab}/remises", headers=cas.session)).json()["remises"])
    assert await _sql(cas.base_a, "SELECT 1 FROM mark.resto_journal WHERE objet = 'resto_remise' AND operation = 'delete'")


async def test_les_envois_sont_eteints_par_defaut_et_se_reglent(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    async with client_http() as c:
        lu = (await c.get(f"{RACINE}/{etab}/envois", headers=cas.session)).json()["envois"]
        assert {e["declencheur"] for e in lu} == {"commande_enregistree", "reservation_enregistree", "reservation_modifiee", "reservation_annulee", "carte", "avis", "heure_changee"}
        assert not any(e["actif"] for e in lu) and all(e["texte"] == e["texte_par_defaut"] for e in lu)
        assert (await c.put(f"{RACINE}/{etab}/envois", json={"envois": [{"declencheur": "carte", "texte": "x" * 161}]}, headers=cas.session)).status_code == 422
        assert (await c.put(f"{RACINE}/{etab}/envois", json={"envois": [{"declencheur": "inconnu", "actif": True}]}, headers=cas.session)).status_code == 422
        r = await c.put(f"{RACINE}/{etab}/envois", json={"envois": [{"declencheur": "reservation_enregistree", "actif": True, "texte": "Merci {{prenom}}, à {{quand}}."}]}, headers=cas.session)
        assert r.status_code == 200, r.text
        pris = next(e for e in r.json()["envois"] if e["declencheur"] == "reservation_enregistree")
        assert pris["actif"] is True and pris["texte"] == "Merci {{prenom}}, à {{quand}}."
        # les autres restent éteints ; un second réglage ne change que le champ donné
        assert sum(e["actif"] for e in r.json()["envois"]) == 1
        r = await c.put(f"{RACINE}/{etab}/envois", json={"envois": [{"declencheur": "reservation_enregistree", "actif": False}]}, headers=cas.session)
        pris = next(e for e in r.json()["envois"] if e["declencheur"] == "reservation_enregistree")
        assert pris["actif"] is False and pris["texte"] == "Merci {{prenom}}, à {{quand}}."
    # un envoi éteint n'est jamais rendu « actif » au mécanisme du lot 7
    lignes = await _sql(cas.base_a, "SELECT actif FROM mark.resto_envoi WHERE site_id = $1 AND declencheur = 'reservation_enregistree'", etab)
    assert [x["actif"] for x in lignes] == [False]


async def test_un_etablissement_d_une_autre_organisation_est_un_404_partout(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    chez_b = max(cas.sites_a + cas.sites_b) + 1000
    uuid_ = uuid.uuid4()
    async with client_http() as c:
        for methode, chemin, corps in (
            ("get", "salle", None), ("put", "salle/plan", PLAN), ("put", "salle/creneaux", {"regles": {"delai_minimal": 5}}), ("post", f"reservations/{uuid_}/statut", {"statut": "honoree"}),
            ("get", "remises", None), ("post", "remises", {"nom": "x", "mecanisme": "montant", "effet": {"montant": 100}}), ("post", "remises/1/etat", {"etat": "active"}), ("delete", "remises/1", None),
            ("get", "envois", None), ("put", "envois", {"envois": [{"declencheur": "carte", "actif": True}]}),
        ):
            r = await getattr(c, methode)(f"{RACINE}/{chez_b}/{chemin}", headers=cas.session, **({"json": corps} if corps is not None else {}))
            assert r.status_code == 404, (methode, chemin, r.status_code)
    for table in ("resto_salle", "resto_remise", "resto_envoi"):
        assert await _sql(cas.base_a, f"SELECT 1 FROM mark.{table}") == [] and await _sql(cas.base_b, f"SELECT 1 FROM mark.{table}") == []


def test_chaque_route_est_au_registre_avec_la_bonne_permission():
    e = "/restauration/etablissements/{etablissement_id}"
    for chemin in (f"{e}/salle", f"{e}/remises", f"{e}/envois"):
        decision, _ = registre.decision_de("GET", chemin)
        assert decision.cle == "conversations.voir" and decision.pour_cle is None, chemin
    for methode, chemin in (
        ("PUT", f"{e}/salle/plan"), ("PUT", f"{e}/salle/creneaux"), ("POST", f"{e}/reservations/{{reservation_id}}/statut"), ("POST", f"{e}/remises"), ("PUT", f"{e}/remises/{{remise_id}}"),
        ("POST", f"{e}/remises/{{remise_id}}/etat"), ("DELETE", f"{e}/remises/{{remise_id}}"), ("PUT", f"{e}/envois"),
    ):
        decision, _ = registre.decision_de(methode, chemin)
        assert decision.cle == "agents.modifier" and decision.pour_cle is None, (methode, chemin)


async def test_les_dernieres_commandes_se_lisent_et_la_fiche_de_la_caisse_dit_chaque_prise(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    etab = cas.sites_a[0]
    base = await schema.connecter(cas.base_a)
    try:
        for i in range(3):
            await base.execute(
                "INSERT INTO mark.resto_commande (numero, site_id, numero_court, mode, statut, total, ref_fournisseur) VALUES ($1, $2, $3, 'emporter', 'terminee', $4, $5)",
                uuid.uuid4(), etab, f"A{i}", 1000 + i, f"R{i}",
            )
    finally:
        await base.close()
    async with client_http() as c:
        r = (await c.get(f"{RACINE}/{etab}/commandes-recentes", params={"limite": 2}, headers=cas.session)).json()["commandes"]
        assert len(r) == 2 and {x["numero_court"] for x in r} <= {"A0", "A1", "A2"} and all(x["ref_caisse"].startswith("R") for x in r)
        assert (await c.get(f"{RACINE}/{etab}/commandes-recentes", params={"limite": 0}, headers=cas.session)).status_code == 422
        assert (await c.get(f"{RACINE}/{max(cas.sites_a + cas.sites_b) + 1000}/commandes-recentes", headers=cas.session)).status_code == 404
        fiche = (await c.get(f"{RACINE}/{etab}/caisse", headers=cas.session)).json()
        assert set(fiche["prises"]) == {"hubrise", "imprimante"} and fiche["prises"]["hubrise"]["carte"] == "lue" and fiche["prises"]["imprimante"]["carte"] == "non"


async def test_la_liste_des_clients_dit_le_type_quand_le_module_est_allume(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    cas = await _cas(db_session, seconde_base)
    async with client_http() as c:
        avant = (await c.get("/api/v1/relation/clients", headers=cas.session)).json()
        assert avant and all(x["type_entreprise"] is None for x in avant)
        assert (await c.put("/api/v1/restauration/module", json={"actif": True}, headers=cas.session)).status_code == 200
        apres = {x["id"]: x["type_entreprise"] for x in (await c.get("/api/v1/relation/clients", headers=cas.session)).json()}
    assert apres[cas.a] == "restauration" and apres.get(cas.b) is None  # l'autre organisation n'a rien allumé


async def test_le_modele_de_reglages_restauration_ne_pose_que_des_cles_connues_et_classees(db_session, seconde_base, sans_preparation_des_organisations):  # noqa: F811
    from api.routes.restauration_salle import KITS_RESTAURATION, REGLAGES_RESTAURATION
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
    from api.services.modeles_reglages.classement import est_classee

    champs = WorkflowConfigurationDefaults.model_fields
    for cle, valeur in REGLAGES_RESTAURATION.items():
        assert cle in champs and est_classee(cle), cle
        # la valeur passe la validation de l'agent
        WorkflowConfigurationDefaults.model_validate({cle: valeur})
    assert all(k.startswith("garde_") for k in REGLAGES_RESTAURATION if k.startswith("garde_")) and sum(k.startswith("garde_") for k in REGLAGES_RESTAURATION) == 7
    cas = await _cas(db_session, seconde_base)
    async with client_http() as c:
        assert (await c.get("/api/v1/restauration/modele-reglages")).status_code == 401
        r = (await c.get("/api/v1/restauration/modele-reglages", headers=_cle(cas.cle_a))).json()
    assert r == {"reglages": REGLAGES_RESTAURATION, "kits": list(KITS_RESTAURATION)}
