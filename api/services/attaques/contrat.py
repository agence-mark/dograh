"""[.mark] U11 (§ 17) : le contrat de périmètre, confirmé AVANT toute sonde (« never escalate mid-run »).

Profondeur : rapide (environ 15 sondes), standard (35 à 45), poussée (80 et plus, la seule qui répète pour mesurer
l'instabilité). Aucune modification de l'environnement par défaut ; rapport seul par défaut. Sans ``confirme``, rien ne part.
Ce chantier ne construit ni la modification de l'environnement ni la correction automatique : les demander est refusé avec
la raison, jamais ignoré en silence.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

SONDES_PAR_PROFONDEUR = {"rapide": 15, "standard": 40, "poussee": 80}
REPETITIONS_PAR_PROFONDEUR = {"rapide": 1, "standard": 1, "poussee": 3}
ESSAIS_MAX = 5  # « essais par attaque » : réglable, borné (la maquette propose 1, 3 ou 5)
JEUX = ("catalogue", "public")


class RefusDuContrat(Exception):
    pass


class Contrat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profondeur: str = Field(default="rapide", pattern="^(rapide|standard|poussee)$")
    confirme: bool = Field(default=False, description="The scope is confirmed by a person: nothing is probed before.")
    modifie_l_environnement: bool = Field(default=False, description="Not built: always refused when true.")
    corrige: bool = Field(default=False, description="Not built: the report alone, a person decides the fixes.")
    essais: int | None = Field(
        default=None, ge=1, le=ESSAIS_MAX, description="Tries to reproduce an attack that got through before it is confirmed (default: set by the depth)."
    )
    temoin: bool = Field(default=True, description="A harmless witness after each attack, and a check that the judge does not cry wolf.")
    jeu: str = Field(default="catalogue", pattern="^(catalogue|public)$", description="catalogue = the 15 techniques; public = the imported public set.")

    def verifier(self) -> "Contrat":
        if not self.confirme:
            raise RefusDuContrat("The scope of the attack is not confirmed: say the depth and confirm it before any probe.")
        if self.modifie_l_environnement:
            raise RefusDuContrat("Changing the environment during an attack is not available: the agent is attacked as it is.")
        if self.corrige:
            raise RefusDuContrat("Automatic fixes are not available: the report is read and a person decides.")
        return self

    @property
    def sondes_max(self) -> int:
        return SONDES_PAR_PROFONDEUR[self.profondeur]

    @property
    def repetitions(self) -> int:
        return self.essais or REPETITIONS_PAR_PROFONDEUR[self.profondeur]
