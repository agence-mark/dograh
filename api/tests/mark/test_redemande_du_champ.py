"""[.mark] Reconnaître qu'une phrase POSE LA QUESTION d'un champ de la fiche (B5).

Le rapprochement ne vient que des données de l'agent (nom et description du champ) : jamais une
liste de mots d'un métier. Preuve sur une fiche de garage. Au moindre doute : ``None`` (un faux
positif coûte une phrase utile).
"""

from api.services.workflow.redemande_du_champ import champ_redemande

CHAMPS = {
    "immatriculation": "Plaque d'immatriculation du véhicule",
    "kilometrage": "Kilométrage au compteur",
    "commune_garage": "Commune du garage",
    "motif": "Ce que la personne demande",
    "marque": "",
    "cv": "Puissance fiscale",
}


def test_la_question_reprend_le_nom_du_champ():
    assert champ_redemande("Quel est le kilométrage ?", ["kilometrage"], CHAMPS) == "kilometrage"
    assert champ_redemande("Et le kilometrage?", ["kilometrage"], CHAMPS) == "kilometrage"
    assert champ_redemande("Quelles sont les marques ?", ["marque"], CHAMPS) == "marque"


def test_tous_les_mots_du_nom_doivent_y_etre():
    assert (
        champ_redemande("Dans quelle commune est le garage ?", ["commune_garage"], CHAMPS)
        == "commune_garage"
    )
    # Un mot manque : le rapprochement est incertain.
    assert champ_redemande("Quelle commune ?", ["commune_garage"], CHAMPS) is None


def test_la_description_sert_quand_le_nom_est_trop_court():
    # Le nom « cv » ne dit rien seul : la description (tous ses mots) le rapproche.
    assert champ_redemande("Quelle est la puissance fiscale ?", ["cv"], CHAMPS) == "cv"
    assert champ_redemande("Quelle est la puissance ?", ["cv"], CHAMPS) is None


def test_un_rapprochement_partiel_ne_compte_pas():
    assert champ_redemande("Quelle est votre plaque ?", ["immatriculation"], CHAMPS) is None
    assert (
        champ_redemande("Pouvez-vous me donner la plaque d'immatriculation ?", ["immatriculation"], CHAMPS)
        == "immatriculation"
    )


def test_seul_un_champ_ecrit_au_meme_tour_compte():
    assert champ_redemande("Quel est le kilométrage ?", ["immatriculation"], CHAMPS) is None
    assert champ_redemande("Quel est le kilométrage ?", [], CHAMPS) is None


def test_sans_point_d_interrogation_ce_n_est_pas_une_question():
    assert champ_redemande("Merci pour le kilométrage.", ["kilometrage"], CHAMPS) is None
    assert champ_redemande("Je note le kilométrage, merci", ["kilometrage"], CHAMPS) is None


def test_seule_la_phrase_qui_pose_la_question_compte():
    assert (
        champ_redemande(
            "Merci pour le kilométrage. Quelle est la marque ?", ["kilometrage"], CHAMPS
        )
        is None
    )
    assert (
        champ_redemande(
            "Merci. Quel est le kilométrage ? Et la marque ?", ["kilometrage"], CHAMPS
        )
        == "kilometrage"
    )


def test_des_donnees_inconnues_ne_cassent_rien():
    assert champ_redemande("", ["kilometrage"], CHAMPS) is None
    assert champ_redemande("Quel est le kilométrage ?", ["inconnu"], CHAMPS) is None
    assert champ_redemande("Quel est le kilométrage ?", ["kilometrage"], {}) is None
