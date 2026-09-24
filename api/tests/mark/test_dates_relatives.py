"""[.mark] Les dates relatives dites par l'appelant (décision D46, correctif A5).

La question à laquelle ce fichier répond, et elle seule :

    Quand la personne dit « l'année dernière », la fiche reçoit-elle l'année
    calculée au jour de l'appel, avec ses mots gardés à côté -- sans qu'aucun
    autre nombre de l'appel ne devienne une date ?

Pourquoi : au run 837, le modèle note « 2025 », le contrôle de citation le
refuse (D38), et l'agent passe quatre tours à faire dire l'année. Les phrases
des cas sont celles des runs 831 à 837.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.schemas.fiche_agent import ChampFiche, lecteur_par_defaut, verifier_champs
from api.services.workflow.dates_relatives import lire_date, lire_expression
from api.services.workflow.fiche_au_fil_de_leau import (
    ReglagesFiche,
    balayer_la_fiche,
    creer_gestionnaire,
    ecrire_dans_la_fiche,
)

# Sans fuseau, comme `dateparser` le veut : le soir des runs 828 à 837.
JOUR = datetime(2026, 9, 24, 23, 25)  # noqa: DTZ001


def _reglages() -> ReglagesFiche:
    reglages = ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": [
                {"nom": "dernier_entretien", "origine": "dicte"},
                {"nom": "numero_dicte", "origine": "dicte"},
                {"nom": "verbatim_demande", "origine": "dicte"},
            ],
        }
    )
    assert reglages is not None
    return reglages


# --- Le calcul ---------------------------------------------------------------


@pytest.mark.parametrize(
    "texte, dit, date",
    [
        ("Il a eu lieu l'année dernière.", "l'année dernière", "2025"),  # 836
        ("C'était l'année dernière.", "l'année dernière", "2025"),  # 837
        ("l'an dernier", "l'an dernier", "2025"),
        ("l'année passée", "l'année passée", "2025"),
        ("ça fait deux ans", "ça fait deux ans", "2024"),
        ("il y a 2 ans", "il y a 2 ans", "2024"),
        ("il y a trois mois", "il y a trois mois", "06/2026"),
        ("Le mois dernier.", "Le mois dernier", "08/2026"),
        ("la semaine dernière", "la semaine dernière", "17/09/2026"),
        ("hier", "hier", "23/09/2026"),
        ("avant-hier", "avant-hier", "22/09/2026"),
        ("cette année", "cette année", "2026"),
        # 837 : la personne se reprend et dit l'année en toutes lettres.
        (
            "Non non, il a eu le l'année dernière donc en deux mille vingt cinq.",
            "l'année dernière",
            "2025",
        ),
    ],
)
def test_une_date_relative_est_calculee_au_jour_de_l_appel(texte, dit, date):
    assert lire_expression(texte, JOUR) == (dit, date)


@pytest.mark.parametrize(
    "texte",
    [
        # Ce que la recherche de `dateparser` prenait pour des dates (24/09).
        "Le zéro six douze trente quatre cinquante six soixante dix huit.",
        "Oui c'est un godin, il a deux ans.",  # l'âge de l'appareil
        "je suis là demain matin",
        "Alors j'habite au six rue Danton, à Ponce-Alpes-Maxence, soixante mille sept cents.",
        "Oui, les lunettes la dernière, oui.",  # 837, transcription ratée
        "Godin",
        "en mars dernier",  # hors de la liste : laissé tel quel, jamais deviné
    ],
)
def test_rien_d_autre_ne_devient_une_date(texte):
    assert lire_expression(texte, JOUR) is None


def test_2025_du_modele_est_retenu_si_la_personne_a_dit_l_annee_derniere():
    paroles = ["Bonjour", "C'était l'année dernière."]
    date = lire_date("2025", paroles, JOUR)
    assert (date.valeur, date.dit) == ("2025", "C'était l'année dernière.")
    # Une autre année, ou une date que ses mots ne donnent pas : rien.
    assert lire_date("2024", paroles, JOUR) is None
    assert lire_date("08/2026", paroles, JOUR) is None


# --- Le lecteur « date » (D42 étendu par D46) --------------------------------


@pytest.mark.parametrize(
    "nom, lecteur",
    [
        ("dernier_entretien", "date"),
        ("date_installation", "date"),
        ("annee_pose", "date"),
        ("verbatim_demande", "aucun"),
        ("numero_dicte", "aucun"),
    ],
)
def test_le_lecteur_date_est_deduit_du_nom(nom, lecteur):
    assert lecteur_par_defaut(nom) == lecteur


def test_un_champ_ne_peut_pas_s_appeler_comme_les_mots_d_une_date():
    with pytest.raises(ValueError, match="caller's words"):
        verifier_champs(
            [
                ChampFiche(nom="dernier_entretien"),
                ChampFiche(nom="dernier_entretien_dit"),
            ]
        )


# --- Par le point d'écriture unique ------------------------------------------


def test_A5_run_837_2025_ecrit_et_les_mots_gardes():
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche,
        _reglages(),
        "dernier_entretien",
        "2025",
        paroles=["C'était l'année dernière."],
        jour=JOUR,
    )
    assert verdict.statut == "ecrit"
    assert fiche["dernier_entretien"] == "2025"
    assert fiche["dernier_entretien_dit"] == "C'était l'année dernière."
    assert fiche["extracted_variables"]["dernier_entretien_dit"] == (
        "C'était l'année dernière."
    )
    assert fiche["fiche_journal"][-1]["dit"] == "C'était l'année dernière."


def test_l_annee_derniere_notee_telle_quelle_est_calculee():
    fiche: dict = {}
    ecrire_dans_la_fiche(
        fiche,
        _reglages(),
        "dernier_entretien",
        "l'année dernière",
        paroles=["Il a eu lieu l'année dernière."],
        jour=JOUR,
    )
    assert fiche["dernier_entretien"] == "2025"
    assert fiche["dernier_entretien_dit"] == "l'année dernière"


def test_une_annee_jamais_dite_reste_refusee():
    """D38 tient : « 2024 » quand la personne a dit « l'année dernière »."""
    fiche: dict = {}
    verdict = ecrire_dans_la_fiche(
        fiche,
        _reglages(),
        "dernier_entretien",
        "2024",
        paroles=["C'était l'année dernière."],
        jour=JOUR,
    )
    assert (verdict.statut, verdict.raison) == ("refuse", "non_dit")
    assert "dernier_entretien" not in fiche


