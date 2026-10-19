"""[.mark] Chantier fiabilite-orchestration, lot 5 (F7) : la relance de silence dite par la voix.

| Test | La garantie |
|---|---|
| phrase | règle allumée (défaut) : la phrase du motif « l'appelant se tait » part à la voix telle quelle, sans consigne au modèle, tracée |
| variantes | les relances successives tournent sur les variantes |
| éteinte | règle éteinte : la relance par le modèle d'avant (`user_idle_prompt`), au clavier aussi |
| au revoir | au-delà de `user_idle_max_prompts`, l'au revoir reste une consigne au modèle et l'appel raccroche |
| coupure | la phrase part micro ouvert (l'appelant la coupe), et le moniteur est déchargé de la réponse due |
| refus | un verrou du diseur refuse la phrase : rien n'est dit, la relance ne compte pas, le silence est de nouveau surveillé |
| délai | celui de la règle s'il est posé, sinon `max_user_idle_timeout` (Rythme) |
| travail | aucune relance (ni minuterie) pendant un travail de fond en cours |
| route | un vrai moteur : le moniteur lit le délai et la suspension du moteur |
"""

import asyncio
from types import SimpleNamespace

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests import MockLLMService

from api.schemas.workflow_configurations import (
    DEFAULT_USER_IDLE_GOODBYE_PROMPT,
    DEFAULT_USER_IDLE_PROMPT,
)
from api.services.phrases.catalogue import APPELANT_SE_TAIT
from api.services.phrases.diseur import CLE_TRACE, DiseurDePhrases
from api.services.pipecat.call_monitor_processor import CallMonitorProcessor
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.pipecat_engine_callbacks import (
    delai_de_la_relance,
    handle_user_idle,
    relance_suspendue,
)
from api.tests.mark.test_attente_parlee import _FauxMoteur


class _Agregateur:
    def __init__(self):
        self.consignes: list[str] = []

    async def push_frame(self, frame):
        for message in frame.messages:
            self.consignes.append(message["content"])


class _MoniteurSuivi:
    """Le moniteur vu du moteur : ce que la relance lui demande."""

    appelant_parle = False
    robot_parle = False
    agent_au_repos = True
    appel_au_calme = True

    def __init__(self):
        self.appels: list[bool] = []

    def relance_par_la_voix(self, *, dite):
        self.appels.append(dite)


class _Moteur(_FauxMoteur):
    def __init__(self, reglages_agent=None, relances=None):
        self.temps = [100.0]
        super().__init__(lambda: self.temps[0])
        self.call_monitor = _MoniteurSuivi()
        self.active_agent = SimpleNamespace(
            reglages=dict(reglages_agent or {}), current_node=None, workflow_id=7
        )
        self.reglages_relances = dict(relances or {})
        self.travaux: list = []
        self.sans_sortie_audio = False
        self.raccroche = None
        self.muets: list = []
        self.phrases = DiseurDePhrases(self, horloge=lambda: self.temps[0])

    async def queue_speech(self, texte, **options):
        self.muets.append(options.get("mute_user"))
        return await super().queue_speech(texte, **options)

    async def end_call_with_reason(self, raison):
        self.raccroche = raison


def _regle(variantes, delai_s=None, active=True):
    return {
        "motif": APPELANT_SE_TAIT,
        "portee": "agent",
        "variantes": variantes,
        "delai_s": delai_s,
        "active": active,
    }


async def _silence(moteur, tentative, agregateur=None):
    agregateur = agregateur or _Agregateur()
    await handle_user_idle(moteur, agregateur, tentative)
    await moteur.phrases.attendre_la_fin()
    return agregateur


# --- La phrase ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_la_phrase_fixe_part_a_la_voix_sans_consigne_au_modele():
    moteur = _Moteur()
    agregateur = await _silence(moteur, 1)
    assert moteur.dites == ["Êtes-vous toujours là ?"]
    assert agregateur.consignes == []  # le modèle n'est pas sollicité
    trace = moteur._gathered_context[CLE_TRACE]
    assert [t["motif"] for t in trace] == [APPELANT_SE_TAIT]
    assert moteur.call_monitor.appels == [True]


@pytest.mark.asyncio
async def test_la_phrase_de_la_regle_et_ses_variantes_tournent():
    moteur = _Moteur(
        {"phrases_regles": [_regle(["Vous êtes là ?", "Je vous entends plus."])]},
        relances={"user_idle_max_prompts": 3},
    )
    await _silence(moteur, 1)
    moteur.temps[0] += 10  # hors du repos
    await _silence(moteur, 2)
    assert moteur.dites == ["Vous êtes là ?", "Je vous entends plus."]


@pytest.mark.asyncio
async def test_regle_eteinte_la_relance_par_le_modele_d_avant():
    moteur = _Moteur({"phrases_regles": [_regle(["x"], active=False)]})
    agregateur = await _silence(moteur, 1)
    assert moteur.dites == []
    assert agregateur.consignes == [DEFAULT_USER_IDLE_PROMPT]
    assert moteur.call_monitor.appels == []


@pytest.mark.asyncio
async def test_au_clavier_le_modele_relance_comme_avant():
    moteur = _Moteur()
    moteur.sans_sortie_audio = True
    agregateur = await _silence(moteur, 1)
    assert moteur.dites == []
    assert agregateur.consignes == [DEFAULT_USER_IDLE_PROMPT]


@pytest.mark.asyncio
async def test_l_au_revoir_reste_une_consigne_et_raccroche():
    moteur = _Moteur()  # 1 relance avant l'au revoir
    agregateur = await _silence(moteur, 2)
    assert moteur.dites == []
    assert agregateur.consignes == [DEFAULT_USER_IDLE_GOODBYE_PROMPT]
    assert moteur.raccroche is not None


