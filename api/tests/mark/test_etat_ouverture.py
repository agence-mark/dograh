"""[.mark] Non-regression test for the opening state computed at call start.

The question this file answers, and only this one:

    From opening hours typed in the readable format, is the state of the shop
    (OUVERT, PAUSE, FERME, SUR_RENDEZ_VOUS) and the spoken reopening exactly
    right -- and does an agent WITHOUT hours get the context it had before?

Why it exists
-------------
Measured on 2026-09-15, runs 242 to 246: ``etat_ouverture`` and
``reouverture`` were absent from the call context, so the agent read "the state
of the shop is given to you: ." -- an empty value. Nothing computed it.

⛔ Every test fixes the instant. None reads the real clock: a test that passes
on a Tuesday morning and fails on a Sunday is not a test.

⚠️ What this file does NOT prove: that the pipeline CALLS the injection. That
is ``test_etat_ouverture_branchement.py``.
"""

from datetime import date, datetime, timedelta

import pytest
from opening_hours import OpeningHours

from api.services.pipecat.etat_ouverture import (
    ETATS,
    FERME,
    OUVERT,
    PARIS,
    PAUSE,
    SUR_RENDEZ_VOUS,
    HorairesInvalides,
    calculer_etat,
    injecter_etat_ouverture,
    phrase_annonce,
    rafraichir_annonce,
    vers_expression_osm,
)

# The example of the plan (D2), verbatim.
EXEMPLE_D2 = """lundi : 10:00-18:30 sur rendez-vous
mardi : 10:00-12:30 et 14:00-18:30
mercredi : 10h-12h30, 14h-18h30
jeudi : 10:00-12:30 et 14:00-18:30
vendredi : 10:00-12:30 et 14:00-19:00
samedi : 10:00-19:00
dimanche : fermé
jours fériés : fermé
exceptions :
du 17/08/2026 au 22/08/2026 : fermé (congés d'été)
24/12/2026 : 10:00-16:00 (horaires réduits)
25/12 : fermé
"""

EXPRESSION_D2 = (
    'Mo 10:00-18:30 "sur rendez-vous"; '
    "Tu 10:00-12:30,14:00-18:30; "
    "We 10:00-12:30,14:00-18:30; "
    "Th 10:00-12:30,14:00-18:30; "
    "Fr 10:00-12:30,14:00-19:00; "
    "Sa 10:00-19:00; "
    "Su off; "
    "PH off; "
    "2026 Aug 17-2026 Aug 22 off \"congés d'été\"; "
    '2026 Dec 24 10:00-16:00 "horaires réduits"; '
    "Dec 25 off"
)

SEPT_JOURS_FERMES = "\n".join(
    f"{jour} : fermé"
    for jour in ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
)


def _a(quand: str) -> datetime:
    return datetime.fromisoformat(quand).replace(tzinfo=PARIS)


def _etat(texte: str, quand: str) -> tuple[str, str]:
    return calculer_etat(vers_expression_osm(texte), _a(quand))


# --------------------------------------------------------------------------- #
# 1. The 17 situations of the trial of 2026-09-15, state AND sentence
# --------------------------------------------------------------------------- #

SITUATIONS = [
    ("mardi matin, ouvert", "2026-09-15 11:00", OUVERT, ""),
    ("mardi 13 h, pause déjeuner", "2026-09-15 13:00", PAUSE, "aujourd'hui à 14 heures"),
    ("mardi 12:30 pile", "2026-09-15 12:30", PAUSE, "aujourd'hui à 14 heures"),
    ("mardi 18:45, fermé le soir", "2026-09-15 18:45", FERME, "demain à 10 heures"),
    ("mardi 8 h, pas encore ouvert", "2026-09-15 08:00", FERME, "aujourd'hui à 10 heures"),
    ("lundi 14 h, sur rendez-vous", "2026-09-14 14:00", SUR_RENDEZ_VOUS, ""),
    ("vendredi 18:45, ouvert jusqu'à 19 h", "2026-09-18 18:45", OUVERT, ""),
    ("samedi 19:30", "2026-09-19 19:30", FERME, "lundi à 10 heures, sur rendez-vous"),
    ("dimanche midi", "2026-09-20 12:00", FERME, "demain à 10 heures, sur rendez-vous"),
    ("11 novembre 2026", "2026-11-11 11:00", FERME, "demain à 10 heures"),
    ("25 décembre 2026", "2026-12-25 11:00", FERME, "demain à 10 heures"),
    ("24 décembre, horaires réduits, 15 h", "2026-12-24 15:00", OUVERT, ""),
    ("24 décembre, 17 h", "2026-12-24 17:00", FERME, "samedi à 10 heures"),
    ("congés d'été, 19 août", "2026-08-19 11:00", FERME, "lundi à 10 heures, sur rendez-vous"),
    (
        "15 août 2026, samedi férié, puis congés",
        "2026-08-15 11:00",
        FERME,
        "lundi 24 août à 10 heures, sur rendez-vous",
    ),
    (
        "changement d'heure, dimanche 25 octobre",
        "2026-10-25 12:00",
        FERME,
        "demain à 10 heures, sur rendez-vous",
    ),
    ("lundi de Pâques 2026", "2026-04-06 11:00", FERME, "demain à 10 heures"),
]


@pytest.mark.parametrize("_libelle,quand,etat,phrase", SITUATIONS, ids=[s[0] for s in SITUATIONS])
def test_les_17_situations_de_lepreuve(_libelle, quand, etat, phrase):
    assert _etat(EXEMPLE_D2, quand) == (etat, phrase)


# --------------------------------------------------------------------------- #
# 2. Translation
# --------------------------------------------------------------------------- #


def test_lexemple_du_plan_donne_lexpression_attendue():
    assert vers_expression_osm(EXEMPLE_D2) == EXPRESSION_D2


