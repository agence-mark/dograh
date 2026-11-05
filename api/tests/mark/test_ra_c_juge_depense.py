"""[.mark] RA-C, sous-lot 1 (audit 06 point 6) : compteur et plafond du juge des vrais appels.

Le juge range ses jetons et ses dollars dans ``mark_depense_roles`` (le mécanisme de SA-3, jamais un second), chaque jugement
dit ce qu'il a coûté, et un budget du mois atteint EN COURS de jugement laisse l'appel non jugé (``budget_atteint``) au lieu de
le noter « non vérifiable » critère après critère. Vraie base de test (transaction annulée), cerveaux factices : aucun appel réel.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from api.db import db_client
from api.services.builder.cerveau import budget_roles, simules
from api.services.builder.cerveau.budget_roles import BudgetDuRole
from api.services.builder.cerveau.factice import CerveauFactice, tour
from api.services.juge import appels, file, passes
from api.tests.mark.builder_commun import AGENT, monde  # noqa: F401
from api.tests.mark.equipe_commun import creer_organisation
from api.tests.mark.test_juge_unifie import LIGNES, _json, _juge, _run, mondes  # noqa: F401

pytestmark = pytest.mark.asyncio

PRIX = (10.0, 10.0)  # un tour factice (100 + 50 jetons) = 0,0015 $


@pytest.fixture(autouse=True)
def _dans_une_transaction_annulee(db_session):
    yield


@pytest.fixture
async def organisation():
    return await creer_organisation(db_client, f"org-juge-{uuid.uuid4().hex[:8]}")


def _brancher(monkeypatch, tours):
    cerveau_factice = CerveauFactice(*tours)
    monkeypatch.setattr("api.services.appel_simule.serie.cle_d_identifiant", AsyncMock(return_value="cle-factice"))
    monkeypatch.setattr(simules, "fabriquer", lambda reglages, cle: cerveau_factice)
    monkeypatch.setattr(simules, "prix_du_role", AsyncMock(return_value=PRIX))
    return cerveau_factice


async def test_chaque_jugement_range_ses_jetons_et_ses_dollars_dans_la_depense_du_juge(mondes,  # noqa: F811
    monkeypatch, organisation):
    await file.regler(organisation, AGENT, True)
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k", budget_mois=100.0)
    grille = await appels.grille()
    _brancher(monkeypatch, [tour(_json()) for _ in grille])
    await appels.apres_appel(_run(), organisation)
    resultat = mondes.ecrits[-1][1]["juge"]
    n = len(grille)
    assert resultat["etat"] == "juge"
    # le jugement dit ce qu'il a coûté, et c'est la même somme que celle du mois
    assert resultat["jetons"] == 150 * n and resultat["cout"] == pytest.approx(0.0015 * n)
    mois = (await budget_roles.depense_du_mois(organisation))["juge"]
    assert mois["jetons"] == 150 * n and mois["cout"] == pytest.approx(0.0015 * n)
    assert (await budget_roles.depense_du_mois(organisation))["appelant"]["jetons"] == 0  # l'autre rôle n'est pas touché


async def test_un_budget_atteint_en_cours_de_jugement_laisse_l_appel_non_juge(mondes,  # noqa: F811
    monkeypatch, organisation):
    await file.regler(organisation, AGENT, True)
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k", budget_mois=0.002)  # deux tours passent, le troisième est refusé
    grille = await appels.grille()
    cerveau = _brancher(monkeypatch, [tour(_json()) for _ in grille])
    await appels.apres_appel(_run(), organisation)
    resultat = mondes.ecrits[-1][1]["juge"]
    assert resultat["etat"] == "budget_atteint" and "monthly budget of the judge is reached" in resultat["raison"]
    assert "verdicts" not in resultat  # ni verdicts « non vérifiable » en cascade, ni note
    assert len(cerveau.requetes) == 2 and all(note is None for _, note in mondes.notes)


async def test_les_passes_ne_transforment_pas_un_budget_atteint_en_echec_du_cerveau():
    refus = BudgetDuRole("juge", "The monthly budget of the judge is reached (1.00 of 1.00): raise it.", 1.0, 1.0)
    cerveau = CerveauFactice(refus)
    with pytest.raises(BudgetDuRole):
        await passes.juger(cerveau, LIGNES, ["Suit le parcours"])
