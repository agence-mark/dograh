"""[.mark] Chantier fiabilite-orchestration, lot 11 : les correctifs de la relecture du 19/10.

| Test | La garantie |
|---|---|
| verrou annulé | une phrase d'attente annulée pendant qu'elle part libère le verrou : les attentes suivantes se disent |
| repli d'un autre protocole | un cerveau de repli dont le client n'est pas de la famille de celui de l'agent est ignoré |
| drapeau du repli | rien relancé (l'agent n'a plus la main) : la prochaine requête normale ne part pas au repli |
| trace du fond | une requête du cerveau de fond ne reçoit jamais le texte dit à l'appelant |
| fabrique arrêtée | l'appel fini, la fabrique des sons s'arrête sans fabriquer le reste |
| réserve unique | deux passations rapprochées vers le même collègue ne lancent qu'une construction |
| carte | un identifiant de principal illisible rend la carte de l'agent seul, jamais une erreur |
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.services.panne.delai_modele import DelaiModeleDepasse
from api.services.panne.garde_modele import GardeDuModele, Repli, _meme_famille
from api.services.phrases.catalogue import APPELANT_SE_TAIT, TRAVAIL_DURE
from api.services.phrases.diseur import DiseurDePhrases
from api.services.phrases.sons import FabriqueDesSons
from api.services.pipecat.trace_modele import TraceDuModele
from api.tests.mark.test_attente_parlee import _FauxMoteur


@pytest.mark.asyncio
async def test_une_attente_annulee_en_partant_libere_le_verrou():
    moteur = _FauxMoteur(lambda: 0.0)
    bloque = asyncio.Event()

    async def lente(texte, **_):
        await bloque.wait()

    moteur.queue_speech = lente
    diseur = DiseurDePhrases(moteur, horloge=lambda: 100.0)
    tache = asyncio.create_task(diseur.dire(TRAVAIL_DURE))
    await asyncio.sleep(0.02)
    tache.cancel()
    await asyncio.gather(tache, return_exceptions=True)

    async def rapide(texte, **_):
        moteur.dites.append(texte)
        fin = asyncio.Event()
        fin.set()
        return SimpleNamespace(wait=fin.wait)

    moteur.queue_speech = rapide
    diseur._horloge = lambda: 200.0  # le repos de 3 s est passé
    assert await diseur.dire(APPELANT_SE_TAIT) is True


class _ClientChat:
    def __init__(self):
        self.chat = SimpleNamespace(completions=object())


class _AutreClient:
    pass


def test_un_repli_d_un_autre_protocole_est_ignore():
    assert _meme_famille(_ClientChat(), _ClientChat()) is True
    assert _meme_famille(_AutreClient(), _ClientChat()) is False
    assert _meme_famille(_ClientChat(), None) is True  # agent inconnu : rien à comparer


@pytest.mark.asyncio
async def test_rien_relance_le_drapeau_du_repli_retombe():
    moteur = SimpleNamespace(
        _gathered_context={},
        phrases=SimpleNamespace(dire=AsyncMock()),
        end_call_with_reason=AsyncMock(),
        is_call_disposed=lambda: False,
    )
    llm = SimpleNamespace(_mark_tentative_au_repli=False)
    garde = GardeDuModele(
        moteur,
        llm,
        AsyncMock(return_value=False),
        parle=True,
        repli=Repli(client=object(), modele="m", fournisseur="f"),
    )
    await garde._depasse(None, DelaiModeleDepasse("premier_morceau", 4.0))
    assert llm._mark_tentative_au_repli is False
    garde.relancer = AsyncMock(return_value=True)
    garde.compteur = 0
    await garde._depasse(None, DelaiModeleDepasse("premier_morceau", 4.0))
    assert llm._mark_tentative_au_repli is True


def test_le_texte_dit_ne_va_jamais_dans_une_requete_du_fond():
    fiche: dict = {}
    trace = TraceDuModele(lambda: fiche)
    conversation = trace.ouvrir("accueil")
    trace.ouvrir("accueil (fond)", parle=False)
    trace.dit("Bonjour.")
    assert conversation["texte_dit"] == "Bonjour."
    from api.services.pipecat.trace_modele import TRACE_REQUETES

    assert fiche[TRACE_REQUETES][1]["texte_dit"] == ""


@pytest.mark.asyncio
async def test_l_appel_fini_la_fabrique_s_arrete():
    vivant = [True]
    voix_creees = []

    class Worker:
        started_at = 1.0

        def __init__(self, *a, **k):
            self.envoyes = []

        def has_finished(self):
            return False

        async def queue_frame(self, frame):
            self.envoyes.append(frame)
            vivant[0] = False  # l'appel finit pendant la première phrase

        async def cancel(self, **_):
            pass

    import pipecat.pipeline.worker as module_worker

    ancien = module_worker.PipelineWorker
    module_worker.PipelineWorker = Worker
    try:
        from pipecat.processors.frame_processor import FrameProcessor

        fabrique = FabriqueDesSons(
            creer_la_voix=lambda: voix_creees.append(1) or FrameProcessor(),
            ajouter_le_circuit=AsyncMock(),
            taux_attendu=16000,
            en_vie=lambda: vivant[0],
        )
        await asyncio.wait_for(fabrique.fabriquer(["A.", "B.", "C."]), 5)
    finally:
        module_worker.PipelineWorker = ancien
    assert fabrique.sons == {} and fabrique.echecs == ["A."]


@pytest.mark.asyncio
async def test_deux_passations_rapprochees_une_seule_construction():
    from api.services.groupe.prechauffage import Precharge
    from api.services.workflow.pipecat_engine import PipecatEngine

    portail = asyncio.Event()
    constructions = []

    async def construire(*, workflow_id, visit_id):
        constructions.append(workflow_id)
        await portail.wait()
        return SimpleNamespace(preconstruit=False, travail=None, llm=None)

    class Moteur:
        pass

    moteur = Moteur()
    moteur._agent_factory = SimpleNamespace(precharge=Precharge(organization_id=1), build=construire)
    moteur.preparer_le_travail = AsyncMock()
    moteur.is_call_disposed = lambda: False
    premiere = asyncio.create_task(PipecatEngine._mettre_en_reserve(moteur, 7))
    seconde = asyncio.create_task(PipecatEngine._mettre_en_reserve(moteur, 7))
    await asyncio.sleep(0.02)
    portail.set()
    await asyncio.gather(premiere, seconde)
    assert constructions == [7]
    assert 7 in moteur._agent_factory.precharge.prets


@pytest.mark.asyncio
async def test_un_principal_illisible_rend_la_carte_de_l_agent_seul(monkeypatch):
    from api.db import db_client
    from api.services.phrases import carte

    agent = SimpleNamespace(
        id=3,
        name="Agent",
        current_definition=SimpleNamespace(
            workflow_configurations={"agent_principal_id": "pas-un-nombre"}, workflow_json={}
        ),
    )
    monkeypatch.setattr(db_client, "get_workflow", AsyncMock(return_value=agent))
    monkeypatch.setattr(
        db_client, "get_workflow_runs_by_workflow_id", AsyncMock(return_value=([], 0))
    )
    resultat = await carte.carte_de_l_agent(3, 1)
    assert [a["id"] for a in resultat["agents"]] == [3]
