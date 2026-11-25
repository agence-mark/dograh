"""[.mark] Lot 7b-C7a, commit 0 : toute valeur qu'un texte de secours disait est dans le signal que lit le modèle.

Evan, 25/11 : « ce n'est pas juste une suppression ». Un texte de secours est vidé seulement quand tout ce qu'il apprend à la personne (statut, raison ou manque qui
distingue le refus, puis chaque valeur) existe dans ce que le modèle reçoit (``aides_signal.signal``) : un cas par texte des fichiers de C7a. Une valeur manquante est un
xfail strict (``raises=AssertionError``) qui passe au vert dans le commit du fait (F1, F2, F7, F8, F9). La comparaison est sur une valeur entière, jamais une sous-chaîne.

``valeurs`` : ``(forme dans le signal, forme dans le texte)``, ou une fonction du retour qui les rend. ``test_la_table_est_fidele_au_texte`` prouve que la table dit bien ce
que disait le texte (elle sort avec les textes).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

import pytest

from api.db.bases_clients import restauration_zone as Z
from api.db.bases_clients import textes_de_secours_commande as TSC
from api.services.actions_communes import phrases_d_information as INFO
from api.services.actions_communes.forme import norm
from api.services.commande import moteur, panier as P, textes_de_secours as TS
from api.services.commande.briques import formule as FO
from api.services.commande.moteur import articles, changement
from api.services.commande.moteur.socle import Appelant, Reglages
from api.services.restauration.appel_et_memoire.appel import Lieu
from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as A_
from api.services.restauration.carte_et_allergenes import textes_de_secours as TSA
from api.services.restauration.carte_et_allergenes import voir_un_article as V_
from api.services.restauration.source_commande import resolution_du_jour_et_de_l_heure
from api.tests.mark import test_base_client as _BASE
from api.tests.mark import test_restauration_classeur_commande as _CLASSEUR
from api.tests.mark import test_restauration_commande_panier as _PANIER
from api.tests.mark import test_restauration_zones as ZONES
from api.tests.mark.commande_sur_la_fiche import article as ART
from api.tests.mark.partie_1.aides_briques import brique
from api.tests.mark.partie_1.aides_signal import (
    Carte, Cas, SourceAllergie, article_de_carte, controler, etape_de_boissons, feuilles, fiche, fidele, formule_du_menu, jouer, option, pareilles, parametres, signal,
)
from api.tests.mark import test_commande_kebab_sa52 as _KEBAB

base_essai, base_prete, commerce = _BASE.base_essai, _BASE.base_prete, _CLASSEUR.commerce  # les fixtures du classeur, reprises sans import inutile
kebab, ADRESSE, AppelKebab = _KEBAB.kebab, _KEBAB.ADRESSE, _KEBAB.Appel
PARIS = ZoneInfo("Europe/Paris")
MATIN = datetime(2026, 11, 17, 10, 50, tzinfo=PARIS)
SOIR = datetime(2026, 11, 17, 20, 0, tzinfo=PARIS)


# ── les scénarios (le vrai moteur ; ce sont ceux des tests de C1 à C3) ───────────────────────────────────────────────────

KETCHUP, MAYO = {"code": "A", "nom": "Ketchup", "rupture": False}, {"code": "B", "nom": "Mayonnaise", "rupture": False}


def _groupe(maximum: int, par_option: int) -> dict:
    return {"id": "g", "nom": "Sauces", "role": "sauce", "min": 0, "max": maximum, "max_par_option": par_option, "options": [KETCHUP, MAYO]}


def _noms(liste) -> list[str]:
    return [x["nom"] if isinstance(x, dict) else str(x) for x in liste]


async def _rien(*_a, **_k):
    return None


async def _vide():
    return []


def _etat_ferme(**en_plus):
    async def etat(_mode):
        return {"ouvert": False, "statut": "FERME", "raison": "ferme", "reprise": None, "reprise_dite": "dix-huit heures", "prochaine_ouverture": None,
                "planifiee_permise": False, **en_plus}
    return etat


async def _melange(_=None):
    article, ligne = formule_du_menu(etape_de_boissons())
    return articles.a_la_taille_de_la_formule(article, ligne)


async def _valeur_sans_la_taille(_=None):
    etape = etape_de_boissons(alternatives=None)
    etape["options"][0]["declinaisons_du_produit"] = [{"nom": "Maxi", "vendable": True, "rupture": False, "code": "BM"}]
    article, ligne = formule_du_menu(etape, {"nom": "Maxi", "declinaisons": {"Boisson": "Maxi"}})
    return articles.a_la_taille_de_la_formule(article, ligne)


async def _retrait_sur_deux_plats(_=None):
    def plat(code, nom):
        return {"code": code, "nom": nom, "retirables": ["olives"]}
    article = {"groupes": [{"id": "e1", "nom": "Plat", "role": FO.ROLE_ETAPE, "options": [plat("P1", "Pizza"), plat("P2", "Pâtes")]}]}
    ligne = {"nom": "Formule", "choix": [{"option_code": c, "nom": n, "quantite": 1, "choix": [], "etape": "e1"} for c, n in (("P1", "Pizza"), ("P2", "Pâtes"))]}
    return articles.retirer_sur_le_plat(article, ligne, "olives")


class _SourceDeCodes:
    def __init__(self, codes):
        async def lire():
            return codes
        self.codes_de_remise = lire


CODES = [{"code": "BIENVENUE", "ref": "R1", "nom": "Bienvenue 10 %", "phrase": None}]


async def _un_code(code):
    return await articles.poser_le_code_de_remise(_SourceDeCodes(CODES), P.nouveau(), Reglages(), code, False)


async def _en_rupture(appel, mp):
    vrai = articles._article_de_la_carte

    async def mega_en_rupture(*a, **k):
        article = await vrai(*a, **k)
        for d in article["declinaisons"]:
            d["rupture"] = d["nom"] == "Mega"
        return article
    mp.setattr(articles, "_article_de_la_carte", mega_en_rupture)
    return await appel.ajouter(ART("margherita", 1, "Mega"))


async def _pas_servi(appel, mp):
    mp.setattr(articles, "_article_de_la_carte", _rien)
    return await appel.ajouter(ART("margherita", 1, "Normale"))


async def _plus_au_catalogue(appel, mp):
    await appel.ajouter(ART("margherita", 1, "Normale"))
    mp.setattr(articles, "_article_de_la_carte", _rien)
    return await appel.modifier(ligne="1", quantite=2)


async def _deux_lignes(appel):
    await appel.ajouter(ART("margherita", 1, "Normale"))
    await appel.ajouter(ART("margherita", 1, "Mega"))


async def _ligne_9(appel, _mp):
    await _deux_lignes(appel)
    return await appel.modifier(ligne="9", quantite=2)


async def _quelle_ligne(appel, _mp):
    await _deux_lignes(appel)
    return await appel.modifier(quantite=2)


async def _laquelle(appel, _mp):
    await _deux_lignes(appel)
    return await appel.modifier(ligne="margherita", quantite=2)


async def _pas_dans_la_commande(appel, _mp):
    await _deux_lignes(appel)
    return await appel.modifier(ligne="xylophone", quantite=2)


async def _quantite_invalide(appel, _mp):
    await appel.ajouter(ART("margherita", 1, "Normale"))
    return await appel.modifier(ligne="1", quantite=-1)


async def _rien_a_changer(appel, _mp):
    await appel.ajouter(ART("margherita", 1, "Normale"))
    return await appel.modifier(ligne="1")


async def _commande_lue(appel, _mp):
    await appel.ajouter("coca")
    await appel.mode()
    return await appel.voir()


async def _offres(appel, mp, offres, en_cours=_vide, **demande):
    await appel.ajouter("coca")
    await appel.mode()

    async def a_portee(_mode, _lignes):
        return offres
    mp.setattr(appel.source, "remises_en_cours", en_cours)
    mp.setattr(appel.source, "offres_a_portee", a_portee, raising=False)
    return await moteur.remises_disponibles(appel.source, appel.p, appel.regles, **demande)


async def _offres_en_cours(appel, mp):
    async def en_cours():
        return [{"ref": "R1", "nom": "Dix pour cent", "phrase": "Dix pour cent sur tout."}, {"ref": "R2", "nom": "Boisson offerte", "phrase": None}]
    mp.setattr(appel.source, "remises_en_cours", en_cours)
    return await moteur.remises_disponibles(appel.source, appel.p, appel.regles, demande=True)


async def _pas_d_offre(appel, mp):
    mp.setattr(appel.source, "remises_en_cours", _vide)
    return await moteur.remises_disponibles(appel.source, appel.p, appel.regles, demande=True)


async def _offre_atteinte(appel, mp):
    return await _offres(appel, mp, [{"ref": "O1", "nom": "Burger offert", "phrase": None, "etat": "atteinte", "proposition": {"prix": 0}, "choix": ["Cheese", "Bacon"], "manque": 0}])


async def _offre_presque(appel, mp):
    return await _offres(appel, mp, [{"ref": "O2", "nom": "Dessert offert", "phrase": None, "etat": "presque", "manque": 1}])


async def _seuil(appel, mp):
    await appel.ajouter("coca")
    await appel.mode()

    async def seuil():
        return [{"ref": "R3", "nom": "Frites offertes", "phrase": None, "minimum": 250}]

    async def rien_a_portee(_mode, _lignes):
        return []
    appel.p["mentions_de_remise"] = 0
    mp.setattr(appel.source, "remises_en_cours", seuil)
    mp.setattr(appel.source, "offres_a_portee", rien_a_portee, raising=False)
    return await moteur.remises_disponibles(appel.source, appel.p, appel.regles)


async def _fermeture(appel, mp):
    mp.setattr(appel.source, "etat", _etat_ferme())
    return await moteur.etat_ouverture(appel.source, appel.p, appel.regles, "emporter")


async def _heure_annoncee(appel, mp):
    async def annonce(_mode, _zone):
        return {"prete": "2026-11-25T20:00:00+01:00", "texte": "à vingt heures", "minutes": 20}
    mp.setattr(appel.source, "annonce", annonce)
    return await moteur.heure_annoncee(appel.source, appel.p, appel.regles, "emporter")


async def _planifiable(appel, mp, **en_plus):
    async def quand_dit(_h):
        return "demain à dix-neuf heures" if appel.p.get("heure_voulue") else "dix-huit heures"
    mp.setattr(appel.source, "etat", _etat_ferme(planifiee_permise=True, **en_plus))
    mp.setattr(appel.source, "quand_dit", quand_dit, raising=False)


async def _commande_pour(appel, mp):
    await _planifiable(appel, mp)
    appel.p["heure_voulue"] = "2026-11-26T19:00:00+01:00"
    return await moteur.choisir_mode(appel.source, appel.p, appel.regles, "emporter")


async def _proposition_d_ouverture(appel, mp):
    await _planifiable(appel, mp, prochaine_ouverture=datetime(2026, 11, 25, 17, tzinfo=timezone.utc))
    return await moteur.choisir_mode(appel.source, appel.p, appel.regles, "emporter")


async def _quel_jour_et_quelle_heure(appel, mp):
    await appel.ajouter("coca")
    await _planifiable(appel, mp)
    return await moteur.choisir_mode(appel.source, appel.p, appel.regles, "emporter")


async def _tout_retirer(appel, mp):
    mp.setattr(changement, "_permet_l_annulation", lambda _source: True)
    avant = {**appel.p, "enregistree": {"numero": "00000000-0000-0000-0000-000000000001", "numero_court": "12", "total": 200}}
    return await changement.changer_commande_enregistree(appel.source, appel.p, appel.regles, Appelant(), avant)


CAS_DE_LA_COMMANDE: list[Cas] = [
    Cas("question_d_un_choix", TS.question_d_un_choix, lambda a, m: a.ajouter("regina"), "F", pareilles("Normale", "Mega"), "CHOIX_OBLIGATOIRE"),
    Cas("article_introuvable", TS.article_introuvable, lambda a, m: a.ajouter(ART("pizza au homard", 1, "Normale")), "F", pareilles("pizza au homard"), "INTROUVABLE"),
    Cas("article_introuvable_avec_proches", TS.article_introuvable, lambda a, m: a.ajouter(ART("quatre fromagez", 1, "Normale")), "F",
        lambda r: pareilles("quatre fromagez", *_noms(r.faits["plus_proches"])), "INTROUVABLE"),
    Cas("ne_se_prend_pas_avec_des_choix", TS.ne_se_prend_pas_avec_des_choix, lambda a, m: a.ajouter(ART("tiramisu", moities=["regina", "margherita"])), "F", [], "aucun_choix"),
    Cas("vous_voulez_dire_une_option", TS.vous_voulez_dire, lambda a, m: a.ajouter(ART("margherita", 1, "Normale", supplements=["jambon cru"])), "F",
        lambda r: pareilles(*_noms(r.faits["candidats"])), "AMBIGU"),
    Cas("option_hors_carte_avec_proche", TS.option_hors_carte, lambda a, m: a.ajouter(ART("margherita", 1, "Normale", supplements=["mozza"])), "F",
        lambda r: pareilles(*_noms(r.faits["plus_proches"])), "HORS_CARTE"),
    Cas("option_hors_carte_sans_proche", TS.option_hors_carte, lambda a, m: a.ajouter(ART("margherita", 1, "Normale", supplements=["viande"])), "F",
        lambda r: pareilles(*_noms(r.faits["choix_possibles"])), "HORS_CARTE"),
    Cas("quel_rangement", TS.quel_rangement, lambda a, m: a.ajouter(ART("pizzas", 1)), "F", lambda r: pareilles(*_noms(r.faits["rangements"])), "articles"),
    Cas("pas_servi_maintenant", TS.pas_servi_maintenant, _pas_servi, "F", pareilles("margherita"), "pas_servi_maintenant"),
    Cas("beaucoup_combien_exactement", TS.beaucoup_combien_exactement, lambda a, m: a.ajouter(ART("margherita", 99999, "Normale")), "F", [("99999", "99999")], "quantite"),
    Cas("taille_en_rupture", TS.taille_en_rupture, _en_rupture, "F", pareilles("Normale"), "RUPTURE"),
    Cas("plus_au_catalogue", TS.plus_au_catalogue, _plus_au_catalogue, "F", [], "INTROUVABLE"),
    Cas("commande_vide", TS.commande_vide, lambda a, m: a.modifier(ligne="1", quantite=2), "F", [], "panier_vide"),
    Cas("pas_de_ligne", TS.pas_de_ligne, _ligne_9, "F", [("9", "9")], "INTROUVABLE"),
    Cas("quelle_ligne", TS.quelle_ligne, _quelle_ligne, "F", [], "ligne"),
    Cas("pas_dans_la_commande", TS.pas_dans_la_commande, _pas_dans_la_commande, "F", pareilles("xylophone"), "INTROUVABLE"),
    Cas("combien_exactement", TS.combien_exactement, _quantite_invalide, "F", [], "quantite"),
    Cas("que_change_t_on", TS.que_change_t_on, _rien_a_changer, "F", [], "modification"),
    Cas("commande_vide_a_lire", TS.commande_vide_a_lire, lambda a, m: a.voir(), "L", [], "vide"),
    Cas("la_commande_se_lit", lambda f: TS.la_commande_se_lit({**f, "lignes_dites": "un Coca-Cola"}), _commande_lue, "L", [("200", "deux euros"), ("Coca-Cola", "Coca-Cola")],
        "OK"),
    Cas("pas_d_offre", TS.pas_d_offre, _pas_d_offre, "L", [], "aucune"),
    Cas("offres_en_ce_moment", TS.offres_en_ce_moment, _offres_en_cours, "L", pareilles("Dix pour cent", "Boisson offerte"), "OK"),
    Cas("offre_atteinte", TS.offre_atteinte, _offre_atteinte, "L", pareilles("Burger offert", "Cheese", "Bacon"), "offre_atteinte"),
    Cas("offre_presque_atteinte", TS.offre_presque_atteinte, _offre_presque, "L", [("Dessert offert", "Dessert offert"), ("1", "un")], "offre_presque_atteinte"),
    Cas("seuil_presque_atteint", TS.seuil_presque_atteint, _seuil, "L", [("Frites offertes", "Frites offertes"), ("50", "cinquante centimes")], "seuil_presque_atteint"),
    Cas("pas_de_commande_en_ce_moment", TS.pas_de_commande_en_ce_moment, _fermeture, "F", [], "ferme"),
    Cas("ce_sera_pret", TS.ce_sera_pret, _heure_annoncee, "L", pareilles("à vingt heures"), "OK"),
    Cas("commande_pour", TS.commande_pour, _commande_pour, "F", pareilles("demain à dix-neuf heures"), "FERME_PLANIFIABLE"),
    Cas("preparer_pour_l_ouverture", TS.preparer_pour_l_ouverture, _proposition_d_ouverture, "F", pareilles("dix-huit heures"), "heure_proposee"),
    Cas("quel_jour_et_quelle_heure", TS.quel_jour_et_quelle_heure, _quel_jour_et_quelle_heure, "F", [], "a_planifier"),
    Cas("tout_retirer_c_est_annuler", TS.tout_retirer_c_est_annuler, _tout_retirer, "F", [], "changement_incomplet"),
]

async def _plusieurs_etapes(essai_de):
    e = await brique(essai_de, "FOR2")
    article = await e.source.article("F-MIDI", "emporter")
    double = {**article, "groupes": [*article["groupes"], {**article["groupes"][0], "id": "Entrée 2", "nom": "Entrée 2"}]}
    double["groupes"][-1]["options"] = [{**o, "code": o["code"] + "-2"} for o in double["groupes"][-1]["options"]]
    return moteur.placer_les_choix(double, {"nom": "Formule midi", "choix": []}, "nems", None)[0]


async def _hors_sous_ensemble(essai_de):
    e = await brique(essai_de, "FOR3")
    article = await e.source.article("F-COMPLETE", "emporter")
    return moteur.placer_les_choix(article, {"nom": "Formule complète", "choix": []}, "tiramisu", None)[0]


CAS_DE_L_ESSAI: list[Cas] = [
    Cas("pour_quelle_etape", TS.pour_quelle_etape, _plusieurs_etapes, "F", pareilles("Entrée", "Entrée 2"), "etape"),
    Cas("pas_dans_la_formule", TS.pas_dans_la_formule, _hors_sous_ensemble, "F", pareilles("tiramisu", "Formule complète"), "hors_sous_ensemble"),
]


async def _regime_du_catalogue():
    class Source(SourceAllergie):
        async def catalogue(self, _mode):
            return {"articles": [{"nom": n, "regimes": ["vegetarien"]} for n in ("Margherita", "Veggie")]}
    return await A_._regime_du_catalogue(Source(), {"mode": "emporter"}, "végétarien")


CAS_PURS: list[Cas] = [
    Cas("n_est_plus_disponible", TS.n_est_plus_disponible, lambda: articles._choisir({"choix": []}, (), _groupe(2, 2), {**MAYO, "rupture": True}, 1), "F", pareilles("Mayonnaise"), "RUPTURE"),
    Cas("maximum_atteint", TS.maximum_atteint,
        lambda: articles._choisir({"choix": [{"option_code": "A", "nom": "Ketchup", "quantite": 1, "choix": []}]}, (), _groupe(1, 3), MAYO, 1), "F",
        [("Sauces", "Sauces"), ("Mayonnaise", "Mayonnaise"), ("1", "un")], "MAXIMUM_ATTEINT"),
    Cas("sur_quelle_moitie", TS.sur_quelle_moitie, lambda: articles._noter_un_retrait_par_moitie({}, "olives", ["Reine", "Reine", "4 fromages"]), "F",
        pareilles("olives", "Reine", "4 fromages"), "AMBIGU"),
    Cas("quoi_retirer", TS.quoi_retirer, lambda: articles._noter_un_retrait_par_moitie({}, "sur la Reine", ["Reine", "4 fromages"]), "F", [], "retrait_sans_ingredient"),
    Cas("vous_voulez_retirer", TS.vous_voulez_retirer,
        lambda: articles._appliquer_les_retraits({"retirables": ["Olives noires", "Olives vertes", "Oignons"], "declinaisons": [], "groupes": []}, {"nom": "Reine", "retires": [], "choix": []}, "olives"),
        "F", pareilles("Olives noires", "Olives vertes"), "AMBIGU"),
    Cas("ne_se_retire_pas", TS.ne_se_retire_pas,
        lambda: articles._appliquer_les_retraits({"declinaisons": [], "groupes": [], "retirables": ["Oignons", "Olives"], "ingredients": ["Tomate", "Oignons", "Olives"]},
                                                 {"nom": "Reine", "retires": [], "choix": []}, "tomate"), "F", pareilles("tomate", "Reine", "Oignons", "Olives"), "HORS_CARTE"),
    Cas("notes_non_acceptees", TS.notes_non_acceptees, lambda: articles._noter({}, "sans stress", Reglages(notes_libres=False)), "F", [], "notes_non_acceptees"),
    Cas("notes_refusees_a_la_commande", TS.notes_non_acceptees, lambda: articles.noter_la_commande(P.nouveau(), Reglages(notes_libres=False), "pour Léa"), "F", [], "notes_non_acceptees"),
    Cas("melange_refuse", TS.melange_refuse, _melange, "F", [("3", "trois"), ("Coca Canette", "Coca Canette"), ("Fanta", "Fanta"), ("1", "un"), ("Coca Bouteille", "Coca Bouteille")],
        "alternatives_melangees"),
    Cas("valeur_parmi_les_choix", TS.valeur_parmi_les_choix, _valeur_sans_la_taille, "F", pareilles("Coca Bouteille"), "choix_sans_la_taille"),
    Cas("sur_lequel", TS.sur_lequel, _retrait_sur_deux_plats, "F", pareilles("Pizza", "Pâtes"), "AMBIGU"),
    Cas("code_inconnu", TS.code_inconnu, lambda: _un_code("FAUX"), "F", [], "code_inconnu"),
    Cas("code_de_remise_bon", TS.code_de_remise_bon, lambda: _un_code("BIENVENUE"), "F", [("BIENVENUE", "BIENVENUE"), ("Bienvenue 10 %", "Bienvenue dix pour cent")], "OK"),
    Cas("regime_d_un_article", TSA.regime_d_un_article, lambda: A_._regime_dit(SourceAllergie(), {"nom": "Burger", "regimes": ["halal"]}, "halal", {"halal_restaurant": False}), "L",
        pareilles("Burger", "halal"), "etiquete"),
    Cas("regime_du_restaurant", TSA.regime_d_un_article, lambda: A_._regime_dit(SourceAllergie(), {"nom": "Burger", "regimes": []}, "halal", {"halal_restaurant": True}), "L",
        pareilles("halal"), "restaurant"),
    Cas("regime_du_catalogue", TSA.regime_du_catalogue, _regime_du_catalogue, "L",
        [("Margherita", "Margherita"), ("Veggie", "Veggie"), ("autres_a_confirmer", "Pour les autres")], "renseigne",
        ),
]

CAS_DE_LA_SOURCE: list[Cas] = [
    Cas("quel_jour", TSC.quel_jour, lambda: resolution_du_jour_et_de_l_heure("bientôt", None, MATIN), "F", [], "jour"),
    Cas("heure_passee_sans_jour", TSC.heure_passee_sans_jour, lambda: resolution_du_jour_et_de_l_heure("dix-neuf heures", "dix-neuf heures", SOIR), "F", pareilles("dix-neuf heures"),
        "heure_passee_aujourd_hui"),
    Cas("heure_ambigue", TSC.heure_ambigue, lambda: resolution_du_jour_et_de_l_heure("demain", "sept heures", MATIN), "F", lambda r: pareilles(*r.faits["candidats_heure"]), "heure"),
    Cas("jour_ambigu", TSC.jour_ambigu, lambda: resolution_du_jour_et_de_l_heure("le 17", None, MATIN), "F", lambda r: pareilles(*[c["jour_dit"] for c in r.faits["candidats"]]), "jour"),
    Cas("quelle_heure_ce_jour", TSC.quelle_heure_ce_jour, lambda: resolution_du_jour_et_de_l_heure("demain", None, MATIN), "F", pareilles("mercredi dix-huit novembre"), "heure"),
    Cas("quelle_heure_exactement", TSC.quelle_heure_exactement, lambda: resolution_du_jour_et_de_l_heure("demain", "bientôt", MATIN), "F", [], "heure"),
    Cas("heure_passee", TSC.heure_passee, lambda: resolution_du_jour_et_de_l_heure("aujourd'hui", "neuf heures du matin", MATIN), "F", [], "heure"),
]


async def _senlis(commerce):
    """Deux zones autour de Senlis : Chantilly nommée, et un rayon de huit kilomètres."""
    c, a = commerce.c, commerce.a
    await c.execute("UPDATE mark.site SET adresse_insee = $2 WHERE id = $1", a, ZONES.SENLIS)
    await c.execute("DELETE FROM mark.resto_zone WHERE site_id = $1", a)
    for nom, forme, communes, rayon, ordre in (("Chantilly", "communes", [ZONES.CHANTILLY], None, 0), ("Centre", "rayon", [], 8, 1)):
        await c.execute("INSERT INTO mark.resto_zone (site_id, nom, forme, communes, rayon_km, exclues, frais, delai, ordre) VALUES ($1,$2,$3,$4,$5,$6,200,30,$7)",
                        a, nom, forme, communes, rayon, [], ordre)


CAS_DE_LA_ZONE: list[Cas] = [
    Cas("hors_zone", TSC.hors_zone, lambda c: Z.verifier_adresse(c.c, c.a, "7 rue Victor Hugo, Compiègne"), "F", lambda r: pareilles("Compiègne", *r.faits["communes_livrees"]), "HORS_ZONE"),
    Cas("adresse_non_comprise", TSC.adresse_non_comprise, lambda c: Z.verifier_adresse(c.c, c.a, "  "), "F", [], "adresse"),
    Cas("quelle_commune", TSC.quelle_commune, lambda c: Z.verifier_adresse(c.c, c.a, "rue de Paris"), "F", [], "commune"),
    Cas("commune_ambigue", TSC.commune_ambigue, lambda c: Z.verifier_adresse(c.c, c.a, "5 rue de la Mairie, Saint-Just"), "F",
        lambda r: pareilles(*{c["nom"] for c in r.faits["candidats"]}, *{c["departement"] for c in r.faits["candidats"]}), "commune",
        ),
]


async def _minimum_de_l_adresse(kebab_):
    await kebab_.c.execute("UPDATE mark.resto_zone SET minimum = 1500 WHERE site_id = $1", kebab_.a)
    a = await AppelKebab(kebab_).charger()
    await moteur.choisir_mode(a.source, a.p, a.regles, "livraison")
    return await moteur.verifier_adresse(a.source, a.p, a.regles, ADRESSE)


CAS_DU_KEBAB: list[Cas] = [
    Cas("minimum_de_l_adresse", TS.minimum_de_l_adresse, _minimum_de_l_adresse, "F", [("quinze euros", "quinze euros")], "RETENU",
        ),
]


def _allergie(*, signalements, option_=None, mot="lait", options=None):
    async def jouer(mp):
        if options is not None:
            mp.setattr(A_, "_options_obligatoires", lambda f: options)
        return A_._signalement_dit(SourceAllergie(), fiche(signalements), option_, mot)
    return jouer


CAS_DE_L_ALLERGIE: list[Cas] = [
    Cas("present", TSA.signalement_dit, _allergie(signalements=["lait"]), "L", [("du lait", "du lait")], "present"),
    Cas("absent_de_la_fiche", TSA.signalement_dit, _allergie(signalements=["gluten"]), "L", [("du lait", "du lait")], "absent_de_la_fiche"),
    Cas("hors_liste", TSA.signalement_dit, _allergie(signalements=["lait"], mot="kiwi"), "L", [], "hors_liste"),
    Cas("sans_fiche", TSA.signalement_dit, _allergie(signalements=None), "L", [], "sans_fiche"),
    Cas("inconnu_selon_le_choix", TSA.signalement_dit, _allergie(signalements=[], options=[option("sauce maison", None)]), "L", [("options_a_confirmer", "Ça dépend du choix")], "inconnu",
        ),
    Cas("selon_option", TSA.signalement_dit, _allergie(signalements=[], options=[option("sauce blanche", ["lait"]), option("sauce maison", None)]), "L",
        [("sauce blanche", "sauce blanche"), ("autres_a_confirmer", "Pour les autres")], "selon_option"),
    Cas("liste_des_allergenes", TSA.signalement_dit, _allergie(signalements=["lait", "gluten"], mot="allergènes"), "L", [("du lait", "du lait"), ("du gluten", "du gluten")], "liste"),
    Cas("plusieurs_allergenes", TSA.signalement_dit, _allergie(signalements=["lait"], mot="lait et kiwi"), "L", [("mot_inconnu", "Pour le reste de ce que vous citez")],
        "a_confirmer_par_l_equipe"),
]


# ── les tests : un par famille de fixtures ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
async def appel(commerce):
    a = _PANIER.Appel(commerce)
    await a.mode()
    return a


@pytest.mark.parametrize("cas", parametres(CAS_DE_LA_COMMANDE))
async def test_le_signal_porte_ce_que_le_secours_de_la_commande_disait(cas, appel, monkeypatch):
    controler(cas, await jouer(cas.scenario, appel, monkeypatch))


@pytest.mark.parametrize("cas", parametres(CAS_DE_L_ESSAI))
async def test_le_signal_porte_ce_que_le_secours_d_une_formule_disait(cas, essai_de):
    controler(cas, await jouer(cas.scenario, essai_de))


@pytest.mark.parametrize("cas", parametres(CAS_PURS))
async def test_le_signal_porte_ce_que_le_secours_d_un_geste_pur_disait(cas):
    controler(cas, await jouer(cas.scenario))


@pytest.mark.parametrize("cas", parametres(CAS_DE_LA_SOURCE))
def test_le_signal_porte_ce_que_le_secours_de_la_source_disait(cas):
    controler(cas, cas.scenario())


@pytest.mark.parametrize("cas", parametres(CAS_DE_LA_ZONE))
async def test_le_signal_porte_ce_que_le_secours_de_la_zone_disait(cas, commerce):
    await _senlis(commerce)
    controler(cas, await jouer(cas.scenario, commerce))


@pytest.mark.parametrize("cas", parametres(CAS_DU_KEBAB))
async def test_le_signal_porte_ce_que_le_secours_du_minimum_disait(cas, kebab):
    controler(cas, await jouer(cas.scenario, kebab))


@pytest.mark.parametrize("cas", parametres(CAS_DE_L_ALLERGIE))
async def test_le_signal_porte_ce_que_le_secours_d_une_allergie_disait(cas, monkeypatch):
    controler(cas, await jouer(cas.scenario, monkeypatch))


# Commit 0 seulement, retiré avec les textes : la table dit bien ce que disait le texte (les cas sans base ni moteur lourd).
@pytest.mark.parametrize("cas", CAS_PURS, ids=lambda c: c.nom)
async def test_la_table_pure_est_fidele_au_texte(cas):
    fidele(cas, await jouer(cas.scenario))


@pytest.mark.parametrize("cas", CAS_DE_L_ALLERGIE, ids=lambda c: c.nom)
async def test_la_table_de_l_allergie_est_fidele_au_texte(cas, monkeypatch):
    fidele(cas, await jouer(cas.scenario, monkeypatch))


@pytest.mark.parametrize("cas", CAS_DE_LA_SOURCE, ids=lambda c: c.nom)
def test_la_table_de_la_source_est_fidele_au_texte(cas):
    fidele(cas, cas.scenario())


@pytest.mark.parametrize("cas", CAS_DE_LA_COMMANDE, ids=lambda c: c.nom)
async def test_la_table_de_la_commande_est_fidele_au_texte(cas, appel, monkeypatch):
    fidele(cas, await jouer(cas.scenario, appel, monkeypatch))


# ── R1 : « l'équipe pourra le confirmer » (la fin de INFO.NON_GARANTI) est un fait, pas seulement le statut `inconnu` ───────────────────

def _inconnu_avec_option():
    return _allergie(signalements=[], option_=option("sauce maison", None))


CAS_NON_GARANTIS: list[tuple[str, Callable]] = [
    ("hors_liste", _allergie(signalements=["lait"], mot="kiwi")),
    ("option_sans_donnee", _inconnu_avec_option()),
    ("liste_avec_option_sans_donnee", _allergie(signalements=["lait"], mot="allergènes", options=[option("sauce maison", None)])),
    ("selon_option_avec_des_inconnues", _allergie(signalements=[], options=[option("sauce blanche", ["lait"]), option("sauce maison", None)])),
    ("inconnu_selon_le_choix", _allergie(signalements=[], options=[option("sauce maison", None)])),
]

CAS_GARANTIS: list[tuple[str, Callable]] = [
    ("present", _allergie(signalements=["lait"])),
    ("absent_de_la_fiche", _allergie(signalements=["gluten"])),
    ("liste_sans_inconnue", _allergie(signalements=["lait"], mot="allergènes", options=[option("sauce blanche", ["lait"])])),
    ("selon_option_sans_inconnue", _allergie(signalements=[], options=[option("sauce blanche", ["lait"]), option("sauce rouge", ["gluten"])])),
]


@pytest.mark.parametrize("scenario", [c[1] for c in CAS_NON_GARANTIS], ids=[c[0] for c in CAS_NON_GARANTIS])
async def test_r1_le_non_garanti_dit_que_l_equipe_peut_confirmer(scenario, monkeypatch):
    """Client « Il y a des fruits à coque dans le tiramisu ? » : le modèle sait dire « je ne peux pas le garantir, l'équipe pourra vous le confirmer »."""
    r = await jouer(scenario, monkeypatch)
    assert r.faits["a_confirmer_par_l_equipe"] is True, r.faits


