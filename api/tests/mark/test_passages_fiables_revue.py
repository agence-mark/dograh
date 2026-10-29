"""[.mark] passages-fiables : les corrections de la revue `revue-archi-secu` (un test par correction, rouge avant, vert après).

| Test | Ce qu'il prouve |
|---|---|
| 1 arbitre | deux demandes dans la même étape : la plus récente seule compte, l'ancienne est annulée et n'écrit rien |
| 2 interruption | interrompue pendant l'attente du greffier : aucun passage ; interrompue pendant le passage : il va au bout |
| 3 notice | une notice dont l'étape d'arrivée n'est plus celle où l'on est ne sort jamais plus tard |
| 4 bornes | délai du passage 0 à 10 s (lecture et schéma), seuil de l'arbitre 0 à 1 |
| 5 mail | la case de l'appel (principal) prime sur celle du spécialisé actif |
| 6 rejeu | au rejeu, aucun transfert ne part par les chemins « sortie » et « équipe » |
| 7 tri | le filtre par statut passe avant la coupe de la page |
| 8 rejeu | un test sans organisation ne désactive plus le contrôle d'organisation |
"""

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext
from pydantic import ValidationError

from api.services.tests_rejouables.modele import ErreurTestRejouable, TestRejouable
from api.services.tests_rejouables.rejeu import rejouer
from api.services.tests_rejouables.simulation import CLE_REJEU
from api.services.tri import alertes
from api.services.workflow import passage_sur_la_fiche as passage
from api.services.workflow.arbitre import ArbitreDuPassage
from api.tests.mark.test_passages_fiables_arbitre import ECHANGES, Collecteur, _reponse
from api.tests.mark.test_passages_fiables_fiche import (
    GreffierFactice,
    _etape,
    _etape_option_2,
    _noeud,
    graphe,
    monter,
)


class _Contexte:
    def __init__(self, messages):
        self._m = messages

    def get_messages(self):
        return self._m


# --------------------------------------------------------------------------- #
# 1. L'arbitre : une décision périmée ne compte jamais
# --------------------------------------------------------------------------- #


ECHANGES_LENTS = [*ECHANGES[:1], {"role": "user", "content": "LENT : je voudrais continuer."}]


class FauxEnDeuxTemps:
    """La première demande est lente (et dit « refus »), la seconde rapide (et dit « suite »)."""

    async def __call__(self, service, systeme, message, schema=None):
        if "LENT" in message:
            await asyncio.sleep(0.3)
            return _reponse("refus", 0.99), {"jetons_entree": 1, "jetons_sortie": 1}
        return _reponse("suite", 0.99), {"jetons_entree": 1, "jetons_sortie": 1}


@pytest.mark.asyncio
async def test_1_la_demande_la_plus_recente_seule_compte(monkeypatch):
    monkeypatch.setattr("api.services.pipecat.greffier.interroger", FauxEnDeuxTemps())
    harness = await monter(
        graphe({"qui_decide_du_passage": "libre", "champs_etape": "nom,objet"}), greffier=GreffierFactice()
    )
    try:
        engine = harness.engine
        engine.arbitre_service = object()
        engine.collecteur_de_cout = Collecteur()
        engine.arbitre = ArbitreDuPassage(engine)
        jeton = engine.jeton_de_visite()  # le même jeton pour les deux paroles
        noeud = engine.active_agent.current_node
        assert engine.arbitre.lancer(jeton, noeud, ECHANGES_LENTS)
        premiere = engine.arbitre._tache
        assert engine.arbitre.lancer(jeton, noeud, ECHANGES)
        decision = await engine.arbitre.resultat(jeton)
        assert decision is not None and decision.choix == "suite" and decision.parole == 2
        await asyncio.sleep(0.5)  # la première aurait fini : elle est annulée, elle n'écrit rien
        assert premiere.cancelled()
        assert engine.arbitre._decision.choix == "suite"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# 2. L'option 2 : l'interruption ne coupe pas le passage
# --------------------------------------------------------------------------- #


class GreffierLent:
    async def rattraper(self, delai):
        await asyncio.sleep(5)
        return True


