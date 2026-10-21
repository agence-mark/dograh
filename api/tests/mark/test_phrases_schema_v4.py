"""[.mark] Chantier correctifs-apres-banc-v4, lot 4 (4.2 à 4.5, 4.8) : le schéma des règles de phrase et le
catalogue des motifs.

| Test | La garantie |
|---|---|
| zéro perte | une règle écrite avant le lot se relit telle quelle : mêmes phrases, même délai, une fois par attente, rien de plus |
| ancien motif | « un connecteur échoue » se lit comme « un outil échoue », règle comprise |
| cases permises | une case que le motif ne permet pas disparaît (pas de redite, d'outil ou de délai là où ça n'a pas de sens) |
| bornes | délai 0 permis pour un outil, minimum propre au silence et à la passation, redite 2 à 60 s, plafonds |
| sorties | une action interdite pour le motif est refusée ; un transfert exige sa destination ; une note exige champ et valeur |
| unicité | (motif, portée, étape, outils) : deux règles identiques sont refusées, deux outils différents passent |
| étape | une règle d'étape se repère par son identifiant ou, avant, par son nom ; sans l'un ni l'autre, refusée |
| catalogue | dix motifs, chacun dit ses cases permises ; les problèmes n'ont ni délai ni redite |
| enregistrement | la configuration de l'agent accepte et rend les règles (clé ``phrases_regles``) |
"""

import pytest
from pydantic import ValidationError

from api.schemas.phrases_du_code import ReglePhrase, verifier_regles
from api.services.phrases.catalogue import (
    APPELANT_SE_TAIT,
    MISE_EN_RELATION,
    MODELE_TARDE,
    MOTIFS,
    MOTIFS_DE_PROBLEME,
    OUTIL_ECHOUE,
    OUTIL_TARDE,
    PASSATION_TARDE,
    REPONSE_PERDUE,
    TRANSFERT_ECHOUE,
    TRAVAIL_DURE,
    TRAVAIL_ECHOUE,
)
from api.services.phrases.regles import NIVEAU_AGENT, resoudre


def _regle(**champs):
    base = {"motif": OUTIL_TARDE, "portee": "agent", "variantes": ["Un instant."]}
    return ReglePhrase.model_validate({**base, **champs})


def test_une_regle_d_avant_le_lot_se_relit_telle_quelle():
    ancienne = {
        "motif": TRAVAIL_DURE,
        "portee": "agent",
        "etape": None,
        "variantes": ["C'est presque bon.", "Encore un peu."],
        "delai_s": 6,
        "active": True,
    }
    regle = ReglePhrase.model_validate(ancienne)
    assert regle.ordre == "tournees"
    assert regle.redite_s is None and regle.max_par_attente is None and regle.max_par_appel is None
    assert regle.outils == [] and regle.texte_de_l_agent is False and regle.ensuite.posee is False
    phrase = resoudre(TRAVAIL_DURE, reglages_agent={"phrases_regles": [ancienne]})
    assert phrase.niveau == NIVEAU_AGENT
    assert phrase.variantes == ("C'est presque bon.", "Encore un peu.")
    assert phrase.delai_s == 6 and phrase.delai_pose is True
    # Comme avant : une seule fois par attente, sans redite, sans plafond, aucune sortie réglée.
    assert (phrase.redite_s, phrase.max_par_attente, phrase.max_par_appel) == (None, 1, None)
    assert phrase.sortie_posee is False and phrase.max_pose is False


def test_l_ancien_motif_connecteur_se_lit_comme_un_outil_qui_echoue():
    regle = ReglePhrase.model_validate(
        {"motif": "connecteur_echoue", "portee": "groupe", "variantes": ["On vous rappelle."]}
    )
    assert regle.motif == OUTIL_ECHOUE
    phrase = resoudre("connecteur_echoue", reglages_agent={"phrases_regles": [{
        "motif": "connecteur_echoue", "variantes": ["On vous rappelle."]}]})
    assert phrase.motif.id == OUTIL_ECHOUE and phrase.variantes == ("On vous rappelle.",)


def test_une_case_que_le_motif_ne_permet_pas_disparait():
    # Une réponse perdue est un fait : ni délai, ni redite, ni outil visé.
    regle = _regle(
        motif=REPONSE_PERDUE, delai_s=5, redite_s=10, max_par_attente=3, outils=["chercher"]
    )
    assert regle.delai_s is None and regle.redite_s is None
    assert regle.max_par_attente is None and regle.outils == []
    # Le texte de l'agent n'existe que pour le travail de fond.
    assert _regle(motif=OUTIL_TARDE, texte_de_l_agent=True).texte_de_l_agent is False
    assert _regle(motif=TRAVAIL_DURE, texte_de_l_agent=True, variantes=[]).texte_de_l_agent is True
    # Un outil peut être visé pour « un outil travaille » et « un outil échoue », pas pour le fond.
    assert _regle(motif=OUTIL_TARDE, outils=["chercher"]).outils == ["chercher"]
    assert _regle(motif=OUTIL_ECHOUE, outils=["chercher"]).outils == ["chercher"]
    assert _regle(motif=TRAVAIL_DURE, outils=["chercher"]).outils == []


