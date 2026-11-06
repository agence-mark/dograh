"""[.mark] builder partie 3, sous-lot 6 (SE-11 = D-3) : l'alerte « une version fait moins bien », le service d'alertes unique, le point
d'origine « Déploiement » de « À améliorer », le rejeu planifié.

Aucun appel réel : les chiffres de la page Qualité, le mail et le rejeu de la suite sont des doublures ; la base est en mémoire.

| Test | La garantie |
|---|---|
| comparaison | la dernière version contre la précédente : baisse de note, hausse d'impasses ; pas assez d'appels ou sous le seuil = rien |
| seuils | bornés, un nom inconnu écarté, un type inconnu refusé |
| service | une alerte levée une seule fois (rangée, versée dans « À améliorer » avec l'origine Déploiement, dite par mail seulement si le mail est allumé, une fois) |
| jamais de bascule | l'évaluation ne touche ni la publication ni la version d'un agent |
| rejeu planifié | éteint par défaut ; une période = un rejeu (même en parallèle) ; arrêtable (délai, extinction) ; réservation oubliée libérée |
| tâches | au plus cinq rejeux par passage, une organisation en échec n'arrête pas les autres |
| routes | l'agent d'une autre organisation est un 404, la permission est déclarée |
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import ameliorations as route_ameliorations
from api.routes import builder_alertes as route
from api.services.alertes_agent import planifie, regression, reglages, service, taches, types
from api.services.auth.depends import get_user_with_selected_organization
from api.services.boucle import vues
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, utilisateur

EQUIPE = utilisateur(1, ORG_CLIENT)
AUTRE = utilisateur(2, 8)
SEUILS = types.seuils_par_defaut(types.VERSION_MOINS_BIEN)


def ligne(version, note, juges=20, impasse=0.02, mesures=20, workflow_id=AGENT):
    return {
        "workflow_id": workflow_id,
        "workflow_nom": "agent",
        "version": version,
        "note": note,
        "juges": juges,
        "part_impasse": impasse,
        "appels_mesures": mesures,
    }


# --- la comparaison ---------------------------------------------------------------------------------------------------------


def test_une_baisse_de_note_assez_grande_avec_assez_d_appels_est_une_regression():
    r = regression.comparer([ligne(6, 4.4), ligne(7, 3.7)], SEUILS)
    assert r["version"] == 7 and r["contre"] == 6
    (m,) = r["mesures"]
    assert m["nom"] == "note_du_juge" and m["ecart"] == -0.7 and m["appels_avant"] == 20
    assert "7 contre version 6" in regression.resume(r) and "4.4 → 3.7" in regression.resume(r)


def test_une_hausse_d_impasses_est_une_regression_a_part_et_les_deux_peuvent_se_dire_ensemble():
    r = regression.comparer([ligne(6, 4.4, impasse=0.02), ligne(7, 4.4, impasse=0.10)], SEUILS)
    assert [m["nom"] for m in r["mesures"]] == ["impasses"]
    deux = regression.comparer([ligne(6, 4.6, impasse=0.0), ligne(7, 3.9, impasse=0.2)], SEUILS)
    assert [m["nom"] for m in deux["mesures"]] == ["note_du_juge", "impasses"]
    assert "appels avec impasse 0 % → 20 %" in regression.resume(deux)


def test_pas_assez_d_appels_ou_sous_le_seuil_ou_une_seule_version_ou_une_amelioration_ne_disent_rien():
    assert regression.comparer([ligne(6, 4.4), ligne(7, 3.0, juges=5)], SEUILS) is None  # 5 appels jugés < 10 : du bruit
    assert regression.comparer([ligne(6, 4.4, juges=4), ligne(7, 3.0)], SEUILS) is None  # la version d'avant aussi doit être assez vue
    assert regression.comparer([ligne(6, 4.4), ligne(7, 4.1)], SEUILS) is None  # 0,3 < 0,5
    assert regression.comparer([ligne(7, 3.0)], SEUILS) is None
    assert regression.comparer([ligne(6, 3.0), ligne(7, 4.5)], SEUILS) is None
    assert regression.comparer([ligne(6, None), ligne(7, 3.0)], SEUILS) is None
    assert regression.comparer([ligne(6, 4.4, impasse=0.02, mesures=4), ligne(7, 4.4, impasse=0.5)], SEUILS) is None


def test_seule_la_derniere_version_est_comparee_a_la_precedente_quel_que_soit_l_ordre():
    lignes = [ligne(5, 2.0), ligne(7, 3.7), ligne(6, 4.4)]
    r = regression.comparer(lignes, SEUILS)
    assert (r["version"], r["contre"]) == (7, 6)


def test_les_seuils_sont_bornes_et_un_type_inconnu_est_refuse():
    s = types.seuils_valides(types.VERSION_MOINS_BIEN, {"baisse_note": 99, "appels_min": 0, "jours": "x", "inconnu": 1, "hausse_impasses": True})
    assert s["baisse_note"] == 4.0 and s["appels_min"] == 3 and s["jours"] == 14 and "inconnu" not in s and s["hausse_impasses"] == 0.05


# --- les réglages -----------------------------------------------------------------------------------------------------------


async def test_les_defauts_sont_une_alerte_active_et_un_mail_eteint(monde):
    r = await reglages.lire(ORG_CLIENT, AGENT)
    assert r["mail"] is False and r["types"][types.VERSION_MOINS_BIEN]["actif"] is True and r["levees"] == []
    r = await reglages.regler(ORG_CLIENT, AGENT, mail=True, par_type={types.VERSION_MOINS_BIEN: {"seuils": {"baisse_note": 1}, "actif": False}})
    assert r["mail"] is True and r["types"][types.VERSION_MOINS_BIEN] == {"actif": False, "seuils": {**SEUILS, "baisse_note": 1.0}}
    with pytest.raises(ValueError):
        await reglages.regler(ORG_CLIENT, AGENT, par_type={"type_inconnu": {"actif": True}})


async def test_une_alerte_au_meme_identifiant_n_est_levee_qu_une_fois_et_garde_sa_premiere_date(monde):
    a = {"id": "x:1:v7", "type": "x", "levee_le": "2026-11-01T00:00:00+00:00", "notifiee": False, "mesures": []}
    _, nouvelle = await reglages.lever(ORG_CLIENT, AGENT, dict(a))
    assert nouvelle is True
    await reglages.marquer_notifiee(ORG_CLIENT, AGENT, "x:1:v7")
    _, encore = await reglages.lever(ORG_CLIENT, AGENT, {**a, "levee_le": "2026-11-09T00:00:00+00:00", "mesures": [1]})
    assert encore is False
    (levee,) = (await reglages.lire(ORG_CLIENT, AGENT))["levees"]
    assert levee["levee_le"] == "2026-11-01T00:00:00+00:00" and levee["notifiee"] is True and levee["mesures"] == [1]
    for i in range(30):
        await reglages.lever(ORG_CLIENT, AGENT, {**a, "id": f"x:1:v{100 + i}"})
    assert len((await reglages.lire(ORG_CLIENT, AGENT))["levees"]) == reglages.LEVEES_MAX


# --- le service -------------------------------------------------------------------------------------------------------------


@pytest.fixture
def banc(monde, monkeypatch):
    """Les chiffres de la page Qualité, la base de « À améliorer » et le mail : des doublures qui notent ce qu'on leur demande."""
    chiffres = {"versions": [ligne(6, 4.4), ligne(7, 3.6)]}

    async def calculer(organisation_id, *, jours, workflow_id=None):
        chiffres["demande"] = (organisation_id, jours, workflow_id)
        return {"versions": chiffres["versions"]}

    from api.services.boucle import qualite

    monkeypatch.setattr(qualite, "calculer", calculer)
    db = MagicMock()
    db.ajouter_un_cas_d_amelioration = AsyncMock(return_value={})
    monkeypatch.setattr(service, "db_client", db)
    # L3e : les signaux des vrais appels lisent leurs propres lignes ; ici, aucun appel.
    from api.services.alertes_agent import appels

    monkeypatch.setattr(appels, "db_client", MagicMock(runs_pour_la_qualite=AsyncMock(return_value=[])))
    mail = AsyncMock(return_value=["equipe@exemple.test"])
    monkeypatch.setattr("api.services.apres_appel.notification.notifier", mail)
    return SimpleNS(chiffres=chiffres, db=db, mail=mail)


