"""[.mark] Partie 3, revue RV (point 2) : les tests lancés par l'API ont une limite.

| Test | Ce qu'il prouve |
|---|---|
| clé sans budget | une clé ne lance rien tant que le budget du mois de l'appelant simulé n'est pas posé (> 0) : 409 et phrase claire, rien joué |
| clé avec budget | le même appel passe quand le budget est réglé ; la session d'une personne n'est pas concernée |
| juge | un juge allumé sur une clé d'API exige aussi son budget |
| débit | au-delà de la limite par heure : 429, rien joué |
| dépense comptée | le modèle de l'agent pendant le rejeu entre dans la dépense du mois (rôle du rejeu), au prix de la table |
| budget atteint | la suite s'arrête avant le test suivant quand ce budget est atteint |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.db import db_client
from api.schemas.appel_simule import ReglagesAppelantSimule, RoleSimule
from api.services.appel_simule import reglages as appel_simule
from api.services.builder.cerveau import budget_roles, prix
from api.services.builder.tests_agent import automatisation, execution
from api.tests.mark.equipe_commun import client_http, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_n3b_tests_par_api import RENDU_OK, _cache_du_labo_propre, _monde  # noqa: F401

pytestmark = pytest.mark.usefixtures("sans_preparation_des_organisations")


def _adresse(cas) -> str:
    return f"/api/v1/automatisation/agents/{cas.agent.id}/tests/lancer"


async def _regler(org: int, *, appelant: float = 0.0, juge: float = 0.0, juge_actif: bool = False):
    await appel_simule.enregistrer_reglages(
        org,
        ReglagesAppelantSimule(
            appelant=RoleSimule(consigne="c", budget_mois=appelant),
            juge=RoleSimule(consigne="j", budget_mois=juge, actif=juge_actif, identifiant="k" if juge_actif else None),
        ),
    )


async def test_une_cle_sans_budget_du_mois_ne_lance_rien(db_session, monkeypatch):
    cas = await _monde(db_session, "rvb0")
    jouer = AsyncMock(return_value=RENDU_OK)
    monkeypatch.setattr(execution, "rejouer_la_suite", jouer)
    async with client_http() as c:
        r = await c.post(_adresse(cas), headers=cas.cle_a)
    assert r.status_code == 409 and "monthly budget" in r.json()["detail"] and "simulated caller" in r.json()["detail"]
    jouer.assert_not_awaited()


async def test_la_meme_cle_passe_quand_le_budget_est_regle(db_session, monkeypatch):
    cas = await _monde(db_session, "rvb1")
    await _regler(cas.a, appelant=5.0)
    jouer = AsyncMock(return_value=RENDU_OK)
    monkeypatch.setattr(execution, "rejouer_la_suite", jouer)
    async with client_http() as c:
        r = await c.post(_adresse(cas), headers=cas.cle_a)
    assert r.status_code == 200
    jouer.assert_awaited_once()


async def test_un_juge_sur_cle_d_api_exige_aussi_son_budget(db_session, monkeypatch):
    cas = await _monde(db_session, "rvj")
    await _regler(cas.a, appelant=5.0, juge=0.0, juge_actif=True)
    monkeypatch.setattr(execution, "rejouer_la_suite", AsyncMock(return_value=RENDU_OK))
    async with client_http() as c:
        r = await c.post(_adresse(cas), headers=cas.cle_a)
    assert r.status_code == 409 and "judge" in r.json()["detail"]


async def test_la_session_d_une_personne_n_est_pas_freinee_par_cette_regle(db_session):
    await automatisation.verifier_le_budget(SimpleNamespace(par_cle_api=False, selected_organization_id=1))


async def test_la_limite_de_debit_refuse_avec_un_429(db_session, monkeypatch):
    cas = await _monde(db_session, "rvd")
    await _regler(cas.a, appelant=5.0)
    jouer = AsyncMock(return_value=RENDU_OK)
    monkeypatch.setattr(execution, "rejouer_la_suite", jouer)
    appels = []

    class Limiteur:
        async def acquire_token(self, *args, **kwargs):
            appels.append((args, kwargs))
            return False

    monkeypatch.setattr("api.routes.automatisation.rate_limiter", Limiteur())
    async with client_http() as c:
        r = await c.post(_adresse(cas), headers=cas.cle_a)
    assert r.status_code == 429 and appels[0][0][1] == automatisation.PAR_HEURE
    assert appels[0][1]["scope_key"] == f"tests-api:{cas.a}"  # un seau par organisation
    jouer.assert_not_awaited()


async def test_le_modele_de_l_agent_pendant_le_rejeu_est_compte_dans_la_depense_du_mois(db_session, monkeypatch):
    cas = await _monde(db_session, "rvc")
    await prix.ecrire(cas.a, prix.TableDesPrix(modeles=[prix.PrixDUnModele(modele="m-agent", entree_par_million=10.0, sortie_par_million=20.0)]))
    usage = {"llm": {"LLMService#0|||m-agent": {"prompt_tokens": 1000, "completion_tokens": 500}}}
    monkeypatch.setattr(db_client, "get_workflow_run", AsyncMock(return_value=SimpleNamespace(usage_info=usage)))
    monkeypatch.setattr(execution, "_modele_de_l_agent", AsyncMock(return_value="m-agent"))
    avant = (await budget_roles.depense_du_mois(cas.a))["appelant"]["cout"]
    cout = await execution.compter_le_modele_de_l_agent(cas.agent, cas.a, [11, 12])
    # 2 runs x (1000 x 10 + 500 x 20) / 1e6 = 0,04
    assert cout == pytest.approx(0.04) and avant == 0
    assert (await budget_roles.depense_du_mois(cas.a))["appelant"]["cout"] == pytest.approx(0.04)
    assert (await budget_roles.depense_du_mois(cas.b))["appelant"]["cout"] == 0  # l'autre organisation ne voit rien


async def test_le_budget_atteint_arrete_la_suite_avant_le_test_suivant(db_session):
    cas = await _monde(db_session, "rva")
    await _regler(cas.a, appelant=0.5)
    assert await execution._budget_du_rejeu_atteint(cas.a) is None
    await budget_roles.enregistrer(cas.a, "appelant", entree=1_000_000, sortie=0, prix_entree=1.0, prix_sortie=1.0)
    assert await execution._budget_du_rejeu_atteint(cas.a) == "budget_appelant"
