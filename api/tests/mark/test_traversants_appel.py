"""[.mark] Tests TRAVERSANTS : une vraie donnée par le vrai montage d'un appel.

Lot 5 du chantier durcissement-outils-fork (trou T2, réflexe R1),
plan `Labo-agent-vocal/plans/durcissement-outils-fork/`.

Pourquoi ce fichier existe
--------------------------
Nos tests éprouvent chaque fonctionnalité .mark isolément : un processeur seul,
une liste de processeurs fabriquée à la main, une fonction pure. Aucun ne partait
de ce qu'un appel lit vraiment (la configuration de l'agent enregistrée en base,
le lexique de l'organisation, la langue de sa transcription) pour aller jusqu'à
ce que le modèle reçoit et ce que la voix prononce. Une fonctionnalité éteinte en
silence par un branchement cassé (R1) laissait donc toute la suite verte : c'est
le chemin où se cachait le bloquant de la nuit du 16/09.

Ici, chaque test monte un appel avec ``_run_pipeline`` (le vrai), sur la base de
test, et ne remplace que les bords qui parlent à l'extérieur : la transcription
(les paroles de l'appelant arrivent déjà écrites), le modèle (réponses écrites
d'avance, contextes reçus gardés), et le seul FOURNISSEUR de voix (Cartesia) :
la fabrique de voix, elle, est la vraie, avec ses filtres et ses transformations.

| Test | Ce qu'il prouve, de la base jusqu'au bout de la chaîne |
|---|---|
| lecture | « trois mille cinq euros » arrive au modèle en chiffres, avec sa note |
| lecture éteinte | interrupteur éteint : les paroles arrivent telles quelles |
| lexique | « Edilcamin » arrive au modèle écrit « Edilkamin » (lexique de l'organisation) |
| voix | « 350 euros » est prononcé en mots ; un appel de fonction écrit n'est pas dit |
| fiche + nom | `noter_information` écrit le nom dans la fiche de l'appel, en base, et la voix ne le prononce jamais |
| relance | après un silence, le modèle reçoit la consigne de relance de l'agent |
| micro | `mute_always` réglé en base est dans l'agrégateur réel de l'appel, absent sinon |
| plafond du lexique | la liste remise à la transcription tient sous le plafond déclaré avec le fournisseur, dictionnaire de l'agent en tête |
| noms proposés | l'agent reçoit `lexique_propose` et `lexique_a_ecouter` (même contenu), tirés de la seule case « l'entreprise le propose » |
| filet du lexique | une liste refusée par la transcription (HTTP 400) : reconnexion sans la liste, l'appel continue, le refus est estampillé |

⛔ Chacun a été éprouvé en débranchant sa fonctionnalité : il rougit (journal du
chantier). Un test traversant qui reste vert fonctionnalité débranchée ne
protège rien.

⚠️ Il vit dans `api/tests/mark/` : un test du fork ailleurs n'est pas rejoué aux
montées de version (règle du 08/09).
"""

import asyncio
import contextlib
import copy
import functools
import uuid
from unittest.mock import patch

import pytest
from pipecat.frames.frames import TranscriptionFrame
from pipecat.tests import ContextCapturingMockLLM, MockLLMService, MockTTSService
from pipecat.tests.mock_transport import MockTransport
from pipecat.transports.base_transport import TransportParams
from pipecat.turns.user_mute import AlwaysUserMuteStrategy
from pipecat.utils.time import time_now_iso8601

from api.db.models import OrganizationModel, UserModel
from api.enums import OrganizationConfigurationKey, WorkflowRunMode
from api.schemas.ai_model_configuration import EffectiveAIModelConfiguration
from api.services.configuration.ai_model_configuration import (
    convert_legacy_ai_model_configuration_to_v2,
)
from api.services.lexique.stockage import CLE as CLE_LEXIQUE
from api.services.pipecat import service_factory
from api.services.pipecat.audio_config import create_audio_config
from api.services.pipecat.run_pipeline import _run_pipeline
from api.services.pipecat.worker_runner import wait_for_pipeline_worker_started
from api.tests.integrations._run_pipeline_helpers import (
    USER_CONFIGURATION,
    patch_run_pipeline_externals,
)

