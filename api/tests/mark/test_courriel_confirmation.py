"""[.mark] En mode greffier, l'agent fait confirmer une épellation douteuse (chantier courriel-confirmation).

Run 1144 (14/10, n° 62, mode greffier) : l'adresse lue avec un doute était juste dans la fiche, « à
confirmer », mais l'agent n'a rien fait confirmer. Le greffier écrit après la réponse du tour : sa
consigne arrivait un tour trop tard (l'agent avait pris sa porte), puis une passe vide l'effaçait.

Relecture : le souffle de l'étape disait « prends ta porte » juste après la consigne ; la consigne
gardée pouvait revenir à chaque tour ; un « oui » ne rendait jamais sûr un champ que le greffier
renvoyait inchangé ; une adresse épelée comptait comme un nom lu.

| Test | Ce qu'il prouve |
|---|---|
| tour même | le doute du lecteur est dit à l'agent au tour de la dictée, avant le greffier ; toutes les épellations douteuses du tour |
| domaine proche, sans doute, lexique | domaine proche aussi ; rien sans doute ; jamais un terme du lexique épelé |
| tour d'après, déjà écrite | la ligne du tour même ne revient pas ; pas de doublon |
| consigne gardée, bornée | une passe vide n'efface plus la consigne ; pas après un oui ; pas au-delà du tour suivant |
| souffle | jamais « prends ta porte » quand une confirmation attend |
| greffier et oui | après un oui, le champ inchangé encore à confirmer est renvoyé à la note |
| traces | une adresse épelée ou une épellation douteuse n'est pas un nom lu |
| autres modes | rien ne change hors du mode greffier |
"""

from api.services.fiche.traces import valeurs_des_traces
from api.services.pipecat.greffier import champs_a_noter
from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_JOURNAL,
    CLE_TOUR,
    CONSIGNE_A_CONFIRMER,
    SOUFFLE_ETAPE_COMPLETE,
    TRACE_EPELLATIONS,
    Notices,
    ReglagesFiche,
    etat_de_la_fiche,
    souffle_de_l_etape,
)

CHAMPS = [{"nom": "nom", "origine": "dicte"}, {"nom": "email", "origine": "dicte"}]
LU = "rousseau60.marie@exemple.fr"


def _reglages(mode: str = "greffier") -> ReglagesFiche:
    return ReglagesFiche.depuis(
        {
            "fiche_au_fil_de_leau": True,
            "fiche_champs": CHAMPS,
            "fiche_mode_de_note": mode,
            "etiquettes_des_etapes": True,
        }
    )


def _fiche(tour: int = 8, **trace) -> dict:
    return {
        CLE_TOUR: tour,
        "nom": "Rousseau",
        CLE_ETAT: {"nom": {"sure": True, "source": "greffier"}},
        TRACE_EPELLATIONS: [{"epele": LU, "courriel": True, "tour": 8, **trace}],
    }


def _email_a_confirmer(fiche: dict, ecrit_au_tour: int = 8) -> dict:
    fiche["email"] = LU
    fiche[CLE_ETAT]["email"] = {"sure": False, "source": "greffier"}
    fiche[CLE_JOURNAL] = [
        {"champ": "email", "valeur": LU, "statut": "ecrit", "sure": False, "suite": "a_confirmer", "tour": ecrit_au_tour}
    ]
    return fiche


def _etat(fiche: dict, mode: str = "greffier", notices: Notices | None = None, parole: str | None = None) -> str:
    return etat_de_la_fiche(_reglages(mode), fiche, notices, parole) or ""


# --- ① au tour même -----------------------------------------------------------


def test_le_doute_du_lecteur_est_dit_au_tour_meme():
    etat = _etat(_fiche(doutes=["« soixante » écrit 60"]))
    assert f"vient d'épeler « {LU} »" in etat and "avant de prendre une porte" in etat


def test_toutes_les_epellations_douteuses_du_tour():
    fiche = _fiche(doutes=["x"])
    fiche[TRACE_EPELLATIONS].insert(0, {"epele": "Boné", "tour": 8, "doutes": ["N"]})
    etat = _etat(fiche)
    assert "« Boné »" in etat and f"« {LU} »" in etat


def test_un_domaine_proche_aussi():
    assert f"« {LU} »" in _etat(_fiche(domaine_proche="exemple.com"))


