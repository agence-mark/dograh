"""[.mark] Builder, U6 : les consignes générales de l'appelant simulé et du juge, LUES dans la bibliothèque.

Le texte vit dans la bibliothèque (``personnages-appelant/consigne``, ``criteres-types/grille-juge``) : une personne le corrige
sans toucher au code. Le texte du code (``schemas/appel_simule.py``, ``tests_agent/jeu.ADIEUX``) ne sert plus que de SECOURS :
élément absent, rejeté, vide ou bibliothèque illisible. Le module de versement dépose le texte actuel du code, mot pour mot
(``versement/contenu``).

Une lecture ne lève jamais : un test ne doit pas tomber parce que la bibliothèque est indisponible.
"""

from __future__ import annotations

from loguru import logger

FAMILLE_APPELANT = "personnages-appelant"
SLUG_APPELANT = "consigne"
FAMILLE_JUGE = "criteres-types"
SLUG_JUGE = "grille-juge"


async def contenu_de(famille: str, slug: str) -> dict:
    from api.services.builder.bibliotheque import service

    try:
        element = await service.element_ou_none(famille, slug)
    except Exception as erreur:  # noqa: BLE001 -- jamais un test en panne pour une bibliothèque illisible
        logger.debug(f"[consignes] {famille}/{slug} illisible : {type(erreur).__name__}")
        return {}
    if element is None:
        return {}
    courante = element.courante
    if getattr(courante.statut, "value", courante.statut) == "rejete":
        return {}
    contenu = getattr(courante, "contenu", None)
    return dict(contenu) if isinstance(contenu, dict) else {}


async def consigne_appelant() -> str:
    from api.schemas.appel_simule import CONSIGNE_APPELANT

    texte = (await contenu_de(FAMILLE_APPELANT, SLUG_APPELANT)).get("consigne")
    return texte.strip() if isinstance(texte, str) and texte.strip() else CONSIGNE_APPELANT


async def consigne_juge() -> str:
    from api.schemas.appel_simule import CONSIGNE_JUGE

    texte = (await contenu_de(FAMILLE_JUGE, SLUG_JUGE)).get("consigne")
    return texte.strip() if isinstance(texte, str) and texte.strip() else CONSIGNE_JUGE


async def adieux() -> tuple[str, ...]:
    """Les formules d'au revoir qui terminent une conversation de test. Le secours est ``jeu.ADIEUX``."""
    from api.services.builder.tests_agent import jeu

    brut = (await contenu_de(FAMILLE_APPELANT, SLUG_APPELANT)).get("adieux")
    if isinstance(brut, list):
        formules = tuple(f for f in (str(x) for x in brut) if f.strip())
        if formules:
            return formules
    return jeu.ADIEUX
