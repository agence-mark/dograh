"""[.mark] Module Restauration, lot 13 : les corps et les réponses des routes des écrans du fork Salle, Remises et Envois (F6, F7, M7).

Des routes du FORK seulement (le portail écrit directement dans sa base, contrat portail ↔ fork § 1). Corps fermés (``extra="forbid"``), tailles bornées,
listes fermées. Aucun texte de caisse.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Forme = Literal["ronde", "carree", "rectangle"]
_Ferme = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- salle


class ElementDeSalle(BaseModel):
    model_config = _Ferme
    id: str = Field(min_length=1, max_length=40)
    type: Literal["bar", "porte"]
    x: float = Field(ge=0, le=40)
    y: float = Field(ge=0, le=40)
    l: int = Field(ge=1, le=20)  # noqa: E741
    h: int = Field(ge=1, le=12)


class TableDeSalle(BaseModel):
    model_config = _Ferme
    id: str = Field(min_length=1, max_length=40, description="Un identifiant réel, ou ``nouveau-…`` pour une table que l'écran vient de poser.")
    nom: str = Field(min_length=1, max_length=40)
    forme: Forme = "carree"
    x: float = Field(ge=0, le=40)
    y: float = Field(ge=0, le=40)
    l: int = Field(default=2, ge=1, le=10)  # noqa: E741
    h: int = Field(default=2, ge=1, le=10)
    couverts_min: int = Field(ge=1, le=50)
    couverts_max: int = Field(ge=1, le=50)
    assemblable_avec: list[str] = Field(default_factory=list, max_length=20)
    actif: bool = True

    @model_validator(mode="after")
    def _ordre(self):
        if self.couverts_max < self.couverts_min:
            raise ValueError("couverts_max must be at least couverts_min")
        return self


class SalleDeSalle(BaseModel):
    model_config = _Ferme
    id: str = Field(min_length=1, max_length=40)
    nom: str = Field(min_length=1, max_length=60)
    elements: list[ElementDeSalle] = Field(default_factory=list, max_length=30)
    tables: list[TableDeSalle] = Field(default_factory=list, max_length=80)


class PlanDemande(BaseModel):
    model_config = _Ferme
    salles: list[SalleDeSalle] = Field(min_length=1, max_length=12)


class ServiceDemande(BaseModel):
    model_config = _Ferme
    nom: str = Field(min_length=1, max_length=60)
    jours: list[int] = Field(min_length=1, max_length=7)
    debut: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    fin: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    pas_minutes: int = Field(default=15, ge=5, le=120)

    @model_validator(mode="after")
    def _jours(self):
        if any(j < 1 or j > 7 for j in self.jours) or self.fin <= self.debut:
            raise ValueError("invalid days or hours")
        return self


class DureeDemande(BaseModel):
    model_config = _Ferme
    couverts_min: int = Field(ge=1, le=100)
    couverts_max: int = Field(ge=1, le=100)
    duree_minutes: int = Field(ge=15, le=600)

    @model_validator(mode="after")
    def _ordre(self):
        if self.couverts_max < self.couverts_min:
            raise ValueError("couverts_max must be at least couverts_min")
        return self


class ReglesDemandees(BaseModel):
    model_config = _Ferme
    delai_minimal: int | None = Field(default=None, ge=0, le=10080)
    jours_a_l_avance: int | None = Field(default=None, ge=0, le=730)
    couverts_max_groupe: int | None = Field(default=None, ge=1, le=200)
    couverts_max_creneau: int | None = Field(default=None, ge=1, le=1000)


class CreneauxDemandes(BaseModel):
    """Seuls les blocs donnés changent : ``services`` et ``durees`` remplacent la liste entière, ``regles`` ne change que les champs donnés."""

    model_config = _Ferme
    services: list[ServiceDemande] | None = Field(default=None, max_length=40)
    durees: list[DureeDemande] | None = Field(default=None, max_length=20)
    regles: ReglesDemandees | None = None


class StatutDemande(BaseModel):
    model_config = _Ferme
    statut: Literal["confirmee", "honoree", "absente"]


class SalleRendue(BaseModel):
    fuseau: str
    aujourd_hui: str
    maintenant_min: int
    salles: list[dict[str, Any]]
    services: list[dict[str, Any]]
    durees: list[dict[str, Any]]
    regles: dict[str, Any]
    reservations: list[dict[str, Any]]


class OkSalle(BaseModel):
    ok: bool


class CommandeRecente(BaseModel):
    numero: str
    numero_court: str
    mode: str
    statut: str
    total: int
    ref_caisse: str | None
    le: str
    # Le règlement noté sur la commande, tel que le ticket le dit (``None`` tant que rien n'est noté).
    paiement: str | None = None


class CommandesRecentes(BaseModel):
    commandes: list[CommandeRecente]


class LigneDeCommande(BaseModel):
    rang: int
    code_caisse: str
    nom: str
    quantite: int
    prix_unitaire: int
    note: str | None = None
    choix: list[Any] = []
    retires: list[str] = []
    formule_ref: str | None = None


class CommandeDeLAppel(BaseModel):
    """Une commande telle que ``resto_commande`` la garde : de quoi juger ce qui a été enregistré (heure, adresse, consigne, règlement, note, total, statut)."""

    numero: str
    numero_court: str
    statut: str
    mode: str
    heure_voulue: str | None
    heure_annoncee: str | None
    adresse: dict[str, Any] | None
    consigne_livreur: str | None
    paiement: dict[str, Any]
    note: str | None
    sous_total: int
    frais: int
    total: int
    telephone: str | None
    prenom: str | None
    lignes: list[LigneDeCommande]


class CommandesDeLAppel(BaseModel):
    appel_id: str
    commandes: list[CommandeDeLAppel]


# --------------------------------------------------------------------------- remises

Mecanisme = Literal[
    "pourcentage", "montant", "x_achetes_y_offert", "deuxieme_moitie_prix", "prix_du_jour", "seuil_panier",
    "passage_en_menu", "taille_superieure", "offre_famille", "creneau", "nouveaute", "fidelite",
]
EtatRemise = Literal["brouillon", "active", "suspendue", "terminee"]
TRANSITIONS_REMISE: dict[str, tuple[str, ...]] = {
    "brouillon": ("active",), "active": ("suspendue", "terminee"), "suspendue": ("active", "terminee"), "terminee": (),
}


class RemiseDemandee(BaseModel):
    """La règle telle que l'écran la compose (les colonnes de la table des remises). Le calcul exact est celui du comptoir ; une forme qu'il ne sait pas lire n'est
    jamais appliquée (R1) : ``declencheur``, ``effet`` et ``perimetre`` sont des objets bornés."""

    model_config = _Ferme
    nom: str = Field(min_length=1, max_length=80)
    mecanisme: Mecanisme
    declencheur: dict[str, Any] = Field(default_factory=dict)
    effet: dict[str, Any] = Field(default_factory=dict)
    perimetre: dict[str, Any] = Field(default_factory=dict)
    cumul: Literal["exclusive", "cumulable"] = "exclusive"
    limite: dict[str, Any] | None = None
    phrase: str | None = Field(default=None, max_length=300)
    moment: dict[str, Any] | None = None
    debut: datetime | None = None
    fin: datetime | None = None
    etat: Literal["brouillon", "active"] = "brouillon"

    @model_validator(mode="after")
    def _bornes(self):
        import json

        for champ in ("declencheur", "effet", "perimetre", "limite", "moment"):
            valeur = getattr(self, champ)
            if valeur is not None and len(json.dumps(valeur)) > 8000:
                raise ValueError(f"{champ} is too large")
        if self.debut and self.fin and self.fin <= self.debut:
            raise ValueError("fin must be after debut")
        return self


class EtatRemiseDemande(BaseModel):
    model_config = _Ferme
    etat: EtatRemise


class RemiseRendue(BaseModel):
    id: int
    nom: str
    mecanisme: str
    declencheur: dict[str, Any]
    effet: dict[str, Any]
    perimetre: dict[str, Any]
    cumul: str
    limite: dict[str, Any] | None
    phrase: str | None
    moment: dict[str, Any] | None
    debut: datetime | None
    fin: datetime | None
    etat: str
    ref_caisse: str | None
    source: str
    maj_le: datetime
    utilisations: int = 0
    ca_centimes: int = 0
    remise_centimes: int = 0
    # M38 : les offres de cette remise dites par l'agent, et celles qui se sont retrouvées sur une commande.
    dite: int = 0
    acceptee: int = 0


class RemisesRendues(BaseModel):
    remises: list[RemiseRendue]
    lecture_seule: bool = Field(description="La caisse porte les remises : elles se lisent ici, elles se tiennent dans la caisse.")
    prise: str


# --------------------------------------------------------------------------- envois

DECLENCHEURS = ("commande_enregistree", "reservation_enregistree", "reservation_modifiee", "reservation_annulee", "carte", "avis", "heure_changee")


class EnvoiRendu(BaseModel):
    declencheur: str
    type: Literal["sms"]
    texte: str
    actif: bool
    texte_par_defaut: str
    trous: list[str]


class EnvoisRendus(BaseModel):
    envois: list[EnvoiRendu]


class EnvoiDemande(BaseModel):
    model_config = _Ferme
    declencheur: Literal["commande_enregistree", "reservation_enregistree", "reservation_modifiee", "reservation_annulee", "carte", "avis", "heure_changee"]
    texte: str | None = Field(default=None, min_length=1, max_length=160)
    actif: bool | None = None


class EnvoisChanges(BaseModel):
    model_config = _Ferme
    envois: list[EnvoiDemande] = Field(min_length=1, max_length=7)