class SimpleNS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


async def test_une_regression_est_levee_une_fois_versee_dans_a_ameliorer_avec_l_origine_deploiement(banc):
    rendu = await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    ((r),) = rendu["alertes"]
    assert r["statut"] == "levee" and r["alerte"]["id"] == f"version_moins_bien:{AGENT}:v7" and r["alerte"]["notifiee"] is False
    assert banc.chiffres["demande"] == (ORG_CLIENT, 14, AGENT)
    banc.db.ajouter_un_cas_d_amelioration.assert_awaited_once()
    org, wf, cle, valeurs, cas = banc.db.ajouter_un_cas_d_amelioration.await_args.args
    assert (org, wf) == (ORG_CLIENT, AGENT) and valeurs["critere"].startswith("deploiement:") and valeurs["version_numero"] == 7
    assert cas["deploiement"] == 7 and cas["contre"] == 6 and "note du juge" in valeurs["replique"]
    banc.mail.assert_not_awaited()  # le mail est éteint par défaut
    # La même alerte évaluée de nouveau : rien de plus (ni problème, ni mail).
    encore = await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    assert encore["alertes"][0]["statut"] == "deja_levee"
    banc.db.ajouter_un_cas_d_amelioration.assert_awaited_once()
    assert len((await reglages.lire(ORG_CLIENT, AGENT))["levees"]) == 1


