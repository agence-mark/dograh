"""[.mark] Lot 7b-C7a : les faits que portait seulement un texte de secours sont dans ce que le modèle lit (un fait brut, jamais une phrase).

Un test par fait (F1, F2, F7, F8, F9), chacun vu rouge avant son commit, avec son voisin (la règle 9 de ``regles-zero-aller-retour``)."""

from __future__ import annotations

from api.services.actions_communes.enveloppe_legere import pour_le_modele


def _ambigu(*candidats: dict) -> dict:
    return {"resultats": [{"statut_du_module": "AMBIGU", "manque": "commune", "faits": {"candidats": list(candidats)}}]}


def test_f1_deux_communes_homonymes_portent_leur_departement():
    """« À Nointel. » : le modèle demande « Nointel dans l'Oise ou dans le Val-d'Oise ? » ; sans le département il ne peut que dire « lequel des deux ? »."""
    vu = pour_le_modele(_ambigu({"nom": "Nointel", "departement": "Oise", "insee": "60471"}, {"nom": "Nointel", "departement": "Val-d'Oise", "insee": "95446"}))
    candidats = vu["resultats"][0]["faits"]["candidats"]
    assert [c["departement"] for c in candidats] == ["Oise", "Val-d'Oise"]


def test_f1_voisin_le_code_insee_et_le_code_postal_restent_retires():
    vu = pour_le_modele(_ambigu({"nom": "Nointel", "departement": "Oise", "insee": "60471", "code_postal": "60840"}))
    assert vu["resultats"][0]["faits"]["candidats"] == [{"nom": "Nointel", "departement": "Oise"}]
