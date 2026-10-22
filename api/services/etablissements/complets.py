"""[.mark] cloture-code, F-8 (règle d'Evan du 22/10) : un établissement a ses propres règles complètes.

Aucune valeur n'est héritée de l'organisation. La valeur commune (celle de l'organisation) sert à deux
choses seulement : préremplir un NOUVEL établissement, et répondre aux appels qui ne servent aucun
établissement. Ensuite, chaque établissement vit sa vie : un champ vide est vide.

Ce module ne lit ni n'écrit rien (la route et le script le font) ; il dit quoi écrire.

- ``preremplir`` : un nouvel établissement reçoit, dans ses champs vides, les valeurs communes que Dograh
  garde : l'adresse de l'organisation, ses annonces de fermeture et de pause (valeurs par défaut comprises),
  les contenus des phrases placées au niveau de l'établissement. Les horaires n'ont pas de valeur commune
  dans Dograh : rien à recopier. Ce qui vit dans la base du client (règles du planificateur, fenêtre du tour
  de rôle, types de rendez-vous, réglages des modules, contenus des phrases) est prérempli par la base
  elle-même, à la création du lieu (``mark.preremplir_etablissement``, migration 021).
- ``plan_complets`` : pour les établissements EXISTANTS (script ``api/scripts/mark/etablissements_complets.py``),
  la même recopie, et ce qu'un appel y lisait avant la règle pour que rien ne change au téléphone : les
  horaires et l'adresse de l'agent qui le sert par ses numéros (s'ils concordent), sinon l'adresse de
  l'organisation ; les annonces de l'organisation ; les contenus des phrases. Une valeur déjà posée n'est
  JAMAIS remplacée ; un désaccord n'est pas tranché (``a_decider``, rien n'est écrit pour lui).

Aucun mot de métier : des noms de champs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from api.schemas.annonce_ouverture import ReglagesAnnonceOuverture
from api.schemas.etablissements import (
    ActionReprise,
    CatalogueEtablissements,
    Etablissement,
)
from api.schemas.organization_preferences import AdresseEtablissement
from api.schemas.phrases import CataloguePhrases
from api.services.etablissements.appel import CLE_FICHE_DE_LAGENT
from api.services.etablissements.reprise import (
    CHAMPS_ANNONCE,
    AgentVu,
    PlanReprise,
    _adresse,
    _agents_de,
    _horaires,
    _vide,
)


def phrases_communes(phrases: CataloguePhrases | None) -> dict[str, str]:
    """Les contenus communs des phrases placées au niveau de l'établissement (vide : aucune)."""
    if phrases is None:
        return {}
    return {
        p.variable: p.contenu.strip()
        for p in phrases.phrases
        if p.niveau == "etablissement" and not _vide(p.contenu)
    }


def valeurs_de_depart(
    fiche: Etablissement,
    adresse_organisation: AdresseEtablissement | None,
    annonce_organisation: ReglagesAnnonceOuverture | None,
    phrases: CataloguePhrases | None,
) -> dict:
    """Les champs vides de ``fiche`` que les valeurs communes remplissent (rien d'autre)."""
    ecrits: dict = {}
    if fiche.adresse is None and adresse_organisation is not None:
        ecrits["adresse"] = adresse_organisation
    for champ in CHAMPS_ANNONCE:
        voulue = getattr(annonce_organisation, champ, None) if annonce_organisation is not None else None
        if getattr(fiche, champ) is None and not _vide(voulue):
            ecrits[champ] = voulue
    manquantes = {v: c for v, c in phrases_communes(phrases).items() if _vide(fiche.phrases.get(v))}
    if manquantes:
        ecrits["phrases"] = {**fiche.phrases, **manquantes}
    return ecrits


def preremplir(
    fiche: Etablissement,
    adresse_organisation: AdresseEtablissement | None,
    annonce_organisation: ReglagesAnnonceOuverture | None,
    phrases: CataloguePhrases | None,
) -> Etablissement:
    """Un NOUVEL établissement, ses champs vides remplis des valeurs communes. Validé comme tout autre."""
    ecrits = valeurs_de_depart(fiche, adresse_organisation, annonce_organisation, phrases)
    if not ecrits:
        return fiche
    return Etablissement.model_validate({**fiche.model_dump(), **ecrits})


def nouveaux_preremplis(
    avant: CatalogueEtablissements,
    apres: CatalogueEtablissements,
    adresse_organisation: AdresseEtablissement | None,
    annonce_organisation: ReglagesAnnonceOuverture | None,
    phrases: CataloguePhrases | None,
) -> CatalogueEtablissements:
    """Le catalogue ``apres`` où seuls les établissements absents de ``avant`` sont préremplis."""
    connus = {e.id for e in avant.etablissements}
    if all(e.id in connus for e in apres.etablissements):
        return apres
    return apres.model_copy(
        update={
            "etablissements": [
                e if e.id in connus else preremplir(e, adresse_organisation, annonce_organisation, phrases)
                for e in apres.etablissements
            ]
        }
    )


