"""[.mark] Builder : les démarrages de l'accueil du Labo (E50), lus dans la famille ``demarrages-builder`` de la bibliothèque.

Les cartes sont des DONNÉES : un démarrage ajouté dans la bibliothèque apparaît à l'accueil, un démarrage Rejeté disparaît.
L'accueil montre les 4 plus utilisés. Le compteur est la clé d'usage de la bibliothèque (``enregistrer_utilisation``), notée
à chaque conversation ouverte depuis un démarrage ; la clé retient la conversation (un chat = une utilisation).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Statut

FAMILLE = "demarrages-builder"
NOMBRE_A_L_ACCUEIL = 4
BESOINS_AGENT = ("agent", "agent et fichiers")
BESOINS_FICHIERS = ("fichiers", "agent et fichiers")


async def plus_utilises(nombre: int = NOMBRE_A_L_ACCUEIL, *, dans_le_labo: bool = True) -> list[dict[str, Any]]:
    """Les démarrages à montrer : hors Rejeté, du plus utilisé au moins utilisé (à égalité, par titre).

    ``dans_le_labo=False`` (l'espace d'un client, E57) écarte les cartes « proposées dans le Labo seulement »."""
    try:
        elements = await service.elements_de(FAMILLE)
        utilisations = {r.slug: r.utilisee_par for r in await service.lister(FAMILLE)}
    except service.ErreurBibliotheque:
        return []
    cartes: list[dict[str, Any]] = []
    for element in elements:
        if element.statut is Statut.REJETE:
            continue
        contenu = element.courante.contenu
        proposee = "labo" if contenu.get("proposee_dans") == "labo" else "labo_et_clients"
        if proposee == "labo" and not dans_le_labo:
            continue
        cartes.append(
            {
                "slug": element.slug,
                "titre": element.titre,
                "phrase": str(contenu.get("phrase") or ""),
                "demande": str(contenu.get("demande") or ""),
                "besoin": str(contenu.get("besoin") or "rien"),
                "icone": str(contenu.get("icone") or "etincelle"),
                "proposee_dans": proposee,
                "statut": element.statut.value,
                "utilisations": utilisations.get(element.slug, 0),
            }
        )
    cartes.sort(key=lambda c: (-c["utilisations"], c["titre"].casefold()))
    return cartes[:nombre]


async def lire(slug: str, *, dans_le_labo: bool = True) -> dict[str, Any] | None:
    for carte in await plus_utilises(10_000, dans_le_labo=dans_le_labo):
        if carte["slug"] == slug:
            return carte
    return None


def remplir(demande: str, nom_de_l_agent: str | None) -> str:
    """``{agent}`` devient le nom de l'agent choisi."""
    return demande.replace("{agent}", nom_de_l_agent) if nom_de_l_agent else demande


def manque(carte: dict[str, Any], workflow_id: int | None) -> str | None:
    """Ce qui manque pour envoyer ce démarrage (côté serveur : l'agent ; les fichiers se joignent à l'écran)."""
    if carte["besoin"] in BESOINS_AGENT and workflow_id is None:
        return "This starter needs an agent: choose one."
    return None


async def noter_l_utilisation(slug: str, organisation_id: int, fil_id: int) -> None:
    try:
        element = await service.lire_element(FAMILLE, slug)
        await service.enregistrer_utilisation(FAMILLE, slug, element.version_courante, organisation_id, fil_id)
    except Exception as erreur:  # noqa: BLE001 -- le compteur n'empêche jamais d'ouvrir un chat
        logger.warning(f"[builder] usage du démarrage {slug} non noté ({type(erreur).__name__})")
