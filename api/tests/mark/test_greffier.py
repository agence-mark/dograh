"""[.mark] Le greffier (plan mode-prise-de-notes, partie 2, lots 10 et 11).

Plan `Labo-agent-vocal/plans/mode-prise-de-notes/`, D8 à D10. Chaque test a été vu ROUGE avant
d'être vert (R7).

| Test | Ce qu'il prouve |
|---|---|
| requête | par le client du fournisseur : JSON demandé, consigne + champs + fiche + conversation, jetons relevés |
| repli | un service sans ce client passe par `run_inference` |
| écrit | seuls les champs nouveaux ou changés passent par `noter`, source « greffier » au journal |
| vrais modules | une commune écrite par le greffier passe par le module des communes ; les notices suivent |
| une en vol | trois demandes pendant une passe = une seule passe de plus, sur la dernière conversation |
| 429 | rien ne casse, la passe est sautée et tracée, la suivante écrit |
| échec, illisible | tracés, jamais d'exception |
| lent | le déclencheur laisse passer les frames sans attendre la passe |
| après l'agent | une passe part à la fin de la réponse de l'agent, jamais avant (D9) |
| consigne | générique par défaut, sans un mot de métier ; celle de l'agent la remplace ; champs et format toujours ajoutés |
| service | modèle par défaut Large chez Mistral, bloc appliqué comme une surcharge, clé vide = celle de la conversation |
| repli outil | un service qui ne se construit pas fait jouer l'appel en mode outil ; l'estampille ne porte jamais la clé |
| moteur | la fabrique, jouée sur un vrai moteur ; hors mode greffier, rien |
"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.tests.utils import SleepFrame

from api.services.pipecat import greffier as module
from api.services.pipecat.greffier import (
    CLE_ESTAMPILLE,
    CONSIGNE_GENERIQUE,
    ECHEC,
    ECRIT,
    ILLISIBLE,
    MODELE_PAR_DEFAUT_MISTRAL,
    RIEN,
    SAUTE,
    TARDIVE,
    TRACE_GREFFIER,
    DeclencheurDuGreffier,
    Greffier,
    champs_a_noter,
    configuration_du_greffier,
    consigne_du_greffier,
    greffier_du_moteur,
    interroger,
    message_du_greffier,
    preparer_le_greffier,
)
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_JOURNAL,
    CLE_MODE,
    DELAI_DES_NOTES_EN_COURS,
    DELAI_DU_GREFFIER,
    MODE_GREFFIER,
    MODE_OUTIL,
    MODE_POST_SCRIPTUM,
    Notices,
    ReglagesFiche,
    attendre_les_notes,
    delai_des_notes,
)
from api.tests.mark.test_modules_derriere_outil import (  # noqa: F401 -- fixture
    REGLAGES,
    _appel,
    index_de_test,
)
from api.tests.mark.test_post_scriptum import DEMARRAGE_S, FICHE_SIMPLE, PAROLE, _Aval
from pipecat.tests import run_test

FICHE_GREFFIER = {**FICHE_SIMPLE, CLE_MODE: MODE_GREFFIER}


class _Modele:
    """Un modèle de greffier sans client de fournisseur : `run_inference` seul.
    Rend les réponses dans l'ordre ; une exception est levée telle quelle."""

    def __init__(self, *reponses, delai: float = 0.0):
        self.reponses = list(reponses)
        self.delai = delai
        self.lus: list[str] = []

    async def run_inference(self, contexte, system_instruction=None):
        self.lus.append(contexte.get_messages()[-1]["content"])
        await asyncio.sleep(self.delai)
        reponse = self.reponses.pop(0) if self.reponses else "{}"
        if isinstance(reponse, BaseException):
            raise reponse
        return reponse if isinstance(reponse, str) else json.dumps(reponse)


