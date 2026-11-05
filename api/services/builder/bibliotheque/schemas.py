"""[.mark] Bibliothèque : la forme du contenu d'un élément, par famille (E49).

Une famille dont un mécanisme LIT le contenu a ses champs fixés ici et validés à l'écriture : un contenu hors schéma est
refusé avec la raison. Une famille créée à l'écran ne porte que ``{"texte": ...}``. Les autres familles du code gardent un
objet libre (le code ne connaît pas leur métier).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from api.services.builder.bibliotheque.familles import FAMILLES


class _Forme(BaseModel):
    # Ce qu'un mécanisme ne lit pas peut accompagner le contenu (licence, notes) : pas de refus des champs en plus.
    model_config = ConfigDict(extra="allow")


class Personnage(_Forme):
    description: str = Field(min_length=1, max_length=1500)
    but: str = Field(default="", max_length=1000)
    fin: str = Field(default="", max_length=600)
    comportements: list[str] = Field(default_factory=list, max_length=12)
    # U6 : l'élément « consigne » porte la consigne générale de l'appelant simulé et ses formules d'au revoir (``ADIEUX``).
    consigne: str = Field(default="", max_length=6000)
    adieux: list[str] = Field(default_factory=list, max_length=30)


class ScenarioType(_Forme):
    but: str = Field(min_length=1, max_length=2000)
    personnage: str | None = Field(default=None, max_length=64)
    ouverture: str = Field(default="", max_length=500)
    tours_max: int | None = Field(default=None, ge=1, le=60)
    criteres: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    questions_juge: list[str] = Field(default_factory=list, max_length=5)
    # Sous-lot 5 : ce que le scénario fixe autour de la conversation (voir ``tests_rejouables.environnement``), copié dans le test.
    environnement: dict[str, Any] | None = None


class CritereType(_Forme):
    critere: dict[str, Any]
    explication: str = Field(default="", max_length=600)
    # U6 : l'élément « grille-juge » porte la consigne générale du juge.
    consigne: str = Field(default="", max_length=6000)

    @field_validator("critere")
    @classmethod
    def _type(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not str(v.get("type") or "").strip():
            raise ValueError("a criterion has a type")
        return v


class PhrasesDuCode(_Forme):
    regles: list[dict[str, Any]] = Field(min_length=1, max_length=40)


class Lexique(_Forme):
    termes: list[dict[str, Any]] = Field(min_length=1, max_length=400)


class ModeleDeReglages(_Forme):
    valeurs: dict[str, Any] = Field(min_length=1)


class Demarrage(_Forme):
    """Une carte de l'accueil du Labo (E50) : ce que l'écran lit, champ par champ."""

    phrase: str = Field(min_length=1, max_length=120)
    demande: str = Field(min_length=1, max_length=4000)
    besoin: Literal["rien", "agent", "fichiers", "agent et fichiers"] = "rien"
    icone: Literal["agent", "amelioration", "test", "fichier", "etincelle"] = "etincelle"
    # U2 quater (E57) : où la carte est proposée. « labo » : seulement dans le Labo (ex. « Verser à la bibliothèque »).
    proposee_dans: Literal["labo_et_clients", "labo"] = "labo_et_clients"


class PieceDeRecette(BaseModel):
    famille: str = Field(min_length=1, max_length=64)
    slug: str = Field(min_length=1, max_length=120)
    role: str = Field(default="", max_length=200)


class RecetteAgent(_Forme):
    """Une façon de construire un agent (lot M, 7) : lue par la fenêtre de création, la méthode et les gardes du builder."""

    nom: str = Field(min_length=1, max_length=80)
    quand: str = Field(default="", max_length=600)
    # V4 : la même phrase en anglais (le français reste la référence) ; vide = l'écran garde le français.
    quand_en: str = Field(default="", max_length=600)
    defaut_de_depart: bool = False
    methode_de_construction: str = Field(min_length=1, max_length=4000)
    pieces: list[PieceDeRecette] = Field(default_factory=list, max_length=80)
    tests: list[str] = Field(default_factory=list, max_length=80)
    # Ce que la recette permet (ex. « regle_de_descente »). Le code lit la capacité, jamais le nom de la recette.
    capacites: list[str] = Field(default_factory=list, max_length=12)


class Texte(_Forme):
    texte: str = Field(min_length=1)


SCHEMAS: dict[str, type[BaseModel]] = {
    "personnages-appelant": Personnage,
    "scenarios-test": ScenarioType,
    "criteres-types": CritereType,
    "phrases-du-code": PhrasesDuCode,
    "lexiques": Lexique,
    "modeles-reglages": ModeleDeReglages,
    "demarrages-builder": Demarrage,
    "recettes-agent": RecetteAgent,
}


def champs_de(famille: str) -> list[dict[str, Any]]:
    """Lot 14 (I-3) : les champs du contenu d'une famille, lus dans sa forme (jamais écrits à part : un champ de plus dans la
    forme apparaît seul à l'écran). Une famille créée à l'écran n'a que ``texte`` ; une famille du code sans forme imposée : aucun champ."""
    forme = SCHEMAS.get(famille)
    if forme is None and famille not in FAMILLES:
        forme = Texte
    if forme is None:
        return []
    schema = forme.model_json_schema()
    obligatoires = set(schema.get("required", []))
    champs: list[dict[str, Any]] = []
    for nom, p in (schema.get("properties") or {}).items():
        # Un champ optionnel est un « anyOf » avec ``null`` : on lit la branche utile.
        branches = [b for b in p.get("anyOf", [p]) if b.get("type") != "null"] or [p]
        b = branches[0]
        type_ = b.get("type")
        sorte, choix = "objet", []
        if "enum" in b:
            sorte, choix = "choix", [str(v) for v in b["enum"]]
        elif type_ == "string":
            sorte = "long" if (b.get("maxLength") or 0) > 300 or nom == "texte" else "texte"
        elif type_ == "integer":
            sorte = "nombre"
        elif type_ == "array" and (b.get("items") or {}).get("type") == "string":
            sorte = "liste"
        champs.append(
            {
                "nom": nom,
                "sorte": sorte,
                "obligatoire": nom in obligatoires,
                "choix": choix,
                "longueur_max": b.get("maxLength"),
            }
        )
    return champs


def verifier(famille: str, contenu: dict[str, Any]) -> dict[str, Any]:
    """Le contenu tel quel s'il respecte la forme de sa famille ; ``ValueError`` avec la raison sinon."""
    forme = SCHEMAS.get(famille)
    if forme is None and famille not in FAMILLES:
        forme = Texte  # famille créée à l'écran
    if forme is None:
        return contenu
    try:
        forme.model_validate(contenu)
    except ValidationError as erreur:
        premier = erreur.errors()[0]
        champ = ".".join(str(p) for p in premier.get("loc", ())) or "content"
        raise ValueError(f"{famille}: field « {champ} » {premier.get('msg', 'is invalid')}.") from None
    return contenu
