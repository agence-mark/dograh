"""[.mark] Les agents que l'organisation sert, tels que le portail les lit (chantier agents-specialises,
lot 9 = lot 6 du plan fiche-etablissement, M9, M10, D89, D90, A13).

Tout est LU dans Dograh (la définition publiée de chaque agent), jamais saisi : un agent sait faire ce
que ses outils et ses réglages disent. Aucun mot de métier : des mécanismes (transfert, demande
transmise, rendez-vous, courriel, SMS, vérification) et des identifiants d'agents.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CapacitesAgent(BaseModel):
    """Ce que sait faire un agent (D89) : déduit de sa définition publiée."""

    transfert: bool = Field(
        default=False,
        description="Outil de transfert d'appel, ou de direction vers une personne.",
    )
    demande_transmise: bool = Field(
        default=False, description="Outil de direction vers une personne de l'équipe."
    )
    rendez_vous: bool = Field(
        default=False,
        description="Outils du planificateur (créneaux, pose d'un rendez-vous).",
    )
    mail: bool = Field(
        default=False, description="Après-appel allumé avec le courriel."
    )
    sms: bool = Field(
        default=False,
        description="Après-appel allumé avec un SMS à l'appelant ou à l'équipe.",
    )
    verification: bool = Field(
        default=False, description="Vérification de l'appelant allumée."
    )

    def ou(self, autre: "CapacitesAgent") -> "CapacitesAgent":
        """Les capacités de deux agents réunis (un groupe : l'ensemble)."""
        return CapacitesAgent(
            **{
                nom: bool(getattr(self, nom) or getattr(autre, nom))
                for nom in type(self).model_fields
            }
        )


class LienDePassation(BaseModel):
    """Qui appelle qui, dans un groupe."""

    de: int
    vers: int
    par: Literal["outil", "retour"] = Field(
        description="outil : une passation écrite dans les outils de l'agent ; retour : l'appel est rendu au principal par le code."
    )


class AgentServi(BaseModel):
    id: int
    nom: str
    version_publiee: int | None = Field(
        default=None, description="Numéro de la version publiée ; vide : jamais publié."
    )
    numeros: list[str] = Field(
        default_factory=list, description="Les numéros actifs qui mènent à cet agent."
    )
    etablissement_id: str | None = Field(
        default=None, description="La fiche choisie par l'agent."
    )
    role: Literal["seul", "principal", "specialise"] = "seul"
    agent_principal_id: int | None = None
    agents_specialises: list[int] = Field(default_factory=list)
    appelle: list[int] = Field(
        default_factory=list,
        description="Les agents qu'il peut appeler (ses outils de passation).",
    )
    appele_par: list[int] = Field(
        default_factory=list, description="Les agents qui peuvent l'appeler."
    )
    capacites: CapacitesAgent = Field(default_factory=CapacitesAgent)
    rattache: bool = Field(
        default=False, description="Rattaché au portail par .mark (D90)."
    )


class GroupeServi(BaseModel):
    principal_id: int
    specialises: list[int] = Field(default_factory=list)
    capacites: CapacitesAgent = Field(
        default_factory=CapacitesAgent,
        description="Les capacités de l'ensemble : le principal et ses spécialisés.",
    )
    passations: list[LienDePassation] = Field(default_factory=list)
    rattache: bool = Field(
        default=False,
        description="Le principal est rattaché ; ses spécialisés le sont avec lui (A13).",
    )


class AgentsServis(BaseModel):
    agents: list[AgentServi] = Field(default_factory=list)
    groupes: list[GroupeServi] = Field(default_factory=list)


class DemandeRattachement(BaseModel):
    workflow_ids: list[int] = Field(min_length=1, max_length=50)
    rattache: bool = Field(
        default=True, description="Vrai : rattacher ; faux : détacher."
    )


class ResultatRattachement(BaseModel):
    rattaches: list[int] = Field(
        default_factory=list,
        description="Les agents rattachés par ce geste (déjà rattachés : absents).",
    )
    detaches: list[int] = Field(default_factory=list)
    agents: list[int] = Field(
        default_factory=list,
        description="Tous les agents concernés, les spécialisés d'un principal compris.",
    )


class DemandeControleHoraires(BaseModel):
    texte: str = Field(
        max_length=4000, description="Les horaires, au format lisible que lit l'agent."
    )


class ResultatControleHoraires(BaseModel):
    valide: bool
    raison: str | None = Field(
        default=None,
        description="Pourquoi le texte est refusé (ligne et cause), sinon vide.",
    )
