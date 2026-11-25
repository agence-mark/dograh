"""[.mark] Lot 7b-C3, commit 7 : les réponses sur un régime et sur un allergène (``allergie_de_la_commande``) rendent le texte d'avant, au caractère près, ET ce texte se refait des faits
du retour (``carte_et_allergenes/textes_de_secours``). Faits ajoutés : ``libelle`` (``present``, ``absent_de_la_fiche``), ``hors_liste``, ``sans_fiche``, ``options_a_confirmer``,
``autres_a_confirmer``, ``mot_inconnu`` ; ``par_signalement`` porte maintenant les faits entiers de chaque réponse. La source est un double qui ne nomme que ses codes."""

from __future__ import annotations

from typing import Any

from api.services.actions_communes import phrases_d_information as INFO
from api.services.commande.moteur import socle as SOCLE
from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as A
from api.services.restauration.carte_et_allergenes import textes_de_secours as TS

NG = INFO.NON_GARANTI
LIBELLES = {"lait": "du lait", "gluten": "du gluten"}


class Source:
    """Ne connaît que le lait et le gluten ; ``halal`` est le seul régime étiqueté."""

    def __init__(self, halal: bool = True):
        self.halal = halal

    def signalement_dit(self, texte: str):
        return next((c for c, libelle in LIBELLES.items() if texte in (c, libelle)), None)  # le code, ou son libellé (le multiple redonne le libellé)

    def signalements_dits(self, texte: str):
        mots = [m.strip() for m in texte.split(" et ")]
        return [m for m in mots if m in LIBELLES], any(m not in LIBELLES for m in mots)

    def regime_code(self, texte: str):
        return "halal" if texte == "halal" else ("vegetarien" if texte == "végétarien" else None)


def fiche(signalements: list[str] | None, **plus: Any) -> dict[str, Any]:
    return {"nom": "Pizza reine", "declinaisons": [], "groupes": [], "signalements": None if signalements is None else [{"code": c} for c in signalements], "signalements_libelles": LIBELLES, **plus}


def option(nom: str, signalements: list[str] | None) -> dict[str, Any]:
    return {"nom": nom, "signalements": None if signalements is None else [{"code": c} for c in signalements], "signalements_du_nom": []}


def _verifie(r, texte: str):
    assert r.suggestion == texte, r
    assert r.suggestion == TS.signalement_dit(r.faits), r
    return r


def test_present_et_absent_de_la_fiche_disent_le_libelle():
    r = _verifie(A._signalement_dit(Source(), fiche(["lait"]), None, "lait"), "Oui, Pizza reine contient du lait.")
    assert r.faits["libelle"] == "du lait"
    r = _verifie(A._signalement_dit(Source(), fiche(["gluten"]), None, "lait"), "D'après la fiche, Pizza reine ne contient pas du lait.")
    assert r.faits["libelle"] == "du lait"


def test_avec_une_option_le_produit_et_l_option_ensemble():
    sauce = option("sauce blanche", ["lait"])
    _verifie(A._signalement_dit(Source(), fiche([]), sauce, "lait"), "Oui, Pizza reine sauce blanche contient du lait.")
    _verifie(A._signalement_dit(Source(), fiche([]), option("sauce rouge", []), "lait"), "D'après la fiche, Pizza reine sauce rouge ne contient pas du lait.")
    r = _verifie(A._signalement_dit(Source(), fiche([]), option("sauce maison", None), "lait"), f"Pour Pizza reine sauce maison, {NG}")
    assert "libelle" not in r.faits


def test_inconnu_hors_liste_sans_fiche_et_selon_le_choix(monkeypatch):
    r = _verifie(A._signalement_dit(Source(), fiche(["lait"]), None, "kiwi"), f"Pour cette chose, {NG}")
    assert r.faits["hors_liste"] is True
    r = _verifie(A._signalement_dit(Source(), fiche(None), None, "lait"), INFO.NON_CONFIRMABLE)
    assert r.faits["sans_fiche"] is True
    monkeypatch.setattr(A, "_options_obligatoires", lambda f: [option("sauce maison", None)])
    _verifie(A._signalement_dit(Source(), fiche([]), None, "lait"), f"Ça dépend du choix, et {NG}")


