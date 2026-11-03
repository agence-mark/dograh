"""[.mark] builder-agent-vocal : la méthode du builder, prompt VERSIONNÉ dans la bibliothèque (famille ``methode-builder``).

Ce qui doit tenir : le moteur lit la version courante de la bibliothèque (même Candidat) ; sans bibliothèque ou sans
élément, le texte rangé dans le dépôt (méthode v1, C3) sert ; le module de versement le range comme CANDIDAT, une seule
fois ; les conventions et les préférences s'ajoutent sans toucher à la méthode.
"""

from __future__ import annotations

from api.services.builder import methode, versement
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Statut


async def test_sans_element_le_texte_du_depot_sert(monde):
    assert await methode.charger_methode() == methode.texte_de_secours()


async def test_sans_bibliotheque_le_texte_du_depot_sert_aussi(monde, monkeypatch):
    monkeypatch.delenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID")
    assert await methode.charger_methode() == methode.texte_de_secours()


async def test_la_methode_v1_est_versee_une_fois_comme_candidat(monde):
    premier = await versement.verser()
    second = await versement.verser()
    assert "methode-builder/methode" in premier.crees and "methode-builder/methode" in second.inchanges
    element = await service.lire_element("methode-builder", "methode")
    assert element.statut is Statut.CANDIDAT and len(element.versions) == 1
    assert element.courante.contenu["texte"] == methode.texte_de_secours()


async def test_le_moteur_lit_la_version_courante_de_la_bibliotheque(monde):
    await versement.verser()
    await service.ajouter_version("methode-builder", "methode", {"texte": "Méthode corrigée avec Evan."}, "evan", notes="v2")
    assert await methode.charger_methode() == "Méthode corrigée avec Evan."
    await service.retour_arriere("methode-builder", "methode", 1, "evan")  # versionnée : on revient à la précédente
    assert await methode.charger_methode() == methode.texte_de_secours()


def test_la_methode_v1_suit_la_decision_c3_et_ne_porte_aucun_metier():
    texte = methode.texte_de_secours()
    for attendu in (
        "Un trou = une question",
        "Rien n'est annoncé sans preuve",
        "trois couches",
        "Lire les dossiers",
        "UNE question à la fois, avec la réponse que tu proposes",
        "document de conception",
        "recettes façon Tala",
        "trois fois",
        "phrases à essayer",
        "La publication : une personne",
    ):
        assert attendu.lower() in texte.lower(), attendu
    assert "à fixer avec evan" not in texte.lower()
    for interdit in ("poêle", "cheminée", "Nuances", "véranda", "restaurant"):
        assert interdit.lower() not in texte.lower()


async def test_conventions_et_preferences_s_ajoutent_a_la_methode(monde):
    await service.creer("conventions-mark", "conventions", "Conventions", {"texte": "Toujours vouvoyer."}, "evan")
    from api.services.builder import contexte

    await contexte.ecrire_preferences(1, "Réponses courtes.")
    systeme = await methode.systeme_complet(1)
    assert systeme.startswith(methode.texte_de_secours()) and "Toujours vouvoyer." in systeme and "Réponses courtes." in systeme
    assert "Réponses courtes." not in await methode.systeme_complet(2)
