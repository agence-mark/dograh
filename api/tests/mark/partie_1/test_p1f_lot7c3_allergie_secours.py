"""[.mark] Lot 7b-C3, commit 7 : les réponses sur un régime et sur un allergène (``allergie_de_la_commande``) ne rendent plus de texte ; C7 B9 : le catalogue
supprimé, ce que disait le texte d'avant est vérifié dans les faits du retour. Faits ajoutés : ``libelle`` (``present``, ``absent_de_la_fiche``), ``hors_liste``, ``sans_fiche``, ``options_a_confirmer``,
``autres_a_confirmer``, ``mot_inconnu`` ; ``par_signalement`` porte maintenant les faits entiers de chaque réponse. La source est un double qui ne nomme que ses codes."""

from __future__ import annotations

from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as A
from api.tests.mark.partie_1.aides_signal import SourceAllergie as Source, fiche, option


def _verifie(r, faits: dict):
    """C7a : le retour ne porte plus le texte (``suggestion`` vide) ; B9 : ce que disait le texte d'avant est dans ses faits (ceux qu'il lisait)."""
    assert r.suggestion == "", r
    assert {k: r.faits.get(k) for k in faits} == faits, r
    return r


def test_present_et_absent_de_la_fiche_disent_le_libelle():
    r = _verifie(A._signalement_dit(Source(), fiche(["lait"]), None, "lait"), {'signalement': 'present', 'option': None, 'article': 'Pizza reine', 'libelle': 'du lait'})
    assert r.faits["libelle"] == "du lait"
    r = _verifie(A._signalement_dit(Source(), fiche(["gluten"]), None, "lait"), {'signalement': 'absent_de_la_fiche', 'option': None, 'article': 'Pizza reine', 'libelle': 'du lait'})
    assert r.faits["libelle"] == "du lait"


def test_avec_une_option_le_produit_et_l_option_ensemble():
    sauce = option("sauce blanche", ["lait"])
    _verifie(A._signalement_dit(Source(), fiche([]), sauce, "lait"), {'signalement': 'present', 'option': 'sauce blanche', 'article': 'Pizza reine', 'libelle': 'du lait'})
    _verifie(A._signalement_dit(Source(), fiche([]), option("sauce rouge", []), "lait"), {'signalement': 'absent_de_la_fiche', 'option': 'sauce rouge', 'article': 'Pizza reine', 'libelle': 'du lait'})
    r = _verifie(A._signalement_dit(Source(), fiche([]), option("sauce maison", None), "lait"), {'signalement': 'inconnu', 'hors_liste': None, 'sans_fiche': None, 'option': 'sauce maison', 'article': 'Pizza reine'})
    assert "libelle" not in r.faits


def test_inconnu_hors_liste_sans_fiche_et_selon_le_choix(monkeypatch):
    r = _verifie(A._signalement_dit(Source(), fiche(["lait"]), None, "kiwi"), {'signalement': 'inconnu', 'hors_liste': True})
    assert r.faits["hors_liste"] is True
    r = _verifie(A._signalement_dit(Source(), fiche(None), None, "lait"), {'signalement': 'inconnu', 'hors_liste': None, 'sans_fiche': True})
    assert r.faits["sans_fiche"] is True
    monkeypatch.setattr(A, "_options_obligatoires", lambda f: [option("sauce maison", None)])
    _verifie(A._signalement_dit(Source(), fiche([]), None, "lait"), {'signalement': 'inconnu', 'hors_liste': None, 'sans_fiche': None, 'option': None})


def test_ca_depend_dit_les_options_qui_contiennent_et_ce_qui_reste_a_confirmer(monkeypatch):
    monkeypatch.setattr(A, "_options_obligatoires", lambda f: [option("sauce blanche", ["lait"]), option("sauce rouge", [])])
    r = _verifie(A._signalement_dit(Source(), fiche([]), None, "lait"), {'signalement': 'selon_option', 'autres_a_confirmer': False, 'options_qui_contiennent': ['sauce blanche']})
    assert r.faits["autres_a_confirmer"] is False
    monkeypatch.setattr(A, "_options_obligatoires", lambda f: [option("sauce blanche", ["lait"]), option("sauce maison", None)])
    r = _verifie(A._signalement_dit(Source(), fiche([]), None, "lait"), {'signalement': 'selon_option', 'autres_a_confirmer': True, 'options_qui_contiennent': ['sauce blanche']})
    assert r.faits["autres_a_confirmer"] is True


def test_la_liste_des_allergenes_et_ce_qui_reste_a_confirmer_selon_le_choix(monkeypatch):
    _verifie(A._signalement_dit(Source(), fiche(["lait", "gluten"]), None, "allergènes"), {'signalement': 'liste', 'presents': ['du lait', 'du gluten'], 'option': None, 'article': 'Pizza reine', 'options_a_confirmer': None})
    _verifie(A._signalement_dit(Source(), fiche([]), None, "allergènes"), {'signalement': 'liste', 'presents': [], 'option': None, 'article': 'Pizza reine', 'options_a_confirmer': None})
    monkeypatch.setattr(A, "_options_obligatoires", lambda f: [option("sauce maison", None)])
    r = _verifie(A._signalement_dit(Source(), fiche(["lait"]), None, "allergènes"), {'signalement': 'liste', 'presents': ['du lait'], 'option': None, 'article': 'Pizza reine', 'options_a_confirmer': True})
    assert r.faits["options_a_confirmer"] is True
    _verifie(A._signalement_dit(Source(), fiche(["lait"]), option("sauce maison", None), "allergènes"), {'signalement': 'liste', 'presents': ['du lait'], 'option': 'sauce maison', 'article': 'Pizza reine', 'options_a_confirmer': True})


def test_plusieurs_allergenes_une_reponse_chacun_et_le_reste_non_reconnu():
    r = _verifie(A._signalement_dit(Source(), fiche(["lait"]), None, "lait et gluten"), {'signalement': 'plusieurs', 'par_signalement': [{'article': 'Pizza reine', 'code': 'lait', 'signalement': 'present', 'libelle': 'du lait'}, {'article': 'Pizza reine', 'code': 'gluten', 'signalement': 'absent_de_la_fiche', 'libelle': 'du gluten'}], 'mot_inconnu': None})
    assert [(e["code"], e["signalement"]) for e in r.faits["par_signalement"]] == [("lait", "present"), ("gluten", "absent_de_la_fiche")]
    assert "mot_inconnu" not in r.faits
    r = _verifie(A._signalement_dit(Source(), fiche(["lait"]), None, "lait et kiwi"), {'signalement': 'plusieurs', 'par_signalement': [{'article': 'Pizza reine', 'code': 'lait', 'signalement': 'present', 'libelle': 'du lait'}], 'mot_inconnu': True})
    assert r.faits["mot_inconnu"] is True and r.faits["a_confirmer_par_l_equipe"] is True


def test_un_regime_etiquete_a_l_article_ou_au_restaurant():
    r = A._regime_dit(Source(), {"nom": "Burger", "regimes": ["halal"]}, "halal", {"halal_restaurant": False})
    assert (r.suggestion, r.faits.get("etiquete")) == ("", True), r
    assert {k: r.faits.get(k) for k in ('etiquete', 'article', 'regime')} == {'etiquete': True, 'article': 'Burger', 'regime': 'halal'}
    r = A._regime_dit(Source(), {"nom": "Burger", "regimes": []}, "halal", {"halal_restaurant": True})
    assert r.suggestion == "" and {k: r.faits.get(k) for k in ('etiquete', 'regime')} == {'etiquete': False, 'regime': 'halal'}, r
