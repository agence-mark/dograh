"""[.mark] Lot 7b-C1 : le texte de secours de chaque refus de la commande se fait des seuls faits que le modèle reçoit.

Un test par texte de secours (``services/commande/textes_de_secours.py``) : le vrai moteur refuse, et ``r.suggestion == TS.nom(faits vus par le modèle)``. Un fait qui manque au refus
(le texte lit une valeur que le modèle ne reçoit pas) ou une fonction absente rend le test rouge. Le texte rendu reste celui d'avant, au caractère près.
"""

from __future__ import annotations

import pytest

from api.services.commande import porte, textes_de_secours as TS
from api.services.commande import moteur
from api.services.commande.briques import formule as FO
from api.services.commande.moteur import articles
from api.tests.mark.partie_1.aides_briques import brique
from api.tests.mark import test_restauration_commande_panier as _PANIER
from api.tests.mark import test_restauration_classeur_commande as _CLASSEUR
from api.tests.mark import test_base_client as _BASE
from api.tests.mark.commande_sur_la_fiche import article as A

base_essai, base_prete, commerce = _BASE.base_essai, _BASE.base_prete, _CLASSEUR.commerce  # les fixtures du classeur, reprises sans import inutile


@pytest.fixture
async def appel(commerce):
    a = _PANIER.Appel(commerce)
    await a.mode()
    return a


def le_texte_de_secours_suffit(r, texte_de_secours, attendu: str | None = None) -> None:
    """Le texte du module est celui que fait la fonction de secours des faits publics du refus (et, s'il est donné, celui d'avant)."""
    assert r.suggestion, r
    assert r.suggestion == texte_de_secours(porte.faits_vus_par_le_modele(r)), (r.suggestion, r.faits)
    if attendu is not None:
        assert r.suggestion == attendu


# ── commit 1 : choisir, ajouter, retirer (articles.py) ──────────────────────────────────────────────────────────────────

async def test_question_d_un_choix_de_taille(appel):
    r = await appel.ajouter("regina")
    assert r.statut == "CHOIX_OBLIGATOIRE"
    le_texte_de_secours_suffit(r, TS.question_d_un_choix, "Quelle taille pour votre Regina : Normale ou Mega ?")


async def test_question_d_un_choix_d_un_groupe_obligatoire(appel):
    r = await appel.ajouter("cheeseburger")
    assert r.faits["question"]["nom"] == "Sauce"
    le_texte_de_secours_suffit(r, TS.question_d_un_choix)


async def test_question_d_un_choix_au_nom_de_la_carte_et_non_de_la_ligne(appel):
    """La ligne s'appelle « Regina Mega » une fois sa taille choisie : la question d'un groupe garde le nom de l'article de la carte."""
    r = await appel.ajouter(A("regina", 1, "Mega"))
    if r.statut == "CHOIX_OBLIGATOIRE":
        assert r.faits["article_de_la_carte"] == "Regina"
        le_texte_de_secours_suffit(r, TS.question_d_un_choix)


async def test_maximum_atteint_par_option(appel):
    await appel.ajouter(A("margherita", 1, "Normale", supplements=["champignons", "champignons"]))
    r = await appel.modifier(ligne="1", choix="champignons")
    assert r.statut == "MAXIMUM_ATTEINT" and r.faits["maximum_atteint"] == r.faits["maximum_par_option"]
    le_texte_de_secours_suffit(r, TS.maximum_atteint)


KETCHUP, MAYO = {"code": "A", "nom": "Ketchup", "rupture": False}, {"code": "B", "nom": "Mayonnaise", "rupture": False}


def _groupe(maximum: int, par_option: int) -> dict:
    return {"id": "g", "nom": "Sauces", "role": "sauce", "min": 0, "max": maximum, "max_par_option": par_option, "options": [KETCHUP, MAYO]}


def test_maximum_atteint_du_groupe():
    """Le groupe a la place d'une seule sauce : c'est son maximum que le refus dit, pas celui de l'option."""
    ligne = {"choix": [{"option_code": "A", "nom": "Ketchup", "quantite": 1, "choix": []}]}
    r = articles._choisir(ligne, (), _groupe(1, 3), MAYO, 1)
    assert r is not None and r.statut == "MAXIMUM_ATTEINT" and r.faits["maximum_atteint"] == 1
    le_texte_de_secours_suffit(r, TS.maximum_atteint, "Sauces : pas plus de un ; Mayonnaise n'est pas pris.")


