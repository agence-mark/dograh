"""Lot 20 (Evan, 21/11 : « 3 conversations c'est bien ») : la porte d'un client = les contrôles du code (sans modèle) et les 3 conversations sur sa
carte ; la série de base se joue une fois par version du gabarit, jamais par client (règle d'Evan, 20/11). Avant, chaque client recevait la série de
base en tests obligatoires (≈ 1 400 tests à rejouer sur le chantier pour diffuser une version)."""

from api.services.gabarits import tests_generes as TG


def test_la_serie_de_base_n_est_pas_obligatoire_pour_un_client():
    serie = TG._test("Série de base S1 : x", "serie_de_base", "S1", etape="commande", version_gabarit="restauration@4", scenario="x", garantie="y")
    assert serie["obligatoire"] is False


def test_les_controles_du_code_et_les_conversations_de_la_carte_restent_obligatoires():
    article = TG._test("Article de la carte : Reine", "article", "reine", etape="commande", version_gabarit="restauration@4")
    conversation = TG._test("Conversation sur la carte : a", "conversation", "a", etape="commande", version_gabarit="restauration@4", scenario="x")
    assert article["obligatoire"] is True and conversation["obligatoire"] is True
    assert TG.NB_CONVERSATIONS == 3
