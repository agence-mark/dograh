"""[.mark] La fiche de l'agent : les champs que l'outil `noter_information` écrit.

Plan « la fiche au fil de l'eau », lot 1 (D22) : le minimum -- nom du champ, type,
dicté ou déduit, indice. Rangée dans `workflow_configurations` (colonne JSON) :
aucune migration de base (D32).
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class OrigineChamp(str, Enum):
    """D4 : un champ DICTÉ subit le contrôle de citation, un champ DÉDUIT non."""

    dicte = "dicte"
    deduit = "deduit"


class ChampFiche(BaseModel):
    nom: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]{0,63}$",
        description="snake_case name of the field, also the tool parameter name.",
    )
    # Mêmes valeurs que `VariableType` des variables d'extraction, sans importer
    # la couche workflow depuis les schémas.
    type: Literal["string", "number", "boolean"] = "string"
    origine: OrigineChamp = Field(
        default=OrigineChamp.dicte,
        description=(
            "Dictated: the value must have been said by the caller (name, town, "
            "street, number, brand). Deduced: the model sums it up (reason, urgency)."
        ),
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Hint given to the model for this parameter.",
    )
    # D42 : quel module lit ce champ. Vide = déduit du nom (``lecteur_par_defaut``).
    lecteur: Literal["commune", "rue", "aucun"] | None = Field(
        default=None,
        description=(
            "Which reader checks the value: town (official name and INSEE code), "
            "street (official street name), or none. Empty: from the field name."
        ),
    )

    @model_validator(mode="after")
    def _lecteur_deduit(self) -> "ChampFiche":
        if self.lecteur is None:
            self.lecteur = lecteur_par_defaut(self.nom)
        return self


def lecteur_par_defaut(nom: str) -> str:
    """D42 : ``commune*`` -> commune ; ``adresse*`` et ``rue*`` -> rue ; sinon aucun."""
    if nom.startswith("commune"):
        return "commune"
    if nom.startswith(("adresse", "rue")):
        return "rue"
    return "aucun"


def cle_insee(nom: str) -> str:
    """Où le code INSEE d'une commune sûre est écrit, à côté de son nom."""
    return f"{nom}_insee"


# Clés que le moteur et les modules écrivent eux-mêmes dans la fiche de l'appel.
# Un champ de ce nom les écraserait : refusé à l'enregistrement. ⚠️ Tenue à jour
# par un test qui la compare aux clés réelles du moteur et des modules.
NOMS_RESERVES = frozenset(
    {
        # moteur (`_ENGINE_OWNED_CONTEXT_KEYS` et clés d'état)
        "call_disposition",
        "mapped_call_disposition",
        "call_status",
        "call_tags",
        "answer_supervisor",
        "extracted_variables",
        "nodes_visited",
        "agent_visits",
        # traces des modules
        "communes_verifiees",
        "voies_verifiees",
        "epellations_lues",
        "nombres_lus",
        "lexique_reconnu",
        "lexique_metier",
        # la fiche elle-même
        "fiche_etat",
        "fiche_journal",
    }
)


def verifier_champs(champs: list[ChampFiche]) -> list[ChampFiche]:
    """Refuse un nom réservé ou un nom en double (422 à l'enregistrement)."""
    vus: set[str] = set()
    insee = {cle_insee(c.nom) for c in champs if c.lecteur == "commune"}
    for champ in champs:
        if champ.nom in insee:
            raise ValueError(
                f"fiche field name '{champ.nom}' is where a town's INSEE code is written"
            )
        if champ.nom in NOMS_RESERVES:
            raise ValueError(f"fiche field name '{champ.nom}' is reserved")
        if champ.nom in vus:
            raise ValueError(f"fiche field name '{champ.nom}' is used twice")
        vus.add(champ.nom)
    return champs
