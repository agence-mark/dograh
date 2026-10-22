"""[.mark] cloture-code, D152 (Evan, 22/10) : « Appliquer à tous les établissements ».

Chaque établissement a ses propres règles complètes (F-8) ; ce geste recopie UN réglage d'un
établissement (la source) dans tous les autres de l'organisation, en une seule transaction, pour ne pas
refaire dix fois la même modification. La valeur est LUE sur la source par le serveur (jamais envoyée
par l'écran) : ce qui est recopié est exactement ce qui est enregistré.

Les cinq familles :

| ``reglage``      | ``cle``                         | ce qui est recopié                                             |
|------------------|---------------------------------|----------------------------------------------------------------|
| ``planificateur``| un champ des règles             | ce champ (la fenêtre du tour de rôle comprise)                 |
| ``type``         | le code d'un type               | le type entier (copie sur chaque lieu)                         |
| ``module``       | ``<module>.<clé>``              | un réglage terrain d'un module                                 |
| ``fiche``        | un champ de la fiche            | horaires, adresse, annonce de fermeture, annonce de pause      |
| ``phrase``       | la variable d'une phrase        | son contenu au niveau de l'établissement                       |

Aucun mot de métier : des noms de champs.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Les champs de la fiche qui se recopient (ni le nom, ni les numéros, ni la fermeture immédiate : propres au lieu).
CHAMPS_DE_FICHE = ("horaires_ouverture", "adresse", "annonce_fermeture", "annonce_pause")

Famille = Literal["planificateur", "type", "module", "fiche", "phrase"]


class DemandeAppliquerATous(BaseModel):
    """Quel réglage de l'établissement source est recopié dans tous les autres."""

    model_config = ConfigDict(extra="forbid")

    reglage: Famille = Field(description="The family of the setting (see the table of the module).")
    cle: str = Field(
        min_length=1,
        max_length=100,
        description=(
            "Which setting of the family: a planner field, a type's code, « module.key », a field of the fiche "
            "(hours, address, announcements) or a sentence's variable."
        ),
    )


class EtablissementTouche(BaseModel):
    id: str
    nom: str


class ResultatAppliquerATous(BaseModel):
    """What the gesture did: the source, and every other establishment that now carries its value."""

    source: str = Field(description="Identifier of the establishment whose value was copied.")
    reglage: Famille
    cle: str
    etablissements: list[EtablissementTouche] = Field(
        default_factory=list, description="The other establishments of the organization, all written."
    )