ACCUEIL = "Bonjour, Chauffage Martin, je vous écoute."

DEFINITION = {
    "nodes": [
        {
            "id": "start",
            "type": "startCall",
            "position": {"x": 0, "y": 0},
            "data": {
                "name": "Accueil",
                "prompt": "Tu es l'accueil téléphonique de Chauffage Martin.",
                "is_start": True,
                "allow_interrupt": False,
                "add_global_prompt": False,
                "greeting": ACCUEIL,
                "greeting_type": "text",
            },
        },
        {
            "id": "end",
            "type": "endCall",
            "position": {"x": 0, "y": 200},
            "data": {
                "name": "Fin",
                "prompt": "Termine l'appel poliment.",
                "is_end": True,
                "allow_interrupt": False,
                "add_global_prompt": False,
            },
        },
    ],
    "edges": [
        {
            "id": "start-end",
            "source": "start",
            "target": "end",
            "data": {"label": "End Call", "condition": "Quand l'appelant veut raccrocher."},
        }
    ],
}

# Ce que la fabrique de voix transmet au fournisseur et que la fausse voix doit
# recevoir pour appliquer, elle aussi, les filtres et transformations .mark.
REGLAGES_DE_VOIX = (
    "text_filters",
    "text_transforms",
    "text_aggregation_mode",
    "push_silence_after_stop",
    "silence_time_s",
    "skip_aggregator_types",
)

# Plafond d'un test : sans lui, un montage bloqué garderait pytest ouvert.
PLAFOND_S = 40.0


# --------------------------------------------------------------------------- #
# Montage
# --------------------------------------------------------------------------- #


async def _monter(db_session, async_session, configurations: dict, *, lexique=None):
    """Organisation, agent français, workflow publié AVEC sa configuration, run."""
    suffixe = uuid.uuid4().hex[:10]
    org = OrganizationModel(provider_id=f"test-org-traversant-{suffixe}")
    async_session.add(org)
    await async_session.flush()
    user = UserModel(
        provider_id=f"test-user-traversant-{suffixe}", selected_organization_id=org.id
    )
    async_session.add(user)
    await async_session.flush()

    modeles = copy.deepcopy(USER_CONFIGURATION)
    modeles["stt"]["language"] = "fr"  # la langue de l'agent vient d'ici (lecture, voix)
    await db_session.upsert_configuration(
        org.id,
        OrganizationConfigurationKey.MODEL_CONFIGURATION_V2.value,
        convert_legacy_ai_model_configuration_to_v2(
            EffectiveAIModelConfiguration.model_validate(modeles)
        ).model_dump(mode="json", exclude_none=True),
    )
    if lexique is not None:
        await db_session.upsert_configuration(org.id, CLE_LEXIQUE, lexique)

    workflow = await db_session.create_workflow(
        name="Traversant",
        workflow_definition=DEFINITION,
        user_id=user.id,
        organization_id=org.id,
    )
    # Comme l'écran : un brouillon porte la configuration, la publication la
    # rend lue par l'appel (`workflow_run.definition.workflow_configurations`).
    await db_session.save_workflow_draft(
        workflow.id, workflow_definition=DEFINITION, workflow_configurations=configurations
    )
    publiee = await db_session.publish_workflow_draft(workflow.id)
    run = await db_session.create_workflow_run(
        name="Traversant",
        workflow_id=workflow.id,
        mode=WorkflowRunMode.SMALLWEBRTC.value,
        user_id=user.id,
        definition_id=publiee.id,
    )
    return run, user, workflow


def _fausse_cartesia(voix: list):
    def fabrique(**reglages):
        tts = MockTTSService(
            mock_audio_duration_ms=40,
            frame_delay=0,
            **{cle: reglages[cle] for cle in REGLAGES_DE_VOIX if cle in reglages},
        )
        voix.append(tts)
        return tts

    return fabrique


