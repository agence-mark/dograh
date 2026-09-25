"""[.mark] La fiche de l'agent : les champs que l'outil `noter_information` écrit.

Plan « la fiche au fil de l'eau », lot 1 (D22) : le minimum -- nom du champ, type,
dicté ou déduit, indice. Rangée dans `workflow_configurations` (colonne JSON) :
aucune migration de base (D32).
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# PB3 : les bornes d'une liste fermée de valeurs (reprises par l'écran).
MAX_VALEURS = 20
MAX_LONGUEUR_VALEUR = 40


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
    # D42 : quel module lit ce champ. Vide = déduit du nom (``lecteur_effectif``).
    # ⛔ Gardé VIDE en base, jamais remplacé par sa valeur déduite : l'écran
    # comparerait ce qu'il a envoyé à ce qu'il relit et se croirait modifié, et
    # un champ renommé garderait le lecteur de son ancien nom (constaté le 24/09).
    lecteur: Literal["commune", "rue", "date", "lexique", "aucun"] | None = Field(
        default=None,
        description=(
            "Which reader checks the value: town (official name and INSEE code), "
            "street (official street name), date (a relative date such as 'last "
            "year' computed on the day of the call, the caller's words kept), "
            "trade vocabulary (a name of the organization's vocabulary, sure only "
            "when recognised), or none. Empty: from the field name."
        ),
    )

    # PB3 (patch du banc, 25/09) : une liste fermée de valeurs. Le champ n'accepte
    # qu'une d'elles, écrite sous la forme déclarée, d'où que vienne la valeur ;
    # et un champ déduit qui en déclare une est exempté de l'ancrage (PB2).
    # Vide = aucune liste. Rangée dans le JSON de l'agent : aucune migration.
    valeurs: list[str] | None = Field(
        default=None,
        description=(
            "Allowed values: the field only accepts one of them (case and accents "
            "ignored), written as declared. Empty: any value."
        ),
    )

    @field_validator("valeurs")
    @classmethod
    def _valeurs_lisibles(cls, valeurs: list[str] | None) -> list[str] | None:
        if valeurs is None:
            return None
        propres = [v.strip() for v in valeurs if v and v.strip()]
        if len(propres) > MAX_VALEURS:
            raise ValueError(f"at most {MAX_VALEURS} allowed values")
        for valeur in propres:
            if len(valeur) > MAX_LONGUEUR_VALEUR:
                raise ValueError(
                    f"allowed value '{valeur[:20]}…' is longer than "
                    f"{MAX_LONGUEUR_VALEUR} characters"
                )
        return propres or None

    @property
    def lecteur_effectif(self) -> str:
        return self.lecteur or lecteur_par_defaut(self.nom)


def lecteur_par_defaut(nom: str) -> str:
    """D42 : ``commune*`` -> commune ; ``adresse*`` et ``rue*`` -> rue ; D46 :
    ``*date*``, ``dernier_*`` et ``annee*`` -> date ; C10 (PB12) : ``marque*``
    -> lexique ; sinon aucun."""
    if nom.startswith("commune"):
        return "commune"
    if nom.startswith("marque"):
        return "lexique"
    if nom.startswith(("adresse", "rue")):
        return "rue"
    if "date" in nom or nom.startswith(("dernier_", "annee")):
        return "date"
    return "aucun"


def cle_insee(nom: str) -> str:
    """Où le code INSEE d'une commune sûre est écrit, à côté de son nom."""
    return f"{nom}_insee"


def cle_dit(nom: str) -> str:
    """D46 : où les mots de la personne sont gardés, à côté de la date calculée."""
    return f"{nom}_dit"


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
        "tour_appelant",
    }
)


def verifier_champs(champs: list[ChampFiche]) -> list[ChampFiche]:
    """Refuse un nom réservé ou un nom en double (422 à l'enregistrement)."""
    vus: set[str] = set()
    insee = {cle_insee(c.nom) for c in champs if c.lecteur_effectif == "commune"}
    dits = {cle_dit(c.nom) for c in champs if c.lecteur_effectif == "date"}
    for champ in champs:
        if champ.nom in insee:
            raise ValueError(
                f"fiche field name '{champ.nom}' is where a town's INSEE code is written"
            )
        if champ.nom in dits:
            raise ValueError(
                f"fiche field name '{champ.nom}' is where the caller's words for a "
                "date are kept"
            )
        if champ.nom in NOMS_RESERVES:
            raise ValueError(f"fiche field name '{champ.nom}' is reserved")
        if champ.nom in vus:
            raise ValueError(f"fiche field name '{champ.nom}' is used twice")
        vus.add(champ.nom)
    return champs
