"""[.mark] Correctifs après le banc commun, lots 1 et 2 : passations, fin d'appel, transfert échoué.

Plan `Labo-agent-vocal/plans/correctifs-apres-banc-commun/` (K1, K4, K14, K15, P12). Les tests de moteur
passent par le VRAI moteur et le VRAI coordinateur de passation (banc fendu de `test_agent_transfer.py`) ;
seuls les modèles, la voix et la base sont remplacés. Ni Postgres ni Redis.

| Test | Ce qu'il prouve |
|---|---|
| K1 outil exposé | un outil de passation porte le paramètre obligatoire ``demande`` ; les autres outils sont inchangés ; un paramètre du même nom écrit à l'écran est gardé |
| K1 note | la demande est lue sans crochets, bornée, et remise au collègue dans sa note d'aller (et seulement quand elle existe) |
| K1 chemin réel | le gestionnaire de l'outil lit l'argument, la passation le porte jusqu'au prompt du collègue et à la trace |
| K1 filet (a) | un flux en erreur AVANT le premier morceau est relancé sans flux ; après un morceau, l'erreur remonte |
| K1 filet (b) | un outil de passation aux arguments illisibles est exécuté comme ``{}`` ; les autres appels et les arguments lisibles passent à l'octet |
| K4 | un retour marqué « fin demandée » (filet, ou ``fin`` réécrite) fait prendre à l'accueil sa sortie ``fin`` sans tour de modèle ; un retour ordinaire est inchangé |
| K14 | une porte écrite en tête qui rend la main fait taire la phrase du collègue ; ni la ``fin`` réécrite ni une porte ordinaire |
| K15 | le résultat d'un transfert échoué ne porte aucune phrase du fournisseur : statut neutre et consigne |
| P12 | la phrase du code parle seule : le tour du modèle qui suivrait est supprimé ; une sortie réglée « le modèle reprend » garde son comportement |
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pipecat.tests import MockLLMService

from api.services.groupe.notes import LIBELLE_DEMANDE, note_d_aller
from api.services.groupe.passations import (
    PARAMETRE_DEMANDE,
    demande_de,
    est_un_outil_de_passation,
    porte_ecrite_est_une_fin,
    sortie_de_fin_de_l_etape,
)
from api.services.pipecat.reponse_avalee import (
    ArgumentsLisibles,
    RepriseSansFluxMixin,
    noter_un_outil_de_passation,
)
from api.services.workflow.agent_transfer import TransferRequest
from api.services.workflow.dto import ReactFlowDTO
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.services.workflow.tools.custom_tool import tool_to_function_schema
from api.services.workflow.workflow_graph import WorkflowGraph
from api.tests.mark.test_etape_de_retour import (
    COLLEGUE,
    FICHE_REGLAGES,
    PRINCIPAL,
    _arete,
    _noeud,
    graphe_de_l_accueil,
)
from api.tests.mark.test_filet_de_fin import graphe_du_collegue
from api.tests.test_agent_transfer import TransferHarness


# --------------------------------------------------------------------------- #
# K1 : l'outil de passation et sa note
# --------------------------------------------------------------------------- #


def _outil(type_="transfer_agent", parametres=None, categorie=None):
    config = {"workflow_id": 5, "message": "", "play_greeting": False}
    if parametres is not None:
        config["parameters"] = parametres
    return SimpleNamespace(
        name="Passer à l'agent Support",
        description="Passe l'appel.",
        tool_uuid="u1",
        category=categorie or type_,
        definition={"schema_version": 1, "type": type_, "config": config},
    )


def test_un_outil_de_passation_expose_le_parametre_demande_obligatoire():
    fonction = tool_to_function_schema(_outil())["function"]
    assert fonction["parameters"]["required"] == [PARAMETRE_DEMANDE]
    propriete = fonction["parameters"]["properties"][PARAMETRE_DEMANDE]
    assert propriete["type"] == "string" and propriete["description"]


def test_les_autres_outils_ne_changent_pas():
    autre = SimpleNamespace(
        name="Fin",
        description="d",
        tool_uuid="u2",
        category="end_call",
        definition={"type": "end_call", "config": {}},
    )
    assert tool_to_function_schema(autre)["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "required": [],
    }
    assert not est_un_outil_de_passation(autre) and est_un_outil_de_passation(_outil())


def test_un_parametre_demande_ecrit_a_l_ecran_est_garde_tel_quel():
    ecrit = [{"name": "demande", "type": "string", "description": "Ma description", "required": False}]
    fonction = tool_to_function_schema(_outil(parametres=ecrit))["function"]
    assert fonction["parameters"]["properties"]["demande"]["description"] == "Ma description"
    assert fonction["parameters"]["required"] == []


def test_la_demande_est_lue_sans_crochets_et_bornee():
    assert demande_de({"demande": "  Un   [devis]\npour un poêle "}) == "Un (devis) pour un poêle"
    assert demande_de({"demande": "x" * 1000}) == "x" * 300
    for illisible in (None, {}, {"demande": 12}, {"demande": "   "}, "texte", [1]):
        assert demande_de(illisible) is None


def test_la_note_d_aller_porte_la_demande_seulement_quand_elle_existe():
    sans = note_d_aller(None, {}, outil="Passer à Support")
    avec = note_d_aller(None, {}, outil="Passer à Support", demande="Il veut un devis")
    assert LIBELLE_DEMANDE not in sans
    assert f"{LIBELLE_DEMANDE}Il veut un devis" in avec.splitlines()
    # Rien d'autre ne bouge : la même note, la ligne en plus.
    assert [ligne for ligne in avec.splitlines() if not ligne.startswith(LIBELLE_DEMANDE)] == sans.splitlines()


# --------------------------------------------------------------------------- #
# K1 : le chemin réel de la passation (gestionnaire de l'outil -> moteur -> prompt du collègue)
# --------------------------------------------------------------------------- #


async def test_la_demande_donnee_a_l_outil_arrive_dans_la_note_du_collegue_et_dans_la_trace():
    from api.tests.mark.test_notes_de_passation import FICHE
    from api.tests.mark.test_passation_rapide_groupe import GROUPE, _monter_groupe

    harness = await _monter_groupe(GROUPE)
    try:
        engine = harness.engine
        engine._fiche = FICHE
        engine._gathered_context["passations"] = []
        engine.reglages_appel = dict(GROUPE)
        demandes = []
        original = TransferRequest.__init__

        def espion(self, *a, **k):
            original(self, *a, **k)
            demandes.append(self.demande)

        # Le gestionnaire réel de l'outil lit ``function_call_params.arguments``.
        from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager

        gestionnaire = CustomToolManager(engine, engine.active_agent)
        outil = SimpleNamespace(
            name="Passer à Support",
            description="d",
            tool_uuid="u1",
            category="transfer_agent",
            definition={"type": "transfer_agent", "config": {"workflow_id": 99, "message": "", "play_greeting": False}},
        )
        gestionnaire._agent = engine.active_agent
        resultats = []

        async def rendre(resultat, properties=None):
            resultats.append(resultat)
            if properties is not None and properties.on_context_updated is not None:
                await properties.on_context_updated()

        handler = gestionnaire._create_transfer_agent_handler(outil, "passer_a_support")
        params = SimpleNamespace(
            arguments={"demande": "Il veut [un] devis"}, result_callback=rendre, tool_call_id="t1"
        )
        with patch.object(TransferRequest, "__init__", espion):
            await handler(params)
            coordinateur = engine.transfer_coordinator
            if coordinateur.in_progress:
                await asyncio.wait_for(coordinateur._task, 20)
        assert resultats and resultats[0]["status"] == "transferring"
        assert demandes == ["Il veut (un) devis"]
        # Le collègue la lit dans sa note d'aller, au prompt de sa première étape.
        assert f"{LIBELLE_DEMANDE}Il veut (un) devis" in engine.active_agent.system_prompt
        assert engine._gathered_context["passations"][-1]["demande"] == "Il veut (un) devis"
        # Le clavier recalcule la note depuis la fiche : la demande y est aussi.
        from api.services.groupe.notes import demande_de_passation_vers

        assert demande_de_passation_vers(engine._gathered_context, 99) == "Il veut (un) devis"
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# K1 : filet (a), l'erreur du flux avant le premier morceau
# --------------------------------------------------------------------------- #

from api.tests.mark.test_reponse_avalee import (  # noqa: E402
    FLUX_AVALE,
    _Base,
    _Contexte,
    _Service,
    _morceau,
    _reponse,
)


class _FluxEnErreur:
    """Un flux qui rend ``avant`` puis lève (le fournisseur coupe le flux)."""

    def __init__(self, avant, erreur):
        self._avant, self._erreur = list(avant), erreur

    def __aiter__(self):
        async def gen():
            for m in self._avant:
                yield m
            raise self._erreur

        return gen()


class _BaseEnErreur(_Base):
    def __init__(self, avant, erreur_du_flux, **kw):
        super().__init__([], **kw)
        self._flux_en_erreur = _FluxEnErreur(avant, erreur_du_flux)

    async def get_chat_completions(self, context):
        return self._flux_en_erreur


class _ServiceEnErreur(RepriseSansFluxMixin, _BaseEnErreur):
    pass


def _texte(morceaux):
    return "".join(m.choices[0].delta.content or "" for m in morceaux if m.choices)


async def test_un_flux_en_erreur_avant_le_premier_morceau_est_relance_sans_flux():
    service = _ServiceEnErreur([], APIErreur("list index out of range"), reprise=_reponse(outil="passer_a_support"))
    morceaux = [m async for m in await _appeler(service, ["bonjour"])]
    appels = [a for m in morceaux if m.choices for a in (m.choices[0].delta.tool_calls or [])]
    assert [a.function.name for a in appels] == ["passer_a_support"]
    [requete] = service.requetes
    assert requete["stream"] is False


class APIErreur(RuntimeError):
    pass


async def _appeler(service, contexte):
    """La requête passe par le vrai mixin ; la base rend le flux fourni par le service."""
    return await service.get_chat_completions(contexte)


async def test_un_flux_en_erreur_apres_un_morceau_utile_remonte_comme_avant():
    service = _ServiceEnErreur([_morceau("Bonjour")], APIErreur("coupé"), reprise=_reponse(texte="jamais"))
    flux = await _appeler(service, ["bonjour"])
    recu = []
    with pytest.raises(APIErreur):
        async for m in flux:
            recu.append(m)
    assert _texte(recu) == "Bonjour" and service.requetes == []


async def test_erreur_du_flux_et_relance_en_erreur_l_erreur_d_origine_remonte_sans_appelant_qui_attend():
    service = _ServiceEnErreur([], APIErreur("coupé"), erreur=RuntimeError("panne"))
    with pytest.raises(APIErreur):
        [m async for m in await _appeler(service, ["bonjour"])]


async def test_erreur_du_flux_et_relance_vide_l_appelant_attend_la_phrase_de_repli_est_dite():
    from api.services.pipecat.reponse_avalee import phrase_de_repli

    service = _ServiceEnErreur([], APIErreur("coupé"), reprise=_reponse())
    contexte = _Contexte([{"role": "user", "content": "Allô ?"}])
    morceaux = [m async for m in await _appeler(service, contexte)]
    assert _texte(morceaux) == phrase_de_repli(None)


# --------------------------------------------------------------------------- #
# K1 : filet (b), les arguments illisibles d'un outil de passation
# --------------------------------------------------------------------------- #

from openai.types.chat.chat_completion_chunk import (  # noqa: E402
    ChatCompletionChunk,
    Choice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)

COMMUN = {"id": "c", "created": 0, "model": "m", "object": "chat.completion.chunk"}


def _appel(index, nom=None, arguments=None, id_=None):
    return ChatCompletionChunk(
        **COMMUN,
        choices=[
            Choice(
                index=0,
                delta=ChoiceDelta(
                    tool_calls=[
                        ChoiceDeltaToolCall(
                            index=index,
                            id=id_,
                            type="function",
                            function=ChoiceDeltaToolCallFunction(name=nom, arguments=arguments),
                        )
                    ]
                ),
                finish_reason=None,
            )
        ],
    )


class _FluxSimple:
    def __init__(self, morceaux):
        self._m = list(morceaux)

    def __aiter__(self):
        async def gen():
            for m in self._m:
                yield m

        return gen()


def _comme_pipecat(morceaux):
    """Ce que Pipecat reconstruit : (nom, arguments) par appel, puis la tentative de lecture JSON."""
    noms, args = {}, {}
    for m in morceaux:
        if not m.choices or not m.choices[0].delta.tool_calls:
            continue
        a = m.choices[0].delta.tool_calls[0]
        noms[a.index] = noms.get(a.index, "") + (a.function.name or "")
        args[a.index] = args.get(a.index, "") + (a.function.arguments or "")
    sortie = []
    for i in sorted(noms):
        try:
            sortie.append((noms[i], json.loads(args[i] or "{}")))
        except json.JSONDecodeError:
            pass  # Pipecat jette l'appel
    return sortie


ILLISIBLE = ['{"name": "passer_a_support", "descr', 'iption": "x']


async def _passer_par(morceaux, noms):
    return [m async for m in ArgumentsLisibles(_FluxSimple(morceaux), lambda: noms)]


async def test_un_outil_de_passation_aux_arguments_illisibles_est_execute_comme_un_objet_vide():
    flux = [
        _appel(0, "passer_a_support", ILLISIBLE[0], "t1"),
        _appel(0, None, ILLISIBLE[1]),
        _morceau(fin="tool_calls"),
    ]
    # Sans le filet, Pipecat jette l'appel.
    assert _comme_pipecat(flux) == []
    corrige = await _passer_par(flux, {"passer_a_support"})
    assert _comme_pipecat(corrige) == [("passer_a_support", {})]
    # La requête d'origine n'est pas modifiée en place.
    assert flux[0].choices[0].delta.tool_calls[0].function.arguments == ILLISIBLE[0]


async def test_les_autres_appels_et_les_arguments_lisibles_passent_a_l_octet():
    lisible = [_appel(0, "passer_a_support", '{"demande": "un ', "t1"), _appel(0, None, 'devis"}'), _morceau(fin="stop")]
    assert await _passer_par(lisible, {"passer_a_support"}) == lisible
    # Un autre outil aux arguments illisibles reste jeté par Pipecat (le filet ne vaut que pour la passation).
    autre = [_appel(0, "chercher", ILLISIBLE[0], "t1"), _appel(0, None, ILLISIBLE[1])]
    assert await _passer_par(autre, {"passer_a_support"}) == autre
    # Aucun outil de passation connu : le flux passe tel quel.
    assert await _passer_par(autre, set()) == autre
    # Texte et fin avant les appels : rien n'est retenu hors des appels d'outil.
    texte = [_morceau("Je vous passe"), _morceau(fin="stop")]
    assert await _passer_par(texte, {"passer_a_support"}) == texte


async def test_deux_appels_dont_un_de_passation_illisible_seul_celui_ci_est_corrige():
    flux = [
        _appel(0, "chercher", '{"q": "a"}', "t1"),
        _appel(1, "passer_a_support", ILLISIBLE[0], "t2"),
        _appel(1, None, ILLISIBLE[1]),
    ]
    assert _comme_pipecat(await _passer_par(flux, {"passer_a_support"})) == [
        ("chercher", {"q": "a"}),
        ("passer_a_support", {}),
    ]


async def test_le_cerveau_compatible_openai_branche_le_filet_et_connait_les_passations():
    service = _Service([_appel(0, "passer_a_support", ILLISIBLE[0], "t1"), _appel(0, None, ILLISIBLE[1])])
    noter_un_outil_de_passation(service, "passer_a_support")
    morceaux = [m async for m in await _appeler(service, ["x"])]
    assert _comme_pipecat(morceaux) == [("passer_a_support", {})]


# --------------------------------------------------------------------------- #
# K4 : la fin demandée par le collègue
# --------------------------------------------------------------------------- #


def graphe_du_collegue_sans_porte_fin() -> WorkflowGraph:
    """Une étape qui n'a que la sortie « retour » : le modèle y écrit ``fin`` (le nom du nœud de fin)."""
    noeuds = [
        _noeud("etape", "startCall", "Qualification", "Tu qualifies."),
        _noeud("fin", "endCall", "Fin", "Tu remercies."),
        _noeud("retour", "agentNode", "Retour au principal", "Retour.", retour_au_principal=True),
    ]
    aretes = [_arete("etape", "retour", "Retour"), _arete("retour", "fin", "Fin")]
    return WorkflowGraph(ReactFlowDTO(nodes=noeuds, edges=aretes))


