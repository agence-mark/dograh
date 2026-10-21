"""[.mark] Chantier fiabilite-orchestration (F15, F18, F23) puis correctifs-apres-banc-v4 (lot 4) : une
règle de phrase dite par le code.

Une règle se lit comme une phrase : « Dans [OÙ], quand [MOTIF] [pour l'outil …], le code dit
[PHRASE 1 / 2 / 3] [tournées | dans l'ordre] au bout de [DÉLAI], puis la redit toutes les
[INTERVALLE], au plus [N] fois par attente et [M] fois dans l'appel. Ensuite : [SORTIE]. »

Le **motif** vient du catalogue ``api.services.phrases.catalogue`` ; l'**endroit** est le groupe, l'agent
ou une étape de l'agent (repérée par son identifiant de nœud, le nom n'est qu'affiché ; une règle d'avant,
repérée par le nom seul, se relit telle quelle). Rangée dans la configuration de l'agent (clé
``phrases_regles``) : aucune migration de base. Chaque case nouvelle a pour défaut le comportement
d'avant (zéro perte). ⛔ Aucun mot de métier ici : le texte est une donnée réglée à l'écran.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_VARIANTES = 3
MAX_LONGUEUR_PHRASE = 300
MAX_REGLES = 60
# 0 = dès que l'attente commence ; le minimum de chaque motif est lu dans le catalogue.
DELAI_MIN_S = 0.0
DELAI_MAX_S = 120.0
REDITE_MIN_S = 2.0
REDITE_MAX_S = 60.0
MAX_PAR_ATTENTE = 5
MAX_PAR_APPEL = 20
MAX_OUTILS = 20

PORTEE_GROUPE = "groupe"
PORTEE_AGENT = "agent"
PORTEE_ETAPE = "etape"

ORDRE_TOURNEES = "tournees"
ORDRE_DANS_L_ORDRE = "dans_l_ordre"

ACTION_CONTINUER = "continuer"
ACTION_MODELE = "modele"
ACTION_TRANSFERER = "transferer"
ACTION_RACCROCHER = "raccrocher"
ACTIONS = (ACTION_CONTINUER, ACTION_MODELE, ACTION_TRANSFERER, ACTION_RACCROCHER)

# Les anciens identifiants de motif, lus comme les nouveaux (le motif « un connecteur échoue » est
# devenu « un outil échoue » : les règles d'avant se lisent telles quelles).
ALIAS_DE_MOTIFS = {"connecteur_echoue": "outil_echoue"}


class NoteDeSortie(BaseModel):
    """Noter dans la fiche : [un champ de la fiche] = [une valeur de sa liste]."""

    champ: str = Field(..., min_length=1, max_length=200)
    valeur: str = Field(..., min_length=1, max_length=300)

    @field_validator("champ", "valeur")
    @classmethod
    def _nettoye(cls, texte: str) -> str:
        propre = " ".join(str(texte or "").split())
        if not propre:
            raise ValueError("empty")
        return propre


def _phrases_propres(phrases: list[str] | None) -> list[str]:
    propres: list[str] = []
    for brute in phrases or []:
        texte = " ".join(str(brute or "").split())
        if not texte:
            continue
        if len(texte) > MAX_LONGUEUR_PHRASE:
            raise ValueError(f"a sentence is longer than {MAX_LONGUEUR_PHRASE} characters")
        if texte not in propres:
            propres.append(texte)
    return propres


class Sortie(BaseModel):
    """« Ensuite » : dire, noter dans la fiche, puis une action finale, toujours dans cet ordre.
    Chaque élément est facultatif ; ``action`` vide : l'action par défaut du motif (le comportement
    d'avant)."""

    phrases: list[str] = Field(
        default_factory=list,
        max_length=MAX_VARIANTES,
        description="What the voice says on the way out (one to three variants, rotated).",
    )
    noter: NoteDeSortie | None = Field(
        default=None, description="A field of the call record and one of its values to write."
    )
    action: Literal["continuer", "modele", "transferer", "raccrocher"] | None = Field(
        default=None,
        description="The final action. Empty: the default of the cause (the behavior before).",
    )
    destination: str | None = Field(
        default=None,
        max_length=200,
        description="For a transfer: the key of a member of the team (set in Team).",
    )

    @field_validator("phrases")
    @classmethod
    def _phrases(cls, phrases: list[str]) -> list[str]:
        return _phrases_propres(phrases)

    @model_validator(mode="after")
    def _coherente(self) -> Sortie:
        if self.action == ACTION_TRANSFERER:
            if not (self.destination or "").strip():
                raise ValueError("a transfer exit needs its destination")
            self.destination = self.destination.strip()
        else:
            self.destination = None
        return self

    @property
    def posee(self) -> bool:
        """Au moins un élément réglé (sinon : le comportement d'avant)."""
        return bool(self.phrases or self.noter or self.action)


