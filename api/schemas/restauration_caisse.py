"""[.mark] Module Restauration, lots 9 et 10 : les corps et les réponses des routes de la caisse (contrat portail ↔ fork § 2, figé dans ``contrat_portail_fork.json``).

Aucun texte de caisse : des valeurs fermées, des codes et des nombres. Aucune adresse sortante n'est rendue (la liste fermée reste côté serveur).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BrancherDemande(BaseModel):
    """Début du branchement d'une caisse : seule la prise HubRise se branche par le portail (l'imprimante se pose depuis le fork)."""

    model_config = ConfigDict(extra="forbid")

    prise: Literal["hubrise"]


class BrancherRendu(BaseModel):
    adresse_autorisation: str = Field(description="L'adresse de la page d'autorisation de la caisse : le portail y envoie la personne, qui revient ensuite sur la page du portail.")


class RuptureDemandee(BaseModel):
    """Une rupture (ou sa reprise) sur un code de caisse. Toujours possible, même quand la caisse est maître (E-44)."""

    model_config = ConfigDict(extra="forbid")

    code_caisse: str = Field(min_length=1, max_length=120)
    disponible: bool
    fin: datetime | None = Field(default=None, description="La reprise attendue (avec fuseau, dans le futur). Vide : jusqu'à nouvel ordre.")


class RuptureRendue(BaseModel):
    ok: bool
    poussee_a_la_caisse: bool = Field(description="Vrai si la caisse a accepté la rupture. Faux : posée chez nous (l'agent la respecte), la caisse n'a pas répondu ou ne sait pas la poser.")


class CapacitesRendues(BaseModel):
    """La fiche de capacités de la prise (``fiches-capacites.md``) : ce que le portail peut lire et faire. Jamais le nom d'un fournisseur à tester."""

    carte: str
    carte_notifiee: bool
    ruptures: str
    ruptures_posees_par_nous: bool
    etat_restaurant: str
    temps_preparation: bool
    horaires: bool
    commande_non_payee: bool
    controle_avant_creation: bool
    annulation: bool
    etapes: list[str]
    anti_doublon: str
    notifications: str
    clients_lus: bool
    remises_lues: bool
    represente: list[str]
    limites: list[str]


class EtatDeLaCaisse(BaseModel):
    mode: Literal["normal", "deborde", "pause"]
    minutes_en_plus: int
    reprise: datetime | None = None
    temps_preparation: int | None = None


class CaisseRendue(BaseModel):
    prise: str = Field(description="``portail`` quand aucune caisse n'est reliée : le classeur est maître.")
    etat: Literal["aucune", "ok", "erreur", "rompue"]
    derniere_erreur: str | None = Field(default=None, description="Un code (``jeton_refuse``, ``caisse_injoignable``…), jamais le texte de la caisse.")
    derniere_synchro: datetime | None = None
    point_de_vente: str | None = None
    mode_passif: bool = False
    derniere_releve: datetime | None = None
    avertissements: list[str] = Field(default_factory=list, description="Codes : ``horaires_differents`` (jamais écrasés).")
    etat_caisse: EtatDeLaCaisse | None = Field(default=None, description="L'état que la caisse porte (E-49) ; vide : le portail et la fiche font foi.")
    capacites: CapacitesRendues
    prises: dict[str, CapacitesRendues] = Field(
        default_factory=dict, description="Lot 13 (F8) : la fiche de chaque prise qui se branche (liste fermée côté serveur), pour montrer ce qu'elle saurait faire avant de la brancher."
    )


class ImprimanteDemandee(BaseModel):
    """Poser (ou remplacer) l'imprimante de l'établissement. ``differe`` : un ticket planifié est libéré ``minutes_avant`` minutes avant l'heure ; ``immediat`` : imprimé
    tout de suite, marqué « PROGRAMMÉE » (T-11)."""

    model_config = ConfigDict(extra="forbid")

    nom: str | None = Field(default=None, max_length=80)
    mode_planifiee: Literal["differe", "immediat"] = "differe"
    minutes_avant: int = Field(default=20, ge=0, le=240)


class ImprimanteRendue(BaseModel):
    adresse: str = Field(description="L'adresse à saisir dans l'imprimante (réglage du serveur CloudPRNT). Elle contient le secret : elle ne se montre qu'une fois.")


class OkCaisse(BaseModel):
    ok: bool


class ResynchroRendue(BaseModel):
    """Lot 13 (M6) : ce que la relecture de la caisse a fait. ``erreur`` est un code fermé de la liaison, jamais le texte de la caisse."""

    ok: bool
    erreur: str | None = None
    carte: bool = Field(description="La carte a été relue.")
    ruptures: bool = Field(description="Les ruptures ont été relues.")
    etat: bool = Field(description="L'état du restaurant (mode, minutes en plus) a été relu.")