@pytest.mark.parametrize(
    "ecriture",
    [
        "10:00-12:30 et 14:00-18:30",
        "10h-12h30, 14h-18h30",
        "10h00-12h30 et 14h-18h30",
        "10:00-12:30,14:00-18:30",
    ],
)
def test_les_ecritures_dune_heure_sont_equivalentes(ecriture):
    texte = SEPT_JOURS_FERMES.replace("mardi : fermé", f"mardi : {ecriture}")
    assert "Tu 10:00-12:30,14:00-18:30" in vers_expression_osm(texte)


def test_casse_et_accents_ignores():
    texte = SEPT_JOURS_FERMES.replace("mardi : fermé", "MARDI : Ferme").replace(
        "dimanche : fermé", "Dimanche : FERMÉE"
    )
    expression = vers_expression_osm(texte + "\nJOURS FERIES : fermé")
    assert "Tu off" in expression and "Su off" in expression and "PH off" in expression


def test_9h05_est_accepte():
    texte = SEPT_JOURS_FERMES.replace("lundi : fermé", "lundi : 9:05-12:00")
    assert _etat(texte, "2026-09-14 08:00") == (FERME, "aujourd'hui à 9 heures 05")


# --------------------------------------------------------------------------- #
# 3 and 4. Refusals, with the line number
# --------------------------------------------------------------------------- #

SAISIES_FAUTIVES = [
    "lundi 10:00-18:30",
    "lundi : 10:00-25:00",
    "lundi : 10:00\nmardi : fermé",
    "lundi : fermé\nmardi : fermé",
    "31/02/2026 : fermé",
    "noel : fermé",
]


@pytest.mark.parametrize("saisie", SAISIES_FAUTIVES)
def test_les_6_saisies_fautives_du_prototype_sont_refusees(saisie):
    with pytest.raises(HorairesInvalides, match="ligne"):
        vers_expression_osm(saisie)


def test_le_numero_de_ligne_est_le_bon():
    texte = SEPT_JOURS_FERMES + "\nexceptions :\n24/12/2026 : 10:00-16:61"
    with pytest.raises(HorairesInvalides, match=r"^ligne 9 : "):
        vers_expression_osm(texte)


@pytest.mark.parametrize("fautive", ["24:30", "10:60"])
def test_heure_au_dela_de_24_ou_minutes_au_dela_de_59_refusees(fautive):
    texte = SEPT_JOURS_FERMES.replace("lundi : fermé", f"lundi : 10:00-{fautive}")
    with pytest.raises(HorairesInvalides, match="ligne 1 : heure impossible"):
        vers_expression_osm(texte)


def test_les_jours_sans_ligne_sont_nommes():
    with pytest.raises(HorairesInvalides) as erreur:
        vers_expression_osm("lundi : fermé\nmardi : fermé\njeudi : fermé")
    message = str(erreur.value)
    for jour in ("mercredi", "vendredi", "samedi", "dimanche"):
        assert jour in message
    assert "lundi" not in message and "jeudi" not in message


def test_ligne_jours_feries_absente_veut_dire_feries_fermes():
    """Rule 5. ⛔ The prototype left holidays OPEN when the line was missing."""
    ouvert_tous_les_jours = "\n".join(
        f"{jour} : 10:00-18:00"
        for jour in ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    )
    assert "PH off" in vers_expression_osm(ouvert_tous_les_jours)
    assert _etat(ouvert_tous_les_jours, "2026-11-11 11:00")[0] == FERME
    # And the other direction: "ouvert" really lets the weekday rule apply.
    assert _etat(ouvert_tous_les_jours + "\njours fériés : ouvert", "2026-11-11 11:00")[0] == OUVERT


def test_lignes_vides_et_commentaires_ignores():
    texte = "# horaires du magasin\n\n" + SEPT_JOURS_FERMES + "\n\n# fin"
    assert vers_expression_osm(texte).startswith("Mo off; Tu off")


@pytest.mark.parametrize("fautive", ["ouverte le matin", "ouvert n'importe quoi"])
def test_jours_feries_ouvert_est_strict(fautive):
    """Review of 2026-09-15: « ouvert le matin seulement » was read as open all day."""
    with pytest.raises(HorairesInvalides, match="ligne 8"):
        vers_expression_osm(SEPT_JOURS_FERMES + f"\njours fériés : {fautive}")
    assert "PH" not in vers_expression_osm(SEPT_JOURS_FERMES + "\njours fériés : Ouverte")


@pytest.mark.parametrize("plage", ["22:00-02:00", "12:00-12:00"])
def test_une_plage_dont_la_fin_precede_le_debut_est_refusee(plage):
    """Review of 2026-09-15: a range past midnight was cut at midnight in silence."""
    texte = SEPT_JOURS_FERMES.replace("vendredi : fermé", f"vendredi : {plage}")
    with pytest.raises(HorairesInvalides, match="ligne 5 : la fin précède le début"):
        vers_expression_osm(texte)


def test_une_plage_jusqua_24h_est_acceptee():
    texte = SEPT_JOURS_FERMES.replace("vendredi : fermé", "vendredi : 22:00-24:00")
    assert _etat(texte, "2026-09-18 23:00") == (OUVERT, "")


# --------------------------------------------------------------------------- #
# 5. Priority (rule 7)
# --------------------------------------------------------------------------- #


def test_une_exception_sur_un_jour_ferie_lemporte():
    texte = EXEMPLE_D2 + "11/11/2026 : 10:00-12:00\n"
    assert _etat(texte, "2026-11-11 11:00") == (OUVERT, "")


def test_entre_deux_exceptions_recouvrantes_la_derniere_gagne():
    base = SEPT_JOURS_FERMES + "\nexceptions :\n"
    ouvre_puis_ferme = base + "du 01/10/2026 au 10/10/2026 : 10:00-18:00\n05/10/2026 : fermé"
    ferme_puis_ouvre = base + "05/10/2026 : fermé\ndu 01/10/2026 au 10/10/2026 : 10:00-18:00"
    assert _etat(ouvre_puis_ferme, "2026-10-05 11:00")[0] == FERME
    assert _etat(ferme_puis_ouvre, "2026-10-05 11:00")[0] == OUVERT


