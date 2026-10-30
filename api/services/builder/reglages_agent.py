"""[.mark] Builder : écrire les réglages .mark d'un agent (B33) et remplir son lexique depuis la fiche (B41).

Une seule porte d'écriture pour tout ce qui est réglage de l'agent (phrases du code, fiche de l'appel, modules,
greffier, transferts, tour de parole...) : les clés de ``WorkflowConfigurationDefaults``. Ce qui s'écrit passe par
les MÊMES validateurs que l'enregistrement de l'écran (``UpdateWorkflowRequest``) et se range en BROUILLON
(``update_workflow`` ne publie pas). Un secret ne passe pas : une clé de réglage qui sent la clé est refusée
(on désigne une clé du coffre par ``mark-cle:<id>``, jamais sa valeur).

* **Phrases du code** : les motifs viennent du catalogue (``services/phrases/catalogue``) ; jamais de nouveau
  motif (c'est du code). Trois niveaux : groupe, agent, étape.
* **Lexique** (B41) : les termes de la fiche VALIDÉE deviennent des mots à écouter de la reconnaissance vocale, après
  ceux qui y sont déjà (jamais écrasés). Le lexique propre au client reste dans son organisation.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from api.db import db_client
from api.schemas.lexique_metier import LexiqueMetier, TermeLexique
from api.schemas.phrases_du_code import ReglePhrase
from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.builder import fiche as service_fiche
from api.services.phrases.catalogue import MOTIFS, catalogue_pour_l_ecran
from api.services.phrases.regles import CLE_REGLES

CHAMP_FICHE_LEXIQUE = "lexique"
INTERDITS_DANS_UNE_CLE = ("api_key", "token", "secret", "password", "credential")


class ErreurReglage(Exception):
    pass


def catalogue_des_motifs() -> dict[str, Any]:
    return catalogue_pour_l_ecran()


def cles_reglables() -> frozenset[str]:
    return frozenset(
        nom for nom in WorkflowConfigurationDefaults.model_fields if not any(m in nom.lower() for m in INTERDITS_DANS_UNE_CLE)
    )


async def _configurations(organization_id: int, workflow_id: int) -> dict[str, Any]:
    from api.services.modeles_reglages import service as modeles

    try:
        return (await modeles.configuration_active(workflow_id, organization_id))["configurations"]
    except modeles.ModeleRefuse as erreur:
        raise ErreurReglage(str(erreur)) from None


async def lire_reglages(organization_id: int, workflow_id: int, cles: list[str] | None = None) -> dict[str, Any]:
    configurations = await _configurations(organization_id, workflow_id)
    if cles:
        inconnues = [c for c in cles if c not in cles_reglables()]
        if inconnues:
            raise ErreurReglage(f"Unknown setting: {inconnues[0]}.")
        return {c: configurations.get(c) for c in cles}
    return {c: v for c, v in configurations.items() if c in cles_reglables()}


def _verifier(configurations: dict[str, Any]) -> None:
    """Les validateurs de l'enregistrement de l'écran, avant d'écrire quoi que ce soit."""
    from api.routes.workflow import UpdateWorkflowRequest

    try:
        UpdateWorkflowRequest(workflow_configurations=configurations)
    except ValidationError as erreur:
        premier = erreur.errors()[0]
        lieu = ".".join(str(p) for p in premier.get("loc", ())[1:])
        raise ErreurReglage(f"Setting refused ({lieu}): {premier.get('msg', 'invalid')}.") from None


async def regler(organization_id: int, workflow_id: int, valeurs: dict[str, Any]) -> dict[str, Any]:
    """Écrit ces réglages dans le BROUILLON de l'agent. Rend les clés écrites."""
    if not valeurs:
        raise ErreurReglage("Give at least one setting.")
    autorisees = cles_reglables()
    for nom in valeurs:
        if nom not in autorisees:
            raise ErreurReglage(f"Unknown or forbidden setting: {nom}.")
    nouveau = {**await _configurations(organization_id, workflow_id), **valeurs}
    _verifier(nouveau)
    await db_client.update_workflow(
        workflow_id=workflow_id,
        name=None,
        workflow_definition=None,
        template_context_variables=None,
        workflow_configurations=nouveau,
        organization_id=organization_id,
    )
    from api.services.groupe.groupe import recopier_dans_les_specialises

    await recopier_dans_les_specialises(workflow_id, organization_id)
    return {"ecrits": sorted(valeurs)}


