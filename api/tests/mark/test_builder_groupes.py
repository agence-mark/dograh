"""[.mark] Builder partie 3, L5b (sous-lot 3) : le builder lit, crée et règle un groupe d'agents, par les fonctions de ``services/groupe/``.

| Test | Ce qu'il prouve |
|---|---|
| créer | ``groupe_creer`` pose le principal (liste de spécialisés vide) et son sous-dossier (refuse un nom vide et le dossier d'une autre organisation), et journalise « par le builder » ; ``groupe_specialise_creer`` ajoute un spécialisé lié des deux côtés avec son outil de passation |
| lire | ``groupes_lister`` rend le principal et ses spécialisés ; ``groupe_lire`` (par le principal ou par un spécialisé) rend le groupe et les réglages de passation avec leurs défauts d'un groupe ; un agent seul rend ``groupe: null`` |
| régler | ``groupe_regler`` écrit plafond, passation sans résumé, préchauffage, renvoi unique, phrase de mise en relation et attente dans le BROUILLON du principal (la version publiée ne bouge pas), sans effacer le reste de ``attente`` ni de ``transfert_humain`` ; les spécialisés reçoivent la recopie |
| cerveau propre | un spécialisé du groupe garde son cerveau (jamais écrasé), puis se rattache et reprend celui du principal |
| refus | un agent seul, un agent qui n'est pas du groupe, un spécialisé d'un autre principal, un réglage hors bornes, aucun réglage donné, ``specialise_id`` sans ``cerveau_propre`` : refusés, rien n'est écrit |
| cloisonnement | l'agent d'une autre organisation est introuvable pour chaque action ; ``groupes_lister`` ne rend que les groupes de l'organisation |
| gestes de personne | publier un groupe et archiver existent (N1) et demandent une carte en « Demander » |
| sauvegarde | avec l'option « sauvegarde avant modification » allumée, régler un groupe existant exige la sauvegarde (comme tout réglage) |
"""

from __future__ import annotations

import pytest

from api.services.builder.actions import registre
from api.services.builder.actions.registre import Contexte
from api.services.equipe_mark.permissions import PERMISSIONS
from api.services.groupe import groupe as service
from api.services.groupe.passations import CLE_AGENT_PRINCIPAL, CLE_AGENTS_SPECIALISES
from api.services.groupe.reglages import CLE_CERVEAU_PROPRE
from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import _agent, _oublier, _reglages, autre_org, org  # noqa: F401


def _ctx(org, workflow_id=None) -> Contexte:
    # N1 : le chat « Tout permettre », par une personne qui a les droits (ce que ce fichier prouve est le groupe, pas la permission).
    return Contexte(user=org.utilisateur, workflow_id=workflow_id, conversation={"mode": "tout"}, permissions=frozenset(PERMISSIONS))


async def _groupe(org, nom="Standard", specialises=("Devis", "Urgence")):
    """Un groupe créé PAR LES ACTIONS du builder : (principal, [spécialisés])."""
    cree = await registre.executer("groupe_creer", {"nom": nom}, _ctx(org))
    assert cree["ok"], cree
    ids = []
    for nom_s in specialises:
        r = await registre.executer("groupe_specialise_creer", {"workflow_id": cree["workflow_id"], "nom": nom_s}, _ctx(org))
        assert r["ok"], r
        ids.append(r["workflow_id"])
    return cree["workflow_id"], ids


async def test_groupe_creer_pose_le_principal_et_son_dossier_et_le_specialise_est_lie_des_deux_cotes(org, db_session, async_session):
    principal, specialises = await _groupe(org, specialises=("Devis",))
    await _oublier(async_session)
    reglages = await _reglages(db_session, org, principal)
    assert reglages[CLE_AGENTS_SPECIALISES] == specialises  # le principal liste son spécialisé
    assert (await _reglages(db_session, org, specialises[0]))[CLE_AGENT_PRINCIPAL] == principal  # et le spécialisé nomme son principal
    agent = await service.lire_agent(principal, org.organisation.id)
    assert agent is not None and agent.folder_id is not None  # le sous-dossier du groupe
    assert (await service.lire_agent(specialises[0], org.organisation.id)).folder_id == agent.folder_id


async def test_groupe_creer_refuse_un_nom_vide_et_un_dossier_d_une_autre_organisation(org, autre_org, db_session):
    vide = await registre.executer("groupe_creer", {"nom": "   "}, _ctx(org))
    assert vide["ok"] is False
    dossier = await db_session.create_folder(name="Chez l'autre", organization_id=autre_org.organisation.id, parent_id=None)
    refus = await registre.executer("groupe_creer", {"nom": "Intrus", "dossier_id": dossier.id}, _ctx(org))
    assert refus["ok"] is False and refus["code"] == "groupe"  # le dossier d'une autre organisation n'existe pas ici