def test_les_bornes_de_chaque_motif():
    # « Dès le lancement » : 0 s pour l'outil et le fond.
    assert _regle(motif=OUTIL_TARDE, delai_s=0).delai_s == 0
    assert _regle(motif=TRAVAIL_DURE, delai_s=0).delai_s == 0
    # Sous le minimum du motif : borné à la lecture, jamais une erreur (revue m5).
    assert _regle(motif=PASSATION_TARDE, delai_s=0.2).delai_s == 0.5
    assert _regle(motif=PASSATION_TARDE, delai_s=0.5).delai_s == 0.5
    assert _regle(motif=APPELANT_SE_TAIT, delai_s=1).delai_s == 2
    assert _regle(motif=APPELANT_SE_TAIT, delai_s=2).delai_s == 2
    with pytest.raises(ValidationError):
        _regle(delai_s=121)
    with pytest.raises(ValidationError):
        _regle(redite_s=1.5)
    with pytest.raises(ValidationError):
        _regle(redite_s=61)
    assert _regle(redite_s=2, max_par_attente=5, max_par_appel=20).max_par_attente == 5
    for trop in ({"max_par_attente": 6}, {"max_par_attente": 0}, {"max_par_appel": 21}):
        with pytest.raises(ValidationError):
            _regle(**trop)


def test_les_sorties_permises_par_motif():
    # Une attente d'outil ne raccroche pas ; le silence peut transférer ou raccrocher, pas « le modèle reprend ».
    with pytest.raises(ValidationError):
        _regle(motif=OUTIL_TARDE, ensuite={"action": "raccrocher"})
    with pytest.raises(ValidationError):
        _regle(motif=APPELANT_SE_TAIT, ensuite={"action": "modele"})
    assert _regle(
        motif=APPELANT_SE_TAIT, ensuite={"phrases": ["Au revoir."], "action": "raccrocher"}
    ).ensuite.action == "raccrocher"
    for motif in (OUTIL_ECHOUE, TRAVAIL_ECHOUE, TRANSFERT_ECHOUE, REPONSE_PERDUE):
        for action in ("continuer", "modele", "raccrocher"):
            assert _regle(motif=motif, ensuite={"action": action}).ensuite.action == action
    # Un transfert exige sa destination ; sans transfert, la destination n'est pas gardée.
    with pytest.raises(ValidationError):
        _regle(motif=OUTIL_ECHOUE, ensuite={"action": "transferer"})
    regle = _regle(motif=OUTIL_ECHOUE, ensuite={"action": "transferer", "destination": " accueil "})
    assert regle.ensuite.destination == "accueil"
    assert _regle(motif=OUTIL_ECHOUE, ensuite={"action": "modele", "destination": "x"}).ensuite.destination is None
    # Une note exige son champ et sa valeur.
    with pytest.raises(ValidationError):
        _regle(motif=OUTIL_ECHOUE, ensuite={"noter": {"champ": "rdv", "valeur": " "}})
    note = _regle(motif=OUTIL_ECHOUE, ensuite={"noter": {"champ": "rdv", "valeur": "à rappeler"}})
    assert note.ensuite.noter.champ == "rdv" and note.ensuite.posee is True


def test_l_unicite_est_motif_portee_etape_et_outils():
    a = _regle(motif=OUTIL_ECHOUE, outils=["reserver"])
    b = _regle(motif=OUTIL_ECHOUE, outils=["chercher"])
    tous = _regle(motif=OUTIL_ECHOUE)
    assert len(verifier_regles([a, b, tous])) == 3
    with pytest.raises(ValueError):
        verifier_regles([a, _regle(motif=OUTIL_ECHOUE, outils=["reserver"])])
    # L'ordre des outils n'y change rien.
    with pytest.raises(ValueError):
        verifier_regles(
            [_regle(motif=OUTIL_ECHOUE, outils=["a", "b"]), _regle(motif=OUTIL_ECHOUE, outils=["b", "a"])]
        )
    # Deux étapes différentes (par identifiant) passent, la même étape deux fois non.
    e1 = _regle(portee="etape", etape="Rendez-vous", etape_id="n1")
    e2 = _regle(portee="etape", etape="Rendez-vous", etape_id="n2")
    assert len(verifier_regles([e1, e2])) == 2
    with pytest.raises(ValueError):
        verifier_regles([e1, _regle(portee="etape", etape="Autre nom", etape_id="n1")])


