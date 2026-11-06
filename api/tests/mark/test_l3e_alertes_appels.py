"""[.mark] builder partie 3, L3e sous-lot 1 : les alertes sur les VRAIS appels, nouveaux types du service d'alertes unique.

| Test | La garantie |
|---|---|
| signaux | chaque signal (ratés du juge, transferts, garde-fous, pannes, latence) monte contre la période précédente, avec assez d'appels et de cas |
| bruit | pas assez d'appels, pas assez de cas, sous le seuil, ou latence non mesurée : rien |
| un seul mécanisme | les types sont dans ``types.TYPES`` / ``service.CALCULS`` ; l'alerte est levée une fois, la liste des appels concernés est jointe |
| aucune dépense | aucun appel à un modèle ; une seule lecture des appels pour les cinq signaux |
| indicateurs | l'après-appel range ``garde_fous`` et ``panne`` |
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from api.services.alertes_agent import appels, reglages, service, types
from api.services.boucle import indicateurs
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT

MAINTENANT = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def appel(run_id, jours_avant, *, transfert=False, garde_fous=0, panne=False, latence=1.0, verdict="reussi"):
    return {
        "run_id": run_id,
        "workflow_id": AGENT,
        "workflow_nom": "agent",
        "cree_le": MAINTENANT - timedelta(days=jours_avant),
        "version": 1,
        "annotations": {
            "boucle": {"indicateurs": {"transfert": transfert, "garde_fous": garde_fous, "panne": panne, "latence_mediane": latence}},
            "juge": {"etat": "juge", "verdicts": [{"verdict": verdict}]},
        },
    }


def periode(debut_id, jours, n, **kw):
    return [appel(debut_id + i, jours, **kw) for i in range(n)]


def cas(mauvais, **kw):
    """10 appels sains la semaine d'avant, puis 10 appels dont ``mauvais`` sont concernés cette semaine."""
    return periode(100, 10, 10) + periode(200, 2, 10 - mauvais) + periode(300, 2, mauvais, **kw)


SEUILS = {code: types.seuils_par_defaut(code) for code in types.TYPES_DES_APPELS}

SIGNAUX = [
    (types.HAUSSE_RATES, {"verdict": "rate"}),
    (types.HAUSSE_TRANSFERTS, {"transfert": True}),
    (types.HAUSSE_GARDE_FOUS, {"garde_fous": 2}),
    (types.HAUSSE_PANNES, {"panne": True}),
]


@pytest.mark.parametrize("code,kw", SIGNAUX)
def test_un_signal_qui_monte_assez_avec_assez_d_appels_leve_une_alerte_avec_ses_appels(code, kw):
    r = appels.comparer(code, cas(4, **kw), SEUILS[code], MAINTENANT)
    assert r is not None and r["appels_concernes"] == 4 and sorted(r["appels"]) == [300, 301, 302, 303]
    (m,) = r["mesures"]
    assert m["nom"] == code and m["avant"] == 0 and m["apres"] == 0.4
    assert "40 %" in appels.resume(code, r) and "4 appel(s)" in appels.resume(code, r)


@pytest.mark.parametrize("code,kw", SIGNAUX)
def test_pas_assez_de_cas_ou_d_appels_ou_une_hausse_trop_faible_ne_disent_rien(code, kw):
    assert appels.comparer(code, cas(2, **kw), SEUILS[code], MAINTENANT) is None  # 2 cas < 3 : du bruit
    assert appels.comparer(code, cas(4, **kw)[:15], SEUILS[code], MAINTENANT) is None  # 5 appels dans la période < 10
    stable = periode(100, 10, 7) + periode(150, 10, 3, **kw) + periode(200, 2, 7) + periode(300, 2, 3, **kw)  # 3 sur 10 des deux côtés
    assert appels.comparer(code, stable, SEUILS[code], MAINTENANT) is None


def test_une_periode_precedente_a_zero_compte_comme_une_hausse_et_les_vieux_appels_sont_ignores():
    lignes = cas(3, transfert=True) + periode(900, 40, 20, transfert=True)  # 40 jours : hors des deux périodes
    r = appels.comparer(types.HAUSSE_TRANSFERTS, lignes, SEUILS[types.HAUSSE_TRANSFERTS], MAINTENANT)
    assert r is not None and r["appels_concernes"] == 3


def test_la_latence_se_compare_en_mediane_et_seulement_quand_elle_est_mesuree():
    seuils = SEUILS[types.HAUSSE_LATENCE]
    lente = periode(100, 10, 10, latence=1.0) + periode(200, 2, 10, latence=1.6)
    r = appels.comparer(types.HAUSSE_LATENCE, lente, seuils, MAINTENANT)
    assert r is not None and r["mesures"][0]["avant"] == 1.0 and r["mesures"][0]["apres"] == 1.6 and r["appels_concernes"] == 10
    assert "1.00 s → 1.60 s" in appels.resume(types.HAUSSE_LATENCE, r)
    nonmesuree = periode(100, 10, 10, latence=None) + periode(200, 2, 10, latence=None)
    assert appels.comparer(types.HAUSSE_LATENCE, nonmesuree, seuils, MAINTENANT) is None
    proche = periode(100, 10, 10, latence=1.0) + periode(200, 2, 10, latence=1.2)  # +20 % < 30 %
    assert appels.comparer(types.HAUSSE_LATENCE, proche, seuils, MAINTENANT) is None


