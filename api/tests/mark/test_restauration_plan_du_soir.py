"""[.mark] Module Restauration, lot 26, M13 : le plan de salle du soir (tables rassemblées pour un jour, positions du soir) et la capacité qui en tient compte.

| Test | Ce qu'il prouve |
|---|---|
| rassembler | un groupe de tables devient UNE table (couverts min le plus petit, max la somme) ; groupe incomplet ou en double ignoré ; rejouer ne change rien |
| capacité | la fenêtre du plan seule compte ; une réservation sur une table rassemblée prend toutes ses tables ; une table prise rend le groupe indisponible |
| base | un groupe pour le soir permet un groupe de 7 que le plan enregistré refuse ; un autre jour ou un autre service, rien ne change ; « Revenir au plan » le retire |
| écriture | tables d'un autre établissement, doublons, service d'un autre : refusés ; positions gardées ; le plan enregistré n'est jamais modifié ; journal |
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import connexion as schema
from api.db.bases_clients import horloge
from api.db.bases_clients.capacite import Occupation, Regles, Service, Unite, placer, rassembler, unites_du_creneau
from api.db.bases_clients.restauration_plan_soir import plan_du_soir, poser_plan_du_soir, retirer_plan_du_soir
from api.db.bases_clients.restauration_reservation import creer_reservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI

PARIS = ZoneInfo("Europe/Paris")
TEL = "+33612345678"
SAMEDI_20H = datetime(2026, 11, 14, 20, 0, tzinfo=PARIS)
DIMANCHE_20H = SAMEDI_20H + timedelta(days=1)
MAINTENANT = datetime(2026, 11, 12, 12, 0, tzinfo=PARIS)
SERVICES = [Service("soir", [1, 2, 3, 4, 5, 6, 7], "19:00", "22:00", 15)]


# --------------------------------------------------------------------------- #
# le calcul, sans base
# --------------------------------------------------------------------------- #


def test_un_groupe_devient_une_seule_table_et_rejouer_ne_change_rien():
    unites = [Unite(1, 1, 2, frozenset({2})), Unite(2, 1, 2, frozenset({1})), Unite(3, 2, 4), Unite(4, 4, 6, frozenset({9}))]
    r = rassembler(unites, [[3, 4]])
    fusion = next(u for u in r if u.membres)
    assert (fusion.id, fusion.capacite_min, fusion.capacite_max, sorted(fusion.membres)) == (3, 2, 10, [3, 4])
    assert fusion.assemblable_avec == frozenset({9}) and sorted(u.id for u in r) == [1, 2, 3]
    assert rassembler(r, [[3, 4]]) == r  # rejouer : les membres ne sont plus là, le groupe est ignoré
    # un membre absent (table retirée), un groupe d'une seule table, une table déjà prise par un autre groupe : ignorés
    assert rassembler(unites, [[3, 99], [1]]) == unites
    deux = rassembler(unites, [[1, 3], [3, 4]])
    assert sorted(sorted(u.ids) for u in deux) == [[1, 3], [2], [4]]


def test_la_fenetre_du_plan_est_la_seule_a_compter_et_la_table_rassemblee_prend_toutes_ses_tables():
    unites = [Unite(1, 1, 2), Unite(2, 1, 2), Unite(3, 2, 4)]
    soir = (SAMEDI_20H.replace(hour=19), SAMEDI_20H.replace(hour=22), [[2, 3]])
    regles = Regles(plans_du_soir=(soir,))
    assert len(unites_du_creneau(unites, SAMEDI_20H, regles)) == 2
    assert len(unites_du_creneau(unites, SAMEDI_20H.replace(hour=22), regles)) == 3  # la fin de la fenêtre est exclue
    assert len(unites_du_creneau(unites, DIMANCHE_20H, regles)) == 3
    # 5 personnes : seule la table rassemblée (2 à 6) les accueille ; elle réserve ses deux tables
    assert placer(SAMEDI_20H, 90, 5, unites, [], SERVICES, PARIS, MAINTENANT, regles) == ("ok", (2, 3))
    assert placer(SAMEDI_20H, 90, 5, unites, [], SERVICES, PARIS, MAINTENANT, Regles())[0] == "complet"
    # une des deux tables est prise : le groupe n'est plus libre
    prise = Occupation(SAMEDI_20H, SAMEDI_20H + timedelta(minutes=90), 2, frozenset({3}))
    assert placer(SAMEDI_20H, 90, 5, unites, [prise], SERVICES, PARIS, MAINTENANT, regles)[0] == "complet"
    # et à l'inverse, une réservation faite sur le groupe rend les deux tables indisponibles pour un petit groupe
    groupe_pris = Occupation(SAMEDI_20H, SAMEDI_20H + timedelta(minutes=90), 5, frozenset({2, 3}))
    assert placer(SAMEDI_20H, 90, 2, unites, [groupe_pris], SERVICES, PARIS, MAINTENANT, regles) == ("ok", (1,))
    assert placer(SAMEDI_20H, 90, 4, unites, [groupe_pris], SERVICES, PARIS, MAINTENANT, regles)[0] == "complet"


# --------------------------------------------------------------------------- #
# avec la base
# --------------------------------------------------------------------------- #


@pytest.fixture
async def salle(base_prete):
    c = await schema.connecter(base_prete)
    try:
        await c.execute("INSERT INTO mark.entreprise (raison_sociale) VALUES ('Entreprise')")
        ids = {}
        for cle in ("a", "b"):
            ids[cle] = await c.fetchval("INSERT INTO mark.site (entreprise_id, cle, nom, fuseau) SELECT id, $1, $1, 'Europe/Paris' FROM mark.entreprise RETURNING id", cle)
        a, b = ids["a"], ids["b"]
        s = await c.fetchval("INSERT INTO mark.resto_salle (site_id, nom) VALUES ($1, 'Salle') RETURNING id", a)
        t = {}
        for nom, mini, maxi in (("T1", 1, 2), ("T2", 1, 2), ("T3", 2, 4), ("T4", 4, 6)):
            t[nom] = await c.fetchval("INSERT INTO mark.resto_table (site_id, salle_id, nom, couverts_min, couverts_max) VALUES ($1, $2, $3, $4, $5) RETURNING id", a, s, nom, mini, maxi)
        sb = await c.fetchval("INSERT INTO mark.resto_salle (site_id, nom) VALUES ($1, 'Autre') RETURNING id", b)
        t["B1"] = await c.fetchval("INSERT INTO mark.resto_table (site_id, salle_id, nom, couverts_min, couverts_max) VALUES ($1, $2, 'B1', 1, 4) RETURNING id", b, sb)
        service = await c.fetchval("INSERT INTO mark.resto_service (site_id, nom, jours, debut, fin, pas_minutes) VALUES ($1, 'Soir', '{1,2,3,4,5,6,7}', '19:00', '22:00', 15) RETURNING id", a)
        midi = await c.fetchval("INSERT INTO mark.resto_service (site_id, nom, jours, debut, fin, pas_minutes) VALUES ($1, 'Midi', '{1,2,3,4,5,6,7}', '11:00', '14:00', 15) RETURNING id", a)
        service_b = await c.fetchval("INSERT INTO mark.resto_service (site_id, nom, debut, fin) VALUES ($1, 'Soir', '19:00', '22:00') RETURNING id", b)
        await c.execute("INSERT INTO mark.resto_duree_groupe (site_id, couverts_min, couverts_max, duree_minutes) VALUES ($1, 1, 20, 90)", a)
        await c.execute("INSERT INTO mark.resto_regle_reservation (site_id, delai_minimal, jours_a_l_avance, couverts_max_groupe) VALUES ($1, 60, 30, 12)", a)
        with horloge.remplacer(base_prete, JEUDI_MIDI):
            yield SimpleNamespace(c=c, a=a, b=b, t=t, base=base_prete, service=service, midi=midi, service_b=service_b)
    finally:
        await c.close()


def demande(**plus):
    return {"debut": SAMEDI_20H, "couverts": 7, "prenom": "Alice", "telephone": TEL, "appel_id": "a1", **plus}


async def test_un_groupe_pour_le_soir_permet_un_groupe_que_le_plan_enregistre_refuse(salle):
    c, a, t = salle.c, salle.a, salle.t
    assert (await creer_reservation(c, a, demande())).faits["detail"] == "complet"  # sans plan du soir : 7 ne tient nulle part
    tables_avant = [dict(r) for r in await c.fetch("SELECT * FROM mark.resto_table WHERE site_id = $1 ORDER BY id", a)]
    r = await poser_plan_du_soir(c, a, SAMEDI_20H.date(), [[t["T3"], t["T4"]]], {t["T1"]: {"x": 12.5, "y": 40}})
    assert r.statut == "OK" and r.faits["assemblages"] == [[t["T3"], t["T4"]]] and r.faits["positions"] == {str(t["T1"]): {"x": 12.5, "y": 40}}
    res = await creer_reservation(c, a, demande())
    assert res.statut == "ENREGISTREE", res
    assert sorted(res.faits["tables"]) == ["T3", "T4"]
    assert sorted(await c.fetchval("SELECT table_ids FROM mark.resto_reservation WHERE numero = $1::uuid", res.faits["numero"])) == sorted([t["T3"], t["T4"]])
    # le groupe est pris : un second groupe de 7 au même moment est complet, un petit groupe prend une autre table
    assert (await creer_reservation(c, a, demande(appel_id="a2", telephone="+33611111111"))).faits["detail"] == "complet"
    assert (await creer_reservation(c, a, demande(appel_id="a3", telephone="+33622222222", couverts=2))).faits["tables"] == ["T1"]
    # le plan enregistré n'a jamais été touché
    assert [dict(r) for r in await c.fetch("SELECT * FROM mark.resto_table WHERE site_id = $1 ORDER BY id", a)] == tables_avant
    # un autre jour : rien ne change
    assert (await creer_reservation(c, a, demande(debut=DIMANCHE_20H, appel_id="d1"))).faits["detail"] == "complet"


async def test_un_plan_d_un_autre_service_ne_joue_pas_et_revenir_au_plan_le_retire(salle):
    c, a, t = salle.c, salle.a, salle.t
    jour = SAMEDI_20H.date()
    await poser_plan_du_soir(c, a, jour, [[t["T3"], t["T4"]]], service_id=salle.midi)
    assert (await creer_reservation(c, a, demande())).faits["detail"] == "complet"  # le plan est celui du midi, la réservation est du soir
    assert (await plan_du_soir(c, a, jour)) is None and (await plan_du_soir(c, a, jour, salle.midi)) is not None
    await poser_plan_du_soir(c, a, jour, [[t["T3"], t["T4"]]], service_id=salle.service)
    assert (await creer_reservation(c, a, demande())).statut == "ENREGISTREE"
    # remplacer un plan : une seule ligne par (jour, service)
    await poser_plan_du_soir(c, a, jour, [[t["T1"], t["T2"]]], service_id=salle.service)
    assert await c.fetchval("SELECT count(*) FROM mark.resto_plan_soir WHERE site_id = $1 AND service_id = $2", a, salle.service) == 1
    assert (await retirer_plan_du_soir(c, a, jour, salle.service)).statut == "OK"
    assert (await retirer_plan_du_soir(c, a, jour, salle.service)).statut == "DEJA_FAIT"
    assert (await creer_reservation(c, a, demande(appel_id="apres", telephone="+33644444444"))).faits["detail"] == "complet"


async def test_les_refus_du_plan_du_soir_et_le_journal(salle):
    c, a, t = salle.c, salle.a, salle.t
    jour = SAMEDI_20H.date()
    avant = await c.fetchval("SELECT count(*) FROM mark.resto_plan_soir")
    assert (await poser_plan_du_soir(c, a, jour, [[t["T3"], t["B1"]]])).statut == "INTROUVABLE"        # une table d'un autre établissement
    assert (await poser_plan_du_soir(c, a, jour, [[t["T3"], t["T4"]]], service_id=salle.service_b)).statut == "INTROUVABLE"  # un service d'un autre
    assert (await poser_plan_du_soir(c, a, jour, [], {t["B1"]: {"x": 1, "y": 1}})).statut == "INTROUVABLE"
    assert (await poser_plan_du_soir(c, a, jour, [[t["T3"]]])).manque == "assemblages"                  # un groupe d'une seule table
    assert (await poser_plan_du_soir(c, a, jour, [[t["T3"], t["T3"]]])).statut == "ARGUMENT_INVALIDE"
    assert (await poser_plan_du_soir(c, a, jour, [[t["T1"], t["T2"]], [t["T2"], t["T3"]]])).manque == "assemblages"  # une table dans deux groupes
    assert (await poser_plan_du_soir(c, a, jour, [], {t["T1"]: {"x": "a", "y": 1}})).manque == "positions"
    assert await c.fetchval("SELECT count(*) FROM mark.resto_plan_soir") == avant                        # rien n'est écrit
    # une table désactivée ne se rassemble pas
    await c.execute("UPDATE mark.resto_table SET actif = false WHERE id = $1", t["T4"])
    assert (await poser_plan_du_soir(c, a, jour, [[t["T3"], t["T4"]]])).statut == "INTROUVABLE"
    await c.execute("UPDATE mark.resto_table SET actif = true WHERE id = $1", t["T4"])
    await poser_plan_du_soir(c, a, jour, [[t["T3"], t["T4"]]], source="portail", auteur="portail:test")
    j = await c.fetchrow("SELECT source, auteur, operation FROM mark.resto_journal WHERE objet = 'resto_plan_soir' ORDER BY id DESC LIMIT 1")
    assert (j["source"], j["auteur"], j["operation"]) == ("portail", "portail:test", "insert")
