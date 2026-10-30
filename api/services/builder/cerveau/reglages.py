"""[.mark] Builder : les réglages du cerveau (fournisseur, modèle, clé, plafonds).

Une ligne ``MARK_BUILDER_CERVEAU`` dans l'organisation des réglages : l'organisation .mark quand la
bibliothèque est réglée (le coût de fabrication est celui de .mark, jamais la clé d'un client), sinon celle de
la personne. La clé n'est JAMAIS dans cette ligne : elle est rangée dans le coffre d'identifiants (chiffré,
comme les autres clés) et la ligne n'en garde que l'identifiant (``cle_ref``).

⛔ La clé n'est ni renvoyée par l'API, ni journalisée, ni mise dans un message d'erreur.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.db import db_client
from api.services.builder import stock
from api.services.builder.constantes import CLE_CERVEAU, organisation_bibliotheque

FormatDuFil = Literal["openai", "anthropic"]

ADRESSE_PAR_DEFAUT: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
}


class ReglagesPublics(BaseModel):
    """Tout ce qui se règle SAUF la clé (ni la clé ni son identifiant : ce que l'écran lit)."""

    format: FormatDuFil = "anthropic"
    modele: str = Field(default="", max_length=200)
    # Vide : l'adresse du fournisseur du format. Pour un fournisseur compatible OpenAI (Mistral, Gemini…).
    adresse: str = Field(default="", max_length=500)
    # Plafonds par conversation : dépense en dollars (si les prix sont connus) ET jetons (toujours).
    plafond_depense: float = Field(default=2.0, ge=0)
    plafond_jetons: int = Field(default=1_500_000, ge=1000)
    prix_entree_par_million: float = Field(default=0.0, ge=0)
    prix_sortie_par_million: float = Field(default=0.0, ge=0)
    # Fenêtre de contexte du modèle (jetons) : le compactage se déclenche à 70 % (B45).
    fenetre: int = Field(default=200_000, ge=4000)
    sortie_max: int = Field(default=8192, ge=256)
    tours_outils_max: int = Field(default=12, ge=1, le=40)
    tours_correction_max: int = Field(default=3, ge=1, le=10)


class ReglagesCerveau(ReglagesPublics):
    # L'identifiant du coffre (jamais la clé).
    cle_ref: str | None = Field(default=None, max_length=100)


class VueReglagesCerveau(ReglagesPublics):
    """Ce que l'écran lit : les mêmes réglages, et SEULEMENT si une clé est posée."""

    cle_posee: bool = False


async def organisation_des_reglages(user) -> int:
    return organisation_bibliotheque() or user.selected_organization_id


async def lire(organisation: int) -> ReglagesCerveau:
    brut = await stock.lire(organisation, CLE_CERVEAU)
    return ReglagesCerveau.model_validate(brut) if brut else ReglagesCerveau()


async def ecrire(organisation: int, reglages: ReglagesCerveau) -> None:
    await stock.ecrire(organisation, CLE_CERVEAU, reglages.model_dump(mode="json"))


async def vue(organisation: int) -> VueReglagesCerveau:
    reglages = await lire(organisation)
    return VueReglagesCerveau(**reglages.model_dump(exclude={"cle_ref"}), cle_posee=bool(reglages.cle_ref))


async def lire_la_cle(organisation: int, reglages: ReglagesCerveau) -> str | None:
    """La valeur de la clé, lue dans le coffre au moment de l'appel. ``None`` si elle manque."""
    if not reglages.cle_ref:
        return None
    identifiant = await db_client.get_credential_by_uuid(reglages.cle_ref, organisation)
    valeur = (identifiant.credential_data or {}).get("token") if identifiant is not None else None
    return valeur if isinstance(valeur, str) and valeur.strip() else None