def _trouver(tache, nom_de_classe: str):
    vus: set[int] = set()
    pile = [tache._pipeline]
    while pile:
        p = pile.pop()
        if id(p) in vus:
            continue
        vus.add(id(p))
        if p.__class__.__name__ == nom_de_classe:
            return p
        pile.extend(getattr(p, "_processors", None) or [])
    return None


async def _attendre(condition, delai: float) -> bool:
    fin = asyncio.get_event_loop().time() + delai
    while asyncio.get_event_loop().time() < fin:
        if condition():
            return True
        await asyncio.sleep(0.05)
    return condition()


async def _appeler(
    montage,
    llm,
    paroles: list[str],
    *,
    fin_attendue: bool = False,
    apres=None,
    fabrique_stt=None,
):
    """Joue un appel : accueil, puis chaque parole attend la réponse du modèle.

    Rend (la fausse voix, la tâche). ``apres(tache, agregateur, voix)``
    s'exécute pendant l'appel, avant l'arrêt.
    """
    run, user, workflow = montage
    voix: list = []
    capture: list = []
    transport = MockTransport(
        TransportParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_end_silence_secs=0)
    )
    vraie_fabrique_de_voix = service_factory.create_tts_service
    tache = None
    appel = None
    # ⛔ Tout, y compris l'ARRÊT, se joue à l'intérieur des doublures : un appel
    # arrêté après leur retrait met de vrais travaux en file et appelle de vrais
    # services (relecture du 25/09). Et l'appel est ATTENDU jusqu'au bout : une
    # exception de fin d'appel (un finaliseur .mark qui casse) doit faire échouer
    # le test, pas se perdre dans la boucle partagée de la session.
    with (
        patch_run_pipeline_externals(capture, llm=llm),
        # La VRAIE fabrique de voix (le harnais la remplace), seul le
        # fournisseur est faux.
        patch("api.services.pipecat.run_pipeline.create_tts_service", vraie_fabrique_de_voix),
        patch.object(service_factory, "CartesiaTTSService", _fausse_cartesia(voix)),
        # Une transcription à soi (par défaut, celle du harnais : un passe-plat).
        (
            patch("api.services.pipecat.run_pipeline.create_stt_service", fabrique_stt)
            if fabrique_stt is not None
            else contextlib.nullcontext()
        ),
    ):
        try:
            appel = asyncio.create_task(
                _run_pipeline(
                    transport=transport,
                    workflow_id=workflow.id,
                    workflow_run_id=run.id,
                    user_id=user.id,
                    audio_config=create_audio_config(WorkflowRunMode.SMALLWEBRTC.value),
                    user_provider_id=user.provider_id,
                )
            )
            assert await _attendre(lambda: capture or appel.done(), 5.0)
            if appel.done() and not capture:
                appel.result()
            tache = capture[0]
            await wait_for_pipeline_worker_started(tache, timeout=5.0, run_task=appel)

            agregateur = _trouver(tache, "LLMUserAggregator")
            assert agregateur is not None
            assert await _attendre(lambda: voix and _accueil_dit(voix[0]), 8.0), "accueil jamais dit"
            assert await _attendre(lambda: not agregateur._user_is_muted, 5.0), "micro resté coupé"

            for parole in paroles:
                etape = llm.get_current_step()
                await tache.queue_frame(
                    TranscriptionFrame(text=parole, user_id="appelant", timestamp=time_now_iso8601())
                )
                assert await _attendre(lambda e=etape: llm.get_current_step() > e, 8.0), (
                    f"le modèle n'a pas répondu à « {parole} »"
                )
                await _reponse_finie(llm)

            if apres is not None:
                await apres(tache, agregateur, voix[0])
            if fin_attendue:
                await asyncio.wait_for(appel, timeout=10.0)
        finally:
            if tache is not None and not tache.has_finished():
                await asyncio.wait_for(tache.cancel(), timeout=3.0)
            if appel is not None:
                try:
                    await asyncio.wait_for(appel, timeout=5.0)
                except asyncio.CancelledError:
                    # Seul l'arrêt demandé ci-dessus s'avale. L'annulation du
                    # plafond du test (`_borne`) doit remonter, sinon un test
                    # bloqué continuerait vers ses assertions (R7, contre-relecture).
                    if not appel.cancelled():
                        raise
    return (voix[0] if voix else None), tache


