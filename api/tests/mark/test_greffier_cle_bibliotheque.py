"""[.mark] Le greffier prend-il une clé de la bibliothèque, et son fournisseur entier ?

La question de ce fichier, et elle seule :

    Un bloc ``greffier_llm`` qui désigne une clé de la bibliothèque (``mark-cle:<uuid>``)
    et un fournisseur compatible OpenAI avec son adresse (Scaleway) donne-t-il un greffier
    qui part chez ce fournisseur, avec la vraie clé de l'organisation de l'appel -- et une
    clé introuvable ou d'un autre fournisseur fait-elle jouer l'appel en mode outil, sans
    jamais envoyer la référence ?

Pourquoi il existe
------------------
Chantier ``agent-leger-greffier``, lot C (D9, constat d'Evan et Pierre du 09/10) : la clé
du greffier devait être TAPÉE dans son bloc (« type it »), et son adresse ne pouvait pas
y être écrite : un greffier chez Scaleway avec un cerveau ailleurs était impossible.
"""

import inspect
from unittest.mock import AsyncMock, patch

import pytest

from api.services.pipecat import greffier as module_greffier
from api.services.pipecat.greffier import (
    configuration_du_greffier,
    resoudre_le_bloc_du_greffier,
)

REF = "mark-cle:343322ca-f4d1-4806-8bf6-b2c7ed904a4a"
SCALEWAY = "https://api.scaleway.ai/v1"
BLOC = {
    "provider": "openai",
    "model": "mistral-small-3.2-24b-instruct-2506",
    "base_url": SCALEWAY,
    "reasoning_effort": "low",
    "api_key": REF,
}


def _conversation():
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration

    return EffectiveAIModelConfiguration.model_validate(
        {
            "llm": {
                "provider": "mistral",
                "model": "mistral-large-2512",
                "api_key": "cle-conv",
            }
        }
    )


def _patch_cle(retour):
    return patch("api.services.cles_reference._cle", AsyncMock(return_value=retour))


async def test_la_reference_est_remplacee_par_la_cle_de_l_organisation():
    run_configs = {"greffier_llm": dict(BLOC), "autre": 1}
    with _patch_cle(("vraie-cle-scaleway", "openai")) as lecture:
        rendu = await resoudre_le_bloc_du_greffier(run_configs, 2)
    lecture.assert_awaited_once_with(REF.split(":", 1)[1], 2)
    assert rendu["greffier_llm"]["api_key"] == "vraie-cle-scaleway"
    assert rendu["autre"] == 1
    # La configuration lue n'est jamais modifiée (elle est estampillée ailleurs).
    assert run_configs["greffier_llm"]["api_key"] == REF


@pytest.mark.parametrize("retour", [None, ("cle-mistral", "mistral")])
async def test_introuvable_ou_autre_fournisseur_la_reference_reste(retour):
    with _patch_cle(retour):
        rendu = await resoudre_le_bloc_du_greffier({"greffier_llm": dict(BLOC)}, 2)
    assert rendu["greffier_llm"]["api_key"] == REF
    # ... et la configuration la refuse : l'appel part en mode outil, la référence jamais.
    with pytest.raises(ValueError):
        configuration_du_greffier(_conversation(), rendu["greffier_llm"])


async def test_sans_reference_rien_n_est_lu():
    with _patch_cle(("x", "openai")) as lecture:
        bloc = {**BLOC, "api_key": "cle-tapee"}
        rendu = await resoudre_le_bloc_du_greffier({"greffier_llm": bloc}, 2)
    lecture.assert_not_awaited()
    assert rendu["greffier_llm"]["api_key"] == "cle-tapee"


def test_le_greffier_part_chez_scaleway_avec_ses_reglages():
    configuration = configuration_du_greffier(
        _conversation(), {**BLOC, "api_key": "vraie-cle-scaleway"}
    )
    llm = configuration.llm
    assert (llm.provider, llm.model, llm.base_url) == (
        "openai",
        BLOC["model"],
        SCALEWAY,
    )
    assert llm.reasoning_effort == "low"
    assert llm.api_key == "vraie-cle-scaleway"


def test_les_deux_chemins_resolvent_avant_de_construire_le_greffier():
    from api.services.pipecat import run_pipeline
    from api.services.workflow import text_chat_runner

    for module in (run_pipeline, text_chat_runner):
        source = inspect.getsource(module)
        assert (
            "await resoudre_le_bloc_du_greffier(run_configs, workflow.organization_id)"
            in source
        )
    assert hasattr(module_greffier, "resoudre_le_bloc_du_greffier")
