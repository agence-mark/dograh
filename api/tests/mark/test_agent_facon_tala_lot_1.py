"""[.mark] agent-facon-tala, lot 1 : la réplique qui n'est que le nom d'un outil (C1), le filet de fin (C2), l'impasse (C9).

| Test | Ce qu'il prouve |
|---|---|
| lecture | nom nu, habillé (tirets bas, italiques, ponctuation), avec arguments ``nom,{…}`` et ``nom_cle="…"`` |
| texte réel | une réplique qui contient du vrai texte en plus n'est pas touchée ; une porte écrite (« → nom ») reste une porte |
| flux | la réplique devient un appel d'outil, jamais dite ; la parole normale passe morceau par morceau |
| case éteinte | sans la case, le flux est celui d'avant, à l'octet |
| mixin | la case posée sur le service par ``preparer_la_requete`` (route de la requête, téléphone et clavier) agit sur le flux |
| texte d'équipe | « tu appelles l'outil » quand les sorties du collègue sont des outils |
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk, Choice, ChoiceDelta

from api.services.pipecat.texte_du_cerveau import (
    ATTRIBUT_OUTIL_ECRIT,
    FluxNettoye,
    TexteDuCerveauMixin,
    case_outil_ecrit,
    lire_un_outil_ecrit,
    poser_la_case_outil_ecrit,
)

COMMUN = {"id": "c", "created": 0, "model": "m", "object": "chat.completion.chunk"}
OUTILS = ["coordonnees", "retour", "fin", "passer_a_l_agent_infos"]


def _m(texte=None, fin=None):
    return ChatCompletionChunk(**COMMUN, choices=[Choice(index=0, delta=ChoiceDelta(content=texte), finish_reason=fin)])


class _Flux:
    def __init__(self, morceaux):
        self._morceaux = morceaux

    def __aiter__(self):
        async def gen():
            for m in self._morceaux:
                yield m

        return gen()


async def _lire(morceaux, outil_ecrit=True, outils=OUTILS, portes=False):
    return [m async for m in FluxNettoye(_Flux(morceaux), outils, portes, outil_ecrit=outil_ecrit)]


def _dit(sorties):
    return "".join((m.choices[0].delta.content or "") for m in sorties if m.choices)


def _appels(sorties):
    return [a for m in sorties if m.choices for a in (m.choices[0].delta.tool_calls or [])]


@pytest.mark.parametrize(
    "ecrit, nom",
    [
        ("coordonnees", "coordonnees"),
        ("_coordonnees_", "coordonnees"),
        ("*retour*", "retour"),
        ("__fin__.", "fin"),
        ("« fin »", "fin"),
        ("`retour`\n", "retour"),
        ("Retour", "retour"),
        ("passer_a_l_agent_infos", "passer_a_l_agent_infos"),
    ],
)
def test_le_nom_nu_ou_habille_est_lu(ecrit, nom):
    assert lire_un_outil_ecrit(ecrit, OUTILS) == (nom, "{}")


def test_les_arguments_sont_lus():
    assert lire_un_outil_ecrit('coordonnees,{"nom": "X"}', OUTILS) == ("coordonnees", '{"nom": "X"}')
    assert lire_un_outil_ecrit('_coordonnees_{"nom": "X"}', OUTILS) == ("coordonnees", '{"nom": "X"}')
    assert lire_un_outil_ecrit('coordonnees_demande="le nom"', OUTILS) == ("coordonnees", '{"demande": "le nom"}')
    assert lire_un_outil_ecrit('retour(motif="fini", suite="non")', OUTILS) == ("retour", '{"motif": "fini", "suite": "non"}')


@pytest.mark.parametrize(
    "texte",
    [
        "Je note vos coordonnees.",
        "fin de la conversation, merci",
        "finalement",
        "retour sous huit jours",
        "→ retour",
        "*(→ fin)*",
        "autre_chose",
        'coordonnees {"nom": "X"} et merci',
        "",
    ],
)
def test_du_vrai_texte_ou_une_porte_ecrite_n_est_pas_touche(texte):
    assert lire_un_outil_ecrit(texte, OUTILS) is None


async def test_la_replique_nom_d_outil_devient_l_appel_jamais_dit():
    for morceaux in (
        [_m(), _m("_coord"), _m("onnees_"), _m(fin="stop")],
        [_m("*retour*"), _m(fin="stop")],
        [_m("fin"), _m("."), _m(fin="stop")],
        [_m("coordonnees"), _m(',{"nom"'), _m(': "X"}'), _m(fin="stop")],
    ):
        sorties = await _lire(morceaux)
        assert _dit(sorties) == ""
        [appel] = _appels(sorties)
        assert appel.function.name in OUTILS
        assert [m.choices[0].finish_reason for m in sorties if m.choices][-1] == "tool_calls"


async def test_les_arguments_ecrits_arrivent_dans_l_appel():
    sorties = await _lire([_m("coordonnees"), _m(',{"nom": "X"}'), _m(fin="stop")])
    [appel] = _appels(sorties)
    assert json.loads(appel.function.arguments) == {"nom": "X"}


async def test_du_vrai_texte_est_rendu_tel_quel_et_la_parole_normale_part_aussitot():
    sorties = await _lire([_m("fin"), _m(" de la conversation."), _m(fin="stop")])
    assert _dit(sorties) == "fin de la conversation."
    assert not _appels(sorties)
    flux = [_m(), _m("Bonjour,"), _m(" que puis-je faire ?"), _m(fin="stop")]
    assert await _lire(flux) == flux  # aucun retard, aucun changement


async def test_une_porte_ecrite_reste_une_porte():
    sorties = await _lire([_m("→ retour\n"), _m("Au revoir."), _m(fin="stop")], portes=True)
    assert _dit(sorties) == "→ retour\nAu revoir."
    assert not _appels(sorties)


async def test_un_vrai_appel_deja_present_l_emporte_sans_doublon():
    from api.services.pipecat.texte_du_cerveau import _morceau_d_appel

    vrai = _morceau_d_appel(_m(), "retour", "{}")
    sorties = await _lire([_m("retour"), vrai, _m(fin="tool_calls")])
    assert _dit(sorties) == ""
    assert [a.function.name for a in _appels(sorties)] == ["retour"]


async def test_case_eteinte_le_flux_est_celui_d_avant():
    for morceaux in ([_m("_coordonnees_"), _m(fin="stop")], [_m("retour"), _m(fin="stop")]):
        sans = await _lire(morceaux, outil_ecrit=False)
        assert sans == morceaux
        assert not _appels(sans)


async def test_sans_outil_declare_rien_n_est_retenu():
    flux = [_m("retour"), _m(fin="stop")]
    assert await _lire(flux, outils=[]) == flux


class _Base:
    _settings = SimpleNamespace(system_instruction="Parle.")

    def __init__(self, morceaux):
        self._morceaux = morceaux

    async def get_chat_completions(self, context):
        return _Flux(self._morceaux)


class _Cerveau(TexteDuCerveauMixin, _Base):
    pass


def _contexte():
    outil = lambda nom: SimpleNamespace(name=nom)  # noqa: E731
    return SimpleNamespace(tools=SimpleNamespace(standard_tools=[outil(n) for n in OUTILS]), messages=[])


async def test_le_cerveau_suit_la_case_posee_sur_son_service():
    llm = _Cerveau([_m("_retour_"), _m(fin="stop")])
    # case jamais posée : comme avant
    flux = await llm.get_chat_completions(_contexte())
    assert _dit([m async for m in flux]) == "_retour_"
    setattr(llm, ATTRIBUT_OUTIL_ECRIT, True)
    sorties = [m async for m in await llm.get_chat_completions(_contexte())]
    assert _dit(sorties) == "" and [a.function.name for a in _appels(sorties)] == ["retour"]


def test_la_case_de_l_agent_actif_est_posee_sur_son_service():
    llm = SimpleNamespace()
    moteur = SimpleNamespace(active_agent=SimpleNamespace(reglages={"reconnaitre_un_outil_ecrit": True}), reglages_appel={})
    poser_la_case_outil_ecrit(moteur, llm)
    assert getattr(llm, ATTRIBUT_OUTIL_ECRIT) is True
    moteur.active_agent.reglages = {}
    poser_la_case_outil_ecrit(moteur, llm)
    assert getattr(llm, ATTRIBUT_OUTIL_ECRIT) is False
    assert case_outil_ecrit(SimpleNamespace(reglages={"reconnaitre_un_outil_ecrit": "oui"}), None) is False


# --- R1 : la vraie route de la requête (processeur posé autour du cerveau → cerveau) ----------------------------------


async def _par_la_route(case: bool, reponse: str):
    from api.services.pipecat.avant_la_requete import preparer_la_requete
    from api.tests.mark.test_passages_fiables_fiche import GreffierFactice, monter
    from pipecat.frames.frames import LLMContextFrame
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.tests import MockLLMService

    class Cerveau(TexteDuCerveauMixin, MockLLMService):
        pass

    cerveau = Cerveau(mock_steps=[MockLLMService.create_text_chunks(reponse, chunk_size=4)], chunk_delay=0)
    harness = await monter(None, fiche={}, greffier=GreffierFactice())
    try:
        engine = harness.engine
        engine.active_agent.llm = cerveau
        engine.active_agent.reglages = {"reconnaitre_un_outil_ecrit": True} if case else {}
        from pipecat.adapters.schemas.function_schema import FunctionSchema
        from pipecat.adapters.schemas.tools_schema import ToolsSchema

        outils = ToolsSchema(
            standard_tools=[FunctionSchema(name=nom, description="x", properties={}, required=[]) for nom in OUTILS]
        )
        contexte = LLMContext(messages=[{"role": "user", "content": "bonjour"}], tools=outils)
        await preparer_la_requete(engine, cerveau, LLMContextFrame(context=contexte))
        return [m async for m in await cerveau.get_chat_completions(contexte)]
    finally:
        await harness.stop()


@pytest.mark.asyncio
async def test_r1_par_la_vraie_route_case_allumee_le_nom_d_outil_devient_l_appel():
    sorties = await _par_la_route(True, "_retour_")
    assert _dit(sorties) == ""
    assert [a.function.name for a in _appels(sorties)] == ["retour"]


@pytest.mark.asyncio
async def test_r1_par_la_vraie_route_case_eteinte_la_replique_reste_ecrite():
    sorties = await _par_la_route(False, "_retour_")
    assert _dit(sorties) == "_retour_"
    assert not _appels(sorties)


def test_la_case_seule_pose_les_processeurs_autour_du_cerveau():
    from api.services.pipecat.avant_la_requete import autour_du_cerveau

    class Agent:
        def __init__(self, reglages):
            self.reglages, self.llm, self.visit_id = reglages, object(), "v"
            self.workflow = type("W", (), {"nodes": {}})()

    class Moteur:
        reglages_appel: dict = {}

    avant, apres = autour_du_cerveau(Moteur(), Agent({"reconnaitre_un_outil_ecrit": True}))
    assert avant is not None and apres is not None
    assert autour_du_cerveau(Moteur(), Agent({})) == (None, None)


def test_la_case_est_eteinte_par_defaut_et_dans_les_reglages_d_agent():
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
    from api.services.groupe.reglages import CLES_THEME_DONNEES

    assert WorkflowConfigurationDefaults().reconnaitre_un_outil_ecrit is False
    assert "reconnaitre_un_outil_ecrit" in CLES_THEME_DONNEES


# --- Texte d'équipe d'un collègue (correction de texte faux, sans case) --------------------------------------------------


def _collegue():
    return [
        {"type": "startCall", "data": {"name": "Début", "prompt": "Tu renseignes."}},
        {"type": "endCall", "data": {"name": "retour", "prompt": "Rends la main.", "retour_au_principal": True}},
        {"type": "endCall", "data": {"name": "fin", "prompt": "Dis au revoir."}},
    ]


def test_le_texte_d_equipe_dit_appelle_l_outil_quand_les_sorties_sont_des_outils():
    from api.services.workflow.schema_du_parcours import MARQUEUR_RETOUR, _equipe_specialiste, _portes_ecrites

    noeuds = _collegue()
    noeuds[1]["data"][MARQUEUR_RETOUR] = True
    outils = " ".join(_equipe_specialiste(noeuds, portes_ecrites=False))
    assert "tu appelles l'outil fin" in outils and "tu appelles l'outil retour" in outils
    assert "écris" not in outils
    ecrites = " ".join(_equipe_specialiste(noeuds, portes_ecrites=True))
    assert "tu écris la sortie fin" in ecrites and "tu écris la sortie retour" in ecrites
    assert " ".join(_equipe_specialiste(noeuds)) == ecrites  # défaut inchangé
    assert _portes_ecrites({"portes_dans_la_reponse": True, "fiche_mode_de_note": "greffier"}) is True
    assert _portes_ecrites({"portes_dans_la_reponse": True, "fiche_mode_de_note": "outil"}) is False
    assert _portes_ecrites({}) is False


# --- C9 : le détecteur d'impasse compte le nom d'outil écrit et la question redemandée autrement -------------------------


def _banc_c9(outils=("coordonnees",), noeud=None):
    from api.tests.mark.test_sortie_d_impasse import Banc, _entrer

    banc = Banc(noeud=noeud)
    banc.active_agent.llm = SimpleNamespace(_mark_derniers_outils=tuple(outils))
    _entrer(banc)
    return banc


async def _repliques_c9(banc, *textes):
    from api.tests.mark.test_sortie_d_impasse import _repliques

    await _repliques(banc, *textes)
    return banc.etat()["signes"]


@pytest.mark.asyncio
async def test_c9_une_replique_qui_n_est_que_le_nom_d_un_outil_redite_compte():
    banc = _banc_c9()
    # Une seule fois : rien. La redite, nue ou habillée, est un signe (avant : jamais, moins de trois mots).
    assert await _repliques_c9(banc, "coordonnees") == 0
    assert await _repliques_c9(banc, "_coordonnees_") == 1
    assert [e.get("signe") for e in banc.etat()["journal"] if e.get("signe")] == ["replique_redite"]


@pytest.mark.asyncio
async def test_c9_le_nom_d_une_sortie_de_l_etape_compte_aussi_et_un_mot_ordinaire_non():
    noeud = SimpleNamespace(
        id="n1", name="Étape", prompt="x", champs_etape=(), conditions_de_champs=(), is_end=False,
        out_edges=[SimpleNamespace(get_function_name=lambda: "retour")],
    )
    banc = _banc_c9(outils=(), noeud=noeud)
    assert await _repliques_c9(banc, "retour", "*retour*") == 1
    autre = _banc_c9(outils=("coordonnees",))
    assert await _repliques_c9(autre, "d'accord", "d'accord", "d'accord") == 0  # moins de trois mots, pas un outil


@pytest.mark.asyncio
async def test_c9_la_meme_question_une_troisieme_fois_sous_d_autres_mots_compte():
    banc = _banc_c9(outils=())
    q1 = "Quelle est votre commune de résidence ?"
    q2 = "Pouvez-vous m'indiquer votre commune de résidence ?"
    q3 = "Dans quelle commune de résidence habitez-vous ?"
    assert await _repliques_c9(banc, q1, q2) == 0  # deux essais : permis
    assert await _repliques_c9(banc, q3) == 1  # le troisième est un signe
    assert [e.get("signe") for e in banc.etat()["journal"] if e.get("signe")] == ["redemande_reformulee"]


@pytest.mark.asyncio
async def test_c9_deux_questions_sur_autre_chose_ou_coupees_par_une_phrase_ne_comptent_pas():
    banc = _banc_c9(outils=())
    assert await _repliques_c9(
        banc,
        "Quelle est votre commune de résidence ?",
        "Quel est votre numéro de téléphone mobile ?",
        "Quelle est votre adresse électronique personnelle ?",
        "Quel est votre numéro de client habituel ?",
    ) == 0
    banc = _banc_c9(outils=())
    q1 = "Quelle est votre commune de résidence ?"
    q2 = "Pouvez-vous m'indiquer votre commune de résidence ?"
    q3 = "Dans quelle commune de résidence habitez-vous ?"
    # Une phrase sans question au milieu remet la série à zéro : trois questions, mais pas de suite.
    assert await _repliques_c9(banc, q1, q2, "Très bien, je note cela pour la suite de votre dossier.", q3) == 0