async def _monter(collegue=None, accueil=None):
    from api.services.groupe.passations import MARQUEUR_ETAPE_DE_RETOUR  # noqa: F401

    harness = TransferHarness()
    await harness.build(
        source_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
        destination_llm=MockLLMService(mock_steps=[], chunk_delay=0.001),
        source_workflow=collegue or graphe_du_collegue(),
        destination_workflow=accueil or graphe_de_l_accueil(),
    )
    engine = harness.engine
    engine.reglages_appel = {"agents_specialises": [COLLEGUE]}
    engine.active_agent.workflow_name = "Support"
    engine.active_agent.reglages = {"agent_principal_id": PRINCIPAL, "filet_de_fin": True}
    engine._fiche = ReglagesFiche.depuis(dict(FICHE_REGLAGES))
    engine._gathered_context.update(
        {
            "objet": "une fuite",
            "passations": [{"de": PRINCIPAL, "vers": COLLEGUE, "raison": "Passer à Support", "issue": "completed"}],
            "parcours_etapes": [
                {"agent": "Accueil", "agent_id": PRINCIPAL, "etape": "Accueil"},
                {"agent": "Support", "agent_id": COLLEGUE, "etape": "Qualification"},
            ],
        }
    )
    await harness.start()
    await engine.set_node("etape")
    # Les effets de bord de la sortie : on les observe, sans voix ni téléphonie.
    engine.end_call_with_reason = AsyncMock()
    engine.queue_node_opening = AsyncMock(return_value=SimpleNamespace(action="llm", playback=None))
    return harness