@pytest.mark.parametrize("scenario", [c[1] for c in CAS_GARANTIS], ids=[c[0] for c in CAS_GARANTIS])
async def test_r1_une_reponse_sure_ne_renvoie_pas_a_l_equipe(scenario, monkeypatch):
    r = await jouer(scenario, monkeypatch)
    assert not r.faits.get("a_confirmer_par_l_equipe"), r.faits


# ── R2 : les textes vidés qui n'avaient pas de cas ──────────────────────────────────────────────────────────────────────────

REGLES = Reglages()
PANIER_VIDE = {"mode": "sur_place", "lignes": []}


class CarteQuiRenvoie(Carte):
    """Une carte dont le restaurant renvoie toute question d'allergène vers lui (D22)."""

    async def regles_d_information(self):
        return {"allergies_renvoyees_au_restaurant": True}


def _en_etat(statut: str, texte: Callable[[dict], str] = TSC.fermeture):
    """La fermeture d'avant se refait de ``statut``, ``reprise_dite`` et ``planifiee_permise`` : le statut est celui du retour, pas un fait."""
    return lambda faits: texte({"statut": statut, **(faits["modes"][0] if "modes" in faits else faits)})  # la lecture de l'ouverture range l'état sous ``modes``


def _pause(appel, mp):
    mp.setattr(appel.source, "etat", _etat_ferme(statut="PAUSE_TYPE", raison="pause_type", en_pause=True))
    return moteur.etat_ouverture(appel.source, appel.p, appel.regles, "emporter")