async def test_groupes_lister_et_groupe_lire_rendent_le_groupe_et_les_defauts_de_passation(org, db_session, async_session):
    principal, specialises = await _groupe(org)
    seul = await _agent(db_session, org, "Agent seul")
    await _oublier(async_session)
    liste = await registre.executer("groupes_lister", {}, _ctx(org))
    assert liste["ok"] and liste["groupes"] == [
        {"principal": {"id": principal, "nom": "Standard"}, "specialises": [{"id": specialises[0], "nom": "Devis"}, {"id": specialises[1], "nom": "Urgence"}]}
    ]
    lu = await registre.executer("groupe_lire", {"workflow_id": principal}, _ctx(org))
    assert lu["ok"] and lu["groupe"]["principal"]["id"] == principal
    assert [s["id"] for s in lu["groupe"]["specialises"]] == specialises and all(s["cerveau_propre"] is False for s in lu["groupe"]["specialises"])
    # Les défauts d'un groupe, tels que le moteur les lit.
    assert lu["passations"]["plafond_passations"] == 6 and lu["passations"]["passation_sans_resume_jusqua"] == 40
    assert lu["passations"]["prechauffage_agents"] is True and lu["passations"]["un_seul_renvoi_par_appel"] is True
    # Lu par un spécialisé : le même groupe.
    par_specialise = await registre.executer("groupe_lire", {"workflow_id": specialises[0]}, _ctx(org))
    assert par_specialise["groupe"]["principal"]["id"] == principal
    # Un agent seul n'est dans aucun groupe.
    alone = await registre.executer("groupe_lire", {"workflow_id": seul.id}, _ctx(org))
    assert alone["ok"] and alone["groupe"] is None


async def test_groupe_regler_ecrit_dans_le_brouillon_du_principal_sans_effacer_le_reste_et_recopie(org, db_session, async_session):
    principal, specialises = await _groupe(org)
    # Un réglage voisin déjà posé : il ne doit pas être effacé par la mise à jour d'une autre clé du même objet.
    await registre.executer("groupe_regler", {"workflow_id": principal, "attente": {"duree_min_s": 2.5, "phrase_pont": "Un instant"}}, _ctx(org))
    r = await registre.executer(
        "groupe_regler",
        {
            "workflow_id": principal,
            "plafond_passations": 3,
            "passation_sans_resume_jusqua": 10,
            "prechauffage_agents": False,
            "un_seul_renvoi_par_appel": False,
            "phrase_mise_en_relation": "Je vous mets en relation.",
            "attente": {"delai_phrase_pont_s": 4},
        },
        _ctx(org),
    )
    assert r["ok"], r
    await _oublier(async_session)
    reglages = await _reglages(db_session, org, principal)
    assert reglages["passations_max_par_appel"] == 3 and reglages["passation_sans_resume_jusqua"] == 10
    assert reglages["prechauffage_agents"] is False and reglages["un_seul_renvoi_par_appel"] is False
    assert reglages["transfert_humain"]["phrase_mise_en_relation"] == "Je vous mets en relation."
    assert reglages["attente"] == {"duree_min_s": 2.5, "phrase_pont": "Un instant", "delai_phrase_pont_s": 4.0}
    # Les spécialisés reçoivent la recopie des clés communes du groupe.
    for s in specialises:
        propre = await _reglages(db_session, org, s)
        assert propre["passations_max_par_appel"] == 3 and propre["prechauffage_agents"] is False
    # Ce que le moteur lira : la valeur réglée, plus le défaut.
    lu = await registre.executer("groupe_lire", {"workflow_id": principal}, _ctx(org))
    assert lu["passations"]["plafond_passations"] == 3 and lu["passations"]["phrase_mise_en_relation"] == "Je vous mets en relation."


async def test_groupe_regler_le_cerveau_propre_d_un_specialise_puis_son_rattachement(org, db_session, async_session):
    principal, specialises = await _groupe(org, specialises=("Devis",))
    await _oublier(async_session)
    propre = await registre.executer("groupe_regler", {"workflow_id": principal, "specialise_id": specialises[0], "cerveau_propre": True}, _ctx(org))
    assert propre["ok"], propre
    await _oublier(async_session)
    assert (await _reglages(db_session, org, specialises[0]))[CLE_CERVEAU_PROPRE] is True
    lu = await registre.executer("groupe_lire", {"workflow_id": principal}, _ctx(org))
    assert lu["groupe"]["specialises"][0]["cerveau_propre"] is True
    rattache = await registre.executer("groupe_regler", {"workflow_id": principal, "specialise_id": specialises[0], "cerveau_propre": False}, _ctx(org))
    assert rattache["ok"], rattache
    await _oublier(async_session)
    assert (await _reglages(db_session, org, specialises[0])).get(CLE_CERVEAU_PROPRE) is not True


