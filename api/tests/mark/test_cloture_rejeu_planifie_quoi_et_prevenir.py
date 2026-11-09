"""[.mark] Clôture, lot E (D19) : le rejeu planifié dit « ce qui est rejoué » et « prévenir qui ».

| Test | Ce qu'il prouve |
|---|---|
| défauts | toute la suite et « tous » : ce que faisait le rejeu avant ; les valeurs inconnues sont refusées (la route : 422) |
| tests obligatoires | seuls les tests marqués obligatoires sont rejoués ; aucun obligatoire : « sans tests », rien n'est joué |
| suite et attaques | les attaques ne partent que sur ce choix (fonction remplacée : aucune dépense) ; leur échec ne défait pas la suite |
| régression | un recul (ok puis pas ok, ou moins de réussites) prévient, une première exécution ou une amélioration non |
| prévenir qui | « personne » ne prévient jamais ; la portée du mail est celle choisie ; un mail qui échoue ne défait rien |
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from api.services.alertes_agent import planifie
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT  # noqa: F401
from api.tests.mark.test_alertes_agent import EQUIPE, LUNDI_11H, banc, client_pour, faux_db, routes, un_rejeu  # noqa: F401

pytestmark = pytest.mark.asyncio

BON = {"ok": True, "reussis": 3, "total": 3, "version": 2, "plafond": None}
MOINS_BON = {"ok": False, "reussis": 2, "total": 3, "version": 3, "plafond": None}


async def test_les_defauts_sont_ce_que_faisait_le_rejeu(faux_db):  # noqa: F811
    lu = await planifie.lire(ORG_CLIENT, AGENT)
    assert lu["quoi"] == "toute_la_suite" and lu["prevenir"] == "tous"
    with pytest.raises(ValueError):
        await planifie.regler(ORG_CLIENT, AGENT, quoi="tout")
    with pytest.raises(ValueError):
        await planifie.regler(ORG_CLIENT, AGENT, prevenir="Evan")
    assert planifie.propres({"quoi": "x", "prevenir": 3})["quoi"] == "toute_la_suite"


async def test_toute_la_suite_ne_passe_pas_de_noms_comme_avant(faux_db):  # noqa: F811
    await planifie.regler(ORG_CLIENT, AGENT, actif=True, heure=3)
    rejouer = un_rejeu()
    await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H)
    assert "noms" not in rejouer.appels[0][2]


async def test_les_tests_obligatoires_seuls_sont_rejoues(faux_db, monkeypatch):  # noqa: F811
    from api.services.builder.tests_agent import stockage

    async def lister(organisation, agent):
        return [{"slug": "a", "obligatoire": True}, {"slug": "b"}, {"slug": "c", "obligatoire": True}]

    monkeypatch.setattr(stockage, "lister", lister)
    await planifie.regler(ORG_CLIENT, AGENT, actif=True, heure=3, quoi="tests_obligatoires")
    rejouer = un_rejeu()
    rendu = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H)
    assert rejouer.appels[0][2]["noms"] == ["a", "c"] and rendu["quoi"] == "tests_obligatoires"


async def test_sans_test_obligatoire_rien_n_est_joue(faux_db, monkeypatch):  # noqa: F811
    from api.services.builder.tests_agent import stockage

    monkeypatch.setattr(stockage, "lister", AsyncMock(return_value=[{"slug": "b"}]))
    await planifie.regler(ORG_CLIENT, AGENT, actif=True, heure=3, quoi="tests_obligatoires")
    rejouer = un_rejeu()
    rendu = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=rejouer, maintenant=LUNDI_11H)
    assert rendu["statut"] == "sans_tests" and rejouer.appels == []


async def test_les_attaques_ne_partent_que_sur_suite_et_attaques_et_leur_echec_ne_defait_pas_la_suite(faux_db):  # noqa: F811
    attaquer = AsyncMock(return_value={"resume": "21 ont tenu, 1 a cédé"})
    await planifie.regler(ORG_CLIENT, AGENT, actif=True, heure=3)  # toute la suite
    await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu(), attaquer=attaquer, maintenant=LUNDI_11H)
    assert attaquer.await_count == 0
    await planifie.regler(ORG_CLIENT, AGENT, quoi="suite_et_attaques")
    rendu = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu(), attaquer=attaquer, maintenant=LUNDI_11H + timedelta(days=1))
    assert attaquer.await_count == 1 and rendu["attaques"] == {"statut": "joue", "resume": "21 ont tenu, 1 a cédé"} and rendu["statut"] == "joue"
    casse = AsyncMock(side_effect=RuntimeError("fournisseur en panne"))
    rendu = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu(), attaquer=casse, maintenant=LUNDI_11H + timedelta(days=2))
    assert rendu["statut"] == "joue" and rendu["attaques"]["statut"] == "echec"  # la suite reste jouée


def test_une_regression_est_un_recul_jamais_une_premiere_execution_ni_une_amelioration():
    def joue(**k):
        return {"statut": "joue", **k}

    assert planifie.est_une_regression(joue(ok=True, reussis=3), joue(ok=False, reussis=2)) is True
    assert planifie.est_une_regression(joue(ok=False, reussis=2), joue(ok=False, reussis=1)) is True
    assert planifie.est_une_regression(joue(ok=False, reussis=2), joue(ok=False, reussis=2)) is False
    assert planifie.est_une_regression(joue(ok=False, reussis=2), joue(ok=True, reussis=3)) is False
    assert planifie.est_une_regression(None, joue(ok=False, reussis=0)) is False
    assert planifie.est_une_regression({"statut": "echec"}, joue(ok=False, reussis=0)) is False
    assert planifie.est_une_regression(joue(ok=True, reussis=3), {"statut": "interrompu"}) is False


async def test_une_regression_previent_selon_le_choix_et_jamais_pour_personne(faux_db):  # noqa: F811
    prevenir = AsyncMock()
    await planifie.regler(ORG_CLIENT, AGENT, actif=True, heure=3, prevenir="mark")
    premier = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu(BON), prevenir=prevenir, maintenant=LUNDI_11H)
    assert premier["regression"] is False and prevenir.await_count == 0
    recul = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu(MOINS_BON), prevenir=prevenir, maintenant=LUNDI_11H + timedelta(days=1))
    assert recul["regression"] is True and prevenir.await_count == 1
    assert prevenir.await_args.args[3] == "mark"  # la portée choisie
    await planifie.regler(ORG_CLIENT, AGENT, prevenir="personne")
    await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu(BON), prevenir=prevenir, maintenant=LUNDI_11H + timedelta(days=2))
    await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu(MOINS_BON), prevenir=prevenir, maintenant=LUNDI_11H + timedelta(days=3))
    assert prevenir.await_count == 1  # personne : rien de plus


async def test_un_mail_qui_echoue_ne_defait_ni_le_resultat_ni_la_tache(faux_db):  # noqa: F811
    await planifie.regler(ORG_CLIENT, AGENT, actif=True, heure=3)
    await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu(BON), maintenant=LUNDI_11H)
    casse = AsyncMock(side_effect=RuntimeError("pas de serveur de mail"))
    rendu = await planifie.jouer_si_du(ORG_CLIENT, AGENT, rejouer=un_rejeu(MOINS_BON), prevenir=casse, maintenant=LUNDI_11H + timedelta(days=1))
    assert rendu["regression"] is True and (await planifie.lire(ORG_CLIENT, AGENT))["derniere"]["regression"] is True


async def test_la_portee_du_mail_est_celle_choisie(monkeypatch):
    from api.services.apres_appel import notification

    monkeypatch.setattr(notification, "adresses_de_lorganisation", AsyncMock(return_value=["org@example.org"]))
    installation = type("I", (), {"adresses_notification": ["mark@example.org"], "smtp": type("S", (), {"configure": False})()})()
    monkeypatch.setattr(notification, "lire_installation", AsyncMock(return_value=(None, installation)))
    envoyer = AsyncMock()
    monkeypatch.setattr(notification.mail, "envoyer", envoyer)
    monkeypatch.setattr(notification, "lire_reglages", AsyncMock(return_value=type("R", (), {"smtp": type("S", (), {"configure": True})()})()))
    for portee, attendu in (("tous", ["org@example.org", "mark@example.org"]), ("organisation", ["org@example.org"]), ("mark", ["mark@example.org"])):
        assert await notification.notifier(5, "sujet", "texte", portee=portee) == attendu
    assert await notification.notifier(5, "sujet", "texte", portee="Evan") == []  # une faute de frappe n'envoie à personne


def test_la_route_pose_ce_qui_est_rejoue_et_qui_prevenir_et_refuse_le_reste(routes):  # noqa: F811
    client = client_pour(EQUIPE)
    adresse = f"/builder/planification/{AGENT}"
    ok = client.put(adresse, json={"quoi": "suite_et_attaques", "prevenir": "organisation"})
    assert ok.status_code == 200 and ok.json()["quoi"] == "suite_et_attaques" and ok.json()["prevenir"] == "organisation"
    assert client.get(adresse).json()["quoi"] == "suite_et_attaques"
    assert client.put(adresse, json={"quoi": "tout"}).status_code == 422
    assert client.put(adresse, json={"prevenir": "Pierre"}).status_code == 422