def test_une_exception_lemporte_sur_le_jour_de_la_semaine():
    assert _etat(EXEMPLE_D2, "2026-12-24 17:00")[0] == FERME  # a Thursday, normally open till 18:30


# --------------------------------------------------------------------------- #
# 6. PAUSE only when the shop reopens the same day
# --------------------------------------------------------------------------- #


def test_pause_seulement_si_reouverture_le_meme_jour():
    une_seule_plage = SEPT_JOURS_FERMES.replace("mardi : fermé", "mardi : 10:00-12:30")
    assert _etat(une_seule_plage, "2026-09-15 13:00") == (FERME, "mardi 22 septembre à 10 heures")


def test_1230_pile_est_une_pause():
    assert _etat(EXEMPLE_D2, "2026-09-15 12:30")[0] == PAUSE


def test_avant_la_premiere_ouverture_ce_nest_pas_une_pause():
    assert _etat(EXEMPLE_D2, "2026-09-15 08:00")[0] == FERME


# --------------------------------------------------------------------------- #
# 7. The sentence
# --------------------------------------------------------------------------- #


def test_suffixe_sur_rendez_vous():
    assert _etat(EXEMPLE_D2, "2026-09-20 12:00")[1].endswith(", sur rendez-vous")


def test_minuit():
    texte = SEPT_JOURS_FERMES.replace("mercredi : fermé", "mercredi : 00:00-02:00")
    assert _etat(texte, "2026-09-15 20:00") == (FERME, "demain à minuit")


@pytest.mark.parametrize(
    "ouverture,phrase",
    [("00:30-02:00", "demain à minuit 30"), ("00:05-02:00", "demain à minuit 05"), ("01:00-02:00", "demain à 1 heure")],
)
def test_minuit_et_des_minutes(ouverture, phrase):
    """Evan, 2026-09-15: « minuit 30 », not « 0 heure 30 »."""
    texte = SEPT_JOURS_FERMES.replace("mercredi : fermé", f"mercredi : {ouverture}")
    assert _etat(texte, "2026-09-15 20:00") == (FERME, phrase)


def test_au_dela_de_7_jours_le_quantieme_et_le_mois_accentue():
    texte = SEPT_JOURS_FERMES + "\nexceptions :\n24/08/2026 : 10:00-12:00"
    assert _etat(texte, "2026-08-10 11:00") == (FERME, "lundi 24 août à 10 heures")


def test_a_6_jours_le_jour_seul():
    texte = SEPT_JOURS_FERMES.replace("lundi : fermé", "lundi : 10:00-12:00")
    assert _etat(texte, "2026-09-15 11:00") == (FERME, "lundi à 10 heures")


def test_ouvert_et_sur_rendez_vous_nont_pas_de_reouverture():
    assert _etat(EXEMPLE_D2, "2026-09-15 11:00")[1] == ""
    assert _etat(EXEMPLE_D2, "2026-09-14 11:00")[1] == ""


# --------------------------------------------------------------------------- #
# 8. No opening within 60 days
# --------------------------------------------------------------------------- #


def test_aucune_ouverture_sous_60_jours():
    assert _etat(SEPT_JOURS_FERMES, "2026-09-15 11:00") == (FERME, "")


@pytest.mark.parametrize("quand", ["2026-01-28 02:30", "2026-01-28 02:00", "2026-08-26 02:30"])
def test_lhorizon_ne_tombe_pas_dans_lheure_qui_nexiste_pas(quand):
    """⛔ Review of 2026-09-15: 28 January 02:30 + 60 days in local time is
    29 March 02:30, skipped by the switch to summer time. The library raised
    and, through the injection, the call got no state -- one night a year.
    (26 August 02:30 + 60 days: 25 October 02:30, the hour that happens twice.)"""
    assert _etat(EXEMPLE_D2, quand) == (FERME, "aujourd'hui à 10 heures")


def test_ouverture_a_61_jours_ignoree_a_59_jours_trouvee():
    loin = SEPT_JOURS_FERMES + "\nexceptions :\n15/11/2026 : 10:00-12:00"
    assert _etat(loin, "2026-09-15 11:00") == (FERME, "")  # 61 days
    assert _etat(loin, "2026-09-17 11:00")[1] == "dimanche 15 novembre à 10 heures"  # 59 days


# --------------------------------------------------------------------------- #
# 9 to 11. Injection into the call context
# --------------------------------------------------------------------------- #

MARDI_11H = _a("2026-09-15 11:00")
MARDI_13H = _a("2026-09-15 13:00")


@pytest.mark.parametrize("configs", [{}, {"horaires_ouverture": None}, {"horaires_ouverture": "  "}, None])
def test_sans_horaires_le_contexte_est_identique(configs):
    """D6. 🔒 Every existing agent: the context it had before this patch."""
    contexte = {"direction": "inbound", "runtime_configuration": {"llm_model": "x"}}
    copie = {"direction": "inbound", "runtime_configuration": {"llm_model": "x"}}
    resultat = injecter_etat_ouverture(contexte, configs, maintenant=MARDI_11H)
    assert resultat == copie
    assert set(resultat) == set(copie)


def test_avec_horaires_les_quatre_variables_sont_injectees():
    """The fourth, ``annonce_ouverture``, arrived with the chantier
    corrections-appels-agent-6 (2026-09-18): see section 14 below."""
    resultat = injecter_etat_ouverture(
        {"direction": "inbound"}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_13H
    )
    assert resultat == {
        "direction": "inbound",
        "etat_ouverture": PAUSE,
        "reouverture": "aujourd'hui à 14 heures",
        "horaires_ouverture": EXEMPLE_D2,
        "annonce_ouverture": "Nous sommes fermés pour le moment, nous rouvrons aujourd'hui à 14 heures. ",
    }


