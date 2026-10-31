"""[.mark] Bibliothèque : les propositions (B9, B35) du builder et de l'équipe.

Une proposition attend dans une file (``MARK_BIBLIO_PROPOSITION:<id>``, organisation .mark). La créer est permis
au builder ; l'accepter ou la refuser est un geste d'une personne de l'équipe (``droits``). Accepter :

* ``version``         : crée l'élément ou ajoute une version Candidat avec le contenu proposé ;
* ``passage_recette`` : exige un banc (celui de la proposition, ou donné à l'acceptation) ;
* ``rejet``           : exige une raison (le motif donné à l'acceptation, sinon la justification).
"""

from __future__ import annotations

import uuid

from pydantic import ValidationError

from api.services.builder import stock
from api.services.builder.bibliotheque import service
from api.services.builder.bibliotheque.modele import Banc, Proposition, Statut, maintenant
from api.services.builder.bibliotheque.service import ErreurBibliotheque
from api.services.builder.constantes import PREFIXE_PROPOSITION, organisation_bibliotheque


def _cle(identifiant: str) -> str:
    return f"{PREFIXE_PROPOSITION}{identifiant}"


def _org() -> int:
    org = organisation_bibliotheque()
    if org is None:
        raise ErreurBibliotheque("The library organization is not configured (MARK_BIBLIOTHEQUE_ORGANISATION_ID).", 503)
    return org


async def creer(
    type_: str,
    famille: str,
    slug: str,
    justification: str,
    auteur: str,
    *,
    titre: str = "",
    contenu: dict | None = None,
    version: int | None = None,
    banc: Banc | None = None,
) -> Proposition:
    if famille not in service.FAMILLES:
        raise ErreurBibliotheque(f"Unknown family: {famille}.", 404)
    try:
        proposition = Proposition(
            id=uuid.uuid4().hex[:12],
            type=type_,  # type: ignore[arg-type]
            famille=famille,
            slug=slug,
            titre=titre,
            contenu=contenu,
            version=version,
            justification=justification,
            banc=banc,
            auteur=auteur,
        )
    except (ValidationError, ValueError) as erreur:
        premier = erreur.errors()[0].get("msg", "invalid") if isinstance(erreur, ValidationError) else str(erreur)
        raise ErreurBibliotheque(f"Invalid proposal: {premier}") from None
    if type_ == "version" and not contenu:
        raise ErreurBibliotheque("A proposed version carries its content.")
    if type_ in ("passage_recette", "rejet") and version is None:
        raise ErreurBibliotheque("Say which version the proposal aims at.")
    await stock.ecrire(_org(), _cle(proposition.id), proposition.model_dump(mode="json"))
    return proposition


async def lire(identifiant: str) -> Proposition:
    brut = await stock.lire(_org(), _cle(identifiant))
    if brut is None:
        raise ErreurBibliotheque("Proposal not found.", 404)
    return Proposition.model_validate(brut)


async def lister(etat: str | None = "en_attente") -> list[Proposition]:
    org = organisation_bibliotheque()
    if org is None:
        return []
    propositions: list[Proposition] = []
    for _cle_ligne, brut in await stock.lister(org, PREFIXE_PROPOSITION):
        try:
            proposition = Proposition.model_validate(brut)
        except ValidationError:
            continue
        if etat is None or proposition.etat == etat:
            propositions.append(proposition)
    return sorted(propositions, key=lambda p: p.date)


async def accepter(identifiant: str, decideur: str, *, banc: Banc | None = None, motif: str | None = None) -> Proposition:
    proposition = await lire(identifiant)
    if proposition.etat != "en_attente":
        raise ErreurBibliotheque("This proposal is already decided.", 409)
    # Revue (dernière passe) : la proposition est RÉSERVÉE d'abord (en_attente -> en_cours, écriture conditionnelle). Deux
    # acceptations simultanées : une seule passe cette porte, l'autre reçoit « déjà décidée » avant tout effet.
    await _passer(identifiant, "en_attente", proposition.model_copy(update={"etat": "en_cours"}))
    try:
        await _appliquer(proposition, decideur, banc, motif)
    except BaseException:
        # L'effet a échoué : la proposition redevient décidable.
        await _passer(identifiant, "en_cours", proposition)
        raise
    decidee = proposition.model_copy(update={"etat": "acceptee", "decide_par": decideur, "decide_le": maintenant()})
    return await _passer(identifiant, "en_cours", decidee)


async def _appliquer(proposition: Proposition, decideur: str, banc: Banc | None, motif: str | None) -> None:
    if proposition.type == "version":
        assert proposition.contenu is not None
        existant = await service.element_ou_none(proposition.famille, proposition.slug)
        if existant is None:
            await service.creer(
                proposition.famille,
                proposition.slug,
                proposition.titre or proposition.slug,
                proposition.contenu,
                proposition.auteur,
                notes=proposition.justification,
            )
        else:
            await service.ajouter_version(
                proposition.famille,
                proposition.slug,
                proposition.contenu,
                proposition.auteur,
                notes=proposition.justification,
                titre=proposition.titre or None,
            )
        if banc is not None:
            courant = await service.lire_element(proposition.famille, proposition.slug)
            await service.marquer(
                proposition.famille, proposition.slug, courant.version_courante, Statut.RECETTE, decideur, banc=banc
            )
    elif proposition.type == "passage_recette":
        assert proposition.version is not None
        await service.marquer(
            proposition.famille,
            proposition.slug,
            proposition.version,
            Statut.RECETTE,
            decideur,
            banc=banc or proposition.banc,
        )
    else:
        assert proposition.version is not None
        await service.marquer(
            proposition.famille,
            proposition.slug,
            proposition.version,
            Statut.REJETE,
            decideur,
            raison=motif or proposition.justification,
        )


async def _passer(identifiant: str, attendu: str, suivante: Proposition) -> Proposition:
    """Écrit ``suivante`` seulement si la proposition est encore à l'état ``attendu`` : deux personnes qui décident en même temps,
    la seconde reçoit « déjà décidée » au lieu d'écraser la première (revue R6)."""

    def transformer(brut):
        if brut is not None and brut.get("etat") != attendu:
            raise ErreurBibliotheque("This proposal is already decided.", 409)
        return suivante.model_dump(mode="json")

    try:
        await stock.modifier(_org(), _cle(identifiant), transformer)
    except stock.ConflitDEcriture:
        raise ErreurBibliotheque("This proposal keeps changing: try again.", 409) from None
    return suivante


async def refuser(identifiant: str, decideur: str, motif: str) -> Proposition:
    if not (motif or "").strip():
        raise ErreurBibliotheque("A refusal keeps its reason: give it.")
    proposition = await lire(identifiant)
    if proposition.etat != "en_attente":
        raise ErreurBibliotheque("This proposal is already decided.", 409)
    decidee = proposition.model_copy(
        update={"etat": "refusee", "decide_par": decideur, "decide_le": maintenant(), "motif_refus": motif.strip()}
    )
    return await _passer(identifiant, "en_attente", decidee)
