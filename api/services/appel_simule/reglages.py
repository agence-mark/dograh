"""Les réglages de l'appelant simulé, la bibliothèque de scénarios et le registre des séries (.mark,
chantier langwatch-et-fenetre-du-run, lot 3, L10, L13, L18, Q3).

Trois lignes de ``organization_configurations`` (aucune migration) :

- ``APPELANT_SIMULE`` : ``ReglagesAppelantSimule`` (modèles, consignes, voix, clés choisies,
  simultanéité, taille et plafond d'une série) ;
- ``SCENARIOS_SIMULES`` : ``BibliothequeScenarios``, rangés par agent ; l'écran lit et remplace
  les scénarios d'UN agent, jamais ceux des autres ;
- ``SERIES_SIMULEES`` : les dernières séries (``SerieSimulee``), pour le suivi et le reporting.

Lecture stricte pour l'écran (une ligne illisible lève : ne pas montrer une liste vide qu'un
enregistrement écraserait), comme la table des prix.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.db import db_client
from api.enums import OrganizationConfigurationKey
from api.schemas.appel_simule import (
    BibliothequeScenarios,
    ReglagesAppelantSimule,
    ScenarioSimule,
)

CLE_REGLAGES = OrganizationConfigurationKey.APPELANT_SIMULE.value
CLE_SCENARIOS = OrganizationConfigurationKey.SCENARIOS_SIMULES.value
CLE_SERIES = OrganizationConfigurationKey.SERIES_SIMULEES.value
SERIES_GARDEES = 100

EtatSerie = Literal["en_cours", "terminee", "arretee_plafond", "arretee", "echec"]


class AppelDeSerie(BaseModel):
    scenario_id: str
    scenario_nom: str
    run_id: int | None = None
    etat: Literal["a_jouer", "en_cours", "joue", "echec"] = "a_jouer"
    reussi: bool | None = None
    cout: float | None = None
    erreur: str | None = None


class SerieSimulee(BaseModel):
    id: str
    workflow_id: int
    lancee_le: str
    lancee_par: int
    etat: EtatSerie = "en_cours"
    plafond: float
    devise: str = "USD"
    cout_estime: float | None = None
    cout: float = 0.0
    cout_partiel: bool = False
    raison: str | None = None
    terminee_le: str | None = None
    appels: list[AppelDeSerie] = Field(default_factory=list)


class RegistreSeries(BaseModel):
    format: Literal["series-simulees-mark"] = "series-simulees-mark"
    version: Literal[1] = 1
    series: list[SerieSimulee] = Field(default_factory=list)


def maintenant() -> str:
    return datetime.now(UTC).isoformat()


async def _lire(organization_id: int, cle: str, modele):
    ligne = await db_client.get_configuration(organization_id, cle)
    if ligne is None or not ligne.value:
        return modele()
    return modele.model_validate(ligne.value)


async def _ecrire(organization_id: int, cle: str, valeur: BaseModel) -> None:
    await db_client.upsert_configuration(
        organization_id, cle, valeur.model_dump(mode="json")
    )


# --- Réglages ------------------------------------------------------------------------------------


async def lire_reglages(organization_id: int) -> ReglagesAppelantSimule:
    return await _lire(organization_id, CLE_REGLAGES, ReglagesAppelantSimule)


async def enregistrer_reglages(
    organization_id: int, reglages: ReglagesAppelantSimule
) -> ReglagesAppelantSimule:
    await _ecrire(organization_id, CLE_REGLAGES, reglages)
    return reglages


# --- Scénarios, par agent ------------------------------------------------------------------------


async def lire_scenarios(
    organization_id: int, workflow_id: int
) -> list[ScenarioSimule]:
    bibliotheque = await _lire(organization_id, CLE_SCENARIOS, BibliothequeScenarios)
    return [s for s in bibliotheque.scenarios if s.workflow_id == workflow_id]


async def remplacer_scenarios(
    organization_id: int, workflow_id: int, scenarios: list[ScenarioSimule]
) -> list[ScenarioSimule]:
    """Remplace les scénarios de CET agent ; ceux des autres agents restent tels quels. Un
    scénario envoyé pour un autre agent est refusé (ValueError)."""
    if any(s.workflow_id != workflow_id for s in scenarios):
        raise ValueError("A scenario belongs to another agent.")
    bibliotheque = await _lire(organization_id, CLE_SCENARIOS, BibliothequeScenarios)
    autres = [s for s in bibliotheque.scenarios if s.workflow_id != workflow_id]
    nouvelle = BibliothequeScenarios(scenarios=[*autres, *scenarios])
    await _ecrire(organization_id, CLE_SCENARIOS, nouvelle)
    return scenarios


# --- Séries --------------------------------------------------------------------------------------


async def lire_series(organization_id: int) -> list[SerieSimulee]:
    return (await _lire(organization_id, CLE_SERIES, RegistreSeries)).series


async def lire_serie(organization_id: int, serie_id: str) -> SerieSimulee | None:
    return next(
        (s for s in await lire_series(organization_id) if s.id == serie_id), None
    )


async def ecrire_serie(organization_id: int, serie: SerieSimulee) -> SerieSimulee:
    """Ajoute ou remplace la série ; garde les ``SERIES_GARDEES`` plus récentes. Une seule série
    tourne à la fois par organisation (verrou de ``serie.py``) : pas d'écritures concurrentes."""
    registre = await _lire(organization_id, CLE_SERIES, RegistreSeries)
    autres = [s for s in registre.series if s.id != serie.id]
    registre.series = [serie, *autres][:SERIES_GARDEES]
    await _ecrire(organization_id, CLE_SERIES, registre)
    return serie
