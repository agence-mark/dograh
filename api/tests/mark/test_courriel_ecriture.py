"""[.mark] L'adresse mail lue par le code prime sur celle du modèle (chantier courriel-ecriture).

Run 1143 (14/10, mode greffier) : une adresse dictée lettre à lettre (« r o u deux s e a u
soixante… ») est lue juste par le code, avec un doute (« soixante » écrit 60), mais le greffier
en écrit une autre lecture (« rou2seau60… »), sûre, et l'agent ne fait rien confirmer. Le point
d'écriture ne reconnaissait l'épellation que si la valeur lui était identique.

Relecture n° 1 : l'adresse lue ne s'impose qu'au message où elle a été dite, puis seulement contre
l'écriture qu'elle a déjà remplacée ; une autre écriture plus tard est une correction de la
personne. Elle remplace la valeur AVANT les règles du « oui » et du « déjà confirmé ».

Adresses fictives (domaine ``exemple.fr``).

| Test | Ce qu'il prouve |
|---|---|
| run 1143 | l'adresse lue est écrite, à faire confirmer (doute du lecteur) |
| sans doute | l'adresse lue est écrite, sûre |
| domaine proche | domaine proche d'un connu : à faire confirmer |
| passe en retard | la passe du greffier finit après le tour suivant : le message dit compte |
| répétition | le greffier répète l'écriture remplacée à une passe suivante : l'adresse lue reste |
| oui puis écriture fausse | un « oui » rend l'adresse lue sûre même si le modèle garde son écriture |
| correction | « non, c'est 61 » ou un autre domaine, plus tard : jamais écrasé par l'adresse lue |
| dernière seulement | une adresse lue plus ancienne n'a plus d'autorité |
| sans rapport, hors courriel | rien n'est touché |
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
LU = "rousseau60.marie@exemple.fr"
FAUX = "rou2seau60.marie@exemple.fr"
ENTENDU = "r o u deux s e a u soixante point marie arobase exemple point f r"
DOUTE = ["« soixante » écrit 60"]


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


def _ecrire(fiche: dict, valeur: str, paroles=(ENTENDU,), champ: str = "email", question=None):
    return ecrire_dans_la_fiche(
        fiche, _reglages(), champ, valeur, source=MODE_GREFFIER, paroles=list(paroles), question=question
    )


def _sure(fiche: dict) -> bool:
    return fiche[CLE_ETAT]["email"]["sure"]


def test_run_1143_l_adresse_lue_est_ecrite_a_faire_confirmer():
    fiche = _fiche(doutes=DOUTE)
    verdict = _ecrire(fiche, FAUX)
    assert (verdict.statut, verdict.valeur, verdict.suite) == ("ecrit", LU, "a_confirmer")
    assert fiche["email"] == LU and not _sure(fiche)


def test_sans_doute_l_adresse_lue_est_ecrite_sure():
    fiche = _fiche()
    verdict = _ecrire(fiche, FAUX)
    assert verdict.valeur == LU and verdict.suite is None and _sure(fiche)


def test_valeur_identique_avec_doute_reste_a_confirmer():
    """Avant, une valeur identique à l'épellation était écrite sûre malgré le doute."""
    assert _ecrire(_fiche(doutes=DOUTE), LU).suite == "a_confirmer"


def test_domaine_proche_a_faire_confirmer():
    assert _ecrire(_fiche(domaine_proche="exemple.com"), FAUX).suite == "a_confirmer"


def test_passe_en_retard_le_message_dit_compte():
    fiche = _fiche(tour=9)
    assert _ecrire(fiche, FAUX, paroles=["bonjour", ENTENDU]).valeur == LU


def test_hors_du_message_dit_une_nouvelle_ecriture_n_est_pas_remplacee():
    fiche = _fiche(tour=9)
    reglages = _reglages()
    assert courriel_lu(FAUX, fiche, reglages, reglages.par_nom["email"], ["autre chose"]) is None


def test_le_greffier_repete_l_ecriture_remplacee_l_adresse_lue_reste():
    fiche = _fiche(doutes=DOUTE)
    _ecrire(fiche, FAUX)
    fiche[CLE_TOUR] = 11
    verdict = _ecrire(fiche, FAUX, paroles=[ENTENDU, "le jeudi matin"])
    assert verdict.valeur == LU and fiche["email"] == LU


