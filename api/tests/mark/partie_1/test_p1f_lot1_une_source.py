"""[.mark] Plan final Partie 1, lot 1, « une source par donnée » (n° 43 hors lot, 70, 82, 85, 86, 94, 97, 132, 134, L2, L3, L4, M8).

Chaque donnée vit à UN endroit ; ce fichier prouve deux choses : ce qui est rendu est EXACTEMENT ce qui était écrit avant (valeurs d'avant recopiées ici en
littéral), et plus rien d'autre dans le code ne porte la même donnée.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime, time

from api.outils import inventaire_rustines as I
from api.services.actions_communes import euros as EU
from api.services.actions_communes import moyens_de_paiement as MP
from api.services.actions_communes import phrases_d_information as INFO
from api.services.actions_communes import petits_mots as PM
from api.services.phrases import catalogue as CAT

API = I.RACINE_API


def _sources(*dossiers: str):
    for d in dossiers:
        for p in sorted((API / d).rglob("*.py")):
            if "tests" not in p.parts and "__pycache__" not in p.parts:
                yield p, p.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- n° 70 : les petits mots

def test_les_petits_mots_rendus_sont_ceux_d_avant():
    assert PM.LIAISON_D_UNE_COMPOSITION == frozenset({"de", "du", "des", "la", "le", "les", "l", "un", "une", "sans", "avec", "en", "et"})
    assert PM.RENVOI_A_UNE_LIGNE == frozenset({"la", "le", "les", "l", "de", "du", "des", "un", "une", "ligne", "celle", "celui", "ci"})
    from api.services.actions_communes.forme import VIDES
    from api.services.commande.moteur.socle import _MOTS_DE_LA_QUESTION

    assert VIDES == {"le", "la", "les", "l", "au", "aux", "a", "de", "du", "des", "d", "et", "c", "est", "pour", "en", "un", "une"}
    assert _MOTS_DE_LA_QUESTION == frozenset({
        "un", "une", "des", "de", "du", "d", "la", "le", "les", "l", "vous", "avez", "auriez", "est", "ce", "que", "qu", "quoi", "qui", "il", "y", "a",
        "en", "pour", "moi", "nous", "quelque", "chose", "choses", "truc", "trucs", "rien", "autre", "aussi", "chez", "votre", "vos"})


def test_aucune_liste_de_petits_mots_hors_de_leur_module():
    """Une liste de cinq articles ou plus, écrite à la main dans le moteur, est une seconde source : elle doit dériver de ``ARTICLES``."""
    fautes = []
    for p, source in _sources("services/commande", "services/actions_communes", "services/reservation"):
        if p.name == "petits_mots.py":
            continue
        for n in ast.walk(ast.parse(source)):
            elements = n.elts if isinstance(n, (ast.Set, ast.List, ast.Tuple)) else None
            if elements and sum(1 for e in elements if isinstance(e, ast.Constant) and e.value in PM.ARTICLES) >= 5:
                fautes.append(f"{p.relative_to(API).as_posix()}:{n.lineno}")
    assert not fautes, fautes


# --------------------------------------------------------------------------- n° 85, 132, L3 : les moyens de paiement

def test_les_moyens_de_paiement_rendus_sont_ceux_d_avant():
    assert MP.MOYEN_DE_BASE_SELON_LA_FICHE == {"carte_bancaire": "carte", "especes": "especes", "titre_restaurant": "titre_restaurant",
                                               "carte_bancaire_a_la_livraison": "carte_livraison"}
    assert list(MP.MOYEN_DE_BASE_SELON_LA_FICHE) == ["carte_bancaire", "especes", "titre_restaurant", "carte_bancaire_a_la_livraison"]
    assert MP.LIBELLES_POUR_LE_MODELE == {"carte_bancaire": "carte", "carte": "carte", "especes": "espèces", "titre_restaurant": "titre-restaurant",
                                          "carte_bancaire_a_la_livraison": "carte à la livraison"}
    assert MP.LIBELLES_DITS == {"carte": "par carte", "especes": "en espèces", "titre_restaurant": "en titres-restaurant", "cheque": "par chèque",
                                "en_ligne": "en ligne", "carte_livraison": "par carte à la livraison"}
    assert MP.ABREGES == {"carte": "CB", "especes": "ESP", "titre_restaurant": "TR", "cheque": "CHQ", "en_ligne": "WEB", "carte_livraison": "CBL"}
    assert MP.LIBELLES_DE_LA_CAISSE == {"carte": "Carte bancaire", "especes": "Espèces", "titre_restaurant": "Titre-restaurant", "cheque": "Chèque",
                                        "carte_livraison": "Carte bancaire à la livraison"}
    assert MP.MOYENS_DU_FORMULAIRE == ("carte", "especes", "titre_restaurant", "cheque", "carte_livraison")
    assert MP.RESERVES_AU_MODE == {"carte_livraison": ("livraison",)}
    assert MP.MOYENS_PAR_DEFAUT == ("carte", "especes")


def test_la_valeur_stockee_ne_change_pas_et_le_schema_de_l_ecran_suit_la_table():
    """``carte_livraison`` reste la clé de la base ; le type de l'écran liste exactement les clés de la table."""
    from typing import get_args

    from api.schemas.restauration_ecran import MoyenDePaiement

    assert "carte_livraison" in MP.CLES_DE_BASE and "carte_bancaire_a_la_livraison" not in MP.CLES_DE_BASE
    assert set(get_args(MoyenDePaiement)) == set(MP.CLES_DE_BASE)


