"""[.mark] Lot 7b-C4, canal 4 : ``texte_a_dire`` n'est plus dans le retour du modèle ; le manque est un fait. Lot 7b-C5 (décision d'Evan 25/11 8 h 45) : ce qui est rangé dans le constat caché (``CLE_DU``) est la VALEUR fermée
de ce qui manque, jamais sa phrase ; la relance du modèle la lit."""

from __future__ import annotations

import json

from api.services.actions_communes import du as DU
from api.services.actions_communes.enveloppe import verifier
from api.services.actions_communes.enveloppe_legere import pour_le_modele
from api.services.pipecat.reponse_avalee import texte_du_dernier_outil
from api.services.workflow.verite_des_actions import texte_demande_par

VALEUR = "les articles"


def _retour_d_un_manque() -> dict:
    retour = {"statut": "FAIT", "resultats": [], "faits": {}, "manque": "articles"}
    return DU.constater(retour, None, {"lignes": []}, lambda _dossier: VALEUR, 3)


def test_la_valeur_du_manque_est_dans_le_constat_caché_pas_dans_le_retour_du_modèle():
    retour = _retour_d_un_manque()
    assert "texte_a_dire" not in retour and retour[DU.CLE_DU]["manque"] == VALEUR
    assert VALEUR not in json.dumps(pour_le_modele(retour), ensure_ascii=False)  # la copie du modèle ne la porte pas
    assert DU.du_du_retour(retour).manque == VALEUR  # la parole la lit toujours (la table jette une phrase qui ne le demande pas)


def test_une_valeur_du_manque_deja_rangee_n_est_pas_recalculee():
    retour = {"statut": "FAIT", "resultats": [], "faits": {}, DU.CLE_DU: {"manque": "le jour"}}
    assert DU.constater(retour, None, {"lignes": []}, lambda _dossier: VALEUR, 3)[DU.CLE_DU]["manque"] == "le jour"


def test_les_deux_lecteurs_du_piege_4_ne_rendent_rien_apres_la_fermeture():
    """``reponse_avalee`` (réponse perdue) et ``verite_des_actions`` (affirmation sans outil) lisaient ``texte_a_dire`` du message d'outil : sans lui, ils ne proposent rien (``None``), et la relance
    de la fiche (``controler_le_silence``, ``consigne_de_relance``) ou la phrase réglée prend la main : jamais un tour muet."""
    retour = pour_le_modele(_retour_d_un_manque())
    verifier({k: v for k, v in retour.items()})
    messages = [{"role": "tool", "content": json.dumps(retour, ensure_ascii=False)}]
    assert texte_du_dernier_outil(messages) is None
    assert texte_demande_par([retour]) is None
