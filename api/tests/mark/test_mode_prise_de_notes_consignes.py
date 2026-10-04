"""[.mark] Les consignes de mode et l'état enrichi (plan mode-prise-de-notes, lot 3).

Plan `Labo-agent-vocal/plans/mode-prise-de-notes/`.

- D3 : la consigne propre au mode est écrite par le CODE à la fin du prompt système, là où
  l'outil serait proposé ; les prompts de l'agent restent neutres. Outil : rien ne change.
- D4 : sans outil, la note est vérifiée après que la phrase est partie ; ce que la vérification
  demande (à confirmer, à proposer, refusé) est montré au tour suivant, par l'état de la fiche,
  avec les consignes que l'outil aurait rendues.

| Test | Ce qu'il prouve |
|---|---|
| bloc | post-scriptum : bloc à la fin du prompt d'une étape, champs de la fiche compris ; outil : prompt inchangé ; étape de fin : rien |
| en-tête | « par noter_information » n'est dit qu'en mode outil |
| notices | une note refusée en post-scriptum est montrée à la requête suivante avec sa consigne ; une réponse sans note l'efface ; l'historique reste intact |
| outil | en mode outil, l'état est celui d'avant, sans notices |
| vocabulaire | la consigne ne porte aucun mot de métier : seuls les champs de l'agent y entrent |
"""

import pytest

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_MODE,
    CONSIGNE_NON_DIT,
    CONSIGNE_POST_SCRIPTUM,
    DEBUT_PRISE_DE_NOTES,
    ENTETE_ETAT,
    ENTETE_ETAT_POST_SCRIPTUM,
    FIN_PRISE_DE_NOTES,
    MODE_OUTIL,
    MODE_POST_SCRIPTUM,
    NOTE_DESCRIPTIONS,
    SEPARATEUR,
    ReglagesFiche,
    consigne_du_mode,
    ecrire_dans_la_fiche,
    etat_de_la_fiche,
    noter,
)
from api.tests.mark.test_fiche_montree import (
    PAROLE,
    PROMPT,
    _contexte,
    _mistral,
    _moteur,
    _requete,
)
from api.tests.mark.test_outil_noter import CONFIG_ALLUMEE


def _reglages(mode: str) -> ReglagesFiche:
    reglages = ReglagesFiche.depuis({**CONFIG_ALLUMEE, CLE_MODE: mode})
    assert reglages is not None and reglages.mode == mode
    return reglages


async def _prompt_de_l_etape(workflow, mode: str | None, etape: str) -> str:
    llm = _mistral()
    engine = _moteur(workflow, llm, _contexte(), _reglages(mode) if mode else None)
    agent = engine.active_agent
    await engine._prepare_node(agent, workflow.nodes[etape], apply_settings=False)
    return agent.system_prompt


# --------------------------------------------------------------------------- #
# 1. Le bloc du mode, à la fin du prompt (D3)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_post_scriptum_le_bloc_est_a_la_fin_du_prompt_de_l_etape(
    three_node_workflow,
):
    prompt = await _prompt_de_l_etape(three_node_workflow, MODE_POST_SCRIPTUM, "agent")
    sans_mode = await _prompt_de_l_etape(three_node_workflow, None, "agent")
    assert prompt.startswith(sans_mode)
    bloc = prompt[len(sans_mode) :].strip()
    assert bloc.startswith(DEBUT_PRISE_DE_NOTES) and bloc.endswith(FIN_PRISE_DE_NOTES)
    assert bloc.count(DEBUT_PRISE_DE_NOTES) == 1
    assert f"le séparateur {SEPARATEUR} seul" in bloc
    # Les champs de la fiche, avec leurs descriptions, et l'avertissement A3.
    assert "- nom : Nom de famille" in bloc
    assert "- telephone :" in bloc and "- motif :" in bloc
    assert NOTE_DESCRIPTIONS in bloc


@pytest.mark.asyncio
async def test_outil_le_prompt_est_inchange(three_node_workflow):
    avec_outil = await _prompt_de_l_etape(three_node_workflow, MODE_OUTIL, "agent")
    sans_fiche = await _prompt_de_l_etape(three_node_workflow, None, "agent")
    assert avec_outil == sans_fiche
    assert DEBUT_PRISE_DE_NOTES not in avec_outil


@pytest.mark.asyncio
async def test_post_scriptum_rien_sur_une_etape_de_fin(three_node_workflow):
    fin = await _prompt_de_l_etape(three_node_workflow, MODE_POST_SCRIPTUM, "end")
    assert DEBUT_PRISE_DE_NOTES not in fin