def test_les_modules_lisent_la_table_unique_des_moyens():
    from api.db.bases_clients import restauration_ecran, restauration_reglage
    from api.services.commande import etat_pour_le_modele, porte
    from api.services.gabarits import formulaire
    from api.services.restauration import source_commande
    from api.services.restauration.caisse.prises import hubrise_traduction

    assert source_commande.SourceClasseur.libelles_des_moyens is MP.LIBELLES_DITS
    assert source_commande.SourceClasseur.moyens_reserves_au_mode is MP.RESERVES_AU_MODE
    assert etat_pour_le_modele.LIBELLES_POUR_LE_MODELE is MP.LIBELLES_POUR_LE_MODELE
    assert hubrise_traduction.LIBELLE_MOYEN is MP.LIBELLES_DE_LA_CAISSE
    assert formulaire.MOYENS is MP.MOYENS_DU_FORMULAIRE
    assert restauration_reglage.MOYENS_PAR_DEFAUT is MP.MOYENS_PAR_DEFAUT and restauration_ecran.MOYENS_PAR_DEFAUT is MP.MOYENS_PAR_DEFAUT
    assert not hasattr(porte, "MOYENS_DE_LA_FICHE")


def test_aucune_table_des_moyens_ecrite_a_la_main_dans_le_code():
    """Un dictionnaire dont une clé est un moyen (``especes``…) n'est écrit nulle part ailleurs que dans la table."""
    fautes = []
    for p, source in _sources("services", "db"):
        if p.name == "moyens_de_paiement.py":
            continue
        for n in ast.walk(ast.parse(source)):
            if isinstance(n, ast.Dict):
                cles = {k.value for k in n.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
                if len(cles & {"especes", "titre_restaurant", "carte_livraison", "carte_bancaire"}) >= 2:
                    fautes.append(f"{p.relative_to(API).as_posix()}:{n.lineno}")
    assert not fautes, fautes


# --------------------------------------------------------------------------- n° 94 : les euros

def test_le_format_des_euros_est_unique_et_celui_d_avant():
    assert [EU.en_euros(c) for c in (0, 5, 50, 1250, 100000)] == ["0,00 €", "0,05 €", "0,50 €", "12,50 €", "1000,00 €"]


def test_aucune_autre_copie_du_format_des_euros():
    fautes = [f"{p.relative_to(API).as_posix()}" for p, s in _sources("services", "db") if p.name != "euros.py" and re.search(r"// 100\},\{[^}]*% 100:02d\} €", s)]
    assert not fautes, fautes


# --------------------------------------------------------------------------- n° 97 : la coupure du jour de service

def test_la_coupure_de_six_heures_est_ecrite_une_fois_et_la_migration_dit_la_meme():
    from api.db.bases_clients import horaires_caisse, restauration_commun

    assert restauration_commun.DEBUT_DU_JOUR_DE_SERVICE == time(6, 0)
    assert horaires_caisse.CUTOFF_PAR_DEFAUT is restauration_commun.DEBUT_DU_JOUR_DE_SERVICE
    migration = (API / "db" / "bases_clients" / "migrations" / "050-fin-du-service-en-instant.sql").read_text(encoding="utf-8")
    assert f"time '{restauration_commun.DEBUT_DU_JOUR_DE_SERVICE:%H:%M}'" in migration, "la migration jouée une fois porte la même coupure"


# --------------------------------------------------------------------------- n° 134 : la règle de période

def test_la_periode_couvre_le_debut_et_exclut_la_fin():
    from api.db.bases_clients.restauration_commun import couvre

    a, b, c = (datetime(2026, 11, j, 12, tzinfo=UTC) for j in (10, 15, 20))
    assert couvre(a, c, b) and couvre(a, c, a) and not couvre(a, c, c)
    assert couvre(None, c, b) and couvre(a, None, b) and couvre(None, None, b)
    assert not couvre(b, c, a)


# --------------------------------------------------------------------------- L4 : l'ordre des cases lu dans le contrat

def test_l_ordre_des_cases_de_fin_est_celui_du_contrat():
    from api.services.commande import contrat, porte

    ordre = list(porte.ORDRE_DES_CASES)
    debut = ordre.index(contrat.CASES_DE_FIN[0])
    assert ordre[debut:debut + len(contrat.CASES_DE_FIN)] == list(contrat.CASES_DE_FIN)
    assert ordre == [
        "vider_le_panier", "annuler_la_commande", "annuler_une_commande_enregistree", "reponse", "retirer_article", "changer_quantite", "ajouter",
        "mode_de_retrait", "adresse", "commune", "consigne_livreur", "heure", "moyen_de_paiement", "rendu_sur", "part", "moyen_reste", "telephone", "prenom",
        "note_generale", "code_de_remise", "reduction_annoncee", "c_est_tout"]
    assert porte.INFORMATIONS == ("mode_de_retrait", "adresse", "commune", "consigne_livreur", "heure", "moyen_de_paiement", "rendu_sur", "part",
                                  "moyen_reste", "telephone", "prenom", "note_generale", "code_de_remise", "reduction_annoncee")


# --------------------------------------------------------------------------- M8 : ce qui manque est une valeur fermée

def test_le_manque_se_donne_par_sa_valeur_fermee_sans_lire_de_texte():
    from api.services.commande import etat_pour_le_modele as E
    from api.services.commande import panier as P
    from api.services.commande import phrases_du_manque as PMQ

    connu = {"modes": {"emporter": "à emporter", "livraison": "en livraison"}, "modes_a_adresse": ["livraison"]}
    manque, modes = E.ce_qui_manque(P.nouveau(), connu)
    assert manque is PMQ.Manque.MODE and modes == ("à emporter", "en livraison")
    assert E.ce_qui_manque_ensuite(P.nouveau(), connu) == "le mode de retrait (à emporter ou en livraison)"


def test_la_decision_autre_chose_lit_le_membre_pas_un_texte():
    from api.services.commande import porte
    from api.services.commande.phrases_du_manque import Manque
    from api.services.commande import etat_pour_le_modele as E, panier as P

    p = {**P.nouveau(), "mode": "emporter", "lignes": [{"n": 1, "quantite": 1, "code": "x"}]}
    assert E.ce_qui_manque(p, {})[0] is Manque.AUTRE_CHOSE and porte.seul_autre_chose_manque(p)
    relue = {**p}
    from api.services.commande import etape as E_
    E_.transition(relue, E_.RELECTURE_POSEE, relecture={"x": 1})  # la relecture est posée par l'étape, jamais par un fait écrit à la main
    assert not porte.seul_autre_chose_manque(relue)


# --------------------------------------------------------------------------- L2, n° 82, 86 : les phrases du code
# 7b-C6 n° 12 (décision d'Evan, 25/11 9 h 30, § 8 bis) : le module des phrases d'avant est supprimé ; la liste fermée ``PHRASES_DU_CODE`` (motifs réglés du catalogue)
# le remplace : le total, le numéro, le rendu, et les phrases déjà réglées (numéro dicté relu, numéro affiché gardé, M108) (garde : test_p1f_lot7c6_phrases_du_code.py).

def test_chaque_phrase_du_code_est_un_motif_regle_de_la_liste_fermee():
    assert CAT.PHRASES_DU_CODE == {
        CAT.TOTAL_RELECTURE, CAT.TOTAL_APRES_CORRECTION, CAT.TOTAL_APRES_CHANGEMENT, CAT.RENDU_DE_MONNAIE, CAT.NUMERO_RETENU,
        CAT.NUMERO_DICTE_RELU, CAT.NUMERO_AFFICHE_GARDE, CAT.APRES_ENREGISTREMENT,
    }
    assert all(CAT.MOTIFS[m].variantes_defaut for m in CAT.PHRASES_DU_CODE)
    # ni DC5, ni le repli de panne (audit du lot 1)
    assert not [k for k in CAT.PHRASES_DU_CODE if "panne" in k or "nouvelle" in k]
    assert not (API / "services" / "commande" / "phrases_dites_par_le_code.py").exists()


def test_les_phrases_dites_par_le_code_sont_celles_d_avant_mot_pour_mot():
    assert "nouvelle_commande" not in CAT.PHRASES_DU_CODE, "DC5 n'est pas une phrase du code : un refus suivi d'une question, que le modèle dit"
    assert INFO.NOUVELLE_COMMANDE_PROPOSEE == "Votre commande est annulée, je ne peux plus rien y ajouter. Voulez-vous en passer une nouvelle ?"
    # C6 n° 5 à 7 (décision d'Evan 25/11 9 h 30) : la confirmation, le changement et l'annulation passent au modèle ; C7 B9 : leurs textes de secours sont supprimés, le
    # journal garde le fait accompli en faits (``fait`` : enregistree, changee, annulee, annulee_en_cours ; ``quand_dit``, ``total``), vérifié par ``test_p1f_lot7c7_fait_accompli_en_faits``


def test_les_appelants_disent_la_phrase_du_registre_des_phrases_du_code():
    from api.services.commande import registre

    p = {"enregistree": {"total": 2180}}
    assert registre.TEXTE_NOUVELLE_COMMANDE == INFO.NOUVELLE_COMMANDE_PROPOSEE
    # C6 n° 7 (décision d'Evan 25/11 9 h 30) : la question DC4 n'a plus de texte du code ; le montant d'aujourd'hui, en lettres, est exigé de la phrase du modèle
    assert registre.montant_enregistre_dit(p) == "vingt et un euros quatre-vingts" and registre.montant_enregistre_dit({}) is None and not hasattr(registre, "texte_de_l_annulation")
    assert not hasattr(registre, "texte_du_changement")  # C6 n° 6 (décision d'Evan 25/11 9 h 30) : le code ne compose plus le changement


def test_une_phrase_du_code_n_est_ecrite_nulle_part_ailleurs():
    """C6 n° 12 : chaque variante d'un motif de la liste fermée n'est écrite qu'au catalogue (le code la dit par le motif, jamais par un texte recopié)."""
    fautes = []
    for m in sorted(CAT.PHRASES_DU_CODE):
        for v in CAT.MOTIFS[m].variantes_defaut:
            debut = v.split("{")[0].strip()
            if len(debut) < 20:
                continue
            for p, source in _sources("services", "db"):
                if p.parts[-2:] != ("phrases", "catalogue.py") and debut in source:
                    fautes.append(f"{p.relative_to(API).as_posix()} : « {debut} »")
    assert not fautes, fautes


def test_les_phrases_d_information_sont_celles_d_avant_et_rangees_une_fois():
    from api.services.actions_communes import phrases_d_information as INFO
    from api.services.commande.moteur import socle
    from api.services.service_client import action

    assert INFO.NON_CONFIRMABLE == "Je ne peux pas vous le confirmer." == action.PHRASE_INCONNUE
    assert not hasattr(socle, "NON_CONFIRMABLE")  # C7 B5 (Evan 25/11 8 h 45) : la commande ne la compose plus, ``renseigne`` faux la porte
    assert INFO.PAS_SUR == socle._PAS_SUR == "la fiche ne le précise pas, l'équipe peut vous répondre."
    assert INFO.NON_GARANTI == "je ne peux pas le garantir : l'équipe peut vous le confirmer."
    assert INFO.POUR_LES_AUTRES_NON_GARANTI == "Pour les autres, je ne peux pas le garantir."
    assert INFO.SOURCE_FICHE == "D'après la fiche" and INFO.SOURCE_ARTICLES == "D'après nos articles" and INFO.SOURCE_FICHE_DU_RESTAURANT == "D'après la fiche du restaurant"
    fautes = [p.relative_to(API).as_posix() for p, s in _sources("services") if p.name != "phrases_d_information.py" and ("D'après la fiche, " in s or "D'après nos articles, " in s)]
    assert not fautes, fautes


def test_la_liste_des_phrases_a_rendre_au_modele_existe_et_ne_cite_pas_le_registre():
    texte = (API / "outils" / "phrases-a-rendre-au-modele.md").read_text(encoding="utf-8")
    assert texte.count("\n| `") > 100
    assert "Je vous confirme l'annulation de votre commande." not in texte
