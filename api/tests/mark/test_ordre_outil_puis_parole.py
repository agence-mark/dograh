"""[.mark] Une parole de l'appelant ne suit jamais directement un résultat d'outil dans la requête envoyée.

La question de ce fichier, et elle seule :

    Quand la réponse qui a appelé un outil avait parlé (« Je regarde les disponibilités. » puis
    ``confier_le_travail``) et que l'outil a rendu tout de suite, la requête suivante (réplique de l'appelant, ou
    résultat du fond remis seul) replace-t-elle cette phrase juste après le résultat de l'outil -- sans jamais toucher
    l'historique ?

Pourquoi
--------
Run 1469 (20/10/2026, groupe v4 small, Small 3.2 chez Scaleway) : depuis R15 l'historique finit par le résultat
« lancé » ; la parole suivante est un ``user`` ; Scaleway répond 400 « Unexpected role 'user' after role 'tool' » et
l'appel s'arrête. La requête rejouée avec la phrase après le résultat de l'outil est acceptée.
"""

import copy
from itertools import pairwise
from types import SimpleNamespace

from api.services.configuration.registry import MistralLLMConfiguration
from api.services.configuration.registry import OpenAILLMService as OpenAIConfig
from api.services.pipecat.ordre_outil_puis_parole import (
    remettre_la_parole_apres_l_outil,
)
from api.services.pipecat.service_factory import create_llm_service

APPEL = {
    "role": "assistant",
    "tool_calls": [
        {
            "id": "MKRh6Vsm0",
            "type": "function",
            "function": {"name": "confier_le_travail", "arguments": "{\"demande\": \"chercher deux dates\"}"},
        }
    ],
}
LANCE = {"role": "tool", "content": "{\"statut\": \"lancé\"}", "tool_call_id": "MKRh6Vsm0"}
PHRASE = {"role": "assistant", "content": "Je regarde les disponibilités."}
RESULTAT = {"role": "user", "content": "[Résultat du travail : jeudi 22 octobre ou lundi 26 octobre.]"}
FICHE = {"role": "user", "content": "[Fiche de l'appel : pour toi seulement.]"}
DACCORD = {"role": "user", "content": "D'accord."}
DEBUT = [
    {"role": "system", "content": "# Qui tu es"},
    {"role": "assistant", "content": "Quelle est votre adresse, avec la commune et le code postal ?"},
    {"role": "user", "content": "1 rue de l'Essai à Testville, 99999."},
]

# La suite exacte du tour refusé du run 1469 (valeurs personnelles remplacées).
RUN_1469 = [*DEBUT, PHRASE, APPEL, LANCE, RESULTAT, FICHE, DACCORD]


def _roles(messages):
    return [m["role"] for m in messages]


def _jamais_user_apres_tool(messages):
    return all(
        not (a["role"] == "tool" and b["role"] == "user") for a, b in pairwise(messages)
    )


def test_le_tour_refuse_du_1469_est_remis_en_ordre():
    sortie = remettre_la_parole_apres_l_outil(RUN_1469)
    assert _jamais_user_apres_tool(sortie)
    assert sortie[3:7] == [APPEL, LANCE, PHRASE, RESULTAT]
    assert sortie[-2:] == [FICHE, DACCORD]
    assert len(sortie) == len(RUN_1469)


def test_l_appelant_se_tait_le_resultat_arrive_seul():
    sortie = remettre_la_parole_apres_l_outil([*DEBUT, PHRASE, APPEL, LANCE, RESULTAT])
    assert _roles(sortie)[-4:] == ["assistant", "tool", "assistant", "user"]
    assert sortie[-2] == PHRASE and sortie[-1] == RESULTAT


def test_la_parole_dans_le_meme_message_que_l_appel_sort_apres_le_resultat():
    appel_avec_parole = {**APPEL, "content": "Je regarde les disponibilités."}
    sortie = remettre_la_parole_apres_l_outil([*DEBUT, appel_avec_parole, LANCE, DACCORD])
    assert sortie[-4]["content"] is None and sortie[-4]["tool_calls"] == APPEL["tool_calls"]
    assert sortie[-2] == {"role": "assistant", "content": "Je regarde les disponibilités."}
    assert _jamais_user_apres_tool(sortie)


def test_sans_phrase_dite_rien_ne_change():
    messages = [*DEBUT, APPEL, LANCE, DACCORD]
    assert remettre_la_parole_apres_l_outil(messages) == messages


def test_un_outil_suivi_de_l_assistant_reste_tel_quel():
    messages = [*DEBUT, PHRASE, APPEL, LANCE, {"role": "assistant", "content": "Voilà."}, DACCORD]
    assert remettre_la_parole_apres_l_outil(messages) == messages


def test_l_historique_n_est_jamais_modifie():
    original = copy.deepcopy(RUN_1469)
    remettre_la_parole_apres_l_outil(RUN_1469)
    appel_avec_parole = {**APPEL, "content": "Je regarde."}
    liste = [*DEBUT, appel_avec_parole, LANCE, DACCORD]
    remettre_la_parole_apres_l_outil(liste)
    assert RUN_1469 == original
    assert appel_avec_parole["content"] == "Je regarde."


def _contexte():
    return {"messages": copy.deepcopy(RUN_1469), "tools": [], "tool_choice": None}


def test_r1_la_requete_du_service_scaleway_sort_en_ordre():
    """R1 : par la vraie fabrique, comme les deux exécutants (téléphone et clavier) construisent le service."""
    config = SimpleNamespace(
        llm=OpenAIConfig(
            api_key="cle-de-test-jamais-envoyee",
            model="mistral-small-3.2-24b-instruct-2506",
            base_url="https://api.scaleway.ai/v1",
        )
    )
    params = create_llm_service(config).build_chat_completion_params(_contexte())
    assert _jamais_user_apres_tool(params["messages"])


def test_r1_la_requete_du_service_mistral_sort_en_ordre():
    config = SimpleNamespace(
        llm=MistralLLMConfiguration(api_key="cle-de-test-jamais-envoyee", model="mistral-small-2506")
    )
    params = create_llm_service(config).build_chat_completion_params(_contexte())
    assert _jamais_user_apres_tool(params["messages"])
