"""[.mark] M122 : ``laisser_un_message`` notait « Madame » comme prénom. Un titre n'est pas un prénom : il n'est jamais gardé comme tel
(l'outil redemande le prénom), et la description du paramètre le dit au modèle."""

from __future__ import annotations

import pytest
from api.services.integrations.connectors import catalogue
from api.tests.mark.test_restauration_service_client import jouer


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : le service passe par la fiche du service (urgent booléen, prénom au greffier, passer_a) ; hors inventaire D49, voir a-trancher.md")
async def test_un_titre_seul_n_est_pas_un_prenom():
    fiche: dict = {}
    r = await jouer("laisser_un_message", {"objet": "Rappeler pour la facture", "prenom": "Madame", "nom": "Dupont"}, fiche)
    assert r.donnees["statut"] == "INCOMPLETE" and r.donnees["suggestion"] == "Et votre prénom ?", r.donnees
    assert "prenom" not in fiche["service_message_en_cours"]


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : le service passe par la fiche du service (urgent booléen, prénom au greffier, passer_a) ; hors inventaire D49, voir a-trancher.md")
async def test_un_titre_devant_le_prenom_part():
    fiche: dict = {}
    r = await jouer("laisser_un_message", {"objet": "Rappeler", "prenom": "Monsieur Paul", "nom": "Durand"}, fiche)
    assert r.donnees["statut"] == "OK", r.donnees
    assert fiche["service_message_en_cours"]["prenom"] == "Paul"


@pytest.mark.xfail(strict=True, reason="Repris au lot 6 : le service passe par la fiche du service (urgent booléen, prénom au greffier, passer_a) ; hors inventaire D49, voir a-trancher.md")
def test_la_description_le_dit():
    _, a = catalogue.trouver("service", "laisser_un_message")
    prenom = next(p for p in a.parametres if p.nom == "prenom")
    nom = next(p for p in a.parametres if p.nom == "nom")
    assert "title" in prenom.description and "Dupont" in nom.description
