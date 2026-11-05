"""[.mark] builder partie 3, sous-lot 7 (SE-15 = E-2) : « Revenir avant » restaure TOUT, famille par famille.

Monde simulé (aucune base, aucun appel réel). Les objets de l'agent (base du client) sont une doublure.

| Test | La garantie |
|---|---|
| prendre | un instantané garde les cinq familles ; les champs « branche » et « outils épinglés » sont prévus et vides |
| famille par famille | restaurer UNE famille ne touche à aucune autre (schéma, phrases, réglages, vocabulaire, objets) |
| tout | sans choix, toutes les familles que la version a gardées reviennent |
| validation | une valeur qui ne passerait plus refuse AVANT toute écriture ; famille inconnue, absente ou vide refusée |
| défaire | une restauration range son propre instantané complet : la restaurer remet l'état d'avant |
| aperçu | famille par famille ce qui changerait, des noms et des comptes, jamais une valeur (ni une clé) |
| publication | chaque publication range l'état publié ; une panne d'instantané ne rate pas la publication |
| cloisonnement | l'instantané d'une organisation ne se lit ni ne se restaure depuis une autre |
| route | familles au corps, 422 pour un refus, 404 pour l'inconnu, l'action sensible est journalisée |
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import builder_c2 as route
from api.services.auth.depends import get_user_with_selected_organization
from api.services.builder import apercu, brouillon, instantane, revue, stock
from api.services.builder.constantes import cle_builder
from api.services.lexique.stockage import enregistrer_lexique, lire_lexique
from api.schemas.lexique_metier import LexiqueMetier, TermeLexique
from api.tests.mark.builder_commun import AGENT, ORG_CLIENT, graphe_depart, utilisateur
from api.tests.mark.test_builder_actions import MOTIF, regle

EQUIPE = utilisateur(1, ORG_CLIENT)
AUTRE = utilisateur(2, 8)
CLE_SECRETE = "sk-test-pas-une-vraie-cle"


def etat_1():
    return {
        "phrases_regles": [regle("Un instant, je regarde.")],
        "relecture_des_numeros": True,
        "stt": {"api_key": CLE_SECRETE, "provider": "x"},
    }


def etat_2():
    return {"phrases_regles": [regle("Autre phrase.")], "relecture_des_numeros": False}


def lexique(*termes):
    return LexiqueMetier(termes=[TermeLexique(terme=t) for t in termes])


OBJETS_1 = [{"nom": "horaires", "libelle": "Horaires", "forme": "valeur", "type": "texte", "valeur": "9 h à 18 h"}]
OBJETS_2 = [
    {"nom": "horaires", "libelle": "Horaires", "forme": "valeur", "type": "texte", "valeur": "10 h à 12 h"},
    {"nom": "zone", "libelle": "Zone", "forme": "valeur", "type": "texte", "valeur": "Oise"},
]


class FauxObjets:
    """La base du client : des objets par nom. Écrire un nom existant le réécrit ; rien n'est jamais supprimé."""

    def __init__(self, objets):
        self.objets = {o["nom"]: dict(o) for o in objets}
        self.ecritures: list[str] = []

    async def lister(self, contexte):
        from api.schemas.objets_agent import ObjetAgent, ObjetsAgent

        return ObjetsAgent(objets=[ObjetAgent.model_validate({**o, "id": i + 1}) for i, o in enumerate(self.objets.values())])

    async def ecrire(self, contexte, objets):
        for o in objets:
            self.ecritures.append(o.nom)
            self.objets[o.nom] = o.model_dump(mode="json", include=set(OBJETS_1[0]))
        return [{"ok": True, "nom": o.nom} for o in objets]


@pytest.fixture
async def banc(monde, monkeypatch):
    """Un agent, un brouillon d'état 1, un vocabulaire et des objets d'état 1."""
    monde.brouillons[AGENT] = SimpleNamespace(workflow_json=graphe_depart(), version_number=2, status="draft", workflow_configurations=etat_1())
    await enregistrer_lexique(ORG_CLIENT, lexique("chaudière", "entretien"))
    faux = FauxObjets(OBJETS_1)
    from api.services.builder.actions import objets

    monkeypatch.setattr(objets, "lister_les_objets", faux.lister)
    monkeypatch.setattr(objets, "ecrire_des_objets", faux.ecrire)
    monkeypatch.setattr(revue, "db_client", monde)
    return SimpleNamespace(db=monde, objets=faux, workflow=monde.workflows[AGENT])