def _accueil_dit(tts) -> bool:
    return any("Chauffage Martin" in t for t in tts.received_texts)


async def _reponse_finie(llm, calme_s: float = 0.8, delai: float = 8.0) -> None:
    """Attend que le modèle ne produise plus rien pendant ``calme_s`` : un outil
    appelé est suivi d'une seconde génération, qu'une nouvelle parole de
    l'appelant couperait."""
    fin = asyncio.get_event_loop().time() + delai
    derniere, depuis = llm.get_current_step(), asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() < fin:
        await asyncio.sleep(0.05)
        if llm.get_current_step() != derniere:
            derniere, depuis = llm.get_current_step(), asyncio.get_event_loop().time()
        elif asyncio.get_event_loop().time() - depuis >= calme_s:
            return
    raise AssertionError(f"le modèle produisait encore après {delai} s")


def _derniere_parole_recue(llm) -> str:
    messages = llm.captured_contexts[0]["messages"]
    return [m for m in messages if m.get("role") == "user"][-1]["content"]


def _texte(reponse: str):
    return MockLLMService.create_text_chunks(reponse)


def _outil(nom: str, arguments: dict, identifiant: str):
    return MockLLMService.create_function_call_chunks(
        function_name=nom, arguments=arguments, tool_call_id=identifiant
    )


def _borne(corps):
    # `wraps` : pytest lit la signature du test à travers l'enveloppe pour
    # injecter `db_session` et `async_session`.
    @functools.wraps(corps)
    async def enveloppe(*args, **kwargs):
        await asyncio.wait_for(corps(*args, **kwargs), timeout=PLAFOND_S)

    return enveloppe


# --------------------------------------------------------------------------- #
# Ce que le modèle reçoit
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@_borne
async def test_lecture_des_nombres_arrive_au_modele(db_session, async_session):
    montage = await _monter(
        db_session, async_session, {"conversion_nombres_transcription": True}
    )
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    await _appeler(montage, llm, ["trois mille cinq euros"])
    recu = _derniere_parole_recue(llm)
    assert recu.startswith("3005 euros [Lecture des nombres"), recu


@pytest.mark.asyncio
@_borne
async def test_lecture_eteinte_les_paroles_arrivent_telles_quelles(db_session, async_session):
    montage = await _monter(
        db_session,
        async_session,
        {
            "conversion_nombres_transcription": False,
            "verification_communes": False,
            "lecture_epellation": False,
        },
    )
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    await _appeler(montage, llm, ["trois mille cinq euros"])
    assert _derniere_parole_recue(llm) == "trois mille cinq euros"


@pytest.mark.asyncio
@_borne
async def test_le_lexique_de_l_organisation_corrige_avant_le_modele(db_session, async_session):
    lexique = {
        "termes": [
            {"terme": "Edilkamin", "variantes": ["Edil Kamin"], "categorie": "marque", "a_ecouter": True}
        ]
    }
    montage = await _monter(db_session, async_session, {}, lexique=lexique)
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    await _appeler(montage, llm, ["c'est un Edilcamin"])
    assert _derniere_parole_recue(llm) == "c'est un Edilkamin"


