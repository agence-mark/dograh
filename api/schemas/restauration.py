"""[.mark] Module Restauration, lot 6 : les corps et les réponses des routes du temps (contrat portail ↔ fork § 2, figé dans ``contrat_portail_fork.json``).

La puce du temps du portail lit l'état de chaque type de commande et ce que l'agent annonce (``GET``), et pose la durée ajoutée et la pause d'un
type (``PUT``). Aucun texte de caisse : des valeurs fermées et des nombres.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TypeDeCommande = Literal["emporter", "livraison", "sur_place", "reservation"]


class PauseDemandee(BaseModel):
    """Une pause du type. Sans ``jusqu_a`` ni ``minutes`` : jusqu'à la fin de la journée (une pause oubliée ne dure jamais plus d'un jour)."""

    model_config = ConfigDict(extra="forbid")

    jusqu_a: datetime | None = Field(default=None, description="Reprise à cette heure (avec fuseau).")
    minutes: int | None = Field(default=None, ge=1, le=720, description="Reprise dans ce nombre de minutes.")


class TempsDemande(BaseModel):
    """La puce d'un type : ``minutes_ajoutees`` REMPLACE la durée ajoutée du type (0 la retire) ; ``pause`` absente laisse la pause intacte, ``null``
    la lève."""

    model_config = ConfigDict(extra="forbid")

    type: TypeDeCommande
    minutes_ajoutees: int = Field(default=0, ge=0, le=240, description="Minutes ajoutées par-dessus le délai du type (coup de feu).")
    jusqu_a: datetime | Literal["fin_du_service"] | None = Field(
        default=None, description="La durée ajoutée s'éteint à cette heure, ou à la fin du service (lue dans les horaires). Vide : jusqu'à nouvel ordre."
    )
    pause: PauseDemandee | None = Field(default=None, description="Absente : pas touchée. null : levée. Objet : en pause.")


class AnnonceRendue(BaseModel):
    format: Literal["heure_fixe", "tranche", "duree"]
    minutes: int = Field(description="La durée annoncée à partir de maintenant, entière, arrondie vers le haut.")
    prete: datetime
    debut: datetime | None = None
    fin: datetime | None = None
    phrase: str = Field(description="L'annonce en français : « dans 30 minutes », « à 20 h 15 », « entre 20 h 15 et 20 h 30 ».")


class ZoneRendue(BaseModel):
    zone_id: int
    nom: str
    delai_zone: int = Field(description="Le délai de la zone, EN ENTIER, en minutes.")
    annonce: AnnonceRendue


class TypeRendu(BaseModel):
    type: TypeDeCommande
    ouvert: bool
    raison: str | None = Field(default=None, description="Pourquoi fermé (liste fermée du classeur), vide quand ouvert.")
    reprise: datetime | None = None
    pause_jusqu_a: datetime | None = None
    minutes_ajoutees: int
    ajout_jusqu_a: datetime | None = None
    ajout_actif: int = Field(description="Les minutes ajoutées qui comptent à cet instant (0 quand l'ajout s'est éteint).")
    format: Literal["heure_fixe", "tranche", "duree"]
    delai_minutes: int | None = Field(default=None, description="Le délai du type (jamais pour la livraison, portée par chaque zone, ni la réservation).")
    annonce: AnnonceRendue | None = None
    par_zone: list[ZoneRendue] = Field(default_factory=list, description="Livraison seulement : ce que l'agent annoncerait maintenant, par zone.")


class EtatDeLaCaisse(BaseModel):
    mode: Literal["normal", "deborde", "pause"]
    minutes_en_plus: int
    reprise: datetime | None = None
    temps_preparation: int | None = None


class TempsRendu(BaseModel):
    """L'état combiné par type et ce que l'agent annonce. ``lecture_seule`` : la caisse porte l'état, la puce l'affiche sans le modifier (E-49)."""

    types: list[TypeRendu]
    source_de_l_etat: Literal["caisse", "portail"]
    lecture_seule: bool
    etat_caisse: EtatDeLaCaisse | None = None
    moment: datetime