class _Montage:
    def __init__(
        self, modele, config: dict = FICHE_GREFFIER, fiche: dict | None = None
    ):
        self.reglages = ReglagesFiche.depuis(config)
        self.fiche: dict = fiche if fiche is not None else {}
        self.messages = [{"role": "user", "content": PAROLE}]
        self.notices = Notices()
        self.notes: set[asyncio.Task] = set()
        self.greffier = Greffier(
            service=modele,
            reglages=self.reglages,
            fiche=lambda: self.fiche,
            messages=lambda: self.messages,
            notices=self.notices,
            notes_en_cours=self.notes,
        )

    async def passe(self):
        self.greffier.declencher()
        await attendre_les_notes(self.notes, delai=5)

    @property
    def traces(self) -> list[dict]:
        return self.fiche.get(TRACE_GREFFIER) or []


# --------------------------------------------------------------------------- #
# 1. La requête
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_requete_passe_par_le_client_en_json_et_releve_les_jetons():
    from api.tests.mark.test_fiche_montree import _mistral

    service = _mistral()
    reponse = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"nom": "Dupont"}'))],
        usage=SimpleNamespace(prompt_tokens=812, completion_tokens=9),
    )
    with patch.object(
        service._client.chat.completions, "create", new=AsyncMock(return_value=reponse)
    ) as envoi:
        texte, jetons = await interroger(service, "CONSIGNE", "MESSAGE")
    assert texte == '{"nom": "Dupont"}'
    assert jetons == {"jetons_entree": 812, "jetons_sortie": 9}
    params = envoi.call_args.kwargs
    assert params["response_format"] == {"type": "json_object"}
    assert params["stream"] is False
    assert "stream_options" not in params
    assert params["model"] == "mistral-large-2512"
    assert params["messages"][0] == {"role": "system", "content": "CONSIGNE"}
    assert params["messages"][-1] == {"role": "user", "content": "MESSAGE"}


@pytest.mark.asyncio
async def test_sans_client_de_fournisseur_run_inference_en_repli():
    modele = _Modele({"nom": "Dupont"})
    texte, jetons = await interroger(modele, "CONSIGNE", "MESSAGE")
    assert json.loads(texte) == {"nom": "Dupont"}
    assert jetons == {}
    assert modele.lus == ["MESSAGE"]


def test_le_message_porte_la_fiche_la_conversation_et_la_derniere_replique():
    reglages = ReglagesFiche.depuis(FICHE_GREFFIER)
    fiche = {"nom": "Dupont", "fiche_etat": {"nom": {"sure": True}}}
    message = message_du_greffier(
        reglages,
        fiche,
        [
            {"role": "system", "content": "PROMPT DE L'AGENT"},
            {"role": "assistant", "content": "Bonjour, à quel nom ?"},
            {"role": "user", "content": PAROLE},
            {"role": "tool", "content": "ignoré"},
        ],
    )
    assert '- nom = "Dupont"' in message
    assert "(à confirmer)" not in message
    assert "1. Agent : Bonjour, à quel nom ?" in message
    assert f"2. Personne : {PAROLE}" in message
    assert message.rstrip().endswith(PAROLE)
    assert "PROMPT DE L'AGENT" not in message and "ignoré" not in message


# --------------------------------------------------------------------------- #
# 2. Ce qui s'écrit
# --------------------------------------------------------------------------- #


def test_seuls_les_champs_nouveaux_ou_changes_sont_notes():
    reglages = ReglagesFiche.depuis(FICHE_GREFFIER)
    assert champs_a_noter(
        reglages,
        {"nom": "Dupont"},
        {"nom": "Dupont", "motif": "entretien", "inconnu": "x", "autre": ""},
    ) == {"motif": "entretien"}


@pytest.mark.asyncio
async def test_une_passe_ecrit_par_noter_avec_la_source_greffier():
    montage = _Montage(_Modele({"nom": "Dupont", "motif": "un entretien"}))
    await montage.passe()
    assert montage.fiche["nom"] == "Dupont"
    assert montage.fiche["motif"] == "un entretien"
    assert {e["source"] for e in montage.fiche[CLE_JOURNAL]} == {MODE_GREFFIER}
    assert montage.traces[-1]["etat"] == ECRIT
    assert montage.traces[-1]["champs"] == ["motif", "nom"]