async def passer_a_l_etat_2(banc):
    """Tout a changé depuis l'instantané : graphe, phrases, réglages, vocabulaire, objets."""
    graphe = graphe_depart()
    graphe["nodes"][0]["data"]["prompt"] = "un autre prompt"
    banc.db.brouillons[AGENT] = SimpleNamespace(workflow_json=graphe, version_number=3, status="draft", workflow_configurations=etat_2())
    await enregistrer_lexique(ORG_CLIENT, lexique("devis"))
    banc.objets.objets = {o["nom"]: dict(o) for o in OBJETS_2}
    banc.objets.ecritures.clear()


async def instantane_de_l_etat_1(banc) -> int:
    complement = await instantane.capturer(ORG_CLIENT, banc.workflow, user=EQUIPE)
    return await revue._ranger(  # noqa: SLF001
        ORG_CLIENT, AGENT, cause="acceptation", avant=graphe_depart(), apres=graphe_depart(), version_avant=2, version_apres=2, fil_id=None, operations=[], complement=complement
    )


async def etat_courant(banc):
    graphe, _ = await brouillon.source_courante(banc.workflow)
    configs = await brouillon.configurations_courantes(banc.workflow)
    return {
        "prompt": graphe["nodes"][0]["data"]["prompt"],
        "phrases": configs.get("phrases_regles"),
        "relecture": configs.get("relecture_des_numeros"),
        "stt": configs.get("stt"),
        "termes": sorted(t.terme for t in (await lire_lexique(ORG_CLIENT)).termes),
        "objets": {n: o["valeur"] for n, o in banc.objets.objets.items()},
    }


ETAT_1 = {"prompt": "p1", "phrases": [regle("Un instant, je regarde.")], "relecture": True, "stt": {"api_key": CLE_SECRETE, "provider": "x"}, "termes": ["chaudière", "entretien"], "objets": {"horaires": "9 h à 18 h"}}
ETAT_2 = {"prompt": "un autre prompt", "phrases": [regle("Autre phrase.")], "relecture": False, "stt": None, "termes": ["devis"], "objets": {"horaires": "10 h à 12 h", "zone": "Oise"}}


# --- prendre -----------------------------------------------------------------------------------------------------------------


async def test_un_instantane_garde_les_cinq_familles_et_prevoit_la_branche_et_les_outils_epingles(banc):
    complement = await instantane.capturer(ORG_CLIENT, banc.workflow, user=EQUIPE)
    assert complement["familles"] == ["phrases", "vocabulaire", "objets", "reglages"]
    assert complement["phrases"][0]["motif"] == MOTIF and complement["reglages"]["relecture_des_numeros"] is True
    assert "phrases_regles" not in complement["reglages"]  # une clé, une famille
    assert [t["terme"] for t in complement["vocabulaire"]["termes"]] == ["chaudière", "entretien"]
    assert [o["nom"] for o in complement["objets"]] == ["horaires"]
    # Prévus pour la suite (audit 12 § 2, décision 21) : rien de construit ici.
    assert complement["branche"] is None and complement["outils_epingles"] is None
    numero = await instantane_de_l_etat_1(banc)
    (ligne,) = [v for v in await revue.instantanes(ORG_CLIENT, AGENT) if v["numero"] == numero]
    assert ligne["familles"] == ["schema", "phrases", "vocabulaire", "objets", "reglages"] and "complement" not in ligne


async def test_sans_personne_pour_les_lire_les_objets_ne_sont_pas_gardes_et_le_dit(banc):
    complement = await instantane.capturer(ORG_CLIENT, banc.workflow)
    assert complement["objets"] is None and "objets" not in complement["familles"]


async def test_une_acceptation_et_une_sauvegarde_rangent_le_complement(banc):
    from api.services.builder import sauvegarde
    from api.services.builder.actions.registre import Contexte

    pris = await sauvegarde.prendre(Contexte(user=EQUIPE, workflow_id=AGENT, conversation={}), banc.workflow)
    (ligne,) = await revue.instantanes(ORG_CLIENT, AGENT, complets=True)
    assert ligne["numero"] == pris["instantane"] and ligne["complement"]["reglages"]["relecture_des_numeros"] is True
    assert ligne["familles"] == ["schema", "phrases", "vocabulaire", "objets", "reglages"]