class ReglePhrase(BaseModel):
    motif: str = Field(
        ...,
        pattern=r"^[a-z][a-z_]{0,63}$",
        description="The cause or problem that makes the code speak (from the catalogue).",
    )
    portee: Literal["groupe", "agent", "etape"] = Field(
        default=PORTEE_AGENT,
        description=(
            "Where the rule applies: the whole group (set on the main agent), this agent, "
            "or one step of this agent."
        ),
    )
    etape: str | None = Field(
        default=None,
        max_length=200,
        description="The step name, shown on screen (a rule from before is found by it).",
    )
    etape_id: str | None = Field(
        default=None,
        max_length=200,
        description="The step's node identifier: renaming the step keeps its rules.",
    )
    outils: list[str] = Field(
        default_factory=list,
        max_length=MAX_OUTILS,
        description="The tools this rule aims at (tool causes only). Empty: all tools.",
    )
    variantes: list[str] = Field(
        default_factory=list,
        max_length=MAX_VARIANTES,
        description=(
            "One to three sentences said by the voice, without the model. The code rotates "
            "them and never says the same one twice in a call while another is left."
        ),
    )
    ordre: Literal["tournees", "dans_l_ordre"] = Field(
        default=ORDRE_TOURNEES,
        description="Rotated, or in order (the first time sentence 1, the second time sentence 2...).",
    )
    delai_s: float | None = Field(
        default=None,
        ge=DELAI_MIN_S,
        le=DELAI_MAX_S,
        description="After how long the sentence is said, for a cause that has a delay (0 = at once).",
    )
    redite_s: float | None = Field(
        default=None,
        ge=REDITE_MIN_S,
        le=REDITE_MAX_S,
        description=(
            "Says it again every so often, counted from the end of the previous sentence. "
            "Empty: never."
        ),
    )
    max_par_attente: int | None = Field(
        default=None,
        ge=1,
        le=MAX_PAR_ATTENTE,
        description=(
            "At most this many times for one wait, the first included. Empty: once. For the "
            "caller's silence: the number of prompts."
        ),
    )
    max_par_appel: int | None = Field(
        default=None,
        ge=1,
        le=MAX_PAR_APPEL,
        description=(
            "At most this many times in the call. Empty: no limit. For a problem: the number of "
            "incidents allowed before the exit."
        ),
    )
    ensuite: Sortie = Field(
        default_factory=Sortie, description="What happens after the last time, or when it repeats."
    )
    texte_de_l_agent: bool = Field(
        default=False,
        description=(
            "Background work only: the announcement is the one the agent writes when it hands the "
            "work over, falling back on the sentences above."
        ),
    )
    active: bool = Field(default=True, description="Off: the code says nothing for this cause.")

    @field_validator("motif", mode="before")
    @classmethod
    def _motif_d_avant(cls, motif: object) -> object:
        return ALIAS_DE_MOTIFS.get(motif, motif) if isinstance(motif, str) else motif

    @field_validator("variantes")
    @classmethod
    def _variantes_propres(cls, variantes: list[str]) -> list[str]:
        return _phrases_propres(variantes)

    @field_validator("outils")
    @classmethod
    def _outils_propres(cls, outils: list[str]) -> list[str]:
        propres: list[str] = []
        for brut in outils or []:
            nom = " ".join(str(brut or "").split())
            if nom and nom not in propres:
                propres.append(nom)
        return propres

    @model_validator(mode="after")
    def _endroit_coherent(self) -> ReglePhrase:
        from api.services.phrases.catalogue import MOTIFS

        motif = MOTIFS.get(self.motif)
        if motif is None:
            raise ValueError(f"unknown cause: {self.motif}")
        if self.portee == PORTEE_ETAPE:
            self.etape = (self.etape or "").strip() or None
            self.etape_id = (self.etape_id or "").strip() or None
            if not (self.etape or self.etape_id):
                raise ValueError("a step rule needs its step")
        else:
            self.etape = None
            self.etape_id = None
        if self.active and not self.variantes and not self.texte_de_l_agent:
            raise ValueError("an active rule needs at least one sentence")
        if not motif.a_un_delai:
            self.delai_s = None
        elif self.delai_s is not None and self.delai_s < motif.delai_min_s:
            raise ValueError(f"the delay of '{motif.id}' is at least {motif.delai_min_s} s")
        if not motif.peut_redire:
            self.redite_s = None
            self.max_par_attente = None
        if not motif.filtre_outil:
            self.outils = []
        if self.texte_de_l_agent and not motif.texte_de_l_agent:
            self.texte_de_l_agent = False
        if self.ensuite.action is not None and self.ensuite.action not in motif.sorties_permises:
            raise ValueError(f"the exit '{self.ensuite.action}' is not allowed for '{motif.id}'")
        return self

    @property
    def cle(self) -> tuple[str, str, str | None, tuple[str, ...]]:
        """L'unicité : (motif, portée, étape, outils)."""
        return (
            self.motif,
            self.portee,
            self.etape_id or self.etape,
            tuple(sorted(self.outils)),
        )


def verifier_regles(regles: list[ReglePhrase]) -> list[ReglePhrase]:
    """Deux règles du même motif au même endroit pour les mêmes outils sont refusées (F23)."""
    vues: set[tuple] = set()
    for regle in regles:
        if regle.cle in vues:
            endroit = regle.etape or regle.portee
            raise ValueError(f"two rules for the cause '{regle.motif}' at '{endroit}'")
        vues.add(regle.cle)
    return regles