# --------------------------------------------------------------------------- #
# Ce que la voix prononce
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@_borne
async def test_la_voix_dit_les_nombres_en_mots_et_jamais_un_appel_de_fonction(
    db_session, async_session
):
    montage = await _monter(db_session, async_session, {})
    # Deux formes d'appel écrit (run 852) : glissé AU MILIEU d'une phrase, que
    # seul le retrait des appels attrape ; seul dans sa phrase, que le filtre
    # des phrases-appels attrape aussi. ⛔ Avec la seconde forme seule, ce test
    # restait vert retrait débranché (éprouvé le 25/09).
    llm = ContextCapturingMockLLM(
        mock_steps=[
            _texte(
                "Le devis est de 350 euros. D'accord transfert() je vous passe. "
                'Noté. noter_information({"nom": "Lefebvre"})'
            )
        ],
        chunk_delay=0.001,
    )
    async def tout_dit(_tache, _agregateur, voix):
        # PENDANT l'appel : la dernière phrase doit avoir atteint la voix.
        assert await _attendre(
            lambda: any("Noté" in t for t in voix.received_texts), 5.0
        ), "la réponse n'a jamais atteint la voix"

    voix, _ = await _appeler(montage, llm, ["combien pour le ramonage ?"], apres=tout_dit)
    dit = " ".join(voix.received_texts)
    assert "trois cent cinquante" in dit, dit
    assert "350" not in dit, dit
    assert "je vous passe" in dit and "transfert" not in dit, dit
    assert "noter_information" not in dit and "Lefebvre" not in dit, dit


@pytest.mark.asyncio
@_borne
async def test_la_fiche_note_le_nom_en_base_et_la_voix_ne_le_dit_jamais(
    db_session, async_session
):
    montage = await _monter(
        db_session,
        async_session,
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": [{"nom": "nom", "origine": "dicte", "description": "Nom de famille"}],
            "interdire_nom_appelant": True,
        },
    )
    llm = ContextCapturingMockLLM(
        mock_steps=[
            _outil("noter_information", {"nom": "Dupont"}, "note_1"),
            _texte("Merci Monsieur Dupont. C'est quel modèle ?"),
            _outil("end_call", {}, "fin_1"),
        ],
        chunk_delay=0.001,
    )
    voix, _ = await _appeler(
        montage, llm, ["je m'appelle Dupont", "au revoir"], fin_attendue=True
    )
    dit = " ".join(voix.received_texts)
    assert "Merci" in dit, dit
    assert "Dupont" not in dit, dit

    run = await db_session.get_workflow_run_by_id(montage[0].id)
    fiche = run.gathered_context
    assert fiche.get("nom") == "Dupont", fiche
    assert fiche["extracted_variables"]["nom"] == "Dupont"


# --------------------------------------------------------------------------- #
# Tour de parole
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@_borne
async def test_la_relance_d_inactivite_de_l_agent_atteint_le_modele(db_session, async_session):
    consigne = "RELANCE-MARK : demande si l'appelant est toujours en ligne."
    montage = await _monter(
        db_session,
        async_session,
        {"max_user_idle_timeout": 1.0, "user_idle_prompt": consigne},
    )
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Vous êtes toujours là ?")], chunk_delay=0.001)

    async def silence(_tache, _agregateur, _voix):
        assert await _attendre(lambda: llm.captured_contexts, 8.0), "aucune relance"

    await _appeler(montage, llm, [], apres=silence)
    recu = str(llm.captured_contexts[0]["messages"]) + str(llm.captured_contexts[0]["system_prompt"])
    assert "RELANCE-MARK" in recu, recu


@pytest.mark.asyncio
@pytest.mark.parametrize("regle", [True, False])
@_borne
async def test_la_coupure_du_micro_reglee_arrive_dans_l_agregateur_de_l_appel(
    db_session, async_session, regle
):
    """⚠️ Ce que `mute_always` fait : couper le micro PENDANT QUE L'AGENT PARLE
    (Pipecat, `AlwaysUserMuteStrategy`), pas en permanence. Une première version
    affirmait « l'appelant n'atteint jamais le modèle » : fausse, et instable
    selon que la parole tombait avant ou après la fin de l'accueil (25/09).
    Ce qui s'affirme sans dépendre de l'horloge : le réglage de la base est dans
    l'agrégateur que l'appel a réellement construit, et absent sans lui."""
    montage = await _monter(db_session, async_session, {"mute_always": regle})
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    trouvees = []

    async def relever(_tache, agregateur, _voix):
        trouvees.extend(agregateur._params.user_mute_strategies)

    await _appeler(montage, llm, [], apres=relever)
    presente = any(isinstance(s, AlwaysUserMuteStrategy) for s in trouvees)
    assert presente is regle, trouvees


