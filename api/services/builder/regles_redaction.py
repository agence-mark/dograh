"""[.mark] Builder : nos règles de rédaction (famille ``regles-redaction`` de la bibliothèque), lues AVANT le guide de l'amont.

``get_voice_prompting_guide`` (serveur MCP) rend d'abord ces règles, puis le guide de l'amont : pour écrire un prompt, la
méthode de .mark passe avant le conseil générique. Un élément rejeté n'est pas rendu ; un candidat l'est, marqué comme tel.
Une bibliothèque injoignable ou vide ne coupe pas le guide : rien n'est ajouté.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.familles import FAMILLE_REDACTION
from api.services.builder.bibliotheque.modele import Statut

REGLES_MAX = 30


async def charger() -> list[dict[str, Any]]:
    try:
        resumes = await service.lister(FAMILLE_REDACTION)
        regles = []
        for r in sorted(resumes, key=lambda x: (x.statut is not Statut.RECETTE, x.titre.casefold())):
            if r.statut is Statut.REJETE:
                continue
            element = await service.lire_element(FAMILLE_REDACTION, r.slug)
            texte = str(element.courante.contenu.get("texte") or "")
            if texte:
                regles.append({"slug": r.slug, "titre": r.titre, "statut": r.statut.value, "texte": texte})
        return regles[:REGLES_MAX]
    except Exception:  # noqa: BLE001 -- une bibliothèque illisible ne coupe pas le guide
        logger.info("[builder] règles de rédaction illisibles : le guide de l'amont est rendu seul")
        return []
