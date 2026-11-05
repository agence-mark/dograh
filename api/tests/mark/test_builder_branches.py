"""[.mark] Builder partie 3, SA-L3d, sous-lot 2 : le builder et les branches d'agent.

| Test | Ce qu'il prouve |
|---|---|
| lire | ``branches_lire`` rend les branches, leur part de trafic (la principale prend le reste) et la branche de travail |
| créer | ``branche_creer`` ouvre une branche à 0 % du trafic, sans toucher la principale ; nom pris refusé ; journalisé |
| travailler | après ``branche_travailler``, passer un outil de version écrit dans le brouillon de la BRANCHE, jamais dans la principale ; une branche inconnue ou d'un autre agent est refusée |
| passer un outil | par nom ou par identifiant ; l'agent en ligne garde sa version ; un nom ambigu ou inconnu est refusé ; cloisonné par organisation |
| interdits | fusionner, régler la part du trafic et publier n'existent pas pour le builder (refus explicite) |
| tours suivants | la branche choisie reste ouverte aux tours suivants de la conversation, et l'en-tête de l'écran garde la priorité |
"""

from __future__ import annotations

import pytest

from api.db import branche_ouverte
from api.services.builder.actions import registre
from api.services.builder.actions.registre import Contexte
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_outils_versions import _agent, _outil
from api.tests.mark.test_sous_dossiers_et_groupe import _oublier, autre_org, org  # noqa: F401


@pytest.fixture(autouse=True)
def _branche_fermee():
    branche_ouverte.ouvrir(None, None)
    yield
    branche_ouverte.ouvrir(None, None)


def _contexte(org, agent) -> Contexte:
    return Contexte(user=org.utilisateur, workflow_id=agent.id, conversation={})


async def _monde(org, db_session):
    outil = await _outil(db_session, org, "reserver")
    agent = await _agent(db_session, org, outil.tool_uuid)
    await db_session.update_tool(outil.tool_uuid, org.organisation.id, description="v2", user_id=org.utilisateur.id)
    return outil, agent


async def test_branches_lire_rend_les_parts_et_la_branche_de_travail(org, db_session):
    _, agent = await _monde(org, db_session)
    ctx = _contexte(org, agent)
    vide = await registre.executer("branches_lire", {}, ctx)
    assert vide["ok"] and [(b["nom"], b["part"], b["principale"]) for b in vide["branches"]] == [("Principale", 100, True)]
    assert vide["branche_de_travail"] is None
    cree = await registre.executer("branche_creer", {"nom": "Essai"}, ctx)
    lu = await registre.executer("branches_lire", {}, ctx)
    assert [(b["nom"], b["part"]) for b in lu["branches"]] == [("Principale", 100), ("Essai", 0)]
    assert cree["id"] == lu["branches"][1]["id"]


async def test_branche_creer_part_a_zero_refuse_un_nom_pris_et_journalise(org, db_session):
    _, agent = await _monde(org, db_session)
    ctx = _contexte(org, agent)
    cree = await registre.executer("branche_creer", {"nom": "Essai"}, ctx)
    assert cree["ok"] and cree["part_trafic"] == 0
    assert (await db_session.get_draft_version(agent.id)) is None  # la principale n'a rien reçu
    pris = await registre.executer("branche_creer", {"nom": "essai"}, ctx)
    assert pris["ok"] is False and pris["code"] == "nom_pris"
    inconnue = await registre.executer("branche_creer", {"nom": "Autre", "depuis_version": 99}, ctx)
    assert inconnue["ok"] is False and inconnue["code"] == "introuvable"
    lignes, _ = await db_session.lister_journal(limit=20, offset=0, organization_id=org.organisation.id)
    assert any(l["action"] == "agents.branche_creee" and l["detail"].get("par") == "builder" for l in lignes)


async def test_travailler_sur_une_branche_ecrit_dans_son_brouillon_et_jamais_dans_la_principale(org, db_session):
    outil, agent = await _monde(org, db_session)
    ctx = _contexte(org, agent)
    cree = await registre.executer("branche_creer", {"nom": "Essai"}, ctx)
    ouverte = await registre.executer("branche_travailler", {"branche_id": cree["id"]}, ctx)
    assert ouverte == {"ok": True, "branche_de_travail": cree["id"], "nom": "Essai"}
    assert ctx.conversation["branche"] == cree["id"]
    fait = await registre.executer("outil_passer_a_la_version", {"outil": "reserver", "version": 2}, ctx)
    assert fait["ok"] and fait["version"] == 2 and "DRAFT" in fait["suite"]
    lu = await registre.executer("outils_versions_lire", {}, ctx)
    assert lu["source"] == "brouillon" and [(o["nom"], o["epinglee"], o["courante"]) for o in lu["outils"]] == [("reserver", 2, 2)]
    # de retour sur la principale : rien n'a bougé, ni brouillon ni version en ligne
    retour = await registre.executer("branche_travailler", {"branche_id": None}, ctx)
    assert retour["branche_de_travail"] is None and ctx.conversation["branche"] is None
    assert await db_session.get_draft_version(agent.id) is None
    principale = await registre.executer("outils_versions_lire", {}, ctx)
    assert principale["source"] == "en_ligne" and [(o["epinglee"], o["courante"]) for o in principale["outils"]] == [(1, 2)]


