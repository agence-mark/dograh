"""[.mark] V4 : les catégories du catalogue des intégrations (CRM, Agenda, Messages…), comme la colonne de la maquette.

La question : chaque connecteur du fork a-t-il une catégorie connue, et la route du catalogue la rend-elle ?
"""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.services.auth.depends import get_user_with_selected_organization
from api.services.integrations.connectors import actions  # noqa: F401  (déclare tous les connecteurs)
from api.services.integrations.connectors.catalogue import CATEGORIE_DU_CONNECTEUR, CATEGORIES, categorie_de, connecteurs
from api.services.integrations.connectors.routes import router


def test_chaque_connecteur_declare_a_une_categorie_connue():
    sans = [c.nom for c in connecteurs() if categorie_de(c) not in CATEGORIES]
    assert sans == []


def test_aucune_entree_de_la_table_ne_vise_un_connecteur_absent():
    noms = {c.nom for c in connecteurs()}
    assert sorted(set(CATEGORIE_DU_CONNECTEUR) - noms) == []


def test_la_route_du_catalogue_rend_la_categorie_de_chaque_connecteur():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(id=1, provider_id="p", selected_organization_id=7)
    chemins = [r.path for r in router.routes if getattr(r, "path", "").endswith("/catalogue")]
    assert chemins, "la route du catalogue n'existe plus"
    corps = TestClient(app).get(chemins[0])
    assert corps.status_code == 200, corps.text
    vus = {c["nom"]: c["categorie"] for c in corps.json()}
    assert vus["hubspot"] == "CRM" and vus["google_agenda"] == "Agenda" and vus["equipe"] == "Nos connecteurs" and vus["hektor"] == "Immobilier"
    assert all(v in CATEGORIES for v in vus.values())