def _livraison_terminee(appel, mp):
    mp.setattr(appel.source, "etat", _etat_ferme(statut="LIVRAISON_TERMINEE", raison="livraison_terminee", reprise_dite=None))
    return moteur.etat_ouverture(appel.source, appel.p, appel.regles, "livraison")


async def _fermee_et_planifiable(appel, mp):
    await _planifiable(appel, mp, reprise_dite="dix-sept heures")  # la reprise n'est pas l'heure que propose ``quand_dit`` : la valeur vue est bien la reprise
    return await moteur.choisir_mode(appel.source, appel.p, appel.regles, "emporter")


CAS_DE_LA_FERMETURE: list[Cas] = [
    Cas("fermeture_planifiable", _en_etat("FERME"), _fermee_et_planifiable, "F",
        [("dix-sept heures", "dix-sept heures"), ("planifiee_permise", "Je peux prendre votre commande pour plus tard")], "FERME_PLANIFIABLE"),
    Cas("fermeture_en_pause", _en_etat("PAUSE_TYPE"), _pause, "L", [("dix-huit heures", "dix-huit heures")], "PAUSE_TYPE"),
    Cas("fermeture_livraison_terminee", _en_etat("LIVRAISON_TERMINEE"), _livraison_terminee, "L", [], "LIVRAISON_TERMINEE"),
]


