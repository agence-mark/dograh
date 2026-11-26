"""[.mark] Partie 1, lot 8a (C4, 115, 114) : la fin d'un tour et la fin de l'appel sont des crochets des modules, à la voix comme au clavier.

Ce qui tient : ``fin_de_l_appel`` est jouée UNE fois par fin (le rejouer ne fait rien de plus) pour la fin d'un montage tombé, pour un tour qui termine la partie au clavier et pour
une fin demandée ou par inactivité ; un tour en échec ne finit pas la partie ; la connexion de l'appel à la base du client est fermée dans chaque cas (lot 5, D53).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm.exc import DetachedInstanceError

from api.services.modules import crochets
from api.services.pipecat import run_pipeline as RP
from api.services.restauration.appel_et_memoire import memoire_de_l_appel as M
from api.services.workflow import text_chat_runner as runner
from api.services.workflow import text_chat_session_service as service


class _Connexion:
    def __init__(self):
        self.fermee = False

    def is_closed(self):
        return self.fermee

    async def close(self):
        self.fermee = True


@pytest.fixture
def appel_ouvert():
    """Un appel suivi (run 777) dont la connexion est comptée ; vidé à la sortie."""
    connexion = _Connexion()
    M._APPELS["777"] = M.AppelOuvert("base_essai", connexion=connexion)
    yield connexion
    M._APPELS.pop("777", None)


@pytest.fixture
def fins(monkeypatch):
    """Chaque ``fin_de_l_appel`` jouée, avec la vraie fin derrière (ce que la restauration y fait)."""
    jouees: list = []
    vraie = crochets.fin_de_l_appel

    async def espionne(fin):
        jouees.append(fin)
        await vraie(fin)

    monkeypatch.setattr(crochets, "fin_de_l_appel", espionne)
    return jouees


# ---- la voix : l'échec du montage (115)


async def test_un_montage_qui_tombe_joue_la_fin_de_l_appel_avec_l_identifiant_nomme(monkeypatch, fins, appel_ouvert):
    recus: list = []

    async def corps(*args, **kwargs):
        recus.append((args, kwargs))
        raise RuntimeError("montage en échec")

    monkeypatch.setattr(RP, "_run_pipeline_corps", corps)
    with pytest.raises(RuntimeError):
        await RP._run_pipeline_impl(None, 1, 777, 1, organization_id=7)
    assert [(f.run_id, f.fiche, f.organization_id) for f in fins] == [(777, None, 7)]
    assert appel_ouvert.fermee and M.appel_ouvert(777) is None
    assert recus == [((None, 1, 777, 1), {"organization_id": 7})]  # les arguments passent tels quels au corps


async def test_l_identifiant_de_l_appel_se_lit_par_son_nom_jamais_par_sa_position(monkeypatch, fins):
    async def corps(*_a, **_k):
        raise RuntimeError("montage en échec")

    monkeypatch.setattr(RP, "_run_pipeline_corps", corps)
    with pytest.raises(RuntimeError):
        await RP._run_pipeline_impl(transport=None, workflow_id=1, workflow_run_id=555, user_id=1)
    assert [f.run_id for f in fins] == [555]


# ---- le clavier : la fin d'un tour


def _resultat(termine: bool):
    return SimpleNamespace(is_completed=termine, gathered_context={"fiche": 1})


async def _tour(monkeypatch, resultat):
    async def executer(**_k):
        if isinstance(resultat, Exception):
            raise resultat
        return resultat

    monkeypatch.setattr(runner, "_executer_le_tour", executer)
    return await runner.execute_text_chat_pending_turn(workflow_run_id=777, workflow_id=1, session_data={}, checkpoint=None)


async def test_un_tour_qui_termine_la_partie_joue_la_fin_de_l_appel_et_ferme_la_connexion(monkeypatch, fins, appel_ouvert):
    await _tour(monkeypatch, _resultat(True))
    assert [(f.run_id, f.fiche, f.au_clavier) for f in fins] == [(777, {"fiche": 1}, True)]
    assert appel_ouvert.fermee and M.appel_ouvert(777) is None


async def test_un_tour_ordinaire_garde_l_appel_pour_le_tour_suivant(monkeypatch, fins, appel_ouvert):
    await _tour(monkeypatch, _resultat(False))
    assert fins == [] and not appel_ouvert.fermee and M.appel_ouvert(777) is not None  # la connexion est gardée entre deux tours (clôture A5)
    assert M.appel_ouvert(777).au_clavier is True


async def test_un_tour_en_echec_ferme_la_connexion_mais_ne_finit_pas_la_partie(monkeypatch, fins, appel_ouvert):
    with pytest.raises(RuntimeError):
        await _tour(monkeypatch, RuntimeError("le tour a levé"))
    assert fins == [] and appel_ouvert.fermee


# ---- le clavier : la fin demandée ou par inactivité (un seul point d'entrée, ``complete_text_chat_session``)


class _RunDetache:
    """Le ``workflow_run`` tel que le chargent les trois appelants de la fin (``get_workflow_run_text_session``) : ``definition`` n'est pas chargée, la lire lève (objet détaché)."""

    def __init__(self, terminee):
        self.is_completed = terminee
        self.workflow_id = 5
        self.workflow = SimpleNamespace(organization_id=7)
        self.mode = "textchat"

    @property
    def definition(self):
        raise DetachedInstanceError("definition n'est pas chargée")