async def test_le_mail_ne_part_qu_une_fois_et_seulement_s_il_est_allume(banc):
    await reglages.regler(ORG_CLIENT, AGENT, mail=True)
    await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    banc.mail.assert_awaited_once()
    sujet, texte = banc.mail.await_args.args[1:3]
    assert "version 7" in sujet and "Rien n'a été retiré ni changé" in texte
    assert (await reglages.lire(ORG_CLIENT, AGENT))["levees"][0]["notifiee"] is True


async def test_un_mail_qui_ne_part_pas_ne_perd_pas_l_alerte_et_sera_redit_au_passage_suivant_seulement_si_nouvelle(banc):
    banc.mail.return_value = []  # aucune adresse : l'alerte reste dans la page, jamais perdue
    await reglages.regler(ORG_CLIENT, AGENT, mail=True)
    rendu = await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    assert rendu["alertes"][0]["alerte"]["notifiee"] is False
    assert (await reglages.lire(ORG_CLIENT, AGENT))["levees"][0]["id"].endswith("v7")


async def test_un_type_eteint_n_est_meme_pas_calcule_et_une_version_qui_va_bien_ne_dit_rien(banc):
    banc.chiffres["versions"] = [ligne(6, 4.0), ligne(7, 4.5)]
    assert (await service.evaluer_un_agent(ORG_CLIENT, AGENT))["alertes"] == []
    banc.chiffres.pop("demande")
    await reglages.regler(ORG_CLIENT, AGENT, par_type={types.VERSION_MOINS_BIEN: {"actif": False}})
    rendu = await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    assert rendu == {"alertes": [], "eteints": [types.VERSION_MOINS_BIEN]} and "demande" not in banc.chiffres
    banc.db.ajouter_un_cas_d_amelioration.assert_not_awaited()


