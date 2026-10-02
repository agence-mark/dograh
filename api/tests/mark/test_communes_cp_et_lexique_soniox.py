"""[.mark] Chantier communes-cp-et-lexique-soniox.
Plan : ``Labo-agent-vocal/plans/communes-cp-et-lexique-soniox/2026-10-02-plan-communes-cp-et-lexique-soniox.md``.

Chaque test de la fiche appelle le VRAI gestionnaire de ``noter_information``
(``creer_gestionnaire``) comme le modèle l'appelle, sur une fiche où les traces des
modules sont écrites comme les modules les écrivent.

| Test | Lot | Preuve (run) |
|---|---|---|
| un oui à une commune proposée depuis le code postal l'écrit | C1 | 1019 |
"""

import pytest

from api.services.communes.base import charger_base
from api.tests.mark.test_fiche_correctifs_modules import Appel, _a_faire_confirmer, _reglages

COMMUNE = {"nom": "commune", "origine": "dicte"}
CODE_POSTAL = {"nom": "code_postal", "origine": "dicte"}


# --- C1 : une option proposée par la fiche se confirme, quelle que soit sa source ---


async def _sainte_maxence_proposee() -> Appel:
    """Run 1019 : « Sainte-Maxence » n'est pas une commune ; le code postal 60700, lu par le
    module des nombres, fait proposer ses communes, Pont-Sainte-Maxence en premier."""
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL))
    appel.dit("je suis au circuit dentaire 60700, pour Sainte-Maxence.")
    appel.trace("nombres_lus", type="code_postal", retenu="60700")
    r = await appel.note(commune="Sainte-Maxence", code_postal="60700")
    proposees = [p for p in r.get("a_proposer") or [] if p["champ"] == "commune"]
    assert proposees and proposees[0]["options"][0] == "Pont-Sainte-Maxence (Oise)", r
    assert not appel.sure("commune")
    return appel


@pytest.mark.asyncio
async def test_C1_run_1019_un_oui_a_la_commune_proposee_depuis_le_code_postal_l_ecrit():
    appel = await _sainte_maxence_proposee()
    appel.dit("Oui, oui.", agent_avant="Est-ce que vous êtes bien sur Pont-Sainte-Maxence ?")
    r = await appel.note(commune="Pont-Sainte-Maxence")
    assert "commune" not in _a_faire_confirmer(r), r
    assert appel.sure("commune") and appel.fiche["commune"] == "Pont-Sainte-Maxence", r


@pytest.mark.asyncio
async def test_C1_l_option_renvoyee_avec_son_departement_est_aussi_reconnue():
    appel = await _sainte_maxence_proposee()
    appel.dit("Oui.", agent_avant="Vous êtes à Pont-Sainte-Maxence, dans l'Oise ?")
    r = await appel.note(commune="Pont-Sainte-Maxence (Oise)")
    assert appel.sure("commune") and appel.fiche["commune"] == "Pont-Sainte-Maxence", r


@pytest.mark.asyncio
async def test_C1_temoin_un_non_ne_confirme_rien():
    appel = await _sainte_maxence_proposee()
    appel.dit("Non, pas du tout.", agent_avant="Est-ce que vous êtes bien sur Pont-Sainte-Maxence ?")
    await appel.note(commune="Pont-Sainte-Maxence")
    assert not appel.sure("commune")


@pytest.mark.asyncio
async def test_C1_temoin_une_commune_hors_des_propositions_n_est_pas_confirmee_par_un_oui():
    appel = await _sainte_maxence_proposee()
    appel.dit("Oui, oui.", agent_avant="Est-ce que vous êtes bien sur Compiègne ?")
    await appel.note(commune="Compiègne")
    assert not appel.sure("commune")


# --- C2 : un code postal incompatible avec la commune devient « à confirmer » (Q2, Q3) ---

