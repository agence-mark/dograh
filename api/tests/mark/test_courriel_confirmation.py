"""[.mark] En mode greffier, l'agent fait confirmer une épellation douteuse (chantier courriel-confirmation).

Run 1144 (14/10, n° 62, mode greffier) : l'adresse lue avec un doute était juste dans la fiche, « à
confirmer », mais l'agent n'a rien fait confirmer. Le greffier écrit après la réponse du tour : sa
consigne arrivait un tour trop tard (l'agent avait pris sa porte), puis une passe vide l'effaçait.

| Test | Ce qu'il prouve |
|---|---|
| tour même | le doute du lecteur est dit à l'agent au tour de la dictée, avant le greffier |
| domaine proche | idem pour un domaine proche d'un connu |
| sans doute | rien de plus quand le lecteur n'a pas de doute |
| tour d'après | la ligne du tour même ne revient pas au tour suivant |
| déjà écrite | pas de doublon quand le greffier a déjà écrit la valeur à confirmer |
| consigne gardée | une passe vide du greffier n'efface plus la consigne tant qu'un champ reste à confirmer |
| autres modes | rien ne change hors du mode greffier |
"""

from api.services.workflow.fiche_au_fil_de_leau import (
    CLE_ETAT,
    CLE_TOUR,
    CONSIGNE_A_CONFIRMER,
    TRACE_EPELLATIONS,
    Notices,
    ReglagesFiche,
    etat_de_la_fiche,
)

CHAMPS = [{"nom": "nom", "origine": "dicte"}, {"nom": "email", "origine": "dicte"}]
LU = "rousseau60.marie@exemple.fr"


def _reglages(mode: str = "greffier") -> ReglagesFiche:
    return ReglagesFiche.depuis(
        {"fiche_au_fil_de_leau": True, "fiche_champs": CHAMPS, "fiche_mode_de_note": mode}
    )


def _fiche(tour: int = 8, **trace) -> dict:
    return {
        CLE_TOUR: tour,
        "nom": "Rousseau",
        CLE_ETAT: {"nom": {"sure": True, "source": "greffier"}},
        TRACE_EPELLATIONS: [{"epele": LU, "courriel": True, "tour": 8, **trace}],
    }


def _etat(fiche: dict, mode: str = "greffier", notices: Notices | None = None) -> str:
    return etat_de_la_fiche(_reglages(mode), fiche, notices) or ""


def test_le_doute_du_lecteur_est_dit_au_tour_meme():
    etat = _etat(_fiche(doutes=["« soixante » écrit 60"]))
    assert f"vient d'épeler « {LU} »" in etat
    assert "avant de prendre une porte" in etat


def test_un_domaine_proche_aussi():
    assert f"« {LU} »" in _etat(_fiche(domaine_proche="exemple.com"))


def test_sans_doute_rien_de_plus():
    assert "vient d'épeler" not in _etat(_fiche())


def test_la_ligne_du_tour_meme_ne_revient_pas_au_tour_suivant():
    assert "vient d'épeler" not in _etat(_fiche(tour=9, doutes=["x"]))


def test_pas_de_doublon_quand_le_greffier_a_deja_ecrit():
    fiche = _fiche(doutes=["x"])
    fiche["email"] = LU
    fiche[CLE_ETAT]["email"] = {"sure": False, "source": "greffier"}
    etat = _etat(fiche)
    assert f"À confirmer : email = « {LU} »" in etat
    assert "vient d'épeler" not in etat


def test_une_passe_vide_n_efface_plus_la_consigne():
    fiche = _fiche(tour=9)
    fiche["email"] = LU
    fiche[CLE_ETAT]["email"] = {"sure": False, "source": "greffier"}
    notices = Notices()
    notices.retenir(None)  # la passe vide du greffier
    assert CONSIGNE_A_CONFIRMER in _etat(fiche, notices=notices)


def test_rien_ne_change_hors_du_mode_greffier():
    fiche = _fiche(doutes=["x"])
    fiche["email"] = LU
    fiche[CLE_ETAT]["email"] = {"sure": False, "source": "outil"}
    etat = _etat(fiche, mode="outil")
    assert "vient d'épeler" not in etat and CONSIGNE_A_CONFIRMER not in etat