async def test_les_seuils_de_l_agent_sont_ceux_de_la_comparaison(banc):
    await reglages.regler(ORG_CLIENT, AGENT, par_type={types.VERSION_MOINS_BIEN: {"seuils": {"baisse_note": 1.5, "jours": 7}}})
    rendu = await service.evaluer_un_agent(ORG_CLIENT, AGENT)  # 0,8 de baisse < 1,5
    assert rendu["alertes"] == [] and banc.chiffres["demande"][1] == 7


async def test_l_evaluation_ne_bascule_jamais_rien(banc):
    """Une alerte dit et pointe : la base n'est touchée que par le versement dans « À améliorer »."""
    await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    assert [a[0] for a in banc.db.method_calls] == ["ajouter_un_cas_d_amelioration"]
    source = open(service.__file__, encoding="utf8").read() + open(regression.__file__, encoding="utf8").read()
    for interdit in ("publish_workflow", "revenir", "set_current_definition", "retirer_le_deploiement", "update_workflow("):
        assert interdit not in source


async def test_une_panne_du_versement_ne_perd_pas_l_alerte(banc):
    banc.db.ajouter_un_cas_d_amelioration.side_effect = RuntimeError("base indisponible")
    rendu = await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    assert rendu["alertes"][0]["statut"] == "levee"
    assert (await reglages.lire(ORG_CLIENT, AGENT))["levees"][0]["id"].endswith("v7")


# --- le point d'origine « Déploiement » -------------------------------------------------------------------------------------


def test_un_probleme_de_deploiement_a_l_origine_deploiement_suggeree_et_acceptee_par_la_route():
    probleme = {"releve_par": "code", "critere": "deploiement:version_moins_bien:v7"}
    assert vues.origine_suggeree(probleme) == "deploiement"
    assert vues.origine_suggeree({"releve_par": "code", "critere": "impasse"}) == "code"  # les autres suggestions ne bougent pas
    assert route_ameliorations.ChangementDAmelioration(origine="deploiement").origine == "deploiement"
    with pytest.raises(ValueError):
        route_ameliorations.ChangementDAmelioration(origine="autre")


# --- le rejeu planifié ------------------------------------------------------------------------------------------------------

LUNDI_11H = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)  # 11 h à Paris


def un_rejeu(rendu=None, *, duree=0.0):
    appels = []

    async def rejouer(user, workflow, **kw):
        appels.append((user.selected_organization_id, workflow.id, kw))
        if duree:
            await asyncio.sleep(duree)
        return rendu if rendu is not None else {"ok": True, "reussis": 3, "total": 3, "version": 2, "plafond": None}

    rejouer.appels = appels
    return rejouer


@pytest.fixture
def faux_db(monde, monkeypatch):
    monkeypatch.setattr("api.db.db_client", monde)
    return monde


async def test_le_rejeu_planifie_est_eteint_par_defaut_et_ne_joue_rien(faux_db):
    assert (await planifie.lire(ORG_CLIENT, AGENT))["actif"] is False
    rejouer = un_rejeu()
    assert await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H) == {"statut": "pas_du"}
    assert rejouer.appels == []


async def test_une_periode_ne_se_joue_qu_une_fois_puis_la_suivante_repart(faux_db):
    await planifie.regler(ORG_CLIENT, AGENT, actif=True, heure=3, repetitions=2)
    rejouer = un_rejeu()
    premier = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H)
    assert premier["statut"] == "joue" and premier["ok"] is True and premier["reussis"] == 3
    assert rejouer.appels[0][2] == {"repetitions": 2}
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H + timedelta(hours=5)))["statut"] == "pas_du"
    assert len(rejouer.appels) == 1
    demain = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H + timedelta(days=1))
    assert demain["statut"] == "joue" and len(rejouer.appels) == 2
    lu = await planifie.lire(ORG_CLIENT, AGENT)
    assert lu["derniere"]["periode"] == "2026-11-03" and lu["en_cours"] is None