async def test_travailler_refuse_une_branche_inconnue_archivee_ou_d_un_autre_agent(org, db_session):
    outil, agent = await _monde(org, db_session)
    autre = await _agent(db_session, org, outil.tool_uuid, nom="Autre agent")
    ctx = _contexte(org, agent)
    chez_l_autre = await registre.executer("branche_creer", {"workflow_id": autre.id, "nom": "Ailleurs"}, _contexte(org, autre))
    for visee in (999999, chez_l_autre["id"]):
        refus = await registre.executer("branche_travailler", {"branche_id": visee}, ctx)
        assert refus["ok"] is False and refus["code"] == "introuvable"
    assert ctx.conversation == {}


async def test_passer_un_outil_par_son_identifiant_et_refuser_l_inconnu_et_l_ambigu(org, autre_org, db_session):
    outil, agent = await _monde(org, db_session)
    ctx = _contexte(org, agent)
    par_uuid = await registre.executer("outil_passer_a_la_version", {"outil": outil.tool_uuid, "version": 2}, ctx)
    assert par_uuid["ok"]
    lignes, _ = await db_session.lister_journal(limit=20, offset=0, organization_id=org.organisation.id)
    assert any(l["action"] == "agents.outil_version_changee" and l["detail"].get("par") == "builder" for l in lignes)
    inconnu = await registre.executer("outil_passer_a_la_version", {"outil": "n'existe-pas", "version": 2}, ctx)
    assert inconnu["ok"] is False and inconnu["code"] == "pas_utilise"
    mauvaise_version = await registre.executer("outil_passer_a_la_version", {"outil": "reserver", "version": 9}, ctx)
    assert mauvaise_version["ok"] is False
    etranger = Contexte(user=autre_org.utilisateur, workflow_id=agent.id, conversation={})
    refus = await registre.executer("outil_passer_a_la_version", {"outil": "reserver", "version": 2}, etranger)
    assert refus["ok"] is False and refus["code"] == "introuvable"
    assert (await registre.executer("branches_lire", {}, etranger))["ok"] is False


@pytest.mark.parametrize("nom", ["fusionner_une_branche", "branche_fusionner", "repartition_regler", "regler_la_repartition", "publier", "publier_agent", "branche_publier"])
async def test_fusionner_regler_la_part_et_publier_restent_des_gestes_de_personne(nom, org, db_session):
    _, agent = await _monde(org, db_session)
    refus = await registre.executer(nom, {}, _contexte(org, agent))
    assert refus["ok"] is False
    assert nom not in registre.REGISTRE


def test_les_actions_de_branches_sont_dans_le_registre_avec_leur_famille():
    attendues = {
        "branches_lire": False,
        "branche_creer": True,
        "branche_travailler": False,
        "outils_versions_lire": False,
        "outil_passer_a_la_version": True,
    }
    for nom, ecriture in attendues.items():
        action = registre.REGISTRE[nom]
        assert action.groupe == "branches" and action.ecriture is ecriture and action.moteur and action.mcp
    from api.services.builder.sauvegarde import MODIFIENT_L_AGENT

    assert "outil_passer_a_la_version" in MODIFIENT_L_AGENT  # la sauvegarde avant modification la couvre


async def test_la_branche_choisie_reste_ouverte_aux_tours_suivants_et_l_entete_de_l_ecran_garde_la_priorite(monde):
    from api.services.builder import contexte, moteur
    from api.services.builder.cerveau.factice import CerveauFactice, texte, tour
    from api.services.builder.cerveau.reglages import ReglagesCerveau
    from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, utilisateur

    ctx = Contexte(user=utilisateur(1), workflow_id=AGENT)
    conv = await contexte.charger(ORG_CLIENT, AGENT)
    conv["branche"] = 5
    await contexte.enregistrer(ORG_CLIENT, AGENT, conv)
    reglages = ReglagesCerveau(modele="factice")
    _ = [e async for e in moteur.conversation(ctx, "Bonjour", CerveauFactice(tour(texte("Oui."))), reglages)]
    assert branche_ouverte.courante().branch_id == 5
    # l'écran a ouvert la branche 8 : elle garde la priorité
    branche_ouverte.ouvrir(8, 1)
    _ = [e async for e in moteur.conversation(ctx, "Encore", CerveauFactice(tour(texte("Oui."))), reglages)]
    assert branche_ouverte.courante().branch_id == 8
