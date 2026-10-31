"""[.mark] Lot 8 de builder-agent-vocal : les interrupteurs des interventions du moteur.

Chaque interrupteur : éteint, la fonctionnalité ne s'applique pas ; allumé (ou clé absente, ou ``null``), le
comportement est celui d'avant. Un test de plus : une configuration vide et une configuration où tous les interrupteurs
valent leur défaut produisent la même requête au modèle et le même texte dit.

| Test | Ce qu'il prouve |
|---|---|
| lecture | seul ``False`` éteint ; clé absente, ``null`` ou illisible = allumé ; le schéma les donne allumés |
| sorties de l'étape | éteint, aucune ligne « Sortie X » ; allumé, les lignes d'avant |
| sortie d'impasse | éteint, rien n'est compté ni montré (moteur) ; au clavier, une session qui redit la même réplique ne pose rien |
| parole avant l'outil | éteint, le modèle est relancé même si la réponse avait parlé |
| main passée | éteint, l'agent qui a passé la main répond encore et la note n'est pas ajoutée |
| ordre outil puis parole | éteint, la requête part dans l'ordre enregistré |
| compte rendu | éteint, aucun compte rendu écrit ni dans l'avis de passage ni dans les résultats d'outil |
| phrases coupées | éteint, la requête n'est pas réécrite |
| réplique inachevée | éteint, la fin de phrase est dite et le modèle ne reparle pas |
| réponse muette | éteint, une réponse sans phrase ni porte ne relance pas le modèle |
| notes de passation | éteint, le prompt de l'étape du collègue n'a pas la note |
| parité | l'interrupteur est posé sur le cerveau aux trois endroits qui le construisent (appel, collègue, clavier) |
| tout allumé | configuration vide et configuration « tous les défauts » : même requête, même texte dit |
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.groupe.passations import NOTE_DE_PASSATION
from api.services.groupe.reglages import CLES_COMMUNES
from api.services.interventions_du_moteur import (
    ATTRIBUT,
    CLE_COMPTE_RENDU_DE_PHRASE,
    CLE_MAIN_PASSEE,
    CLE_NOTES_DE_PASSATION,
    CLE_ORDRE_OUTIL_PUIS_PAROLE,
    CLE_PAROLE_AVANT_OUTIL,
    CLE_PHRASES_COUPEES,
    CLE_REPLIQUE_INACHEVEE,
    CLE_REPONSE_MUETTE,
    CLE_SORTIE_D_IMPASSE,
    CLE_SORTIES_DE_L_ETAPE,
    CLES_DES_INTERVENTIONS,
    brancher_les_interventions,
    est_allumee,
    intervention_du_moteur,
    intervention_du_service,
)
from api.services.phrases.compte_rendu import compte_rendu
from api.services.pipecat.lecteur_de_portes import LecteurDePortes
from api.services.pipecat.main_passee import MainPasseeMixin, muter
from api.services.pipecat.ordre_outil_puis_parole import ordre_outil_puis_parole
from api.services.pipecat.replique_inachevee import TRACE_INACHEVEES
from api.services.workflow.fiche_au_fil_de_leau import CLE_TOUR, ReglagesFiche
from api.services.workflow.sortie_d_impasse import (
    CLE_IMPASSE,
    fin_de_la_replique,
    noter_un_signe,
)
from api.services.workflow.sorties_de_l_etape import (
    LIGNE_PREMIERE_CHOSE,
    lignes_des_sorties,
)

RACINE = Path(__file__).resolve().parents[2] / "services"
ETEINT = {cle: False for cle in CLES_DES_INTERVENTIONS}


def _eteint(cle: str) -> dict:
    return {cle: False}


def _moteur(reglages: dict | None = None, *, appel: dict | None = None, fiche: dict | None = None):
    """Le témoin du moteur : l'agent qui a la main et les réglages de l'appel (le même objet au clavier)."""
    return SimpleNamespace(
        active_agent=SimpleNamespace(reglages=dict(reglages or {}), current_node=None, llm=None),
        reglages_appel=dict(appel if appel is not None else (reglages or {})),
        _gathered_context=fiche if fiche is not None else {},
    )


# --------------------------------------------------------------------------- #
# Lecture
# --------------------------------------------------------------------------- #


def test_seul_false_eteint_et_le_schema_les_donne_allumes():
    for cle in CLES_DES_INTERVENTIONS:
        assert est_allumee({}, cle) and est_allumee({cle: None}, cle) and est_allumee({cle: True}, cle)
        assert est_allumee({cle: "non"}, cle) and est_allumee(None, cle)
        assert not est_allumee({cle: False}, cle)
    defauts = WorkflowConfigurationDefaults.model_validate({})
    nulls = WorkflowConfigurationDefaults.model_validate({cle: None for cle in CLES_DES_INTERVENTIONS})
    for cle in CLES_DES_INTERVENTIONS:
        assert getattr(defauts, cle) is True and getattr(nulls, cle) is True
    assert WorkflowConfigurationDefaults.model_validate(ETEINT).moteur_main_passee is False


def test_les_interrupteurs_sont_communs_au_groupe_et_aux_modeles():
    assert set(CLES_DES_INTERVENTIONS) <= set(CLES_COMMUNES)
    from api.services.modeles_reglages.classement import SECTIONS

    assert set(CLES_DES_INTERVENTIONS) <= set(SECTIONS["interventions"])
    from api.services.groupe.reglages import CLES_THEME_INTERVENTIONS

    # les dix clés sont écrites une à une dans le groupe (l'écran lit ce fichier) : même liste, même ordre
    assert [c for c in CLES_THEME_INTERVENTIONS if c.startswith("moteur_")] == list(CLES_DES_INTERVENTIONS)


def test_le_moteur_lit_l_agent_qui_a_la_main_puis_l_appel():
    assert intervention_du_moteur(_moteur(), CLE_MAIN_PASSEE)
    assert not intervention_du_moteur(_moteur(_eteint(CLE_MAIN_PASSEE)), CLE_MAIN_PASSEE)
    # un agent sans réglage propre : ceux de l'appel
    moteur = SimpleNamespace(active_agent=SimpleNamespace(reglages=None), reglages_appel=_eteint(CLE_MAIN_PASSEE))
    assert not intervention_du_moteur(moteur, CLE_MAIN_PASSEE)


def test_poser_sur_le_service_tout_allume_ne_touche_a_rien():
    llm = SimpleNamespace()
    assert brancher_les_interventions(llm, {}) == frozenset()
    assert not hasattr(llm, ATTRIBUT)
    assert brancher_les_interventions(llm, {CLE_MAIN_PASSEE: False}) == {CLE_MAIN_PASSEE}
    assert not intervention_du_service(llm, CLE_MAIN_PASSEE) and intervention_du_service(llm, CLE_PHRASES_COUPEES)
    # un service rebranché avec tout allumé redevient celui d'avant
    brancher_les_interventions(llm, {})
    assert intervention_du_service(llm, CLE_MAIN_PASSEE)


# --------------------------------------------------------------------------- #
# Sorties de l'étape
# --------------------------------------------------------------------------- #

CONFIG_FICHE = {
    "fiche_au_fil_de_leau": True,
    "fiche_champs": [{"nom": "nom", "origine": "dicte"}, {"nom": "adresse", "origine": "dicte"}],
    "etiquettes_des_etapes": True,
}


def _arrivee(*champs):
    return SimpleNamespace(name="La", champs_etape=tuple(champs), conditions_de_champs=(), out_edges=[])


def _sorties(config: dict) -> list[str]:
    reglages = ReglagesFiche.depuis({**CONFIG_FICHE, **config})
    assert reglages is not None and reglages.etiquettes
    return lignes_des_sorties(reglages, {"nom": "Durand"}, [("porte_a", _arrivee("nom", "adresse"))])


def test_sorties_de_l_etape_eteint_aucune_ligne_allume_les_lignes_d_avant():
    attendu = [LIGNE_PREMIERE_CHOSE.format(sortie="porte_a", champ="adresse")]
    assert _sorties({}) == attendu
    assert _sorties({CLE_SORTIES_DE_L_ETAPE: True}) == attendu
    assert _sorties(_eteint(CLE_SORTIES_DE_L_ETAPE)) == []


# --------------------------------------------------------------------------- #
# Sortie d'impasse
# --------------------------------------------------------------------------- #


def test_impasse_eteinte_rien_n_est_compte_allumee_le_signe_compte():
    allume = _moteur()
    assert noter_un_signe(allume, "replique_redite") == 1
    assert CLE_IMPASSE in allume._gathered_context
    eteint = _moteur(_eteint(CLE_SORTIE_D_IMPASSE))
    assert noter_un_signe(eteint, "replique_redite") == 0
    assert CLE_IMPASSE not in eteint._gathered_context


@pytest.mark.asyncio
async def test_impasse_eteinte_la_fin_de_replique_ne_fait_rien():
    moteur = _moteur(_eteint(CLE_SORTIE_D_IMPASSE))
    moteur.is_call_disposed = lambda: False
    assert await fin_de_la_replique(moteur, "Je cherche.", None) is False
    assert CLE_IMPASSE not in moteur._gathered_context


@pytest.mark.asyncio
async def test_impasse_au_clavier_eteinte_la_replique_redite_ne_pose_rien(db_session, async_session, test_client_factory):
    from api.tests.mark.test_clavier_porte_la_fiche import FICHE, _monter
    from api.tests.mark.test_parite_clavier_telephone import REDITE
    from api.tests.mark.test_passation_clavier import _dit, _session, _texte, _vide

    user, workflow = await _monter(db_session, async_session, {**FICHE, CLE_SORTIE_D_IMPASSE: False})
    reponses = await _session(
        test_client_factory,
        user,
        workflow,
        [_vide(), *(_dit(_texte(REDITE)) for _ in range(4))],
        ["bonjour", "alors ?", "toujours rien ?", "vous êtes là ?"],
    )
    assert not (reponses[-1]["checkpoint"]["gathered_context"].get(CLE_IMPASSE) or {}).get("temps")


# --------------------------------------------------------------------------- #
# Parole avant l'outil
# --------------------------------------------------------------------------- #


def test_parole_avant_l_outil_eteinte_le_modele_est_toujours_relance():
    from api.services.travail import agent as travail_agent

    suivi = SimpleNamespace(a_parle_avant=lambda _id: True)
    with patch.object(travail_agent, "suivre_la_parole", return_value=suivi):
        allume = travail_agent._proprietes_du_resultat(object(), _moteur(), None)
        eteint = travail_agent._proprietes_du_resultat(object(), _moteur(_eteint(CLE_PAROLE_AVANT_OUTIL)), None)
    params = SimpleNamespace(tool_call_id="t1")
    assert allume(params).run_llm is False  # comportement d'avant : la phrase déjà dite, pas de relance
    assert eteint(params) is None  # relance du modèle


# --------------------------------------------------------------------------- #
# Main passée
# --------------------------------------------------------------------------- #


class _Base:
    def __init__(self):
        self.appels = 0

    async def get_chat_completions(self, context):
        self.appels += 1
        return ["réponse"]

    def build_chat_completion_params(self, params):
        return {"model": "m", "messages": list(params["messages"])}


class _Service(MainPasseeMixin, _Base):
    pass


FINIE_PAR_L_ASSISTANT = [
    {"role": "system", "content": "consigne"},
    {"role": "user", "content": "Bonjour."},
    {"role": "assistant", "content": "Très bien."},
]


@pytest.mark.asyncio
async def test_main_passee_eteinte_l_agent_repond_encore_et_la_note_n_est_pas_ajoutee():
    allume, eteint = _Service(), _Service()
    brancher_les_interventions(eteint, _eteint(CLE_MAIN_PASSEE))
    for service in (allume, eteint):
        muter(service)
    assert [m async for m in await allume.get_chat_completions([])] == []
    assert await eteint.get_chat_completions([]) == ["réponse"]
    entree = {"messages": FINIE_PAR_L_ASSISTANT}
    assert allume.build_chat_completion_params(entree)["messages"][-1] == {"role": "user", "content": NOTE_DE_PASSATION}
    assert eteint.build_chat_completion_params(entree)["messages"] == FINIE_PAR_L_ASSISTANT


# --------------------------------------------------------------------------- #
# Ordre outil puis parole
# --------------------------------------------------------------------------- #

APPEL = {"role": "assistant", "tool_calls": [{"id": "t1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]}
LANCE = {"role": "tool", "content": "{}", "tool_call_id": "t1"}
PHRASE = {"role": "assistant", "content": "Je regarde."}
SUITE = [{"role": "system", "content": "s"}, {"role": "user", "content": "a"}, PHRASE, APPEL, LANCE, {"role": "user", "content": "ok"}]


def test_ordre_outil_puis_parole_eteint_la_requete_part_comme_enregistree():
    llm = SimpleNamespace()
    brancher_les_interventions(llm, _eteint(CLE_ORDRE_OUTIL_PUIS_PAROLE))
    corrige = ordre_outil_puis_parole({"messages": list(SUITE)}, SimpleNamespace())
    assert corrige["messages"] != SUITE and corrige["messages"][-2] == PHRASE
    assert ordre_outil_puis_parole({"messages": list(SUITE)}, llm)["messages"] == SUITE
    assert ordre_outil_puis_parole({"messages": list(SUITE)})["messages"] == corrige["messages"]  # sans service : d'avant


# --------------------------------------------------------------------------- #
# Compte rendu après une phrase du code
# --------------------------------------------------------------------------- #


def test_compte_rendu_eteint_rien_n_est_ecrit():
    assert "L'appelant a entendu" in compte_rendu("un fait", dit="Bonjour.")
    assert compte_rendu("un fait", dit="Bonjour.", actif=True) == compte_rendu("un fait", dit="Bonjour.")
    assert compte_rendu("un fait", dit="Bonjour.", actif=False) == ""


def test_compte_rendu_eteint_l_avis_de_passage_n_a_plus_que_la_premiere_replique():
    from api.services.workflow import passage_sur_la_fiche as passage

    def avis(moteur):
        with patch.object(passage, "_la_premiere_replique", return_value="Pose la question."):
            passage.poser_la_notice(moteur, None, "Un instant.")
        return moteur._notice_de_passage

    allume, eteint = avis(_moteur()), avis(_moteur(_eteint(CLE_COMPTE_RENDU_DE_PHRASE)))
    assert "Un instant." in allume and "Pose la question." in allume
    assert eteint == "Pose la question."


def test_compte_rendu_chaque_appelant_passe_l_interrupteur():
    """Les cinq endroits qui écrivent un compte rendu lisent l'interrupteur (aucun n'en oublie)."""
    for chemin in (
        "integrations/connectors/outil.py",
        "workflow/enveloppe_des_actions.py",
        "workflow/passage_sur_la_fiche.py",
        "workflow/pipecat_engine_custom_tools.py",
        "travail/agent.py",
    ):
        texte = (RACINE / chemin).read_text(encoding="utf-8")
        appels = len(re.findall(r"(?<![\w.])compte_rendu\(", re.sub(r"def\s+\w+\(", "", texte)))
        assert appels and appels == texte.count("actif=intervention_du_moteur(self.moteur, CLE_COMPTE_RENDU_DE_PHRASE)") + texte.count(
            "actif=intervention_du_moteur(moteur, CLE_COMPTE_RENDU_DE_PHRASE)"
        ) + texte.count("actif=intervention_du_moteur(engine, CLE_COMPTE_RENDU_DE_PHRASE)") + texte.count(
            "actif=intervention_du_moteur(self, CLE_COMPTE_RENDU_DE_PHRASE)"
        ), (chemin, appels)


# --------------------------------------------------------------------------- #
# Phrases coupées
# --------------------------------------------------------------------------- #


def test_phrases_coupees_eteint_la_requete_n_est_pas_reecrite():
    from api.services.phrases import coupures

    class _LLM:
        def build_chat_completion_params(self, params):
            return {"messages": ["m"]}

    def requete(config):
        llm = _LLM()
        brancher_les_interventions(llm, config)
        moteur = SimpleNamespace(phrases=SimpleNamespace(coupures=coupures.RegistreDesCoupures()))
        assert coupures.brancher_les_coupures(moteur, llm) is True
        with patch.object(coupures, "reecrire_les_coupures", side_effect=lambda p, r: {**p, "reecrite": True}):
            return llm.build_chat_completion_params({})

    assert requete({}) == {"messages": ["m"], "reecrite": True}
    assert requete(_eteint(CLE_PHRASES_COUPEES)) == {"messages": ["m"]}


# --------------------------------------------------------------------------- #
# Réplique inachevée et réponse muette (lecteur de portes)
# --------------------------------------------------------------------------- #


def _lecteur(fiche: dict, moteur) -> LecteurDePortes:
    from api.tests.mark.test_trace_modele import GREFFIER_PORTES

    return LecteurDePortes(
        reglages=ReglagesFiche.depuis(GREFFIER_PORTES),
        fiche=lambda: fiche,
        messages=list,
        attendu=lambda: True,
        portes=moteur,
    )


async def _jouer(reglages: dict, *textes):
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.tests import run_test
    from pipecat.tests.utils import SleepFrame

    from api.tests.mark.test_post_scriptum import DEMARRAGE_S
    from api.tests.mark.test_replique_inachevee import _MoteurRelance
    from api.tests.mark.test_porte_parlee_processeur import _Ordre

    moteur = _MoteurRelance()
    moteur.active_agent = SimpleNamespace(reglages=reglages)
    moteur.reglages_appel = reglages
    fiche = {CLE_TOUR: 7}
    ordre = _Ordre()
    await run_test(
        Pipeline([_lecteur(fiche, moteur), ordre]),
        frames_to_send=[
            LLMFullResponseStartFrame(),
            *[LLMTextFrame(t) for t in textes],
            LLMFullResponseEndFrame(),
            SleepFrame(sleep=0.3),
        ],
        start_timeout=DEMARRAGE_S,
    )
    return ordre.dit, moteur.relances, fiche


@pytest.mark.asyncio
async def test_replique_inachevee_eteinte_la_fin_est_dite_et_le_modele_ne_reparle_pas():
    textes = ("C'est noté.", " Avez-vous une adresse", " mail pour", " que")
    dit, relances, fiche = await _jouer({}, *textes)
    assert "pour que" not in dit and relances == 1 and fiche[TRACE_INACHEVEES]
    dit, relances, fiche = await _jouer(_eteint(CLE_REPLIQUE_INACHEVEE), *textes)
    assert "mail pour que" in dit and relances == 0 and TRACE_INACHEVEES not in fiche


@pytest.mark.asyncio
async def test_reponse_muette_eteinte_le_modele_ne_reparle_pas():
    muette = ('{"champ": "valeur"}',)
    _, relances, _ = await _jouer({}, *muette)
    assert relances == 1
    _, relances, _ = await _jouer(_eteint(CLE_REPONSE_MUETTE), *muette)
    assert relances == 0


# --------------------------------------------------------------------------- #
# Notes de passation
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_notes_de_passation_eteintes_le_collegue_n_a_pas_la_note():
    from api.tests.mark.test_notes_de_passation import PATCH_OUTILS, _passer, _sonnerie
    from api.tests.mark.test_passation_rapide_groupe import GROUPE, _monter_groupe
    from api.tests.test_agent_transfer import TransferAgentTool

    async def prompt_du_collegue(reglages, monkeypatch):
        _sonnerie(monkeypatch)
        harness = await _monter_groupe(reglages)
        engine = harness.engine
        engine._fiche = ReglagesFiche.depuis(CONFIG_FICHE)
        engine._gathered_context.update({"nom": "Dupont"})
        try:
            with patch(PATCH_OUTILS, AsyncMock(return_value=[TransferAgentTool()])):
                assert (await _passer(harness, 99, raison="Passer à Support"))["outcome"] == "completed"
            return engine.active_agent.system_prompt
        finally:
            await harness.stop()

    mp = pytest.MonkeyPatch()
    try:
        allume = await prompt_du_collegue(GROUPE, mp)
        eteint = await prompt_du_collegue({**GROUPE, **_eteint(CLE_NOTES_DE_PASSATION)}, mp)
    finally:
        mp.undo()
    assert "# Passation depuis l'accueil" in allume
    assert "# Passation depuis l'accueil" not in eteint


# --------------------------------------------------------------------------- #
# Parité clavier / téléphone
# --------------------------------------------------------------------------- #


def test_l_interrupteur_est_pose_sur_le_cerveau_aux_trois_endroits_qui_le_construisent():
    for chemin in ("pipecat/run_pipeline.py", "pipecat/agent_runtime_factory.py", "workflow/text_chat_runner.py"):
        texte = (RACINE / chemin).read_text(encoding="utf-8")
        assert re.search(r"\bbrancher_les_interventions\(", re.sub(r"\bdef\s+\w+\(", "", texte)), chemin


# --------------------------------------------------------------------------- #
# Tout allumé = le comportement d'avant
# --------------------------------------------------------------------------- #

DEFAUTS = {cle: True for cle in CLES_DES_INTERVENTIONS}


def test_tout_allume_la_requete_au_modele_est_la_meme_que_la_configuration_vide():
    # service : la même requête, sur les deux formats d'envoi
    for config in ({}, DEFAUTS, {cle: None for cle in CLES_DES_INTERVENTIONS}):
        llm = _Service()
        brancher_les_interventions(llm, config)
        assert llm.build_chat_completion_params({"messages": FINIE_PAR_L_ASSISTANT})["messages"][-1]["content"] == NOTE_DE_PASSATION
        assert ordre_outil_puis_parole({"messages": list(SUITE)}, llm) == ordre_outil_puis_parole({"messages": list(SUITE)})
        assert ordre_outil_puis_parole({"input": list(SUITE)}, llm) == ordre_outil_puis_parole({"input": list(SUITE)})
        assert not hasattr(llm, ATTRIBUT)
    # moteur : mêmes lignes de sorties, mêmes comptes rendus
    assert _sorties({}) == _sorties(DEFAUTS)
    assert compte_rendu("fait", dit="Bonjour.") == compte_rendu("fait", dit="Bonjour.", actif=intervention_du_moteur(_moteur(DEFAUTS), CLE_COMPTE_RENDU_DE_PHRASE))


@pytest.mark.asyncio
async def test_tout_allume_le_texte_dit_est_le_meme_que_la_configuration_vide():
    textes = ("C'est noté.", " Avez-vous une adresse", " mail pour", " que")
    assert (await _jouer({}, *textes))[:2] == (await _jouer(DEFAUTS, *textes))[:2]
    assert (await _jouer({}, '{"a": 1}'))[:2] == (await _jouer(DEFAUTS, '{"a": 1}'))[:2]