def test_un_oui_rend_l_adresse_sure_meme_si_le_modele_garde_son_ecriture():
    fiche = _fiche(doutes=DOUTE)
    assert _ecrire(fiche, FAUX).suite == "a_confirmer"
    fiche[CLE_TOUR] = 9
    question = f"Votre adresse est bien {LU} ?"
    verdict = _ecrire(fiche, FAUX, paroles=[ENTENDU, "oui"], question=question)
    assert verdict.valeur == LU and verdict.suite is None and _sure(fiche)
    # Une passe suivante qui répète l'écriture fausse ne rouvre rien.
    fiche[CLE_TOUR] = 10
    _ecrire(fiche, FAUX, paroles=[ENTENDU, "oui", "merci"])
    assert fiche["email"] == LU and _sure(fiche)


def test_une_correction_plus_tard_n_est_jamais_ecrasee():
    fiche = _fiche()
    _ecrire(fiche, FAUX)
    fiche[CLE_TOUR] = 10
    corrigee = "rousseau61.marie@exemple.fr"
    verdict = _ecrire(fiche, corrigee, paroles=[ENTENDU, f"non, c'est {corrigee}"])
    assert verdict.valeur == corrigee and fiche["email"] == corrigee


def test_une_correction_du_domaine_n_est_jamais_ecrasee():
    fiche = _fiche()
    _ecrire(fiche, FAUX)
    fiche[CLE_TOUR] = 10
    reglages = _reglages()
    autre = "rousseau60.marie@exemple.com"
    assert courriel_lu(autre, fiche, reglages, reglages.par_nom["email"], ["non, point com"]) is None


def test_seule_la_derniere_adresse_lue_a_autorite():
    fiche = _fiche()
    fiche[TRACE_EPELLATIONS].append(
        {"entendu": "jean arobase exemple point f r", "epele": "jean@exemple.fr", "courriel": True, "tour": 8}
    )
    reglages = _reglages()
    assert courriel_lu(FAUX, fiche, reglages, reglages.par_nom["email"], [ENTENDU]) is None


def test_deux_champs_courriel_la_premiere_adresse_reste_elle_meme():
    """Relecture n° 2 : la seconde adresse épelée (tour 12) ressemble à la première ; le
    greffier relit tout l'appel et renvoie la première, juste : elle n'est pas remplacée."""
    fiche = _fiche()
    seconde = "rousseau60.paul@exemple.fr"
    fiche[TRACE_EPELLATIONS].append(
        {"entendu": "rousseau soixante point paul arobase exemple point f r", "epele": seconde, "courriel": True, "tour": 12}
    )
    fiche[CLE_TOUR] = 12
    reglages = _reglages()
    paroles = ["rousseau soixante point paul arobase exemple point f r"]
    assert courriel_lu(LU, fiche, reglages, reglages.par_nom["email"], paroles) is None
    # Ni l'écriture que la première a remplacée.
    fiche[TRACE_EPELLATIONS][1]["remplacees"] = [FAUX]
    assert courriel_lu(FAUX, fiche, reglages, reglages.par_nom["email"], paroles) is None
    # La seconde, mal écrite par le greffier, reçoit bien la seconde lecture.
    assert courriel_lu("rousseau6o.paul@exemple.fr", fiche, reglages, reglages.par_nom["email"], paroles).valeur == seconde


def test_une_adresse_sans_rapport_ne_recoit_pas_celle_lue():
    reglages = _reglages()
    assert courriel_lu("dupont@autre.fr", _fiche(), reglages, reglages.par_nom["email"], [ENTENDU]) is None


def test_un_champ_hors_courriel_n_est_jamais_touche():
    reglages = _reglages()
    assert courriel_lu(FAUX, _fiche(), reglages, reglages.par_nom["appareil"], [ENTENDU]) is None


def test_une_trace_qui_n_est_pas_une_adresse_n_est_jamais_prise():
    reglages = _reglages()
    fiche = _fiche()
    fiche[TRACE_EPELLATIONS][1].pop("courriel")
    assert courriel_lu(FAUX, fiche, reglages, reglages.par_nom["email"], [ENTENDU]) is None
