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


def test_aucun_des_deux_metiers_ne_dit_plus_rien_avant_la_phrase_du_modele():
    """C6 n° 12 (décision d'Evan 25/11 9 h 30 ; ordre de « C6 révisée » : la phrase du modèle, puis les phrases réglées, la question à la fin) : ``premier_cas`` (le texte dit à la
    place du modèle, ``avant``) n'a plus d'appelant et est retiré ; la question réglée du numéro dicté de la commande suit la phrase du modèle (``suffixe``), comme à la réservation."""
    refus = Resultat("REFUSEE", {"detail": "complet"}, "Plus de place.")
    assert reservation.textes_du_code({}, refus, "reserver", None, False) == {}  # C6 n° 9 : la réservation ne dit plus rien mot pour mot (n° 8 et 9)
    assert not hasattr(PC, "premier_cas")
    ok = Resultat("OK", {}, "")
    textes = commande.textes_du_code({}, ok, {"type": "numero_dicte", "texte": "Je note le zéro six, c'est bon ?"}, [], False)
    assert "avant" not in textes and textes["suffixe"] == "Je note le zéro six, c'est bon ?" and textes["chiffres_exiges"] == {}, textes
