"""[.mark] Builder : la méthode du builder, son prompt, VERSIONNÉ dans la bibliothèque (famille ``methode-builder``).

Le mécanisme : le moteur lit à chaque conversation la version courante de ``methode-builder/methode`` (n'importe
quel statut : elle se teste et se corrige comme le reste, lot 7). Tant que la bibliothèque n'est pas réglée ou
que l'élément manque, le texte de départ ci-dessous sert, et ``semer_la_methode`` le range comme **Candidat**.

⚠️ ``TEXTE_DE_DEPART`` est une version MINIMALE, à fixer avec Evan (règle « prompts fixés avec Evan »). Elle ne
reprend que ce que le plan impose : les étapes de ``05-architecture.md`` § 7, « un trou = une question », « rien
n'est annoncé sans preuve » et les trois couches de contexte. Aucun contenu de prompt d'agent ni de recette.
"""

from __future__ import annotations

from api.services.builder import contexte
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.familles import FAMILLE_METHODE
from api.services.builder.bibliotheque.service import ErreurBibliotheque

SLUG_METHODE = "methode"
AUTEUR_DE_DEPART = "systeme"

TEXTE_DE_DEPART = """\
[À FIXER AVEC EVAN : version de départ minimale, statut Candidat]

Tu es le builder d'agents vocaux de .mark. Tu construis, corriges et testes un agent vocal avec les actions qui te
sont données. Tu ne publies jamais, tu ne supprimes rien, tu ne passes rien en Recette : une personne le fait.

Les trois couches de contexte : (1) les conventions de .mark, (2) le contexte de cet agent, (3) les préférences de la
personne. Elles te sont données ci-dessous ou dans l'état relu sur le disque, qui est la vérité.

Règles :
- Un trou = une question. Si une information manque, tu poses la question ou tu écris un trou dans la fiche. Tu n'inventes rien.
- Rien n'est annoncé sans preuve. Tu ne dis « fait », « branché » ou « vérifié » que si une action te l'a montré.
  Une action « pas encore disponible » n'a rien fait.
- Chaque ligne de la fiche cite sa source. Une ligne sans source n'entre pas.
- Un élément de bibliothèque Candidat n'est pas prouvé : tu le dis quand tu l'utilises.

Étapes, dans l'ordre :
1. Contexte : lire les documents, proposer la fiche client, poser les questions sur les trous, attendre la validation.
2. Document de conception : l'écrire, attendre qu'une personne l'approuve ou le renvoie avec une note.
3. Construction en brouillon, par opérations, puis contrôle du prompt.
4. Outils : chacun est essayé avec des données de test avant d'être dit branché.
5. Exigences et tests : scénarios écrits depuis la fiche, rejeu, verdict.
6. Rapport : ce qui est prouvé, supposé, non testable, le pire défaut.
7. Publication : une personne, jamais toi.
"""


async def charger_methode() -> str:
    try:
        element = await service.element_ou_none(FAMILLE_METHODE, SLUG_METHODE)
    except ErreurBibliotheque:
        element = None
    texte = str(element.courante.contenu.get("texte") or "") if element else ""
    return texte or TEXTE_DE_DEPART


async def semer_la_methode() -> bool:
    """Range la version de départ comme Candidat si l'élément n'existe pas. Rend ``True`` si elle l'a créée."""
    if await service.element_ou_none(FAMILLE_METHODE, SLUG_METHODE) is not None:
        return False
    await service.creer(
        FAMILLE_METHODE,
        SLUG_METHODE,
        "Méthode du builder",
        {"texte": TEXTE_DE_DEPART},
        AUTEUR_DE_DEPART,
        notes="Version de départ minimale, à fixer avec Evan.",
    )
    return True


async def systeme_complet(user_id: int | None) -> str:
    """La méthode + couche 1 (conventions) + couche 3 (préférences). Stable d'un tour à l'autre : mis en cache."""
    parties = [await charger_methode()]
    conventions = await contexte.conventions()
    if conventions:
        parties.append("## Conventions de .mark\n" + conventions)
    preferences = await contexte.preferences(user_id)
    if preferences:
        parties.append("## Préférences de la personne\n" + preferences)
    return "\n\n".join(parties)
