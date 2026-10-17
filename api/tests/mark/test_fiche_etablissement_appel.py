"""[.mark] Chantier agents-specialises, lot 1 (= lot 1 du plan fiche-etablissement) :
l'agent choisit sa fiche, une fiche n'hérite de rien, fermeture par fiche.

Plan `Labo-agent-vocal/plans/agents-specialises/` (lot 1) et
`Labo-agent-vocal/plans/fiche-etablissement/` (F1, F3, F4, C2, C3, C5).

| Test | Ce qu'il prouve |
|---|---|
| fiche de l'agent | horaires, adresse, annonce, transfert de la FICHE, même si l'agent a les siens ; source estampillée |
| fiche sans adresse | une fiche sans adresse n'en a aucune (ni celle de l'agent, ni celle de l'organisation) |
| fiche disparue | une fiche choisie qui n'existe plus : aucun établissement, l'appel d'avant |
| agent sans fiche | le chemin d'avant, intact (le test d'avant reste vert) |
| passation | un agent sans fiche reçoit la fiche que l'appel porte |
| fermeture de la fiche | ferme ses agents et pas les autres |
| tout fermer | la fermeture de l'organisation ferme une fiche qui n'a pas la sienne |
| écran | ``POST /etablissements/agent`` rend la fiche et l'origine « fiche » |
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture
from api.schemas.etablissements import CatalogueEtablissements, Etablissement
from api.schemas.organization_preferences import OrganizationPreferences
from api.schemas.phrases import CataloguePhrases
from api.services.etablissements import copie as module_copie
from api.services.etablissements.appel import (
    choisir_etablissement,
    etablissements_de_lagent,
)
from api.services.workflow import text_chat_runner
from api.tests.mark.test_adresse_etablissement import _jouer_au_clavier
from api.tests.mark.test_etablissements_heritage import (
    CATALOGUE,
    CREIL,
    DIMANCHE_11H,
    HORAIRES_AGENT,
    HORAIRES_CREIL,
    MARDI_11H,
    SENLIS_SITE,
)

ADRESSE_AGENT = {"code_postal": "60100", "code_insee": "60175", "commune": "Creil"}


async def _clavier(catalogue, configurations=None, contexte=None, maintenant=DIMANCHE_11H, annonce=None, preferences=None):
    from api.services.pipecat import etat_ouverture

    reel = etat_ouverture.injecter_etat_ouverture
    with (
        patch.object(
            module_copie,
            "lire_copie_complete",
            AsyncMock(
                return_value=module_copie.CopieOrganisation(
                    etablissements=catalogue, phrases=CataloguePhrases(), lu_depuis="copie"
                )
            ),
        ),
        patch.object(
            text_chat_runner,
            "injecter_etat_ouverture",
            lambda ctx, cfg, **kw: reel(ctx, cfg, maintenant=maintenant, **kw),
        ),
        patch.object(
            text_chat_runner,
            "lire_annonce_ouverture",
            AsyncMock(return_value=annonce or ReglagesAnnonceOuverture()),
        ),
    ):
        return await _jouer_au_clavier(
            configurations or {}, contexte or {"direction": "inbound"}, preferences or OrganizationPreferences()
        )


@pytest.mark.asyncio
async def test_la_fiche_de_l_agent_seule_meme_s_il_a_ses_horaires():
    persiste = await _clavier(
        CATALOGUE,
        {"etablissement_id": "creil", "horaires_ouverture": HORAIRES_AGENT, "adresse_etablissement": ADRESSE_AGENT},
    )
    assert persiste["etablissement"] == "Magasin de Creil"
    assert persiste["numero_transfert"] == "+33344000099"
    assert persiste["horaires_ouverture"] == HORAIRES_CREIL
    assert persiste["adresse_etablissement"] == "60300 Senlis"
    assert persiste["etat_ouverture"] == "FERME"
    assert persiste["annonce_ouverture"].startswith("Le magasin de Creil est fermé")
    assert persiste["etablissement_de_lappel"] == "creil"
    estampille = persiste["runtime_configuration"]["etablissement"]
    assert estampille["source"] == "fiche_de_lagent", estampille
    assert estampille["origines"] == {"horaires_ouverture": "fiche", "adresse": "fiche"}


@pytest.mark.asyncio
async def test_une_fiche_sans_adresse_n_en_a_aucune():
    org = OrganizationPreferences(adresse_etablissement=ADRESSE_AGENT)
    persiste = await _clavier(
        CATALOGUE,
        {"etablissement_id": "senlis", "adresse_etablissement": ADRESSE_AGENT},
        preferences=org,
    )
    assert persiste["etablissement"] == "Magasin de Senlis"
    assert "adresse_etablissement" not in persiste, persiste.get("adresse_etablissement")
    assert persiste["runtime_configuration"]["etablissement"]["origines"]["adresse"] == "aucune"


@pytest.mark.asyncio
async def test_une_fiche_disparue_donne_l_appel_d_avant():
    avec = await _clavier(CATALOGUE, {"etablissement_id": "fermee-depuis", "horaires_ouverture": HORAIRES_AGENT})
    assert "etablissement" not in avec and "etablissement" not in avec["runtime_configuration"]
    assert avec["horaires_ouverture"] == HORAIRES_AGENT
    assert choisir_etablissement(CATALOGUE, {}, [], "fermee-depuis") is None


@pytest.mark.asyncio
async def test_l_agent_appele_sans_fiche_recoit_la_fiche_de_l_appel():
    persiste = await _clavier(
        CATALOGUE,
        {"horaires_ouverture": HORAIRES_AGENT},
        contexte={"direction": "inbound", "etablissement_de_lappel": "creil", "called_number": "+33344000002"},
    )
    assert persiste["etablissement"] == "Magasin de Creil"
    assert persiste["horaires_ouverture"] == HORAIRES_CREIL
    assert persiste["runtime_configuration"]["etablissement"]["source"] == "appel"


@pytest.mark.asyncio
async def test_la_fermeture_de_la_fiche_ferme_ses_agents_et_pas_les_autres():
    fermee = Etablissement(**{**CREIL.model_dump(), "etat_force": "FERME"})
    catalogue = CatalogueEtablissements(etablissements=[fermee, SENLIS_SITE])
    horaires_ouverts = HORAIRES_CREIL
    a = await _clavier(catalogue, {"etablissement_id": "creil"}, maintenant=MARDI_11H)
    assert a["etat_ouverture"] == "FERME", a["etat_ouverture"]
    autre = Etablissement(**{**SENLIS_SITE.model_dump(), "horaires_ouverture": horaires_ouverts})
    b = await _clavier(
        CatalogueEtablissements(etablissements=[fermee, autre]),
        {"etablissement_id": "senlis"},
        maintenant=MARDI_11H,
    )
    assert b["etat_ouverture"] == "OUVERT", b.get("etat_ouverture")


@pytest.mark.asyncio
async def test_tout_fermer_ferme_une_fiche_qui_n_a_pas_la_sienne():
    ouverte = Etablissement(**{**SENLIS_SITE.model_dump(), "horaires_ouverture": HORAIRES_CREIL})
    annonce = ReglagesAnnonceOuverture(etat_force="FERME")
    persiste = await _clavier(
        CatalogueEtablissements(etablissements=[ouverte]),
        {"etablissement_id": "senlis"},
        maintenant=MARDI_11H,
        annonce=annonce,
    )
    assert persiste["etat_ouverture"] == "FERME", persiste["etat_ouverture"]


def test_une_fin_de_fermeture_sans_etat_est_refusee():
    with pytest.raises(ValueError):
        Etablissement(id="x", nom="X", etat_force_jusqu_a=datetime(2026, 12, 24, 18, 0))


def test_l_ecran_de_l_agent_rend_sa_fiche_et_l_origine_fiche():
    vu = etablissements_de_lagent(
        CATALOGUE, ["+33344000002"], {"etablissement_id": "creil", "horaires_ouverture": HORAIRES_AGENT}, None, None
    )
    assert vu.fiche_de_lagent == "creil" and [e.id for e in vu.etablissements] == ["creil"]
    assert vu.etablissements[0].horaires_ouverture.origine == "fiche"
    assert vu.etablissements[0].horaires_ouverture.valeur == HORAIRES_CREIL
    disparue = etablissements_de_lagent(CATALOGUE, [], {"etablissement_id": "nulle-part"}, None, None)
    assert disparue.fiche_introuvable and disparue.etablissements == []


def test_l_ecran_rend_les_numeros_de_l_agent_avec_ou_sans_fiche():
    """Lot 11 (C4) : les numéros sont à l'agent. L'écran les lit sous le choix de la fiche, quel
    que soit le mode (fiche choisie, fiche disparue, agent sans fiche)."""
    numeros = ["+33344000002", "+33100000000"]
    avec = etablissements_de_lagent(CATALOGUE, numeros, {"etablissement_id": "creil"}, None, None)
    assert avec.numeros_de_lagent == numeros
    disparue = etablissements_de_lagent(CATALOGUE, numeros, {"etablissement_id": "nulle-part"}, None, None)
    assert disparue.fiche_introuvable and disparue.numeros_de_lagent == numeros
    sans = etablissements_de_lagent(CATALOGUE, numeros, {}, None, None)
    assert sans.numeros_de_lagent == numeros
    assert etablissements_de_lagent(CATALOGUE, [], {"etablissement_id": "creil"}, None, None).numeros_de_lagent == []
