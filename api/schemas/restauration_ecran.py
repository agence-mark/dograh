"""[.mark] Module Restauration, lot 12 : les corps et les réponses des routes des écrans du fork (Entreprise › Carte, Livraison, Réglages restaurant).

Des routes du FORK seulement (le portail écrit directement dans la base du restaurant, contrat portail ↔ fork § 1) : elles ne figurent pas dans
``contrat_portail_fork.json``. Aucun texte de caisse ; montants en centimes ; corps fermés (``extra="forbid"``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TypeDeCommande = Literal["emporter", "livraison", "sur_place", "reservation"]
MoyenDePaiement = Literal["carte", "especes", "titre_restaurant", "cheque", "en_ligne"]
Annonce = Literal["heure_fixe", "tranche", "duree"]


class EtablissementDuModule(BaseModel):
    id: int
    nom: str


class ModuleRendu(BaseModel):
    actif: bool = Field(description="Le module Restauration est allumé pour cette organisation.")
    etablissements: list[EtablissementDuModule] = Field(description="Les établissements de la base du client (le sélecteur des onglets du module).")


class ModuleDemande(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actif: bool


# --------------------------------------------------------------------------- la carte


class CarteRendue(BaseModel):
    """La carte au format commun, exceptions appliquées, chaque objet avec sa ``portee`` ; plus les ruptures, la source et la dernière mise à jour."""

    version: int
    categories: list[dict[str, Any]]
    produits: list[dict[str, Any]]
    groupes: list[dict[str, Any]]
    formules: list[dict[str, Any]]
    ruptures: list[dict[str, Any]]
    derniere_maj: datetime | None = None
    lecture_seule: bool = Field(description="La caisse porte la carte (la prise la lit) : elle se tient dans la caisse, pas ici.")
    prise: str


class EtoileDemandee(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1, max_length=120)
    etoile: bool


class SynonymesDemandes(BaseModel):
    """La liste des synonymes d'un produit, REMPLACÉE ; elle est active tout de suite (au plus 10, 80 caractères chacun)."""

    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1, max_length=120)
    synonymes: list[str] = Field(max_length=10)


class SynonymesRelus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref: str = Field(min_length=1, max_length=120)
    synonymes: list[str] | None = Field(default=None, max_length=10, description="Corrigés ; absents : les propositions telles quelles.")


class ImportDemande(BaseModel):
    """``caisse`` : relit la carte de la prise de l'établissement. ``fichier`` : la carte au format commun (``carte``), rangée selon la portée."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["caisse", "fichier"]
    carte: dict[str, Any] | None = Field(default=None, description="La carte au format commun (``source`` = ``fichier``).")


class ImportRendu(BaseModel):
    ajoutes: int = 0
    changes: int = 0
    retires: int = 0
    conserves: int = 0
    sans_code_caisse: int = 0
    synonymes_proposes: int = 0


class OkRendu(BaseModel):
    ok: bool


# --------------------------------------------------------------------------- la livraison


class ZoneDite(BaseModel):
    id: int | None = None
    nom: str = Field(min_length=1, max_length=80)
    forme: Literal["communes", "rayon"]
    cercle_km: float | None = Field(default=None, gt=0, le=200, description="Le cercle du schéma ; pour une zone par rayons, c'est le rayon.")
    communes: list[str] = Field(default_factory=list, max_length=400, description="Codes INSEE (zone par communes).")
    exclues: list[str] = Field(default_factory=list, max_length=400, description="Codes INSEE refusés : jamais livrés, même dans la zone.")
    frais: int = Field(default=0, ge=0, le=100_000)
    minimum: int = Field(default=0, ge=0, le=1_000_000)
    gratuite_des: int | None = Field(default=None, ge=0, le=1_000_000)
    delai: int = Field(default=0, ge=0, le=600, description="Minutes entières annoncées pour cette zone.")


class ZoneRendue(ZoneDite):
    id: int
    rayon_km: float | None = None
    ordre: int = 0


class CommuneTrouvee(BaseModel):
    insee: str
    nom: str
    code_postal: str | None = None
    km: float
    zone_id: int | None = None
    refusee: bool = False


class LivraisonRendue(BaseModel):
    centre_connu: bool = Field(description="Faux : la commune de l'établissement n'est pas connue, aucune commune ne peut être cherchée.")
    commune: str | None = None
    zones: list[ZoneRendue]
    communes: list[CommuneTrouvee]


class ZonesDemandees(BaseModel):
    """L'ensemble des zones de l'établissement (au plus 5), dans l'ordre des cercles. Une zone avec son ``id`` est mise à jour, sans ``id`` créée,
    une zone absente est retirée."""

    model_config = ConfigDict(extra="forbid")

    zones: list[ZoneDite] = Field(max_length=5)


# --------------------------------------------------------------------------- les réglages


class TypeReglage(BaseModel):
    type: TypeDeCommande
    ouvert: bool = True
    pause_jusqu_a: datetime | None = None
    fin_par_jour: dict[str, str] = Field(default_factory=dict, description="Heure de fin par jour (``1`` = lundi) : ``{\"1\": \"22:00\"}``.")
    planifiee_permise: bool = False
    delai_minimal: int = 0
    jours_a_l_avance: int = 0
    delai_annonce: int | None = None
    minutes_ajoutees: int = 0
    ajout_jusqu_a: datetime | None = None
    annonce: Annonce = "duree"


class TypeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TypeDeCommande
    ouvert: bool | None = None
    fin_par_jour: dict[str, str] | None = None
    planifiee_permise: bool | None = None
    delai_minimal: int | None = Field(default=None, ge=0, le=1440)
    jours_a_l_avance: int | None = Field(default=None, ge=0, le=365)
    delai_annonce: int | None = Field(default=None, ge=0, le=600)
    annonce: Annonce | None = None


NumeroMode = Literal["aucun", "moyen", "type"]
HEURE = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


class ReglageDuModule(BaseModel):
    prefixe_numero_court: str = ""
    numero_mode: NumeroMode = "aucun"
    prefixe_mixte: str = "MIX"
    notes_libres: bool = True
    titre_alcool_exclu: bool = True
    titre_sans_rendu: bool = True
    moyens_paiement: list[MoyenDePaiement] = Field(default_factory=list)
    plafond_titre_restaurant: int | None = None
    conservation_client_mois: int = 12


class ReglageChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prefixe_numero_court: str | None = Field(default=None, pattern=r"^[A-Z0-9]{0,4}$")
    numero_mode: NumeroMode | None = None
    prefixe_mixte: str | None = Field(default=None, pattern=r"^[A-Z0-9]{0,4}$")
    notes_libres: bool | None = None
    titre_alcool_exclu: bool | None = None
    titre_sans_rendu: bool | None = None
    moyens_paiement: list[MoyenDePaiement] | None = Field(default=None, max_length=5)
    plafond_titre_restaurant: int | None = Field(default=None, ge=0, le=1_000_000)
    conservation_client_mois: int | None = Field(default=None, ge=1, le=36)


class TempsRecurrent(BaseModel):
    """Un soir toujours chargé : des minutes ajoutées par-dessus le délai d'un type, ces jours (1 = lundi), dans cette plage (heure locale)."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    type: Literal["emporter", "livraison", "sur_place"]
    jours: list[Literal[1, 2, 3, 4, 5, 6, 7]] = Field(min_length=1, max_length=7)
    debut: str = Field(pattern=HEURE)
    fin: str = Field(pattern=HEURE)
    minutes_ajoutees: int = Field(ge=1, le=240)

    @model_validator(mode="after")
    def _plage(self):
        if self.fin <= self.debut:
            raise ValueError("fin must be after debut")
        return self