def _session(run_id=777, terminee=False):
    workflow_run = _RunDetache(terminee)
    return SimpleNamespace(
        workflow_run=workflow_run, workflow_run_id=run_id, revision=2, session_data={}, checkpoint={"gathered_context": {"panier": "en cours"}}, updated_at=None, created_at=None
    )


@pytest.fixture
def fin_de_session(monkeypatch):
    """Tout ce qui touche la base ou le modèle est remplacé ; reste le vrai ``complete_text_chat_session`` et ses crochets."""
    ecritures: list = []

    async def ecrire(run_id, **kwargs):
        ecritures.append(run_id)

    monkeypatch.setattr(service, "extract_text_chat_final_variables", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "extract_text_chat_final_disposition", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "map_disposition", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_build_text_chat_completion_write", lambda **_k: {})
    monkeypatch.setattr(service.db_client, "complete_workflow_run_text_session", ecrire)
    monkeypatch.setattr(service, "_upload_text_chat_transcript", AsyncMock())
    monkeypatch.setattr(service, "_enqueue_text_chat_completion", AsyncMock())
    monkeypatch.setattr(service, "_reload_text_chat_session", AsyncMock(return_value="relue"))
    return ecritures


async def test_une_fin_demandee_joue_la_fin_de_l_appel_une_fois_avec_la_fiche_du_point_de_reprise(fin_de_session, fins, appel_ouvert):
    await service.complete_text_chat_session(run_id=777, text_session=_session(), expected_revision=2)
    assert [(f.run_id, f.fiche, f.organization_id, f.au_clavier) for f in fins] == [(777, {"panier": "en cours"}, 7, True)]
    assert appel_ouvert.fermee and fin_de_session == [777]


async def test_une_fin_deja_faite_est_rejouee_sans_rien_de_plus(fin_de_session, fins, appel_ouvert):
    await service.complete_text_chat_session(run_id=777, text_session=_session(terminee=True), expected_revision=2)
    assert fins == [] and fin_de_session == []  # la partie est finie : le chemin idempotent sort avant


async def test_la_fin_est_jouee_apres_l_ecriture_pas_quand_un_tour_a_gagne_la_course(fin_de_session, fins, monkeypatch):
    from api.db.workflow_run_text_session_client import WorkflowRunTextSessionRevisionConflictError

    async def conflit(run_id, **_k):
        raise WorkflowRunTextSessionRevisionConflictError(expected_revision=2, actual_revision=3)

    monkeypatch.setattr(service.db_client, "complete_workflow_run_text_session", conflit)
    with pytest.raises(service.TextChatSessionRevisionConflictError):
        await service.complete_text_chat_session(run_id=777, text_session=_session(), expected_revision=2)
    assert fins == []  # la partie n'est pas finie : rien ne part


async def test_la_fin_par_inactivite_passe_par_le_meme_point(fin_de_session, fins, appel_ouvert, monkeypatch):
    from api.tasks import text_chat_inactivity

    monkeypatch.setattr(text_chat_inactivity.db_client, "get_organization_id_by_workflow_run_id", AsyncMock(return_value=7))
    monkeypatch.setattr(text_chat_inactivity.db_client, "get_workflow_run_text_session", AsyncMock(return_value=_session()))
    await text_chat_inactivity.complete_inactive_text_chat_session({}, run_id=777, expected_revision=2, completed_at_iso=datetime.now(UTC).isoformat())
    assert [f.run_id for f in fins] == [777] and appel_ouvert.fermee


async def test_un_point_de_reprise_illisible_n_empeche_ni_la_fin_ni_le_crochet(fin_de_session, fins, appel_ouvert):
    """Une fin ne dépend jamais du point de reprise : illisible, la fiche est ``None`` et la partie finit quand même (lot 8a ne touche pas ce filet)."""
    session = _session()
    session.checkpoint = {"messages": 5, "gathered_context": 3}
    await service.complete_text_chat_session(run_id=777, text_session=session, expected_revision=2)
    assert [(f.run_id, f.fiche) for f in fins] == [(777, None)] and appel_ouvert.fermee and fin_de_session == [777]


async def test_une_fin_ne_lit_pas_la_definition_d_un_run_detache_et_va_jusqu_au_bout(fin_de_session, fins, appel_ouvert):
    """R1 : la définition n'est pas chargée par les appelants de la fin ; la lire ne doit pas couper la fin (transcription, mise en file) ni le crochet."""
    await service.complete_text_chat_session(run_id=777, text_session=_session(), expected_revision=2)
    assert service._upload_text_chat_transcript.await_count == 1 and service._enqueue_text_chat_completion.await_count == 1
    assert [(f.run_id, f.run_configs) for f in fins] == [(777, None)] and appel_ouvert.fermee


# ---- la fermeture de la connexion de l'appel ne dépend d'aucun interrupteur (R2)


async def test_la_connexion_de_l_appel_est_fermee_meme_commande_coupee(appel_ouvert):
    await crochets.fin_de_l_appel(crochets.FinDeLAppel(777, {"fiche": 1}, 7, {"commande_sur_catalogue": False}))
    assert appel_ouvert.fermee and M.appel_ouvert(777) is None


async def test_la_connexion_de_l_appel_est_fermee_meme_commande_coupee_au_clavier(appel_ouvert):
    await crochets.fin_de_l_appel(crochets.FinDeLAppel(777, {"fiche": 1}, 7, {"commande_sur_catalogue": False}, au_clavier=True))
    assert appel_ouvert.fermee and M.appel_ouvert(777) is None