@pytest.mark.asyncio
async def test_une_fiche_recopiee_telle_quelle_n_ecrit_rien_et_efface_les_notices():
    montage = _Montage(_Modele({"nom": "Dupont"}, {"nom": "Dupont"}))
    await montage.passe()
    journal = len(montage.fiche[CLE_JOURNAL])
    await montage.passe()
    assert len(montage.fiche[CLE_JOURNAL]) == journal
    assert [t["etat"] for t in montage.traces] == [ECRIT, RIEN]
    assert montage.notices.derniere is None


@pytest.mark.asyncio
async def test_le_greffier_passe_par_les_vrais_modules_et_ses_notices_suivent():
    fiche, _ = await _appel("c'est à creil 60100")
    montage = _Montage(
        _Modele({"commune": "creil"}, {"commune": "Creil", "nom": "Martin"}),
        {**REGLAGES, CLE_MODE: MODE_GREFFIER},
        fiche=fiche,
    )
    montage.messages = [{"role": "user", "content": "c'est à creil 60100"}]
    await montage.passe()
    assert montage.fiche["commune"] == "Creil"
    assert montage.fiche["commune_insee"] == "60175"
    assert montage.fiche["fiche_etat"]["commune"] == {
        "sure": True,
        "source": MODE_GREFFIER,
    }
    # Une valeur jamais dite : refusée, comme avec l'outil.
    await montage.passe()
    assert "nom" not in montage.fiche
    assert montage.greffier._refus == [{"champ": "nom", "raison": "non_dit"}]


@pytest.mark.asyncio
async def test_les_refus_vont_au_greffier_jamais_a_l_agent():
    """L'agent n'a rien noté : une consigne de rédacteur (« note ses mots
    exacts ») l'égarerait. Le greffier, lui, lit son refus à la passe suivante."""
    modele = _Modele({"nom": "Martin"}, {"nom": "Martin"}, {})
    montage = _Montage(modele)
    await montage.passe()
    assert "nom" not in montage.fiche
    derniere = montage.notices.derniere or {}
    assert "refuses" not in derniere
    assert "Note ses mots exacts" not in derniere.get("consigne", "")
    assert "Refusé" not in modele.lus[0]
    await montage.passe()
    assert "# Refusé à ta passe précédente" in modele.lus[1]
    assert "- nom : pas dit tel quel par la personne" in modele.lus[1]
    # La passe 3 lit encore le refus de la passe 2, n'écrit rien : la liste se
    # vide, la passe 4 ne lit plus de refus.
    await montage.passe()
    assert "# Refusé à ta passe précédente" in modele.lus[2]
    await montage.passe()
    assert "Refusé" not in modele.lus[3]


def test_l_etat_de_la_fiche_dit_que_la_note_est_celle_du_greffier():
    from api.services.workflow.fiche_au_fil_de_leau import (
        Note,
        etat_de_la_fiche,
    )

    notices = Notices()
    notices.retenir(Note(ecrits=["nom"], a_confirmer=[{"champ": "nom"}]))
    greffier = etat_de_la_fiche(
        ReglagesFiche.depuis(FICHE_GREFFIER), {"nom": "Dupont"}, notices
    )
    post_scriptum = etat_de_la_fiche(
        ReglagesFiche.depuis(FICHE_SIMPLE), {"nom": "Dupont"}, notices
    )
    assert "Retour de la dernière note du greffier : " in greffier
    assert "Retour de ta dernière note : " in post_scriptum


# --------------------------------------------------------------------------- #
# 3. Le déclenchement (lot 11)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_une_seule_passe_en_vol_la_plus_recente_gagne():
    modele = _Modele(
        {"nom": "Dupont"}, {"nom": "Dupont", "motif": "un entretien"}, delai=0.2
    )
    montage = _Montage(modele)
    montage.greffier.declencher()
    await asyncio.sleep(0.05)
    montage.messages = [
        *montage.messages,
        {"role": "user", "content": "je rappelle demain matin"},
    ]
    montage.greffier.declencher()
    montage.greffier.declencher()
    montage.greffier.declencher()
    await attendre_les_notes(montage.notes, delai=5)
    # Deux passes, pas quatre : la seconde lit la conversation la plus récente.
    assert len(modele.lus) == 2
    assert "je rappelle demain matin" in modele.lus[1]
    assert "je rappelle demain matin" not in modele.lus[0]
    assert montage.fiche["motif"] == "un entretien"