def test_une_etape_se_repere_par_son_identifiant_ou_son_nom():
    assert _regle(portee="etape", etape_id="n1").etape_id == "n1"
    assert _regle(portee="etape", etape="Rendez-vous").etape == "Rendez-vous"
    with pytest.raises(ValidationError):
        _regle(portee="etape")
    # Hors d'une étape, ni nom ni identifiant ne sont gardés.
    hors = _regle(portee="agent", etape="X", etape_id="n9")
    assert hors.etape is None and hors.etape_id is None


def test_une_regle_active_exige_une_phrase_sauf_le_texte_de_l_agent():
    with pytest.raises(ValidationError):
        _regle(variantes=[])
    assert _regle(variantes=[], active=False).active is False
    assert _regle(motif=TRAVAIL_DURE, variantes=[], texte_de_l_agent=True).variantes == []


def test_le_catalogue_dit_les_cases_de_chaque_motif():
    assert len(MOTIFS) == 10
    # Les problèmes sont déclenchés par un fait : ni délai, ni redite.
    assert set(MOTIFS_DE_PROBLEME) == {REPONSE_PERDUE, OUTIL_ECHOUE, TRAVAIL_ECHOUE, TRANSFERT_ECHOUE}
    for identifiant in MOTIFS_DE_PROBLEME:
        motif = MOTIFS[identifiant]
        assert not motif.a_un_delai and not motif.peut_redire and motif.fait_fr
        assert motif.sortie_defaut in motif.sorties_permises
    # Les attentes qui répètent.
    for identifiant in (OUTIL_TARDE, TRAVAIL_DURE, PASSATION_TARDE, APPELANT_SE_TAIT):
        assert MOTIFS[identifiant].peut_redire and MOTIFS[identifiant].a_un_delai
    assert not MOTIFS[MODELE_TARDE].peut_redire and not MOTIFS[MODELE_TARDE].a_un_delai
    # Le silence : sortie par défaut = raccrocher (le comportement d'avant).
    assert MOTIFS[APPELANT_SE_TAIT].sortie_defaut == "raccrocher"
    assert MOTIFS[APPELANT_SE_TAIT].delai_min_s == 2.0
    assert MOTIFS[OUTIL_TARDE].filtre_outil and MOTIFS[OUTIL_ECHOUE].filtre_outil
    assert not MOTIFS[TRAVAIL_DURE].filtre_outil
    assert MOTIFS[TRAVAIL_DURE].texte_de_l_agent and not MOTIFS[OUTIL_TARDE].texte_de_l_agent
    assert MOTIFS[MISE_EN_RELATION].moment == "action"
    # Renommés sans changer les identifiants.
    assert MOTIFS[OUTIL_TARDE].libelle_fr == "Un outil travaille"
    assert MOTIFS[TRAVAIL_DURE].libelle_fr == "Le travail de fond travaille"
    # Zéro perte : ce qui parlait avant parle encore, les deux nouveautés sont éteintes ou comme avant.
    assert MOTIFS[OUTIL_ECHOUE].actif_par_defaut is True  # l'ancien « connecteur échoue »
    assert MOTIFS[TRAVAIL_ECHOUE].actif_par_defaut is False
    assert MOTIFS[TRAVAIL_DURE].variantes_defaut == ("C'est presque bon, merci de patienter.",)


def test_la_configuration_de_l_agent_accepte_et_rend_les_regles():
    from api.schemas.workflow_configurations import WorkflowConfigurationDefaults

    configuration = WorkflowConfigurationDefaults.model_validate(
        {
            "phrases_regles": [
                {
                    "motif": OUTIL_ECHOUE,
                    "portee": "etape",
                    "etape": "Rendez-vous",
                    "etape_id": "n3",
                    "outils": ["reserver"],
                    "variantes": ["Je n'arrive pas à finaliser."],
                    "max_par_appel": 2,
                    "ensuite": {
                        "phrases": ["Un conseiller vous rappelle."],
                        "noter": {"champ": "rdv", "valeur": "à rappeler"},
                        "action": "transferer",
                        "destination": "accueil",
                    },
                }
            ]
        }
    )
    rendu = configuration.model_dump(mode="json")["phrases_regles"][0]
    assert rendu["etape_id"] == "n3" and rendu["outils"] == ["reserver"]
    assert rendu["ensuite"]["action"] == "transferer" and rendu["ensuite"]["destination"] == "accueil"
    assert rendu["ensuite"]["noter"] == {"champ": "rdv", "valeur": "à rappeler"}
    # Deux fois la même règle : refusé à l'enregistrement.
    with pytest.raises(ValidationError):
        WorkflowConfigurationDefaults.model_validate(
            {"phrases_regles": [{"motif": OUTIL_TARDE, "variantes": ["A."]}] * 2}
        )