def _source_de_la_commande(mp, allume, envoi=None):
    from api.services.restauration.source_commande import SourceClasseur as S

    async def envoi_actif(*_):
        return allume

    async def envoyer_et_dire_pourquoi(*_):
        return envoi

    mp.setattr("api.services.restauration.source_commande.envois.liaison_db.envoi_actif", envoi_actif)
    mp.setattr("api.services.restauration.source_commande.envois.envoyer_et_dire_pourquoi", envoyer_et_dire_pourquoi)
    return S(None, Lieu("base", 1, 1), nom_prise="test")


def _envoi_eteint(mp):
    return _source_de_la_commande(mp, None).envoyer("carte", "+33612345678", "cle", 7)


def _envoi_parti(mp):
    from api.services.restauration.envois_et_sms.sms_restauration import Envoi
    return _source_de_la_commande(mp, object(), Envoi.PARTI).envoyer("carte", "+33612345678", "cle", 7)


CAS_DE_L_ENVOI: list[Cas] = [
    Cas("envoi_indisponible", TSC.envoi_indisponible, _envoi_eteint, "F", [], "INDISPONIBLE"),
    Cas("envoye", TSC.envoye, _envoi_parti, "F", [("envoye", "envoye")], "envoye"),
]


def _sans(articles_de_la_carte, produit="pizzas sans lait", signale=None):
    return lambda: V_._chercher_ce_qui_est_sans(Carte(articles_de_la_carte), {}, REGLES, produit, signale)