async def test_avant_l_heure_reglee_rien_ne_part_et_l_hebdomadaire_attend_la_semaine_suivante(faux_db):
    await planifie.regler(ORG_CLIENT, AGENT, actif=True, heure=12)
    rejouer = un_rejeu()
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H))["statut"] == "pas_du"
    await planifie.regler(ORG_CLIENT, AGENT, frequence="hebdomadaire", heure=3)
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H))["statut"] == "joue"
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H + timedelta(days=4)))["statut"] == "pas_du"
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H + timedelta(days=7)))["statut"] == "joue"
    assert planifie.periode("hebdomadaire", LUNDI_11H) == "2026-W45"
    with pytest.raises(ValueError):
        await planifie.regler(ORG_CLIENT, AGENT, frequence="chaque seconde")


async def test_deux_taches_en_meme_temps_ne_jouent_qu_une_fois(faux_db):
    await planifie.regler(ORG_CLIENT, AGENT, actif=True)
    rejouer = un_rejeu(duree=0.05)
    rendus = await asyncio.gather(*[planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H) for _ in range(4)])
    assert sorted(r["statut"] for r in rendus) == ["joue", "pas_du", "pas_du", "pas_du"]
    assert len(rejouer.appels) == 1


async def test_un_rejeu_trop_long_est_coupe_et_la_periode_est_rendue(faux_db, monkeypatch):
    monkeypatch.setattr(planifie, "DELAI_S", 0.05)
    await planifie.regler(ORG_CLIENT, AGENT, actif=True)
    rendu = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu(duree=2), maintenant=LUNDI_11H)
    assert rendu["statut"] == "interrompu"
    lu = await planifie.lire(ORG_CLIENT, AGENT)
    assert lu["en_cours"] is None and lu["derniere"]["statut"] == "interrompu"


async def test_un_echec_est_rangee_comme_resultat_de_la_periode_sans_remonter(faux_db):
    await planifie.regler(ORG_CLIENT, AGENT, actif=True)
    rejouer = AsyncMock(side_effect=RuntimeError("modèle indisponible"))
    rendu = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H)
    assert rendu["statut"] == "echec" and rendu["erreur"] == "RuntimeError"
    assert (await planifie.lire(ORG_CLIENT, AGENT))["derniere"]["periode"] == "2026-11-02"
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H))["statut"] == "pas_du"


async def test_un_agent_sans_test_ou_disparu_est_dit_sans_rien_jouer_de_plus(faux_db):
    await planifie.regler(ORG_CLIENT, AGENT, actif=True)
    rendu = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu({"disponible": False, "ok": False}), maintenant=LUNDI_11H)
    assert rendu["statut"] == "sans_tests"
    await planifie.regler(ORG_CLIENT, 999, actif=True)
    assert (await planifie.jouer_si_du(ORG_CLIENT, 999, rejouer=un_rejeu(), maintenant=LUNDI_11H))["statut"] == "echec"


async def test_eteindre_arrete_et_une_reservation_oubliee_se_libere_d_elle_meme(faux_db):
    await planifie.regler(ORG_CLIENT, AGENT, actif=True)
    ancienne = (LUNDI_11H - timedelta(seconds=planifie.DELAI_S + 600)).isoformat()
    from api.services.builder import stock

    await stock.ecrire(ORG_CLIENT, planifie.cle(AGENT), {**(await planifie.lire(ORG_CLIENT, AGENT)), "en_cours": {"periode": "2026-11-02", "depuis": ancienne}})
    rejouer = un_rejeu()
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H))["statut"] == "joue"  # tâche morte : reprise
    # Une réservation VIVANTE n'est pas reprise ; éteindre la retire.
    await stock.ecrire(ORG_CLIENT, planifie.cle(AGENT), {"actif": True, "en_cours": {"periode": "2026-11-03", "depuis": (LUNDI_11H + timedelta(days=1)).isoformat()}})
    demain = LUNDI_11H + timedelta(days=1, minutes=1)
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=demain))["statut"] == "pas_du"
    eteint = await planifie.regler(ORG_CLIENT, AGENT, actif=False)
    assert eteint["actif"] is False and eteint["en_cours"] is None
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=demain))["statut"] == "pas_du"
    assert len(rejouer.appels) == 1


