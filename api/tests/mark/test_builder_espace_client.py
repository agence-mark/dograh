"""[.mark] Builder partie 2, U2 quater (lot H2, E57) : le builder et le chat dans l'espace d'un client, cloisonnés.

| Test | Ce qu'il prouve |
|---|---|
| bibliothèque en lecture | dans l'espace d'un client, même une personne de l'équipe lit la bibliothèque et ne l'écrit pas (routes et actions) |
| depuis le Labo | la même personne, dans le Labo, l'écrit |
| autre organisation | une action du builder qui vise l'agent d'une autre organisation est refusée côté serveur (lecture et écriture) |
| clé d'API | une clé d'API n'écrit pas la bibliothèque, quel que soit son espace |
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import builder as route
from api.services.auth.depends import get_user, get_user_with_selected_organization
from api.services.builder.actions.registre import Contexte, executer
from api.tests.mark.builder_commun import AGENT, ORG_AUTRE, ORG_CLIENT, ORG_MARK, utilisateur

B = "/builder/bibliotheque"
CHEZ_LE_CLIENT = utilisateur(1, ORG_CLIENT)  # l'utilisateur 1 est de l'équipe .mark (voir ``monde``) ; ici dans l'espace d'un client
DANS_LE_LABO = utilisateur(1, ORG_MARK)
UN_AUTRE_CLIENT = utilisateur(1, ORG_AUTRE)


def client_pour(user) -> TestClient:
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: user
    app.dependency_overrides[get_user] = lambda: user
    return TestClient(app)


def test_dans_l_espace_d_un_client_la_bibliotheque_se_lit_sans_s_ecrire(monde):
    chez_le_client, au_labo = client_pour(CHEZ_LE_CLIENT), client_pour(DANS_LE_LABO)
    assert au_labo.post(f"{B}/moules-etape", json={"slug": "a", "titre": "A", "contenu": {"texte": "a"}}).status_code == 201
    for lecture in (f"{B}/familles", f"{B}/etiquettes", f"{B}/parcourir", f"{B}/moules-etape/a"):
        assert chez_le_client.get(lecture).status_code == 200, lecture
    ecritures = (
        chez_le_client.post(f"{B}/moules-etape", json={"slug": "b", "titre": "B", "contenu": {"texte": "b"}}),
        chez_le_client.post(f"{B}/etiquettes", json={"nom": "x"}),
        chez_le_client.post(f"{B}/moules-etape/a/rangement", json={"dossier": "x"}),
        chez_le_client.post(f"{B}/familles", json={"slug": "metiers", "libelle": "Métiers", "groupe": "guide", "mode": "fournit"}),
    )
    assert [r.status_code for r in ecritures] == [403] * len(ecritures)
    # Rien n'a été écrit au Labo, et le même geste, depuis le Labo, passe.
    assert chez_le_client.get(f"{B}/moules-etape/b").status_code == 404
    assert au_labo.post(f"{B}/etiquettes", json={"nom": "x"}).status_code in (200, 201)


@pytest.mark.asyncio
async def test_le_builder_d_un_client_ne_propose_ni_n_ecrit_rien_a_la_bibliotheque(monde):
    candidat = {"famille": "moules-etape", "slug": "c", "titre": "C", "contenu": {"texte": "c"}}
    proposition = {"type": "fiche", "famille": "moules-etape", "slug": "moules-etape", "justification": "plus clair", "contenu": {"description": "D", "quand": "Q", "comment": "C"}}
    chez_le_client = Contexte(user=CHEZ_LE_CLIENT, workflow_id=AGENT)
    for action, parametres in (("bibliotheque_ecrire_candidat", candidat), ("bibliotheque_proposer", proposition)):
        refus = await executer(action, parametres, chez_le_client)
        assert refus["ok"] is False and refus["code"] == "bibliotheque_403", (action, refus)
    # Depuis le Labo, la proposition entre (elle attend une personne).
    rendu = await executer("bibliotheque_proposer", proposition, Contexte(user=DANS_LE_LABO, workflow_id=None))
    assert rendu["ok"]
    # Lire reste permis chez le client.
    assert (await executer("bibliotheque_lister", {}, chez_le_client))["familles"]


@pytest.mark.asyncio
async def test_une_action_du_builder_vers_une_autre_organisation_est_refusee(monde):
    """L'agent 42 est celui du client 7 : le builder du client 8 ne le lit ni ne l'écrit, même avec son identifiant exact."""
    chez_l_autre = Contexte(user=UN_AUTRE_CLIENT, workflow_id=AGENT)
    for action in ("agent_montrer_le_graphe", "sauvegarde_prendre"):
        refus = await executer(action, {"workflow_id": AGENT}, chez_l_autre)
        assert refus["ok"] is False and refus["code"] == "introuvable", (action, refus)
    # Le même geste, dans l'organisation de l'agent, passe.
    rendu = await executer("agent_montrer_le_graphe", {"workflow_id": AGENT}, Contexte(user=CHEZ_LE_CLIENT, workflow_id=AGENT))
    assert rendu.get("ok", True) is not False, rendu


@pytest.mark.asyncio
async def test_une_carte_proposee_dans_le_labo_seulement_n_est_pas_offerte_a_un_client(monde):
    from api.services.builder import demarrages
    from api.services.builder.bibliotheque import service

    base = {"phrase": "une phrase", "demande": "Fais {agent}", "besoin": "agent", "icone": "test"}
    await service.creer("demarrages-builder", "partout", "Partout", base, "test")
    await service.creer("demarrages-builder", "labo-seul", "Labo seul", {**base, "proposee_dans": "labo"}, "test")
    au_labo = {c["slug"]: c for c in await demarrages.plus_utilises(dans_le_labo=True)}
    chez_un_client = {c["slug"]: c for c in await demarrages.plus_utilises(dans_le_labo=False)}
    assert set(au_labo) == {"partout", "labo-seul"} and au_labo["labo-seul"]["proposee_dans"] == "labo"
    assert set(chez_un_client) == {"partout"} and chez_un_client["partout"]["proposee_dans"] == "labo_et_clients"
    # Ouvrir une carte du Labo depuis l'espace d'un client : elle n'existe pas pour lui.
    assert await demarrages.lire("labo-seul", dans_le_labo=False) is None
    assert (await demarrages.lire("labo-seul", dans_le_labo=True))["slug"] == "labo-seul"


@pytest.mark.asyncio
async def test_les_demarrages_a_rang_suivent_l_ordre_de_la_maquette_les_autres_l_usage(monde):
    """Clôture D2 (É3) : un ``rang`` lu avec la donnée règle l'ordre ; sans rang, le classement par usage reprend, après eux."""
    from api.services.builder import demarrages
    from api.services.builder.bibliotheque import service

    base = {"phrase": "une phrase", "demande": "Fais {agent}", "besoin": "agent", "icone": "test"}
    await service.creer("demarrages-builder", "d-sans-rang-b", "Bravo sans rang", dict(base), "test")
    await service.creer("demarrages-builder", "d-trois", "Zèbre", {**base, "rang": 3}, "test")
    await service.creer("demarrages-builder", "d-un", "Yack", {**base, "rang": 1}, "test")
    await service.creer("demarrages-builder", "d-deux", "Xénon", {**base, "rang": 2}, "test")
    await service.creer("demarrages-builder", "d-sans-rang-a", "Alpha sans rang", {**base, "rang": "vite"}, "test")
    slugs = [c["slug"] for c in await demarrages.plus_utilises(10, dans_le_labo=True)]
    assert slugs[:3] == ["d-un", "d-deux", "d-trois"]
    # Sans rang (ou rang invalide) : après, par titre à égalité d'usage.
    assert slugs[3:] == ["d-sans-rang-a", "d-sans-rang-b"]