def _par_ingredient(articles_de_la_carte, chose="thon", *, contient=True):
    return lambda: V_.chercher_par_ingredient(Carte(articles_de_la_carte), {}, REGLES, chose, contient=contient)


_SELON = {**article_de_carte("Burger", []), "obligatoires": [[{"nom": "pain", "signalements": [{"code": "gluten"}]}, {"nom": "salade", "signalements": []}]]}

CAS_DE_LA_RECHERCHE: list[Cas] = [
    Cas("article_sans_une_chose", TSA.article_sans_une_chose,
        _sans([article_de_carte("Reine", ["lait"]), article_de_carte("Margherita", ["gluten"]), article_de_carte("Veggie", [])]), "L",
        [("Margherita", "Margherita"), ("Veggie", "Veggie"), ("lait", "lait")], "OK"),
    Cas("article_sans_une_chose_code_opaque", TSA.article_sans_une_chose,
        lambda: V_._chercher_ce_qui_est_sans(Carte([article_de_carte("Reine", ["ING-12"]), article_de_carte("Veggie", [])], libelles={"ING-12": "le lait"}), {}, REGLES,
                                             "pizzas sans lait", None), "L", [("Veggie", "Veggie"), ("lait", "lait")], "OK"),
    Cas("article_sans_une_chose_selon_le_choix", TSA.article_sans_une_chose, _sans([article_de_carte("Reine", []), _SELON], "sans gluten"), "L",
        [("Reine", "Reine"), ("Burger", "Burger"), ("gluten", "gluten")], "OK"),
    Cas("article_sans_une_chose_et_des_inconnus", TSA.article_sans_une_chose, _sans([article_de_carte("Reine", []), article_de_carte("Maison", None)], "pizzas sans gluten"), "L",
        [("Reine", "Reine"), ("1", INFO.POUR_LES_AUTRES_NON_GARANTI)], "OK"),
    Cas("articles_par_ingredient", TSA.articles_par_ingredient,
        _par_ingredient([article_de_carte("Reine", None, ["jambon"]), article_de_carte("Marine", None, ["thon"]), article_de_carte("Maison", None, None)]), "L",
        [("Marine", "Marine"), ("thon", "thon"), ("1", INFO.POUR_LES_AUTRES_NON_CONFIRMABLE)], "OK"),
    Cas("articles_par_ingredient_sans_la_chose", TSA.articles_par_ingredient, _par_ingredient([article_de_carte("Reine", None, ["jambon"])], contient=False), "L",
        [("Reine", "Reine"), ("thon", "thon")], "OK"),
    Cas("de_quel_article", TSA.de_quel_article, lambda: V_.voir_produit(Carte([article_de_carte("Reine", [])]), PANIER_VIDE, REGLES, ""), "F", [], "ARGUMENT_INVALIDE"),
    Cas("article_introuvable_de_la_fiche", TSA.article_introuvable, lambda: V_.voir_produit(Carte([article_de_carte("Reine", [])], fiche=None), PANIER_VIDE, REGLES, "Reine"), "F",
        [], "INTROUVABLE"),
    Cas("l_equipe_le_confirme", TSA.l_equipe_le_confirme,
        lambda: V_.voir_produit(CarteQuiRenvoie([article_de_carte("Reine", [])], fiche=fiche([])), PANIER_VIDE, REGLES, "Reine", "lait"), "F",
        [("equipe_confirme", "L'équipe vous le confirme")], "renvoye_au_restaurant"),
]

