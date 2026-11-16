"""[.mark] Défaut C1 : un résultat d'outil qui termine la conversation n'est jamais suivi d'un ``assistant`` « »
à ``prefix`` (Mistral serait forcé de continuer en texte et ne pourrait plus enchaîner un second outil).

Le ``tool`` suivi d'un ``user`` garde l'``assistant`` intercalé que Mistral exige.
"""

from api.services.pipecat.mistral_adapter_mark import MarkMistralLLMAdapter
from api.services.pipecat.service_factory import DograhMistralLLMService

APPEL = {
    "role": "assistant",
    "tool_calls": [{"id": "A1", "type": "function", "function": {"name": "choisir_mode", "arguments": "{}"}}],
}
RESULTAT = {"role": "tool", "content": "{\"ok\": true}", "tool_call_id": "A1"}


def _mettre_en_forme(messages):
    return MarkMistralLLMAdapter()._transform_messages(messages)


def test_un_outil_final_reste_le_dernier_message():
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "une regina"}, APPEL, RESULTAT]
    sortie = _mettre_en_forme(messages)
    assert [m["role"] for m in sortie] == ["system", "user", "assistant", "tool"]
    assert all("prefix" not in m for m in sortie)


def test_un_outil_suivi_de_l_appelant_garde_l_assistant_intercale():
    messages = [{"role": "system", "content": "s"}, APPEL, RESULTAT, {"role": "user", "content": "et un coca"}]
    sortie = _mettre_en_forme(messages)
    assert [m["role"] for m in sortie] == ["system", "assistant", "tool", "assistant", "user"]
    assert sortie[3] == {"role": "assistant", "content": " "}


def test_un_assistant_final_garde_son_prefix_et_le_system_tardif_devient_user():
    messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "a"},
                {"role": "system", "content": "note"}, {"role": "assistant", "content": "ok"}]
    sortie = _mettre_en_forme(messages)
    assert sortie[2]["role"] == "user"
    assert sortie[-1]["prefix"] is True


def test_le_service_mistral_de_dograh_utilise_l_adaptateur_corrige():
    assert DograhMistralLLMService.adapter_class is MarkMistralLLMAdapter
