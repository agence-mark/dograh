"""[.mark] builder partie 2, U4 (F3, E16) : d'où vient la valeur de chaque réglage d'un agent.

Une seule grammaire pour l'héritage, calculée à partir des cinq mécanismes qui existent déjà (rien n'est stocké) :

* ``principal``      : un agent spécialisé lit chez son principal les réglages communs (``groupe/reglages.py``) ;
* ``etablissement``  : un agent qui sert une fiche lit les horaires et l'adresse de la fiche seule ;
* ``organisation``   : l'adresse de l'organisation, quand ni l'agent ni une fiche n'en ont ; la configuration des modèles
  de l'organisation, quand l'agent n'a pas la sienne ;
* ``agent``          : une valeur propre à l'agent (écrite et différente de ce qu'il hériterait) ;
* ``defaut``         : le défaut du schéma.

Une valeur écrite qui vaut ce que l'agent hériterait est dite héritée : l'écran enregistre toute la configuration résolue
(« revenir à la valeur héritée » pose donc la valeur héritée, sans clé à retirer), et seule une valeur DIFFÉRENTE est
« propre à l'agent ».

Aucune clé d'accès ne sort d'ici : la configuration des modèles n'a pas de valeur rendue (``masquee``) et tout champ dont
le nom sent un secret est remplacé par ``***``. Pur sauf ``lire`` (lectures, jamais d'écriture). Aucun mot de métier.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults
from api.services.groupe.passations import agent_principal_de
from api.services.groupe.reglages import (
    CLE_CERVEAU_PROPRE,
    CLES_COMMUNES,
    CLES_PROPRES,
    CLES_SUIVENT_LE_CERVEAU,
    a_son_cerveau,
)

ORIGINES = ("organisation", "principal", "etablissement", "agent", "defaut")

CLES_MODELES = ("model_overrides", "model_configuration_v2_override", "mark_per_service_override")
CLE_HORAIRES = "horaires_ouverture"
CLE_ADRESSE = "adresse_etablissement"
CLE_FICHE = "etablissement_id"
SENT_UN_SECRET = ("api_key", "token", "secret", "password", "credential")


def _masquer(valeur: Any) -> Any:
    """Copie de la valeur où tout champ au nom de secret est remplacé (défense en profondeur : aucun n'est attendu)."""
    if isinstance(valeur, dict):
        return {
            c: ("***" if any(m in str(c).lower() for m in SENT_UN_SECRET) else _masquer(v)) for c, v in valeur.items()
        }
    if isinstance(valeur, list):
        return [_masquer(v) for v in valeur]
    return copy.deepcopy(valeur)


def cles_du_schema() -> list[str]:
    """Toutes les clés de réglage d'un agent : le schéma, plus les clés communes et propres qu'il ne déclare pas (extra)."""
    return sorted({*WorkflowConfigurationDefaults.model_fields, *CLES_COMMUNES, *CLES_PROPRES})


def valeurs_par_defaut() -> dict[str, Any]:
    return WorkflowConfigurationDefaults().model_dump(mode="json")


def cles_suivies_du_principal(configurations: Mapping[str, Any]) -> frozenset[str]:
    """Les clés qu'un spécialisé reçoit de son principal (cerveau détaché : celles qui suivent le cerveau restent siennes)."""
    if agent_principal_de(configurations) is None:
        return frozenset()
    communes = set(CLES_COMMUNES)
    if a_son_cerveau(configurations):
        communes -= set(CLES_SUIVENT_LE_CERVEAU)
    communes.discard(CLE_CERVEAU_PROPRE)
    return frozenset(communes)


def calculer(
    configurations: Mapping[str, Any],
    *,
    configurations_du_principal: Mapping[str, Any] | None = None,
    fiche: Any | None = None,
    adresse_de_l_organisation: Any | None = None,
    modeles_de_l_organisation: bool = False,
) -> dict[str, dict[str, Any]]:
    """Pour chaque clé : ``origine``, ``valeur`` (effective), ``valeur_heritee``, ``propre`` (vrai pour l'origine ``agent``),
    ``modifiable`` (faux quand le principal règle la clé), ``masquee`` (vrai quand la valeur ne sort pas)."""
    defauts = valeurs_par_defaut()
    suivies = cles_suivies_du_principal(configurations)
    du_principal = dict(configurations_du_principal or {})
    resultat: dict[str, dict[str, Any]] = {}
    for cle in cles_du_schema():
        masquee = cle in CLES_MODELES
        defaut = defauts.get(cle)
        origine_heritee = "defaut"
        heritee: Any = defaut
        if cle in suivies:
            origine_heritee = "principal"
            heritee = du_principal.get(cle, defaut)
        elif fiche is not None and cle == CLE_HORAIRES:
            origine_heritee, heritee = "etablissement", getattr(fiche, "horaires_ouverture", None)
        elif fiche is not None and cle == CLE_ADRESSE:
            adresse = getattr(fiche, "adresse", None)
            origine_heritee, heritee = "etablissement", (adresse.model_dump(mode="json") if adresse is not None else None)
        elif cle == CLE_ADRESSE and adresse_de_l_organisation is not None:
            origine_heritee = "organisation"
            heritee = (
                adresse_de_l_organisation.model_dump(mode="json")
                if hasattr(adresse_de_l_organisation, "model_dump")
                else adresse_de_l_organisation
            )
        elif masquee and modeles_de_l_organisation:
            origine_heritee, heritee = "organisation", None
        ecrite = configurations.get(cle)
        a_une_valeur = ecrite is not None
        if origine_heritee == "principal":
            # Le principal règle la clé : une valeur écrite ici serait recopiée par-dessus à son prochain enregistrement.
            origine, valeur = "principal", heritee
        elif a_une_valeur and (masquee or ecrite != heritee):
            origine, valeur = "agent", ecrite
        else:
            origine, valeur = origine_heritee, heritee
        resultat[cle] = {
            "origine": origine,
            "valeur": None if masquee else _masquer(valeur),
            "valeur_heritee": None if masquee else _masquer(heritee),
            "propre": origine == "agent",
            "modifiable": origine_heritee != "principal",
            "masquee": masquee,
        }
    return resultat


async def lire(organization_id: int, workflow_id: int) -> dict[str, dict[str, Any]]:
    """Le calcul pour un agent de l'organisation (``ModeleRefuse`` 404 si l'agent est celui d'une autre)."""
    from api.services.configuration.ai_model_configuration import get_resolved_ai_model_configuration
    from api.services.etablissements.stockage import lire_etablissements
    from api.services.modeles_reglages import service as modeles
    from api.services.organization_preferences import get_organization_preferences

    active = await modeles.configuration_active(workflow_id, organization_id)
    configurations = active["configurations"]
    principal_id = agent_principal_de(configurations)
    du_principal: dict[str, Any] | None = None
    if principal_id is not None:
        try:
            du_principal = (await modeles.configuration_active(principal_id, organization_id))["configurations"]
        except modeles.ModeleRefuse:
            du_principal = None
    fiche = None
    fiche_id = configurations.get(CLE_FICHE)
    if isinstance(fiche_id, str) and fiche_id.strip():
        catalogue = await lire_etablissements(organization_id)
        fiche = next((e for e in catalogue.etablissements if e.id == fiche_id.strip()), None)
    preferences = await get_organization_preferences(organization_id)
    resolue = await get_resolved_ai_model_configuration(organization_id=organization_id)
    return calculer(
        configurations,
        configurations_du_principal=du_principal,
        fiche=fiche,
        adresse_de_l_organisation=getattr(preferences, CLE_ADRESSE, None),
        modeles_de_l_organisation=resolue.source != "empty",
    )
