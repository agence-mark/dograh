"""[.mark] Les types communs des actions, du moteur à la caisse (chantier Partie 1, lot 1 ; audit des rustines S4, S10).

Quatre types, tous figés (``frozen``) et sérialisables en JSON (``vers_json`` / ``depuis_json``) pour la colonne ``jsonb`` de la commande :

- ``Adresse`` : fabriquée seulement par le code (résultat de la vérification de l'adresse), jamais par le modèle ; ``texte_dit`` garde les mots dits ;
- ``MomentVoulu`` : l'instant voulu, toujours avec son fuseau (un instant sans fuseau lève ``ValueError``) ;
- ``ConsigneLivreur`` et ``Habitude`` : deux types distincts (S4) : la consigne vaut pour CETTE commande, l'habitude vit sur la fiche du client ;
- ``Note`` : une note sait d'où elle vient (``source``) et à quoi elle s'attache (``portee``), pour ne jamais écraser une allergie (E22).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any, ClassVar

SOURCES_DE_NOTE = frozenset({"greffier", "modele", "fiche_client"})
PORTEES_DE_NOTE = frozenset({"ligne", "commande"})


def _champs(cls: type, donnees: dict[str, Any]) -> dict[str, Any]:
    """Les champs connus du type, lus d'un dictionnaire ; une clé inconnue est ignorée, un champ absent prend son défaut."""
    if not isinstance(donnees, dict):
        raise TypeError(f"{cls.__name__} : un objet JSON est attendu, reçu {type(donnees).__name__}")
    noms = {f.name for f in fields(cls)}
    return {k: v for k, v in donnees.items() if k in noms}


@dataclass(frozen=True)
class Adresse:
    """Une adresse vérifiée par le code : la voie (« 12 rue de la République »), le code postal, la commune, son code INSEE, et les mots dits."""

    voie: str
    code_postal: str | None
    commune: str
    insee: str | None
    texte_dit: str

    def __post_init__(self) -> None:
        if not isinstance(self.commune, str) or not self.commune.strip():
            raise ValueError("Adresse : la commune est obligatoire (une adresse vient toujours de la vérification du code)")

    def vers_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def depuis_json(cls, donnees: dict[str, Any]) -> Adresse:
        return cls(**_champs(cls, donnees))


@dataclass(frozen=True)
class MomentVoulu:
    """L'instant voulu par la personne : ``debut`` en ISO 8601 AVEC fuseau, les mots dits, et « dès que possible »."""

    debut: str | None
    texte_dit: str
    des_que_possible: bool = False

    def __post_init__(self) -> None:
        if self.debut is None:
            if not self.des_que_possible:
                raise ValueError("MomentVoulu : un instant, ou « dès que possible »")
            return
        instant = datetime.fromisoformat(self.debut)  # une chaîne qui n'est pas une date lève ValueError
        if instant.tzinfo is None:
            raise ValueError(f"MomentVoulu : instant sans fuseau refusé ({self.debut!r})")

    @classmethod
    def depuis_un_instant(cls, instant: datetime, texte_dit: str) -> MomentVoulu:
        if instant.tzinfo is None:
            raise ValueError("MomentVoulu : instant sans fuseau refusé")
        return cls(instant.isoformat(), texte_dit)

    def instant(self) -> datetime | None:
        return datetime.fromisoformat(self.debut) if self.debut else None

    def vers_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def depuis_json(cls, donnees: dict[str, Any]) -> MomentVoulu:
        return cls(**_champs(cls, donnees))


@dataclass(frozen=True)
class _TexteSource:
    texte: str
    source: str
    USAGE: ClassVar[str] = ""

    def __post_init__(self) -> None:
        if not isinstance(self.texte, str) or not self.texte.strip():
            raise ValueError(f"{type(self).__name__} : texte vide")

    def vers_json(self) -> dict[str, Any]:
        return {"type": type(self).__name__, **asdict(self)}

    @classmethod
    def depuis_json(cls, donnees: dict[str, Any]):
        if donnees.get("type") not in (None, cls.__name__):
            raise ValueError(f"{cls.__name__} : objet d'un autre type ({donnees.get('type')!r})")
        return cls(**_champs(cls, donnees))


@dataclass(frozen=True)
class ConsigneLivreur(_TexteSource):
    """La consigne de CETTE commande, pour le livreur (« code 1234, deuxième étage ») : elle part avec la commande, jamais sur la fiche du client."""

    USAGE: ClassVar[str] = "commande"


@dataclass(frozen=True)
class Habitude(_TexteSource):
    """Ce que la personne veut qu'on retienne d'un appel à l'autre : elle vit sur la fiche du client, jamais dans une seule commande."""

    USAGE: ClassVar[str] = "fiche_client"


@dataclass(frozen=True)
class Note:
    """Une note (« sans gluten », « bien cuite ») qui sait d'où elle vient et à quoi elle s'attache. La composition sans écrasement est au lot 6."""

    texte: str
    source: str
    portee: str

    def __post_init__(self) -> None:
        if not isinstance(self.texte, str) or not self.texte.strip():
            raise ValueError("Note : texte vide")
        if self.source not in SOURCES_DE_NOTE:
            raise ValueError(f"Note : source {self.source!r} hors de {sorted(SOURCES_DE_NOTE)}")
        if self.portee not in PORTEES_DE_NOTE:
            raise ValueError(f"Note : portée {self.portee!r} hors de {sorted(PORTEES_DE_NOTE)}")

    def vers_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def depuis_json(cls, donnees: dict[str, Any]) -> Note:
        return cls(**_champs(cls, donnees))
