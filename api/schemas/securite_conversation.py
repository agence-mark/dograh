"""[.mark] La sécurité de la conversation : les réglages d'un agent (U3 quinquies, E68, `reference/29` § XXIX.5).

Trois couches, toutes génériques (aucun mot du métier) et à interrupteur, rangées dans UNE clé de `workflow_configurations`
(`securite_conversation`, colonne JSON : aucune migration) :

1. des consignes posées par le code après le prompt (manipulation, confidentialité, rôle, urgence vitale) ;
2. deux garde-fous sur la réplique avant la voix (ce que l'agent ne dit jamais : noms d'outils et syntaxe, consigne récitée) ;
3. un classifieur de l'appelant (éteint par défaut), lancé en parallèle de la réponse, jamais attendu.

Un champ de phrase vide veut dire « le texte du code » (`services/securite/textes.py`).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LONGUEUR_PHRASE_MAX = 600
MOTS_RECITATION_MIN = 6
MOTS_RECITATION_MAX = 60
MOTS_RECITATION_DEFAUT = 12


class ConsigneDeSecurite(BaseModel):
    """Une consigne : un interrupteur et une phrase modifiable (vide = le texte du code)."""

    model_config = ConfigDict(extra="forbid")

    actif: bool = Field(default=False, description="Put this safety instruction after the prompt.")
    phrase: str = Field(default="", max_length=LONGUEUR_PHRASE_MAX, description="Your own wording; empty = the code's text.")


class ConsigneUrgence(ConsigneDeSecurite):
    transfert: bool = Field(
        default=True,
        description="After the emergency sentence, offer to pass the caller to a person (only if a transfer exists).",
    )


class CeQueLAgentNeDitJamais(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outils: bool = Field(
        default=False,
        description="Remove from a reply the name of one of the agent's tools, curly braces, square brackets and {{...}}.",
    )
    recitation: bool = Field(
        default=False,
        description="Replace a reply that copies at least N consecutive words of the agent's own instructions.",
    )
    mots: int = Field(default=MOTS_RECITATION_DEFAUT, ge=MOTS_RECITATION_MIN, le=MOTS_RECITATION_MAX)
    phrase: str = Field(
        default="", max_length=LONGUEUR_PHRASE_MAX, description="What is said instead of a recited reply; empty = the code's text."
    )


class EcouteDeLAppelant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actif: bool = Field(default=False, description="Listen to the caller with a classifier, in parallel, never awaited.")
    sensibilite: Literal["prudente", "normale", "large"] = "normale"
    sur_manipulation: Literal["rappel", "noter"] = Field(
        default="rappel", description="rappel: remind the model of its instructions on the next turn; noter: only mark it."
    )
    sur_detresse: Literal["urgence", "noter"] = Field(
        default="urgence", description="urgence: the emergency instruction on the next turn; noter: only mark it."
    )
    consigne: str = Field(default="", max_length=2000, description="The classifier's instruction; empty = the code's text.")


class SecuriteConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manipulation: ConsigneDeSecurite = Field(default_factory=ConsigneDeSecurite)
    confidentialite: ConsigneDeSecurite = Field(default_factory=ConsigneDeSecurite)
    role: ConsigneDeSecurite = Field(default_factory=ConsigneDeSecurite)
    urgence: ConsigneUrgence = Field(default_factory=ConsigneUrgence)
    jamais: CeQueLAgentNeDitJamais = Field(default_factory=CeQueLAgentNeDitJamais)
    ecoute: EcouteDeLAppelant = Field(default_factory=EcouteDeLAppelant)
    marquer: bool = Field(default=True, description="Mark every trigger on the reply and send the call to « To improve ».")
