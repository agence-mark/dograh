"""[.mark] Non-regression test for the announcement settings of an organization.

The questions this file answers, and only these:

    Are the two sentences and the forced state read back exactly as they were
    saved? Is what would be heard wrong refused with a 422 BEFORE anything is
    written (an unclosed bracket, a placeholder that does not exist, an end date
    with no forced state)? Does a row that is absent, unreadable or past a bound
    cost nothing to a CALL -- the default sentences, no exception -- while the
    SCREEN is told rather than shown defaults it would overwrite? Is one
    organization's setting never read for another?

Why it exists
-------------
The chantier ``corrections-appels-agent-6`` (18/09/2026) made the closing
announcement computed by the code. The sentences were written IN the code. Evan,
the same day: the phrases and the state of the business must be editable in the
settings. 🔴 Two defects this file exists to keep out: a sentence that costs a
call (a bound checked when a call reads it), and a save that replaces settings
the screen could not read -- the exact defect the independent review of 17/09
found on the trade vocabulary.

⚠️ What this file does NOT prove: that the screen shows these settings (that is
``ui/src/components/mark/annonce-ouverture-ecran.test.tsx``), nor what the agent
says with them (that is ``test_etat_ouverture.py``).
"""

from datetime import datetime
from types import SimpleNamespace
from typing import get_args
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.enums import OrganizationConfigurationKey
from api.routes import organization as route_organisation
from api.schemas.annonce_ouverture import (
    MAX_LONGUEUR_ANNONCE,
    EtatForce,
    ReglagesAnnonceOuverture,
)
from api.services.annonce import stockage
from api.services.annonce.stockage import lire_annonce_ouverture
from api.services.auth.depends import get_user_with_selected_organization
from api.services.pipecat.etat_ouverture import (
    ANNONCE_FERMETURE_DEFAUT,
    ANNONCE_PAUSE_DEFAUT,
    ETATS,
)

ORGANISATION_A = 11
ORGANISATION_B = 12

REGLAGES = {
    "format": "annonce-ouverture-mark",
    "version": 1,
    "annonce_fermeture": "Le magasin est fermé[, nous rouvrons {reouverture}].",
    "annonce_pause": "Nous revenons dans un instant[, à {reouverture}].",
    "etat_force": "FERME",
    "etat_force_jusqu_a": "2026-12-26T09:00:00",
}


class _BaseEnMemoire:
    """The two methods of ``db_client`` these settings use, keyed by organization."""

    def __init__(self):
        self.lignes: dict[tuple[int, str], object] = {}

    async def get_configuration(self, organization_id, key):
        valeur = self.lignes.get((organization_id, key))
        return None if valeur is None else SimpleNamespace(value=valeur)

    async def upsert_configuration(self, organization_id, key, value, last_validated_at=None):
        self.lignes[(organization_id, key)] = value
        return SimpleNamespace(value=value)


CLE = OrganizationConfigurationKey.ANNONCE_OUVERTURE.value


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
# 1. The list of states cannot drift away from the one the call uses
# --------------------------------------------------------------------------- #


def test_les_etats_offerts_a_lecran_sont_exactement_ceux_de_lappel():
    """⛔ The Literal is duplicated so the screen's types can be generated.

    Both ways, and the count: a Literal that lost a state would offer three
    choices on screen, and a Literal that gained one would let an organization
    force a state no call can read. Decision 4 of 18/09: the list of states does
    not change.
    """
    offerts = get_args(EtatForce)
    assert set(offerts) == set(ETATS)
    assert len(offerts) == len(ETATS) == 4


# --------------------------------------------------------------------------- #
# 2. PUT, GET, bounds
# --------------------------------------------------------------------------- #


def test_des_reglages_valides_sont_relus_a_lidentique(base):
    client = _client(base)
    ecrit = client.put("/organizations/annonce-ouverture", json=REGLAGES)
    assert ecrit.status_code == 200, ecrit.text
    assert base.lignes[(ORGANISATION_A, CLE)] == REGLAGES
    relu = client.get("/organizations/annonce-ouverture")
    assert relu.status_code == 200
    assert relu.json() == REGLAGES