async def _attendre(harness):
    coordinateur = harness.engine.transfer_coordinator
    assert coordinateur.in_progress, "le retour aurait dû partir"
    await asyncio.wait_for(coordinateur._task, 20)
    for tache in list(harness.engine._taches_de_porte) + list(harness.engine.__dict__.get("_taches_du_groupe", ())):
        await asyncio.wait_for(tache, 5)
    return coordinateur.completed[-1]


async def test_le_filet_de_fin_fait_prendre_a_l_accueil_sa_sortie_fin_sans_tour_de_modele():
    harness = await _monter()
    try:
        engine = harness.engine
        assert await engine.filet_de_fin("Très bien, bonne journée.", engine.etat_pour_le_filet()) is True
        resultat = await _attendre(harness)
        assert resultat["outcome"] == "completed"
        accueil = engine.active_agent
        assert accueil.workflow_id == PRINCIPAL and accueil.current_node.id == "fin" and accueil.current_node.is_end
        engine.queue_node_opening.assert_not_called()  # aucun tour de modèle
        engine.end_call_with_reason.assert_awaited_once()
        assert engine._gathered_context["passations"][-1]["raison"] == "retour"
    finally:
        await harness.stop()


async def test_une_porte_fin_reecrite_en_retour_fait_aussi_prendre_la_sortie_fin():
    harness = await _monter(collegue=graphe_du_collegue_sans_porte_fin())
    try:
        engine = harness.engine
        assert porte_ecrite_est_une_fin(engine.active_agent.workflow, "fin")
        assert await engine.prendre_porte_ecrite("fin") == "prise"
        await _attendre(harness)
        assert engine.active_agent.current_node.id == "fin"
        engine.queue_node_opening.assert_not_called()
        engine.end_call_with_reason.assert_awaited_once()
    finally:
        await harness.stop()


