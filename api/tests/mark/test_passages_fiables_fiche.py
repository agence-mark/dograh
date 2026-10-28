"""[.mark] passages-fiables, lot A : le passage d'étape sur la fiche, et le décideur unique de fin de tour.

Plan `Labo-agent-vocal/plans/passages-fiables/` (§ 6, § 12 bis R2/R3/R6, § 12 ter L0-2 à L0-6). Ces tests passent par le
VRAI moteur (banc fendu de `test_agent_transfer.py`) ; seuls les modèles, la voix et la base sont remplacés.

| Test | Ce qu'il prouve |
|---|---|
| collecte complète | la fiche est complète : le code prend la première porte sans condition, l'étape d'arrivée reparle |
| à confirmer | un champ « à confirmer » : pas de passage |
| agent déjà passé | l'agent a pris sa porte pendant sa réponse : le code ne passe pas par-dessus |
| refus | `champ = refusé` : la porte du refus, pas celle de la suite |
| retour | la personne change d'avis après un passage : la porte retour marche |
| mode agent | étape en mode `agent` : rien lu, rien posé, trace absente (comportement d'avant) |
| personne reparle | la personne parle pendant l'attente du greffier : aucun passage |
| une porte | deux décideurs vrais le même tour : une seule porte, celle de la fiche |
| jeton | une décision née sous une autre visite d'étape est jetée et tracée ; le même retour dans la même étape change le jeton |
| greffier muet | le greffier ne répond pas à temps : aucun passage, l'appel continue |
| option 2 | un seul champ manquant : le passage a lieu avant la requête, sans relance ; au délai, l'option 1 joue ; jamais vers une fin |
| notice | dans `test_passages_fiables_agnostique.py` (deux familles de cerveaux, par les trames) |
| filet déplacé | le filet de fin passe d'abord dans le décideur ; sa porte interdit la fiche et la sortie d'impasse |
| impasse | les signes de l'impasse se comptent, sa sortie est interdite quand une porte est prise |
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from api.services.workflow import decideur_de_fin_de_tour as decideur
from api.services.workflow import passage_sur_la_fiche as passage
from api.services.workflow.dto import (
    AgentNodeData,
    ConditionDePorteDTO,
    EdgeDataDTO,
    EndCallNodeData,
    Position,
    ReactFlowDTO,
    RFEdgeDTO,
    RFNodeDTO,
    StartCallNodeData,
)
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.test_agent_transfer import TransferHarness
from pipecat.tests import MockLLMService

FICHE_REGLAGES = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        {"nom": "objet", "origine": "dicte", "description": "Ce que la personne demande"},
    ],
}


def _noeud(identifiant, type_, nom, **donnees):
    classe = {"startCall": StartCallNodeData, "endCall": EndCallNodeData}.get(type_, AgentNodeData)
    base = dict(name=nom, prompt=f"Tu es l'étape {nom}.", allow_interrupt=False, add_global_prompt=False)
    if type_ == "startCall":
        base["is_start"] = True
    if type_ == "endCall":
        base["is_end"] = True
    return RFNodeDTO(id=identifiant, type=type_, position=Position(x=0, y=0), data=classe(**{**base, **donnees}))


def _arete(source, cible, nom, condition=None):
    return RFEdgeDTO(
        id=f"{source}-{cible}",
        source=source,
        target=cible,
        data=EdgeDataDTO(
            label=nom,
            condition=f"Quand {nom}.",
            condition_sur_la_fiche=ConditionDePorteDTO(**condition) if condition else None,
        ),
    )


def graphe(etape: dict | None = None, *, vers_la_fin: bool = False, refus: bool = True) -> WorkflowGraph:
    """Une étape de départ, une suite (qui a une porte retour vers la reprise et une fin), un refus."""
    reglages = {"champs_etape": "nom,objet", **({"qui_decide_du_passage": "collecte"} if etape is None else etape)}
    noeuds = [
        _noeud("etape", "startCall", "Collecte", **reglages),
        _noeud("suite", "agentNode", "Suite"),
        *([_noeud("refus", "agentNode", "Refus")] if refus else []),
        _noeud("reprise", "agentNode", "Reprise"),
        _noeud("fin", "endCall", "Fin"),
    ]
    aretes = []
    if refus:
        aretes.append(_arete("etape", "refus", "Refus", {"champ": "objet", "vaut": "refusé"}))
    if vers_la_fin:
        # La suite reste atteignable, par une condition jamais vraie ; la première porte sans condition mène à la fin.
        aretes.append(_arete("etape", "suite", "Autre", {"champ": "nom", "vaut": "jamais vrai"}))
    aretes.append(_arete("etape", "fin" if vers_la_fin else "suite", "Suite"))
    aretes.append(_arete("suite", "reprise", "Retour"))
    if not vers_la_fin:
        aretes.append(_arete("suite", "fin", "Fin"))
    if refus:
        aretes.append(_arete("refus", "fin", "Fin du refus"))
    aretes.append(_arete("reprise", "fin", "Fin de la reprise"))
    return WorkflowGraph(ReactFlowDTO(nodes=noeuds, edges=aretes))


class GreffierFactice:
    def __init__(self, reponse=True, pendant=None):
        self.reponse, self.pendant, self.appels = reponse, pendant, []

    async def rattraper(self, delai):
        self.appels.append(delai)
        if self.pendant:
            self.pendant()
        return self.reponse


async def monter(g: WorkflowGraph | None = None, *, fiche: dict | None = None, greffier=None):
    harness = TransferHarness()
    g = g or graphe()
    await harness.build(
        source_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
        destination_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
        source_workflow=g,
        destination_workflow=g,
    )
    engine = harness.engine
    engine._fiche = ReglagesFiche.depuis(dict(FICHE_REGLAGES))
    engine._gathered_context.update(fiche or {})
    engine.greffier = greffier
    await harness.start()
    await engine.set_node("etape")
    # Pas de pipeline réel : on observe la relance.
    engine.active_agent.queue_frame = AsyncMock()
    return harness


def _etape(engine):
    return engine.active_agent.current_node.id


def _complete():
    return {"nom": "Lemaire", "objet": "une demande"}


async def _fin_de_reponse(engine, texte="Très bien, merci."):
    """Ce que l'agrégateur de l'assistant fait : l'état et le jeton au début, puis le décideur à la fin."""
    depart, jeton = engine.etat_pour_le_filet(), engine.jeton_de_visite()
    return await decideur.decider(engine, texte, depart, jeton), depart, jeton