VERNEUIL = {
    "nom": "Verneuil-en-Halatte",
    "code_insee": "60670",
    "departement": "Oise",
    "codes_postaux": ["60550"],
}


def _verneuil_sure(appel: Appel, entendu: str = "vernay en malatte") -> None:
    """Le module des communes retient Verneuil-en-Halatte au tour courant (run 1018)."""
    appel.trace(
        "communes_verifiees",
        entendu=entendu,
        statut="sure",
        commune_retenue=VERNEUIL,
        propositions=[],
    )


def _code_a_proposer(resultat: dict) -> list:
    return [p for p in resultat.get("a_proposer") or [] if p["champ"] == "code_postal"]


async def _run_1018() -> tuple[Appel, dict]:
    """Run 1018 : « Vernay-en-Malatte, 65150 » dans la même note ; le module retient
    Verneuil-en-Halatte (60550). Le code dicté ne lui appartient pas."""
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL))
    appel.dit("Euh, je suis à Vernay-en-Malatte, 65150.")
    _verneuil_sure(appel)
    r = await appel.note(commune="Vernay-en-Malatte", code_postal="65150")
    return appel, r


@pytest.mark.asyncio
async def test_C2_run_1018_le_code_incompatible_devient_a_confirmer_avec_celui_de_la_commune():
    appel, r = await _run_1018()
    assert appel.fiche["commune"] == "Verneuil-en-Halatte" and appel.sure("commune"), r
    # Rien n'est écrasé sans demander : la valeur dite reste, marquée à confirmer.
    assert appel.fiche["code_postal"] == "65150" and not appel.sure("code_postal"), r
    assert [p["options"] for p in _code_a_proposer(r)] == [["60550"]], r


@pytest.mark.asyncio
async def test_C2_dans_l_autre_ordre_le_code_d_abord_puis_la_commune():
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL))
    appel.dit("C'est le 65150.")
    await appel.note(code_postal="65150")
    assert appel.sure("code_postal")
    appel.dit("À Vernay-en-Malatte.", agent_avant="Et c'est dans quelle commune ?")
    _verneuil_sure(appel)
    r = await appel.note(commune="Vernay-en-Malatte")
    assert appel.fiche["code_postal"] == "65150" and not appel.sure("code_postal"), r
    assert [p["options"] for p in _code_a_proposer(r)] == [["60550"]], r


@pytest.mark.asyncio
async def test_C2_un_oui_au_code_de_la_commune_l_ecrit():
    appel, _ = await _run_1018()
    appel.dit("Oui, c'est ça.", agent_avant="Le code postal, c'est bien le 60550 ?")
    r = await appel.note(code_postal="60550")
    assert appel.fiche["code_postal"] == "60550" and appel.sure("code_postal"), r


@pytest.mark.asyncio
async def test_C2_Q3_un_non_garde_la_valeur_dite_a_confirmer_sans_reposer_la_question():
    appel, _ = await _run_1018()
    appel.dit("Non, c'est bien le 65150.", agent_avant="Le code postal, c'est bien le 60550 ?")
    r = await appel.note(code_postal="65150")
    assert appel.fiche["code_postal"] == "65150" and not appel.sure("code_postal"), r
    assert not _code_a_proposer(r), r


@pytest.mark.asyncio
async def test_C2_temoin_un_code_compatible_ne_declenche_rien():
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL))
    appel.dit("Je suis à Verneuil-en-Halatte, 60550.")
    _verneuil_sure(appel, entendu="verneuil en halatte")
    r = await appel.note(commune="Verneuil-en-Halatte", code_postal="60550")
    assert appel.sure("code_postal") and not _code_a_proposer(r), r


@pytest.mark.asyncio
async def test_C2_temoin_une_commune_non_sure_ne_juge_pas_le_code():
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL))
    appel.dit("Je suis à Zorvexville, 65150.")
    r = await appel.note(commune="Zorvexville", code_postal="65150")
    assert not appel.sure("commune")
    assert not _code_a_proposer(r), r