@pytest.mark.asyncio
async def test_la_phrase_part_micro_ouvert_l_appelant_la_coupe():
    moteur = _Moteur()
    await _silence(moteur, 1)
    assert moteur.muets == [False]


@pytest.mark.asyncio
async def test_un_verrou_du_diseur_refuse_la_phrase_la_relance_ne_compte_pas():
    moteur = _Moteur()
    moteur.call_monitor.appelant_parle = True  # l'appelant vient de reprendre la parole
    agregateur = await _silence(moteur, 1)
    assert moteur.dites == []
    assert agregateur.consignes == []  # pas de relance du modèle par-dessus
    assert moteur.call_monitor.appels == [False]


# --- Le délai et la suspension --------------------------------------------------


def test_le_delai_de_la_regle_sinon_celui_de_rythme():
    assert delai_de_la_relance(_Moteur()) is None  # défaut du catalogue : Rythme reste le délai
    assert delai_de_la_relance(_Moteur({"phrases_regles": [_regle(["x"])]})) is None
    assert delai_de_la_relance(_Moteur({"phrases_regles": [_regle(["x"], delai_s=4)]})) == 4
    eteinte = _Moteur({"phrases_regles": [_regle(["x"], delai_s=4, active=False)]})
    assert delai_de_la_relance(eteinte) is None


def test_pendant_un_travail_de_fond_aucune_relance():
    moteur = _Moteur()
    assert relance_suspendue(moteur) is False
    moteur.travaux.append(SimpleNamespace(occupe=True))
    assert relance_suspendue(moteur) is True
    moteur.travaux[0].occupe = False
    assert relance_suspendue(moteur) is False


def _moniteur(**reglages):
    moniteur = CallMonitorProcessor(
        response_source=lambda: None,
        on_response_timeout=lambda _s: None,
        on_user_idle=None,
        conversation_enabled=lambda: True,
    )
    moniteur.user_idle_timeout = 10.0
    moniteur.user_aggregator = SimpleNamespace(
        user_turn_controller=SimpleNamespace(has_active_user_turn=False)
    )
    moniteur._active = True
    moniteur._waiting_for_user = True
    for nom, valeur in reglages.items():
        setattr(moniteur, nom, valeur)
    return moniteur


@pytest.mark.asyncio
async def test_le_moniteur_arme_le_delai_de_la_regle_sinon_celui_de_rythme():
    sans = _moniteur()
    sans._arm_idle()
    assert sans._deadline is not None and sans._deadline_kind == "idle"
    loop = asyncio.get_running_loop()
    assert 9 < sans._deadline.when() - loop.time() <= 10

    avec = _moniteur(delai_de_relance=lambda: 4.0)
    avec._arm_idle()
    assert 3 < avec._deadline.when() - loop.time() <= 4
    sans._cancel_deadline()
    avec._cancel_deadline()


@pytest.mark.asyncio
async def test_le_moniteur_n_arme_aucune_relance_pendant_un_travail():
    moniteur = _moniteur(relance_suspendue=lambda: True)
    moniteur._arm_idle()
    assert moniteur._deadline is None
    moniteur.relance_suspendue = lambda: False
    moniteur._arm_idle()
    assert moniteur._deadline is not None
    moniteur._cancel_deadline()


@pytest.mark.asyncio
async def test_une_relance_dite_decharge_la_reponse_due_sinon_l_appel_raccrocherait():
    moniteur = _moniteur()
    moniteur._response_watch = object()  # « une réponse est due », armée avant la relance
    moniteur._retry_count = 1
    moniteur.relance_par_la_voix(dite=True)
    assert moniteur._response_watch is None
    assert moniteur._retry_count == 1  # la relance compte
    assert moniteur._waiting_for_user is True


@pytest.mark.asyncio
async def test_une_relance_refusee_ne_compte_pas_et_le_silence_est_de_nouveau_surveille():
    moniteur = _moniteur()
    moniteur._response_watch = object()
    moniteur._retry_count = 1
    moniteur.relance_par_la_voix(dite=False)
    assert moniteur._retry_count == 0
    assert moniteur._deadline_kind == "idle"
    moniteur._cancel_deadline()


# --- La vraie route ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_un_vrai_moteur_donne_au_moniteur_le_delai_et_la_suspension(three_node_workflow):
    """R1 : si le câblage du moteur s'éteint, le délai de la règle et la suspension ne valent
    plus rien sans qu'aucun autre test ne rougisse."""
    moteur = PipecatEngine(
        llm=MockLLMService(),
        context=LLMContext(),
        workflow=three_node_workflow,
        call_context_vars={},
        workflow_run_id=1,
    )
    moniteur = moteur.call_monitor
    assert moniteur.delai_de_relance() is None
    moteur.active_agent.reglages = {"phrases_regles": [_regle(["Allô ?"], delai_s=6)]}
    assert moniteur.delai_de_relance() == 6
    assert moniteur.relance_suspendue() is False
    moteur.travaux.append(SimpleNamespace(occupe=True))
    assert moniteur.relance_suspendue() is True
    # Et la relance elle-même passe par le diseur du moteur : pas de consigne au modèle.
    moteur.travaux.clear()
    dites: list[str] = []

    async def queue_speech(texte, **_):
        dites.append(texte)
        fin = asyncio.Event()
        fin.set()
        return SimpleNamespace(wait=fin.wait, outcome=None)

    moteur.queue_speech = queue_speech
    moteur.is_call_disposed = lambda: False
    agregateur = _Agregateur()
    await handle_user_idle(moteur, agregateur, 1)
    await moteur.phrases.attendre_la_fin()
    assert dites == ["Allô ?"]
    assert agregateur.consignes == []
