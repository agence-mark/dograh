"""[.mark] passages-fiables, lots F (signalement par l'agent) et G (file de tri, alertes).

Plan `Labo-agent-vocal/plans/passages-fiables/2026-10-28-plan-passages-fiables.md` § 10, R7, L0-9.

| Test | Ce qu'il prouve |
|---|---|
| F outil | absent case éteinte ; offert case allumée (vrai moteur : le téléphone et le clavier partagent `set_node`) ; jamais sur une fin |
| F effet | écrit dans `signalements` (source agent), rien n'est dit, le résultat ne fait pas reparler, deux au plus par appel |
| F clavier | une vraie session clavier : le signalement est dans le run, sans réplique de plus |
| G lecture | chaque trace du code qui mérite un tri est lue ; ce qui est normal ne l'est pas ; le filtre SQL suit la lecture |
| G page bornée | 30 jours, seulement les runs avec un signalement, 50 par page |
| G cloisonnement | une organisation ne lit ni ne modifie le tri ou les alertes d'une autre |
| G statut | écrit dans `annotations["tri"]`, le reste du run ne bouge pas |
| G alertes | écrites par les quatre faits ; la panne du gardien est tracée sans doublon ; pas de serveur de mail : la liste et le journal gardent tout ; un seul mail par appel |
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.tests import MockLLMService
from sqlalchemy import update

from api.db.models import WorkflowRunModel
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.tri import alertes, donnees, pages
from api.services.workflow.pipecat_engine import PipecatEngine
from api.services.workflow.signaler_un_probleme import (
    NOM_OUTIL,
    RESULTAT,
    brancher_signaler_un_probleme,
)
from api.tests.mark.test_clavier_porte_la_fiche import DEFINITION, FICHE, _monter
from api.tests.mark.test_passation_clavier import _dit, _session, _textes, _vide

# --------------------------------------------------------------------------- #
# F : l'outil
# --------------------------------------------------------------------------- #


class _Agent:
    def __init__(self, reglages, fin=False):
        self.reglages = reglages
        self.current_node = SimpleNamespace(name="Étape", is_end=fin)
        self.enregistres = {}
        self.llm = SimpleNamespace(register_function=lambda nom, f: self.enregistres.update({nom: f}))

    def bind_tool(self, moteur, f):
        return f


async def _appeler(agent, **arguments):
    rendu = {}

    async def result_callback(valeur, properties=None):
        rendu["valeur"], rendu["properties"] = valeur, properties

    await agent.enregistres[NOM_OUTIL](SimpleNamespace(arguments=arguments, result_callback=result_callback))
    return rendu


def test_f_l_outil_n_est_offert_que_case_allumee_et_jamais_sur_une_fin():
    moteur = SimpleNamespace(_gathered_context={})
    eteinte = _Agent({})
    assert brancher_signaler_un_probleme(moteur, eteinte, eteinte.current_node) is None and eteinte.enregistres == {}
    allumee = _Agent({"signaler_un_probleme": True})
    schema = brancher_signaler_un_probleme(moteur, allumee, allumee.current_node)
    assert schema.name == NOM_OUTIL and NOM_OUTIL in allumee.enregistres
    assert schema.required == ["motif", "categorie"]
    assert schema.properties["categorie"]["enum"] == list(donnees.CATEGORIES)
    fin = _Agent({"signaler_un_probleme": True}, fin=True)
    assert brancher_signaler_un_probleme(moteur, fin, fin.current_node) is None
    assert WorkflowConfigurationDefaults().signaler_un_probleme is False
    assert WorkflowConfigurationDefaults().alertes_par_mail is False


async def test_f_le_signalement_est_ecrit_rien_n_est_dit_et_l_agent_ne_reparle_pas():
    moteur = SimpleNamespace(_gathered_context={"mark_tour": 3})
    agent = _Agent({"signaler_un_probleme": True})
    brancher_signaler_un_probleme(moteur, agent, agent.current_node)
    rendu = await _appeler(agent, motif="La demande peut vouloir dire deux choses", categorie="demande ambiguë")
    assert rendu["properties"].run_llm is False
    assert rendu["valeur"] == RESULTAT
    (ligne,) = moteur._gathered_context["signalements"]
    assert ligne["source"] == "agent" and ligne["categorie"] == "demande ambiguë"
    assert ligne["motif"].startswith("La demande") and ligne["etape"] == "Étape"


async def test_f_deux_signalements_au_plus_par_appel_le_troisieme_est_ignore_sans_erreur():
    moteur = SimpleNamespace(_gathered_context={})
    agent = _Agent({"signaler_un_probleme": True})
    brancher_signaler_un_probleme(moteur, agent, agent.current_node)
    for numero in range(3):
        rendu = await _appeler(agent, motif=f"motif {numero}", categorie="autre")
        assert rendu["properties"].run_llm is False
    assert [s["motif"] for s in moteur._gathered_context["signalements"]] == ["motif 0", "motif 1"]


async def test_f_une_categorie_inconnue_devient_autre_et_un_motif_trop_long_est_coupe():
    moteur = SimpleNamespace(_gathered_context={})
    agent = _Agent({"signaler_un_probleme": True})
    brancher_signaler_un_probleme(moteur, agent, agent.current_node)
    await _appeler(agent, motif="x" * 1000, categorie="n'importe quoi")
    (ligne,) = moteur._gathered_context["signalements"]
    assert ligne["categorie"] == "autre" and len(ligne["motif"]) == donnees.LONGUEUR_MAX_MOTIF


async def test_f_sans_fiche_ou_sans_arguments_l_outil_ne_leve_pas():
    moteur = SimpleNamespace(_gathered_context=None)
    agent = _Agent({"signaler_un_probleme": True})
    brancher_signaler_un_probleme(moteur, agent, agent.current_node)
    rendu = await _appeler(agent)
    assert rendu["properties"].run_llm is False


async def test_f_un_vrai_moteur_offre_l_outil_case_allumee_et_pas_case_eteinte(three_node_workflow, no_disposition_mapping):
    """Le branchement est dans le moteur (téléphone et clavier : même `set_node`)."""

    async def outils(reglages):
        moteur = PipecatEngine(
            llm=MockLLMService(), context=LLMContext(), workflow=three_node_workflow, call_context_vars={}, workflow_run_id=1
        )
        moteur.active_agent.reglages = reglages
        vus: list[list[str]] = []
        origine = moteur._update_llm_context

        async def espion(prompt, fonctions):
            vus.append([f.name for f in fonctions])
            return await origine(prompt, fonctions)

        moteur._update_llm_context = espion
        await moteur.set_node(moteur.active_agent.workflow.start_node_id)
        return vus[-1]

    assert NOM_OUTIL in await outils({"signaler_un_probleme": True})
    assert NOM_OUTIL not in await outils({})


async def test_f_session_clavier_le_signalement_est_dans_le_run_et_l_agent_n_a_rien_dit_de_plus(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, {**FICHE, "signaler_un_probleme": True})
    appel = MockLLMService.create_function_call_chunks(
        NOM_OUTIL, {"motif": "Règle inconnue pour ce cas", "categorie": "règle inconnue"}, tool_call_id="s1"
    )
    reponses = await _session(
        test_client_factory, user, workflow, [_vide(), _dit(appel)], ["je voudrais une chose bizarre"]
    )
    contexte = reponses[-1]["checkpoint"]["gathered_context"]
    (ligne,) = contexte["signalements"]
    assert ligne["source"] == "agent" and ligne["categorie"] == "règle inconnue"
    assert all(RESULTAT not in dit and "motif" not in dit.lower() for dit in _textes(reponses[-1]))


async def test_f_session_clavier_case_eteinte_l_outil_est_inconnu_et_rien_n_est_ecrit(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, dict(FICHE))
    appel = MockLLMService.create_function_call_chunks(
        NOM_OUTIL, {"motif": "x", "categorie": "autre"}, tool_call_id="s1"
    )
    reponses = await _session(test_client_factory, user, workflow, [_vide(), _dit(appel)], ["bonjour"])
    assert "signalements" not in reponses[-1]["checkpoint"]["gathered_context"]


# --------------------------------------------------------------------------- #
# G : la lecture des signalements du code
# --------------------------------------------------------------------------- #


def _contexte_riche():
    return {
        "signalements": [{"source": "agent", "motif": "perdu", "categorie": "autre", "etape": "A", "tour": 2}],
        "impasse": {"etape": "B", "impasses": 1, "journal": [{"tour": 4, "motif": "impasse", "impasse": 1}, {"tour": 5, "signe": "x"}]},
        "arbitre": [
            {"etape": "A", "choix": "porte_x", "resultat": "porte_inconnue", "tour": 3},
            {"etape": "A", "choix": "rester_dans_l_etape", "resultat": "rien", "tour": 2},
        ],
        "desaccords_arbitre": [{"tour": 6, "etape_de_depart": "A", "arbitre": "porte_y"}],
        "passages_par_le_code": [
            {"etape": "A", "resultat": "prise", "tour": 1},
            {"etape": "A", "resultat": "jetee_la_personne_parle", "tour": 2},
            {"etape": "C", "resultat": "greffier_sans_reponse", "tour": 7},
        ],
        "depassements_modele": 2,
    }


def test_g_chaque_trace_du_code_qui_merite_un_tri_est_lue_et_pas_le_normal():
    lignes = donnees.lire_les_signalements(_contexte_riche())
    types = sorted(ligne["type"] for ligne in lignes)
    assert types == sorted(
        ["agent", "impasse", "porte_inconnue", "desaccord", "passage_sans_suite", "garde_modele"]
    )
    assert len({ligne["id"] for ligne in lignes}) == len(lignes)  # identifiants uniques et stables
    assert {ligne["source"] for ligne in lignes if ligne["type"] != "agent"} == {"code"}


def test_g_un_run_sain_ne_donne_aucune_ligne():
    sain = {
        "arbitre": [{"resultat": "rien"}],
        "passages_par_le_code": [{"resultat": "prise"}],
        "impasse": {"impasses": 0, "journal": [{"signe": "x"}]},
        "depassements_modele": 1,
        "alertes": [],
    }
    assert donnees.lire_les_signalements(sain) == []
    assert donnees.lire_les_signalements(None) == [] and donnees.lire_les_signalements({"signalements": "bizarre"}) == []


def test_g_les_lignes_portent_le_statut_de_tri_du_run():
    run = {"run_id": 1, "workflow_id": 2, "workflow_nom": "A", "cree_le": datetime.now(timezone.utc), "extrait": _contexte_riche(),
           "annotations": {"tri": {"agent:0": {"statut": "résolu"}, "impasse:1": {"statut": "n'importe quoi"}}}}
    par_id = {ligne["id"]: ligne["statut"] for ligne in pages.lignes_de_tri([run])}
    assert par_id["agent:0"] == "résolu" and par_id["impasse:1"] == "ouvert"
    assert [ligne["id"] for ligne in pages.lignes_de_tri([run], "résolu")] == ["agent:0"]


# --------------------------------------------------------------------------- #
# G : la page bornée, le cloisonnement, le statut (vraie base, vraies routes)
# --------------------------------------------------------------------------- #


async def _run(db_session, async_session, user, workflow, contexte, *, jours=0, annotations=None):
    run = await db_session.create_workflow_run(
        "r", workflow.id, "chat", user.id, gathered_context=contexte, organization_id=user.selected_organization_id
    )
    valeurs = {}
    if jours:
        valeurs["created_at"] = datetime.now(timezone.utc) - timedelta(days=jours)
    if annotations is not None:
        valeurs["annotations"] = annotations
    if valeurs:
        await async_session.execute(update(WorkflowRunModel).where(WorkflowRunModel.id == run.id).values(**valeurs))
        await async_session.flush()
    return run


async def test_g_la_page_est_bornee_trente_jours_seulement_les_runs_avec_un_signalement_cinquante_par_page(
    db_session, async_session, test_client_factory
):
    user, workflow = await _monter(db_session, async_session, dict(FICHE))
    avec = {"signalements": [{"source": "agent", "motif": "m", "categorie": "autre"}]}
    for _ in range(52):
        await _run(db_session, async_session, user, workflow, avec)
    vieux = await _run(db_session, async_session, user, workflow, avec, jours=31)
    sans = await _run(db_session, async_session, user, workflow, {"extracted_variables": {"a": 1}})
    normal = await _run(db_session, async_session, user, workflow, {"passages_par_le_code": [{"resultat": "prise"}]})
    async with test_client_factory(user) as client:
        premiere = (await client.get("/api/v1/tri")).json()
        seconde = (await client.get("/api/v1/tri", params={"page": 1})).json()
    assert len({ligne["run_id"] for ligne in premiere["lignes"]}) == 50 and premiere["a_une_suite"] is True
    assert len({ligne["run_id"] for ligne in seconde["lignes"]}) == 2 and seconde["a_une_suite"] is False
    vus = {ligne["run_id"] for ligne in premiere["lignes"] + seconde["lignes"]}
    assert vieux.id not in vus and sans.id not in vus and normal.id not in vus
    assert premiere["jours"] == 30 and premiere["par_page"] == 50


async def test_g_le_filtre_par_agent_et_par_statut(db_session, async_session, test_client_factory):
    user, workflow = await _monter(db_session, async_session, dict(FICHE))
    autre = await db_session.create_workflow(
        name="Autre", workflow_definition=DEFINITION, user_id=user.id, organization_id=user.selected_organization_id,
    )
    avec = {"signalements": [{"source": "agent", "motif": "m", "categorie": "autre"}]}
    run_a = await _run(db_session, async_session, user, workflow, avec)
    run_b = await _run(db_session, async_session, user, autre, avec, annotations={"tri": {"agent:0": {"statut": "résolu"}}})
    async with test_client_factory(user) as client:
        seul_a = (await client.get("/api/v1/tri", params={"workflow_id": workflow.id})).json()["lignes"]
        resolus = (await client.get("/api/v1/tri", params={"statut": "résolu"})).json()["lignes"]
    assert {ligne["run_id"] for ligne in seul_a} == {run_a.id}
    assert [ligne["run_id"] for ligne in resolus] == [run_b.id]


async def test_g_cloisonnement_une_organisation_ne_lit_ni_ne_modifie_le_tri_ou_les_alertes_d_une_autre(
    db_session, async_session, test_client_factory
):
    user_a, workflow_a = await _monter(db_session, async_session, dict(FICHE))
    user_b, workflow_b = await _monter(db_session, async_session, dict(FICHE))
    contexte = {
        "signalements": [{"source": "agent", "motif": "secret de A", "categorie": "autre"}],
        "alertes": [{"type": "outil_en_echec", "detail": "alerte de A"}],
    }
    run_a = await _run(db_session, async_session, user_a, workflow_a, contexte)
    run_b = await _run(db_session, async_session, user_b, workflow_b, {"signalements": [{"source": "agent", "motif": "b", "categorie": "autre"}]})
    async with test_client_factory(user_b) as client:
        tri_b = (await client.get("/api/v1/tri")).json()["lignes"]
        alertes_b = (await client.get("/api/v1/alertes")).json()["lignes"]
        tentative = await client.put(f"/api/v1/tri/{run_a.id}", json={"identifiant": "agent:0", "statut": "résolu"})
        filtre_croise = (await client.get("/api/v1/tri", params={"workflow_id": workflow_a.id})).json()["lignes"]
    assert {ligne["run_id"] for ligne in tri_b} == {run_b.id} and alertes_b == []
    assert tentative.status_code == 404 and filtre_croise == []
    assert "secret de A" not in str(tri_b)
    async with test_client_factory(user_a) as client:
        alertes_a = (await client.get("/api/v1/alertes")).json()["lignes"]
        tri_a = (await client.get("/api/v1/tri")).json()["lignes"]
    assert [a["run_id"] for a in alertes_a] == [run_a.id] and alertes_a[0]["detail"] == "alerte de A"
    assert tri_a[0]["statut"] == "ouvert"  # la tentative de B n'a rien écrit


async def test_g_le_statut_est_ecrit_dans_annotations_sans_toucher_au_reste(db_session, async_session, test_client_factory):
    user, workflow = await _monter(db_session, async_session, dict(FICHE))
    contexte = {"signalements": [{"source": "agent", "motif": "m", "categorie": "autre"}], "extracted_variables": {"nom": "x"}}
    run = await _run(db_session, async_session, user, workflow, contexte, annotations={"mark_apres_appel": {"etapes": {"a": 1}}})
    async with test_client_factory(user) as client:
        ecrit = await client.put(f"/api/v1/tri/{run.id}", json={"identifiant": "agent:0", "statut": "en cours"})
        inconnu = await client.put(f"/api/v1/tri/{run.id}", json={"identifiant": "agent:9", "statut": "résolu"})
        mauvais = await client.put(f"/api/v1/tri/{run.id}", json={"identifiant": "agent:0", "statut": "supprimé"})
        lignes = (await client.get("/api/v1/tri")).json()["lignes"]
    assert ecrit.status_code == 200 and ecrit.json() == {"run_id": run.id, "identifiant": "agent:0", "statut": "en cours"}
    assert inconnu.status_code == 404 and mauvais.status_code == 422
    assert lignes[0]["statut"] == "en cours"
    relu = await db_session.get_workflow_run_by_id(run.id)
    assert relu.annotations["mark_apres_appel"] == {"etapes": {"a": 1}}  # le reste des annotations est intact
    assert relu.annotations["tri"]["agent:0"]["statut"] == "en cours"
    assert relu.gathered_context == contexte  # ce que l'appel a noté n'a pas bougé


async def test_g_la_route_des_alertes_est_bornee_et_scopee(db_session, async_session, test_client_factory):
    user, workflow = await _monter(db_session, async_session, dict(FICHE))
    avec = {"alertes": [{"type": "transfert_echoue", "detail": "d", "heure": "2026-10-28T10:00:00+00:00"}]}
    recent = await _run(db_session, async_session, user, workflow, avec)
    vieux = await _run(db_session, async_session, user, workflow, avec, jours=40)
    sans = await _run(db_session, async_session, user, workflow, {"signalements": [{"motif": "m"}]})
    async with test_client_factory(user) as client:
        lignes = (await client.get("/api/v1/alertes")).json()["lignes"]
    assert [ligne["run_id"] for ligne in lignes] == [recent.id]
    assert vieux.id not in {ligne["run_id"] for ligne in lignes} and sans.id not in {ligne["run_id"] for ligne in lignes}
    assert lignes[0]["type"] == "transfert_echoue" and lignes[0]["id"] == "alerte:0"


# --------------------------------------------------------------------------- #
# G : les alertes pendant l'appel
# --------------------------------------------------------------------------- #


def _moteur(**plus):
    return SimpleNamespace(_gathered_context={}, active_agent=_Agent({}), **plus)


def test_g_les_quatre_faits_ecrivent_une_alerte():
    from api.services.phrases.catalogue import OUTIL_ECHOUE, TRANSFERT_ECHOUE, TRAVAIL_ECHOUE

    moteur = _moteur()
    alertes.alerter_un_fait(moteur, OUTIL_ECHOUE, outil="un_outil")
    alertes.alerter_un_fait(moteur, TRAVAIL_ECHOUE)
    alertes.alerter_un_fait(moteur, TRANSFERT_ECHOUE)
    alertes.alerter_un_fait(moteur, "autre_motif")  # un motif qui n'est pas un échec : rien
    alertes.alerter_la_fin_en_erreur(moteur, "pipeline_error")
    alertes.alerter_la_fin_en_erreur(moteur, "end_call")  # fin normale : rien
    assert [a["type"] for a in moteur._gathered_context["alertes"]] == [
        "outil_en_echec", "outil_en_echec", "transfert_echoue", "appel_en_erreur"
    ]
    assert moteur._gathered_context["alertes"][0]["outil"] == "un_outil"


async def test_g_le_diseur_alerte_meme_quand_la_phrase_est_eteinte():
    from api.services.phrases.catalogue import TRANSFERT_ECHOUE
    from api.services.phrases.diseur import DiseurDePhrases

    moteur = _moteur()
    await DiseurDePhrases(moteur).signaler_un_probleme(TRANSFERT_ECHOUE)
    assert [a["type"] for a in moteur._gathered_context["alertes"]] == ["transfert_echoue"]


def test_g_la_fin_en_erreur_apres_une_panne_dite_par_le_gardien_n_ajoute_pas_de_doublon():
    moteur = _moteur()
    moteur._gathered_context["panne"] = {"decision": "rappel"}
    alertes.alerter_la_fin_en_erreur(moteur, "pipeline_error")
    assert "alertes" not in moteur._gathered_context


async def test_g_la_panne_du_gardien_est_tracee_comme_deja_notifiee():
    from api.services.panne.gardien import ContextePanne, GardienPanne

    moteur = _moteur()
    contexte = ContextePanne(
        run_id=1, organization_id=1, workflow_id=1, reglages=SimpleNamespace(), entrant=True, call_sid=None
    )
    gardien = GardienPanne(contexte, moteur)
    with patch.object(GardienPanne, "_alerter", new=AsyncMock()) as alerter:
        await gardien._noter("modele_lent", "modele", "d", "sans_telephonie", None, None, None)
    (alerte,) = moteur._gathered_context["alertes"]
    assert alerte["type"] == "panne_modele" and alerte["deja_notifiee"] is True
    alerter.assert_called_once()  # le mail est celui du gardien, une seule fois
    assert donnees.lire_les_alertes(moteur._gathered_context)[0]["mail"] == "deja_notifiee"


async def test_g_un_seul_mail_par_appel_il_regroupe_et_ne_redit_pas_la_panne():
    moteur = _moteur()
    moteur.active_agent.reglages = {"alertes_par_mail": True}
    alertes.alerter(moteur, "outil_en_echec", outil="o")
    alertes.alerter(moteur, "transfert_echoue")
    alertes.alerter(moteur, "panne_modele", deja_notifiee=True)
    with patch("api.services.apres_appel.notification.notifier", new=AsyncMock(return_value=["a@x.fr"])) as notifier:
        premier = await alertes.envoyer_le_mail_de_l_appel(moteur, 42, 7)
        second = await alertes.envoyer_le_mail_de_l_appel(moteur, 42, 7)
    assert premier == "envoye" and second is None
    notifier.assert_awaited_once()
    organisation, sujet, texte = notifier.await_args.args
    assert organisation == 7 and "2 alertes" in sujet and "42" in sujet
    assert "outil en échec" in texte and "transfert échoué" in texte and "panne" not in texte
    assert moteur._gathered_context["alertes_mail"]["etat"] == "envoye"


async def test_g_case_eteinte_ou_rien_a_dire_aucun_mail_ne_part():
    moteur = _moteur()
    alertes.alerter(moteur, "outil_en_echec")
    with patch("api.services.apres_appel.notification.notifier", new=AsyncMock(return_value=["a@x.fr"])) as notifier:
        assert await alertes.envoyer_le_mail_de_l_appel(moteur, 1, 1) is None  # case éteinte (défaut)
        vide = _moteur()
        vide.active_agent.reglages = {"alertes_par_mail": True}
        assert await alertes.envoyer_le_mail_de_l_appel(vide, 1, 1) is None  # rien à dire
    notifier.assert_not_called()


async def test_g_sans_serveur_de_mail_l_alerte_reste_dans_la_liste_et_le_journal_jamais_perdue(caplog):
    """Le vrai `notifier`, sans serveur : aucun envoi réel, aucune exception, l'alerte reste lisible."""
    moteur = _moteur()
    moteur.active_agent.reglages = {"alertes_par_mail": True}
    alertes.alerter(moteur, "outil_en_echec", outil="o")
    sans_serveur = SimpleNamespace(adresses_notification=["mark@x.fr"], smtp=SimpleNamespace(configure=False))
    with (
        patch("api.services.apres_appel.notification.adresses_de_lorganisation", new=AsyncMock(return_value=["client@x.fr"])),
        patch("api.services.apres_appel.notification.lire_installation", new=AsyncMock(return_value=(None, sans_serveur))),
        patch("api.services.apres_appel.notification.lire_reglages", new=AsyncMock(return_value=SimpleNamespace(smtp=SimpleNamespace(configure=False)))),
        patch("api.services.apres_appel.mail.envoyer", new=AsyncMock()) as envoi,
    ):
        etat = await alertes.envoyer_le_mail_de_l_appel(moteur, 5, 7)
    envoi.assert_not_called()
    assert etat == "non_envoye"
    (ligne,) = donnees.lire_les_alertes(moteur._gathered_context)
    assert ligne["type"] == "outil_en_echec" and ligne["mail"] == "non_envoye"