# --------------------------------------------------------------------------- #
# Le passage sur la fiche
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_collecte_complete_le_code_prend_la_porte_et_l_etape_d_arrivee_reparle():
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche"
        assert _etape(engine) == "suite"
        engine.active_agent.queue_frame.assert_awaited()  # relancer=True : l'étape d'arrivée parle
        trace = engine._gathered_context[passage.CLE_PASSAGES]
        assert len(trace) == 1 and trace[0]["raison"] == "fiche" and trace[0]["resultat"] == "prise"
        assert trace[0]["porte"] == "suite" and trace[0]["vers"] == "Suite" and trace[0]["option"] == 1
        assert trace[0]["condition"] == {"type": "etape_complete", "implicite": True}
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_un_champ_manquant_ou_a_confirmer_pas_de_passage():
    for fiche in (
        {"nom": "Lemaire"},  # un champ manque
        {**_complete(), "fiche_etat": {"nom": {"sure": False}}},  # encore à confirmer
    ):
        harness = await monter(fiche=fiche, greffier=GreffierFactice())
        try:
            engine = harness.engine
            qui, _, _ = await _fin_de_reponse(engine)
            assert qui is None and _etape(engine) == "etape"
            assert passage.CLE_PASSAGES not in engine._gathered_context
        finally:
            await harness.stop()