# --------------------------------------------------------------------------- #
# Décisions d'Evan du 25/09/2026, remise à niveau sur l'amont 4e6cb22b
# --------------------------------------------------------------------------- #


def _espion_mots_minimum(installees: list):
    """Remplace, dans le contrôleur d'accueil de l'amont, la stratégie « N mots »
    par une enveloppe qui note N à chaque installation."""
    from api.services.pipecat import greeting as module_accueil

    vraie = module_accueil.MinWordsUserTurnStartStrategy

    def enveloppe(*args, **kwargs):
        installees.append(kwargs.get("min_words"))
        return vraie(*args, **kwargs)

    return patch.object(module_accueil, "MinWordsUserTurnStartStrategy", enveloppe)


@pytest.mark.asyncio
@_borne
async def test_E1_accueil_eteint_par_defaut_la_premiere_phrase_reste_protegee(
    db_session, async_session
):
    """Défaut (E1 éteint) : la coupure « jusqu'à la fin de la première phrase »
    est dans l'agrégateur réel, et le contrôleur d'accueil de l'amont n'installe
    JAMAIS sa stratégie « N mots » : la production du 25/09, à l'identique."""
    from pipecat.turns.user_mute import MuteUntilFirstBotCompleteUserMuteStrategy

    montage = await _monter(db_session, async_session, {})
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    installees, coupures = [], []

    async def relever(_tache, agregateur, _voix):
        coupures.extend(agregateur._params.user_mute_strategies)

    with _espion_mots_minimum(installees):
        await _appeler(montage, llm, [], apres=relever)
    assert any(isinstance(s, MuteUntilFirstBotCompleteUserMuteStrategy) for s in coupures)
    assert installees == [], installees


@pytest.mark.asyncio
@_borne
async def test_E1_accueil_allume_l_appelant_le_coupe_a_N_mots(db_session, async_session):
    """Allumé : la protection de la première phrase est retirée pour cet agent,
    et le contrôleur d'accueil installe « N mots » avec le N réglé en base."""
    from pipecat.turns.user_mute import MuteUntilFirstBotCompleteUserMuteStrategy

    montage = await _monter(
        db_session,
        async_session,
        {"accueil_interruptible": True, "accueil_mots_minimum": 3},
    )
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    installees, coupures = [], []

    async def relever(_tache, agregateur, _voix):
        coupures.extend(agregateur._params.user_mute_strategies)

    with _espion_mots_minimum(installees):
        await _appeler(montage, llm, [], apres=relever)
    assert not any(isinstance(s, MuteUntilFirstBotCompleteUserMuteStrategy) for s in coupures)
    assert installees and set(installees) == {3}, installees


@pytest.mark.asyncio
@pytest.mark.parametrize("reglage,attendu", [(None, 35.0), (47, 47.0)])
@_borne
async def test_E2_le_raccrochage_regle_arrive_au_moniteur_de_l_appel(
    db_session, async_session, reglage, attendu
):
    """Le délai de silence de l'agent avant raccrochage est celui de la base,
    35 s sans réglage (la valeur de l'amont), dans le moniteur que l'appel a
    réellement construit."""
    configuration = {} if reglage is None else {"raccrochage_silence_agent_s": reglage}
    montage = await _monter(db_session, async_session, configuration)
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    delais = []

    async def relever(tache, _agregateur, _voix):
        moniteur = _trouver(tache, "CallMonitorProcessor")
        delais.append(moniteur.response_timeout if moniteur else None)

    await _appeler(montage, llm, [], apres=relever)
    assert delais == [attendu]


# --------------------------------------------------------------------------- #
# Le lexique envoyé à la transcription (plan « le lexique », L1 et L2)
# --------------------------------------------------------------------------- #


