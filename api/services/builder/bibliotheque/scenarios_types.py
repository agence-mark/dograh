"""[.mark] Bibliothèque : copier un scénario de test type dans un agent (« Ajouter un test › Depuis la bibliothèque », U7).

Un scénario type (famille ``scenarios-test``) porte un but, un personnage (identifiant de la famille ``personnages-appelant``),
une ouverture, des critères et des questions pour le juge. Le copier crée un TEST de l'agent (le même qu'un test écrit à la
main), qu'on ajuste ensuite.

Avant la copie, on **signale** ce qui manque à l'agent : un critère qui cite une étape, un outil, une issue ou un champ de la
fiche que l'agent n'a pas, et un personnage absent de la bibliothèque. Sans « copier quand même », rien n'est copié tant que
quelque chose manque : la personne décide en connaissance de cause.
"""

from __future__ import annotations

from typing import Any

from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.tests_agent.verdict import normaliser

FAMILLE = "scenarios-test"
FAMILLE_PERSONNAGES = "personnages-appelant"


async def _ce_que_l_agent_a(workflow: Any, organisation_id: int) -> dict[str, set[str]]:
    from api.services.builder.controle import service as controle
    from api.services.builder.tests_agent import diagnostic

    graphe = await controle.graphe_de_travail(workflow)
    outils = {normaliser(o.nom) for o in (await controle._outils(graphe, organisation_id)).values()}
    champs: set[str] = set(getattr(workflow, "template_context_variables", None) or {})
    for noeud in graphe.get("nodes") or []:
        for v in (noeud.get("data") or {}).get("extraction_variables") or []:
            if isinstance(v, dict) and v.get("name"):
                champs.add(str(v["name"]))
    for champ in (getattr(workflow, "workflow_configurations", None) or {}).get("fiche_champs") or []:
        nom = champ.get("nom") if isinstance(champ, dict) else getattr(champ, "nom", None)
        if nom:
            champs.add(str(nom))
    issues = {normaliser(str(c)) for c in (getattr(workflow, "call_disposition_codes", None) or [])}
    return {"etapes": diagnostic.noms_de_etapes(graphe), "outils": outils, "champs": {normaliser(c) for c in champs}, "issues": issues}


def _manques(criteres: list[dict[str, Any]], a: dict[str, set[str]]) -> list[dict[str, Any]]:
    absents: list[dict[str, Any]] = []

    def noter(i: int, genre: str, valeur: str, sorte: str) -> None:
        absents.append({"critere": i, "type": genre, "manque": valeur, "sorte": sorte})

    for i, c in enumerate(criteres):
        genre = c.get("type")
        if genre == "etape" and normaliser(c.get("attendue")) not in a["etapes"]:
            noter(i, genre, str(c.get("attendue")), "etape")
        elif genre in ("outil", "outil_une_seule_fois") and normaliser(c.get("nom")) not in a["outils"]:
            noter(i, genre, str(c.get("nom")), "outil")
        elif genre == "outils_dans_l_ordre":
            for nom in c.get("noms") or []:
                if normaliser(nom) not in a["outils"]:
                    noter(i, genre, str(nom), "outil")
        elif genre == "issue" and normaliser(c.get("attendue")) not in a["issues"]:
            noter(i, genre, str(c.get("attendue")), "issue")
        elif genre == "coordonnees_prises":
            for champ in c.get("champs") or []:
                if normaliser(champ) not in a["champs"]:
                    noter(i, genre, str(champ), "champ")
    return absents


async def examiner(workflow: Any, organisation_id: int, slug: str) -> dict[str, Any]:
    """Le scénario et ce qui manque à l'agent pour le jouer. 404 si le scénario n'existe pas."""
    element = await service.lire_element(FAMILLE, slug)
    contenu = element.courante.contenu
    criteres = [c for c in contenu.get("criteres") or [] if isinstance(c, dict)]
    personnage = contenu.get("personnage")
    personnage_absent = bool(personnage) and await service.element_ou_none(FAMILLE_PERSONNAGES, str(personnage)) is None
    return {
        "slug": element.slug,
        "titre": element.titre,
        "statut": element.statut.value,
        "version": element.version_courante,
        "but": contenu.get("but"),
        "personnage": personnage,
        "personnage_absent": personnage_absent,
        "criteres": criteres,
        "absents": _manques(criteres, await _ce_que_l_agent_a(workflow, organisation_id)),
    }


async def copier(
    workflow: Any, organisation_id: int, slug: str, auteur: str | None, *, copier_quand_meme: bool = False, nom: str | None = None
) -> dict[str, Any]:
    """Crée le test de l'agent depuis le scénario. Rend ``{"copie": False, ...}`` et ce qui manque si quelque chose manque et
    qu'on n'a pas demandé de copier quand même ; ``ErreurBibliotheque`` si le test est refusé (avec la raison)."""
    from api.services.builder.tests_agent import creation, stockage
    from api.services.tests_rejouables.modele import ErreurTestRejouable

    bilan = await examiner(workflow, organisation_id, slug)
    if (bilan["absents"] or bilan["personnage_absent"]) and not copier_quand_meme:
        return {"copie": False, **bilan}
    element = await service.lire_element(FAMILLE, slug)
    contenu = element.courante.contenu
    origine = element.courante.origine
    mention = f" Origine : {origine.source}, licence {origine.licence}." if origine else ""
    try:
        test = await creation.creer(
            organisation_id,
            workflow.id,
            nom=nom or element.titre,
            criteres=list(contenu.get("criteres") or []),
            origine="manuel",
            description=f"Copié de la bibliothèque ({FAMILLE}/{slug}, version {element.version_courante}).{mention}",
            auteur=auteur,
            scenario=str(contenu.get("but") or ""),
            personnage=contenu.get("personnage"),
            ouverture=contenu.get("ouverture") or None,
            tours_max=contenu.get("tours_max"),
            questions_juge=list(contenu.get("questions_juge") or []),
            environnement=contenu.get("environnement") or None,
        )
    except (stockage.ErreurTest, ErreurTestRejouable) as erreur:
        raise ErreurBibliotheque(str(erreur)) from None
    await service.enregistrer_utilisation(FAMILLE, slug, element.version_courante, organisation_id, workflow.id)
    return {"copie": True, "test": creation.en_resume(test), **bilan}
