"""[.mark] Partie 3, lot 14 (SE-21) : Bibliothèque, I-1, I-3, I-5.

| Test | Ce qu'il prouve |
|---|---|
| I-1 | la liste paginée accepte plusieurs statuts à la fois (``?statut=candidat&statut=rejete``) et garde l'un OU l'autre |
| I-5 | chaque famille rend son nombre d'éléments, en une lecture, sans toucher aux autres |
| I-3 | la route des champs d'une famille lit la forme imposée par le serveur (liste, nombre, choix, JSON), refuse une famille inconnue |
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import builder as route
from api.services.auth.depends import get_user, get_user_with_selected_organization
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Banc, Statut
from api.tests.mark.builder_commun import ORG_MARK, utilisateur

B = "/builder/bibliotheque"


@pytest.fixture
def c(monde):
    app = FastAPI()
    app.include_router(route.router)
    equipe = utilisateur(1, ORG_MARK)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: equipe
    app.dependency_overrides[get_user] = lambda: equipe
    return TestClient(app)


async def _remplir():
    await service.creer("moules-etape", "q", "Qualifier", {"texte": "t"}, "alice")
    await service.creer("moules-etape", "r", "Rejeter", {"texte": "t"}, "alice")
    await service.creer("moules-etape", "s", "Recette", {"texte": "t"}, "alice")
    await service.creer("personas", "p", "Persona", {"texte": "t"}, "alice")
    await service.marquer("moules-etape", "r", 1, Statut.REJETE, "alice", raison="trop long")
    await service.marquer("moules-etape", "s", 1, Statut.RECETTE, "alice", banc=Banc(description="banc"))


async def test_i1_plusieurs_statuts_se_cumulent(c, monde):
    await _remplir()

    def slugs(q: str) -> list[str]:
        return sorted(e["slug"] for e in c.get(f"{B}/parcourir?famille=moules-etape{q}").json()["elements"])

    assert slugs("") == ["q", "r", "s"]
    assert slugs("&statut=candidat") == ["q"]
    assert slugs("&statut=candidat&statut=rejete") == ["q", "r"]
    assert slugs("&statut=recette&statut=rejete") == ["r", "s"]


async def test_i5_chaque_famille_rend_son_nombre_d_elements(c, monde):
    await _remplir()
    familles = {f["slug"]: f for f in c.get(f"{B}/familles").json()}
    assert familles["moules-etape"]["nombre"] == 3
    assert familles["personas"]["nombre"] == 1
    assert familles["phrases-fixes"]["nombre"] == 0


def test_i3_les_champs_d_une_famille_viennent_de_la_forme_du_serveur(c, monde):
    champs = {x["nom"]: x for x in c.get(f"{B}/familles/scenarios-test/champs").json()}
    assert champs["but"]["obligatoire"] is True and champs["but"]["sorte"] == "long"
    assert champs["tours_max"]["sorte"] == "nombre" and champs["tours_max"]["obligatoire"] is False
    assert champs["questions_juge"]["sorte"] == "liste"
    assert champs["criteres"]["sorte"] == "objet"
    demarrage = {x["nom"]: x for x in c.get(f"{B}/familles/demarrages-builder/champs").json()}
    assert demarrage["besoin"]["sorte"] == "choix" and "agent et fichiers" in demarrage["besoin"]["choix"]
    assert c.get(f"{B}/familles/moules-etape/champs").json() == []  # forme libre : rien à montrer
    assert c.get(f"{B}/familles/famille-inconnue/champs").status_code == 404
