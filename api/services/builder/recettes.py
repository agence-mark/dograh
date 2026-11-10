"""[.mark] Builder, lot M (pièce 7) : les façons de construire un agent sont des DONNÉES de la bibliothèque, jamais une liste en dur.

Une recette = une fiche de la famille « Recettes d'agent » (``recettes-agent``) : son nom, quand la choisir, ses pièces, sa méthode de
construction, ses scénarios de test et ses capacités. **Aucun nom de recette dans ce code** : la fenêtre de création lit la liste ici,
l'étape « construction » de la méthode lit la recette de l'agent, et les gardes lisent une CAPACITÉ (``regle_de_descente``), pas un nom.

* la recette d'un agent est une ligne ``MARK_BUILDER:<agent>:recette`` ; une fois une version publiée, elle ne change qu'avec une
  confirmation explicite (SE-6) : la ligne porte alors ``tests_a_rejouer_depuis`` et la garde de publication exige les tests rejoués ;
* défaut : l'option ``recette_par_defaut`` (Réglages du builder) ; sinon la fiche qui se déclare « défaut de départ » ; sinon la
  première de la liste ; un agent sans recette indiquée reçoit ce défaut, et le builder le dit ;
* une recette Rejetée disparaît de la liste de création mais reste lisible : les agents qui l'utilisent ne changent pas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from loguru import logger
from pydantic import ValidationError

from api.db import db_client
from api.services.builder import options, stock
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.familles import FAMILLE_RECETTES
from api.services.builder.bibliotheque.modele import Statut
from api.services.builder.bibliotheque.schemas import RecetteAgent
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.constantes import cle_builder

PARTIE = "recette"
CAPACITE_REGLE_DE_DESCENTE = "regle_de_descente"


class ErreurRecette(Exception):
    """Un refus normal (recette inconnue ou rejetée, agent déjà publié), dit en une phrase."""

    def __init__(self, message: str, statut: int = 422):
        super().__init__(message)
        self.statut = statut


@dataclass
class Recette:
    slug: str
    statut: str
    fiche: RecetteAgent
    notes: list[str] = field(default_factory=list)

    @property
    def prouvee(self) -> bool:
        return self.statut == Statut.RECETTE.value

    def en_json(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "nom": self.fiche.nom,
            "quand": self.fiche.quand,
            "quand_en": self.fiche.quand_en,
            "statut": self.statut,
            "prouvee": self.prouvee,
            "capacites": list(self.fiche.capacites),
        }


async def lire(slug: str) -> Recette | None:
    """Une recette, même rejetée (un agent qui l'utilise garde ses pièces). ``None`` : absente ou illisible."""
    try:
        element = await service.element_ou_none(FAMILLE_RECETTES, slug)
        if element is None:
            return None
        return Recette(slug, getattr(element.courante.statut, "value", element.courante.statut), RecetteAgent.model_validate(element.courante.contenu))
    except (ErreurBibliotheque, ValidationError):
        logger.info(f"[recettes] fiche illisible : {slug}")
        return None


async def lister() -> list[Recette]:
    """Les recettes proposées à la création : hors Rejeté, Recette d'abord, puis par nom."""
    try:
        resumes = await service.lister(FAMILLE_RECETTES)
    except ErreurBibliotheque:
        return []
    recettes = []
    for resume in resumes:
        if resume.statut is Statut.REJETE:
            continue
        recette = await lire(resume.slug)
        if recette is not None:
            recettes.append(recette)
    return sorted(recettes, key=lambda r: (not r.prouvee, r.fiche.nom.casefold()))


async def par_defaut(organisation_de_l_agent: int) -> Recette | None:
    """Le défaut réglé dans les options ; sinon la fiche « défaut de départ » ; sinon la première. ``None`` : aucune recette en bibliothèque."""
    liste = await lister()
    if not liste:
        return None
    reglee = (await options.lire(options.organisation_pour(organisation_de_l_agent))).recette_par_defaut
    for recette in liste:
        if reglee and recette.slug == reglee:
            return recette
    return next((r for r in liste if r.fiche.defaut_de_depart), liste[0])


def _cle(workflow_id: int) -> str:
    return cle_builder(workflow_id, PARTIE)


async def choisie_de_l_agent(organisation: int, workflow_id: int) -> str | None:
    ligne = await stock.lire(organisation, _cle(workflow_id))
    slug = (ligne or {}).get("slug")
    return slug if isinstance(slug, str) and slug else None


async def de_l_agent(organisation: int, workflow_id: int) -> tuple[Recette | None, bool]:
    """(la recette de l'agent, ``True`` si elle est indiquée sur l'agent). Sans recette indiquée (ou si sa fiche a disparu) : le défaut, ``False``."""
    slug = await choisie_de_l_agent(organisation, workflow_id)
    if slug:
        recette = await lire(slug)
        if recette is not None:
            return recette, True
    return await par_defaut(organisation), False


async def capacites_de_l_agent(organisation: int, workflow_id: int, declaree: str = "") -> set[str]:
    """Les capacités de la recette de l'agent. ``declaree`` : une recette nommée par l'appelant, prise seulement si l'agent n'en a pas d'indiquée."""
    recette, indiquee = await de_l_agent(organisation, workflow_id)
    if not indiquee and declaree:
        nommee = await lire(declaree)
        if nommee is not None:
            recette = nommee
    return set(recette.fiche.capacites) if recette is not None else set()


async def verifier_le_choix(organisation: int, slug: str | None) -> Recette | None:
    """Le choix fait à la création : la recette nommée (refus si inconnue ou rejetée), sinon le défaut. ``None`` : la bibliothèque n'a aucune recette."""
    if slug:
        recette = await lire(slug)
        if recette is None or recette.statut == Statut.REJETE.value:
            raise ErreurRecette("Unknown recipe.", 422)
        return recette
    return await par_defaut(organisation)


async def poser_a_la_creation(organisation: int, workflow_id: int, recette: Recette | None, par: str = "") -> None:
    if recette is not None:
        await stock.ecrire(organisation, _cle(workflow_id), {"slug": recette.slug, "date": datetime.now(UTC).isoformat(), "par": par[:120]})


async def definir(
    organisation: int, workflow_id: int, slug: str, *, deja_publie: bool = False, confirmer: bool = False, par: str = ""
) -> Recette:
    """Pose la recette d'un agent. Refus : recette inconnue ou rejetée ; agent déjà publié sans confirmation (409).

    SE-6 : après une publication, le changement est permis avec ``confirmer`` ; il note la date (``tests_a_rejouer_depuis``) :
    les tests de l'agent doivent être rejoués depuis cette date avant de republier (``tests_agent/publication``)."""
    recette = await lire(slug)
    if recette is None or recette.statut == Statut.REJETE.value:
        raise ErreurRecette("Unknown recipe.", 422)
    if deja_publie:
        if await choisie_de_l_agent(organisation, workflow_id) == slug:
            return recette  # rien ne change : aucun test à rejouer
        if not confirmer:
            raise ErreurRecette("This agent already has a published version: confirm to change its recipe (its tests must then be replayed before publishing again).", 409)
    maintenant = datetime.now(UTC).isoformat()
    ligne: dict[str, Any] = {"slug": slug, "date": maintenant, "par": par[:120]}
    if deja_publie:
        ligne["tests_a_rejouer_depuis"] = maintenant
        logger.info(f"[recettes] recette changée après publication : organisation {organisation}, agent {workflow_id}, recette {slug}, par {par[:120] or '?'}")
    await stock.ecrire(organisation, _cle(workflow_id), ligne)
    return recette


async def tests_a_rejouer_depuis(organisation: int, workflow_id: int) -> str | None:
    """La date du changement de recette après publication, ``None`` si aucun test n'est à rejouer à ce titre."""
    ligne = await stock.lire(organisation, _cle(workflow_id))
    depuis = (ligne or {}).get("tests_a_rejouer_depuis")
    return depuis if isinstance(depuis, str) and depuis else None


def _ligne_piece(piece: Any) -> str:
    return f"- {piece.famille}/{piece.slug}" + (f" ({piece.role})" if piece.role else "")


async def section_pour_la_methode(organisation: int, workflow_id: int | None) -> str:
    """Le texte ajouté à la méthode du builder : la recette de CET agent et sa méthode de construction. Vide si la bibliothèque n'a aucune recette."""
    if workflow_id is None:
        defaut = await par_defaut(organisation)
        if defaut is None:
            return ""
        autres = [r for r in await lister() if r.slug != defaut.slug]
        lignes = [
            "## La recette de l'agent",
            "Cette conversation n'a pas encore d'agent. Sans autre demande, propose la recette par défaut "
            f"« {defaut.fiche.nom} » ({defaut.slug}) et dis-le" + (" ; elle n'est pas prouvée." if not defaut.prouvee else "."),
        ]
        if autres:
            lignes.append("Autres recettes : " + ", ".join(f"« {r.fiche.nom} » ({r.slug})" for r in autres) + ". Lis la recette choisie avec recette_lire.")
        return "\n".join(lignes)
    recette, indiquee = await de_l_agent(organisation, workflow_id)
    if recette is None:
        return ""
    fiche = recette.fiche
    lignes = ["## La recette de cet agent", f"Recette : « {fiche.nom} » ({recette.slug})."]
    if not indiquee:
        lignes.append("Aucune recette n'est indiquée sur cet agent : c'est la recette par défaut. Dis-le à la personne.")
    if not recette.prouvee:
        lignes.append("Cette recette n'est pas prouvée (Candidat) : tu le dis quand tu t'en sers.")
    if fiche.quand:
        lignes.append(f"Quand la choisir : {fiche.quand}")
    lignes.append(f"Construction : {fiche.methode_de_construction}")
    if fiche.pieces:
        lignes.append("Pièces (lis-les avec recette_lire ou bibliotheque_lire) :")
        lignes.extend(_ligne_piece(p) for p in fiche.pieces)
    if fiche.tests:
        lignes.append("Scénarios de test de la recette : " + ", ".join(fiche.tests))
    if fiche.capacites:
        lignes.append("Capacités : " + ", ".join(fiche.capacites))
    return "\n".join(lignes)


FAMILLE_PROMPT_GENERAL = "prompt-general"


async def _texte_du_prompt_general(slug: str) -> str | None:
    """Le texte d'un prompt général de la bibliothèque ; ``None`` : absent, rejeté ou sans texte."""
    try:
        element = await service.element_ou_none(FAMILLE_PROMPT_GENERAL, slug)
    except ErreurBibliotheque:
        return None
    if element is None or getattr(element.courante.statut, "value", element.courante.statut) == Statut.REJETE.value:
        return None
    texte = element.courante.contenu.get("texte")
    return texte if isinstance(texte, str) and texte.strip() else None


async def graine_du_prompt_general(organisation: int, workflow_id: int) -> dict[str, Any]:
    """Le texte de départ d'un Prompt général NEUF (É68, Evan 09/11) : jamais écrit en dur, lu dans la bibliothèque.

    D'abord la pièce « prompt général » de la recette de l'agent (la recette en cours) ; sinon le premier prompt général de la
    bibliothèque (hors Rejeté, par titre) ; sinon ``texte`` est ``None`` et l'écran garde le texte d'amont (bibliothèque vide).
    Lecture seule : un prompt déjà écrit n'est jamais touché."""
    recette, _indiquee = await de_l_agent(organisation, workflow_id)
    if recette is not None:
        for piece in recette.fiche.pieces:
            if piece.famille == FAMILLE_PROMPT_GENERAL:
                texte = await _texte_du_prompt_general(piece.slug)
                if texte:
                    return {"texte": texte, "source": "recette", "slug": piece.slug}
    try:
        resumes = await service.lister(FAMILLE_PROMPT_GENERAL)
    except ErreurBibliotheque:
        resumes = []
    for resume in sorted(resumes, key=lambda r: (r.titre.casefold(), r.slug)):
        texte = await _texte_du_prompt_general(resume.slug)
        if texte:
            return {"texte": texte, "source": "bibliotheque", "slug": resume.slug}
    return {"texte": None, "source": "amont", "slug": None}


async def lire_avec_les_pieces(slug: str) -> dict[str, Any] | None:
    """La fiche de la recette et le contenu de chacune de ses pièces (celles qui manquent sont dites)."""
    recette = await lire(slug)
    if recette is None:
        return None
    pieces = []
    for piece in recette.fiche.pieces:
        try:
            element = await service.element_ou_none(piece.famille, piece.slug)
        except ErreurBibliotheque:
            element = None
        if element is None:
            pieces.append({"famille": piece.famille, "slug": piece.slug, "role": piece.role, "manque": True})
            continue
        courante = element.courante
        pieces.append(
            {
                "famille": piece.famille,
                "slug": piece.slug,
                "role": piece.role,
                "statut": getattr(courante.statut, "value", courante.statut),
                "contenu": courante.contenu,
            }
        )
    return {**recette.en_json(), "methode_de_construction": recette.fiche.methode_de_construction, "tests": recette.fiche.tests, "pieces": pieces}


async def verser_les_agents() -> dict[str, int]:
    """Versement idempotent : chaque agent sans recette indiquée reçoit la recette par défaut. Aucun changement de comportement
    (un agent sans ligne se lit déjà avec ce défaut) ; une recette déjà posée n'est jamais touchée."""
    rapport = {"poses": 0, "deja": 0, "sans_recette": 0}
    defauts: dict[int, Recette | None] = {}
    for workflow_id, organisation in await db_client.list_workflow_ids_with_organization():
        if await choisie_de_l_agent(organisation, workflow_id):
            rapport["deja"] += 1
            continue
        if organisation not in defauts:
            defauts[organisation] = await par_defaut(organisation)
        defaut = defauts[organisation]
        if defaut is None:
            rapport["sans_recette"] += 1
            continue
        await stock.ecrire(organisation, _cle(workflow_id), {"slug": defaut.slug, "date": datetime.now(UTC).isoformat(), "par": "versement"})
        rapport["poses"] += 1
    return rapport
