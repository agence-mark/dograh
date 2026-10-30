"""[.mark] builder-agent-vocal, lot 1 : la méthode du builder, prompt VERSIONNÉ dans la bibliothèque (famille ``methode-builder``).

Ce qui doit tenir : le moteur lit la version courante de la bibliothèque (même Candidat) ; sans bibliothèque ou sans
élément, la version de départ sert ; la version de départ est rangée comme CANDIDAT, marquée « à fixer avec Evan », et
ne contient que ce que le plan impose ; les conventions et les préférences s'ajoutent sans toucher à la méthode.
"""

from __future__ import annotations

from api.services.builder import methode
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Statut


async def test_sans_element_la_version_de_depart_sert(monde):
    assert await methode.charger_methode() == methode.TEXTE_DE_DEPART


async def test_sans_bibliotheque_la_version_de_depart_sert_aussi(monde, monkeypatch):
    monkeypatch.delenv("MARK_BIBLIOTHEQUE_ORGANISATION_ID")
    assert await methode.charger_methode() == methode.TEXTE_DE_DEPART


async def test_la_version_de_depart_est_semee_une_fois_comme_candidat(monde):
    assert await methode.semer_la_methode() is True and await methode.semer_la_methode() is False
    element = await service.lire_element("methode-builder", "methode")
    assert element.statut is Statut.CANDIDAT and len(element.versions) == 1
    assert "À FIXER AVEC EVAN" in element.courante.contenu["texte"]


async def test_le_moteur_lit_la_version_courante_de_la_bibliotheque(monde):
    await methode.semer_la_methode()
    await service.ajouter_version("methode-builder", "methode", {"texte": "Méthode corrigée avec Evan."}, "evan", notes="v2")
    assert await methode.charger_methode() == "Méthode corrigée avec Evan."
    await service.retour_arriere("methode-builder", "methode", 1, "evan")  # versionnée : on revient à la précédente
    assert await methode.charger_methode() == methode.TEXTE_DE_DEPART


def test_la_version_de_depart_ne_reprend_que_ce_que_le_plan_impose():
    texte = methode.TEXTE_DE_DEPART
    for attendu in ("Un trou = une question", "Rien n'est annoncé sans preuve", "trois couches", "7. Publication"):
        assert attendu.lower() in texte.lower(), attendu
    # Aucun mot de métier dans le code du builder (la méthode vit dans la bibliothèque, la fiche et les recettes).
    for interdit in ("poêle", "cheminée", "Nuances", "véranda", "restaurant"):
        assert interdit.lower() not in texte.lower()


async def test_conventions_et_preferences_s_ajoutent_a_la_methode(monde):
    await service.creer("conventions-mark", "conventions", "Conventions", {"texte": "Toujours vouvoyer."}, "evan")
    from api.services.builder import contexte

    await contexte.ecrire_preferences(1, "Réponses courtes.")
    systeme = await methode.systeme_complet(1)
    assert systeme.startswith(methode.TEXTE_DE_DEPART) and "Toujours vouvoyer." in systeme and "Réponses courtes." in systeme
    assert "Réponses courtes." not in await methode.systeme_complet(2)
