"""[.mark] Mécanisme commun : les gestes de la commande sur catalogue (lot 5, E-01, E-35, T-06, T-18).

Chaque geste prend la SOURCE (le catalogue vrai), le panier de l'appel et les réglages de l'agent, et rend un ``Resultat`` fermé.
Le moteur est découpé par sujet (réglages et outils communs, préalables, articles, règlement, proposition, allergie, enregistrement,
changement d'une commande enregistrée, lecture, message) ; ce paquet garde TOUS les noms de l'ancien ``moteur.py`` : rien ne change pour ceux qui l'appellent.
"""
# ruff: noqa: F401

from __future__ import annotations

import copy
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from loguru import logger

from api.db.bases_clients import dates_futures, recherche_liste
from api.schemas.apres_appel import numero_e164
from api.db.bases_clients.recherche_liste import Element
from api.db.bases_clients.recherche_liste_moteur import norme_de_recherche
from api.services.commande import lecture, panier as P, tailles
from api.services.commande.briques import art3, conditions_de_vente, dec1, dec2, for1, for2, for6, for10, for12, for15, inconnue, inf1, inf2, inf3, inf4, inf5, inf6, inf7, off3, opt1, opt6, prx2, prx5, prx6, qte1, qte2, taille
from api.services.commande.briques import formule as FO
from api.services.mots_dits import chiffres_en_lettres, liste_dite, liste_dite_et, montant_en_lettres, nom_dit, nombre_en_lettres, phrase_nette
from api.services.commande.resultat import Resultat, avec_numero_affiche, avec_numeros_retenus
from api.services.phrases.catalogue import APRES_ENREGISTREMENT, MOTIFS as MOTIFS_DES_PHRASES, NUMERO_AFFICHE_GARDE, NUMERO_DICTE_RELU
from api.services.commande.source import Source
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.types import Adresse, MomentVoulu
from api.services.commande.moteur.socle import (
    Appelant,
    CLE_NOTES_DU_GREFFIER,
    LONGUEUR_NOTE,
    NON_CONFIRMABLE,
    RAISON_ALLERGIE,
    Reglages,
    _MOTS_DE_LA_QUESTION,
    _PAS_SUR,
    _PERDUES,
    _PETITS_MOTS,
    _PLUS_DE_NOMS,
    _avec,
    _dit,
    _le,
    _mots_significatifs,
    _phrase_d_une_remise_appliquee,
    _r,
    _racines,
    _sans_accent,
    cle_de_la_remise,
    commande_de_l_appel,
)
from api.services.commande.moteur.prealables import (
    CLES_DE_L_ETAT,
    _article_de_la_carte,
    _avec_le_moment,
    _chiffrer,
    _minimum_de_l_adresse,
    _mode_dit,
    _phrase_des_modes,
    _poser_le_mode,
    _prealables,
    _resoudre_l_heure_du_lieu,
    _rien_n_est_pris,
    _sans_jour_dit,
    _servi_le,
    _valider,
    _zone_id,
    adresse_verifiee,
    annoncer_la_fermeture,
    choisir_mode,
    etat_ouverture,
    exiger_une_voie,
    garder_l_heure,
    heure_annoncee,
    heure_du_lieu,
    lire_l_ouverture,
    mode_implique_par_l_adresse,
    poser_l_heure,
    poser_le_moment,
    proposer_un_autre_mode_hors_zone,
    question_du_mode,
    resoudre_l_heure_selon_l_ouverture,
    resoudre_une_date,
    retenir_la_seule_commune_livree,
    verifier_adresse,
    verifier_le_creneau,
    voie_de_l_adresse,
)
from api.services.commande.moteur.articles import (
    CLE_OPTION_DITE,
    CLE_REFERENCES,
    CLE_REF_CHOISIE,
    RAISON_QUANTITE_INFERIEURE_A_UN,
    _LIAISON_AVANT_MOITIE,
    _MOTS_DE_LIAISON,
    _UNITES_EN_MOTS,
    _UNITE_DITE,
    _appliquer_les_choix,
    _appliquer_les_defauts,
    _appliquer_les_retraits,
    _article_de_la_fiche,
    _bloque_l_ajout,
    _ce_qui_se_choisit,
    _chercher_dans,
    _chercher_l_article,
    _choisir,
    _compte,
    _dans_la_composition,
    _declinaison_choisie,
    _declinaison_dite,
    _departager_par_la_taille,
    _est_le_nom,
    _etat_apres_ajout,
    _faits_du_poids_et_du_lot,
    _fusionner,
    _groupes_a_remplir,
    _ligne_dite,
    _minimum_non_atteint,
    _moities_choisies,
    _niveau,
    _noter,
    _noter_un_retrait_par_moitie,
    _noter_une_regle_inconnue_de_la_carte,
    _option_dite,
    _options_disponibles,
    _phrase_de_la_question,
    _phrase_des_lignes,
    _question,
    _question_de_rangement,
    _rang,
    _repondre,
    _repondre_aux_attentes,
    _reprendre_les_dits,
    _retrait_et_moitie,
    _sans_le_nom_du_groupe,
    _taille_dans,
    _travailler_une_ligne,
    _trouver_la_ligne,
    _un_article,
    _un_seul_candidat,
    _unites_dites,
    a_la_taille_de_la_formule,
    ajouter_un_article,
    changer_la_taille,
    choix_sans_objet,
    contenu_dit,
    lots_des_quantites_hautes,
    mettre_en_attente_du_prealable,
    modifier,
    noter_la_commande,
    placer_les_choix,
    poser_le_code_de_remise,
    remplacer_un_choix,
    retirer,
    retirer_sur_le_plat,
    retrait_en_note,
    vider_commande,
)
from api.services.commande.moteur.reglement import (
    _ce_qui_a_change,
    _centimes,
    _cle_de_ligne,
    _cle_lue,
    _instantane,
    _le_reglement,
    _majuscule,
    _numero_dit,
    _relecture_deja_dite,
    dire_le_rendu_de_monnaie,
    le_seul_moyen_de_sa_famille,
    recapituler,
    regler,
)
from api.services.commande.moteur.proposition import (
    _peut_parler_d_offre,
    proposer_un_article_en_plus,
    repondre_a_la_proposition,
)
from api.services.commande.moteur.allergie import (
    BORNE_DES_ARTICLES_D_ALLERGIE,
    CLES_DE_L_ALLERGIE_DONNEE,
    _LA_LISTE,
    _NON_GARANTI,
    _articles_de_la_carte_concernes,
    _bornee,
    _consigne_d_allergie,
    _est_la_liste_demandee,
    _etat_de_l_allergene_par_ligne,
    _faits_d_un_allergene,
    _faits_du_prix,
    _informations_de_la_fiche,
    _lecture_de_la_formule,
    _libelle_de_l_allergene,
    _nomme_une_categorie,
    _option_signale,
    _options_de_la_fiche,
    _options_obligatoires,
    _regime_dit,
    _regime_du_catalogue,
    _regles_d_information,
    _signalement_d_un_mot,
    _signalement_dit,
    _signalements_dits,
    _signature_de_la_ligne,
    allergie_a_donner,
    allergie_connue,
    allergie_sans_reponse,
    faits_a_redonner_pour_les_lignes_nouvelles,
    faits_de_l_allergie,
    lignes_sans_faits_d_allergie,
    noter_l_allergie_donnee,
    rouvrir_l_allergie_non_dite,
)
from api.services.commande.moteur.enregistrement import (
    CONSIGNE_AUCUNE,
    TYPE_DE_LA_QUESTION_DU_NUMERO,
    _brouillon_de_la_commande,
    _consigne_du_livreur,
    _finaliser,
    _note_de_la_commande,
    _relire_le_numero_dicte,
    demander_la_consigne_livreur,
    enregistrer,
    finaliser,
    identifier,
    question_de_la_ligne_en_attente,
    repondre_au_numero_affiche,
    repondre_au_numero_dicte,
    retenir_une_habitude,
)
from api.services.commande.moteur.changement import (
    _manque_pour_remplacer,
    _permet_l_annulation,
    annulation_possible,
    annuler_commande_enregistree,
    changer_commande_enregistree,
)
from api.services.commande.moteur.lecture import (
    _CONTIENT,
    _SANS,
    _SANS_INGREDIENT,
    _chercher_ce_qui_est_sans,
    _contient_l_ingredient,
    _de,
    _etat_sans,
    _etat_sans_pour_tous,
    _noter_dite,
    _sans_article,
    chercher_par_ingredient,
    ingredient_demande,
    remises_disponibles,
    retrouver_commande,
    voir_commande,
    voir_la_carte,
    voir_produit,
)
from api.services.commande.moteur.message import (
    envoyer_un_message,
)