def _lexique_coche(n: int) -> dict:
    return {"termes": [{"terme": f"Marque{i:03d}", "a_ecouter": True} for i in range(n)]}


@pytest.mark.asyncio
@_borne
async def test_la_liste_remise_a_la_transcription_tient_sous_le_plafond_du_fournisseur(
    db_session, async_session
):
    """Le vrai appel construit la liste avec le plafond du fournisseur de
    l'organisation (Deepgram, dans la configuration montée) : dictionnaire de
    l'agent en tête, puis les termes cochés, la fin coupée."""
    from api.services.configuration.plafond_lexique import jetons_du_terme, plafond_du_lexique
    from api.tests.integrations._run_pipeline_helpers import PassthroughProcessor

    montage = await _monter(
        db_session, async_session, {"dictionary": "ramonage, insert"}, lexique=_lexique_coche(400)
    )
    recues = []

    def transcription(*_args, keyterms=None, **_kwargs):
        recues.append(list(keyterms or []))
        return PassthroughProcessor()

    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    await _appeler(montage, llm, ["bonjour"], fabrique_stt=transcription)
    plafond = plafond_du_lexique("deepgram", USER_CONFIGURATION["stt"]["model"])
    assert len(recues) == 1
    liste = recues[0]
    assert liste[:3] == ["ramonage", "insert", "Marque000"]
    assert 3 < len(liste) < 402, len(liste)
    assert sum(jetons_du_terme(t, plafond) for t in liste) <= plafond.jetons


class _TranscriptionQuiRefuseLaListe:
    """Une transcription qui se connecte au démarrage comme Flux, et que le
    fournisseur refuse (HTTP 400) tant que l'adresse porte des termes. Sans
    connexion, elle fait tomber l'appel, comme le 18/09."""

    def __init__(self, keyterms):
        from types import SimpleNamespace

        from api.tests.integrations._run_pipeline_helpers import PassthroughProcessor

        adresses = self.adresses = []
        termes = "".join(f"&keyterm={t}" for t in keyterms or [])

        class Service(PassthroughProcessor):
            def __init__(self):
                super().__init__()
                self._settings = SimpleNamespace(keyterm=list(keyterms or []))
                self._websocket_url = f"wss://api.eu.deepgram.com/v2/listen?model=flux-general-multi{termes}"

            async def _websocket_connect(self, uri, **_kwargs):
                from websockets.datastructures import Headers
                from websockets.exceptions import InvalidStatus
                from websockets.http11 import Response

                adresses.append(uri)
                if "keyterm=" in uri:
                    raise InvalidStatus(Response(400, "Bad Request", Headers(), b""))
                return "connexion"

            async def process_frame(self, frame, direction):
                from pipecat.frames.frames import StartFrame

                if isinstance(frame, StartFrame):
                    await super().process_frame(frame, direction)
                    try:
                        await self._websocket_connect(self._websocket_url)
                    except Exception as erreur:  # noqa: BLE001
                        await self.push_error(error_msg=f"refusé : {erreur}", fatal=True)
                    return
                await super().process_frame(frame, direction)

        self.service = Service()


@pytest.mark.asyncio
@_borne
async def test_une_liste_refusee_ne_fait_pas_tomber_l_appel(db_session, async_session):
    """L2 : la transcription refuse la liste (400) ; le filet se reconnecte sans
    elle, l'appel continue (le modèle répond), et le refus est estampillé."""
    montage = await _monter(
        db_session, async_session, {}, lexique={"termes": [{"terme": "Edilkamin", "a_ecouter": True}]}
    )
    fausses = []

    def transcription(*_args, keyterms=None, **_kwargs):
        fausse = _TranscriptionQuiRefuseLaListe(keyterms)
        fausses.append(fausse)
        return fausse.service

    llm = ContextCapturingMockLLM(
        mock_steps=[_texte("Très bien."), _outil("end_call", {}, "fin_1")], chunk_delay=0.001
    )
    await _appeler(montage, llm, ["bonjour", "au revoir"], fin_attendue=True, fabrique_stt=transcription)

    adresses = fausses[0].adresses
    assert len(adresses) == 2 and "keyterm=Edilkamin" in adresses[0]
    assert "keyterm" not in adresses[1]
    run = await db_session.get_workflow_run_by_id(montage[0].id)
    contexte = run.gathered_context
    estampilles = [v["runtime_configuration"].get("lexique_transcription") for v in contexte["agent_visits"]]
    assert estampilles and estampilles[-1]["etat"] == "non envoyé : refusé", estampilles
    assert "400" in estampilles[-1]["refus"]


