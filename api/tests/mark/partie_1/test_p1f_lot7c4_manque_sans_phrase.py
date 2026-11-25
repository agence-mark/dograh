"""[.mark] Lot 7b-C4, canal 4 : ``texte_a_dire`` n'est plus dans le retour du modèle ; le manque est un fait, sa phrase vit dans le constat caché (``CLE_DU``) lu par le repli seul."""

from __future__ import annotations

import json

from api.services.actions_communes import du as DU
from api.services.actions_communes.enveloppe import verifier
from api.services.actions_communes.enveloppe_legere import pour_le_modele
from api.services.pipecat.reponse_avalee import texte_du_dernier_outil
from api.services.workflow.verite_des_actions import texte_demande_par

PHRASE = "Qu'est-ce que je vous mets ?"


def _retour_d_un_manque() -> dict:
    retour = {"statut": "FAIT", "resultats": [], "faits": {}, "manque": "articles"}
    return DU.constater(retour, None, {"lignes": []}, lambda _dossier: PHRASE, 3)


def test_la_phrase_du_manque_est_dans_le_constat_caché_pas_dans_le_retour_du_modèle():
    retour = _retour_d_un_manque()
    assert "texte_a_dire" not in retour and retour[DU.CLE_DU]["manque"] == PHRASE
    assert PHRASE not in json.dumps(pour_le_modele(retour), ensure_ascii=False)  # la copie du modèle ne la porte pas
    assert DU.du_du_retour(retour).manque == PHRASE  # la parole la lit toujours (reprise, jet d'une phrase qui ne la demande pas)


def test_une_phrase_du_manque_deja_rangee_n_est_pas_recalculee():
    retour = {"statut": "FAIT", "resultats": [], "faits": {}, DU.CLE_DU: {"manque": "Pour quel jour ?"}}
    assert DU.constater(retour, None, {"lignes": []}, lambda _dossier: PHRASE, 3)[DU.CLE_DU]["manque"] == "Pour quel jour ?"


def test_les_deux_lecteurs_du_piege_4_ne_rendent_rien_apres_la_fermeture():
    """``reponse_avalee`` (réponse perdue) et ``verite_des_actions`` (affirmation sans outil) lisaient ``texte_a_dire`` du message d'outil : sans lui, ils ne proposent rien (``None``), et le repli
    de la fiche (``controler_le_silence``, ``repli_dit_par_le_code``) ou la phrase générique prend la main : jamais un tour muet."""
    retour = pour_le_modele(_retour_d_un_manque())
    verifier({k: v for k, v in retour.items()})
    messages = [{"role": "tool", "content": json.dumps(retour, ensure_ascii=False)}]
    assert texte_du_dernier_outil(messages) is None
    assert texte_demande_par([retour]) is None