async def test_le_rejeu_planifie_ne_bascule_jamais_rien(faux_db):
    source = open(planifie.__file__, encoding="utf8").read()
    for interdit in ("publish_workflow", "set_current_definition", "retirer_le_deploiement", "update_workflow("):
        assert interdit not in source


# --- les tâches de fond -----------------------------------------------------------------------------------------------------


async def test_une_passe_ne_joue_que_cinq_rejeux_et_saute_les_agents_eteints(faux_db, monkeypatch):
    for i in range(1, 9):
        faux_db.ajouter_agent(identifiant=500 + i)
        await planifie.regler(ORG_CLIENT, 500 + i, actif=i != 3)
    faux_db.lister_ids_organisations = AsyncMock(return_value=[ORG_CLIENT])
    monkeypatch.setattr(taches, "db_client", faux_db)
    monkeypatch.setattr(planifie, "datetime", MagicMock(now=lambda tz=None: LUNDI_11H, fromisoformat=datetime.fromisoformat))
    rejouer = un_rejeu()
    joues = await taches.rejouer_les_suites_planifiees(rejouer=rejouer)
    assert len(joues) == planifie.PAR_PASSAGE_MAX == len(rejouer.appels)
    assert 503 not in {j["agent"] for j in joues}
    # La passe d'après reprend où elle s'est arrêtée : ceux déjà faits ne rejouent pas.
    suite = await taches.rejouer_les_suites_planifiees(rejouer=rejouer)
    assert {j["agent"] for j in joues}.isdisjoint({j["agent"] for j in suite}) and len(suite) == 2


async def test_la_nuit_une_organisation_en_echec_n_arrete_pas_les_autres(banc, monkeypatch):
    from api.services.boucle import qualite

    async def calculer(organisation_id, *, jours, workflow_id=None):
        if organisation_id == 13:
            raise RuntimeError("lecture impossible")
        return {"versions": banc.chiffres["versions"]}

    monkeypatch.setattr(qualite, "calculer", calculer)
    db = MagicMock()
    db.lister_ids_organisations = AsyncMock(return_value=[13, ORG_CLIENT])
    monkeypatch.setattr(taches, "db_client", db)
    assert await taches.evaluer_les_alertes() == {ORG_CLIENT: 1}


def test_les_deux_taches_sont_au_planning_du_worker():
    source = open(taches.__file__.replace("services\\alertes_agent\\taches.py", "tasks\\arq.py").replace("services/alertes_agent/taches.py", "tasks/arq.py"), encoding="utf8").read()
    assert "cron(evaluer_les_alertes" in source and "cron(rejouer_les_suites_planifiees" in source


# --- les routes -------------------------------------------------------------------------------------------------------------


def client_pour(user):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: user
    return TestClient(app)


@pytest.fixture
def routes(banc, monkeypatch):
    monkeypatch.setattr(route, "db_client", banc_monde(banc))
    return None


def banc_monde(_banc):
    from api.tests.mark.builder_commun import FauxDb

    db = FauxDb()
    db.ajouter_agent()
    return db