@pytest.mark.asyncio
@_borne
async def test_l_agent_recoit_les_noms_proposes_et_seulement_eux(db_session, async_session):
    """L3 : la case « l'entreprise le propose » alimente la variable de l'agent,
    sous son nom et sous l'ancien ; la case « écouter » n'y entre pas."""
    montage = await _monter(
        db_session,
        async_session,
        {},
        lexique={
            "termes": [
                {"terme": "Edilkamin", "a_ecouter": True, "propose": True},
                {"terme": "Rika", "a_ecouter": True, "propose": False},
                {"terme": "Jøtul", "a_ecouter": False, "propose": True},
                # Enregistré avant la seconde case : il était coché, il reste proposé.
                {"terme": "Supra", "a_ecouter": True},
            ]
        },
    )
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    await _appeler(montage, llm, ["bonjour"])
    run = await db_session.get_workflow_run_by_id(montage[0].id)
    assert run.initial_context["lexique_propose"] == "Edilkamin, Jøtul, Supra"
    assert run.initial_context["lexique_a_ecouter"] == "Edilkamin, Jøtul, Supra"


@pytest.mark.asyncio
@_borne
async def test_une_marque_epelee_ne_remplace_pas_le_nom(db_session, async_session):
    """L5 (run 803) : l'appelant épelle sa marque ; le modèle la note dans le nom.
    La fiche en base garde le nom, et la marque va dans son champ."""
    montage = await _monter(
        db_session,
        async_session,
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": [
                {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
                {"nom": "marque", "origine": "dicte", "description": "Marque de l'appareil"},
            ],
            "lecture_epellation": True,
        },
        lexique={"termes": [{"terme": "MCZ", "categorie": "marque"}]},
    )
    llm = ContextCapturingMockLLM(
        mock_steps=[
            _outil("noter_information", {"nom": "Caron"}, "note_1"),
            _texte("Merci. Quelle est la marque ?"),
            _outil("noter_information", {"nom": "MCZ", "marque": "MCZ"}, "note_2"),
            _texte("C'est noté."),
            _outil("end_call", {}, "fin_1"),
        ],
        chunk_delay=0.001,
    )
    await _appeler(
        montage, llm, ["je m'appelle Caron", "c'est un M C Z", "au revoir"], fin_attendue=True
    )
    run = await db_session.get_workflow_run_by_id(montage[0].id)
    fiche = run.gathered_context
    assert fiche.get("nom") == "Caron", fiche.get("fiche_journal")
    assert fiche.get("marque") == "MCZ", fiche.get("fiche_journal")
    refus = [e for e in fiche["fiche_journal"] if e.get("raison") == "terme_du_lexique_epele"]
    assert refus and refus[0]["champ"] == "nom"


@pytest.mark.asyncio
@_borne
async def test_un_telephone_ecrit_en_chiffres_arrive_au_modele_sans_fausse_reference(
    db_session, async_session
):
    """N1 : la transcription a écrit le téléphone avec des points. Le modèle le
    reçoit comme un téléphone, sans la fausse note « référence 06 » d'avant."""
    montage = await _monter(db_session, async_session, {"conversion_nombres_transcription": True})
    llm = ContextCapturingMockLLM(mock_steps=[_texte("Très bien.")], chunk_delay=0.001)
    await _appeler(montage, llm, ["mon numéro c'est 06.12.34.56.78"])
    assert _derniere_parole_recue(llm) == "mon numéro c'est 06 12 34 56 78"