def test_ca_depend_dit_les_options_qui_contiennent_et_ce_qui_reste_a_confirmer(monkeypatch):
    monkeypatch.setattr(A, "_options_obligatoires", lambda f: [option("sauce blanche", ["lait"]), option("sauce rouge", [])])
    r = _verifie(A._signalement_dit(Source(), fiche([]), None, "lait"), "Ça dépend : avec sauce blanche, oui. Pour les autres, d'après la fiche, non.")
    assert r.faits["autres_a_confirmer"] is False
    monkeypatch.setattr(A, "_options_obligatoires", lambda f: [option("sauce blanche", ["lait"]), option("sauce maison", None)])
    r = _verifie(A._signalement_dit(Source(), fiche([]), None, "lait"), f"Ça dépend : avec sauce blanche, oui. Pour les autres, {NG}")
    assert r.faits["autres_a_confirmer"] is True


def test_la_liste_des_allergenes_et_ce_qui_reste_a_confirmer_selon_le_choix(monkeypatch):
    _verifie(A._signalement_dit(Source(), fiche(["lait", "gluten"]), None, "allergènes"), "D'après la fiche, Pizza reine contient du lait et du gluten.")
    _verifie(A._signalement_dit(Source(), fiche([]), None, "allergènes"), "D'après la fiche, Pizza reine n'en déclare aucun.")
    monkeypatch.setattr(A, "_options_obligatoires", lambda f: [option("sauce maison", None)])
    r = _verifie(A._signalement_dit(Source(), fiche(["lait"]), None, "allergènes"), f"D'après la fiche, Pizza reine contient du lait. Selon le choix, {NG}")
    assert r.faits["options_a_confirmer"] is True
    _verifie(A._signalement_dit(Source(), fiche(["lait"]), option("sauce maison", None), "allergènes"), f"D'après la fiche, Pizza reine sauce maison contient du lait. Pour sauce maison, {NG}")


def test_plusieurs_allergenes_une_reponse_chacun_et_le_reste_non_reconnu():
    r = _verifie(A._signalement_dit(Source(), fiche(["lait"]), None, "lait et gluten"), "Oui, Pizza reine contient du lait. D'après la fiche, Pizza reine ne contient pas du gluten.")
    assert [(e["code"], e["signalement"]) for e in r.faits["par_signalement"]] == [("lait", "present"), ("gluten", "absent_de_la_fiche")]
    assert "mot_inconnu" not in r.faits
    r = _verifie(A._signalement_dit(Source(), fiche(["lait"]), None, "lait et kiwi"), f"Oui, Pizza reine contient du lait. Pour le reste de ce que vous citez, {NG}")
    assert r.faits["mot_inconnu"] is True and r.faits["a_confirmer_par_l_equipe"] is True


def test_un_regime_etiquete_a_l_article_ou_au_restaurant():
    r = A._regime_dit(Source(), {"nom": "Burger", "regimes": ["halal"]}, "halal", {"halal_restaurant": False})
    assert (r.suggestion, r.faits.get("etiquete")) == ("D'après la fiche, Burger est halal.", True), r
    assert r.suggestion == TS.regime_d_un_article(r.faits)
    r = A._regime_dit(Source(), {"nom": "Burger", "regimes": []}, "halal", {"halal_restaurant": True})
    assert r.suggestion == "D'après la fiche du restaurant, la carte est halal." and r.suggestion == TS.regime_d_un_article(r.faits), r


def test_les_textes_du_catalogue_d_un_regime_disent_cinq_noms_au_plus():
    sept = ["A1", "B2", "C3", "D4", "E5", "F6", "G7"]
    assert TS.regime_du_catalogue({"regime": "halal", "articles": sept}) == f"D'après la fiche, A1, B2, C3, D4 et E5, entre autres, sont halal. {INFO.POUR_LES_AUTRES_NON_GARANTI}"
    assert TS.regime_du_catalogue({"regime": "halal", "articles": ["A1"]}) == f"D'après la fiche, A1 est halal. {INFO.POUR_LES_AUTRES_NON_GARANTI}"
    assert TS.regime_du_catalogue({"regime": "halal", "restaurant": True}) == "D'après la fiche du restaurant, la carte est halal."
    assert TS.PLUS_DE_NOMS == SOCLE._PLUS_DE_NOMS, "le même nombre de noms dits que le moteur commun"