def test_sans_ligne_lecran_recoit_les_phrases_par_defaut(base):
    reponse = _client(base).get("/organizations/annonce-ouverture")
    assert reponse.status_code == 200
    assert reponse.json()["annonce_fermeture"] == ANNONCE_FERMETURE_DEFAUT
    assert reponse.json()["annonce_pause"] == ANNONCE_PAUSE_DEFAUT
    assert reponse.json()["etat_force"] is None


REFUSES = {
    "crochet-jamais-referme": {"annonce_fermeture": "Fermé[, retour {reouverture}."},
    "crochet-fermant-seul": {"annonce_fermeture": "Fermé, retour]."},
    "crochets-imbriques": {"annonce_fermeture": "Fermé[ [x] ]."},
    "variable-inconnue": {"annonce_fermeture": "Fermé, retour {reouvertue}."},
    "variable-inconnue-en-pause": {"annonce_pause": "Retour {heure}."},
    "phrase-trop-longue": {"annonce_fermeture": "F" * (MAX_LONGUEUR_ANNONCE + 1)},
    "etat-inconnu": {"etat_force": "CONGES"},
    "date-sans-etat": {"etat_force": None, "etat_force_jusqu_a": "2026-12-26T09:00:00"},
    "date-illisible": {"etat_force": "FERME", "etat_force_jusqu_a": "jeudi prochain"},
    "format-inconnu": {"format": "autre"},
    "version-inconnue": {"version": 2},
}


@pytest.mark.parametrize("champs", list(REFUSES.values()), ids=list(REFUSES))
def test_chaque_saisie_fautive_est_refusee_en_422_sans_rien_ecrire(base, champs):
    reponse = _client(base).put("/organizations/annonce-ouverture", json={**REGLAGES, **champs})
    assert reponse.status_code == 422, reponse.text
    assert base.lignes == {}


def test_la_borne_de_longueur_est_juste():
    """300 characters pass, 301 do not (the refusal above is not a side effect)."""
    ReglagesAnnonceOuverture.model_validate({"annonce_fermeture": "F" * MAX_LONGUEUR_ANNONCE})
    with pytest.raises(ValidationError):
        ReglagesAnnonceOuverture.model_validate(
            {"annonce_fermeture": "F" * (MAX_LONGUEUR_ANNONCE + 1)}
        )


def test_une_phrase_vide_est_acceptee_et_relue_vide(base):
    """Decision D: an organization that wants no announcement at all empties it."""
    client = _client(base)
    corps = {**REGLAGES, "annonce_fermeture": "", "annonce_pause": ""}
    assert client.put("/organizations/annonce-ouverture", json=corps).status_code == 200
    assert client.get("/organizations/annonce-ouverture").json()["annonce_fermeture"] == ""


def test_un_etat_force_sans_date_est_accepte(base):
    """Decision C: an empty date is a forcing that holds until someone lifts it."""
    corps = {**REGLAGES, "etat_force": "FERME", "etat_force_jusqu_a": None}
    reponse = _client(base).put("/organizations/annonce-ouverture", json=corps)
    assert reponse.status_code == 200, reponse.text
    assert base.lignes[(ORGANISATION_A, CLE)]["etat_force_jusqu_a"] is None


def test_les_espaces_multiples_sont_reduits_avant_decriture(base):
    corps = {**REGLAGES, "annonce_fermeture": "  Fermé   en   ce moment.  "}
    _client(base).put("/organizations/annonce-ouverture", json=corps)
    assert base.lignes[(ORGANISATION_A, CLE)]["annonce_fermeture"] == "Fermé en ce moment."


# --------------------------------------------------------------------------- #
# 3. Reading: a call never pays, the screen is never shown defaults it would overwrite
# --------------------------------------------------------------------------- #


ILLISIBLES = {
    "pas-un-objet": "Nous sommes fermés.",
    "etat-inconnu": {**REGLAGES, "etat_force": "CONGES"},
    "phrase-hors-bornes": {**REGLAGES, "annonce_fermeture": "F" * (MAX_LONGUEUR_ANNONCE + 1)},
    "champ-du-mauvais-type": {**REGLAGES, "annonce_pause": 12},
}