async def test_g_un_notifieur_qui_leve_ne_coute_rien_a_l_appel():
    moteur = _moteur()
    moteur.active_agent.reglages = {"alertes_par_mail": True}
    alertes.alerter(moteur, "transfert_echoue")
    with patch("api.services.apres_appel.notification.notifier", new=AsyncMock(side_effect=RuntimeError("smtp"))):
        assert await alertes.envoyer_le_mail_de_l_appel(moteur, 1, 1) is None
    assert len(moteur._gathered_context["alertes"]) == 1


def test_g_au_plus_vingt_alertes_par_appel():
    moteur = _moteur()
    for _ in range(30):
        alertes.alerter(moteur, "outil_en_echec")
    assert len(moteur._gathered_context["alertes"]) == donnees.MAX_ALERTES_PAR_APPEL


def test_g_le_moteur_branche_l_alerte_de_fin_en_erreur_et_le_mail_est_au_telephone_seulement():
    """Garde de câblage : `_end_call` alerte (téléphone et clavier, même moteur) ; le mail part de la fin du pipeline."""
    from pathlib import Path

    racine = Path(__file__).resolve().parents[2] / "services"
    assert "alerter_la_fin_en_erreur(self, call_status)" in (racine / "workflow" / "pipecat_engine.py").read_text(encoding="utf-8")
    assert "envoyer_le_mail_de_l_appel" in (racine / "pipecat" / "event_handlers.py").read_text(encoding="utf-8")
    assert "alerter_un_fait" in (racine / "phrases" / "diseur.py").read_text(encoding="utf-8")
    assert "brancher_signaler_un_probleme" in (racine / "workflow" / "pipecat_engine.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("cle", ["signalements", "impasse", "arbitre", "desaccords_arbitre", "passages_par_le_code", "depassements_modele"])
async def test_g_le_filtre_de_la_base_trouve_chaque_sorte_de_signalement_que_la_lecture_trouve(
    db_session, async_session, test_client_factory, cle
):
    """Le filtre SQL et la lecture en Python partent des mêmes constantes : un run que la lecture trouve est aussi un
    run que la base remonte, pour chacune des six sources."""
    user, workflow = await _monter(db_session, async_session, dict(FICHE))
    contexte = {cle: _contexte_riche()[cle]}
    assert donnees.lire_les_signalements(contexte), cle
    run = await _run(db_session, async_session, user, workflow, contexte)
    async with test_client_factory(user) as client:
        lignes = (await client.get("/api/v1/tri")).json()["lignes"]
    assert {ligne["run_id"] for ligne in lignes} == {run.id}