async def test_groupe_regler_refuse_sans_rien_ecrire(org, autre_org, db_session, async_session):
    principal, specialises = await _groupe(org, specialises=("Devis",))
    seul = await _agent(db_session, org, "Seul")
    autre_principal, autres = await _groupe(autre_org, nom="Autre groupe", specialises=("Etranger",))
    await _oublier(async_session)
    avant = await _reglages(db_session, org, principal)

    async def refuse(args, attendu_code=None):
        r = await registre.executer("groupe_regler", args, _ctx(org))
        assert r["ok"] is False, (args, r)
        if attendu_code:
            assert r.get("code") == attendu_code, (args, r)
        return r

    await refuse({"workflow_id": seul.id, "plafond_passations": 3}, "pas_un_principal")  # un agent seul n'est pas un principal
    await refuse({"workflow_id": specialises[0], "plafond_passations": 3}, "pas_un_principal")  # un spécialisé non plus
    await refuse({"workflow_id": principal, "specialise_id": autres[0], "cerveau_propre": True})  # le spécialisé d'une autre organisation
    await refuse({"workflow_id": principal, "specialise_id": seul.id, "cerveau_propre": True}, "pas_un_specialise")  # un agent hors groupe
    await refuse({"workflow_id": principal, "plafond_passations": 9999})  # hors bornes
    await refuse({"workflow_id": principal, "plafond_passations": -1})
    await refuse({"workflow_id": principal})  # aucun réglage
    await refuse({"workflow_id": principal, "specialise_id": specialises[0]})  # specialise_id sans cerveau_propre
    await refuse({"workflow_id": principal, "attente": {"duree_min_s": 999}})
    await refuse({"workflow_id": autre_principal, "plafond_passations": 3}, "introuvable")  # le principal d'une autre organisation
    await _oublier(async_session)
    assert await _reglages(db_session, org, principal) == avant
    assert (await _reglages(db_session, autre_org, autres[0])).get("passations_max_par_appel") == 6  # le groupe de l'autre n'a pas bougé


async def test_chaque_action_est_cloisonnee_par_organisation(org, autre_org, db_session, async_session):
    principal, _ = await _groupe(org)
    await _groupe(autre_org, nom="Groupe de l'autre", specialises=())
    await _oublier(async_session)
    for nom, args in (
        ("groupe_lire", {"workflow_id": principal}),
        ("groupe_specialise_creer", {"workflow_id": principal, "nom": "Intrus"}),
        ("groupe_regler", {"workflow_id": principal, "plafond_passations": 1}),
        ("groupe_completer", {"workflow_id": principal}),
    ):
        r = await registre.executer(nom, args, _ctx(autre_org))
        assert r["ok"] is False and r.get("code") == "introuvable", (nom, r)
    liste = await registre.executer("groupes_lister", {}, _ctx(autre_org))
    assert [g["principal"]["nom"] for g in liste["groupes"]] == ["Groupe de l'autre"]


async def test_groupe_completer_pose_les_fins_et_laisse_les_prompts_a_rediger(org, db_session, async_session):
    principal, specialises = await _groupe(org, specialises=("Devis",))
    await _oublier(async_session)
    r = await registre.executer("groupe_completer", {"workflow_id": principal}, _ctx(org))
    assert r["ok"], r
    assert set(r["ajouts"]) <= {str(principal), str(specialises[0])}
    # La même fonction que la route : rejouée, elle n'ajoute plus rien (idempotente).
    encore = await registre.executer("groupe_completer", {"workflow_id": principal}, _ctx(org))
    assert encore["ok"] and all(not ajouts for ajouts in encore["ajouts"].values())


async def test_publier_un_groupe_et_archiver_sont_des_gestes_qui_demandent_une_carte_en_mode_demander(org):
    """N1 : ``groupe_publier`` (publication) et ``agent_archiver`` (irréversible) existent ; en « Demander », rien n'est fait sans clic."""
    principal, _ = await _groupe(org, specialises=())
    demander = Contexte(user=org.utilisateur, workflow_id=principal, conversation={"mode": "demander"}, permissions=frozenset(PERMISSIONS))
    for nom, famille in (("groupe_publier", "publication"), ("agent_archiver", "irreversible")):
        r = await registre.executer(nom, {"workflow_id": principal}, demander)
        assert r["ok"] is False and r["code"] == "autorisation_requise" and registre.REGISTRE[nom].famille == famille, nom
    for ancien in ("publier_groupe", "groupe_retirer", "groupe_archiver", "publier"):
        assert ancien not in registre.REGISTRE


async def test_regler_un_groupe_existant_exige_la_sauvegarde_quand_l_option_est_allumee(org, monkeypatch):
    principal, _ = await _groupe(org, specialises=())

    async def allumee(_contexte):
        return True

    from api.services.builder import sauvegarde

    monkeypatch.setattr(sauvegarde, "_allumee", allumee)
    r = await registre.executer("groupe_regler", {"workflow_id": principal, "plafond_passations": 2}, _ctx(org))
    assert r["ok"] is False and r.get("code") == "sauvegarde_requise"
    # Créer un groupe, lui, n'a rien à sauvegarder.
    assert (await registre.executer("groupe_creer", {"nom": "Nouveau"}, _ctx(org)))["ok"] is True
