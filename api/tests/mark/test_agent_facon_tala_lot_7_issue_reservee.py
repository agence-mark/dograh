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
