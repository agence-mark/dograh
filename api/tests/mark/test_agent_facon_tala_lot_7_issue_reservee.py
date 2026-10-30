"""[.mark] agent-facon-tala, lot 7 (F3) : une issue de transfert ne sort que d'un vrai résultat de l'outil de transfert.

Banc 1 (runs 210, 211) : un appel sans aucun transfert a reçu l'issue « une personne du magasin a pris la main »,
choisie par le classement final sur une phrase d'annonce. Le classement ne doit ni voir ni rendre une issue que
l'outil de transfert pose lui-même à sa réussite.

| Test | Ce qu'il prouve |
|---|---|
| pures | les issues réservées viennent de la configuration des outils de transfert d'appel, d'eux seuls |
| invite | l'issue réservée n'est pas offerte au classement ; les autres le sont |
| classement | même si le modèle rend l'issue réservée, le classement ne la rend pas ; sans réservation, comme avant |
| lecture des outils | `issues_reservees` lit les outils par le lecteur donné et ne lève jamais |
"""

from types import SimpleNamespace

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext

from api.schemas.workflow_configurations import CallDispositionOption
from api.services.workflow.disposition_extraction import DispositionExtractionService
from api.services.workflow.issue_reservee import codes_reserves, issues_reservees, sans_les_reservees


def _liste(*codes):
    return [CallDispositionOption(code=c, description=f"Issue {c}.") for c in codes]


def _outil(categorie, disposition):
    return SimpleNamespace(category=categorie, definition={"config": {"call_disposition": disposition}})


def _service(options, reservees=None, rendu="transfert_ok"):
    contexte = LLMContext()
    contexte.set_messages([{"role": "user", "content": "Je veux parler à quelqu'un."}])
    service = DispositionExtractionService(
        llm=object(), context=contexte, options=options, template_context={}, reservees=reservees
    )
    invites = []

    async def inference(_contexte, messages, *, parent_context):
        invites.append(messages[0]["content"])
        return '{"call_disposition": "%s"}' % rendu

    service._run_inference = inference
    return service, invites


def test_les_issues_reservees_viennent_des_outils_de_transfert_d_appel_seuls():
    outils = [
        _outil("transfer_call", "transfert_ok"),
        _outil("transfer_call", None),
        _outil("http_api", "autre_issue"),
        _outil("transfer_agent", "encore_une"),
    ]
    assert codes_reserves(outils) == {"transfert_ok"}
    assert codes_reserves([]) == set()
    assert codes_reserves(None) == set()


def test_les_options_reservees_sortent_de_la_liste():
    options = _liste("devis", "transfert_ok")
    assert [o.code for o in sans_les_reservees(options, {"TRANSFERT_OK"})] == ["devis"]
    assert [o.code for o in sans_les_reservees(options, set())] == ["devis", "transfert_ok"]


@pytest.mark.asyncio
async def test_l_issue_reservee_n_est_pas_offerte_au_classement():
    async def reservees():
        return {"transfert_ok"}

    service, invites = _service(_liste("devis", "transfert_ok"), reservees, rendu="devis")
    assert await service.extract() == "devis"
    assert '"code": "devis"' in invites[0]
    assert "transfert_ok" not in invites[0]


@pytest.mark.asyncio
async def test_le_classement_ne_rend_jamais_l_issue_reservee_meme_si_le_modele_la_donne():
    async def reservees():
        return {"transfert_ok"}

    service, _ = _service(_liste("devis", "transfert_ok"), reservees, rendu="transfert_ok")
    assert await service.extract() is None  # sans le correctif : « transfert_ok » (run 210)


@pytest.mark.asyncio
async def test_sans_reservation_le_classement_est_celui_d_avant():
    service, invites = _service(_liste("devis", "transfert_ok"), None, rendu="transfert_ok")
    assert await service.extract() == "transfert_ok"
    assert "transfert_ok" in invites[0]


@pytest.mark.asyncio
async def test_une_lecture_en_echec_garde_la_liste_entiere():
    async def reservees():
        raise RuntimeError("base indisponible")

    service, _ = _service(_liste("devis", "transfert_ok"), reservees, rendu="devis")
    assert await service.extract() == "devis"