def test_sans_doute_rien_de_plus():
    assert "vient d'épeler" not in _etat(_fiche())


def test_jamais_un_terme_du_lexique_epele():
    assert "vient d'épeler" not in _etat(_fiche(doutes=["x"], terme_du_lexique="Marque"))


def test_la_ligne_du_tour_meme_ne_revient_pas_au_tour_suivant():
    assert "vient d'épeler" not in _etat(_fiche(tour=9, doutes=["x"]))


def test_pas_de_doublon_quand_le_greffier_a_deja_ecrit():
    etat = _etat(_email_a_confirmer(_fiche(doutes=["x"])))
    assert f"À confirmer : email = « {LU} »" in etat and "vient d'épeler" not in etat


# --- ② la consigne gardée, bornée ----------------------------------------------


def test_une_passe_vide_n_efface_plus_la_consigne():
    notices = Notices()
    notices.retenir(None)  # la passe vide du greffier
    etat = _etat(_email_a_confirmer(_fiche(tour=9)), notices=notices, parole="non, c'est tout")
    assert CONSIGNE_A_CONFIRMER in etat


def test_pas_de_consigne_juste_apres_un_oui():
    etat = _etat(_email_a_confirmer(_fiche(tour=9)), parole="oui c'est ça")
    assert CONSIGNE_A_CONFIRMER not in etat


def test_la_consigne_ne_revient_pas_au_dela_du_tour_suivant():
    etat = _etat(_email_a_confirmer(_fiche(tour=12)), parole="d'accord")
    assert CONSIGNE_A_CONFIRMER not in etat


# --- le souffle de l'étape -----------------------------------------------------


def test_jamais_prends_ta_porte_quand_une_epellation_douteuse_attend():
    fiche = _email_a_confirmer(_fiche(doutes=["x"]))
    fiche[CLE_ETAT]["email"] = {"sure": True, "source": "greffier"}
    fiche[CLE_JOURNAL] = []
    assert souffle_de_l_etape(_reglages(), fiche, ["nom", "email"]) is None


def test_jamais_prends_ta_porte_quand_un_champ_reste_a_confirmer():
    fiche = _email_a_confirmer(_fiche(tour=9))
    assert souffle_de_l_etape(_reglages(), fiche, ["nom", "email"]) is None


def test_prends_ta_porte_quand_tout_est_sur():
    fiche = _email_a_confirmer(_fiche(tour=9))
    fiche[CLE_ETAT]["email"] = {"sure": True, "source": "greffier"}
    assert souffle_de_l_etape(_reglages(), fiche, ["nom", "email"]) == SOUFFLE_ETAPE_COMPLETE


# --- le greffier et le oui ------------------------------------------------------


def test_apres_un_oui_le_champ_inchange_a_confirmer_est_renvoye():
    fiche = _email_a_confirmer(_fiche(tour=9))
    rendue = {"email": LU, "nom": "Rousseau"}
    assert champs_a_noter(_reglages(), fiche, rendue, oui=True) == {"email": LU}
    assert champs_a_noter(_reglages(), fiche, rendue, oui=False) == {}


# --- les traces --------------------------------------------------------------------


def test_une_adresse_epelee_n_est_pas_un_nom_lu():
    fiche = _fiche()
    del fiche["nom"]
    assert "nom" not in valeurs_des_traces(_reglages(), fiche)


def test_une_epellation_douteuse_n_est_pas_un_nom_lu():
    fiche = {CLE_TOUR: 3, TRACE_EPELLATIONS: [{"epele": "Boné", "tour": 3, "doutes": ["N"]}]}
    assert "nom" not in valeurs_des_traces(_reglages(), fiche)
    fiche[TRACE_EPELLATIONS][0].pop("doutes")
    assert valeurs_des_traces(_reglages(), fiche).get("nom") == "Boné"


# --- hors du mode greffier -----------------------------------------------------------


def test_rien_ne_change_hors_du_mode_greffier():
    fiche = _email_a_confirmer(_fiche(doutes=["x"]))
    fiche[CLE_ETAT]["email"]["source"] = "outil"
    etat = _etat(fiche, mode="outil", parole="non")
    assert "vient d'épeler" not in etat and CONSIGNE_A_CONFIRMER not in etat
