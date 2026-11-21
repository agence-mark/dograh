"""Lot 20 (banc final, a310, H8, H9) : pendant la relecture, l'état lu par le modèle dit qu'un oui qui donne en plus une case ouverte est « accepte »."""

from api.services.commande import etat_pour_le_modele as E
from api.services.commande import panier as P


def test_la_relecture_dit_qu_un_oui_avec_le_paiement_est_accepte():
    fiche = {P.CLE: {"lignes": [{"n": 1, "article": "Margherita", "quantite": 2, "variante": "Sénior", "prix_unitaire": 950}], "mode": "emporter",
                          "question": {"id": "Q-1", "type": "relecture", "texte": "Je vous relis : deux Margherita Sénior, à emporter. C'est bon ?"}}}
    etat = E.texte(fiche) or ""
    assert "(« oui, par carte ») est accepte" in etat
    assert "après son accord" not in etat