CAS_DE_L_ALLERGIE_AVEC_OPTION: list[Cas] = [
    Cas("inconnu_avec_option", TSA.signalement_dit, _allergie(signalements=[], option_=option("sauce maison", None)), "L", [("sauce maison", "sauce maison")], "inconnu"),
]


@pytest.mark.parametrize("cas", parametres(CAS_DE_LA_FERMETURE))
async def test_le_signal_porte_ce_que_la_fermeture_disait(cas, appel, monkeypatch):
    controler(cas, await jouer(cas.scenario, appel, monkeypatch))


@pytest.mark.parametrize("cas", parametres(CAS_DE_L_ENVOI))
async def test_le_signal_porte_ce_que_l_envoi_disait(cas, monkeypatch):
    controler(cas, await jouer(cas.scenario, monkeypatch))


@pytest.mark.parametrize("cas", parametres(CAS_DE_LA_RECHERCHE))
async def test_le_signal_porte_ce_que_la_recherche_d_un_article_disait(cas):
    controler(cas, await jouer(cas.scenario))


@pytest.mark.parametrize("cas", parametres(CAS_DE_L_ALLERGIE_AVEC_OPTION))
async def test_le_signal_porte_ce_que_le_secours_d_une_option_disait(cas, monkeypatch):
    controler(cas, await jouer(cas.scenario, monkeypatch))


