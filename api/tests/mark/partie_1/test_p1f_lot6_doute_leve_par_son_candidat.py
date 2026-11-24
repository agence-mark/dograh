"""[.mark] Lot 6 (n° 55) : un doute est levé quand l'article pris EST l'un de ses candidats (même identifiant), jamais quand son nom ne fait que commencer comme
celui d'un candidat : « Napolitaine » n'est pas « Napoli »."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes.resultat import Resultat
from api.services.commande import porte


def _doute(choix: dict[str, str]):
    return {"type": "ambiguite", "choix": list(choix), "candidats_par_identifiant": list(choix.values())}


def _fiche(question: dict, lignes: list[dict], reponse=None):
    return SimpleNamespace(question_avant=question, reponse=reponse, p={"lignes": lignes})


def test_un_article_au_nom_voisin_d_un_candidat_ne_leve_pas_le_doute():
    f = _fiche(_doute({"Napoli": "R1", "Margherita": "R2"}), [{"nom": "Napolitaine Normale", "ref": "R3"}])
    assert porte._le_doute_est_leve_par_un_candidat(f, Resultat("OK", {"ajoute": "Napolitaine Normale"}, "")) is False


def test_le_candidat_pris_avec_sa_taille_leve_le_doute():
    f = _fiche(_doute({"Napoli": "R1", "Margherita": "R2"}), [{"nom": "Napoli Normale", "ref": "R1"}])
    assert porte._le_doute_est_leve_par_un_candidat(f, Resultat("OK", {"ajoute": "Napoli Normale"}, "")) is True


def test_une_reponse_dite_ne_passe_pas_par_la_levee_du_doute():
    f = _fiche(_doute({"Napoli": "R1"}), [{"nom": "Napoli Normale", "ref": "R1"}], reponse={"question_id": "Q-1", "sens": "autre"})
    assert porte._le_doute_est_leve_par_un_candidat(f, Resultat("OK", {"ajoute": "Napoli Normale"}, "")) is False


def test_les_identifiants_des_candidats_ne_sont_jamais_montres_au_modele():
    r = Resultat("AMBIGU", {"candidats": ["Salmone", "Salmone"], "candidats_par_identifiant": ["P-1", "P-2"], "references": {"Salmone": "P-2"}}, "")
    assert porte._faits_publics(r) == {"candidats": ["Salmone", "Salmone"]}