class _Erreur429(Exception):
    status_code = 429


@pytest.mark.asyncio
async def test_un_429_saute_la_passe_et_la_suivante_ecrit():
    montage = _Montage(_Modele(_Erreur429("Too Many Requests"), {"nom": "Dupont"}))
    await montage.passe()
    assert "nom" not in montage.fiche
    assert montage.traces[-1]["etat"] == SAUTE
    await montage.passe()
    assert montage.fiche["nom"] == "Dupont"
    assert [t["etat"] for t in montage.traces] == [SAUTE, ECRIT]


@pytest.mark.asyncio
async def test_un_echec_et_une_reponse_illisible_sont_traces_sans_exception():
    montage = _Montage(_Modele(RuntimeError("panne"), "pas du json"))
    await montage.passe()
    await montage.passe()
    assert [t["etat"] for t in montage.traces] == [ECHEC, ILLISIBLE]
    assert montage.traces[0]["erreur"] == "RuntimeError"


@pytest.mark.asyncio
async def test_une_passe_trop_longue_est_abandonnee_et_tracee():
    montage = _Montage(_Modele({"nom": "Dupont"}, delai=1.0))
    montage.greffier._delai = 0.1
    await montage.passe()
    assert "nom" not in montage.fiche
    assert montage.traces[-1]["etat"] == ECHEC


@pytest.mark.asyncio
async def test_le_declencheur_part_apres_la_reponse_de_l_agent_et_ne_l_attend_pas():
    modele = _Modele({"nom": "Dupont"}, delai=0.5)
    montage = _Montage(modele)
    aval = _Aval()
    await run_test(
        Pipeline([DeclencheurDuGreffier(montage.greffier), aval]),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            LLMTextFrame("Très bien, et votre numéro ?"),
            SleepFrame(sleep=0.1),
        ],
        start_timeout=DEMARRAGE_S,
    )
    # Pas de fin de réponse : pas de passe (D9, jamais avant l'agent).
    assert modele.lus == []
    await run_test(
        Pipeline([DeclencheurDuGreffier(montage.greffier), aval]),
        frames_to_send=[LLMFullResponseEndFrame(), SleepFrame(sleep=0.05)],
        start_timeout=DEMARRAGE_S,
    )
    # La phrase est passée sans attendre la passe, qui est encore en vol.
    assert aval.textes == ["Très bien, et votre numéro ?"]
    assert "nom" not in montage.fiche
    await attendre_les_notes(montage.notes, delai=5)
    assert montage.fiche["nom"] == "Dupont"


def test_le_greffier_a_droit_a_un_delai_plus_long_en_fin_d_appel():
    assert delai_des_notes(ReglagesFiche.depuis(FICHE_GREFFIER)) == DELAI_DU_GREFFIER
    assert (
        delai_des_notes(ReglagesFiche.depuis(FICHE_SIMPLE)) == DELAI_DES_NOTES_EN_COURS
    )
    assert delai_des_notes(None) == DELAI_DES_NOTES_EN_COURS


# --------------------------------------------------------------------------- #
# 4. La consigne (D10)
# --------------------------------------------------------------------------- #


def test_la_consigne_generique_par_defaut_puis_les_champs_et_le_format():
    reglages = ReglagesFiche.depuis(FICHE_GREFFIER)
    consigne = consigne_du_greffier(reglages, None)
    assert consigne.startswith(CONSIGNE_GENERIQUE.rstrip())
    assert "- nom : Nom de famille" in consigne
    assert "Un seul objet JSON" in consigne
    assert consigne_du_greffier(reglages, "   ") == consigne


