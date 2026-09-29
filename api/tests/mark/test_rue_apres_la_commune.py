"""[.mark] C2 : la rue relue après la confirmation de la commune, et le oui qui lève le « à confirmer ».

Chantier correctifs-banc-34 (29/09/2026). Run 893 : « cinq rues Carnot à Lyon-Cours soixante
mille cent quarante ». La commune n'étant pas sûre à ce tour, le module des rues ne lisait pas
la rue ; la commune confirmée (Liancourt) au tour suivant, rien ne la relisait. Puis l'agent a
fait confirmer l'adresse deux fois : au récapitulatif, le « oui » ne levait pas le « à
confirmer », parce qu'une autre question (la commune) s'était intercalée depuis.

⚠️ Il n'existe pas de rue Carnot à Liancourt (adresse du scénario) : au 893, le « à
confirmer » de la rue était légitime ; seul le oui du récapitulatif est un défaut. La
relecture est éprouvée sur une vraie rue de Liancourt (Rue Pasteur).

| Test | Ce qu'il prouve |
|---|---|
| relecture | la commune confirmée, la rue notée « à confirmer » est relue dans ses rues et écrite sûre, sous son nom officiel |
| rue introuvable | relue, pas trouvée : rien ne change (toujours à confirmer) |
| oui au récapitulatif (893) | la question de l'agent redit l'adresse, la personne dit oui : sûre, même après une autre question |
| oui à une autre question | un oui qui ne répond pas à cette valeur ne lève rien |
"""

import pytest

from api.tests.mark.test_fiche_correctifs_modules import Appel, _a_faire_confirmer, _reglages

COMMUNE = {"nom": "commune", "origine": "dicte"}
CODE = {"nom": "code_postal", "origine": "dicte"}
ADRESSE = {"nom": "adresse_intervention", "origine": "dicte"}
LIANCOURT = {"nom": "Liancourt", "code_insee": "60360", "departement": "Oise", "codes_postaux": ["60140"]}


async def _commune_a_proposer_rue_a_confirmer(rue: str) -> Appel:
    """Le tour 9 du 893 : commune entendue de travers, rue notée sans commune sûre."""
    appel = Appel(_reglages(COMMUNE, CODE, ADRESSE))
    appel.dit(
        f"Alors j'habite aux {rue} à Lyon-Cours 60140",
        agent_avant="Vous êtes dans quelle commune, et quel est le code postal ?",
    )
    appel.trace(
        "communes_verifiees",
        entendu="Lyon-Cours",
        statut="a_confirmer",
        commune_retenue=None,
        propositions=[LIANCOURT],
    )
    r = await appel.note(commune="Lyon-Cours", code_postal="60140", adresse_intervention=rue)
    assert "adresse_intervention" in _a_faire_confirmer(r), r
    return appel


@pytest.mark.asyncio
async def test_C2_la_commune_confirmee_la_rue_est_relue_et_ecrite_sure():
    appel = await _commune_a_proposer_rue_a_confirmer("12 rue Pasteur")
    appel.dit("Oui, c'est bien ça.", agent_avant="Est-ce que vous êtes sur la commune de Liancourt dans l'Oise ?")
    r = await appel.note(commune="Liancourt")
    assert appel.sure("commune") and appel.sure("adresse_intervention"), (r, appel.fiche)
    assert appel.fiche["adresse_intervention"] == "12 Rue Pasteur"
    assert "adresse_intervention" not in _a_faire_confirmer(r), r
    assert any(
        e["champ"] == "adresse_intervention" and e.get("raison") == "rue_relue_apres_la_commune"
        for e in appel.fiche["fiche_journal"]
    )


@pytest.mark.asyncio
async def test_C2_rue_introuvable_dans_la_commune_rien_ne_change():
    appel = await _commune_a_proposer_rue_a_confirmer("5 rue Carnot")
    appel.dit("Oui, c'est bien ça.", agent_avant="Est-ce que vous êtes sur la commune de Liancourt dans l'Oise ?")
    await appel.note(commune="Liancourt")
    assert appel.sure("commune") and not appel.sure("adresse_intervention")
    assert appel.fiche["adresse_intervention"] == "5 rue Carnot"


