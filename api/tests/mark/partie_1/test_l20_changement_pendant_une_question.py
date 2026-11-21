"""Lot 20 (relecture réplique par réplique, H2, H4, H8, n10) : « en fait trois margherita » pendant la relecture : le modèle écrivait le changement mais citait
la question d'avant (Q-1 pour Q-2), ou ne citait rien : la fiche entière était refusée (« rien n'est changé ») et la relecture tournait en boucle.
Garde sur l'état (comme C7) : une fiche qui CHANGE la commande quand une question attend vaut « autre » pour cette question : la question reste posée,
le changement s'applique, la relecture repart. Jamais « accepte » ni « refuse » déduits."""

from api.services.commande.porte import un_changement_repond_autre

RELECTURE = {"id": "Q-2", "type": "relecture", "texte": "Je vous relis : deux Margherita Normale. C'est bon ?"}


def test_un_changement_qui_cite_la_question_d_avant_repond_autre():
    fiche = {"a_dire": "Je rectifie.", "changer_quantite": [{"ligne": 1, "quantite": 3}], "reponse": {"question_id": "Q-1", "sens": "autre"}}
    assert un_changement_repond_autre(fiche, RELECTURE)["reponse"] == {"question_id": "Q-2", "sens": "autre"}


def test_un_changement_sans_reponse_repond_autre():
    fiche = {"a_dire": "Je passe en livraison.", "mode_de_retrait": "livraison", "adresse": "4 rue de Beauvais", "commune": "Chantilly"}
    assert un_changement_repond_autre(fiche, RELECTURE)["reponse"] == {"question_id": "Q-2", "sens": "autre"}


def test_un_accord_n_est_jamais_deduit():
    fiche = {"a_dire": "Parfait.", "moyen_de_paiement": "carte_bancaire", "reponse": {"question_id": "Q-1", "sens": "accepte"}}
    assert un_changement_repond_autre(fiche, RELECTURE) == fiche  # pas un changement : la fiche reste telle quelle (et sera refusée)
    juste = {"a_dire": "Je rectifie.", "changer_quantite": [{"ligne": 1, "quantite": 3}], "reponse": {"question_id": "Q-2", "sens": "accepte"}}
    assert un_changement_repond_autre(juste, RELECTURE) == juste  # la bonne question citée : rien n'est réécrit
    assert un_changement_repond_autre(fiche, None) == fiche