async def test_f1_voisin_une_commune_hors_zone_porte_son_departement(commerce):
    """Le voisin de F1 : le refus « hors zone » donne lui aussi le département de la commune (``commune.departement``), ce que le modèle peut dire sans question."""
    await _senlis(commerce)
    r = await Z.verifier_adresse(commerce.c, commerce.a, "7 rue Victor Hugo, Compiègne")
    assert norm("Oise") in feuilles(signal(r, "F")), r.faits


# Commit R2, retirés avec les textes (C7) : la table dit bien ce que disaient les textes.
@pytest.mark.parametrize("cas", CAS_DE_LA_FERMETURE, ids=lambda c: c.nom)
async def test_la_table_de_la_fermeture_est_fidele_au_texte(cas, appel, monkeypatch):
    fidele(cas, await jouer(cas.scenario, appel, monkeypatch))


@pytest.mark.parametrize("cas", CAS_DE_L_ENVOI, ids=lambda c: c.nom)
async def test_la_table_de_l_envoi_est_fidele_au_texte(cas, monkeypatch):
    fidele(cas, await jouer(cas.scenario, monkeypatch))


@pytest.mark.parametrize("cas", CAS_DE_LA_RECHERCHE, ids=lambda c: c.nom)
async def test_la_table_de_la_recherche_est_fidele_au_texte(cas):
    fidele(cas, await jouer(cas.scenario))


@pytest.mark.parametrize("cas", CAS_DE_L_ALLERGIE_AVEC_OPTION, ids=lambda c: c.nom)
async def test_la_table_de_l_option_est_fidele_au_texte(cas, monkeypatch):
    fidele(cas, await jouer(cas.scenario, monkeypatch))