def test_les_routes_lisent_reglent_et_evaluent(routes):
    c = client_pour(EQUIPE)
    lu = c.get(f"/builder/alertes/{AGENT}").json()
    assert lu["mail"] is False and lu["catalogue"][types.VERSION_MOINS_BIEN]["seuils"]["baisse_note"]["defaut"] == 0.5
    regle = c.put(f"/builder/alertes/{AGENT}", json={"mail": True, "types": {types.VERSION_MOINS_BIEN: {"seuils": {"baisse_note": 1}}}}).json()
    assert regle["mail"] is True and regle["types"][types.VERSION_MOINS_BIEN]["seuils"]["baisse_note"] == 1.0
    assert c.put(f"/builder/alertes/{AGENT}", json={"types": {"inconnu": {"actif": True}}}).status_code == 422
    evalue = c.post(f"/builder/alertes/{AGENT}/evaluer").json()
    assert evalue["alertes"] == []  # 0,8 de baisse < 1,0 réglé ci-dessus


def test_le_rejeu_planifie_se_regle_par_la_route_et_refuse_une_valeur_fausse(routes):
    c = client_pour(EQUIPE)
    assert c.get(f"/builder/planification/{AGENT}").json()["actif"] is False
    ok = c.put(f"/builder/planification/{AGENT}", json={"actif": True, "frequence": "hebdomadaire", "heure": 5, "repetitions": 2}).json()
    assert ok["actif"] is True and ok["frequence"] == "hebdomadaire" and ok["heure"] == 5 and ok["repetitions"] == 2
    for faux in ({"frequence": "chaque seconde"}, {"heure": 25}, {"repetitions": 99}):
        assert c.put(f"/builder/planification/{AGENT}", json=faux).status_code == 422
    assert c.put(f"/builder/planification/{AGENT}", json={"actif": False}).json()["actif"] is False


def test_l_agent_d_une_autre_organisation_est_un_404_partout(routes):
    c = client_pour(AUTRE)
    assert c.get(f"/builder/alertes/{AGENT}").status_code == 404
    assert c.put(f"/builder/alertes/{AGENT}", json={"mail": True}).status_code == 404
    assert c.post(f"/builder/alertes/{AGENT}/evaluer").status_code == 404
    assert c.get(f"/builder/planification/{AGENT}").status_code == 404
    assert c.put(f"/builder/planification/{AGENT}", json={"actif": True}).status_code == 404


def test_les_permissions_sont_declarees_le_rejeu_planifie_demande_celle_de_jouer_les_tests():
    from api.services.equipe_mark.registre_routes import decision_de

    assert decision_de("PUT", "/builder/planification/{workflow_id}")[0].cle == "tests.jouer"
    assert decision_de("PUT", "/builder/alertes/{workflow_id}")[0].cle == "agents.modifier"
    assert decision_de("POST", "/builder/alertes/{workflow_id}/evaluer")[0].cle == "agents.modifier"


async def test_l_hebdomadaire_attend_son_jour_et_rattrape_une_fois_s_il_a_ete_manque(faux_db):
    await planifie.regler(ORG_CLIENT, AGENT, actif=True, frequence="hebdomadaire", jour=4, heure=6)  # le vendredi à 6 h
    rejouer = un_rejeu()
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H))["statut"] == "pas_du"
    vendredi_5h = datetime(2026, 11, 6, 4, 0, tzinfo=UTC)  # 5 h à Paris, avant l'heure
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=vendredi_5h))["statut"] == "pas_du"
    samedi = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)  # le vendredi a été manqué : la semaine se rattrape, une fois
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=samedi))["statut"] == "joue"
    assert (await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=samedi + timedelta(hours=3)))["statut"] == "pas_du"
    assert len(rejouer.appels) == 1


async def test_les_cinq_derniers_resultats_sont_gardes_du_plus_recent_au_plus_ancien(faux_db):
    await planifie.regler(ORG_CLIENT, AGENT, actif=True)
    rejouer = un_rejeu()
    for jour in range(7):
        await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H + timedelta(days=jour))
    lu = await planifie.lire(ORG_CLIENT, AGENT)
    assert [h["periode"] for h in lu["historique"]] == ["2026-11-08", "2026-11-07", "2026-11-06", "2026-11-05", "2026-11-04"]
    assert lu["derniere"]["periode"] == "2026-11-08"
