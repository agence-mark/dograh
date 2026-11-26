"""[.mark] Mécanisme commun : les gestes de la commande sur catalogue (lot 5, E-01, E-35, T-06, T-18).

Chaque geste prend la SOURCE (le catalogue vrai), le panier de l'appel et les réglages de l'agent, et rend un ``Resultat`` fermé.
Le moteur est découpé par sujet (réglages et outils communs, préalables, mode et adresse, articles, règlement, proposition, enregistrement, changement d'une commande
enregistrée, lecture, message). Cette façade ne garde que les noms PUBLICS que la porte, les outils et les tests appellent ; un nom privé se lit dans son module.
"""

from __future__ import annotations

from api.services.commande.resultat import Resultat

from api.services.commande.moteur.socle import (
    Appelant,
    CLE_NOTES_DU_GREFFIER,
    METIER,
    NON_CONFIRMABLE,
    Reglages,
    cle_de_la_remise,
    commande_de_l_appel,
    faits_du_metier_a_donner,
    phrase_d_une_remise_appliquee,
    noter_les_faits_donnes,
)
from api.services.commande.moteur.prealables import (
    chiffrer_le_panier,
    etat_ouverture,
    heure_annoncee,
    heure_du_lieu,
    lire_l_ouverture,
    poser_l_heure,
    question_du_mode,
    resoudre_une_date,
    retenir_la_seule_commune_livree,
)
from api.services.commande.moteur.mode_et_adresse import (
    choisir_mode,
    verifier_adresse,
)
from api.services.commande.moteur.articles import (
    CLE_CANDIDATS,
    CLE_OPTION_DITE,
    CLE_REF_CHOISIE,
    ajouter_un_article,
    chercher_l_article,
    contenu_dit,
    etat_apres_ajout,
    lots_des_quantites_hautes,
    modifier,
    noter_la_commande,
    placer_les_choix,
    poser_le_code_de_remise,
    repondre_a_un_choix,
    retirer,
    vider_commande,
)
from api.services.commande.moteur.reglement import (
    rendu_de_monnaie,
    poser_la_relecture,
    relecture_entendue,
)
from api.services.commande.moteur.proposition import (
    proposer_un_article_en_plus,
    repondre_a_la_proposition,
)
from api.services.commande.moteur.enregistrement import (
    TYPE_DE_LA_QUESTION_DU_NUMERO,
    finaliser,
    noter_le_client,
    question_de_la_ligne_en_attente,
    repondre_au_numero_affiche,
    repondre_au_numero_dicte,
)
from api.services.commande.moteur.changement import (
    annulation_possible,
    annuler_commande_enregistree,
    changer_commande_enregistree,
)
from api.services.commande.moteur.lecture import (
    remises_disponibles,
    retrouver_commande,
    voir_commande,
    voir_la_carte,
)
from api.services.commande.moteur.message import (
    envoyer_un_message,
)

__all__ = [
    "Resultat",
    "Appelant",
    "CLE_NOTES_DU_GREFFIER",
    "CLE_CANDIDATS",
    "CLE_OPTION_DITE",
    "CLE_REF_CHOISIE",
    "METIER",
    "NON_CONFIRMABLE",
    "Reglages",
    "TYPE_DE_LA_QUESTION_DU_NUMERO",
    "ajouter_un_article",
    "annulation_possible",
    "annuler_commande_enregistree",
    "changer_commande_enregistree",
    "chercher_l_article",
    "chiffrer_le_panier",
    "choisir_mode",
    "cle_de_la_remise",
    "commande_de_l_appel",
    "contenu_dit",
    "rendu_de_monnaie",
    "envoyer_un_message",
    "etat_apres_ajout",
    "etat_ouverture",
    "faits_du_metier_a_donner",
    "finaliser",
    "heure_annoncee",
    "heure_du_lieu",
    "lire_l_ouverture",
    "lots_des_quantites_hautes",
    "modifier",
    "noter_la_commande",
    "noter_le_client",
    "phrase_d_une_remise_appliquee",
    "placer_les_choix",
    "poser_l_heure",
    "poser_la_relecture",
    "relecture_entendue",
    "poser_le_code_de_remise",
    "proposer_un_article_en_plus",
    "question_de_la_ligne_en_attente",
    "question_du_mode",
    "remises_disponibles",
    "repondre_a_la_proposition",
    "repondre_a_un_choix",
    "repondre_au_numero_affiche",
    "repondre_au_numero_dicte",
    "resoudre_une_date",
    "retenir_la_seule_commune_livree",
    "retirer",
    "retrouver_commande",
    "noter_les_faits_donnes",
    "verifier_adresse",
    "vider_commande",
    "voir_commande",
    "voir_la_carte",
]
