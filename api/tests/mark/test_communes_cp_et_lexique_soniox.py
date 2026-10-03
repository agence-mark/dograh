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
from api.tests.mark.test_fiche_correctifs_modules import (
    Appel,
    _a_faire_confirmer,
    _reglages,
)

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
    appel.dit(
        "Oui, oui.", agent_avant="Est-ce que vous êtes bien sur Pont-Sainte-Maxence ?"
    )
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
    appel.dit(
        "Non, pas du tout.",
        agent_avant="Est-ce que vous êtes bien sur Pont-Sainte-Maxence ?",
    )
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


def _commune_a_proposer(resultat: dict) -> list:
    return [p for p in resultat.get("a_proposer") or [] if p["champ"] == "commune"]


@pytest.mark.asyncio
async def test_C2_run_1018_le_code_incompatible_et_la_commune_deviennent_a_confirmer():
    appel, r = await _run_1018()
    # Rien n'est écrasé sans demander : les valeurs restent, marquées à confirmer.
    assert appel.fiche["commune"] == "Verneuil-en-Halatte" and not appel.sure(
        "commune"
    ), r
    assert appel.fiche["code_postal"] == "65150" and not appel.sure("code_postal"), r
    assert [p["options"] for p in _code_a_proposer(r)] == [["60550"]], r
    # Décision du 02/10 : la commune aussi, avec les communes du code dit.
    options = [p["options"] for p in _commune_a_proposer(r)]
    assert options and options[0][0].endswith("(Hautes-Pyrénées)"), r


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
async def test_C2_un_oui_au_code_de_la_commune_l_ecrit_et_la_commune_redevient_sure():
    appel, _ = await _run_1018()
    appel.dit("Oui, c'est ça.", agent_avant="Le code postal, c'est bien le 60550 ?")
    r = await appel.note(code_postal="60550")
    assert appel.fiche["code_postal"] == "60550" and appel.sure("code_postal"), r
    assert appel.fiche["commune"] == "Verneuil-en-Halatte" and appel.sure("commune"), r


@pytest.mark.asyncio
async def test_C2_Q3_un_non_garde_la_valeur_dite_a_confirmer_sans_reposer_la_question():
    appel, _ = await _run_1018()
    appel.dit(
        "Non, c'est bien le 65150.", agent_avant="Le code postal, c'est bien le 60550 ?"
    )
    r = await appel.note(code_postal="65150")
    assert appel.fiche["code_postal"] == "65150" and not appel.sure("code_postal"), r
    assert not _code_a_proposer(r) and not _commune_a_proposer(r), r


# Run 967 : « vernayon à la » ; le module retient Vernon (Eure), FAUX ; le code dit,
# 60550, est JUSTE. C'est la commune qu'il faut faire confirmer.
VERNON = {
    "nom": "Vernon",
    "code_insee": "27681",
    "departement": "Eure",
    "codes_postaux": ["27200"],
}


async def _run_967() -> tuple[Appel, dict]:
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL))
    # Le code est écrit en chiffres comme le module des nombres le rend au modèle.
    appel.dit("Je suis au 26 rue des Hauts-de-France, 60550, vernayon à la")
    appel.trace("nombres_lus", type="code_postal", retenu="60550")
    appel.trace(
        "communes_verifiees",
        entendu="vernayon a la",
        statut="sure",
        commune_retenue=VERNON,
        propositions=[],
    )
    r = await appel.note(commune="Vernon", code_postal="60550")
    return appel, r


@pytest.mark.asyncio
async def test_C2_run_967_la_commune_fausse_est_proposee_avec_celle_du_code_dit():
    appel, r = await _run_967()
    assert not appel.sure("commune") and not appel.sure("code_postal"), r
    assert [p["options"] for p in _commune_a_proposer(r)] == [
        ["Verneuil-en-Halatte (Oise)"]
    ], r
    assert [p["options"] for p in _code_a_proposer(r)] == [["27200"]], r


@pytest.mark.asyncio
async def test_C2_run_967_un_oui_a_la_commune_du_code_rend_les_deux_surs():
    appel, _ = await _run_967()
    appel.dit(
        "Oui, Verneuil-en-Halatte.",
        agent_avant="Vous êtes bien à Verneuil-en-Halatte, dans l'Oise ?",
    )
    r = await appel.note(commune="Verneuil-en-Halatte")
    assert appel.fiche["commune"] == "Verneuil-en-Halatte" and appel.sure("commune"), r
    assert appel.fiche["code_postal"] == "60550" and appel.sure("code_postal"), r


@pytest.mark.asyncio
async def test_C2_temoin_un_code_sans_commune_ne_met_pas_la_commune_en_doute():
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL))
    appel.dit("Je suis à Vernay-en-Malatte, 00000.")
    _verneuil_sure(appel)
    r = await appel.note(commune="Vernay-en-Malatte", code_postal="00000")
    assert appel.sure("commune") and not appel.sure("code_postal"), r
    assert not _commune_a_proposer(r), r


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


# --- Relecture indépendante du 03/10 : deux parcours qui faisaient défaut ---