def test_une_date_dite_telle_quelle_ne_garde_pas_les_mots_d_une_autre():
    fiche: dict = {}
    reglages = _reglages()
    ecrire_dans_la_fiche(
        fiche,
        reglages,
        "dernier_entretien",
        "2025",
        paroles=["C'était l'année dernière."],
        jour=JOUR,
    )
    ecrire_dans_la_fiche(
        fiche,
        reglages,
        "dernier_entretien",
        "2023",
        paroles=["C'était l'année dernière.", "non, en 2023"],
        jour=JOUR,
    )
    assert fiche["dernier_entretien"] == "2023"
    assert "dernier_entretien_dit" not in fiche


def test_hors_d_un_champ_de_date_rien_n_est_converti():
    """Le verbatim qui contient « hier » reste le verbatim."""
    fiche: dict = {}
    ecrire_dans_la_fiche(
        fiche,
        _reglages(),
        "verbatim_demande",
        "il fume depuis hier",
        paroles=["il fume depuis hier"],
        jour=JOUR,
    )
    assert fiche["verbatim_demande"] == "il fume depuis hier"
    assert "verbatim_demande_dit" not in fiche


@pytest.mark.asyncio
async def test_A5_par_l_outil_la_note_passe_sans_consigne_de_refus():
    fiche: dict = {}
    messages = [{"role": "user", "content": "C'était l'année dernière."}]
    resultats = []

    async def rappel(resultat, *, properties=None):
        resultats.append(resultat)

    gestionnaire = creer_gestionnaire(_reglages(), lambda: fiche, lambda: messages)
    with patch("api.services.workflow.dates_relatives.aujourd_hui", return_value=JOUR):
        await gestionnaire(
            SimpleNamespace(
                arguments={"dernier_entretien": "2025"},
                tool_call_id="n1",
                result_callback=rappel,
            )
        )
    (resultat,) = resultats
    assert resultat == {"statut": "note", "ecrits": ["dernier_entretien"]}
    assert fiche["dernier_entretien"] == "2025"


@pytest.mark.asyncio
async def test_le_balayage_calcule_aussi_et_garde_la_phrase():
    """Runs 828 à 836 : le balayage écrivait « il a eu lieu l'année dernière »."""
    fiche: dict = {}
    messages = [{"role": "user", "content": "Il a eu lieu l'année dernière."}]

    async def extraire(variables, consigne):
        return {"dernier_entretien": "il a eu lieu l'année dernière"}

    with patch("api.services.workflow.dates_relatives.aujourd_hui", return_value=JOUR):
        ecrits = await balayer_la_fiche(_reglages(), extraire, fiche, messages)
    assert ecrits == {"dernier_entretien": "2025"}
    assert fiche["dernier_entretien_dit"] == "il a eu lieu l'année dernière"