async def test_un_retour_ordinaire_est_inchange_l_accueil_joue_son_tour_sur_l_etape_de_retour():
    harness = await _monter()
    try:
        engine = harness.engine
        # La porte « retour » écrite par le modèle : une demande nouvelle, pas une fin.
        assert await engine.prendre_porte_ecrite("retour") == "prise"
        await _attendre(harness)
        assert engine.active_agent.current_node.id == "retour"
        engine.queue_node_opening.assert_awaited_once()
        engine.end_call_with_reason.assert_not_called()
        # Et une porte autre que « fin » réécrite en retour ne finit pas non plus l'appel.
        assert not porte_ecrite_est_une_fin(engine.active_agent.workflow, "retour")
    finally:
        await harness.stop()


async def test_sans_sortie_fin_offerte_le_retour_marque_joue_le_tour_comme_avant():
    # L'accueil sans nœud de fin sur son étape de retour : rien à prendre, le comportement d'avant.
    noeuds = [
        _noeud("accueil", "startCall", "Accueil", "Tu accueilles."),
        _noeud("retour", "agentNode", "Reprise", "Reprends.", etape_de_retour=True),
    ]
    accueil = WorkflowGraph(ReactFlowDTO(nodes=noeuds, edges=[]))
    assert sortie_de_fin_de_l_etape(accueil.nodes["retour"], accueil) is None
    harness = await _monter(accueil=accueil)
    try:
        engine = harness.engine
        assert await engine.filet_de_fin("Au revoir !", engine.etat_pour_le_filet()) is True
        await _attendre(harness)
        assert engine.active_agent.current_node.id == "retour"
        engine.queue_node_opening.assert_awaited_once()
        engine.end_call_with_reason.assert_not_called()
    finally:
        await harness.stop()