def test_lentree_nest_pas_modifiee_en_place():
    contexte = {"direction": "inbound"}
    injecter_etat_ouverture(contexte, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_11H)
    assert contexte == {"direction": "inbound"}


def test_une_valeur_fournie_gagne():
    """D7. A keyboard replay that injects FERME on a Tuesday at 11 keeps FERME."""
    resultat = injecter_etat_ouverture(
        {"etat_ouverture": FERME, "reouverture": "lundi à 10 heures"},
        {"horaires_ouverture": EXEMPLE_D2},
        maintenant=MARDI_11H,
    )
    assert resultat["etat_ouverture"] == FERME
    assert resultat["reouverture"] == "lundi à 10 heures"
    assert resultat["horaires_ouverture"] == EXEMPLE_D2


@pytest.mark.parametrize("vide", ["", "   ", None])
def test_une_cle_fournie_vide_est_calculee(vide):
    resultat = injecter_etat_ouverture(
        {"etat_ouverture": vide}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_11H
    )
    assert resultat["etat_ouverture"] == OUVERT


def test_horaires_invalides_arrives_jusqua_lappel():
    """D9. Written by hand or through MCP, past the settings screen: logged,
    nothing injected, no exception -- the call goes on."""
    contexte = {"direction": "inbound"}
    resultat = injecter_etat_ouverture(
        contexte, {"horaires_ouverture": "lundi 10:00-18:30"}, maintenant=MARDI_11H
    )
    assert resultat == {"direction": "inbound"}


def test_sans_instant_fourni_lheure_courante_est_utilisee():
    resultat = injecter_etat_ouverture({}, {"horaires_ouverture": EXEMPLE_D2})
    assert resultat["etat_ouverture"] in ETATS


# --------------------------------------------------------------------------- #
# 12. Public holidays 2027 to 2030
# --------------------------------------------------------------------------- #

FERIES = {
    2027: "01/01 29/03 01/05 06/05 08/05 17/05 14/07 15/08 01/11 11/11 25/12",
    2028: "01/01 17/04 01/05 08/05 25/05 05/06 14/07 15/08 01/11 11/11 25/12",
    2029: "01/01 02/04 01/05 08/05 10/05 21/05 14/07 15/08 01/11 11/11 25/12",
    2030: "01/01 22/04 01/05 08/05 30/05 10/06 14/07 15/08 01/11 11/11 25/12",
}


@pytest.mark.parametrize("annee", sorted(FERIES))
def test_les_11_jours_feries_de_lannee(annee):
    ouvert_tous_les_jours = "\n".join(
        f"{jour} : 10:00-11:00"
        for jour in ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    )
    horaires = OpeningHours(vers_expression_osm(ouvert_tous_les_jours), timezone=PARIS, country="FR")
    fermes = []
    jour = date(annee, 1, 1)
    while jour.year == annee:
        if not horaires.is_open(datetime(annee, jour.month, jour.day, 10, 30, tzinfo=PARIS)):
            fermes.append(f"{jour.day:02d}/{jour.month:02d}")
        jour += timedelta(days=1)
    assert " ".join(fermes) == FERIES[annee]
    assert len(fermes) == 11


# --------------------------------------------------------------------------- #
# 13. Counting: every instant of a typical week has exactly one state
# --------------------------------------------------------------------------- #


def test_chaque_instant_dune_semaine_a_exactement_un_etat():
    """⛔ Asserted both ways and counted: a state outside the four, or an open
    instant reported closed, or the reverse, fails here."""
    expression = vers_expression_osm(EXEMPLE_D2)
    horaires = OpeningHours(expression, timezone=PARIS, country="FR")
    debut = _a("2026-09-14 00:00")
    comptes = dict.fromkeys(ETATS, 0)
    instants = 0
    t = debut
    while t < debut + timedelta(days=7):
        etat, phrase = calculer_etat(expression, t)
        assert etat in ETATS
        comptes[etat] += 1
        instants += 1
        # Direct: open in the library -> OUVERT or SUR_RENDEZ_VOUS, no sentence.
        # Inverse: OUVERT or SUR_RENDEZ_VOUS -> open in the library.
        assert horaires.is_open(t) == (etat in (OUVERT, SUR_RENDEZ_VOUS)), t
        assert (phrase == "") == (etat in (OUVERT, SUR_RENDEZ_VOUS)), t
        t += timedelta(minutes=15)
    assert instants == 7 * 24 * 4
    assert sum(comptes.values()) == instants
    assert all(comptes[etat] > 0 for etat in ETATS), comptes


# --------------------------------------------------------------------------- #
# 14. The sentence the recorded greeting says (chantier corrections, 2026-09-18)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("etat", [OUVERT, SUR_RENDEZ_VOUS])
def test_rien_a_annoncer_quand_le_magasin_est_joignable(etat):
    """🔒 An open shop keeps the greeting it has always said, to the character."""
    assert phrase_annonce(etat, "aujourd'hui à 14 heures") == ""


def test_ferme_annonce_la_fermeture_et_la_reouverture():
    phrase = phrase_annonce(FERME, "demain à 10 heures")
    assert phrase == "Nous sommes fermés en ce moment, nous rouvrons demain à 10 heures. "


def test_pause_annonce_une_fermeture_du_moment():
    """⚠️ PAUSE means « already open today and reopening today », NOT lunch: at
    14:30 on a 9-12 / 15-18 week, « pause déjeuner » would be false. And this
    fork says nothing specific to one client, so no « magasin » either."""
    assert phrase_annonce(PAUSE, "aujourd'hui à 14 heures") == (
        "Nous sommes fermés pour le moment, nous rouvrons aujourd'hui à 14 heures. "
    )