def test_option_en_rupture():
    r = articles._choisir({"choix": []}, (), _groupe(2, 2), {**MAYO, "rupture": True}, 1)
    assert r.statut == "RUPTURE"
    le_texte_de_secours_suffit(r, TS.n_est_plus_disponible, "Mayonnaise n'est plus disponible.")


async def test_un_article_qui_ne_se_prend_pas_avec_des_choix(appel):
    r = await appel.ajouter(A("tiramisu", moities=["regina", "margherita"]))
    assert r.faits["raison"] == "aucun_choix"
    le_texte_de_secours_suffit(r, TS.ne_se_prend_pas_avec_des_choix)


async def test_une_option_hors_carte_dit_la_plus_proche(appel):
    r = await appel.ajouter(A("margherita", 1, "Normale", supplements=["mozza"]))
    assert r.statut == "HORS_CARTE" and r.faits["plus_proches"] and "choix_possibles" not in r.faits
    le_texte_de_secours_suffit(r, TS.option_hors_carte)
    assert "Le plus proche" in r.suggestion


async def test_une_option_hors_carte_sans_proche_dit_ce_qui_se_choisit(appel):
    r = await appel.ajouter(A("margherita", 1, "Normale", supplements=["viande"]))
    assert r.statut == "HORS_CARTE" and not r.faits["plus_proches"]
    assert 0 < len(r.faits["choix_possibles"]) <= 4
    le_texte_de_secours_suffit(r, TS.option_hors_carte)
    assert "Ce qui se choisit" in r.suggestion


async def test_une_option_ambigue_est_une_question_des_candidats(appel):
    r = await appel.ajouter(A("margherita", 1, "Normale", supplements=["jambon cru"]))
    assert r.statut == "AMBIGU" and r.faits["candidats"]
    le_texte_de_secours_suffit(r, TS.vous_voulez_dire)


async def test_un_mot_choix_de_deux_etapes_demande_l_etape(essai_de):
    e = await brique(essai_de, "FOR2")
    article = await e.source.article("F-MIDI", "emporter")
    double = {**article, "groupes": [*article["groupes"], {**article["groupes"][0], "id": "Entrée 2", "nom": "Entrée 2"}]}
    double["groupes"][-1]["options"] = [{**o, "code": o["code"] + "-2"} for o in double["groupes"][-1]["options"]]
    r, _ = moteur.placer_les_choix(double, {"nom": "Formule midi", "choix": []}, "nems", None)
    assert r.statut == "INCOMPLETE" and r.faits["etapes"] == ["Entrée", "Entrée 2"]
    le_texte_de_secours_suffit(r, TS.pour_quelle_etape, "Pour quelle étape : Entrée ou Entrée 2 ?")


async def test_un_mot_hors_de_la_ligne_de_la_formule_est_refuse_avec_son_mot(essai_de):
    e = await brique(essai_de, "FOR3")
    article = await e.source.article("F-COMPLETE", "emporter")
    r, _ = moteur.placer_les_choix(article, {"nom": "Formule complète", "choix": []}, "tiramisu", None)
    assert r.faits["raison"] == "hors_sous_ensemble"
    le_texte_de_secours_suffit(r, TS.pas_dans_la_formule, "Je n'ai pas « tiramisu » dans Formule complète.")


def test_un_retrait_sur_deux_plats_demande_lequel():
    plat = lambda code, nom: {"code": code, "nom": nom, "retirables": ["olives"]}  # noqa: E731
    article = {"groupes": [{"id": "e1", "nom": "Plat", "role": FO.ROLE_ETAPE, "options": [plat("P1", "Pizza"), plat("P2", "Pâtes")]}]}
    ligne = {"nom": "Formule", "choix": [{"option_code": c, "nom": n, "quantite": 1, "choix": [], "etape": "e1"} for c, n in (("P1", "Pizza"), ("P2", "Pâtes"))]}
    r = articles.retirer_sur_le_plat(article, ligne, "olives")
    assert r.statut == "AMBIGU"
    le_texte_de_secours_suffit(r, TS.sur_lequel, "Sur lequel : Pizza ou Pâtes ?")