# --------------------------------------------------------------------------- #
# K14 : la demande nouvelle, l'accueil parle tout de suite
# --------------------------------------------------------------------------- #


async def test_une_porte_qui_rend_la_main_fait_taire_la_phrase_du_collegue_sauf_pour_une_fin():
    harness = await _monter(collegue=graphe_du_collegue_sans_porte_fin())
    try:
        engine = harness.engine
        assert engine.porte_vers_le_retour_sur_demande_nouvelle("retour") is True
        # ``fin`` réécrite en retour : le collègue garde son au revoir (K4).
        assert engine.porte_vers_le_retour_sur_demande_nouvelle("fin") is False
        assert engine.porte_vers_le_retour_sur_demande_nouvelle("inconnue") is False
    finally:
        await harness.stop()
    harness = await _monter()  # ici ``fin`` est une vraie porte vers le nœud de fin
    try:
        engine = harness.engine
        assert engine.porte_vers_le_retour_sur_demande_nouvelle("fin") is False
        assert engine.porte_vers_le_retour_sur_demande_nouvelle("retour") is True
    finally:
        await harness.stop()


async def test_le_processeur_tait_la_suite_d_une_porte_en_tete_qui_rend_la_main():
    from api.tests.mark.test_porte_parlee_processeur import _MontagePortes

    montage = _MontagePortes()
    montage.moteur.porte_vers_le_retour_sur_demande_nouvelle = lambda nom: nom == "vers_retour"
    ordre = await montage.reponse("→ vers_retour\n", "Je vous repasse l'accueil pour cela.")
    assert ordre.dit.strip() == ""
    assert [p["nom"] for p in montage.moteur.prises] == ["vers_retour"]
    # Une porte ordinaire, ou une porte écrite après la phrase : la réponse est dite comme avant.
    montage = _MontagePortes()
    montage.moteur.porte_vers_le_retour_sur_demande_nouvelle = lambda nom: nom == "vers_retour"
    ordre = await montage.reponse("→ vers_panne\n", "Quelle marque ?")
    assert ordre.dit.strip() == "Quelle marque ?"
    ordre = await _MontagePortes_apres_la_phrase()
    assert "Très bien" in ordre.dit