@pytest.mark.asyncio
async def test_2_interrompue_pendant_l_attente_aucun_passage():
    harness = await monter(graphe(_etape_option_2()), fiche={"nom": "Lemaire"}, greffier=GreffierLent())
    try:
        engine = harness.engine
        contexte = _Contexte([{"role": "user", "content": "une demande"}])
        tache = asyncio.create_task(passage.avant_la_requete(engine, engine.active_agent.llm, contexte))
        await asyncio.sleep(0.05)
        tache.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tache
        await asyncio.sleep(0.05)
        assert _etape(engine) == "etape" and passage.CLE_PASSAGES not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_2_interrompue_pendant_le_passage_il_va_au_bout():
    greffier = GreffierFactice()
    harness = await monter(graphe(_etape_option_2()), fiche={"nom": "Lemaire"}, greffier=greffier)
    try:
        engine = harness.engine
        greffier.pendant = lambda: engine._gathered_context.__setitem__("objet", "une demande")
        origine = engine.prendre_porte_ecrite

        async def lente(*args, **kwargs):
            await asyncio.sleep(0.2)
            return await origine(*args, **kwargs)

        engine.prendre_porte_ecrite = lente
        contexte = _Contexte([{"role": "user", "content": "une demande"}])
        tache = asyncio.create_task(passage.avant_la_requete(engine, engine.active_agent.llm, contexte))
        await asyncio.sleep(0.08)  # le passage est en cours
        tache.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tache
        await asyncio.sleep(0.4)
        assert _etape(engine) == "suite"
        assert engine._gathered_context[passage.CLE_PASSAGES][-1]["resultat"] == "prise"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# 3. La notice liée à l'étape d'arrivée
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_3_la_notice_est_montree_tant_que_l_etape_d_arrivee_est_la_bonne():
    harness = await monter(graphe(), fiche={"nom": "Lemaire", "objet": "une demande"}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        arete = next(a for a in engine.active_agent.current_node.out_edges if a.target == "suite")
        assert await passage.passer(
            engine, arete, raison="fiche", jeton=engine.jeton_de_visite(), dit="D'accord.", option=1
        )
        ctx = LLMContext(messages=[{"role": "user", "content": "bonjour"}])
        assert passage.contexte_avec_la_notice(engine, ctx) is not None
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_3_passage_puis_changement_d_etape_la_notice_ne_sort_jamais_plus_tard():
    harness = await monter(graphe(), fiche={"nom": "Lemaire", "objet": "une demande"}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        arete = next(a for a in engine.active_agent.current_node.out_edges if a.target == "suite")
        assert await passage.passer(
            engine, arete, raison="fiche", jeton=engine.jeton_de_visite(), dit="D'accord.", option=1
        )
        await engine.set_node("reprise")  # la requête de l'étape d'arrivée n'a jamais eu lieu (retour au principal...)
        ctx = LLMContext(messages=[{"role": "user", "content": "x"}])
        assert passage.contexte_avec_la_notice(engine, ctx) is None
        assert engine._notice_de_passage is None  # et ne ressortira pas plus tard
        await engine.set_node("suite")
        assert passage.contexte_avec_la_notice(engine, ctx) is None
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# 4. Les bornes côté serveur
# --------------------------------------------------------------------------- #


def _noeud_regle(**donnees):
    return SimpleNamespace(data=SimpleNamespace(**donnees))


def test_4_le_delai_du_passage_est_borne_a_dix_secondes():
    assert passage.reglages_du_passage(_noeud_regle(delai_du_passage=99)).delai == 10.0
    assert passage.reglages_du_passage(_noeud_regle(delai_du_passage=4)).delai == 4.0
    assert passage.reglages_du_passage(_noeud_regle(delai_du_passage=-3)).delai == passage.DELAI_PAR_DEFAUT


def test_4_le_seuil_hors_de_zero_un_retombe_au_defaut():
    assert passage.reglages_du_passage(_noeud_regle(seuil_de_l_arbitre=7)).seuil == passage.SEUIL_PAR_DEFAUT
    assert passage.reglages_du_passage(_noeud_regle(seuil_de_l_arbitre=0.5)).seuil == 0.5


def test_4_le_schema_refuse_un_delai_ou_un_seuil_hors_bornes():
    with pytest.raises(ValidationError):
        _noeud("etape", "startCall", "Collecte", delai_du_passage=99)
    with pytest.raises(ValidationError):
        _noeud("etape", "startCall", "Collecte", seuil_de_l_arbitre=1.5)
    _noeud("etape", "startCall", "Collecte", delai_du_passage=10, seuil_de_l_arbitre=1)  # les bornes passent


# --------------------------------------------------------------------------- #
# 5. Le mail d'alerte : la case de l'appel d'abord
# --------------------------------------------------------------------------- #


def test_5_appel_fini_chez_un_specialise_la_case_du_principal_allume_le_mail():
    moteur = SimpleNamespace(
        _gathered_context={},
        reglages_appel={"alertes_par_mail": True},
        active_agent=SimpleNamespace(reglages={"laisser_la_parole": False}),
    )
    assert alertes.mail_allume(moteur) is True
    moteur.reglages_appel = {}
    assert alertes.mail_allume(moteur) is False
    moteur.active_agent.reglages = {"alertes_par_mail": True}  # à défaut, l'agent actif
    assert alertes.mail_allume(moteur) is True


# --------------------------------------------------------------------------- #
# 6. Rejeu : aucun transfert direct
# --------------------------------------------------------------------------- #


def _manager(moteur, partis):
    def creer(outil, nom):
        async def reel(params):
            partis.append(nom)
            await params.result_callback({"status": "transfer_success"})

        return reel

    return SimpleNamespace(
        _engine=moteur,
        get_organization_id=AsyncMock(return_value=1),
        _create_transfer_call_handler=creer,
    )


@dataclass
class _Params:
    arguments: dict
    result_callback: object
    llm: object = None
    tool_call_id: object = None


def _personne():
    return SimpleNamespace(cle="p1", prenom="Léa", nom="Martin", telephone="+33100000000", joignable_par_transfert=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("rejeu", [True, False])
async def test_6_sortie_transfert_au_rejeu_rien_ne_part(monkeypatch, rejeu):
    from api.services.phrases import sorties

    partis = []
    moteur = SimpleNamespace(_gathered_context={CLE_REJEU: True} if rejeu else {}, _call_context_vars={})
    moteur._custom_tool_manager = _manager(moteur, partis)
    monkeypatch.setattr("api.services.equipe.appel.cles_de_lappel", lambda ctx: (["p1"], None))
    monkeypatch.setattr("api.services.equipe.diriger.personne_de_la_copie", AsyncMock(return_value=_personne()))
    await sorties.transferer_a(moteur, "p1")
    assert partis == ([] if rejeu else ["sortie_transfert"])


@pytest.mark.asyncio
@pytest.mark.parametrize("rejeu", [True, False])
async def test_6_equipe_diriger_au_rejeu_rien_ne_part(monkeypatch, rejeu):
    from api.services.equipe import diriger

    partis = []
    moteur = SimpleNamespace(
        _gathered_context={CLE_REJEU: True} if rejeu else {},
        _call_context_vars={},
        queue_text_message=AsyncMock(),
    )
    manager = _manager(moteur, partis)
    monkeypatch.setattr(diriger, "cles_de_lappel", lambda ctx: (["p1"], None))
    monkeypatch.setattr(diriger, "personne_de_la_copie", AsyncMock(return_value=_personne()))
    outil = SimpleNamespace(tool_uuid=None, name="diriger", definition={"config": {}})
    params = _Params(arguments={"personne": "p1", "geste": "transferer"}, result_callback=AsyncMock())
    await diriger.creer_gestionnaire(manager, outil, "diriger")(params)
    assert partis == ([] if rejeu else ["diriger"])


# --------------------------------------------------------------------------- #
# 7. Le filtre par statut avant la page
# --------------------------------------------------------------------------- #


async def test_7_la_page_filtree_n_est_jamais_vide_quand_des_lignes_existent(
    db_session, async_session, test_client_factory
):
    from api.tests.mark.test_passages_fiables_signalements_et_alertes import FICHE, _monter, _run

    user, workflow = await _monter(db_session, async_session, dict(FICHE))
    avec = {"signalements": [{"source": "agent", "motif": "m", "categorie": "autre"}]}
    resolu = await _run(
        db_session, async_session, user, workflow, avec, annotations={"tri": {"agent:0": {"statut": "résolu"}}}
    )
    for _ in range(55):  # 55 runs plus récents, à trier : la première page de runs ne contient aucun « résolu »
        await _run(db_session, async_session, user, workflow, avec)
    async with test_client_factory(user) as client:
        page = (await client.get("/api/v1/tri", params={"statut": "résolu"})).json()
    assert [ligne["run_id"] for ligne in page["lignes"]] == [resolu.id]
    assert page["a_une_suite"] is False


# --------------------------------------------------------------------------- #
# 8. Rejeu sans organisation
# --------------------------------------------------------------------------- #


def _test_sans_organisation():
    return TestRejouable(
        nom="sans-organisation",
        replique="bonjour",
        critere={"type": "texte_present", "texte": "ALPHA"},
        historique=[{"role": "assistant", "texte": "Bonjour"}],
        etape=None,
        fiche={},
        organisation_id=None,
    )


@pytest.mark.asyncio
async def test_8_un_test_sans_organisation_ne_desactive_plus_le_controle(monkeypatch):
    monkeypatch.setattr("api.services.tests_rejouables.rejeu.refuser_si_protege", lambda agent: None)
    agent = SimpleNamespace(organization_id=5)
    monkeypatch.setattr(
        "api.services.tests_rejouables.rejeu.db_client.get_workflow_by_id", AsyncMock(return_value=agent)
    )
    # Ni test ni paramètre ne disent l'organisation : refus.
    with pytest.raises(ErreurTestRejouable, match="organisation"):
        await rejouer(_test_sans_organisation(), 1, 1)
    # Le paramètre dit une autre organisation que celle de l'agent : refus.
    with pytest.raises(ErreurTestRejouable, match="autre"):
        await rejouer(_test_sans_organisation(), 1, 1, organisation_id=9)
