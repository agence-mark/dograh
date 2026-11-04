"""[.mark] U10 / S2 : requêtes et réponses des routes du portail pour les sites et les agents de site."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.apparence_widget import ApparenceWidget


class DemandeSite(BaseModel):
    nom: str = Field(default="", max_length=120)
    allowed_domains: list[str] = Field(default_factory=list, max_length=50)


class DemandeReglageSite(BaseModel):
    nom: str | None = Field(default=None, max_length=120)
    allowed_domains: list[str] | None = Field(default=None, max_length=50)


class SiteLu(BaseModel):
    id: int
    cle: str
    nom: str
    allowed_domains: list[str]
    dernier_chargement: str | None = None
    script: str = Field(description="Le script à copier : un seul par site, quelle que soit la page.")


class DemandeCanal(BaseModel):
    canal: Literal["telephone", "site"]


class DemandeEmplacement(BaseModel):
    site_id: int
    chemins: list[str] = Field(
        default_factory=lambda: ["/"],
        min_length=1,
        max_length=50,
        description="Un ou plusieurs chemins (D188) ; « / » : tout le site.",
    )


class EmplacementLu(BaseModel):
    workflow_id: int
    canal: Literal["telephone", "site"]
    embed_token_id: int | None = None
    widget_actif: bool = False
    site_id: int | None = None
    site_cle: str | None = None
    chemins: list[str] = Field(default_factory=list)
    dernier_chargement: str | None = None
    agent_nom: str = ""
    version_publiee: int | None = None


class ApparenceLue(BaseModel):
    apparence: ApparenceWidget
    couleurs: dict[str, str] = Field(description="La couleur de chaque élément, retouches comprises.")


class DemandeReglagesMark(BaseModel):
    """Les réglages posés par .mark. Un champ absent ne change pas ; hors bornes : refusé."""

    plafond_conversations_mois: int | None = Field(default=None, ge=1, le=1_000_000)
    plafond_minutes_mois: int | None = Field(default=None, ge=1, le=1_000_000)
    duree_max_s: int | None = Field(default=None, ge=60, le=3600)
    sessions_par_heure_et_ip: int | None = Field(default=None, ge=1, le=1000)
    allowed_domains: list[str] | None = Field(default=None, max_length=50)
    modes: Literal["voix_et_ecrit", "voix"] | None = None
    jeton_expire_le: str | None = Field(
        default=None,
        max_length=10,
        description="Date AAAA-MM-JJ de fin du jeton ; chaîne vide : n'expire jamais ; absent : inchangé.",
    )


class DemandeAffichage(BaseModel):
    actif: bool


class ReglagesMarkLus(BaseModel):
    plafond_conversations_mois: int
    plafond_minutes_mois: int
    duree_max_s: int
    sessions_par_heure_et_ip: int
    allowed_domains: list[str]
    conversations_ce_mois: int = 0
    minutes_ce_mois: int = 0
    modes: Literal["voix_et_ecrit", "voix"] = "voix_et_ecrit"
    jeton_expire_le: str | None = None


class DemandeLireSite(BaseModel):
    adresse: str | None = Field(default=None, max_length=500, description="Vide : la page d'accueil du premier domaine autorisé.")


class CouleurDuSite(BaseModel):
    couleur: str | None = None
    logo_url: str | None = None
    sources: list[str] = Field(default_factory=list)