@pytest.mark.asyncio
async def test_issues_reservees_lit_les_outils_et_ne_leve_jamais():
    lus = []

    async def lire(uuids, organisation):
        lus.append((uuids, organisation))
        return [_outil("transfer_call", "transfert_ok")]

    assert await issues_reservees(["b", "a", "a"], 7, lire) == {"transfert_ok"}
    assert lus == [(["a", "b"], 7)]
    assert await issues_reservees([], 7, lire) == set()
    assert await issues_reservees(["a"], None, lire) == set()

    async def casse(uuids, organisation):
        raise RuntimeError("x")

    assert await issues_reservees(["a"], 7, casse) == set()


# --------------------------------------------------------------------------- #
# Tout le groupe, téléphone et clavier : l'appel finit sur un collègue sans outil de transfert
# --------------------------------------------------------------------------- #

from unittest.mock import AsyncMock, patch  # noqa: E402

PRINCIPAL, COLLEGUE_A, COLLEGUE_B, ORG = 10, 11, 12, 7


def _workflow(identifiant, reglages, uuids):
    definition = SimpleNamespace(workflow_json={"nodes": [{"id": "1", "data": {"tool_uuids": uuids}}]})
    return SimpleNamespace(id=identifiant, workflow_configurations=reglages, released_definition=definition, current_definition=None)


GROUPE = {
    PRINCIPAL: _workflow(PRINCIPAL, {"agents_specialises": [COLLEGUE_A, COLLEGUE_B]}, ["outil-de-transfert", "passation"]),
    COLLEGUE_A: _workflow(COLLEGUE_A, {"agent_principal_id": PRINCIPAL}, ["autre-outil"]),
    COLLEGUE_B: _workflow(COLLEGUE_B, {"agent_principal_id": PRINCIPAL}, []),
}
OUTILS = {
    "outil-de-transfert": _outil("transfer_call", "transfert_ok"),
    "passation": _outil("transfer_agent", "autre"),
    "autre-outil": _outil("http_api", None),
}


async def _get_workflow(identifiant, organization_id=None):
    return GROUPE[identifiant]


async def _get_tools(uuids, organization_id):
    return [OUTILS[u] for u in uuids if u in OUTILS]


@pytest.mark.asyncio
async def test_au_telephone_un_appel_qui_finit_sur_un_collegue_sans_transfert_reserve_l_issue_du_groupe():
    from api.services.workflow.pipecat_engine import PipecatEngine

    moteur = SimpleNamespace(
        active_agent=SimpleNamespace(workflow_id=COLLEGUE_B),
        _get_organization_id=AsyncMock(return_value=ORG),
        lire_outils=_get_tools,
    )
    with patch("api.services.workflow.pipecat_engine.db_client.get_workflow", new=_get_workflow):
        reservees = await PipecatEngine._issues_reservees_aux_transferts(moteur)
    assert reservees == {"transfert_ok"}  # sans le correctif : set() (seul le graphe de l'agent actif était lu)


@pytest.mark.asyncio
async def test_au_clavier_le_meme_groupe_donne_les_memes_issues_reservees():
    from api.services.workflow import text_chat_runner

    with (
        patch("api.services.workflow.text_chat_runner.db_client.get_workflow", new=_get_workflow),
        patch("api.services.workflow.text_chat_runner.db_client.get_tools_by_uuids", new=_get_tools),
    ):
        depuis_un_collegue = await text_chat_runner.issues_reservees_du_clavier(COLLEGUE_B, ORG)
        depuis_le_principal = await text_chat_runner.issues_reservees_du_clavier(PRINCIPAL, ORG)
    assert depuis_un_collegue == depuis_le_principal == {"transfert_ok"}


@pytest.mark.asyncio
async def test_un_agent_seul_ne_lit_que_ses_outils_et_une_lecture_en_echec_ne_reserve_rien():
    from api.services.workflow.issue_reservee import uuids_des_outils_du_groupe

    seul = _workflow(99, {}, ["outil-de-transfert"])

    async def lire(identifiant, organisation):
        return seul

    assert await uuids_des_outils_du_groupe(99, ORG, lire) == ["outil-de-transfert"]

    async def casse(identifiant, organisation):
        raise RuntimeError("base indisponible")

    assert await uuids_des_outils_du_groupe(99, ORG, casse) == []