class EnvoiHeureChangee(BaseModel):
    texte: str | None = None
    actif: bool = False


class EnvoiChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texte: str | None = Field(default=None, min_length=1, max_length=480)
    actif: bool | None = None


class Seuils(BaseModel):
    alerte_sans_reponse_min: int = 3
    releve_messages_min: int = 5


class SeuilsChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alerte_sans_reponse_min: int | None = Field(default=None, ge=1, le=120)
    releve_messages_min: int | None = Field(default=None, ge=1, le=120)


class ImprimanteReglage(BaseModel):
    mode_planifiee: Literal["differe", "immediat"]
    minutes_avant: int


class ImprimanteChangee(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode_planifiee: Literal["differe", "immediat"] | None = None
    minutes_avant: int | None = Field(default=None, ge=0, le=240)


class SourceDeObjet(BaseModel):
    objet: Literal["carte", "ruptures", "horaires", "remises", "clients"]
    mode: Literal["caisse", "ici"] = Field(description="``caisse`` : la prise branchée porte cet objet (lecture seule ici) ; ``ici`` : tenu à cet endroit.")
    prise_sait: bool = Field(description="La fiche de capacités de la prise sait lire cet objet.")


class ReglagesRendus(BaseModel):
    types: list[TypeReglage]
    reglage: ReglageDuModule
    recurrents: list[TempsRecurrent] = Field(default_factory=list, description="Les soirs toujours chargés (minutes ajoutées certains jours, dans une plage).")
    envoi_heure_changee: EnvoiHeureChangee
    seuils: Seuils | None = Field(default=None, description="Vide : aucune caisse n'est reliée.")
    imprimante: ImprimanteReglage | None = None
    horaires_fiche: dict[str, list[dict[str, str]]] = Field(default_factory=dict, description="Par jour anglais : ``[{from, to}]``.")
    horaires_caisse: dict[str, Any] | None = None
    sources: list[SourceDeObjet]
    prise: str
    caisse_porte_l_etat: bool


class ReglagesChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    types: list[TypeChange] | None = Field(default=None, max_length=4)
    reglage: ReglageChange | None = None
    recurrents: list[TempsRecurrent] | None = Field(default=None, max_length=30, description="Remplace la liste des soirs chargés (absente : intacte).")
    envoi_heure_changee: EnvoiChange | None = None
    seuils: SeuilsChanges | None = None
    imprimante: ImprimanteChangee | None = None


class LigneDHistorique(BaseModel):
    id: int
    objet: str
    objet_dit: str
    ligne_id: str
    operation: Literal["insert", "update", "delete"]
    avant: str | None = None
    apres: str | None = None
    source: str
    auteur: str
    le: datetime


class HistoriqueRendu(BaseModel):
    lignes: list[LigneDHistorique]
    suite: int | None = Field(default=None, description="Identifiant à passer en ``avant`` pour la page suivante ; vide : c'est la fin.")