def test_la_cle_d_une_alerte_est_celle_du_bloc_de_jours_donc_stable_d_une_nuit_a_l_autre():
    nuit = appels.cle_de_la_periode(MAINTENANT, 7)
    assert appels.cle_de_la_periode(MAINTENANT + timedelta(hours=3), 7) == nuit
    assert appels.cle_de_la_periode(MAINTENANT + timedelta(days=8), 7) != nuit


def test_les_cinq_signaux_sont_des_types_du_service_unique():
    for code in types.TYPES_DES_APPELS:
        assert code in types.TYPES and code in service.CALCULS
        assert set(types.TYPES[code].seuils) == {"hausse", "appels_min", "jours", "cas_min"}
    assert types.VERSION_MOINS_BIEN in service.CALCULS


# --- le service -------------------------------------------------------------------------------------------------------------


@pytest.fixture
def banc(monde, monkeypatch):
    donnees = {"lignes": cas(4, transfert=True)}
    lecture = AsyncMock(side_effect=lambda org, jours, workflow_id: donnees["lignes"])
    db = MagicMock()
    db.runs_pour_la_qualite = lecture
    monkeypatch.setattr(appels, "db_client", db)
    # Les lignes sont datées de ``MAINTENANT`` : on fige l'horloge du calcul.
    vrai = appels.comparer
    monkeypatch.setattr(appels, "comparer", lambda code, lignes, seuils, maintenant=None: vrai(code, lignes, seuils, MAINTENANT))
    from api.services.boucle import qualite

    monkeypatch.setattr(qualite, "calculer", AsyncMock(return_value={"versions": []}))
    ameliorations = MagicMock(ajouter_un_cas_d_amelioration=AsyncMock())
    monkeypatch.setattr(service, "db_client", ameliorations)
    mail = AsyncMock(return_value=["equipe@exemple.test"])
    monkeypatch.setattr("api.services.apres_appel.notification.notifier", mail)
    return type("B", (), {"donnees": donnees, "lecture": lecture, "mail": mail, "db": ameliorations})


async def test_le_service_leve_l_alerte_une_fois_avec_les_appels_concernes_et_une_seule_lecture(banc):
    rendu = await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    levees = [a["alerte"] for a in rendu["alertes"]]
    assert [a["type"] for a in levees] == [types.HAUSSE_TRANSFERTS]
    alerte = levees[0]
    assert alerte["appels_concernes"] == 4 and sorted(alerte["appels"]) == [300, 301, 302, 303]
    assert alerte["id"].startswith(f"{types.HAUSSE_TRANSFERTS}:{AGENT}:p")
    assert banc.lecture.await_count == 1  # cinq signaux, une seule lecture
    banc.db.ajouter_un_cas_d_amelioration.assert_not_awaited()  # pas de faux problème de « Déploiement »
    banc.mail.assert_not_awaited()  # mail éteint par défaut
    encore = await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    assert encore["alertes"][0]["statut"] == "deja_levee"
    assert len((await reglages.lire(ORG_CLIENT, AGENT))["levees"]) == 1


async def test_le_mail_part_une_fois_quand_il_est_allume(banc):
    await reglages.regler(ORG_CLIENT, AGENT, mail=True)
    await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    banc.mail.assert_awaited_once()
    sujet, texte = banc.mail.await_args.args[1:3]
    assert "transférés" in sujet.lower() and "Voir les appels" in texte


async def test_un_type_eteint_n_est_pas_calcule_et_un_signal_en_panne_ne_coupe_pas_les_autres(banc):
    await reglages.regler(ORG_CLIENT, AGENT, par_type={types.HAUSSE_TRANSFERTS: {"actif": False}})
    rendu = await service.evaluer_un_agent(ORG_CLIENT, AGENT)
    assert rendu["alertes"] == [] and types.HAUSSE_TRANSFERTS in rendu["eteints"]
    await reglages.regler(ORG_CLIENT, AGENT, par_type={types.HAUSSE_TRANSFERTS: {"actif": True}})
    banc.lecture.side_effect = RuntimeError("base indisponible")
    assert (await service.evaluer_un_agent(ORG_CLIENT, AGENT))["alertes"] == []  # tracé, jamais levé


async def test_les_seuils_de_l_agent_s_appliquent(banc):
    await reglages.regler(ORG_CLIENT, AGENT, par_type={types.HAUSSE_TRANSFERTS: {"seuils": {"cas_min": 5}}})
    assert (await service.evaluer_un_agent(ORG_CLIENT, AGENT))["alertes"] == []


def test_aucun_appel_a_un_modele_dans_le_calcul_des_alertes():
    source = open(appels.__file__, encoding="utf8").read().lower()
    for interdit in ("interroger", "openai", "anthropic", "mistral", "queue_speech", "chat_completion"):
        assert interdit not in source


# --- l'après-appel range ce que les alertes lisent --------------------------------------------------------------------------


def test_l_apres_appel_range_les_garde_fous_et_la_panne():
    i = indicateurs.calculer([], {"securite_declenchements": [{"nom": "a"}, {"nom": "b"}], "call_disposition": "panne_technique"})
    assert i["garde_fous"] == 2 and i["panne"] is True
    i = indicateurs.calculer([], {"panne": {"cause": "x"}})
    assert i["panne"] is True and i["garde_fous"] == 0
    assert indicateurs.calculer([], {})["panne"] is False