def test_le_bloc_ne_porte_que_les_champs_de_l_agent():
    """Zéro vocabulaire métier : hors des champs de l'agent, la consigne est fixe."""
    autre = ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            CLE_MODE: MODE_POST_SCRIPTUM,
            "fiche_champs": [
                {"nom": "x", "origine": "dicte", "description": "Un champ"}
            ],
        }
    )
    bloc = consigne_du_mode(autre)
    fixe = CONSIGNE_POST_SCRIPTUM.format(
        separateur=SEPARATEUR,
        champs="- x : Un champ",
        note_descriptions=NOTE_DESCRIPTIONS,
    )
    assert bloc == f"{DEBUT_PRISE_DE_NOTES}\n{fixe}\n{FIN_PRISE_DE_NOTES}"
    assert consigne_du_mode(_reglages(MODE_OUTIL)) is None
    assert consigne_du_mode(None) is None


# --------------------------------------------------------------------------- #
# 2. L'état de la fiche selon le mode
# --------------------------------------------------------------------------- #


def test_l_en_tete_ne_parle_de_l_outil_qu_en_mode_outil():
    fiche: dict = {}
    for mode, entete in (
        (MODE_OUTIL, ENTETE_ETAT),
        (MODE_POST_SCRIPTUM, ENTETE_ETAT_POST_SCRIPTUM),
    ):
        ecrire_dans_la_fiche(fiche, _reglages(mode), "nom", "Dupont", paroles=[PAROLE])
        assert etat_de_la_fiche(_reglages(mode), fiche).splitlines()[0] == entete
    assert "noter_information" not in ENTETE_ETAT_POST_SCRIPTUM


@pytest.mark.asyncio
async def test_D4_une_note_refusee_est_montree_au_tour_suivant(three_node_workflow):
    llm = _mistral()
    context = _contexte({"role": "user", "content": PAROLE})
    reglages = _reglages(MODE_POST_SCRIPTUM)
    engine = _moteur(three_node_workflow, llm, context, reglages)
    assert engine._notices_fiche is not None

    # Le post-scriptum du tour note une valeur jamais dite : refusée.
    note = await noter(
        lambda: engine._gathered_context,
        reglages,
        {"nom": "Durand"},
        paroles=[PAROLE],
        question=None,
        source=MODE_POST_SCRIPTUM,
    )
    engine._notices_fiche.retenir(note)

    envoyes = await _requete(llm, context)
    etat = envoyes[-2]["content"]
    assert etat.startswith(ENTETE_ETAT_POST_SCRIPTUM)
    assert "Retour de ta dernière note" in etat
    assert '"refuses": [{"champ": "nom", "raison": "non_dit"}]' in etat
    assert CONSIGNE_NON_DIT.format(champs="nom") in etat
    assert envoyes[-1]["content"] == PAROLE
    # Hors historique, prompt intact (T6.2).
    assert envoyes[0] == {"role": "system", "content": PROMPT}
    assert context.get_messages()[-1] == {"role": "user", "content": PAROLE}

    # La réponse suivante n'a rien noté : la notice s'efface.
    engine._notices_fiche.retenir(None)
    envoyes = await _requete(llm, context)
    assert not any(
        "Retour de ta dernière note" in (m.get("content") or "") for m in envoyes
    )


@pytest.mark.asyncio
async def test_D4_une_note_ecrite_sans_rien_a_demander_n_ajoute_rien(
    three_node_workflow,
):
    llm = _mistral()
    context = _contexte({"role": "user", "content": PAROLE})
    reglages = _reglages(MODE_POST_SCRIPTUM)
    engine = _moteur(three_node_workflow, llm, context, reglages)
    note = await noter(
        lambda: engine._gathered_context,
        reglages,
        {"nom": "Dupont"},
        paroles=[PAROLE],
        question=None,
        source=MODE_POST_SCRIPTUM,
    )
    engine._notices_fiche.retenir(note)
    envoyes = await _requete(llm, context)
    etat = envoyes[-2]["content"]
    assert "Noté : nom = « Dupont »" in etat
    assert "Retour de ta dernière note" not in etat


def test_en_mode_outil_pas_de_notices(three_node_workflow):
    engine = _moteur(
        three_node_workflow, _mistral(), _contexte(), _reglages(MODE_OUTIL)
    )
    assert engine._notices_fiche is None
