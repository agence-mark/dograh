"""[.mark] Lot 7b-C4, canal 4 : ``texte_a_dire`` n'est plus dans le retour du modèle ; le manque est un fait. Lot 7b-C5 (décision d'Evan 25/11 8 h 45) : ce qui est rangé dans le constat caché (``CLE_DU``) est la VALEUR fermée
de ce qui manque, jamais sa phrase ; la relance du modèle la lit."""

from __future__ import annotations

import json

from api.services.actions_communes import du as DU
from api.services.actions_communes.enveloppe_legere import pour_le_modele

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
