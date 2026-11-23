"""Lot 20 (relecture, conv4 ; D36) : « je suis allergique aux noix, il y en a dans la reine ? » : le code rendait les faits de l'allergie, mais la phrase
du modèle (« Je vérifie tout de suite ») était écrite AVANT ce retour et dite seule : les faits n'étaient jamais dits. Mécanisme commun, sans mot de
métier : un retour marqué « faits à dire après ta phrase » fait repasser le modèle, qui répond d'après eux."""

import pytest

from api.services.actions_communes import parole as PA
from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as ALLERGIE


def test_un_retour_qui_porte_des_faits_a_dire_fait_repasser_le_modele():
    retour = {"statut": "FAIT", "resultats": [], "faits": {"allergie": {"articles": [{"article": "Regina", "etat": "inconnu"}]}}, PA.CLE_FAITS_A_DIRE: True}
    d = PA.parole_du_tour(retour, "Je vérifie tout de suite pour votre allergie.", PA.EtatDuTour(tour=2), [])
    assert d.mode == PA.SECOND_PASSAGE and d.motif == PA.FAITS_A_DIRE


@pytest.mark.parametrize("deja", [False])
async def test_les_faits_de_l_allergie_sont_marques_a_dire(monkeypatch, deja):
    async def faits(source, p):
        return {"allergie": "noix", "articles": [{"article": "Regina", "etat": "inconnu"}]}

    monkeypatch.setattr(ALLERGIE, "allergie_a_donner", lambda p: "noix")
    monkeypatch.setattr(ALLERGIE, "allergie_connue", lambda p: "noix")
    monkeypatch.setattr(ALLERGIE, "faits_de_l_allergie", faits)
    monkeypatch.setattr(ALLERGIE, "noter_l_allergie_donnee", lambda p, tour: None)
    retour = {"statut": "FAIT", "faits": {}}
    await ALLERGIE.poser_les_faits_de_l_allergie(None, None, {"tour_de_l_appel": 2}, None, retour)
    assert retour["faits"]["allergie"] and retour[PA.CLE_FAITS_A_DIRE] is True
