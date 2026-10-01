"""[.mark] Chantier fiabilite-fiche-et-renvoi (01/10/2026), plan
`Labo-agent-vocal/plans/fiabilite-fiche-et-renvoi/`.

Lot A : le contrôle « dit tel quel » d'un champ dicté sans module compare aux paroles de
la personne SANS les notes des modules. Au run 925 (clavier, n° 34 v9), « devis » a fait
PROPOSER Deville par le lexique ; la note du lexique, collée au message, contient
« Deville », et le contrôle l'a lue comme une parole : « DEVILLE » a été écrit sûr dans
le nom. Une proposition « à confirmer » n'est jamais une parole ; une reconnaissance SÛRE
du lexique l'est (la même parole, avec l'écriture officielle).

Ces tests passent par les VRAIES routes HTTP du clavier, avec le lexique de
l'organisation en base ; seuls le modèle (réponses écrites d'avance) est remplacé.

| Test | Ce qu'il prouve |
|---|---|
| proposition | un terme seulement PROPOSÉ par le lexique, écrit par le modèle dans un champ sans module, est refusé (`non_dit`) |
| reconnaissance sûre | « édile kamine » reconnu sûr (Edilkamin) : la phrase écrite avec l'écriture officielle reste écrite |
| transcription propre | « Deville » bien transcrit : écrit, comme avant (exigence d'Evan du 01/10 : ne pénaliser aucun transcripteur qui transcrit bien) |
"""

import pytest

from api.enums import OrganizationConfigurationKey
from api.tests.mark.test_clavier_porte_la_fiche import _converser, _monter, _noter
from pipecat.tests import MockLLMService

LEXIQUE = {
    "format": "lexique-mark",
    "version": 1,
    "modeles_importes": [],
    "termes": [
        {"terme": "Deville", "variantes": [], "prononciation": None, "type": "nom", "categorie": "marque", "a_ecouter": False},
        {"terme": "Edilkamin", "variantes": [], "prononciation": "édile kamine", "type": "nom", "categorie": "marque", "a_ecouter": False},
    ],
}

CONFIGURATION = {
    "fiche_au_fil_de_leau": True,
    "lexique_metier": True,
    "sons_lexique": True,
    "fiche_champs": [
        {"nom": "nom", "origine": "dicte", "description": "Nom de famille"},
        {"nom": "motif", "origine": "dicte", "description": "Ce que la personne demande"},
    ],
}


async def _avec_lexique(db_session, async_session):
    user, workflow = await _monter(db_session, async_session, CONFIGURATION)
    await db_session.upsert_configuration(
        workflow.organization_id, OrganizationConfigurationKey.LEXIQUE_METIER.value, LEXIQUE
    )
    return user, workflow


def _journal(fiche: dict, champ: str) -> list[dict]:
    return [e for e in fiche.get("fiche_journal") or [] if e.get("champ") == champ]


@pytest.mark.asyncio
async def test_A_un_terme_seulement_propose_par_le_lexique_n_est_pas_une_parole(
    db_session, async_session, test_client_factory
):
    user, workflow = await _avec_lexique(db_session, async_session)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [_noter({"nom": "Deville"}, "note_1"), MockLLMService.create_text_chunks("D'accord.")],
        "je voudrais un devis",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    # Le lexique a bien proposé Deville pour « devis » (sinon le test ne prouve rien).
    assert any(
        t.get("terme") == "Deville" and t.get("statut") == "a_confirmer"
        for t in fiche.get("lexique_reconnu") or []
    ), fiche.get("lexique_reconnu")
    assert not fiche.get("nom"), fiche
    assert [(e["statut"], e["raison"]) for e in _journal(fiche, "nom")] == [("refuse", "non_dit")]


@pytest.mark.asyncio
async def test_A_une_reconnaissance_sure_du_lexique_compte_comme_dite(
    db_session, async_session, test_client_factory
):
    user, workflow = await _avec_lexique(db_session, async_session)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [
            _noter({"motif": "mon poêle Edilkamin ne démarre plus"}, "note_1"),
            MockLLMService.create_text_chunks("D'accord."),
        ],
        "mon poêle édile kamine ne démarre plus",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert any(
        t.get("terme") == "Edilkamin" and t.get("statut") == "sure"
        for t in fiche.get("lexique_reconnu") or []
    ), fiche.get("lexique_reconnu")
    assert fiche.get("motif") == "mon poêle Edilkamin ne démarre plus", fiche


@pytest.mark.asyncio
async def test_A_transcription_propre_inchangee(db_session, async_session, test_client_factory):
    user, workflow = await _avec_lexique(db_session, async_session)
    charge, _ = await _converser(
        test_client_factory,
        user,
        workflow,
        [_noter({"motif": "mon poêle Deville ne ferme plus"}, "note_1"), MockLLMService.create_text_chunks("D'accord.")],
        "mon poêle Deville ne ferme plus",
    )
    fiche = charge["checkpoint"]["gathered_context"]
    assert fiche.get("motif") == "mon poêle Deville ne ferme plus", fiche