def test_aucun_mot_propre_a_un_client_dans_les_phrases():
    """🔒 Review of 2026-09-18: this fork carries nothing specific to one client."""
    for etat in (FERME, PAUSE):
        phrase = phrase_annonce(etat, "demain à 10 heures").lower()
        assert "magasin" not in phrase and "déjeuner" not in phrase, phrase


@pytest.mark.parametrize("etat", [FERME, PAUSE])
def test_sans_reouverture_la_phrase_sarrete_apres_letat(etat):
    """D11: no opening within 60 days -> an empty reopening. The sentence must
    not say « il rouvre . »"""
    phrase = phrase_annonce(etat, "")
    assert phrase.endswith(". ") and "il rouvre" not in phrase


@pytest.mark.parametrize("etat", [FERME, PAUSE])
def test_la_phrase_finit_par_une_espace_pour_le_message_daccueil(etat):
    """The greeting is written « ... du magasin. {{annonce_ouverture}}Qu'est-ce ... »:
    without the trailing space the announcement would stick to the next sentence."""
    assert phrase_annonce(etat, "demain à 10 heures").endswith(". ")


def test_lannonce_est_injectee_avec_les_autres_variables():
    resultat = injecter_etat_ouverture(
        {"direction": "inbound"}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_13H
    )
    assert resultat["annonce_ouverture"] == (
        "Nous sommes fermés pour le moment, nous rouvrons aujourd'hui à 14 heures. "
    )


def test_lannonce_suit_letat_force_par_un_rejeu_au_clavier():
    """D7 applies to the state; the sentence must follow the state KEPT, not the
    computed one. A keyboard replay forcing FERME on a Tuesday at 11 announces
    a closed shop, otherwise the scenarios of the bench prove nothing."""
    resultat = injecter_etat_ouverture(
        {"etat_ouverture": FERME, "reouverture": "lundi à 10 heures"},
        {"horaires_ouverture": EXEMPLE_D2},
        maintenant=MARDI_11H,
    )
    assert resultat["annonce_ouverture"] == (
        "Nous sommes fermés en ce moment, nous rouvrons lundi à 10 heures. "
    )


@pytest.mark.parametrize("configs", [{}, {"horaires_ouverture": None}, None])
def test_sans_horaires_aucune_annonce_nest_ajoutee(configs):
    """🔒 D6: an agent without opening hours gets the context it had before."""
    resultat = injecter_etat_ouverture({"direction": "inbound"}, configs, maintenant=MARDI_11H)
    assert "annonce_ouverture" not in resultat