async def preremplir_les_nouveaux(
    organization_id: int, catalogue: CatalogueEtablissements
) -> CatalogueEtablissements:
    """La route d'enregistrement : les établissements que l'organisation n'a pas encore reçoivent les
    valeurs communes. Lecture STRICTE du catalogue (une base injoignable lève, rien n'est écrit) ; une
    valeur commune illisible n'est simplement pas recopiée (jamais une raison de refuser la création)."""
    from loguru import logger

    from api.services.annonce.stockage import lire_annonce_ouverture_strict
    from api.services.etablissements.stockage import lire_etablissements_strict, lire_phrases_strict
    from api.services.organization_preferences import get_organization_preferences

    from api.db.bases_clients.connexion import BaseClientIndisponible

    try:
        avant = await lire_etablissements_strict(organization_id)
    except BaseClientIndisponible:
        raise
    except Exception as erreur:  # noqa: BLE001 -- unreadable: which ones are new is unknown, nothing is prefilled
        logger.warning(f"[.mark] Saved establishments unreadable, no prefill: {erreur!r}")
        return catalogue
    if all(e.id in {a.id for a in avant.etablissements} for e in catalogue.etablissements):
        return catalogue
    adresse = annonce = phrases = None
    try:
        adresse = getattr(await get_organization_preferences(organization_id), "adresse_etablissement", None)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Organization's address unreadable, not copied into the new establishment: {erreur!r}")
    try:
        annonce = await lire_annonce_ouverture_strict(organization_id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Organization's announcements unreadable, not copied into the new establishment: {erreur!r}")
    try:
        phrases = await lire_phrases_strict(organization_id)
    except Exception as erreur:  # noqa: BLE001
        logger.warning(f"[.mark] Sentences unreadable, not copied into the new establishment: {erreur!r}")
    return nouveaux_preremplis(avant, catalogue, adresse, annonce, phrases)


@dataclass
class PlanComplets(PlanReprise):
    """Ce que le script écrirait. ``a_signaler`` : écrit quand même, mais un agent l'entendra autrement."""

    a_signaler: list[str] = field(default_factory=list)


def plan_complets(
    catalogue: CatalogueEtablissements,
    agents: list[AgentVu],
    adresse_organisation: AdresseEtablissement | None,
    annonce_organisation: ReglagesAnnonceOuverture | None,
    phrases: CataloguePhrases | None,
) -> PlanComplets:
    """Le plan du script, sans rien écrire. Rejoué après écriture : vide."""
    plan = PlanComplets()
    communes = phrases_communes(phrases)
    for fiche in catalogue.etablissements:
        # Avant la règle, seul un agent SANS fiche, joint par ses numéros, faisait passer ses horaires et son
        # adresse devant ceux de l'établissement : ce sont eux qui disent ce que l'appel entendait.
        par_numeros = [
            a for a in _agents_de(fiche, agents, catalogue) if _vide(a.configurations.get(CLE_FICHE_DE_LAGENT))
        ]
        de_la_fiche = [a.nom for a in agents if a.configurations.get(CLE_FICHE_DE_LAGENT) == fiche.id]
        ecrits: dict = {}
        _horaires(plan, fiche, par_numeros, ecrits)
        _adresse(plan, fiche, par_numeros, adresse_organisation, ecrits)
        for champ in CHAMPS_ANNONCE:
            if getattr(fiche, champ) is not None:
                plan.deja_a_jour += 1
                continue
            voulue = getattr(annonce_organisation, champ, None) if annonce_organisation is not None else None
            if _vide(voulue):
                continue  # l'organisation n'annonçait rien : l'établissement vide n'annonce rien non plus
            ecrits[champ] = voulue
            plan.actions.append(ActionReprise(sujet="fiche", cible=fiche.id, champ=champ, avant=None, apres=voulue))
        manquantes = {v: c for v, c in communes.items() if _vide(fiche.phrases.get(v))}
        plan.deja_a_jour += len(communes) - len(manquantes)
        if manquantes:
            ecrits["phrases"] = {**fiche.phrases, **manquantes}
            for variable, contenu in manquantes.items():
                plan.actions.append(
                    ActionReprise(sujet="fiche", cible=fiche.id, champ=f"phrases.{variable}", avant=None, apres=contenu)
                )
        if not ecrits:
            continue
        plan.fiches[fiche.id] = ecrits
        # Un agent qui a choisi cette fiche la lisait SEULE (C3) : sauf pour les phrases (toujours héritées
        # avant la règle), ce qui est écrit change ce qu'il entend. Écrit quand même (la règle), et dit.
        changes = sorted(c for c in ecrits if c != "phrases")
        if de_la_fiche and changes:
            plan.a_signaler.append(
                f"Fiche « {fiche.id} » : {', '.join(sorted(de_la_fiche))} la lisai(en)t seule ; "
                f"{', '.join(changes)} y sont désormais écrits depuis les valeurs communes."
            )
    return plan