@pytest.mark.asyncio
async def test_l_agent_a_deja_pris_sa_porte_le_code_ne_passe_pas_par_dessus():
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        depart, jeton = engine.etat_pour_le_filet(), engine.jeton_de_visite()
        await engine.prendre_porte_ecrite("suite")  # l'agent prend sa porte pendant sa réponse
        assert _etape(engine) == "suite"
        engine.active_agent.queue_frame.reset_mock()
        qui = await decideur.decider(engine, "Très bien.", depart, jeton)
        assert qui is None and _etape(engine) == "suite"
        engine.active_agent.queue_frame.assert_not_awaited()
        assert passage.CLE_PASSAGES not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_champ_vaut_refuse_la_porte_du_refus_pas_celle_de_la_suite():
    harness = await monter(fiche={"nom": "Lemaire", "objet": "refusé"}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche" and _etape(engine) == "refus"
        trace = engine._gathered_context[passage.CLE_PASSAGES][0]
        assert trace["porte"] == "refus" and trace["condition"]["champ"] == "objet"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_personne_change_d_avis_apres_le_passage_la_porte_retour_marche():
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        jeton_avant = engine.jeton_de_visite()
        await _fin_de_reponse(engine)
        assert _etape(engine) == "suite"
        # Le code n'a rien fermé : la porte retour de l'étape d'arrivée est toujours là.
        assert await engine.prendre_porte_ecrite("retour") == "prise"
        assert _etape(engine) == "reprise"
        assert engine.jeton_de_visite() != jeton_avant
        # Revenir dans la même étape change aussi le jeton (R2) : le rang d'entrée compte.
        jeton_dans_l_etape = engine.jeton_de_visite()
        await engine.set_node("reprise")
        assert engine.jeton_de_visite()[:2] == jeton_dans_l_etape[:2] and engine.jeton_de_visite() != jeton_dans_l_etape
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_etape_en_mode_agent_comportement_d_avant():
    harness = await monter(graphe({}), fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        llm = engine.active_agent.llm
        assert not getattr(llm, "_mark_passage_crochets", False)  # le service n'est pas touché
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui is None and _etape(engine) == "etape"
        assert passage.CLE_PASSAGES not in engine._gathered_context
        assert engine.greffier.appels == []  # le greffier n'est pas attendu pour rien
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_personne_reparle_pendant_l_attente_du_greffier_aucun_passage():
    holder = {}

    def la_personne_parle():
        holder["engine"].call_monitor._user_turn_active = True

    greffier = GreffierFactice(pendant=la_personne_parle)
    harness = await monter(fiche=_complete(), greffier=greffier)
    try:
        engine = harness.engine
        holder["engine"] = engine
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui is None and _etape(engine) == "etape"
        assert greffier.appels  # il a bien attendu
        engine.active_agent.queue_frame.assert_not_awaited()
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_le_greffier_ne_repond_pas_a_temps_aucun_passage_et_l_appel_continue():
    greffier = GreffierFactice(reponse=False)
    harness = await monter(fiche=_complete(), greffier=greffier)
    try:
        engine = harness.engine
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui is None and _etape(engine) == "etape"
        trace = engine._gathered_context[passage.CLE_PASSAGES]
        assert trace[0]["resultat"] == "greffier_sans_reponse"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_une_decision_nee_sous_une_autre_visite_est_jetee_et_tracee():
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        jeton = engine.jeton_de_visite()
        arete = engine.active_agent.current_node.out_edges[-1]
        await engine.set_node("etape")  # de retour dans la même étape : autre visite
        assert engine.jeton_de_visite()[:2] == jeton[:2] and engine.jeton_de_visite() != jeton
        assert not await passage.passer(engine, arete, raison="fiche", jeton=jeton)
        assert _etape(engine) == "etape"
        assert engine._gathered_context[passage.CLE_PASSAGES][-1]["resultat"] == "jetee_autre_visite"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_la_personne_parle_au_moment_de_passer_le_passage_est_jete():
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        arete = engine.active_agent.current_node.out_edges[-1]
        engine.call_monitor._user_turn_active = True
        assert not await passage.passer(engine, arete, raison="fiche", jeton=engine.jeton_de_visite())
        assert _etape(engine) == "etape"
        assert engine._gathered_context[passage.CLE_PASSAGES][-1]["resultat"] == "jetee_la_personne_parle"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Une seule porte par tour, le filet déplacé, l'impasse
# --------------------------------------------------------------------------- #


class ArbitreFactice:
    """Un arbitre qui a déjà répondu."""

    def __init__(self, decision):
        self.decision = decision

    async def resultat(self, jeton):
        return self.decision if self.decision is not None and self.decision.jeton == jeton else None

    def oublier(self):
        pass

    def lancer(self, *a, **k):
        return True


@pytest.mark.asyncio
async def test_deux_decideurs_vrais_le_meme_tour_une_seule_porte_celle_de_la_fiche():
    from api.services.workflow.arbitre import Decision

    harness = await monter(
        graphe({"qui_decide_du_passage": "choix", "champs_etape": "nom,objet"}),
        fiche={"nom": "Lemaire", "objet": "refusé"},
        greffier=GreffierFactice(),
    )
    try:
        engine = harness.engine
        # L'arbitre est sûr d'une AUTRE porte (« suite ») : la fiche, première dans l'ordre, a déjà gagné.
        engine.arbitre = ArbitreFactice(Decision(jeton=engine.jeton_de_visite(), choix="suite", confiance=0.99))
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche" and _etape(engine) == "refus"
        assert len(engine._gathered_context[passage.CLE_PASSAGES]) == 1
        assert "arbitre" not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_le_filet_est_le_premier_dans_l_ordre_et_interdit_la_fiche_et_la_sortie_d_impasse(monkeypatch):
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        engine.filet_de_fin = AsyncMock(return_value=True)
        vus = {}

        async def impasse(moteur, texte, depart, *, sortie_permise=True):
            vus["sortie_permise"] = sortie_permise
            return False

        monkeypatch.setattr(decideur, "fin_de_la_replique", impasse)
        qui, _, _ = await _fin_de_reponse(engine, "Au revoir.")
        assert qui == "filet" and vus == {"sortie_permise": False}
        assert _etape(engine) == "etape" and passage.CLE_PASSAGES not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_tout_eteint_la_sortie_d_impasse_reste_permise_comme_avant(monkeypatch):
    harness = await monter(graphe({}), fiche=_complete())
    try:
        engine = harness.engine
        vus = {}

        async def impasse(moteur, texte, depart, *, sortie_permise=True):
            vus["sortie_permise"] = sortie_permise
            return False

        monkeypatch.setattr(decideur, "fin_de_la_replique", impasse)
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui is None and vus == {"sortie_permise": True}
        assert passage.CLE_PASSAGES not in engine._gathered_context and "arbitre" not in engine._gathered_context
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_le_decideur_attend_les_portes_en_cours_avant_de_decider():
    harness = await monter(fiche=_complete(), greffier=GreffierFactice())
    try:
        engine = harness.engine
        ordre = []

        async def porte_en_cours():
            await asyncio.sleep(0.05)
            ordre.append("porte")

        tache = asyncio.get_running_loop().create_task(porte_en_cours())
        lot = {tache}
        engine.portes_du_post_scriptum.append(lot)
        await decideur.attendre_les_portes(engine)
        assert ordre == ["porte"]
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# L'option 2 : attendre le dernier champ
# --------------------------------------------------------------------------- #


class _Contexte:
    def __init__(self, messages):
        self._m = messages

    def get_messages(self):
        return self._m


def _etape_option_2(**plus):
    return {
        "qui_decide_du_passage": "collecte",
        "moment_du_passage": "attendre_le_dernier_champ",
        "champs_etape": "nom,objet",
        **plus,
    }


@pytest.mark.asyncio
async def test_option_2_un_seul_champ_manque_le_passage_a_lieu_avant_la_requete_sans_relance():
    greffier = GreffierFactice()
    harness = await monter(graphe(_etape_option_2()), fiche={"nom": "Lemaire"}, greffier=greffier)
    try:
        engine = harness.engine

        def le_greffier_note():
            engine._gathered_context["objet"] = "une demande"

        greffier.pendant = le_greffier_note
        llm = engine.active_agent.llm
        contexte = _Contexte([{"role": "assistant", "content": "Quelle est la demande ?"}, {"role": "user", "content": "une demande"}])
        assert await passage.avant_la_requete(engine, llm, contexte) is True
        assert _etape(engine) == "suite"
        engine.active_agent.queue_frame.assert_not_awaited()  # pas de relance : la requête qui part parle déjà dans la suite
        assert greffier.appels == [passage.DELAI_PAR_DEFAUT]
        trace = engine._gathered_context[passage.CLE_PASSAGES][0]
        assert trace["option"] == 2 and trace["resultat"] == "prise"
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_option_2_au_delai_l_option_1_joue_apres_la_reponse():
    greffier = GreffierFactice(reponse=False)
    harness = await monter(graphe(_etape_option_2(delai_du_passage=0.2)), fiche={"nom": "Lemaire"}, greffier=greffier)
    try:
        engine = harness.engine
        llm = engine.active_agent.llm
        contexte = _Contexte([{"role": "user", "content": "une demande"}])
        assert await passage.avant_la_requete(engine, llm, contexte) is False
        assert _etape(engine) == "etape" and greffier.appels == [0.2]
        # La passe du greffier finit après le délai : à la fin de la réponse, l'option 1 prend la porte.
        greffier.reponse = True
        engine._gathered_context["objet"] = "une demande"
        qui, _, _ = await _fin_de_reponse(engine)
        assert qui == "fiche" and _etape(engine) == "suite"
        assert engine._gathered_context[passage.CLE_PASSAGES][-1]["option"] == 1
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_option_2_jamais_vers_une_fin_ni_quand_plusieurs_champs_manquent_ni_apres_un_outil():
    # Vers une fin : l'option 1 jouera.
    greffier = GreffierFactice()
    harness = await monter(graphe(_etape_option_2(), vers_la_fin=True, refus=False), fiche=_complete(), greffier=greffier)
    try:
        engine = harness.engine
        engine._gathered_context.pop("objet")
        greffier.pendant = lambda: engine._gathered_context.update(objet="x")
        contexte = _Contexte([{"role": "user", "content": "x"}])
        assert await passage.avant_la_requete(engine, engine.active_agent.llm, contexte) is False
        assert _etape(engine) == "etape"
    finally:
        await harness.stop()
    # Deux champs manquent : le greffier n'est même pas attendu.
    greffier = GreffierFactice()
    harness = await monter(graphe(_etape_option_2()), fiche={}, greffier=greffier)
    try:
        engine = harness.engine
        contexte = _Contexte([{"role": "user", "content": "x"}])
        assert await passage.avant_la_requete(engine, engine.active_agent.llm, contexte) is False
        assert greffier.appels == []
        # Le dernier message est un résultat d'outil : ce n'est pas la réponse à la personne.
        engine._gathered_context["nom"] = "Lemaire"
        contexte = _Contexte([{"role": "user", "content": "x"}, {"role": "tool", "content": "ok"}])
        assert await passage.avant_la_requete(engine, engine.active_agent.llm, contexte) is False
        assert greffier.appels == []
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# Une session au clavier (R1) : les mêmes cas, par les vraies routes
# --------------------------------------------------------------------------- #


def definition_clavier(etape: dict):
    from api.tests.mark.test_passation_clavier import _arete as arete_json
    from api.tests.mark.test_passation_clavier import _noeud as noeud_json

    return {
        "nodes": [
            noeud_json("start", "startCall", "Collecte", "Tu prends le nom.", greeting_type="text", greeting="Bonjour.", **etape),
            noeud_json("suite", "agentNode", "Suite", "Tu continues."),
            noeud_json("end", "endCall", "Fin", "Fin."),
        ],
        "edges": [arete_json("start", "suite", "Suite"), arete_json("suite", "end", "Fin")],
    }


@pytest.mark.asyncio
async def test_session_clavier_la_collecte_complete_passe_a_la_suite_par_le_code(
    db_session, async_session, test_client_factory
):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide
    from api.tests.mark.test_clavier_porte_la_fiche import _noter

    etape = {"champs_etape": "nom", "qui_decide_du_passage": "collecte"}
    user, workflow = await _monter(db_session, async_session, FICHE, definition_clavier(etape))
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_vide(), _dit(_noter({"nom": "Lemaire"}, "n1"), _texte("Merci."), _texte("Voici la suite."))],
        ["je m'appelle Lemaire"],
    )
    fiche = reponses[-1]["checkpoint"]["gathered_context"]
    passes = fiche.get(passage.CLE_PASSAGES) or []
    assert [p["resultat"] for p in passes] == ["prise"], fiche
    assert passes[0]["etape"] == "Collecte" and passes[0]["vers"] == "Suite" and passes[0]["raison"] == "fiche"
    assert "Suite" in (fiche.get("nodes_visited") or []), fiche


