"""[.mark] U11 : les réglages de la publication d'un agent (« Avant de publier », déploiement progressif).

Rangés dans UNE clé de `workflow_configurations` (`publication`, colonne JSON : aucune migration). Chaque contrôle a trois
positions : éteint, prévient, bloque. Les défauts reproduisent la garde d'avant (tests obligatoires et bilan du prompt
bloquent, le reste est éteint) ; le déploiement progressif est éteint : une publication vaut pour tous les appels.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Position = Literal["eteint", "previent", "bloque"]


class ControlesDePublication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tests_obligatoires: Position = "bloque"
    bilan_du_prompt: Position = "bloque"
    liste_vocale: Position = "eteint"
    attaques: Position = "eteint"
    garde_fous: Position = "eteint"
    # [.mark] Partie 3, SA-L3a (05 § 11, § 2, § 15) : les lignes de « Prêt à publier ». Variables, briques et outils bloquent par
    # défaut (une ligne obligatoire non faite bloque Publier par le même réglage) ; la sortie d'impasse sans issue bloque aussi ;
    # les réglages sans effet et les deux webhooks préviennent (une bonne pratique n'est jamais un blocage codé).
    variables: Position = "bloque"
    briques: Position = "bloque"
    outils: Position = "bloque"
    sans_effet: Position = "previent"
    sortie_d_impasse: Position = "bloque"
    deux_webhooks: Position = "previent"


class DeploiementProgressif(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actif: bool = Field(default=False, description="Allow a new version to take only a share of the calls. Off: a publication is for all calls.")


class Publication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    controles: ControlesDePublication = Field(default_factory=ControlesDePublication)
    deploiement: DeploiementProgressif = Field(default_factory=DeploiementProgressif)


class DemandeDePublication(BaseModel):
    """Corps FACULTATIF de ``POST /workflow/{id}/publish`` : sans corps, la route se comporte comme avant."""

    model_config = ConfigDict(extra="forbid")

    forcer: bool = Field(default=False, description="Publish although a blocking check fails. A reason is then required.")
    raison: str | None = Field(default=None, max_length=600, description="Why the publication is forced: written to the journal with the person.")
    pourcentage: int | None = Field(
        default=None, ge=1, le=99, description="Progressive deployment only: the share of calls the new version takes (the rest stays on the previous one)."
    )
    note: str | None = Field(default=None, max_length=600, description="What changes, for the journal.")