@pytest.mark.asyncio
async def test_C2_run_893_le_oui_au_recapitulatif_leve_le_a_confirmer():
    appel = await _commune_a_proposer_rue_a_confirmer("5 rue Carnot")
    appel.dit(
        "Oui, c'est bien ça.",
        agent_avant="D'accord, donc l'adresse est bien cinq rue Carnot.\nEst-ce que vous êtes sur la commune de Liancourt dans l'Oise ?",
    )
    await appel.note(commune="Liancourt")
    appel.dit(
        "Oui oui, c'est bien ça.",
        agent_avant="L'adresse que j'ai notée est cinq rue Carnot à Liancourt, code postal soixante mille cent quarante, c'est bien ça ?",
    )
    r = await appel.note(adresse_intervention="5 rue Carnot")
    assert appel.sure("adresse_intervention"), (r, appel.fiche)
    assert not _a_faire_confirmer(r), r


@pytest.mark.asyncio
async def test_C2_un_oui_a_une_autre_question_ne_leve_rien():
    appel = await _commune_a_proposer_rue_a_confirmer("5 rue Carnot")
    appel.dit("Oui, c'est bien ça.", agent_avant="Est-ce que vous êtes sur la commune de Liancourt dans l'Oise ?")
    await appel.note(commune="Liancourt")
    appel.dit("Oui.", agent_avant="Est-ce qu'il y a autre chose que je peux faire pour vous ?")
    await appel.note(adresse_intervention="5 rue Carnot")
    assert not appel.sure("adresse_intervention")


def test_C2_revue_la_rue_relue_n_est_pas_ecrite_si_la_fiche_a_change_pendant_le_calcul():
    """Le calcul se fait hors de la boucle ; l'écriture, au retour, vérifie que la
    commune et la rue n'ont pas bougé entre-temps."""
    from api.services.workflow.fiche_au_fil_de_leau import (
        CLE_ETAT,
        RueARelire,
        ecrire_les_rues_relues,
    )

    reglages = _reglages(COMMUNE, ADRESSE)
    fiche = {
        "commune": "Creil",
        "commune_insee": "60175",
        "adresse_intervention": "12 rue Pasteur",
        CLE_ETAT: {"commune": {"sure": True}, "adresse_intervention": {"sure": False}},
    }
    calculee = [(RueARelire("adresse_intervention", "12 rue Pasteur", "60360", "Liancourt"), "12 Rue Pasteur")]
    assert ecrire_les_rues_relues(fiche, reglages, calculee) == {}
    assert fiche["adresse_intervention"] == "12 rue Pasteur"
    fiche["commune_insee"] = "60360"
    assert ecrire_les_rues_relues(fiche, reglages, calculee) == {"adresse_intervention": "12 Rue Pasteur"}


@pytest.mark.asyncio
async def test_C6_revue_une_porte_attend_les_notes_de_son_lot():
    """Pipecat lance en parallèle les fonctions d'une même réponse : la porte du lot
    [note, porte] ne lit la fiche qu'une fois la note terminée."""
    import asyncio
    from types import SimpleNamespace

    from api.services.workflow.fiche_au_fil_de_leau import NOM_OUTIL, SuiviDesTours

    suivi = SuiviDesTours(lambda nom: nom == "porte")
    suivi.enregistrer(
        [SimpleNamespace(function_name=NOM_OUTIL, tool_call_id="n1"), SimpleNamespace(function_name="porte", tool_call_id="p1")]
    )
    attente = asyncio.create_task(suivi.attendre_les_notes("p1"))
    await asyncio.sleep(0.05)
    assert not attente.done()
    suivi.note_terminee("n1")
    await asyncio.wait_for(attente, 1.0)
    # Une porte seule n'attend rien.
    await asyncio.wait_for(suivi.attendre_les_notes("inconnue"), 0.1)
