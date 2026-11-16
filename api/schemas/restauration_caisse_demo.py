"""[.mark] Module Restauration, lot 20 : les corps des routes de l'écran Outils › Simulateurs › Caisse / POS (Labo seulement).

Les listes sont fermées (état, geste, réponse de la caisse) ; aucun secret n'est rendu (ni jeton, ni empreinte). Les textes sont bornés.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreerRestaurantDemande(_Strict):
    nom: str = Field(min_length=1, max_length=120)
    scenario: str | None = Field(default=None, max_length=60, description="Un scénario à mettre en place tout de suite (clé d'un scénario livré ou enregistré).")
    modele_de: int | None = Field(default=None, description="Dupliquer un autre restaurant de test du Labo (carte, réglages, comportement).")


class ReglerRestaurantDemande(_Strict):
    nom: str | None = Field(default=None, max_length=120)
    etat: Literal["ouvert", "ferme", "deborde"] | None = None
    minutes_en_plus: int | None = Field(default=None, ge=0, le=240)
    reglages: dict[str, Any] | None = None
    comportement: dict[str, Any] | None = None
    clients: list[dict[str, Any]] | None = Field(default=None, max_length=200)


class GesteDemande(_Strict):
    """Un geste « par la caisse », en plein appel : rupture ou reprise d'un code, prix changé, état changé, statut ou heure d'une commande. La caisse le dit par un message signé."""

    geste: Literal["rupture", "prix", "etat", "commande"]
    code: str | None = Field(default=None, max_length=120)
    disponible: bool | None = None
    prix: int | None = Field(default=None, ge=0, le=1_000_000, description="En centimes.")
    etat: Literal["ouvert", "ferme", "deborde"] | None = None
    minutes_en_plus: int | None = Field(default=None, ge=0, le=240)
    ref: str | None = Field(default=None, max_length=20)
    statut: str | None = Field(default=None, max_length=30)
    heure_confirmee: str | None = Field(default=None, max_length=40)


class BrancherDemo(_Strict):
    etablissement_id: int = Field(ge=1)


class ImporterLaCarteDemande(_Strict):
    carte: dict[str, Any]


class LirePhotoDemande(_Strict):
    image: str = Field(min_length=20, max_length=14_000_000, description="La photo de la carte, en base64 (sans préfixe).")
    type_image: Literal["image/jpeg", "image/png", "image/webp"]


class EnregistrerScenarioDemande(_Strict):
    nom: str = Field(min_length=1, max_length=80)


class MettreEnPlaceDemande(_Strict):
    scenario: str = Field(min_length=1, max_length=60)