async def _MontagePortes_apres_la_phrase():
    from api.tests.mark.test_porte_parlee_processeur import _MontagePortes

    montage = _MontagePortes()
    montage.moteur.porte_vers_le_retour_sur_demande_nouvelle = lambda nom: nom == "vers_retour"
    return await montage.reponse("Très bien, je regarde.\n", "→ vers_retour\n")


# --------------------------------------------------------------------------- #
# K15, P12 : le transfert échoué
# --------------------------------------------------------------------------- #


def _gestionnaire(diseur_dit=None, issue=None):
    from api.services.workflow.pipecat_engine_custom_tools import CustomToolManager

    moteur = MagicMock()
    moteur._gathered_context = {}
    moteur._call_context_vars = {"caller_number": "+33100000000"}
    moteur.reglages_appel = {}
    gestionnaire = CustomToolManager.__new__(CustomToolManager)
    gestionnaire._engine = moteur
    gestionnaire._agent = SimpleNamespace()
    gestionnaire._cible_transfert_humain = "numero:***"
    probleme = (
        None
        if diseur_dit is None and issue is None
        else SimpleNamespace(dit=diseur_dit, issue=issue, incident=0, phrase=None, notes=[])
    )
    gestionnaire._dire_l_echec_du_transfert = AsyncMock(return_value=probleme)
    return gestionnaire


