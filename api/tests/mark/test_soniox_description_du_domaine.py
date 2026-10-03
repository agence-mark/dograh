"""[.mark] Chantier communes-cp-et-lexique-soniox, lot 5bis (S4, Q5 of 2026-10-02).
Plan : ``Labo-agent-vocal/plans/communes-cp-et-lexique-soniox/2026-10-02-plan-communes-cp-et-lexique-soniox.md``.

A short description of the agent's domain, set on the agent when Soniox is
chosen, sent in Soniox's context (``general``, key ``domain``) with the terms:

| Test | Decision |
|---|---|
| the field is Soniox's only, 300 characters at most, in the « Vocabulary » sub-menu | Q5, Q5-bis |
| the description takes from the ceiling FIRST, the terms fill the rest | Q5-ter |
| without a declared ceiling, neither leaves (rule Q1 of the lexicon) | Q1 du lexique |
| the factory puts it in the message Soniox receives, the stamp counts it | Q5 |
| the agent's save route writes it untouched (real write path) | Q5 |
"""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.services.configuration.plafond_lexique import PlafondLexique
from api.services.configuration.registry import (
    DESCRIPTION_DU_DOMAINE_MAX,
    DeepgramSTTConfiguration,
    SonioxSTTConfiguration,
)
from api.services.lexique.ecoute import construire_liste_ecoutee, description_du_domaine
from api.services.pipecat.filet_lexique import ETAT_ENVOYE, estampille_de_la_liste
from api.tests.mark.test_soniox_expose import _message_de_configuration, _service
from api.tests.mark.test_surcharge_par_service_survit_a_lenregistrement import (
    _enregistrer,
)

DESCRIPTION = (
    "Vente, pose et entretien de poêles à bois, à granulés et d'inserts ; ramonage."
)

# A ceiling in tokens small enough to watch the description take its share.
PETIT_PLAFOND = PlafondLexique(
    fournisseur="Soniox",
    jetons=40,
    termes=None,
    octets_par_jeton=3.5,
    jetons_par_terme=2,
    source="test",
)


# --- The field: Soniox only, bounded, labelled, filed ---


def test_le_champ_est_propre_a_soniox_borne_et_range():
    proprietes = SonioxSTTConfiguration.model_json_schema()["properties"]
    champ = proprietes["domain_description"]
    assert champ["maxLength"] == DESCRIPTION_DU_DOMAINE_MAX == 300
    assert champ["mark_groupe"] == "vocabulaire"
    assert champ["mark_libelle"] == {
        "en": "Domain description",
        "fr": "Description du domaine",
    }
    assert "300 characters" in champ["description"]
    assert (
        "domain_description"
        not in DeepgramSTTConfiguration.model_json_schema()["properties"]
    )


def test_301_caracteres_sont_refuses_a_l_enregistrement():
    SonioxSTTConfiguration(api_key="k", domain_description="a" * 300)
    with pytest.raises(ValidationError):
        SonioxSTTConfiguration(api_key="k", domain_description="a" * 301)


@pytest.mark.parametrize("vide", [None, "", "   \n "])
def test_une_description_vide_n_est_pas_une_description(vide):
    assert (
        description_du_domaine(
            SonioxSTTConfiguration(api_key="k", domain_description=vide)
        )
        is None
    )
    assert description_du_domaine(DeepgramSTTConfiguration(api_key="k")) is None


# --- The budget: the description first (Q5-ter) ---


def test_la_description_passe_d_abord_et_les_termes_remplissent_le_reste():
    termes = ", ".join(f"Marque{n}" for n in range(12))
    sans = construire_liste_ecoutee(termes, None, PETIT_PLAFOND)
    avec = construire_liste_ecoutee(
        termes, None, PETIT_PLAFOND, description="poêles à bois"
    )
    assert avec.description == "poêles à bois"
    assert len(avec.termes) < len(sans.termes), (
        "the description took no share of the ceiling"
    )
    assert avec.jetons <= PETIT_PLAFOND.jetons
    assert avec.termes == sans.termes[: len(avec.termes)], (
        "the terms kept are not the first ones"
    )


def test_sans_plafond_ni_la_liste_ni_la_description_ne_partent():
    liste = construire_liste_ecoutee("Edilkamin", None, None, description=DESCRIPTION)
    assert liste.description is None and liste.termes == []


def test_l_estampille_compte_la_description_envoyee():
    liste = construire_liste_ecoutee(
        None, None, PETIT_PLAFOND, description="poêles à bois"
    )
    estampille = estampille_de_la_liste(liste)
    assert estampille["etat"] == ETAT_ENVOYE
    assert estampille["description_caracteres"] == len("poêles à bois")


# --- The factory: what Soniox receives ---


@pytest.fixture
def plafond_soniox(monkeypatch):
    """A ceiling declared for Soniox, as lot 4 declares it."""
    from api.services.pipecat import service_factory

    monkeypatch.setattr(service_factory, "plafond_du_lexique", lambda *_: PETIT_PLAFOND)


def _service_avec_description(keyterms, description):
    from api.services.pipecat.service_factory import create_stt_service
    from api.tests.mark.test_soniox_expose import _audio_config, _config

    return create_stt_service(
        SimpleNamespace(stt=_config(domain_description=description)),
        _audio_config(),
        keyterms=keyterms,
        description_domaine=description,
    )


@pytest.mark.asyncio
async def test_la_description_et_les_termes_arrivent_dans_le_message(plafond_soniox):
    message = await _message_de_configuration(
        _service_avec_description(["Edilkamin"], DESCRIPTION)
    )
    assert message["context"]["general"] == [{"key": "domain", "value": DESCRIPTION}]
    assert message["context"]["terms"] == ["Edilkamin"]


@pytest.mark.asyncio
async def test_la_description_seule_part_aussi(plafond_soniox):
    message = await _message_de_configuration(
        _service_avec_description(None, DESCRIPTION)
    )
    assert message["context"]["general"] == [{"key": "domain", "value": DESCRIPTION}]
    assert not message["context"].get("terms")


@pytest.mark.asyncio
async def test_sans_plafond_declare_la_description_ne_part_pas(monkeypatch):
    from api.services.pipecat import service_factory

    monkeypatch.setattr(service_factory, "plafond_du_lexique", lambda *_: None)
    message = await _message_de_configuration(
        _service_avec_description(None, DESCRIPTION)
    )
    assert message["context"] is None


@pytest.mark.asyncio
async def test_sans_description_ni_terme_aucun_contexte(plafond_soniox):
    message = await _message_de_configuration(_service())
    assert message["context"] is None


# --- The write path: the agent's save route keeps it ---


def _surcharge_soniox(description: str) -> dict:
    from api.services.configuration.ai_model_configuration import (
        DELIBERATE_PER_SERVICE_OVERRIDE_KEY,
    )

    return {
        "model_overrides": {
            "stt": {
                "provider": "soniox",
                "model": "stt-rt-v5",
                "api_key": "cle-soniox",
                "domain_description": description,
            }
        },
        DELIBERATE_PER_SERVICE_OVERRIDE_KEY: True,
    }


def test_la_route_d_enregistrement_de_l_agent_garde_la_description():
    ecrit = _enregistrer(_surcharge_soniox(DESCRIPTION))
    assert ecrit["model_overrides"]["stt"]["domain_description"] == DESCRIPTION


def test_la_route_d_enregistrement_refuse_301_caracteres():
    with pytest.raises(AssertionError, match="422"):
        _enregistrer(_surcharge_soniox("a" * 301))