# --- famille par famille ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "famille, revenu",
    [
        ("schema", {"prompt": "p1"}),
        ("phrases", {"phrases": ETAT_1["phrases"]}),
        ("reglages", {"relecture": True, "stt": ETAT_1["stt"]}),
        ("vocabulaire", {"termes": ["chaudière", "entretien"]}),
        ("objets", {"objets": {"horaires": "9 h à 18 h", "zone": "Oise"}}),  # la zone ajoutée depuis n'est JAMAIS supprimée
    ],
)
async def test_restaurer_une_famille_ne_touche_a_aucune_autre(banc, famille, revenu):
    numero = await instantane_de_l_etat_1(banc)
    await passer_a_l_etat_2(banc)
    rendu = await revue.restaurer(ORG_CLIENT, banc.workflow, numero, familles=[famille], user=EQUIPE)
    assert rendu["familles"] == [famille]
    attendu = {**ETAT_2, **revenu}
    assert await etat_courant(banc) == attendu


async def test_sans_choix_toutes_les_familles_gardees_reviennent_et_le_brouillon_n_est_jamais_une_publication(banc):
    numero = await instantane_de_l_etat_1(banc)
    await passer_a_l_etat_2(banc)
    rendu = await revue.restaurer(ORG_CLIENT, banc.workflow, numero, user=EQUIPE)
    assert rendu["familles"] == ["schema", "phrases", "vocabulaire", "objets", "reglages"]
    assert rendu["objets"] == {"restaures": 1, "refuses": []} and rendu["vocabulaire"] == {"restaure": True}
    assert (await etat_courant(banc)) == {**ETAT_1, "objets": {"horaires": "9 h à 18 h", "zone": "Oise"}}
    assert banc.db.brouillons[AGENT].status == "draft" and banc.workflow.released_definition.version_number == 1


async def test_un_ancien_instantane_sans_complement_ne_restaure_que_le_graphe(banc):
    numero = await revue._ranger(  # noqa: SLF001
        ORG_CLIENT, AGENT, cause="acceptation", avant=graphe_depart(), apres=graphe_depart(), version_avant=2, version_apres=2, fil_id=None, operations=[]
    )
    await passer_a_l_etat_2(banc)
    rendu = await revue.restaurer(ORG_CLIENT, banc.workflow, numero, user=EQUIPE)
    assert rendu["familles"] == ["schema"]
    assert await etat_courant(banc) == {**ETAT_2, "prompt": "p1"}


# --- valider avant d'écrire --------------------------------------------------------------------------------------------------


async def test_une_valeur_qui_ne_passerait_plus_refuse_avant_toute_ecriture(banc):
    numero = await instantane_de_l_etat_1(banc)
    await passer_a_l_etat_2(banc)
    ligne = await stock.lire(ORG_CLIENT, cle_builder(AGENT, f"instantanes:{numero:06d}"))
    ligne["complement"]["reglages"]["relecture_des_numeros"] = "ni vrai ni faux"  # ce que les validateurs d'aujourd'hui refusent
    await stock.ecrire(ORG_CLIENT, cle_builder(AGENT, f"instantanes:{numero:06d}"), ligne)
    avant = await etat_courant(banc)
    with pytest.raises(revue.ErreurRevue, match="no longer pass"):
        await revue.restaurer(ORG_CLIENT, banc.workflow, numero, familles=["schema", "reglages", "vocabulaire", "objets"], user=EQUIPE)
    assert await etat_courant(banc) == avant and banc.objets.ecritures == []  # RIEN n'a été écrit, pas même le graphe
    assert len(await revue.instantanes(ORG_CLIENT, AGENT)) == 1  # ni l'instantané de la restauration


async def test_famille_inconnue_absente_ou_vide_est_refusee_sans_rien_ecrire(banc):
    numero = await instantane_de_l_etat_1(banc)
    sans_objets = await revue._ranger(  # noqa: SLF001
        ORG_CLIENT, AGENT, cause="x", avant=graphe_depart(), apres=graphe_depart(), version_avant=2, version_apres=2, fil_id=None, operations=[],
        complement={**await instantane.capturer(ORG_CLIENT, banc.workflow), "objets": None},
    )
    await passer_a_l_etat_2(banc)
    avant = await etat_courant(banc)
    for erreur, appel in (
        ("Unknown family", dict(numero=numero, familles=["couleurs"])),
        ("did not keep", dict(numero=sans_objets, familles=["objets"])),
        ("at least one", dict(numero=numero, familles=[])),
    ):
        with pytest.raises(revue.ErreurRevue, match=erreur):
            await revue.restaurer(ORG_CLIENT, banc.workflow, appel.pop("numero"), user=EQUIPE, **appel)
    assert await etat_courant(banc) == avant


