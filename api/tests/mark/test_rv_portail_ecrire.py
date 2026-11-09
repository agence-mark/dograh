"""[.mark] Partie 3, revue RV (point 3, tranché par Pierre le 05/11) : une permission de clé propre au portail.

``agents.modifier`` sort de la liste fermée des clés ; ``portail.ecrire`` n'ouvre que les écritures du contrat du portail.

| Test | Ce qu'il prouve |
|---|---|
| liste | ``portail.ecrire`` est dans la liste fermée des clés, ``agents.modifier`` n'y est plus |
| clé refusée | une clé ne touche plus les outils, les agents, les branches, le journal, le miroir, l'import et l'export en fichiers, le stockage, les connaissances hors portail |
| clé admise | une clé garde chaque route du contrat du portail (lectures comme écritures) |
| session | une session d'équipe garde exactement ses droits : ``agents.modifier`` passe, ``portail.ecrire`` seul passe aussi sur ces routes, rien ne passe sans l'une ou l'autre |
| cloisonnement | une clé reste enfermée dans son organisation, route du portail comprise |
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.services.equipe_mark.acces import appliquer_acces
from api.services.equipe_mark.permissions import PERMISSIONS, PERMISSIONS_DE_CLE
from api.tests.mark.equipe_commun import client_http, creer_compte, creer_organisation, sans_preparation_des_organisations  # noqa: F401
from api.tests.mark.test_contrat_portail_fork import ROUTES_DU_PORTAIL

P = "/api/v1"


async def _appliquer(methode: str, chemin: str, *, par_cle_api: bool, permissions: frozenset[str] = frozenset()):
    connexion = SimpleNamespace(headers={}, scope={"route": SimpleNamespace(path_format=chemin), "type": "http", "method": methode})
    utilisateur = SimpleNamespace(id=1, selected_organization_id=5)
    acces = None if par_cle_api else SimpleNamespace(permissions=permissions, labo_ouvert=True, tous_les_clients=True, organisations=frozenset({5}))
    with (
        patch("api.services.equipe_mark.espaces.rafraichir_labo", AsyncMock()),
        patch("api.services.equipe_mark.acces.acces_de", AsyncMock(return_value=acces)),
        patch("api.services.equipe_mark.acces.detacher_de_sa_session", lambda u: None),
        patch("api.services.equipe_mark.acces.journaliser", AsyncMock()),
    ):
        await appliquer_acces(connexion, utilisateur, par_cle_api=par_cle_api)


def test_la_permission_du_portail_est_dans_la_liste_des_cles_et_agents_modifier_n_y_est_plus():
    assert "portail.ecrire" in PERMISSIONS and "portail.ecrire" in PERMISSIONS_DE_CLE
    assert "agents.modifier" not in PERMISSIONS_DE_CLE
    # les autres permissions des clés ne bougent pas
    assert {"conversations.voir", "tests.automatiser", "connecteurs.autoriser", "base_client.connexion_portail", "contacts.traiter"} <= PERMISSIONS_DE_CLE


INTERDITES_A_UNE_CLE = [
    ("DELETE", f"{P}/tools/{{tool_uuid}}"),  # archiver un outil
    ("POST", f"{P}/tools/"),
    ("PUT", f"{P}/workflow/{{workflow_id}}"),  # écrire le brouillon d'un agent
    ("POST", f"{P}/workflow/create/definition"),
    ("POST", f"{P}/builder/branches/{{workflow_id}}"),  # une branche
    ("GET", f"{P}/builder/journal"),  # lire le journal
    ("POST", f"{P}/builder/journal/{{ligne}}/annuler"),
    ("POST", f"{P}/agent-fichiers/{{workflow_id}}/import"),
    ("GET", f"{P}/agent-fichiers/{{workflow_id}}/export"),
    ("POST", f"{P}/s3/presigned-upload-url"),
    ("POST", f"{P}/folder/"),
    ("PUT", f"{P}/organizations/modeles-de-reglages/x"),  # un outil de l'équipe, au Labo
]


@pytest.mark.parametrize("methode, chemin", INTERDITES_A_UNE_CLE, ids=[f"{m} {c.removeprefix(P)}" for m, c in INTERDITES_A_UNE_CLE])
async def test_une_cle_ne_touche_plus_ce_qui_n_est_pas_au_portail(methode, chemin):
    with pytest.raises(HTTPException) as erreur:
        await _appliquer(methode, chemin, par_cle_api=True)
    assert erreur.value.status_code == 403, (methode, chemin)


@pytest.mark.parametrize("methode, chemin", ROUTES_DU_PORTAIL, ids=[f"{m} {c.removeprefix(P)}" for m, c in ROUTES_DU_PORTAIL])
async def test_une_cle_garde_chaque_route_du_contrat_du_portail(methode, chemin):
    await _appliquer(methode, chemin, par_cle_api=True)


ECRITURES_DU_PORTAIL = [(m, c) for m, c in ROUTES_DU_PORTAIL if m != "GET" and "/organizations/relation" not in c]


@pytest.mark.parametrize("methode, chemin", ECRITURES_DU_PORTAIL, ids=[f"{m} {c.removeprefix(P)}" for m, c in ECRITURES_DU_PORTAIL])
async def test_une_session_d_equipe_garde_exactement_ses_droits_sur_les_routes_du_portail(methode, chemin):
    from api.services.equipe_mark import registre_routes

    decision = registre_routes.decision_de(methode, chemin.removeprefix(P))[0]
    avec = frozenset({decision.cle}) if isinstance(decision, registre_routes.Permission) else frozenset()
    await _appliquer(methode, chemin, par_cle_api=False, permissions=avec)  # aujourd'hui : la permission de la route, rien de plus
    if isinstance(decision, registre_routes.Permission) and decision.pour_cle:
        await _appliquer(methode, chemin, par_cle_api=False, permissions=frozenset({decision.pour_cle}))  # la nouvelle permission suffit aussi
        with pytest.raises(HTTPException) as erreur:
            await _appliquer(methode, chemin, par_cle_api=False, permissions=frozenset({"conversations.voir"}))
        assert erreur.value.status_code == 403


async def test_une_session_garde_l_outil_et_l_agent_comme_avant():
    for methode, chemin in [("DELETE", f"{P}/tools/{{tool_uuid}}"), ("PUT", f"{P}/workflow/{{workflow_id}}")]:
        await _appliquer(methode, chemin, par_cle_api=False, permissions=frozenset({"agents.modifier"}))
        with pytest.raises(HTTPException):
            await _appliquer(methode, chemin, par_cle_api=False, permissions=frozenset({"portail.ecrire"}))  # elle n'ouvre QUE le portail


async def test_la_cle_du_client_ecrit_au_portail_pas_dans_les_outils_et_reste_dans_son_organisation(db_session):
    a = await creer_organisation(db_session, "rv3-a")
    b = await creer_organisation(db_session, "rv3-b")
    admin, _ = await creer_compte(db_session, "rv3-admin@example.com", role="Administrateur", organisations=[a, b])
    _, cle_a = await db_session.create_api_key(a, "portail A", admin.id)
    entetes = {"X-API-Key": cle_a}
    async with client_http() as c:
        lexique = await c.put(f"{P}/organizations/lexique", headers=entetes, json={})
        outil = await c.post(f"{P}/tools/", headers=entetes, json={})
        archive = await c.delete(f"{P}/tools/00000000-0000-0000-0000-000000000000", headers=entetes)
        autre = await c.put(f"{P}/organizations/lexique", headers={**entetes, "X-Mark-Organisation": str(b)}, json={})
    assert lexique.status_code != 403, lexique.text  # la route du portail est ouverte à la clé (la validation du corps répond ensuite)
    assert outil.status_code == 403 and archive.status_code == 403
    assert autre.status_code == 403 and "own organization" in autre.json()["detail"]


# --- RV2 (I-1) : la clé du portail n'ouvre que les écritures du contrat, rien d'autre sous /organizations ---------------------------

FERMEES_A_UNE_CLE_SOUS_ORGANIZATIONS = [
    ("PUT", f"{P}/organizations/preferences"),
    ("POST", f"{P}/organizations/call-events/test"),
    ("PUT", f"{P}/organizations/apres-appel"),
    ("PUT", f"{P}/organizations/apres-appel/installation"),
    ("POST", f"{P}/organizations/apres-appel/essai-mail"),
    ("PUT", f"{P}/organizations/apres-appel/nuit"),
    ("PUT", f"{P}/organizations/apres-appel/recapitulatif"),
    ("PUT", f"{P}/organizations/verification-appelant"),
    ("POST", f"{P}/organizations/sites"),
    ("POST", f"{P}/organizations/sites/{{site_id}}/regenerer-cle"),
    ("PUT", f"{P}/organizations/sites/{{site_id}}/canal"),
    ("PUT", f"{P}/organizations/sites/{{site_id}}/affichage"),
    ("POST", f"{P}/organizations/sites/lire-site"),
    ("POST", f"{P}/organizations/etablissements"),
    ("POST", f"{P}/organizations/etablissements/{{identifiant}}/copier"),
    ("POST", f"{P}/organizations/etablissements/{{identifiant}}/reprise"),
    ("POST", f"{P}/organizations/lexique/import"),
    ("PUT", f"{P}/organizations/annonce-ouverture"),
    ("PUT", f"{P}/organizations/phrases"),
    ("PUT", f"{P}/organizations/objets/{{objet_id}}"),
    ("PUT", f"{P}/organizations/planificateur"),
]


@pytest.mark.parametrize(
    "methode, chemin", FERMEES_A_UNE_CLE_SOUS_ORGANIZATIONS, ids=[f"{m} {c.removeprefix(P)}" for m, c in FERMEES_A_UNE_CLE_SOUS_ORGANIZATIONS]
)
async def test_une_cle_ne_touche_pas_les_ecritures_hors_contrat_sous_organizations(methode, chemin):
    from api.services.equipe_mark import registre_routes

    decision = registre_routes.decision_de(methode, chemin.removeprefix(P))[0]
    assert getattr(decision, "pour_cle", None) != "portail.ecrire", (methode, chemin)
    with pytest.raises(HTTPException) as erreur:
        await _appliquer(methode, chemin, par_cle_api=True)
    assert erreur.value.status_code == 403, (methode, chemin)
    # une session d'équipe garde son droit
    await _appliquer(methode, chemin, par_cle_api=False, permissions=frozenset({"agents.modifier"}))


def test_toute_route_qui_porte_portail_ecrire_est_dans_le_contrat_et_chaque_ecriture_du_contrat_y_est():
    from api.app import app
    from fastapi.routing import APIRoute

    from api.services.equipe_mark import registre_routes

    contrat = set(ROUTES_DU_PORTAIL)
    portent = set()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for methode in route.methods or []:
                trouvee = registre_routes.decision_de(methode, route.path.removeprefix(P))
                if trouvee and getattr(trouvee[0], "pour_cle", None) == "portail.ecrire":
                    portent.add((methode, route.path))
    assert not (portent - contrat), f"portail.ecrire posé hors contrat : {sorted(portent - contrat)}"

    import json

    from api.tests.mark.test_contrat_portail_fork import FICHIER

    figees = json.loads(FICHIER.read_text(encoding="utf-8"))
    attendues = {
        (cle.split(" ", 1)[0], cle.split(" ", 1)[1])
        for cle, forme in figees.items()
        if forme.get("permission_de_cle") == "portail.ecrire"
    }
    assert attendues, "le contrat ne porte aucune écriture portail.ecrire"
    assert attendues <= portent, f"écriture du contrat non ouverte à la clé : {sorted(attendues - portent)}"
    assert attendues == {(m, c) for m, c in portent if (m, c) in contrat}