@pytest.mark.asyncio
@pytest.mark.parametrize("valeur", list(ILLISIBLES.values()), ids=list(ILLISIBLES))
async def test_une_ligne_illisible_donne_les_phrases_par_defaut_sans_lever(base, valeur):
    base.lignes[(ORGANISATION_A, CLE)] = valeur
    reglages = await lire_annonce_ouverture(ORGANISATION_A)
    assert reglages.annonce_fermeture == ANNONCE_FERMETURE_DEFAUT
    assert reglages.etat_force is None


@pytest.mark.asyncio
async def test_sans_ligne_et_sans_organisation_les_phrases_par_defaut(base):
    assert (await lire_annonce_ouverture(ORGANISATION_A)).annonce_pause == ANNONCE_PAUSE_DEFAUT
    assert (await lire_annonce_ouverture(None)).annonce_pause == ANNONCE_PAUSE_DEFAUT


@pytest.mark.asyncio
async def test_une_base_qui_tombe_ne_coute_pas_lappel():
    class _BaseQuiTombe:
        async def get_configuration(self, *args, **kwargs):
            raise RuntimeError("database down")

    with patch.object(stockage, "db_client", _BaseQuiTombe()):
        reglages = await lire_annonce_ouverture(ORGANISATION_A)
    assert reglages.annonce_fermeture == ANNONCE_FERMETURE_DEFAUT


def test_lecran_refuse_de_lire_une_ligne_illisible_plutot_que_montrer_les_defauts(base):
    """⛔ The opposite rule of the call's, and for one reason: the screen SAVES.

    Shown the defaults, the next save would replace sentences that are really
    there with sentences nobody chose.
    """
    base.lignes[(ORGANISATION_A, CLE)] = {**REGLAGES, "etat_force": "CONGES"}
    reponse = _client(base).get("/organizations/annonce-ouverture")
    assert reponse.status_code == 500
    assert "saving now would replace them" in reponse.text


def test_les_reglages_dune_organisation_ne_sont_jamais_lus_pour_une_autre(base):
    _client(base, ORGANISATION_A).put("/organizations/annonce-ouverture", json=REGLAGES)
    autre = _client(base, ORGANISATION_B).get("/organizations/annonce-ouverture")
    assert autre.status_code == 200
    assert autre.json()["annonce_fermeture"] == ANNONCE_FERMETURE_DEFAUT
    assert autre.json()["etat_force"] is None


# --------------------------------------------------------------------------- #
# 4. The defaults are the sentences of before, word for word
# --------------------------------------------------------------------------- #


def test_les_phrases_par_defaut_sont_celles_davant_mot_pour_mot():
    """🔒 An organization that never opens this screen must hear no change.

    These two strings are what ``phrase_annonce`` built in its own code until
    18/09. Changing them here changes what every client already in production
    says at pick-up.
    """
    assert ANNONCE_FERMETURE_DEFAUT == "Nous sommes fermés en ce moment[, nous rouvrons {reouverture}]."
    assert ANNONCE_PAUSE_DEFAUT == "Nous sommes fermés pour le moment[, nous rouvrons {reouverture}]."
    vides = ReglagesAnnonceOuverture()
    assert vides.annonce_fermeture == ANNONCE_FERMETURE_DEFAUT
    assert vides.annonce_pause == ANNONCE_PAUSE_DEFAUT


def test_une_date_de_fin_naive_est_relue_telle_quelle(base):
    """The screen types a Paris date without an offset; it must come back the same."""
    client = _client(base)
    client.put("/organizations/annonce-ouverture", json=REGLAGES)
    relu = ReglagesAnnonceOuverture.model_validate(base.lignes[(ORGANISATION_A, CLE)])
    assert relu.etat_force_jusqu_a == datetime(2026, 12, 26, 9, 0)
    assert relu.etat_force_jusqu_a.tzinfo is None
