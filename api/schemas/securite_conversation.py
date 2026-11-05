"""[.mark] La sécurité de la conversation : les réglages d'un agent (U3 quinquies, E68, `reference/29` § XXIX.5).

Trois couches, toutes génériques (aucun mot du métier) et à interrupteur, rangées dans UNE clé de `workflow_configurations`
(`securite_conversation`, colonne JSON : aucune migration) :

1. des consignes posées par le code après le prompt (manipulation, confidentialité, rôle, urgence vitale) ;
2. deux garde-fous sur la réplique avant la voix (ce que l'agent ne dit jamais : noms d'outils et syntaxe, consigne récitée) ;
3. un classifieur de l'appelant (éteint par défaut), lancé en parallèle de la réponse, jamais attendu.

Un champ de phrase vide veut dire « le texte du code » (`services/securite/textes.py`).
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

LONGUEUR_PHRASE_MAX = 600
NUMERO_URGENCE_MAX = 20
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


class GardeUrgence(BaseModel):
    """L3e : le garde-fou URGENCE du code (mots et tournures, AUCUN appel de modèle). Éteint par défaut. Quand il reconnaît une détresse ou
    une urgence médicale dans les mots de l'appelant, il dit la phrase du catalogue (motif ``urgence_vitale``, une fois par appel) avec le
    numéro d'urgence ci-dessous, note le déclenchement et rappelle au modèle de ne pas la redire."""

    model_config = ConfigDict(extra="forbid")

    actif: bool = Field(default=False, description="Recognise distress or a medical emergency in the caller's words (no model call) and say the emergency sentence.")
    numero: str = Field(
        default="112",
        max_length=NUMERO_URGENCE_MAX,
        pattern=r"^[0-9+ ]{2,20}$",
        description="The emergency number said in the sentence (112 in Europe).",
    )
    mots_en_plus: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=60)]] = Field(
        default_factory=list, max_length=20, description="Words or phrases of your own that also trigger it."
    )


class SecuriteConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manipulation: ConsigneDeSecurite = Field(default_factory=ConsigneDeSecurite)
    confidentialite: ConsigneDeSecurite = Field(default_factory=ConsigneDeSecurite)
    role: ConsigneDeSecurite = Field(default_factory=ConsigneDeSecurite)
    urgence: ConsigneUrgence = Field(default_factory=ConsigneUrgence)
    jamais: CeQueLAgentNeDitJamais = Field(default_factory=CeQueLAgentNeDitJamais)
    ecoute: EcouteDeLAppelant = Field(default_factory=EcouteDeLAppelant)
    garde_urgence: GardeUrgence = Field(default_factory=GardeUrgence)
    marquer: bool = Field(default=True, description="Mark every trigger on the reply and send the call to « To improve ».")