def test_la_consigne_de_l_agent_remplace_la_generique_pas_les_champs():
    reglages = ReglagesFiche.depuis(FICHE_GREFFIER)
    consigne = consigne_du_greffier(reglages, "Tu tiens la fiche d'un cabinet.")
    assert consigne.startswith("Tu tiens la fiche d'un cabinet.")
    assert CONSIGNE_GENERIQUE[:40] not in consigne
    assert "- motif : Ce que la personne demande" in consigne
    assert "Un seul objet JSON" in consigne


# --------------------------------------------------------------------------- #
# 5. Le service, l'estampille, le repli
# --------------------------------------------------------------------------- #


def _conversation(provider="mistral", model="mistral-small-2603"):
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration

    return EffectiveAIModelConfiguration.model_validate(
        {
            "llm": {
                "provider": provider,
                "model": model,
                "api_key": "cle-de-la-conversation-de-test",
            }
        }
    )


def test_sans_modele_le_greffier_prend_large_chez_mistral_et_la_cle_de_la_conversation():
    configuration = configuration_du_greffier(_conversation(), None)
    assert configuration.llm.model == MODELE_PAR_DEFAUT_MISTRAL
    assert configuration.llm.api_key == "cle-de-la-conversation-de-test"


def test_le_bloc_s_applique_comme_une_surcharge():
    configuration = configuration_du_greffier(
        _conversation(),
        {
            "model": "mistral-small-2603",
            "api_key": "cle-propre-au-greffier",
            "temperature": 0.1,
        },
    )
    assert configuration.llm.model == "mistral-small-2603"
    assert configuration.llm.api_key == "cle-propre-au-greffier"
    assert configuration.llm.temperature == 0.1
    # une clé vide ne remplace pas celle de la conversation
    vide = configuration_du_greffier(_conversation(), {"api_key": ""})
    assert vide.llm.api_key == "cle-de-la-conversation-de-test"


def test_l_estampille_dit_le_modele_jamais_la_cle():
    runtime: dict = {}
    reglages, service = preparer_le_greffier(
        ReglagesFiche.depuis(FICHE_GREFFIER),
        {"greffier_llm": {"api_key": "cle-propre-au-greffier"}},
        _conversation(),
        runtime,
    )
    assert reglages.mode == MODE_GREFFIER
    assert service is not None
    assert runtime[CLE_ESTAMPILLE] == {
        "provider": "mistral",
        "model": MODELE_PAR_DEFAUT_MISTRAL,
    }
    assert "cle-" not in json.dumps(runtime)


def test_un_service_impossible_fait_jouer_l_appel_en_mode_outil():
    runtime: dict = {}
    with patch.object(
        module, "service_du_greffier", side_effect=ValueError("cle-secrete")
    ):
        reglages, service = preparer_le_greffier(
            ReglagesFiche.depuis(FICHE_GREFFIER), {}, _conversation(), runtime
        )
    assert reglages.mode == MODE_OUTIL
    assert service is None
    assert CLE_ESTAMPILLE not in runtime


@pytest.mark.parametrize("mode", [MODE_OUTIL, MODE_POST_SCRIPTUM])
def test_hors_mode_greffier_rien(mode):
    runtime: dict = {}
    reglages, service = preparer_le_greffier(
        ReglagesFiche.depuis({**FICHE_SIMPLE, CLE_MODE: mode}),
        {},
        _conversation(),
        runtime,
    )
    assert reglages.mode == mode and service is None and runtime == {}
    assert preparer_le_greffier(None, {}, _conversation(), runtime) == (None, None)


