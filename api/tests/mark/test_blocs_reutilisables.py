"""[.mark] Builder partie 3, lot 22 (§ 3 bis du plan) : les blocs réutilisables de la bibliothèque.

| Test | Ce qu'il prouve (critère du § 3 bis) |
|---|---|
| familles | seules les familles qui écrivent des prompts proposent des blocs |
| suivre ou rester | ``{{bloc:x}}`` suit la dernière RECETTE ; ``{{bloc:x@v2}}`` reste sur la v2 ; une nouvelle Recette ne change pas un agent resté |
| un niveau | un bloc qui cite un bloc : l'étiquette intérieure disparaît à l'appel et la publication le signale |
| blocage | bloc supprimé, version rejetée, version épinglée disparue, aucune Recette à suivre : bloquant, avec la correction |
| conseil | un bloc resté sur sa version alors qu'une Recette plus récente existe : ligne conseillée « Blocs à jour », jamais bloquante |
| suivre / rester par prompt | la correction réécrit l'étiquette d'un prompt, pas des autres |
| cloisonnement | « Utilisé dans » ne lit que les agents de l'organisation de l'appelant (base réelle) |
| builder | ``bloc_poser`` écrit l'étiquette dans le brouillon ; ``bloc_retirer`` l'ôte ; un bloc hors catalogue est refusé, rien n'est écrit |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services.etiquettes_prompt import catalogue as cat
from api.services.etiquettes_prompt import corrections
from api.services.etiquettes_prompt import resolution as res
from api.services.etiquettes_prompt.table import FAMILLES_DE_BLOCS


def _bloc(slug="politesse", *versions, titre="Règles de politesse", famille="prompt-general") -> res.BlocLu:
    return res.BlocLu(slug, titre, famille, tuple(res.VersionDeBloc(n, s, t) for n, s, t in versions))


POLITESSE = _bloc("politesse", (1, "recette", "Vouvoie."), (2, "recette", "Vouvoie toujours."), (3, "candidat", "Tutoie."))


def _catalogue(*blocs: res.BlocLu) -> dict[str, cat.ObjetCitable]:
    return cat.construire(cat.Sources(blocs=list(blocs)))


def _graphe(prompt: str) -> dict:
    return {
        "nodes": [
            {"id": "1", "type": "startCall", "position": {"x": 0, "y": 0}, "data": {"name": "Accueil", "prompt": prompt}},
            {"id": "2", "type": "agentNode", "position": {"x": 0, "y": 1}, "data": {"name": "Tri", "prompt": "{{bloc:politesse}}"}},
            {"id": "3", "type": "endCall", "position": {"x": 0, "y": 2}, "data": {"name": "Fin", "prompt": "Fin."}},
        ],
        "edges": [
            {"id": "a", "source": "1", "target": "2", "data": {"label": "Suite", "condition": "suite"}},
            {"id": "b", "source": "2", "target": "3", "data": {"label": "Fini", "condition": "fini"}},
        ],
    }


# --- familles -------------------------------------------------------------------------------------------------------------


async def test_seules_les_familles_qui_ecrivent_des_prompts_proposent_des_blocs():
    from api.services.builder.bibliotheque.familles import FAMILLES

    assert set(FAMILLES_DE_BLOCS) <= set(FAMILLES)
    assert "scenarios-test" not in FAMILLES_DE_BLOCS and "modeles-outils" not in FAMILLES_DE_BLOCS
    lues: list[str] = []

    async def elements_de(famille):
        lues.append(famille)
        return []

    with patch("api.services.builder.bibliotheque.service.elements_de", elements_de):
        await cat.lire_les_blocs()
    assert lues == list(FAMILLES_DE_BLOCS)


# --- suivre ou rester ----------------------------------------------------------------------------------------------------


def test_suivre_prend_la_derniere_recette_et_rester_garde_sa_version():
    table = res.Table(blocs={"politesse": POLITESSE})
    assert res.rendre("{{bloc:politesse}}", table) == "Vouvoie toujours."  # v3 est Candidat : la dernière RECETTE est la v2
    assert res.rendre("{{bloc:politesse@v1}}", table) == "Vouvoie."


def test_une_nouvelle_recette_ne_change_pas_un_agent_reste_sur_sa_version():
    avant = res.Table(blocs={"politesse": POLITESSE})
    nouvelle = _bloc("politesse", (1, "recette", "Vouvoie."), (2, "recette", "Vouvoie toujours."), (3, "recette", "Tutoie."))
    apres = res.Table(blocs={"politesse": nouvelle})
    assert res.rendre("{{bloc:politesse@v2}}", avant) == res.rendre("{{bloc:politesse@v2}}", apres) == "Vouvoie toujours."
    assert res.rendre("{{bloc:politesse}}", apres) == "Tutoie."  # celui qui suit la reçoit


def test_un_bloc_qui_cite_un_bloc_est_refuse_au_dela_d_un_niveau():
    gabarit = _bloc("gabarit", (1, "recette", "Début {{bloc:politesse}} fin."), titre="Gabarit", famille="moules-etape")
    table = res.Table(blocs={"politesse": POLITESSE, "gabarit": gabarit})
    assert res.rendre("{{bloc:gabarit}}", table) == "Début  fin."
    problemes = cat.diagnostiquer(_graphe("{{bloc:gabarit}}"), None, _catalogue(POLITESSE, gabarit))
    assert [(p.cle, p.motif) for p in problemes] == [("bloc:gabarit", cat.BLOC_DANS_BLOC)]


# --- blocage et conseil ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt, motif, premiere_correction",
    [
        ("{{bloc:disparu}}", cat.INTROUVABLE, "retirer"),
        ("{{bloc:politesse@v9}}", cat.VERSION_DISPARUE, "passer_version"),
        ("{{bloc:rejete@v1}}", cat.BLOC_REJETE, "passer_version"),
        ("{{bloc:candidat}}", cat.SANS_RECETTE, "retirer"),
    ],
)
def test_un_bloc_casse_bloque_la_publication_avec_sa_correction(prompt, motif, premiere_correction):
    rejete = _bloc("rejete", (1, "rejete", "Non."), (2, "recette", "Oui."))
    candidat = _bloc("candidat", (1, "candidat", "Pas prouvé."))
    catalogue = _catalogue(POLITESSE, rejete, candidat)
    problemes = [p for p in cat.diagnostiquer(_graphe(prompt), None, catalogue) if p.noeud_id == "1"]
    assert [p.motif for p in problemes] == [motif] and problemes[0].bloquant
    correction = problemes[0].corrections[0]
    assert correction["type"] == premiere_correction
    graphe, _, n = corrections.appliquer(_graphe(prompt), {}, {**correction, "champ": problemes[0].champ})
    assert n == 1
    assert [p for p in cat.diagnostiquer(graphe, None, catalogue) if p.noeud_id == "1"] == []


def test_rester_sur_une_version_ancienne_est_un_conseil_jamais_un_blocage():
    problemes = [p for p in cat.diagnostiquer(_graphe("{{bloc:politesse@v1}}"), None, _catalogue(POLITESSE)) if p.noeud_id == "1"]
    assert [p.motif for p in problemes] == [cat.PLUS_RECENT] and not problemes[0].bloquant
    assert [c["type"] for c in problemes[0].corrections] == ["passer_version", "suivre", "retirer"]


async def test_la_ligne_blocs_a_jour_est_conseillee_et_ne_bloque_pas(banc):  # noqa: F811
    from api.services.builder.tests_agent import publication
    from api.services.publication import controles
    from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, sans_les_lignes_de_pret

    wf = banc.workflows[AGENT]
    brouillon = SimpleNamespace(
        workflow_json=_graphe("{{bloc:politesse@v1}}"), version_number=2, workflow_configurations=sans_les_lignes_de_pret({"moteur_sortie_d_impasse": False})
    )
    with patch.object(cat, "catalogue_de", AsyncMock(return_value=(_catalogue(POLITESSE), set()))):
        vue = await controles.evaluer(wf, brouillon, ORG_CLIENT)
        bloc = next(c for c in vue["controles"] if c["cle"] == "blocs_a_jour")
        assert (bloc["position"], bloc["statut"]) == ("previent", "alerte")
        ligne = next(l for l in vue["lignes"] if l["id"] == "blocs_a_jour")
        assert (ligne["niveau"], ligne["etat"]) == ("conseille", "a_faire")
        assert next(c for c in vue["controles"] if c["cle"] == "etiquettes")["statut"] == "ok"
        assert await publication.verifier_avant_publication(wf, brouillon, ORG_CLIENT) is None


from api.tests.mark.test_builder_tests_agent import banc  # noqa: E402,F401


# --- suivre / rester par prompt -------------------------------------------------------------------------------------------


def test_le_choix_suivre_ou_rester_reecrit_un_seul_prompt():
    graphe = _graphe("{{bloc:politesse}}")
    reste, _, n = corrections.appliquer(graphe, {}, {"type": "passer_version", "cle": "bloc:politesse", "champ": "nodes[1].prompt", "version": 1})
    assert n == 1
    assert reste["nodes"][0]["data"]["prompt"] == "{{bloc:politesse@v1}}"
    assert reste["nodes"][1]["data"]["prompt"] == "{{bloc:politesse}}"  # l'autre étape n'a pas bougé
    suit, _, _ = corrections.appliquer(reste, {}, {"type": "suivre", "cle": "bloc:politesse@v1", "champ": "nodes[1].prompt"})
    assert suit["nodes"][0]["data"]["prompt"] == "{{bloc:politesse}}"
    citations = corrections.citations_dans("bloc:politesse", [(7, "Agent", reste, None)])
    assert [(c["noeud_id"], c["version"]) for c in citations] == [("1", 1), ("2", None)]


# --- base réelle : cloisonnement et builder ---------------------------------------------------------------------------------

from api.tests.mark.test_apres_appel import _organisation, base_v4, smtp  # noqa: E402,F401  (fixtures)
from api.tests.mark.test_sous_dossiers_et_groupe import autre_org, org  # noqa: E402,F401


async def _agent(db, o, prompt: str, nom="Agent"):
    return await db.create_workflow(name=nom, workflow_definition=_graphe(prompt), user_id=o.utilisateur.id, organization_id=o.organisation.id)


async def test_utilise_dans_ne_lit_que_les_agents_de_l_organisation(org, autre_org, db_session):  # noqa: F811
    a = await _agent(db_session, org, "{{bloc:politesse@v1}}", nom="Chez nous")
    await _agent(db_session, autre_org, "{{bloc:politesse}}", nom="Chez eux")
    trouves = await corrections.utilise_dans(org.organisation.id, "bloc:politesse")
    assert {c["agent"] for c in trouves} == {"Chez nous"} and {c["agent_id"] for c in trouves} == {a.id}


async def test_le_builder_pose_et_retire_un_bloc_dans_le_brouillon(org, db_session):  # noqa: F811
    from api.services.builder import actions  # noqa: F401 -- remplit le registre
    from api.services.builder.actions.registre import Contexte, executer

    agent = await _agent(db_session, org, "Bonjour.")
    user = SimpleNamespace(id=org.utilisateur.id, selected_organization_id=org.organisation.id)
    ctx = Contexte(user=user, workflow_id=agent.id)
    with patch.object(cat, "catalogue_de", AsyncMock(return_value=(_catalogue(POLITESSE), set()))):
        pose = await executer("bloc_poser", {"noeud_id": "1", "bloc": "politesse", "version": 2}, ctx)
        assert pose["ok"] is True, pose
        brouillon = await db_session.get_draft_version(agent.id)
        assert brouillon.workflow_json["nodes"][0]["data"]["prompt"] == "Bonjour.\n\n{{bloc:politesse@v2}}"
        refus = await executer("bloc_poser", {"noeud_id": "1", "bloc": "invente"}, ctx)
        assert refus["ok"] is False and refus["code"] == "etiquette_hors_catalogue"
        retire = await executer("bloc_retirer", {"bloc": "politesse", "noeud_id": "1"}, ctx)
        assert retire["ok"] is True, retire
    brouillon = await db_session.get_draft_version(agent.id)
    assert "{{" not in brouillon.workflow_json["nodes"][0]["data"]["prompt"]
    assert brouillon.workflow_json["nodes"][1]["data"]["prompt"] == "{{bloc:politesse}}"  # l'autre étape garde le sien
