"""[.mark] Clôture de la Partie 1, lot A6 (V3, V4 ; audit des rustines H2, H3) : le réglage du modèle de conversation vient du gabarit, jamais de la main.

Constat du lot 20 : ``reasoning_effort: none`` (sans lui Gemma 4 raisonne : 849 jetons par passe, passes de 6 à 20 s) n'était posé qu'à la main sur
l'organisation du chantier ; le prochain client installé ne l'aurait pas eu. Et deux températures pour une même mesure (0,1 au chantier, 0,5 au banc).
Forme : le gabarit porte une surcharge partielle du modèle (``model_overrides.llm``, température et effort de raisonnement, JAMAIS fournisseur ni clé),
posée sur chaque agent installé ; elle se fusionne sur la configuration du client (``resolve_effective_config``), sa clé et son fournisseur gardés.
"""

from __future__ import annotations

from api.services.configuration.registry import OpenAILLMService
from api.services.configuration.resolve import resolve_effective_config
from api.services.gabarits import gabarit as G

LLM = {"temperature": 0.1, "reasoning_effort": "none"}


def test_le_gabarit_porte_l_effort_et_une_seule_temperature():
    g = G.charger()
    surcharge = g.reglages["agent"]["model_overrides"]
    assert surcharge == {"llm": LLM}, surcharge
    assert g.reglages["modele"]["greffier_llm"]["temperature"] == LLM["temperature"], "une seule température : celle du greffier et celle de l'agent"
    assert not {"api_key", "provider", "base_url", "model"} & set(surcharge["llm"]), "jamais une clé ni un fournisseur dans le gabarit"


def test_la_surcharge_se_pose_sur_la_configuration_du_client_sans_toucher_sa_cle():
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration

    client = EffectiveAIModelConfiguration(
        llm=OpenAILLMService(api_key="cle-du-client", model="gemma-4-26b-a4b-it", base_url="https://api.scaleway.ai/v1", temperature=0.7),
    )
    effective = resolve_effective_config(client, G.charger().reglages["agent"]["model_overrides"])
    assert effective.llm.temperature == 0.1 and effective.llm.reasoning_effort == "none"
    assert effective.llm.api_key == "cle-du-client" and effective.llm.model == "gemma-4-26b-a4b-it"
    assert client.llm.temperature == 0.7, "la configuration du client n'est jamais modifiée"
