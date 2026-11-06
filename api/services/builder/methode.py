"""[.mark] Builder : la méthode du builder, son prompt, VERSIONNÉ dans la bibliothèque (famille ``methode-builder``).

Le mécanisme : le moteur lit à chaque conversation la version courante de ``methode-builder/methode`` (n'importe
quel statut : elle se teste et se corrige comme le reste, lot 7). Le texte rangé dans le dépôt
(``versement/contenu/methode-builder/methode.json``, méthode v1 retenue par Evan le 01/11, constat C3) est versé au
démarrage par le module de versement ; il sert aussi de **secours** tant que la bibliothèque est injoignable ou que
l'élément manque. Une seule source : ce fichier.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from api.services.builder import contexte
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.familles import FAMILLE_METHODE
from api.services.builder.bibliotheque.service import ErreurBibliotheque

SLUG_METHODE = "methode"
FICHIER_METHODE = Path(__file__).resolve().parent / "versement" / "contenu" / FAMILLE_METHODE / f"{SLUG_METHODE}.json"


@lru_cache(maxsize=1)
def texte_de_secours() -> str:
    return str(json.loads(FICHIER_METHODE.read_text(encoding="utf-8"))["contenu"]["texte"])


async def charger_methode() -> str:
    try:
        element = await service.element_ou_none(FAMILLE_METHODE, SLUG_METHODE)
    except ErreurBibliotheque:
        element = None
    texte = str(element.courante.contenu.get("texte") or "") if element else ""
    return texte or texte_de_secours()


async def section_de_la_recette(organisation: int | None, workflow_id: int | None) -> str:
    """Lot M (7) : la recette de l'agent et sa méthode de construction, lues dans la bibliothèque. Vide sans organisation (appel d'avant)."""
    if organisation is None:
        return ""
    from api.services.builder import recettes

    try:
        return await recettes.section_pour_la_methode(organisation, workflow_id)
    except Exception:  # noqa: BLE001 -- une bibliothèque illisible ne coupe pas la conversation
        return ""


async def systeme_complet(user_id: int | None, workflow_id: int | None = None, organisation: int | None = None) -> str:
    """La méthode + la recette de l'agent + couche 1 (conventions) + couche 3 (préférences). Stable d'un tour à l'autre : mis en cache."""
    parties = [await charger_methode()]
    if recette := await section_de_la_recette(organisation, workflow_id):
        parties.append(recette)
    conventions = await contexte.conventions()
    if conventions:
        parties.append("## Conventions de .mark\n" + conventions)
    preferences = await contexte.preferences(user_id)
    if preferences:
        parties.append("## Préférences de la personne\n" + preferences)
    return "\n\n".join(parties)
