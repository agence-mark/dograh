"""[.mark] Non-regression test for the trade vocabulary: format, bounds, storage, import.

The questions this file answers:

    Is a valid vocabulary read back exactly as it was saved? Is every bound
    refused with a 422 BEFORE anything is written, and does a shared spelling
    name both terms? Does an unreadable row cost nothing (an empty vocabulary,
    no exception)? Does an import add only what is absent, unticked, and never
    change a term the organization already set? Is one organization's
    vocabulary never read for another?

Why it exists
-------------
Decisions L1, L3 and T1 to T3, T13 of the plan ``lexique-metier`` (2026-09-16):
the vocabulary lives in the database, per organization, and is filled from a
template of the socle. 🔴 An import that overwrote a term would silently undo a
pronunciation validated by ear; a bound checked only when a call reads the
vocabulary would cost the call.

⚠️ What this file does NOT prove: that the screen shows the vocabulary. That is
``ui/src/components/mark/``.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.enums import OrganizationConfigurationKey
from api.routes import organization as route_organisation
from api.schemas.lexique_metier import (
    MAX_LONGUEUR_CATEGORIE,
    MAX_LONGUEUR_PRONONCIATION,
    MAX_LONGUEUR_TERME,
    MAX_TERMES,
    MAX_VARIANTES,
    LexiqueMetier,
    normaliser_terme,
)
from api.services.auth.depends import get_user_with_selected_organization
from api.services.lexique import stockage
from api.services.lexique.stockage import fusionner_import, lire_lexique

ORGANISATION_A = 11
ORGANISATION_B = 12

LEXIQUE = {
    "format": "lexique-mark",
    "version": 1,
    "modeles_importes": [{"nom": "poeles-bois-granules", "date": "2026-09-16"}],
    "termes": [
        {"terme": "Edilkamin", "variantes": ["Edil Kamin"], "prononciation": "édile kamine",
         "type": "nom", "categorie": "marque", "a_ecouter": True},
        {"terme": "Jøtul", "variantes": [], "prononciation": None, "type": "nom",
         "categorie": "marque", "a_ecouter": False},
        {"terme": "ramoner", "variantes": [], "prononciation": None, "type": "mot",
         "categorie": None, "a_ecouter": True},
    ],
}


class _BaseEnMemoire:
    """The two methods of ``db_client`` the vocabulary uses, keyed by organization."""

    def __init__(self):
        self.lignes: dict[tuple[int, str], object] = {}

    async def get_configuration(self, organization_id, key):
        valeur = self.lignes.get((organization_id, key))
        return None if valeur is None else SimpleNamespace(value=valeur)

    async def upsert_configuration(self, organization_id, key, value, last_validated_at=None):
        self.lignes[(organization_id, key)] = value
        return SimpleNamespace(value=value)


CLE = OrganizationConfigurationKey.LEXIQUE_METIER.value


def _client(base: _BaseEnMemoire, organisation: int = ORGANISATION_A) -> TestClient:
    app = FastAPI()
    app.include_router(route_organisation.router)
    app.dependency_overrides[get_user_with_selected_organization] = lambda: SimpleNamespace(
        id=1, provider_id="p", selected_organization_id=organisation
    )
    return TestClient(app)


@pytest.fixture
def base():
    memoire = _BaseEnMemoire()
    with patch.object(stockage, "db_client", memoire):
        yield memoire


# --------------------------------------------------------------------------- #
# 1. PUT, bounds, shared spellings
# --------------------------------------------------------------------------- #


def test_un_lexique_valide_est_relu_a_lidentique(base):
    client = _client(base)
    ecrit = client.put("/organizations/lexique", json=LEXIQUE)
    assert ecrit.status_code == 200, ecrit.text
    assert base.lignes[(ORGANISATION_A, CLE)] == LEXIQUE
    relu = client.get("/organizations/lexique")
    assert relu.status_code == 200
    assert relu.json() == LEXIQUE


def _avec_terme(**champs) -> dict:
    terme = {"terme": "Rika", "variantes": [], "type": "nom", **champs}
    return {**LEXIQUE, "termes": [*LEXIQUE["termes"], terme]}


BORNES_DEPASSEES = {
    "terme-vide": _avec_terme(terme=""),
    "terme-blanc": _avec_terme(terme="   "),
    "terme-sans-lettre": _avec_terme(terme="+ - ."),
    "terme-trop-long": _avec_terme(terme="R" * (MAX_LONGUEUR_TERME + 1)),
    "trop-de-variantes": _avec_terme(variantes=[f"Rika {i}" for i in range(MAX_VARIANTES + 1)]),
    "variante-trop-longue": _avec_terme(variantes=["R" * (MAX_LONGUEUR_TERME + 1)]),
    "prononciation-trop-longue": _avec_terme(prononciation="r" * (MAX_LONGUEUR_PRONONCIATION + 1)),
    "categorie-trop-longue": _avec_terme(categorie="c" * (MAX_LONGUEUR_CATEGORIE + 1)),
    "type-inconnu": _avec_terme(type="marque"),
    "format-inconnu": {**LEXIQUE, "format": "autre"},
    "version-inconnue": {**LEXIQUE, "version": 2},
    "trop-de-termes": {**LEXIQUE, "termes": [{"terme": f"Marque{i:05d}"} for i in range(MAX_TERMES + 1)]},
}


@pytest.mark.parametrize("corps", list(BORNES_DEPASSEES.values()), ids=list(BORNES_DEPASSEES))
def test_chaque_borne_depassee_est_refusee_en_422_sans_rien_ecrire(base, corps):
    reponse = _client(base).put("/organizations/lexique", json=corps)
    assert reponse.status_code == 422, reponse.text
    assert base.lignes == {}


def test_la_borne_de_termes_est_juste():
    """2 000 terms pass, 2 001 do not (the refusal above is not a side effect)."""
    LexiqueMetier.model_validate({"termes": [{"terme": f"Marque{i:05d}"} for i in range(MAX_TERMES)]})


def test_une_forme_partagee_est_refusee_et_nomme_les_deux_termes(base):
    corps = {**LEXIQUE, "termes": [*LEXIQUE["termes"], {"terme": "Poêles Norvégiens", "variantes": ["Jotul"]}]}
    reponse = _client(base).put("/organizations/lexique", json=corps)
    assert reponse.status_code == 422
    assert "Jøtul" in reponse.text and "Poêles Norvégiens" in reponse.text
    assert base.lignes == {}


def test_deux_termes_de_meme_nom_sont_refuses():
    with pytest.raises(ValidationError, match="Godin"):
        LexiqueMetier.model_validate({"termes": [{"terme": "Godin"}, {"terme": "GODIN"}]})


def test_une_variante_egale_a_son_propre_terme_est_toleree():
    LexiqueMetier.model_validate({"termes": [{"terme": "MCZ", "variantes": ["mcz", "M.C.Z"]}]})


def test_formes_normalisees():
    assert normaliser_terme("Jøtul") == normaliser_terme("jotul") == "jotul"
    assert normaliser_terme("Haas+Sohn") == "haas sohn"
    assert normaliser_terme("Arts & Feu") == "arts et feu"
    assert normaliser_terme("Stûv") == "stuv"
    assert normaliser_terme("Cheminées  Godin") == "cheminees godin"


def test_les_blancs_sont_ranges():
    lexique = LexiqueMetier.model_validate(
        {"termes": [{"terme": "  Nestor   Martin ", "variantes": [" ", "Nestor-Martin "], "prononciation": "  ",
                     "categorie": ""}]}
    )
    terme = lexique.termes[0]
    assert terme.terme == "Nestor Martin"
    assert terme.variantes == ["Nestor-Martin"]
    assert terme.prononciation is None and terme.categorie is None


# --------------------------------------------------------------------------- #
# 2. Reading never raises
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_absent_donne_un_lexique_vide(base):
    assert (await lire_lexique(ORGANISATION_A)).termes == []
    assert (await lire_lexique(None)).termes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "valeur",
    [{"termes": [{"terme": ""}]}, {"termes": "pas une liste"}, ["pas", "un", "objet"], "texte", 12,
     {"termes": [{"terme": "A", "variantes": ["x"]}, {"terme": "X"}]}],
    ids=["borne", "termes-texte", "liste", "texte", "nombre", "forme-partagee"],
)
async def test_une_ligne_corrompue_donne_un_lexique_vide_sans_exception(base, valeur):
    base.lignes[(ORGANISATION_A, CLE)] = valeur
    with patch.object(stockage.logger, "warning") as avertissement:
        assert (await lire_lexique(ORGANISATION_A)).termes == []
    assert avertissement.call_count == 1


@pytest.mark.asyncio
async def test_une_base_indisponible_donne_un_lexique_vide():
    en_panne = SimpleNamespace(get_configuration=AsyncMock(side_effect=RuntimeError("base indisponible")))
    with patch.object(stockage, "db_client", en_panne):
        assert (await lire_lexique(ORGANISATION_A)).termes == []


# --------------------------------------------------------------------------- #
# 3. Import (T13)
# --------------------------------------------------------------------------- #

MODELE = {
    "modeles_importes": [{"nom": "poeles-bois-granules", "date": "2026-09-16"}],
    "termes": [
        {"terme": "Edilkamin", "variantes": ["Edilcamin"], "prononciation": None, "a_ecouter": True},
        {"terme": "Jotul", "prononciation": "iotoul"},
        {"terme": "Rika", "a_ecouter": True},
        {"terme": "Stûv", "variantes": ["Stuv"]},
        {"terme": "ramonage", "type": "mot"},
    ],
}


def test_import_dans_un_lexique_vide_ajoute_tout_decoche(base):
    reponse = _client(base).post("/organizations/lexique/import", json=MODELE)
    assert reponse.status_code == 200, reponse.text
    assert reponse.json() == {"ajoutes": 5, "deja_presents": 0}
    ecrit = LexiqueMetier.model_validate(base.lignes[(ORGANISATION_A, CLE)])
    assert [t.terme for t in ecrit.termes] == ["Edilkamin", "Jotul", "Rika", "Stûv", "ramonage"]
    assert not any(t.a_ecouter for t in ecrit.termes)
    assert [m.nom for m in ecrit.modeles_importes] == ["poeles-bois-granules"]


def test_import_sur_un_lexique_existant_ne_change_aucun_terme_present(base):
    client = _client(base)
    assert client.put("/organizations/lexique", json=LEXIQUE).status_code == 200
    reponse = client.post("/organizations/lexique/import", json=MODELE)
    assert reponse.status_code == 200, reponse.text
    # Edilkamin (same term) and Jotul (Jøtul normalised) were there; Rika, Stûv, ramonage were not.
    assert reponse.json() == {"ajoutes": 3, "deja_presents": 2}
    ecrit = LexiqueMetier.model_validate(base.lignes[(ORGANISATION_A, CLE)])
    avant = LexiqueMetier.model_validate(LEXIQUE)
    assert ecrit.termes[:3] == avant.termes[:3]  # pronunciation, spellings and box kept
    assert [t.terme for t in ecrit.termes[3:]] == ["Rika", "Stûv", "ramonage"]
    assert not any(t.a_ecouter for t in ecrit.termes[3:])
    # The same template imported twice is listed once.
    assert len(ecrit.modeles_importes) == 1
    again = client.post("/organizations/lexique/import", json=MODELE)
    assert again.json() == {"ajoutes": 0, "deja_presents": 5}


def test_un_terme_importe_est_present_des_quune_seule_de_ses_formes_lest():
    existant = LexiqueMetier.model_validate({"termes": [{"terme": "Cheminées Godin", "variantes": ["Godin"]}]})
    importe = LexiqueMetier.model_validate({"termes": [{"terme": "Godin", "variantes": ["Godin Fonderie"]}]})
    fusion, ajoutes, deja = fusionner_import(existant, importe)
    assert (ajoutes, deja) == (0, 1)
    assert fusion.termes == existant.termes


def test_import_qui_depasserait_la_borne_est_refuse_sans_ecrire(base):
    plein = {"termes": [{"terme": f"Marque{i:05d}"} for i in range(MAX_TERMES)]}
    base.lignes[(ORGANISATION_A, CLE)] = plein
    reponse = _client(base).post("/organizations/lexique/import", json={"termes": [{"terme": "Rika"}]})
    assert reponse.status_code == 422, reponse.text
    assert base.lignes[(ORGANISATION_A, CLE)] is plein


def test_import_dun_fichier_hors_bornes_refuse(base):
    reponse = _client(base).post("/organizations/lexique/import", json={"termes": [{"terme": ""}]})
    assert reponse.status_code == 422
    assert base.lignes == {}


# --------------------------------------------------------------------------- #
# 4. Isolation between organizations
# --------------------------------------------------------------------------- #


def test_le_lexique_dune_organisation_nest_jamais_lu_pour_une_autre(base):
    assert _client(base, ORGANISATION_B).put("/organizations/lexique", json=LEXIQUE).status_code == 200
    relu_a = _client(base, ORGANISATION_A).get("/organizations/lexique")
    assert relu_a.status_code == 200
    assert relu_a.json()["termes"] == []
    assert _client(base, ORGANISATION_A).post("/organizations/lexique/import", json=MODELE).json() == {
        "ajoutes": 5, "deja_presents": 0
    }
    # B untouched by A's import; each row carries its own organization.
    assert base.lignes[(ORGANISATION_B, CLE)] == LEXIQUE
    assert {cle[0] for cle in base.lignes} == {ORGANISATION_A, ORGANISATION_B}


def test_les_routes_figurent_dans_la_spec_publiee():
    app = FastAPI()
    app.include_router(route_organisation.router)
    chemins = app.openapi()["paths"]
    assert {"get", "put"} <= set(chemins["/organizations/lexique"])
    assert "post" in chemins["/organizations/lexique/import"]
