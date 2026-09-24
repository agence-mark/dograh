"""[.mark] Lot 6 du plan « la fiche au fil de l'eau » : montrer la fiche au modèle.

La question à laquelle ce fichier répond, et elle seule :

    À chaque requête de conversation, le modèle voit-il ce qu'il a déjà noté,
    sans que le prompt système ni l'historique ne changent ?

| # | Ce qu'il prouve |
|---|---|
| T6.1 | L'état montré reflète la fiche **au tour en cours** |
| T6.2 | Le prompt système **n'est pas modifié**, l'historique non plus |
| D43 | L'état est placé **juste avant la dernière parole de l'appelant** |
| A7 | L'état ne liste **jamais ce qui manque** (run 835 : une liste de questions) |
| A8 | Un numéro de la fiche qui diffère du **dernier numéro dicté** est signalé (run 837) |

Les requêtes sont celles qui PARTENT : le vrai service Mistral du fork, son
adaptateur de messages, le client intercepté au dernier moment. T6.3 (la part
de jetons servie par le cache) se mesure sur des appels réels, pas ici.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.services.mistral.llm import MistralLLMSettings

from api.services.pipecat.service_factory import DograhMistralLLMService
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    ENTETE_ETAT,
    ReglagesFiche,
    ecrire_dans_la_fiche,
    etat_de_la_fiche,
    inserer_l_etat,
    montrer_la_fiche,
    numeros_en_conflit,
)
from api.services.workflow.pipecat_engine import PipecatEngine
from api.tests.mark.test_outil_noter import CONFIG_ALLUMEE

PROMPT = "Tu es l'assistant téléphonique du magasin."
PAROLE = "Je m'appelle Dupont, j'habite à Creil."


def _reglages() -> ReglagesFiche:
    reglages = ReglagesFiche.depuis(CONFIG_ALLUMEE)
    assert reglages is not None
    return reglages


def _mistral() -> DograhMistralLLMService:
    return DograhMistralLLMService(
        api_key="cle-de-test-jamais-envoyee",
        settings=MistralLLMSettings(model="mistral-large-2512"),
        prompt_cache_key="mark-wf-25",
    )


def _contexte(*messages: dict) -> LLMContext:
    context = LLMContext()
    for message in [{"role": "system", "content": PROMPT}, *messages]:
        context.add_message(message)
    return context


async def _requete(llm, context: LLMContext) -> list[dict]:
    """Les messages de la requête qui part, interceptée chez le client."""
    with patch.object(
        llm._client.chat.completions, "create", new=AsyncMock(return_value=object())
    ) as envoi:
        await llm.get_chat_completions(context)
    return envoi.call_args.kwargs["messages"]


def _moteur(workflow, llm, context, fiche=None) -> PipecatEngine:
    return PipecatEngine(
        llm=llm,
        context=context,
        workflow=workflow,
        call_context_vars={},
        workflow_run_id=1,
        fiche=fiche,
    )


# --- Ce que le modèle lit ----------------------------------------------------


def test_etat_noté_et_à_confirmer_dans_l_ordre_de_la_fiche():
    fiche = {
        "nom": "Dupont",
        "commune": "Creil",
        "motif": "panne",
        CLE_ETAT: {
            "nom": {"sure": True, "source": "outil"},
            "commune": {"sure": False, "source": "outil"},
            "motif": {"sure": True, "source": "outil"},
        },
    }
    assert etat_de_la_fiche(_reglages(), fiche).splitlines() == [
        ENTETE_ETAT,
        "Noté : nom = « Dupont » ; motif = « panne »",
        "À confirmer : commune = « Creil »",
    ]


def test_A7_rien_de_note_rien_a_montrer_et_jamais_ce_qui_manque():
    assert etat_de_la_fiche(_reglages(), {}) is None
    etat = etat_de_la_fiche(
        _reglages(), {"nom": "Dupont", CLE_ETAT: {"nom": {"sure": True}}}
    )
    assert "Manque" not in etat and "telephone" not in etat


def test_une_valeur_sans_etat_n_est_pas_dite_sure():
    # Une valeur venue d'ailleurs que la fiche (aucun état) : à confirmer.
    assert "À confirmer : nom = « Dupont »" in etat_de_la_fiche(
        _reglages(), {"nom": "Dupont"}
    )


def test_une_longue_valeur_est_abregee():
    lignes = etat_de_la_fiche(
        _reglages(), {"motif": "mot " * 100, CLE_ETAT: {"motif": {"sure": True}}}
    )
    (ligne,) = [ligne for ligne in lignes.splitlines() if ligne.startswith("Noté")]
    assert ligne.endswith("… »") and len(ligne) < 160


# --- D43 : où l'état se place ------------------------------------------------


def test_D43_juste_avant_la_derniere_parole_dans_une_copie():
    messages = [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "Bonjour, je vous écoute."},
        {"role": "user", "content": PAROLE},
    ]
    avant = [dict(m) for m in messages]
    envoyes = inserer_l_etat(messages, "ETAT")
    assert envoyes[-2] == {"role": "user", "content": "ETAT"}
    assert envoyes[-1]["content"] == PAROLE
    assert messages == avant


def test_D43_a_l_accueil_sans_parole_rien_n_est_ajoute():
    messages = [{"role": "system", "content": PROMPT}]
    assert inserer_l_etat(messages, "ETAT") == messages


# --- T6.1 et T6.2, sur la requête qui part -----------------------------------


@pytest.mark.asyncio
async def test_T6_1_T6_2_l_etat_suit_la_fiche_le_prompt_et_l_historique_intacts(
    three_node_workflow,
):
    llm = _mistral()
    context = _contexte(
        {"role": "assistant", "content": "Bonjour, je vous écoute."},
        {"role": "user", "content": PAROLE},
    )
    engine = _moteur(three_node_workflow, llm, context, _reglages())

    # Rien de noté : rien d'ajouté (A7).
    envoyes = await _requete(llm, context)
    assert envoyes == [
        {"role": "system", "content": PROMPT},
        {"role": "assistant", "content": "Bonjour, je vous écoute."},
        {"role": "user", "content": PAROLE},
    ]

    # Le modèle note : la requête suivante montre la fiche de CE tour (T6.1).
    ecrire_dans_la_fiche(
        engine._gathered_context, _reglages(), "nom", "Dupont", paroles=[PAROLE]
    )
    envoyes = await _requete(llm, context)
    assert envoyes[0] == {"role": "system", "content": PROMPT}  # T6.2
    assert envoyes[-1]["content"] == PAROLE  # D43
    assert envoyes[-2]["content"].startswith(ENTETE_ETAT)
    assert "Noté : nom = « Dupont »" in envoyes[-2]["content"]

    # T6.2 : rien n'est entré dans l'historique, ni dans le prompt système.
    assert context.get_messages() == [
        {"role": "system", "content": PROMPT},
        {"role": "assistant", "content": "Bonjour, je vous écoute."},
        {"role": "user", "content": PAROLE},
    ]
    assert envoyes[0] == {"role": "system", "content": PROMPT}


@pytest.mark.asyncio
async def test_D43_apres_une_note_le_modele_continue_sa_reponse(three_node_workflow):
    """Après le résultat de l'outil, Mistral reprend la réponse de l'agent : l'état
    se place avant la parole de l'appelant, jamais entre l'outil et la reprise."""
    llm = _mistral()
    appel = {
        "id": "n1",
        "type": "function",
        "function": {"name": "noter_information", "arguments": '{"nom": "Dupont"}'},
    }
    context = _contexte(
        {"role": "user", "content": PAROLE},
        {"role": "assistant", "content": None, "tool_calls": [appel]},
        {"role": "tool", "tool_call_id": "n1", "content": '{"statut": "note"}'},
    )
    engine = _moteur(three_node_workflow, llm, context, _reglages())
    ecrire_dans_la_fiche(
        engine._gathered_context, _reglages(), "nom", "Dupont", paroles=[PAROLE]
    )
    envoyes = await _requete(llm, context)
    roles = [m["role"] for m in envoyes]
    assert roles == ["system", "user", "user", "assistant", "tool", "assistant"]
    assert envoyes[1]["content"].startswith(ENTETE_ETAT)
    assert envoyes[-1].get("prefix") is True


@pytest.mark.asyncio
async def test_les_relectures_hors_conversation_ne_voient_pas_l_etat(
    three_node_workflow,
):
    """Le balayage et l'extraction passent par le même objet et le même
    constructeur de requête : ils restent inchangés."""
    llm = _mistral()
    context = _contexte({"role": "user", "content": PAROLE})
    engine = _moteur(three_node_workflow, llm, context, _reglages())
    ecrire_dans_la_fiche(
        engine._gathered_context, _reglages(), "nom", "Dupont", paroles=[PAROLE]
    )
    reponse = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
    )
    with patch.object(
        llm._client.chat.completions, "create", new=AsyncMock(return_value=reponse)
    ) as envoi:
        await llm.run_inference(context, system_instruction="Extrais.")
    contenus = [m.get("content") for m in envoi.call_args.kwargs["messages"]]
    assert not any(ENTETE_ETAT in (c or "") for c in contenus)


@pytest.mark.asyncio
async def test_D12_eteint_la_requete_est_inchangee(three_node_workflow):
    llm = _mistral()
    context = _contexte({"role": "user", "content": PAROLE})
    _moteur(three_node_workflow, llm, context, fiche=None)
    assert "get_chat_completions" not in vars(llm)
    envoyes = await _requete(llm, context)
    assert envoyes == [
        {"role": "system", "content": PROMPT},
        {"role": "user", "content": PAROLE},
    ]


def test_un_service_sans_requete_de_conversation_n_est_pas_touche():
    llm = SimpleNamespace(run_inference=None)
    assert montrer_la_fiche(llm, _reglages(), dict) is False
    assert vars(llm) == {"run_inference": None}


# --- A8 : le numéro corrigé que le modèle n'a pas noté (run 837) ------------

# Les traces du module des nombres au run 837, telles qu'enregistrées.
TRACES_837 = [
    {"etape": "qualif_entretien", "type": "autre", "ecrit": "2025"},
    {"etape": "nom_et_rappel", "type": "telephone", "ecrit": "06 12 34 56 68"},
    {"etape": "nom_et_rappel", "type": "telephone", "ecrit": "06 12 34 56 78"},
    {"etape": "adresse", "type": "code_postal", "ecrit": "60700"},
]


def test_A8_run_837_le_numero_corrige_non_note_est_signale():
    fiche = {
        "telephone": "0612345668",
        CLE_ETAT: {"telephone": {"sure": True}},
        "nombres_lus": TRACES_837,
    }
    assert numeros_en_conflit(_reglages(), fiche) == [("telephone", "0612345678")]
    etat = etat_de_la_fiche(_reglages(), fiche)
    assert "le dernier numéro dicté par la personne est 06 12 34 56 78" in etat
    assert "Si c'est une correction, note le nouveau numéro." in etat


def test_A8_numero_note_a_jour_rien_a_signaler():
    fiche = {
        "telephone": "0612345678",
        CLE_ETAT: {"telephone": {"sure": True}},
        "nombres_lus": TRACES_837,
    }
    assert numeros_en_conflit(_reglages(), fiche) == []
    assert "Attention" not in etat_de_la_fiche(_reglages(), fiche)
