"""[.mark] D3 : un champ peut déclarer qu'il n'est pas rempli en fin d'appel.

Chantier correctifs-second-banc-34 (30/09/2026), runs 900 à 903 : la passe de fin d'appel
remplissait `autre` (« marque de l'appareil : Piazzetta », « il a un budget de 3500 euros »,
« Girard, g i r a r d ») et `symptome` (« C'est un poêle à bois. il remonte l'année
dernière ») de recopies. Mesuré sur les runs 861 à 904 : `symptome` écrit 10 fois par la
passe (1 juste), `autre` 5 fois (2 utiles).

⛔ Aucun champ en dur : le champ DÉCLARE `rempli_en_fin_d_appel` (à l'écran de la fiche).
Coché par défaut : rien ne change pour un agent qui ne le déclare pas.

| Test | Ce qu'il prouve |
|---|---|
| schéma | coché par défaut, décochable |
| clavier, passe de fin | un champ décoché n'est pas demandé à la passe ; le champ coché l'est toujours |
| clavier, outil | pendant l'appel, l'outil écrit toujours le champ décoché |
"""

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.tests.mark.test_clavier_porte_la_fiche import _converser, _monter, _noter
from pipecat.tests import MockLLMService

from unittest.mock import patch

FICHE = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        {
            "nom": "autre",
            "origine": "deduit",
            "description": "Tout ce qui n'entre dans aucun autre champ",
            "rempli_en_fin_d_appel": False,
        },
    ],
}


def test_D3_coche_par_defaut_et_decochable():
    assert ChampFiche(nom="autre").rempli_en_fin_d_appel is True
    assert ChampFiche(nom="autre", rempli_en_fin_d_appel=False).rempli_en_fin_d_appel is False


@pytest.mark.asyncio
async def test_D3_au_clavier_la_passe_de_fin_ne_demande_pas_un_champ_decoche(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE)
    demandes = []

    async def extraction(_gestionnaire, variables, _contexte_parent, consigne, *a, **k):
        demandes.append(sorted(v.name for v in variables))
        return {"nom": "Girard", "autre": "Girard, g i r a r d"}

    with patch(
        "api.services.workflow.pipecat_engine_variable_extractor."
        "VariableExtractionManager._perform_extraction",
        new=extraction,
    ):
        charge, _ = await _converser(
            test_client_factory,
            user,
            workflow,
            [MockLLMService.create_text_chunks("Très bien.")],
            "c'est Girard, g i r a r d",
            finir=True,
        )
    assert demandes == [["nom"]], demandes
    contexte = charge["gathered_context"]
    assert contexte.get("nom") == "Girard", contexte
    assert not contexte.get("autre"), contexte


@pytest.mark.asyncio
async def test_D3_au_clavier_l_outil_ecrit_toujours_un_champ_decoche(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, FICHE)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [
            _noter({"autre": "je voudrais savoir vos horaires"}, "note_1"),
            MockLLMService.create_text_chunks("C'est noté."),
        ],
        "je voudrais savoir vos horaires",
    )
    assert charge["checkpoint"]["gathered_context"].get("autre") == "je voudrais savoir vos horaires", charge[
        "checkpoint"
    ]["gathered_context"]
