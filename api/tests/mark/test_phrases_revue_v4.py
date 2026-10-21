"""[.mark] Chantier correctifs-apres-banc-v4, lot 4, corrections de la relecture (M2, M3, M4, m5).

| Test | La garantie |
|---|---|
| M2 échéance réelle | un service qui ne répond pas, 1 essai, par l'échéance RÉELLE de Pipecat : la phrase, la note partent, le compte rendu est dans le résultat |
| M2 délai total | le délai de la requête est un total (httpx compte par phase) ; l'échéance de l'appel de fonction a une marge au-dessus des essais |
| M2 après la remise | l'action finale d'une sortie lancée pendant un appel de fonction part APRÈS la remise du résultat (``run_llm=False``), jamais attendue dans l'échéance |
| M3 fermé | une sortie « transférer » à 22 h (entreprise fermée) ne part pas : « transférer » est dans « plus possible », le modèle reprend ; ouvert, elle part |
| M4 retiré | « transférer » n'est plus permis pour « le transfert échoue » ; une ancienne règle qui le portait se relit en « le modèle reprend » |
| M4 réentrée | une sortie de transfert déjà passée interdit toute autre, quel que soit le motif |
| m5 borné | une ancienne règle « l'appelant se tait » à 0,5 s est bornée au minimum du motif, à la lecture et à l'enregistrement |
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.schemas.fiche_agent import ChampFiche
from api.schemas.phrases_du_code import ReglePhrase
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.groupe.passations import est_un_resultat_de_travail  # noqa: F401
from api.services.annonce.constantes import FERME, OUVERT, SUR_RENDEZ_VOUS
from api.services.phrases import sorties
from api.services.phrases.catalogue import (
    APPELANT_SE_TAIT,
    MOTIFS,
    OUTIL_ECHOUE,
    TRANSFERT_ECHOUE,
)
from api.services.phrases.diseur import DiseurDePhrases
from api.services.phrases.regles import resoudre
from api.services.workflow.fiche_au_fil_de_leau import ReglagesFiche
from api.services.workflow.pipecat_engine_custom_tools import (
    MARGE_ECHEANCE_S,
    CustomToolManager,
)
from api.services.workflow.tools.custom_tool import delai_total_s
from api.tests.mark.test_essais_des_outils_http import _outil
from api.tests.mark.test_phrases_veille_v4 import _Moteur
from api.tests.mark.test_travail_de_fond import Appel, _appel_d_outil, _texte

MODULE = "api.services.workflow.tools.custom_tool"


@pytest.fixture
async def appel():
    a = Appel()
    try:
        yield a
    finally:
        await a.arreter()


def _regle(motif, variantes=("Souci.",), **champs):
    return {"motif": motif, "portee": "agent", "variantes": list(variantes), **champs}


# --------------------------------------------------------------------------- #
# M2
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_par_l_echeance_reelle_de_pipecat_un_service_muet_donne_la_phrase_et_la_note(appel):
    regle = _regle(
        OUTIL_ECHOUE,
        ["Je n'arrive pas à finaliser."],
        ensuite={"noter": {"champ": "rendez_vous", "valeur": "a_rappeler"}},
    )
    await appel.monter(
        source_etapes=[
            _appel_d_outil("chercher", {"jour": "demain"}, "call_chercher"),
            _texte("Je n'ai pas pu."),
            _texte("Voilà."),
        ],
        fond_etapes=[_texte("x")],
        reglages={"phrases_regles": [regle]},
    )
    moteur = appel.engine
    moteur._fiche = ReglagesFiche(
        champs=(ChampFiche(nom="rendez_vous", origine="deduit", valeurs=["confirme", "a_rappeler"]),)
    )
    manager = CustomToolManager(moteur)
    manager._agent = moteur.active_agent
    outil = _outil(timeout_ms=300, essais=1, attente_entre_essais_s=0, sans_risque_de_doublon=True)
    gestionnaire, echeance = manager._create_handler(outil, "chercher")
    # Le délai de la requête (0,3 s) x 2 essais, plus la marge : l'échéance RÉELLE de Pipecat.
    assert echeance == pytest.approx(delai_total_s(outil.definition["config"]) + MARGE_ECHEANCE_S)
    moteur.active_agent.llm.register_function(
        "chercher", moteur.active_agent.bind_tool(moteur, gestionnaire), timeout_secs=echeance
    )

    async def muet(*_args, **_kwargs):
        await asyncio.sleep(60)  # le service ne répond jamais

    with patch(f"{MODULE}.httpx.AsyncClient") as client:
        session = AsyncMock()
        session.request.side_effect = muet
        client.return_value.__aenter__.return_value = session
        await appel.ouvrir()
        await appel.attendre(lambda: moteur._gathered_context.get("rendez_vous"), delai=10)
    assert session.request.call_count == 2  # 1 + 1 essai
    assert moteur._gathered_context["rendez_vous"] == "a_rappeler"
    await appel.attendre(
        lambda: any("Je n'arrive pas à finaliser." in str(m.get("content")) for m in appel.messages()),
        delai=10,
    )
    messages = appel.messages()
    assert any(
        "Ce qui vient de se passer : l'outil n'a pas abouti." in str(m.get("content"))
        for m in messages
        if m.get("role") == "tool"
    ), [(m.get("role"), str(m.get("content"))[:80]) for m in messages]


def test_le_delai_de_la_requete_est_un_total_et_l_echeance_a_une_marge():
    outil = _outil(timeout_ms=5000, essais=1, attente_entre_essais_s=1)
    manager = CustomToolManager.__new__(CustomToolManager)
    manager._engine = SimpleNamespace()
    manager._agent = None
    _, echeance = manager._create_handler(outil, "chercher")
    assert echeance == 11.0 + MARGE_ECHEANCE_S and MARGE_ECHEANCE_S >= 5.0


@pytest.mark.asyncio
async def test_une_requete_qui_depasse_le_delai_total_est_la_panne_pas_de_reponse():
    from api.services.workflow.tools.custom_tool import execute_http_tool

    async def lente(*_a, **_k):
        await asyncio.sleep(5)

    with patch(f"{MODULE}.httpx.AsyncClient") as client:
        session = AsyncMock()
        session.request.side_effect = lente
        client.return_value.__aenter__.return_value = session
        debut = asyncio.get_running_loop().time()
        resultat = await execute_http_tool(_outil(timeout_ms=200), {})
    assert asyncio.get_running_loop().time() - debut < 2
    assert resultat["status"] == "error" and "timed out" in resultat["error"]


@pytest.mark.asyncio
async def test_l_action_finale_part_apres_la_remise_du_resultat_et_sans_relancer_le_modele():
    from api.services.workflow.enveloppe_des_actions import envelopper_l_action

    moteur = _Moteur()
    moteur.active_agent.llm = object()
    moteur.active_agent.reglages = {
        "phrases_regles": [
            _regle(OUTIL_ECHOUE, ["Souci."], ensuite={"phrases": ["Au revoir."], "action": "raccrocher"})
        ]
    }
    moteur.phrases = DiseurDePhrases(moteur)
    moteur.phrases.repos_s = lambda: 0.0
    ordre = []

    async def rendre(valeur, *args, **kwargs):
        ordre.append(("remis", kwargs.get("properties") is not None and kwargs["properties"].run_llm))

    async def raccroche(raison):
        ordre.append(("raccroche", raison))

    moteur.end_call_with_reason = raccroche

    async def action(params):
        await params.result_callback({"status": "error", "error": "boom"})

    params = SimpleNamespace(result_callback=rendre, llm=moteur.active_agent.llm, arguments={})
    await envelopper_l_action(moteur, "reserver", action, moteur.active_agent, garde=False)(params)
    for _ in range(50):
        if len(ordre) >= 2:
            break
        await asyncio.sleep(0.01)
    # Le résultat est remis d'abord (le modèle n'est pas relancé), l'appel raccroche ensuite.
    assert ordre[0] == ("remis", False)
    assert ordre[1][0] == "raccroche"


# --------------------------------------------------------------------------- #
# M3 : l'entreprise fermée
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_une_sortie_transferer_ne_part_pas_a_22_heures_ouverte_elle_part():
    regle = _regle(
        OUTIL_ECHOUE,
        ["Souci."],
        ensuite={"action": "transferer", "destination": "accueil"},
    )
    for etat, doit_partir in ((FERME, False), (OUVERT, True), (SUR_RENDEZ_VOUS, True), (None, True)):
        moteur = _Moteur()
        moteur.active_agent.reglages = {"phrases_regles": [regle]}
        moteur.phrases = DiseurDePhrases(moteur)
        moteur.phrases.repos_s = lambda: 0.0
        moteur._call_context_vars = {"etat_ouverture": etat} if etat else {}
        transferer = AsyncMock(return_value=(True, None))
        with patch.object(sorties, "transferer_a", transferer):
            probleme = await moteur.phrases.signaler_un_probleme(OUTIL_ECHOUE)
            if probleme.issue.apres is not None:
                await probleme.issue.apres()
        if doit_partir:
            transferer.assert_awaited_once()
            assert probleme.issue.prise_en_main is True
        else:
            transferer.assert_not_awaited()
            assert probleme.issue.prise_en_main is False and probleme.le_modele_reprend
            assert "transférer" in probleme.issue.interdit


def test_les_etats_d_ouverture_sont_ceux_du_montrage_de_l_outil():
    moteur = SimpleNamespace(_call_context_vars={"etat_ouverture": OUVERT})
    assert sorties.transfert_refuse(moteur) is None
    moteur._call_context_vars = {"etat_ouverture": SUR_RENDEZ_VOUS}
    assert sorties.transfert_refuse(moteur) is None
    moteur._call_context_vars = {"etat_ouverture": FERME}
    assert sorties.transfert_refuse(moteur) is not None


# --------------------------------------------------------------------------- #
# M4
# --------------------------------------------------------------------------- #


def test_transferer_n_est_plus_une_sortie_du_transfert_qui_echoue_et_une_ancienne_regle_se_relit():
    assert "transferer" not in MOTIFS[TRANSFERT_ECHOUE].sorties_permises
    for autre in (OUTIL_ECHOUE, "travail_echoue", "reponse_perdue"):
        assert "transferer" in MOTIFS[autre].sorties_permises
    ancienne = {
        "motif": TRANSFERT_ECHOUE,
        "variantes": ["Personne ne répond."],
        "ensuite": {"action": "transferer", "destination": "accueil", "phrases": ["Un instant."]},
    }
    regle = ReglePhrase.model_validate(ancienne)
    assert regle.ensuite.action == "modele" and regle.ensuite.destination is None
    assert regle.ensuite.phrases == ["Un instant."] and regle.variantes == ["Personne ne répond."]
    phrase = resoudre(TRANSFERT_ECHOUE, reglages_agent={"phrases_regles": [ancienne]})
    assert phrase.action_de_sortie == "modele" and phrase.variantes == ("Personne ne répond.",)
    # La configuration de l'agent l'accepte (zéro perte, jamais une erreur).
    WorkflowConfigurationDefaults.model_validate({"phrases_regles": [ancienne]})


@pytest.mark.asyncio
async def test_une_sortie_de_transfert_deja_passee_interdit_toute_autre():
    moteur = _Moteur()
    moteur.active_agent.reglages = {
        "phrases_regles": [
            _regle(OUTIL_ECHOUE, ["Souci."], ensuite={"action": "transferer", "destination": "accueil"}),
            _regle("travail_echoue", ["Echec."], ensuite={"action": "transferer", "destination": "accueil"}),
        ]
    }
    moteur.phrases = DiseurDePhrases(moteur)
    moteur.phrases.repos_s = lambda: 0.0
    transferer = AsyncMock(return_value=(False, "non abouti"))
    with patch.object(sorties, "transferer_a", transferer):
        premier = await moteur.phrases.signaler_un_probleme(OUTIL_ECHOUE)
        assert premier.issue.prise_en_main is True  # partie en tâche détachée
        await premier.issue.apres()
        # Un autre motif, un autre incident, un nouveau transfert : refusé.
        second = await moteur.phrases.signaler_un_probleme("travail_echoue")
        troisieme = await moteur.phrases.signaler_un_probleme(OUTIL_ECHOUE)
    transferer.assert_awaited_once()
    for refuse in (second, troisieme):
        assert refuse.issue.prise_en_main is False and "transférer" in refuse.issue.interdit


# --------------------------------------------------------------------------- #
# m5
# --------------------------------------------------------------------------- #


def test_une_ancienne_regle_du_silence_sous_le_minimum_est_bornee_jamais_une_erreur():
    ancienne = {
        "motif": APPELANT_SE_TAIT,
        "variantes": ["Êtes-vous toujours là ?"],
        "delai_s": 0.5,
    }
    assert ReglePhrase.model_validate(ancienne).delai_s == MOTIFS[APPELANT_SE_TAIT].delai_min_s == 2.0
    phrase = resoudre(APPELANT_SE_TAIT, reglages_agent={"phrases_regles": [ancienne]})
    assert phrase.niveau == "agent" and phrase.delai_s == 2.0 and phrase.delai_pose is True
    # À l'enregistrement de la configuration : acceptée, bornée.
    configuration = WorkflowConfigurationDefaults.model_validate({"phrases_regles": [ancienne]})
    assert configuration.phrases_regles[0].delai_s == 2.0
