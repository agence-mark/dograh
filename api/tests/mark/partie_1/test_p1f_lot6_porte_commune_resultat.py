"""[.mark] Lot 6 (G2, fin) : le résultat donné au modèle et le texte que le code dit lui-même ont UNE seule construction pour la commande et la réservation."""

from __future__ import annotations

from api.services.actions_communes import porte_commune as PC
from api.services.actions_communes.resultat import Resultat
from api.services.commande import porte as commande
from api.services.reservation import porte as reservation


def test_les_deux_metiers_construisent_le_resultat_public_par_le_meme_mecanisme(monkeypatch):
    appels = []
    monkeypatch.setattr(PC, "resultat_public", lambda operation, r, ecartes, *plus: appels.append((operation, tuple(ecartes))) or {"vu": operation})
    r = Resultat("OK", {"a": 1}, "")
    assert commande._resultat_public("ajouter", r) == {"vu": "ajouter"}
    assert reservation._resultat_public("reserver", r) == {"vu": "reserver"}
    assert [o for o, _ in appels] == ["ajouter", "reserver"]


def test_le_resultat_public_garde_ce_que_le_metier_ecarte_et_dit_ce_qui_manque_avec_les_mots_du_modele():
    r = Resultat("INCOMPLETE", {"panier": {"x": 1}, "tables": [1], "visible": "oui"}, "", "prenom")
    assert PC.resultat_public("reserver", r, ("tables",), {"prenom": "nom"}) == {
        "operation": "reserver", "statut_du_module": "INCOMPLETE", "manque": "nom", "faits": {"panier": {"x": 1}, "visible": "oui"}}
    assert PC.resultat_public("ajouter", r, ("panier",)) == {
        "operation": "ajouter", "statut_du_module": "INCOMPLETE", "manque": "prenom", "faits": {"tables": [1], "visible": "oui"}}


def test_le_premier_cas_vrai_donne_son_texte_et_aucun_autre_n_est_calcule():
    calcules = []
    cas = ((False, lambda: calcules.append("a") or "a"), (True, lambda: calcules.append("b") or "b"), (True, lambda: calcules.append("c") or "c"))
    assert PC.premier_cas(cas) == "b" and calcules == ["b"]
    assert PC.premier_cas(((False, lambda: "x"),)) is None
    assert PC.premier_cas(((True, lambda: ""),)) == ""


def test_les_deux_metiers_disent_leur_texte_par_le_meme_mecanisme(monkeypatch):
    monkeypatch.setattr(PC, "premier_cas", lambda cas: "dit par le mecanisme commun")
    refus = Resultat("REFUSEE", {"detail": "complet"}, "Plus de place.")
    assert reservation.textes_du_code({}, refus, "reserver", None, False) == {"avant": "dit par le mecanisme commun"}
    # C6 n° 5 (décision d'Evan 25/11 9 h 30) : la confirmation est dite par le modèle ; le mécanisme commun se voit sur un fait que le code dit encore (l'annulation, jusqu'au n° 7)
    ok = Resultat("OK", {"commande_annulee": "A1"}, "")
    assert commande.textes_du_code({}, ok, None, [], False) == {"avant": "dit par le mecanisme commun"}