@pytest.mark.asyncio
async def test_session_clavier_etape_en_mode_agent_rien_ne_change(db_session, async_session, test_client_factory):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter, _noter
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

    user, workflow = await _monter(
        db_session, async_session, FICHE, definition_clavier({"champs_etape": "nom"})
    )
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_vide(), _dit(_noter({"nom": "Lemaire"}, "n1"), _texte("Merci."))],
        ["je m'appelle Lemaire"],
    )
    fiche = reponses[-1]["checkpoint"]["gathered_context"]
    assert passage.CLE_PASSAGES not in fiche and "Suite" not in (fiche.get("nodes_visited") or []), fiche


def test_parite_le_decideur_est_branche_au_telephone_et_au_clavier_a_la_place_des_deux_anciens():
    from pathlib import Path

    racine = Path(passage.__file__).resolve().parents[1]
    for fichier in (racine / "pipecat" / "run_pipeline.py", racine / "workflow" / "text_chat_runner.py"):
        texte = fichier.read_text(encoding="utf-8")
        assert "brancher_le_decideur_de_fin_de_tour(engine, assistant_context_aggregator, service_arbitre)" in texte, fichier.name
        assert "brancher_le_filet_de_fin(" not in texte and "brancher_la_sortie_d_impasse(" not in texte, fichier.name


