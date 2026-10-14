"""[.mark] L'adresse mail lue par le code prime sur celle du modèle (chantier courriel-ecriture).

Run 1143 (14/10, n° 62, mode greffier) : « r o u deux s e a u soixante point evan arobase gmail
point com » est lu `rousseau60.evan@gmail.com` (doute : « soixante » écrit 60), mais le greffier
écrit `rou2seau60.evan@gmail.com` dans la fiche, sûr, et l'agent ne fait rien confirmer. Le point
d'écriture ne reconnaissait l'épellation que si la valeur lui était identique.

| Test | Ce qu'il prouve |
|---|---|
| run 1143 | l'adresse lue est écrite, à faire confirmer (doute du lecteur) |
| sans doute | l'adresse lue est écrite, sûre |
| domaine proche | domaine proche d'un connu : à faire confirmer |
| passe suivante | le greffier relit tout l'appel : une passe plus tard, l'adresse lue prime encore |
| sans rapport | une autre adresse ne reçoit pas celle lue |
| pas un courriel | un champ hors ``variables_courriel`` n'est jamais touché |
"""

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_TOUR,
    MODE_GREFFIER,
    TRACE_EPELLATIONS,
    ReglagesFiche,
    courriel_lu,
    ecrire_dans_la_fiche,
)

CHAMPS = [
    {"nom": "email", "origine": "dicte"},
    {"nom": "appareil", "origine": "dicte"},
]
LU = "rousseau60.evan@gmail.com"
ENTENDU = "r o u deux s e a u soixante point evan arobase gmail point com"


def _reglages() -> ReglagesFiche:
    return ReglagesFiche.depuis({"fiche_au_fil_de_leau": True, "fiche_champs": CHAMPS})


def _fiche(tour: int = 8, **trace) -> dict:
    return {
        CLE_TOUR: tour,
        TRACE_EPELLATIONS: [
            {"etape": "coordonnees", "entendu": "R, O, U, deux S, E, A, U", "epele": "Rousseau", "tour": 3},
            {"etape": "autre_demande", "entendu": ENTENDU, "epele": LU, "courriel": True, "tour": 8, **trace},
        ],
    }


def _ecrire(fiche: dict, valeur: str, champ: str = "email"):
    return ecrire_dans_la_fiche(
        fiche, _reglages(), champ, valeur, source=MODE_GREFFIER, paroles=[ENTENDU]
    )


def test_run_1143_l_adresse_lue_est_ecrite_a_faire_confirmer():
    fiche = _fiche(doutes=["« soixante » écrit 60"])
    verdict = _ecrire(fiche, "rou2seau60.evan@gmail.com")
    assert verdict.statut == "ecrit"
    assert verdict.valeur == LU
    assert verdict.suite == "a_confirmer"
    assert fiche["email"] == LU
    assert fiche[CLE_ETAT]["email"]["sure"] is False


def test_sans_doute_l_adresse_lue_est_ecrite_sure():
    fiche = _fiche()
    verdict = _ecrire(fiche, "rou2seau60.evan@gmail.com")
    assert verdict.valeur == LU and verdict.suite is None
    assert fiche[CLE_ETAT]["email"]["sure"] is True


def test_valeur_identique_avec_doute_reste_a_confirmer():
    """Avant, une valeur identique à l'épellation était écrite sûre malgré le doute."""
    fiche = _fiche(doutes=["« soixante » écrit 60"])
    assert _ecrire(fiche, LU).suite == "a_confirmer"


def test_domaine_proche_a_faire_confirmer():
    fiche = _fiche(domaine_proche="gmail.com")
    assert _ecrire(fiche, "rou2seau60.evan@gmail.com").suite == "a_confirmer"


def test_une_passe_plus_tard_l_adresse_lue_prime_encore():
    fiche = _fiche(tour=11)
    assert _ecrire(fiche, "rou2seau60.evan@gmail.com").valeur == LU


def test_une_adresse_sans_rapport_ne_recoit_pas_celle_lue():
    reglages = _reglages()
    assert courriel_lu("marie.dupont@orange.fr", _fiche(), reglages, reglages.par_nom["email"]) is None


def test_un_champ_hors_courriel_n_est_jamais_touche():
    reglages = _reglages()
    valeur = "rou2seau60.evan@gmail.com"
    assert courriel_lu(valeur, _fiche(), reglages, reglages.par_nom["appareil"]) is None


def test_une_trace_qui_n_est_pas_une_adresse_n_est_jamais_prise():
    reglages = _reglages()
    fiche = _fiche()
    fiche[TRACE_EPELLATIONS][1].pop("courriel")
    assert courriel_lu("rou2seau60.evan@gmail.com", fiche, reglages, reglages.par_nom["email"]) is None