def _echec(message="Please try calling back later."):
    return {"action": "transfer_failed", "status": "failed", "reason": "timeout", "message": message}


async def test_un_transfert_echoue_ne_porte_aucune_phrase_destinee_a_l_appelant():
    from api.services.workflow.pipecat_engine_custom_tools import CONSIGNE_ECHEC_TRANSFERT

    gestionnaire = _gestionnaire()
    rendu = AsyncMock()
    await gestionnaire._handle_transfer_result(_echec(), SimpleNamespace(result_callback=rendu), MagicMock())
    resultat, reste = rendu.await_args_list[0].args[0], rendu.await_args_list[0].kwargs
    assert resultat["status"] == "transfer_failed" and resultat["reason"] == "timeout"
    assert resultat["message"] == CONSIGNE_ECHEC_TRANSFERT
    assert "later" not in json.dumps(resultat) and "sorry" not in json.dumps(resultat).lower()
    assert "rappel" in CONSIGNE_ECHEC_TRANSFERT
    assert reste == {}  # sans phrase du code, le modèle parle (comme avant)


async def test_la_phrase_du_code_parle_seule_le_tour_du_modele_est_supprime():
    gestionnaire = _gestionnaire(diseur_dit="Je prends votre demande, on vous rappelle.")
    rendu = AsyncMock()
    await gestionnaire._handle_transfer_result(_echec(), SimpleNamespace(result_callback=rendu), MagicMock())
    resultat, options = rendu.await_args.args[0], rendu.await_args.kwargs
    assert resultat["said_to_caller"] == "Je prends votre demande, on vous rappelle."
    assert options["properties"].run_llm is False


async def test_une_sortie_reglee_le_modele_reprend_garde_son_comportement():
    issue = SimpleNamespace(prise_en_main=False, le_modele_reprend=True, interdit=[], apres=None)
    gestionnaire = _gestionnaire(diseur_dit="Une phrase.", issue=issue)
    rendu = AsyncMock()
    await gestionnaire._handle_transfer_result(_echec(), SimpleNamespace(result_callback=rendu), MagicMock())
    assert "properties" not in rendu.await_args.kwargs  # le modèle reprend, comme réglé à l'écran