def test_le_schema_porte_les_reglages_de_l_etape_et_de_la_porte_et_un_agent_sans_reglage_ne_change_pas():
    from api.services.workflow.dto import sanitize_workflow_definition

    vide = {
        "nodes": [
            {"id": "a", "type": "agentNode", "position": {"x": 0, "y": 0},
             "data": {"name": "A", "prompt": "p", "qui_decide_du_passage": "", "moment_du_passage": "", "arbitre": None,
                      "delai_du_passage": None, "seuil_de_l_arbitre": ""}},
        ],
        "edges": [{"id": "e", "source": "a", "target": "b",
                   "data": {"label": "L", "condition": "c", "condition_sur_la_fiche": {"etape_complete": False, "champ": " "}}}],
    }
    propre = sanitize_workflow_definition(vide)
    assert propre["nodes"][0]["data"] == {"name": "A", "prompt": "p"}  # le JSON d'un agent qui n'y touche pas reste identique
    assert "condition_sur_la_fiche" not in propre["edges"][0]["data"]
    plein = sanitize_workflow_definition(
        {"nodes": [{"id": "a", "type": "agentNode", "position": {"x": 0, "y": 0},
                    "data": {"name": "A", "qui_decide_du_passage": "choix", "arbitre": False, "seuil_de_l_arbitre": 0.9}}],
         "edges": [{"id": "e", "source": "a", "target": "b",
                    "data": {"label": "L", "condition": "c", "condition_sur_la_fiche": {"champ": "x", "vaut": "y"}}}]}
    )
    assert plein["nodes"][0]["data"]["qui_decide_du_passage"] == "choix" and plein["nodes"][0]["data"]["arbitre"] is False
    assert plein["edges"][0]["data"]["condition_sur_la_fiche"] == {"champ": "x", "vaut": "y"}
    with pytest.raises(ValueError):
        AgentNodeData(name="A", prompt="p", qui_decide_du_passage="n'importe quoi")