def test_une_variable_absente_du_contexte_ne_se_prononce_pas():
    """The greeting of an agent without hours must not speak the placeholder."""
    from api.utils.template_renderer import render_template

    accueil = (
        "Nuances de Feu bonjour. {{initial_context.annonce_ouverture}}"
        "Qu'est-ce que je peux faire pour vous ?"
    )
    assert render_template(accueil, {"direction": "inbound"}) == (
        "Nuances de Feu bonjour. Qu'est-ce que je peux faire pour vous ?"
    )
    ferme = render_template(accueil, injecter_etat_ouverture(
        {"etat_ouverture": FERME, "reouverture": "demain à 10 heures"},
        {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_11H,
    ))
    assert ferme == (
        "Nuances de Feu bonjour. Nous sommes fermés en ce moment, nous rouvrons demain à 10 heures. "
        "Qu'est-ce que je peux faire pour vous ?"
    )


def test_chaque_etat_connu_annonce_ou_se_tait_dans_les_deux_sens():
    """⛔ Asserted both ways and counted (review of 2026-09-18, Mineur 4):
    the direct sense alone would let a future state fall silent unnoticed."""
    from api.services.pipecat.etat_ouverture import ETATS as tous

    muets, parlants = 0, 0
    for etat in tous:
        phrase = phrase_annonce(etat, "demain à 10 heures")
        # Direct: closed -> a sentence. Inverse: a sentence -> closed.
        assert (phrase != "") == (etat in (FERME, PAUSE)), etat
        assert (phrase == "") == (etat in (OUVERT, SUR_RENDEZ_VOUS)), etat
        muets += phrase == ""
        parlants += phrase != ""
    assert muets + parlants == len(tous) == 4
    assert muets == 2 and parlants == 2


@pytest.mark.parametrize("inconnu", ["ferme", "FERME ", "Fermé", "", "CLOSED"])
def test_un_etat_inconnu_ne_dit_rien_mais_le_dit_dans_les_journaux(inconnu):
    """A state written by hand reads as closed in the prompt while the greeting
    announces nothing. Silent until the review of 2026-09-18 -- so the warning is
    ASSERTED here: without it, removing the log would leave this test green and
    the defect silent again. ``caplog`` is not used: loguru does not feed it
    without explicit wiring, so a sink of our own collects the messages."""
    from loguru import logger

    recus: list[str] = []
    jeton = logger.add(lambda message: recus.append(str(message)), level="WARNING")
    try:
        assert phrase_annonce(inconnu, "demain à 10 heures") == ""
    finally:
        logger.remove(jeton)
    assert any("unknown state" in ligne for ligne in recus), recus


def test_un_etat_connu_najoute_aucun_avertissement():
    """⛔ The inverse sense: a normal call must not log anything."""
    from loguru import logger

    recus: list[str] = []
    jeton = logger.add(lambda message: recus.append(str(message)), level="WARNING")
    try:
        for etat in (OUVERT, PAUSE, FERME, SUR_RENDEZ_VOUS):
            phrase_annonce(etat, "demain à 10 heures")
    finally:
        logger.remove(jeton)
    assert recus == []


@pytest.mark.parametrize("valeur", [["x"], 42, {"a": 1}, None])
def test_une_reouverture_qui_nest_pas_du_texte_nest_jamais_prononcee(valeur):
    """``il rouvre ['x']`` would be spoken as is. The injection filters the
    non-str, like ``_est_vide`` does for the rest of the module."""
    resultat = injecter_etat_ouverture(
        {"etat_ouverture": FERME, "reouverture": valeur},
        {"horaires_ouverture": EXEMPLE_D2},
        maintenant=MARDI_11H,
    )
    annonce = resultat["annonce_ouverture"]
    assert "[" not in annonce and "{" not in annonce and "42" not in annonce


# --------------------------------------------------------------------------- #
# 15. The announcement follows a state overwritten AFTER the injection
# --------------------------------------------------------------------------- #


def test_un_prefetch_qui_ferme_apres_coup_fait_apparaitre_lannonce():
    """Review of 2026-09-18, Majeur 2: a pre-call fetch is merged AFTER the
    injection and can overwrite the state. Without the refresh, a business the
    fetch says is closed announces NOTHING -- the very defect this fixes."""
    injecte = injecter_etat_ouverture(
        {"direction": "inbound"}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_11H
    )
    assert injecte["etat_ouverture"] == OUVERT and injecte["annonce_ouverture"] == ""

    apres_fetch = {**injecte, "etat_ouverture": FERME, "reouverture": "demain à 10 heures"}
    rafraichi = rafraichir_annonce(apres_fetch)
    assert rafraichi["annonce_ouverture"] == (
        "Nous sommes fermés en ce moment, nous rouvrons demain à 10 heures. "
    )


def test_un_prefetch_qui_ouvre_apres_coup_fait_taire_lannonce():
    """The other way round: the fetch says open, the announcement must go."""
    injecte = injecter_etat_ouverture(
        {"direction": "inbound"}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_13H
    )
    assert injecte["annonce_ouverture"] != ""
    rafraichi = rafraichir_annonce({**injecte, "etat_ouverture": OUVERT, "reouverture": ""})
    assert rafraichi["annonce_ouverture"] == ""


def test_le_rafraichissement_ne_touche_pas_un_agent_sans_horaires():
    """🔒 D6 again: nothing was injected, nothing is added."""
    contexte = {"direction": "inbound", "etat_ouverture": FERME}
    assert rafraichir_annonce(contexte) == contexte
    assert "annonce_ouverture" not in rafraichir_annonce(contexte)


def test_le_rafraichissement_ne_modifie_pas_lentree_en_place():
    contexte = injecter_etat_ouverture(
        {"direction": "inbound"}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_11H
    )
    copie = dict(contexte)
    rafraichir_annonce({**contexte, "etat_ouverture": FERME, "reouverture": "demain à 10 heures"})
    assert contexte == copie


@pytest.mark.parametrize("casse", [{"etat_ouverture": ["x"]}, {"reouverture": 42}, {}])
def test_le_rafraichissement_ne_leve_jamais(casse):
    """⛔ Same promise as the injection it completes: the call must go on."""
    contexte = injecter_etat_ouverture(
        {"direction": "inbound"}, {"horaires_ouverture": EXEMPLE_D2}, maintenant=MARDI_13H
    )
    resultat = rafraichir_annonce({**contexte, **casse})
    assert isinstance(resultat, dict) and "annonce_ouverture" in resultat


def test_la_variable_du_message_daccueil_nest_pas_reclamee_aux_campagnes():
    """Review of 2026-09-18, Majeur 1: a BARE ``{{annonce_ouverture}}`` is
    collected as a required template variable, and every outbound campaign on
    that workflow is then rejected (HTTP 400) unless its contact file carries a
    column of that name. A dotted path is skipped."""
    from api.services.workflow.workflow_graph import extract_template_variables

    nu = extract_template_variables("Bonjour. {{annonce_ouverture}}Que puis-je faire ?")
    pointe = extract_template_variables(
        "Bonjour. {{initial_context.annonce_ouverture}}Que puis-je faire ?"
    )
    assert "annonce_ouverture" in nu  # the trap, asserted so it cannot be forgotten
    assert pointe == set()  # the form the greeting must use


# --------------------------------------------------------------------------- #
# 15. The sentences and the state, set on the organization (chantier
#     reglages-annonce-ouverture, 2026-09-18)
#
# The question this section answers:
#
#     Does the agent say the sentence the organization typed, does a state
#     forced by hand win over the hours, and does that forcing LIFT ITSELF once
#     its date has passed -- with nobody coming back to the screen?
#
# ⛔ Every test here fixes the instant too. A forcing that expires is the one
# thing a test reading the real clock could never prove twice.
# --------------------------------------------------------------------------- #

from types import SimpleNamespace  # noqa: E402

from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture  # noqa: E402
from api.services.pipecat.etat_ouverture import (  # noqa: E402
    ANNONCE_FERMETURE_DEFAUT,
    ANNONCE_PAUSE_DEFAUT,
    forcage_actif,
    rendre_annonce,
)

VENDREDI_20H = _a("2026-09-18 20:00")  # after closing, reopens Saturday 10:00
SAMEDI_11H = _a("2026-09-19 11:00")  # open


def _reglages(**champs) -> ReglagesAnnonceOuverture:
    return ReglagesAnnonceOuverture.model_validate(champs)


def _injecte(quand: datetime, reglages=None, configs=None, contexte=None) -> dict:
    return injecter_etat_ouverture(
        dict(contexte or {}),
        {"horaires_ouverture": EXEMPLE_D2} if configs is None else configs,
        maintenant=quand,
        reglages=reglages,
    )


# 15.1 The sentences ------------------------------------------------------- #


def test_sans_reglages_les_phrases_sont_celles_davant():
    """🔒 Every organization that never opens the settings screen hears no change."""
    assert phrase_annonce(FERME, "demain à 10 heures") == (
        "Nous sommes fermés en ce moment, nous rouvrons demain à 10 heures. "
    )
    assert phrase_annonce(PAUSE, "") == "Nous sommes fermés pour le moment. "
    defaut = _reglages()
    assert phrase_annonce(FERME, "demain à 10 heures", defaut) == phrase_annonce(
        FERME, "demain à 10 heures"
    )
    assert phrase_annonce(PAUSE, "", defaut) == phrase_annonce(PAUSE, "")


def test_la_phrase_de_lorganisation_est_reprise_telle_quelle():
    reglages = _reglages(
        annonce_fermeture="Le magasin est fermé[, nous rouvrons {reouverture}].",
        annonce_pause="Nous revenons dans un instant.",
    )
    assert phrase_annonce(FERME, "jeudi à 9 heures", reglages) == (
        "Le magasin est fermé, nous rouvrons jeudi à 9 heures. "
    )
    assert phrase_annonce(PAUSE, "aujourd'hui à 14 heures", reglages) == (
        "Nous revenons dans un instant. "
    )


@pytest.mark.parametrize(
    "modele,reouverture,attendu",
    [
        # The brackets are kept when the reopening is known, dropped when it is not.
        ("Fermé[, retour {reouverture}].", "demain à 10 heures", "Fermé, retour demain à 10 heures. "),
        ("Fermé[, retour {reouverture}].", "", "Fermé. "),
        # An optional part in the middle, with text after it.
        ("Fermé[ jusqu'à {reouverture}], merci.", "", "Fermé, merci. "),
        # No bracket at all: the sentence is said as typed, reopening or not.
        ("Nous sommes fermés.", "demain à 10 heures", "Nous sommes fermés. "),
        # ⛔ An unclosed « [ » is optional to the END -- final full stop included,
        # which is why the screen REFUSES it when it is saved. Read back from a
        # row written by hand, the sentence is poorer; it never speaks a bracket.
        ("Fermé[, retour {reouverture}.", "", "Fermé "),
        ("Fermé[, retour {reouverture}.", "demain à 10 heures", "Fermé, retour demain à 10 heures. "),
        # Empty: nothing at all, not even the trailing space (decision D).
        ("", "demain à 10 heures", ""),
        ("   ", "", ""),
        (None, "", ""),
    ],
)
def test_le_rendu_dune_phrase(modele, reouverture, attendu):
    assert rendre_annonce(modele, reouverture) == attendu


def test_une_phrase_vide_nannonce_rien_du_tout():
    """Decision D: an organization that wants no announcement empties the field."""
    reglages = _reglages(annonce_fermeture="", annonce_pause="")
    assert phrase_annonce(FERME, "demain à 10 heures", reglages) == ""
    assert phrase_annonce(PAUSE, "", reglages) == ""
    contexte = _injecte(VENDREDI_20H, reglages)
    assert contexte["etat_ouverture"] == FERME  # the model is still told
    assert contexte["annonce_ouverture"] == ""  # the greeting says nothing


@pytest.mark.parametrize("etat", [OUVERT, SUR_RENDEZ_VOUS])
def test_une_entreprise_joignable_nannonce_toujours_rien(etat):
    """Decision A: no sentence is offered for these two, and none is said."""
    reglages = _reglages(annonce_fermeture="Fermé.", annonce_pause="Pause.")
    assert phrase_annonce(etat, "", reglages) == ""


@pytest.mark.parametrize("faux", [None, object(), "FERME", 42])
def test_des_reglages_illisibles_donnent_la_phrase_par_defaut(faux):
    """⛔ Anything that is not a settings object falls back to the sentence of before."""
    assert phrase_annonce(FERME, "demain à 10 heures", faux) == (
        "Nous sommes fermés en ce moment, nous rouvrons demain à 10 heures. "
    )


def test_un_reglage_dont_la_phrase_est_none_ne_dit_rien():
    """A row written by hand with a null sentence: nothing said, no exception."""
    assert phrase_annonce(FERME, "demain à 10 heures", SimpleNamespace(annonce_fermeture=None)) == ""


# 15.2 The forced state ---------------------------------------------------- #


def test_letat_force_gagne_sur_les_horaires():
    """Decision 2: Saturday 11:00 the hours say OPEN; forced FERME, it is closed."""
    reglages = _reglages(etat_force=FERME, etat_force_jusqu_a="2026-09-21T10:00:00")
    contexte = _injecte(SAMEDI_11H, reglages)
    assert contexte["etat_ouverture"] == FERME
    assert contexte["reouverture"] == "lundi à 10 heures"
    assert contexte["annonce_ouverture"] == (
        "Nous sommes fermés en ce moment, nous rouvrons lundi à 10 heures. "
    )
    # Without the forcing, the very same instant is OPEN: what is proven here is
    # the forcing, not the hours.
    assert _injecte(SAMEDI_11H)["etat_ouverture"] == OUVERT


def test_un_forcage_expire_rend_la_main_aux_horaires_tout_seul():
    """Decision 3, and the point of the whole mechanism: nobody has to come back.

    Same settings, two instants: before the end date the business is closed,
    after it the hours decide again -- here, OPEN.
    """
    reglages = _reglages(etat_force=FERME, etat_force_jusqu_a="2026-09-19T10:00:00")
    avant = _injecte(_a("2026-09-19 09:59"), reglages)
    apres = _injecte(_a("2026-09-19 10:01"), reglages)
    assert avant["etat_ouverture"] == FERME
    assert apres["etat_ouverture"] == OUVERT
    assert apres["annonce_ouverture"] == ""


def test_a_la_seconde_de_la_date_de_fin_le_forcage_est_deja_leve():
    """The bound is closed on the hours' side: « until 10:00 » means open at 10:00."""
    reglages = _reglages(etat_force=FERME, etat_force_jusqu_a="2026-09-19T10:00:00")
    assert forcage_actif(reglages, _a("2026-09-19 09:59:59")) == (FERME, "aujourd'hui à 10 heures")
    assert forcage_actif(reglages, _a("2026-09-19 10:00:00")) is None


def test_un_forcage_sans_date_tient_et_nannonce_aucune_reouverture():
    """Decision C: an empty date holds until someone goes back to « computed »."""
    reglages = _reglages(etat_force=FERME, etat_force_jusqu_a=None)
    for quand in (SAMEDI_11H, _a("2027-06-15 11:00")):
        contexte = _injecte(quand, reglages)
        assert contexte["etat_ouverture"] == FERME
        assert contexte["reouverture"] == ""
        assert contexte["annonce_ouverture"] == "Nous sommes fermés en ce moment. "


def test_le_retour_a_calcule_rend_la_main_immediatement():
    """Back to « computed » on screen = ``etat_force`` at None, nothing else."""
    contexte = _injecte(SAMEDI_11H, _reglages(etat_force=None))
    assert contexte["etat_ouverture"] == OUVERT
    assert contexte["annonce_ouverture"] == ""


@pytest.mark.parametrize("etat", [OUVERT, SUR_RENDEZ_VOUS])
def test_un_etat_joignable_force_nannonce_pas_de_reouverture(etat):
    """A business forced OPEN has no reopening to announce, date or not."""
    reglages = _reglages(etat_force=etat, etat_force_jusqu_a="2026-09-21T10:00:00")
    contexte = _injecte(VENDREDI_20H, reglages)
    assert contexte["etat_ouverture"] == etat
    assert contexte["reouverture"] == ""
    assert contexte["annonce_ouverture"] == ""
    # Without the forcing, this instant is FERME: the forcing is what is proven.
    assert _injecte(VENDREDI_20H)["etat_ouverture"] == FERME


def test_un_forcage_sapplique_meme_a_un_agent_sans_horaires():
    """A forcing closes the whole company; an agent without hours is one of its agents.

    ⛔ Without a forcing, that same agent keeps EXACTLY the context it had
    before this patch (D6) -- asserted just below, so the two cannot drift.
    """
    reglages = _reglages(etat_force=FERME, etat_force_jusqu_a="2026-09-21T10:00:00")
    ferme = _injecte(SAMEDI_11H, reglages, configs={})
    assert ferme["etat_ouverture"] == FERME
    assert ferme["annonce_ouverture"] == (
        "Nous sommes fermés en ce moment, nous rouvrons lundi à 10 heures. "
    )
    assert "horaires_ouverture" not in ferme  # nothing invented for an agent without hours
    sans_forcage = _injecte(SAMEDI_11H, _reglages(), configs={}, contexte={"direction": "inbound"})
    assert sans_forcage == {"direction": "inbound"}


def test_une_valeur_deja_dans_le_contexte_gagne_encore_sur_un_forcage():
    """D7 still applies ON TOP: the forcing replaces the HOURS, not a replay.

    The keyboard bench must keep being able to play any state, whatever the
    organization forces that day.
    """
    reglages = _reglages(etat_force=FERME, etat_force_jusqu_a="2026-09-21T10:00:00")
    contexte = _injecte(
        SAMEDI_11H, reglages, contexte={"etat_ouverture": OUVERT, "reouverture": ""}
    )
    assert contexte["etat_ouverture"] == OUVERT
    assert contexte["annonce_ouverture"] == ""


def test_un_forcage_avec_des_horaires_invalides_est_quand_meme_applique():
    """Hours refused by the screen but written by hand: the forcing still holds."""
    reglages = _reglages(etat_force=FERME)
    contexte = _injecte(SAMEDI_11H, reglages, configs={"horaires_ouverture": "lundi 10:00-18:30"})
    assert contexte["etat_ouverture"] == FERME


@pytest.mark.parametrize(
    "casse",
    [
        SimpleNamespace(etat_force="CONGES"),
        SimpleNamespace(etat_force=42),
        object(),
        None,
    ],
)
def test_un_forcage_illisible_laisse_decider_les_horaires(casse):
    """⛔ Never raises, and never guesses: anything unreadable means no forcing."""
    assert forcage_actif(casse, SAMEDI_11H) is None


def test_une_date_de_fin_illisible_est_un_forcage_sans_fin():
    """What is unreadable is the DATE, not the decision to close: the state holds."""
    casse = SimpleNamespace(etat_force=FERME, etat_force_jusqu_a="2026-09-21")
    assert forcage_actif(casse, SAMEDI_11H) == (FERME, "")


# 15.3 The refresh after a pre-call fetch keeps the organization's sentence -- #


def test_le_rafraichissement_reprend_la_phrase_de_lorganisation():
    """⛔ Without the settings, a pre-call fetch would rewrite the sentence with
    the DEFAULT one: the organization's wording would vanish mid-call."""
    reglages = _reglages(annonce_fermeture="Le magasin est fermé[, retour {reouverture}].")
    contexte = _injecte(SAMEDI_11H, reglages)
    assert contexte["annonce_ouverture"] == ""  # open, nothing announced
    apres_fetch = rafraichir_annonce(
        {**contexte, "etat_ouverture": FERME, "reouverture": "lundi à 10 heures"}, reglages
    )
    assert apres_fetch["annonce_ouverture"] == "Le magasin est fermé, retour lundi à 10 heures. "


def test_le_rafraichissement_sans_reglages_garde_la_phrase_par_defaut():
    contexte = _injecte(SAMEDI_11H)
    apres_fetch = rafraichir_annonce(
        {**contexte, "etat_ouverture": FERME, "reouverture": "lundi à 10 heures"}
    )
    assert apres_fetch["annonce_ouverture"] == (
        "Nous sommes fermés en ce moment, nous rouvrons lundi à 10 heures. "
    )


def test_les_deux_phrases_par_defaut_restent_generiques():
    """⚠️ The fork carries nothing specific to one client: not « magasin », not
    « pause déjeuner ». What an organization types for itself is its own."""
    for modele in (ANNONCE_FERMETURE_DEFAUT, ANNONCE_PAUSE_DEFAUT):
        minuscules = modele.lower()
        assert "magasin" not in minuscules
        assert "déjeuner" not in minuscules