async def test_un_objet_refuse_par_la_base_du_client_est_dit_sans_defaire_le_reste(banc, monkeypatch):
    from api.services.builder.actions import objets

    async def refuse(contexte, liste):
        return [{"ok": False, "nom": liste[0].nom, "erreur": "name reserved"}]

    monkeypatch.setattr(objets, "ecrire_des_objets", refuse)
    numero = await instantane_de_l_etat_1(banc)
    await passer_a_l_etat_2(banc)
    rendu = await revue.restaurer(ORG_CLIENT, banc.workflow, numero, familles=["objets", "phrases"], user=EQUIPE)
    assert rendu["objets"] == {"restaures": 0, "refuses": [{"nom": "horaires", "erreur": "name reserved"}]}
    assert (await etat_courant(banc))["phrases"] == ETAT_1["phrases"]


# --- défaire ----------------------------------------------------------------------------------------------------------------


async def test_une_restauration_se_defait_toutes_familles_comprises(banc):
    numero = await instantane_de_l_etat_1(banc)
    await passer_a_l_etat_2(banc)
    rendu = await revue.restaurer(ORG_CLIENT, banc.workflow, numero, familles=["schema", "phrases", "reglages", "vocabulaire"], user=EQUIPE)
    assert (await etat_courant(banc))["termes"] == ["chaudière", "entretien"]
    versions = await revue.instantanes(ORG_CLIENT, AGENT)
    assert versions[0]["cause"] == f"restauration de {numero}" and versions[0]["numero"] == rendu["instantane"]
    await revue.restaurer(ORG_CLIENT, banc.workflow, rendu["instantane"], familles=["schema", "phrases", "reglages", "vocabulaire"], user=EQUIPE)
    assert await etat_courant(banc) == ETAT_2


# --- aperçu -----------------------------------------------------------------------------------------------------------------


async def test_l_apercu_dit_famille_par_famille_ce_qui_changerait_sans_jamais_une_valeur(banc):
    numero = await instantane_de_l_etat_1(banc)
    await passer_a_l_etat_2(banc)
    vue = await apercu.apercu_de_la_restauration(ORG_CLIENT, banc.workflow, numero, user=EQUIPE)
    familles = {f["famille"]: f for f in vue["familles"]}
    assert [f["famille"] for f in vue["familles"]] == list(instantane.FAMILLES) and all(f["disponible"] for f in vue["familles"])
    assert familles["reglages"]["change"] is True and familles["reglages"]["details"] == ["relecture_des_numeros", "stt"]
    assert familles["vocabulaire"]["partagee"] is True and familles["objets"]["partagee"] is True and familles["schema"]["partagee"] is False
    assert familles["objets"]["details"] == ["horaires"] and familles["objets"]["ajoutes_depuis"] == ["zone"]
    assert familles["phrases"]["change"] is True
    brut = json.dumps(vue)
    assert CLE_SECRETE not in brut and "9 h à 18 h" not in brut and "Autre phrase" not in brut  # des noms et des comptes, jamais une valeur
    assert vue["total_perdu"] == 1  # le graphe, comme avant


async def test_l_apercu_d_une_famille_sans_changement_ne_dit_rien_a_restaurer(banc):
    numero = await instantane_de_l_etat_1(banc)
    vue = await apercu.apercu_de_la_restauration(ORG_CLIENT, banc.workflow, numero, user=EQUIPE)
    assert all(f["change"] is False for f in vue["familles"] if f["famille"] != "schema")


# --- à chaque publication ---------------------------------------------------------------------------------------------------


async def test_chaque_publication_range_l_etat_publie_et_une_panne_ne_la_rate_pas(banc, monkeypatch):
    publiee = SimpleNamespace(workflow_json=graphe_depart(), workflow_configurations=etat_1(), version_number=7)
    numero = await revue.apres_une_publication(ORG_CLIENT, banc.workflow, publiee, EQUIPE)
    (ligne,) = await revue.instantanes(ORG_CLIENT, AGENT, complets=True)
    assert ligne["numero"] == numero and ligne["cause"] == "publication" and ligne["version_apres"] == 7
    assert ligne["complement"]["reglages"]["relecture_des_numeros"] is True and "objets" in ligne["familles"]
    await passer_a_l_etat_2(banc)
    await revue.restaurer(ORG_CLIENT, banc.workflow, numero, user=EQUIPE)
    assert (await etat_courant(banc))["phrases"] == ETAT_1["phrases"]  # on revient à la version publiée
    monkeypatch.setattr(instantane, "capturer", AsyncMock(side_effect=RuntimeError("base indisponible")))
    assert await revue.apres_une_publication(ORG_CLIENT, banc.workflow, publiee, EQUIPE) is None  # ne lève jamais