CREIL = {
    "nom": "Creil",
    "code_insee": "60175",
    "departement": "Oise",
    "codes_postaux": ["60100"],
}
SAINT_MAUR = {
    "nom": "Saint-Maur-des-Fossés",
    "code_insee": "94068",
    "departement": "Val-de-Marne",
    "codes_postaux": ["94100", "94210"],
}


@pytest.mark.asyncio
async def test_C2_une_adresse_corrigee_en_une_phrase_ne_repropose_pas_l_ancienne():
    """Commune et code changés dans la même note : la paire passe incohérente le temps
    d'écrire l'un, puis redevient cohérente. Rien ne doit être proposé (relecture 03/10)."""
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL))
    appel.dit("Je suis à Verneuil-en-Halatte, 60550.")
    _verneuil_sure(appel, entendu="verneuil en halatte")
    await appel.note(commune="Verneuil-en-Halatte", code_postal="60550")
    appel.dit("Non pardon, je suis à Creil, 60100.")
    appel.trace(
        "communes_verifiees",
        entendu="creil",
        statut="sure",
        commune_retenue=CREIL,
        propositions=[],
    )
    r = await appel.note(commune="Creil", code_postal="60100")
    assert appel.sure("commune") and appel.sure("code_postal"), r
    assert not _commune_a_proposer(r) and not _code_a_proposer(r), r


async def _saint_maur_et_65150() -> Appel:
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL))
    appel.dit("Je suis à Saint-Maur-des-Fossés, 65150.")
    appel.trace(
        "communes_verifiees",
        entendu="saint maur des fosses",
        statut="sure",
        commune_retenue=SAINT_MAUR,
        propositions=[],
    )
    await appel.note(commune="Saint-Maur-des-Fossés", code_postal="65150")
    assert not appel.sure("commune") and not appel.sure("code_postal")
    return appel


@pytest.mark.asyncio
async def test_C2_un_oui_a_la_commune_la_rend_sure_et_repropose_ses_codes():
    """Commune à plusieurs codes : le oui de la personne tient, et seul le code reste à
    confirmer, avec les codes de la commune reproposés (relecture 03/10)."""
    appel = await _saint_maur_et_65150()
    appel.dit(
        "Oui, Saint-Maur-des-Fossés.",
        agent_avant="Vous êtes bien à Saint-Maur-des-Fossés ?",
    )
    r = await appel.note(commune="Saint-Maur-des-Fossés")
    assert appel.sure("commune"), r
    assert appel.fiche["code_postal"] == "65150" and not appel.sure("code_postal"), r
    assert [p["options"] for p in _code_a_proposer(r)] == [["94100", "94210"]], r
    assert not _commune_a_proposer(r), r


@pytest.mark.asyncio
async def test_C2_apres_le_oui_a_la_commune_un_oui_au_code_rend_tout_sur():
    appel = await _saint_maur_et_65150()
    appel.dit(
        "Oui, Saint-Maur-des-Fossés.",
        agent_avant="Vous êtes bien à Saint-Maur-des-Fossés ?",
    )
    await appel.note(commune="Saint-Maur-des-Fossés")
    appel.dit(
        "Oui, le 94100.", agent_avant="Le code postal, c'est le 94100 ou le 94210 ?"
    )
    r = await appel.note(code_postal="94100")
    assert appel.sure("commune") and appel.sure("code_postal"), r
    assert appel.fiche["code_postal"] == "94100", r


ADRESSE = {"nom": "adresse_intervention", "origine": "dicte"}
LIANCOURT = {
    "nom": "Liancourt",
    "code_insee": "60360",
    "departement": "Oise",
    "codes_postaux": ["60140"],
}


@pytest.mark.asyncio
async def test_C2_la_commune_redevenue_sure_fait_relire_la_rue():
    """Un oui au code rend la commune sûre par le contrôle de cohérence, sans qu'elle
    soit écrite : la rue notée pendant le conflit est relue quand même (relecture 03/10)."""
    charger_base()
    appel = Appel(_reglages(COMMUNE, CODE_POSTAL, ADRESSE))
    appel.dit("Je suis à Liancourt, 65150.")
    appel.trace(
        "communes_verifiees",
        entendu="liancourt",
        statut="sure",
        commune_retenue=LIANCOURT,
        propositions=[],
    )
    await appel.note(commune="Liancourt", code_postal="65150")
    assert not appel.sure("commune")
    appel.dit("Au 12 rue Pasteur.", agent_avant="Et l'adresse ?")
    await appel.note(adresse_intervention="12 rue Pasteur")
    assert not appel.sure("adresse_intervention")
    appel.dit("Oui, le 60140.", agent_avant="Le code postal, c'est bien le 60140 ?")
    r = await appel.note(code_postal="60140")
    assert appel.sure("commune") and appel.sure("code_postal"), r
    assert (
        appel.sure("adresse_intervention")
        and appel.fiche["adresse_intervention"] == "12 Rue Pasteur"
    ), (
        r,
        appel.fiche,
    )