# --------------------------------------------------------------------------- #
# 6. Sur un vrai moteur
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_la_fabrique_du_moteur_joue_ses_lectures(three_node_workflow):
    from api.services.workflow.pipecat_engine import PipecatEngine
    from api.tests.mark.test_fiche_montree import _contexte, _mistral

    engine = PipecatEngine(
        llm=_mistral(),
        context=_contexte({"role": "user", "content": PAROLE}),
        workflow=three_node_workflow,
        call_context_vars={},
        workflow_run_id=1,
        fiche=ReglagesFiche.depuis(FICHE_GREFFIER),
    )
    modele = _Modele({"nom": "Dupont", "motif": "Martin"})
    declencheur = greffier_du_moteur(engine, modele, None)
    assert isinstance(declencheur, DeclencheurDuGreffier)
    await run_test(
        Pipeline([declencheur, _Aval()]),
        frames_to_send=[LLMFullResponseEndFrame(), SleepFrame(sleep=0.05)],
        start_timeout=DEMARRAGE_S,
    )
    await attendre_les_notes(engine.notes_en_cours, delai=5)
    fiche = engine._gathered_context
    assert fiche["nom"] == "Dupont"  # dit dans la conversation lue par la fabrique
    assert "motif" not in fiche  # jamais dit : refusé, comme avec l'outil
    # Les notices du moteur sont celles du greffier : ce qu'il a écrit, sans ses refus.
    assert engine.notices_fiche.derniere == {"statut": "note", "ecrits": ["nom"]}
    assert PAROLE in modele.lus[0]
    outil = PipecatEngine(
        llm=_mistral(),
        context=_contexte(),
        workflow=three_node_workflow,
        call_context_vars={},
        workflow_run_id=1,
        fiche=ReglagesFiche.depuis(FICHE_SIMPLE),
    )
    assert greffier_du_moteur(outil, modele, None) is None
    assert greffier_du_moteur(engine, None, None) is None


# --------------------------------------------------------------------------- #
# 7. Corrections de la relecture indépendante du 04/10
# --------------------------------------------------------------------------- #


def test_les_reglages_de_generation_de_la_voix_ne_passent_pas_au_greffier():
    from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration

    conversation = EffectiveAIModelConfiguration.model_validate(
        {
            "llm": {
                "provider": "mistral",
                "model": "mistral-large-2512",
                "api_key": "cle-de-la-conversation-de-test",
                "temperature": 0.4,
                "max_tokens": 120,
                "frequency_penalty": 0.5,
            }
        }
    )
    greffier = configuration_du_greffier(conversation, None).llm
    defauts = type(greffier).model_fields
    assert greffier.max_tokens == defauts["max_tokens"].default
    assert greffier.frequency_penalty == defauts["frequency_penalty"].default
    assert greffier.temperature == 0.4  # à l'écran : « comme la conversation »
    assert conversation.llm.max_tokens == 120  # la conversation n'est pas touchée


@pytest.mark.asyncio
async def test_clos_aucune_passe_ne_part_ni_n_ecrit_apres_la_fin_de_l_appel():
    modele = _Modele({"nom": "Dupont"}, {"nom": "Dupont"}, delai=0.2)
    montage = _Montage(modele)
    montage.greffier.declencher()
    await asyncio.sleep(0.05)
    montage.greffier.declencher()  # gardée pour après la passe en vol
    montage.greffier.clore()
    await attendre_les_notes(montage.notes, delai=5)
    assert "nom" not in montage.fiche
    assert [t["etat"] for t in montage.traces] == [TARDIVE]
    assert len(modele.lus) == 1  # la demande gardée n'est pas rejouée
    montage.greffier.declencher()
    await attendre_les_notes(montage.notes, delai=5)
    assert len(modele.lus) == 1


@pytest.mark.asyncio
async def test_le_moteur_clot_le_greffier_a_la_passe_de_fin(three_node_workflow):
    from api.services.workflow.pipecat_engine import PipecatEngine
    from api.tests.mark.test_fiche_montree import _contexte, _mistral

    engine = PipecatEngine(
        llm=_mistral(),
        context=_contexte({"role": "user", "content": PAROLE}),
        workflow=three_node_workflow,
        call_context_vars={},
        workflow_run_id=1,
        fiche=ReglagesFiche.depuis(FICHE_GREFFIER),
    )
    assert engine.greffier is None
    greffier_du_moteur(engine, _Modele({}), None)
    assert engine.greffier is not None
    with patch(
        "api.services.workflow.pipecat_engine.balayer_la_fiche",
        new=AsyncMock(return_value={}),
    ):
        await engine._balayer_la_fiche()
    assert engine.greffier._clos is True