async def regler_phrases(organization_id: int, workflow_id: int, regles: list[dict[str, Any]]) -> dict[str, Any]:
    """Pose des règles de phrases. Le motif doit être au catalogue (jamais un nouveau) ; une règle de même
    ``cle`` (motif, portée, étape, outils) remplace l'ancienne, les autres restent."""
    if not regles:
        raise ErreurReglage("Give at least one rule.")
    nouvelles: list[ReglePhrase] = []
    for brute in regles:
        try:
            regle = ReglePhrase.model_validate(brute)
        except ValidationError as erreur:
            premier = erreur.errors()[0]
            raise ErreurReglage(f"Rule refused ({'.'.join(str(p) for p in premier.get('loc', ()))}): {premier.get('msg')}.") from None
        if regle.motif not in MOTIFS:
            raise ErreurReglage(
                f"Unknown reason « {regle.motif} »: a new reason is code, not a setting. Known: {', '.join(sorted(MOTIFS))}."
            )
        nouvelles.append(regle)
    configurations = await _configurations(organization_id, workflow_id)
    from api.services.phrases.regles import regles_de

    gardees = {r.cle: r for r in regles_de(configurations)}
    for regle in nouvelles:
        gardees[regle.cle] = regle
    resultat = await regler(
        organization_id, workflow_id, {CLE_REGLES: [r.model_dump(mode="json") for r in gardees.values()]}
    )
    return {**resultat, "regles": len(nouvelles)}


def _termes_de_la_fiche(champ: Any) -> list[TermeLexique]:
    termes: list[TermeLexique] = []
    for brut in champ if isinstance(champ, list) else []:
        donnees = {"terme": brut} if isinstance(brut, str) else dict(brut) if isinstance(brut, dict) else None
        if not donnees:
            continue
        donnees["a_ecouter"] = True
        try:
            termes.append(TermeLexique.model_validate(donnees))
        except ValidationError:
            raise ErreurReglage(f"A lexicon term of the sheet is invalid: {str(brut)[:60]!r}.") from None
    return termes


async def remplir_le_lexique(organization_id: int, workflow_id: int) -> dict[str, Any]:
    """B41 : les termes du champ ``lexique`` de la fiche validée deviennent des mots à écouter."""
    from api.services.lexique.stockage import enregistrer_lexique, lire_lexique_strict

    fiche = await service_fiche.lire(organization_id, workflow_id)
    if not fiche.validee:
        raise ErreurReglage("The client sheet is not validated: a person validates it before the vocabulary is filled.")
    champ = fiche.champs.get(CHAMP_FICHE_LEXIQUE)
    if champ is None:
        raise ErreurReglage(f"The sheet has no « {CHAMP_FICHE_LEXIQUE} » line.")
    termes = _termes_de_la_fiche(champ.valeur)
    existant = await lire_lexique_strict(organization_id)
    presentes: set[str] = set()
    for t in existant.termes:
        presentes |= t.formes_normalisees()
    ajoutes: list[TermeLexique] = []
    for terme in termes:
        formes = terme.formes_normalisees()
        if formes & presentes:
            continue
        ajoutes.append(terme)
        presentes |= formes
    if not ajoutes:
        return {"ajoutes": 0, "deja_presents": len(termes)}
    try:
        fusion = LexiqueMetier.model_validate(
            {
                "modeles_importes": [m.model_dump() for m in existant.modeles_importes],
                "termes": [t.model_dump() for t in [*existant.termes, *ajoutes]],
                "seuil_mots_courants": existant.seuil_mots_courants,
            }
        )
    except ValidationError as erreur:
        raise ErreurReglage(f"The vocabulary would not be accepted: {erreur.errors()[0].get('msg', 'invalid')}.") from None
    await enregistrer_lexique(organization_id, fusion)
    return {"ajoutes": len(ajoutes), "deja_presents": len(termes) - len(ajoutes)}
