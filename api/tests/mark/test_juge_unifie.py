"""[.mark] Partie 2, U6 (sous-lot 2) : le juge v1, le juge des vrais appels par agent (J3) et les outils MCP du juge.

Ce qui doit tenir : un verdict hors forme (sans réplique citée, preuve qui n'est pas une citation exacte, critère inconnu ou manquant)
est REFUSÉ avec la raison ; « non vérifiable » compte comme raté ; le réglage par agent est côté serveur, éteint par défaut ; l'après-appel
écrit FUSIONNÉ sous la clé ``juge`` ; sur Claude Code l'appel reste « à juger » sans aucun appel à un fournisseur ; un juge en panne ou
refusé (D9) n'abîme rien ; tout est cloisonné par organisation. Cerveaux simulés, aucune dépense.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.routes import reglages_agent as route
from api.schemas.appel_simule import ReglagesAppelantSimule, RoleSimule
from api.services.builder.actions import juge as actions_juge
from api.services.builder.actions.registre import PORTE_MCP, Contexte, executer
from api.services.builder.cerveau import independance, simules
from api.services.builder.cerveau import reglages as reglages_cerveau
from api.services.builder.cerveau.factice import CerveauFactice, texte, tour
from api.services.builder.cerveau.reglages import ReglagesCerveau
from api.services.juge import appels, file, passes
from api.services.juge import verdicts as v
from api.tests.mark.builder_commun import AGENT, ORG_AUTRE, ORG_CLIENT, utilisateur
from api.tests.mark.test_builder_tests_agent import EQUIPE, MoteurFactice, banc  # noqa: F401 -- la fixture `banc`

LIGNES = [("agent", "Bonjour, que puis-je faire pour vous ?"), ("moi", "Je voudrais un rendez-vous demain."), ("agent", "C'est noté, au revoir.")]
CRITERES = ["Suit le parcours", "Paraît naturel"]


def verdict(critere, *, verdict="reussi", replique=3, preuve="C'est noté", confiance=0.9):
    return {"critere": critere, "verdict": verdict, "replique": replique, "preuve": preuve, "confiance": confiance}


def valides():
    return [verdict(CRITERES[0]), verdict(CRITERES[1], replique=1, preuve="que puis-je faire pour vous")]


# --- la forme d'un verdict -------------------------------------------------------------------------------------------


def test_des_verdicts_complets_avec_citation_exacte_passent():
    sortie = v.verifier(valides(), LIGNES, CRITERES)
    assert [x["critere"] for x in sortie] == CRITERES and v.reussi(sortie)


@pytest.mark.parametrize(
    ("verdicts", "raison"),
    [
        ([verdict(CRITERES[0], replique=None), verdict(CRITERES[1])], "quoted line must exist"),
        ([verdict(CRITERES[0], replique=9), verdict(CRITERES[1])], "quoted line must exist"),
        ([verdict(CRITERES[0], preuve="une phrase jamais dite"), verdict(CRITERES[1])], "exact quote"),
        ([verdict(CRITERES[0], preuve=""), verdict(CRITERES[1])], "proof is required"),
        ([verdict(CRITERES[0], verdict="peut-etre"), verdict(CRITERES[1])], "verdict must be one of"),
        ([verdict("Inventé"), verdict(CRITERES[1])], "Unknown criterion"),
        ([verdict(CRITERES[0])], "Missing verdict"),
        ([verdict(CRITERES[0]), verdict(CRITERES[0]), verdict(CRITERES[1])], "judged twice"),
        ([verdict(CRITERES[0], confiance=3), verdict(CRITERES[1])], "confidence"),
    ],
)
def test_un_verdict_hors_forme_est_refuse_avec_sa_raison(verdicts, raison):
    with pytest.raises(v.VerdictRefuse, match=raison):
        v.verifier(verdicts, LIGNES, CRITERES)


def test_non_verifiable_compte_comme_rate_et_peut_se_passer_de_citation():
    sortie = v.verifier(
        [verdict(CRITERES[0]), verdict(CRITERES[1], verdict="non_verifiable", replique=None, preuve="No tool call to read.")], LIGNES, CRITERES
    )
    assert v.reussi(sortie) is False


# --- le juge sur clé : une passe par critère, vote si serré -----------------------------------------------------------


def _json(**champs):
    import json

    return texte(json.dumps({"critere": "x", "verdict": "reussi", "replique": 3, "preuve": "C'est noté", "confiance": 0.9, **champs}))


async def test_une_passe_par_critere_quand_la_confiance_est_bonne(monde):
    cerveau = CerveauFactice(tour(_json()), tour(_json(replique=1, preuve="que puis-je faire")))
    rendu = await passes.juger(cerveau, LIGNES, CRITERES)
    assert [x["passes"] for x in rendu["verdicts"]] == [1, 1] and rendu["reussi"] is True


async def test_serre_trois_passes_et_vote_a_la_majorite(monde):
    faible = _json(verdict="rate", confiance=0.3)
    cerveau = CerveauFactice(tour(faible), tour(_json(verdict="rate", confiance=0.4)), tour(_json(confiance=0.5)), tour(_json()))
    rendu = await passes.juger(cerveau, LIGNES, ["Suit le parcours"])
    assert rendu["verdicts"][0]["verdict"] == "rate" and rendu["verdicts"][0]["serre"] is True and rendu["reussi"] is False


async def test_une_reponse_hors_forme_est_ecartee_jamais_corrigee(monde):
    cerveau = CerveauFactice(tour(_json(preuve="inventée")), tour(texte("n'importe quoi")), tour(_json(preuve="encore inventée")))
    rendu = await passes.juger(cerveau, LIGNES, ["Suit le parcours"])
    assert rendu["verdicts"][0]["verdict"] == "non_verifiable" and rendu["reussi"] is False


# --- le réglage par agent (J3), côté serveur ---------------------------------------------------------------------------


async def test_le_juge_des_vrais_appels_est_eteint_par_defaut_et_se_regle_par_agent(monde):
    assert await file.juge_des_vrais_appels(ORG_CLIENT, AGENT) is False
    await file.regler(ORG_CLIENT, AGENT, True)
    assert await file.juge_des_vrais_appels(ORG_CLIENT, AGENT) is True
    assert await file.juge_des_vrais_appels(ORG_CLIENT, AGENT + 1) is False
    assert await file.juge_des_vrais_appels(ORG_AUTRE, AGENT) is False


async def test_la_route_du_reglage_est_bornee_a_l_organisation(monde, monkeypatch):
    monkeypatch.setattr(route.db_client, "get_workflow", AsyncMock(side_effect=lambda wid, organization_id: SimpleNamespace(id=wid) if organization_id == ORG_CLIENT else None))
    moi, autre = utilisateur(1, ORG_CLIENT), utilisateur(2, ORG_AUTRE)
    assert (await route.lire_le_juge_des_vrais_appels(AGENT, moi)).actif is False
    assert (await route.regler_le_juge_des_vrais_appels(AGENT, route.JugeDesVraisAppels(actif=True), moi)).actif is True
    assert (await route.lire_le_juge_des_vrais_appels(AGENT, moi)).actif is True
    for appel in (route.lire_le_juge_des_vrais_appels(AGENT, autre), route.regler_le_juge_des_vrais_appels(AGENT, route.JugeDesVraisAppels(actif=True), autre)):
        with pytest.raises(HTTPException) as erreur:
            await appel
        assert erreur.value.status_code == 404


# --- l'après-appel ------------------------------------------------------------------------------------------------------


def _run(identifiant=5, **champs):
    journal = [
        {"type": "rtf-bot-text", "payload": {"text": LIGNES[0][1]}, "timestamp": "2026-11-03T10:00:00+00:00", "turn": 0},
        {"type": "rtf-user-transcription", "payload": {"text": LIGNES[1][1], "final": True}, "timestamp": "2026-11-03T10:00:02+00:00", "turn": 1},
        {"type": "rtf-bot-text", "payload": {"text": LIGNES[2][1]}, "timestamp": "2026-11-03T10:00:04+00:00", "turn": 2},
    ]
    base = dict(id=identifiant, workflow_id=AGENT, logs={"realtime_feedback_events": journal}, gathered_context={}, annotations={}, definition=None)
    return SimpleNamespace(**{**base, **champs})


@pytest.fixture
def mondes(monde, monkeypatch):
    """Le monde + la base des runs (écritures d'annotations) + les réglages du Labo, tous simulés."""
    ecrits: list[tuple[int, dict]] = []
    notes: list[tuple[int, float | None]] = []
    base = SimpleNamespace(
        update_workflow_run=AsyncMock(side_effect=lambda run_id, annotations=None, **_: ecrits.append((run_id, annotations))),
        ecrire_note_juge=AsyncMock(side_effect=lambda run_id, note: notes.append((run_id, note))),
        get_workflow_run_with_context=AsyncMock(return_value=(_run(), ORG_CLIENT)),
    )
    for module in (appels, actions_juge):
        monkeypatch.setattr(module, "db_client", base)
    monkeypatch.setattr(reglages_cerveau, "lire", AsyncMock(return_value=ReglagesCerveau(modele="builder-m")))
    monkeypatch.setattr(appels, "_modele_de_l_agent", AsyncMock(return_value="agent-m"))
    base.ecrits = ecrits
    base.notes = notes
    return base


def _juge(monkeypatch, **champs):
    champs.setdefault("actif", True)  # lot 12 (SE-23) : un rôle neuf est éteint
    roles = ReglagesAppelantSimule(appelant=RoleSimule(consigne="c"), juge=RoleSimule(consigne="j", **champs))
    from api.services.appel_simule import reglages as appel_simule

    monkeypatch.setattr(appel_simule, "lire_reglages", AsyncMock(return_value=roles))


async def test_agent_eteint_l_appel_n_est_pas_juge(mondes, monkeypatch):
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k")
    fabrique = AsyncMock()
    monkeypatch.setattr(simules, "cerveau_du_role", fabrique)
    await appels.apres_appel(_run(), ORG_CLIENT)
    assert mondes.ecrits == [] and fabrique.await_count == 0


async def test_sur_cle_l_appel_est_juge_et_ecrit_fusionne_sous_la_cle_juge(mondes, monkeypatch):
    await file.regler(ORG_CLIENT, AGENT, True)
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k")
    sorties = [_json(critere=c) for c in range(0)]  # un tour par critère de la grille
    grille = await appels.grille()
    cerveau = CerveauFactice(*[tour(_json()) for _ in grille])
    monkeypatch.setattr(simules, "cerveau_du_role", AsyncMock(return_value=cerveau))
    await appels.apres_appel(_run(), ORG_CLIENT)
    (run_id, annotations), = mondes.ecrits
    assert run_id == 5 and list(annotations) == ["juge"]  # seule la clé « juge » : QA et « À trier » gardent la leur
    assert annotations["juge"]["etat"] == "juge" and len(annotations["juge"]["verdicts"]) == len(grille) == 6 and sorties == []


async def test_la_note_du_juge_est_gardee_avec_le_resultat_sur_cle_et_effacee_hors_juge(mondes, monkeypatch):
    await file.regler(ORG_CLIENT, AGENT, True)
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k")
    grille = await appels.grille()
    cerveau = CerveauFactice(*[tour(_json()) for _ in grille])
    monkeypatch.setattr(simules, "cerveau_du_role", AsyncMock(return_value=cerveau))
    await appels.apres_appel(_run(), ORG_CLIENT)
    assert mondes.notes == [(5, 5.0)]  # 6 critères réussis sur 6
    # Claude Code : l'appel attend, la note est effacée (un ancien jugement ne reste pas)
    _juge(monkeypatch, source="claude_code")
    await appels.apres_appel(_run(), ORG_CLIENT)
    assert mondes.notes[-1] == (5, None)


async def test_sur_claude_code_l_appel_reste_a_juger_sans_aucun_appel_de_fournisseur(mondes, monkeypatch):
    await file.regler(ORG_CLIENT, AGENT, True)
    _juge(monkeypatch, source="claude_code")
    fabrique = AsyncMock()
    monkeypatch.setattr(simules, "cerveau_du_role", fabrique)
    await appels.apres_appel(_run(), ORG_CLIENT)
    assert fabrique.await_count == 0
    assert [i["id"] for i in await file.lister(ORG_CLIENT)] == ["appel-5"]
    assert mondes.ecrits[0][1]["juge"]["etat"] == "a_juger" and mondes.ecrits[0][1]["juge"]["mention"] == independance.MENTION_CLAUDE_CODE


async def test_un_juge_du_modele_de_l_agent_ne_juge_pas_et_le_dit(mondes, monkeypatch):
    await file.regler(ORG_CLIENT, AGENT, True)
    _juge(monkeypatch, modele="mistral/agent-m", identifiant="k")
    await appels.apres_appel(_run(), ORG_CLIENT)
    assert mondes.ecrits[0][1]["juge"]["etat"] == "refuse"


async def test_un_juge_en_panne_n_abime_pas_l_apres_appel(mondes, monkeypatch):
    await file.regler(ORG_CLIENT, AGENT, True)
    _juge(monkeypatch, modele="openai/juge-m", identifiant="k")
    monkeypatch.setattr(simules, "cerveau_du_role", AsyncMock(side_effect=RuntimeError("panne")))
    await appels.apres_appel(_run(), ORG_CLIENT)  # ne lève pas
    await appels.apres_appel(SimpleNamespace(id=None), ORG_CLIENT)  # run illisible : ne lève pas non plus


async def test_un_appel_d_essai_n_est_jamais_un_vrai_appel(mondes, monkeypatch):
    await file.regler(ORG_CLIENT, AGENT, True)
    _juge(monkeypatch, source="claude_code")
    await appels.apres_appel(_run(annotations={"tester": {"source": "test_agent"}}), ORG_CLIENT)
    assert await file.lister(ORG_CLIENT) == []


# --- les trois outils MCP : /juger et /analyser --------------------------------------------------------------------------


MCP = Contexte(user=utilisateur(1, ORG_CLIENT), porte=PORTE_MCP)
MCP_AUTRE = Contexte(user=utilisateur(2, ORG_AUTRE), porte=PORTE_MCP)


async def test_le_cycle_a_faire_lire_ecrire_d_un_vrai_appel(mondes):
    await file.ajouter(ORG_CLIENT, {"id": "appel-5", "type": "appel", "workflow_id": AGENT, "run_id": 5})
    liste = await executer("juge_a_faire", {}, MCP)
    assert liste["total"] == 1 and liste["a_juger"][0]["id"] == "appel-5"
    dossier = await executer("juge_lire", {"id": "appel-5"}, MCP)
    assert [t["n"] for t in dossier["transcription"]] == [1, 2, 3] and len(dossier["criteres"]) == 6 and dossier["consigne"]
    verdicts = [verdict(c) for c in dossier["criteres"]]
    ok = await executer("juge_ecrire", {"id": "appel-5", "verdicts": verdicts}, MCP)
    assert ok["ok"] is True and ok["reussi"] is True and ok["mention"] == independance.MENTION_CLAUDE_CODE
    (run_id, annotations), = mondes.ecrits
    assert run_id == 5 and annotations["juge"]["source"] == "claude_code" and annotations["juge"]["etat"] == "juge"
    assert (await executer("juge_a_faire", {}, MCP))["total"] == 0  # jugé : il sort de la file
    assert mondes.notes == [(5, 5.0)]  # la même fonction d'écriture que le juge sur clé : la note suit


async def test_un_verdict_sans_replique_citee_est_refuse_et_l_element_reste_a_juger(mondes):
    await file.ajouter(ORG_CLIENT, {"id": "appel-5", "type": "appel", "workflow_id": AGENT, "run_id": 5})
    criteres = (await executer("juge_lire", {"id": "appel-5"}, MCP))["criteres"]
    sans = [verdict(c, replique=None) for c in criteres]
    refus = await executer("juge_ecrire", {"id": "appel-5", "verdicts": sans}, MCP)
    assert refus["ok"] is False and refus["code"] == "verdict_refuse" and "quoted line" in refus["erreur"]
    assert mondes.ecrits == [] and (await executer("juge_a_faire", {}, MCP))["total"] == 1


async def test_un_test_a_juger_porte_ses_propres_questions(mondes):
    item = {"id": "test-42-t", "type": "test", "workflow_id": AGENT, "test": "t", "criteres": ["Le ton est-il naturel ?"], "lignes": [list(x) for x in LIGNES]}
    await file.ajouter(ORG_CLIENT, item)
    dossier = await executer("juge_lire", {"id": "test-42-t"}, MCP)
    assert dossier["criteres"] == ["Le ton est-il naturel ?"]
    ok = await executer("juge_ecrire", {"id": "test-42-t", "verdicts": [verdict("Le ton est-il naturel ?")]}, MCP)
    assert ok["ok"] is True and mondes.ecrits == []  # un test n'écrit dans aucun run


async def test_la_file_et_les_dossiers_sont_cloisonnes_par_organisation(mondes):
    await file.ajouter(ORG_CLIENT, {"id": "appel-5", "type": "appel", "workflow_id": AGENT, "run_id": 5})
    assert (await executer("juge_a_faire", {}, MCP_AUTRE))["total"] == 0
    assert (await executer("juge_lire", {"id": "appel-5"}, MCP_AUTRE))["ok"] is False
    pirate = await executer("juge_ecrire", {"id": "appel-5", "verdicts": [verdict("x")]}, MCP_AUTRE)
    assert pirate["ok"] is False and mondes.ecrits == []
    # un run d'une autre organisation que celle de l'élément est introuvable, même si l'élément existe
    mondes.get_workflow_run_with_context.return_value = (_run(), ORG_AUTRE)
    assert (await executer("juge_lire", {"id": "appel-5"}, MCP))["code"] == "introuvable"


# --- les tests du builder sur Claude Code : rangés « à juger » -----------------------------------------------------------


async def test_un_test_dont_le_juge_est_sur_claude_code_attend_dans_la_file(banc, monkeypatch):
    from api.services.appel_simule import reglages as appel_simule
    from api.services.builder.tests_agent import creation, execution

    roles = ReglagesAppelantSimule(appelant=RoleSimule(consigne="c", identifiant="k1"), juge=RoleSimule(consigne="j", source="claude_code"))
    monkeypatch.setattr(appel_simule, "lire_reglages", AsyncMock(return_value=roles))
    monkeypatch.setattr(reglages_cerveau, "lire", AsyncMock(return_value=ReglagesCerveau(modele="builder-m")))
    monkeypatch.setattr(reglages_cerveau, "organisation_des_reglages", AsyncMock(return_value=1))
    monkeypatch.setattr(execution, "_modele_de_l_agent", AsyncMock(return_value="agent-m"))
    monkeypatch.setattr(simules, "cerveau_du_role", AsyncMock(return_value=CerveauFactice(tour(texte("Un rendez-vous.")))))
    await creation.creer(ORG_CLIENT, AGENT, nom="Libre", scenario="Un rendez-vous.", criteres=[{"type": "appel_clos_par_l_agent"}], questions_juge=["Le ton est-il naturel ?"])
    execution.DEPENDANCES.moteur = MoteurFactice(["Bonjour.", "Noté, au revoir."], fin_au_tour=1).en_moteur
    agent = SimpleNamespace(id=AGENT, user_id=1, organization_id=ORG_CLIENT, workflow_configurations={})
    await execution.rejouer_la_suite(EQUIPE.user, agent, repetitions=1)
    (item,) = await file.lister(ORG_CLIENT)
    assert item["type"] == "test" and item["criteres"] == ["Le ton est-il naturel ?"] and item["lignes"]