def test_la_route_de_publication_prend_l_instantane():
    source = open(route.__file__.replace("builder_c2.py", "workflow.py"), encoding="utf8").read()
    assert "revue_du_builder.apres_une_publication" in source


# --- cloisonnement ----------------------------------------------------------------------------------------------------------


async def test_l_instantane_d_une_organisation_ne_se_lit_ni_ne_se_restaure_depuis_une_autre(banc):
    numero = await instantane_de_l_etat_1(banc)
    assert await revue.instantanes(8, AGENT) == []
    with pytest.raises(revue.ErreurRevue, match="Unknown version"):
        await revue.restaurer(8, banc.workflow, numero, user=AUTRE)
    with pytest.raises(revue.ErreurRevue, match="Unknown version"):
        await apercu.apercu_de_la_restauration(8, banc.workflow, numero)


# --- les routes -------------------------------------------------------------------------------------------------------------


def client_pour(user):
    app = FastAPI()
    app.include_router(route.router, prefix="/builder")
    app.dependency_overrides[get_user_with_selected_organization] = lambda: user
    return TestClient(app)


@pytest.fixture
def routes(banc, monkeypatch):
    monkeypatch.setattr(route, "db_client", banc.db)
    journal = AsyncMock()
    monkeypatch.setattr("api.services.equipe_mark.acces.journaliser", journal)
    return SimpleNamespace(journal=journal)


async def test_la_route_restaure_les_familles_choisies_et_journalise(banc, routes):
    numero = await instantane_de_l_etat_1(banc)
    await passer_a_l_etat_2(banc)
    c = client_pour(EQUIPE)
    liste = c.get(f"/builder/agents/{AGENT}/versions").json()
    assert liste[0]["familles"] == ["schema", "phrases", "vocabulaire", "objets", "reglages"]
    r = c.post(f"/builder/agents/{AGENT}/versions/{numero}/restaurer", json={"familles": ["phrases", "vocabulaire"]})
    assert r.status_code == 200 and r.json()["familles"] == ["phrases", "vocabulaire"]
    assert (await etat_courant(banc))["relecture"] is False and (await etat_courant(banc))["termes"] == ["chaudière", "entretien"]
    routes.journal.assert_awaited_once()
    assert routes.journal.await_args.args[1:3] == ("agents.revenir_avant", ORG_CLIENT)
    assert routes.journal.await_args.args[3]["familles"] == ["phrases", "vocabulaire"]


async def test_la_route_sans_corps_restaure_tout_et_dit_pourquoi_elle_refuse(banc, routes):
    numero = await instantane_de_l_etat_1(banc)
    c = client_pour(EQUIPE)
    assert c.post(f"/builder/agents/{AGENT}/versions/{numero}/restaurer").json()["familles"][0] == "schema"
    assert c.post(f"/builder/agents/{AGENT}/versions/{numero}/restaurer", json={"familles": ["couleurs"]}).status_code == 422
    assert c.post(f"/builder/agents/{AGENT}/versions/999/restaurer").status_code == 404
    assert client_pour(AUTRE).post(f"/builder/agents/{AGENT}/versions/{numero}/restaurer").status_code == 404
    assert client_pour(AUTRE).get(f"/builder/agents/{AGENT}/versions").status_code == 404


async def test_l_instantane_d_une_publication_ne_rend_pas_l_agent_suivi_par_le_builder(banc):
    """Publier ne doit pas, à lui seul, imposer à un agent les gardes d'un agent que le builder suit (contrôle du prompt bloquant)."""
    from api.services.builder.tests_agent import publication

    assert await publication.agent_suivi(ORG_CLIENT, AGENT) is False
    publiee = SimpleNamespace(workflow_json=graphe_depart(), workflow_configurations=etat_1(), version_number=7)
    assert await revue.apres_une_publication(ORG_CLIENT, banc.workflow, publiee, EQUIPE) is not None
    assert await publication.agent_suivi(ORG_CLIENT, AGENT) is False
    # Un instantané du builder (acceptation, sauvegarde), lui, est bien la trace d'un agent suivi.
    await instantane_de_l_etat_1(banc)
    assert await publication.agent_suivi(ORG_CLIENT, AGENT) is True
