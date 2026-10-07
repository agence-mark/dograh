"""[.mark] A translator: one software in the common format of the hub (L4, H2, H3, H9).

A translator is declared once, in the software's own file (``connectors/actions/<software>.py``),
and the hub never changes when one is added:

1. **The connection**: ``integration``, the Nango ``provider_config_key`` of the software. The
   relay presents the client's key in our place; the organization is ALWAYS the server's
   (D6 of the connectors), never something a call or a model says.
2. **The correspondence**: a declarative table, hub field <-> software field (a dotted path in
   the software's JSON), with an optional conversion each way. ``vers_logiciel`` and
   ``depuis_logiciel`` apply it; an operation never spells a field by hand.
3. **The operations**: ``lire``, ``chercher``, ``creer``, ``modifier``, each tied to the API:
   ``preparer`` builds the requests (paths of the software's API, never a host), ``lire``
   turns the answer into the hub's value.

The hub's objects and their fields are fixed here (``OBJETS``): a translator that maps a field
the hub does not know is refused at load. That is what keeps the format common.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from api.services.integrations.connectors import nango
from api.services.integrations.connectors.nango import Requete

OPERATIONS = ("lire", "chercher", "creer", "modifier")

# The objects of the common format a translator may serve, and their fields. A field here is a
# column (or a computed value) of the client's database: ``rendez_vous`` is the table of the same
# name; ``disponibilites`` is what a search of agendas returns (who is busy when).
OBJETS: dict[str, tuple[str, ...]] = {
    "rendez_vous": (
        "id_externe",  # the software's identifier (``lien_externe.id_externe``)
        "agenda",  # the agenda it lives in (the person's, ``lien_externe`` of the person)
        "debut",  # ISO 8601 with offset
        "fin",
        "fuseau",  # IANA time zone
        "titre",
        "description",
        "lieu",
    ),
    "disponibilites": ("agendas", "debut", "fin"),
}

_SYSTEME = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


@dataclass(frozen=True)
class Champ:
    """One line of the correspondence: a hub field and its place in the software.

    ``vers``: hub value -> software value; ``depuis``: the way back. None: as is."""

    hub: str
    chemin: str
    vers: Callable[[Any], Any] | None = None
    depuis: Callable[[Any], Any] | None = None


@dataclass(frozen=True)
class Operation:
    """``preparer(arguments, objet)`` -> a request or a list of them (played in order, the last
    answer kept); ``lire(reponse, arguments, objet)`` -> the hub's value."""

    preparer: Callable[[dict, ObjetTraduit], Requete | list[Requete]]
    lire: Callable[[Any, dict, ObjetTraduit], Any]


@dataclass(frozen=True)
class ObjetTraduit:
    objet: str
    correspondance: tuple[Champ, ...]
    operations: dict[str, Operation]

    def vers_logiciel(self, valeurs: dict) -> dict:
        return vers_logiciel(self.correspondance, valeurs)

    def depuis_logiciel(self, donnees: Any) -> dict:
        return depuis_logiciel(self.correspondance, donnees)


@dataclass(frozen=True)
class Traducteur:
    systeme: str  # stable name, also ``lien_externe.systeme``
    libelle: str
    integration: str  # Nango provider_config_key
    domaine: str  # "agenda" today
    objets: tuple[ObjetTraduit, ...]
    # What identifies a person's agenda in this software, shown next to the field on screen,
    # in English and in French (convention of the screen, T2).
    reference_agenda: dict[str, str] = field(default_factory=dict)
    base_url: str | None = (
        None  # test translators only (an unauthenticated integration)
    )

    def objet(self, nom: str) -> ObjetTraduit | None:
        return next((o for o in self.objets if o.objet == nom), None)


class TraducteurInvalide(ValueError):
    pass


class TraducteurInconnu(LookupError):
    """No translator by that name, or it does not do that operation. Safe to show."""


# --------------------------------------------------------------------------- #
# The correspondence
# --------------------------------------------------------------------------- #


def _poser(cible: dict, chemin: str, valeur: Any) -> None:
    morceaux = chemin.split(".")
    for morceau in morceaux[:-1]:
        cible = cible.setdefault(morceau, {})
    cible[morceaux[-1]] = valeur


def _prendre(source: Any, chemin: str) -> Any:
    for morceau in chemin.split("."):
        if not isinstance(source, dict):
            return None
        source = source.get(morceau)
    return source


def vers_logiciel(correspondance: tuple[Champ, ...], valeurs: dict) -> dict:
    """The software's body for these hub values. A hub value absent or empty is not sent."""
    corps: dict = {}
    for champ in correspondance:
        valeur = valeurs.get(champ.hub)
        if valeur in (None, ""):
            continue
        _poser(corps, champ.chemin, champ.vers(valeur) if champ.vers else valeur)
    return corps


def depuis_logiciel(correspondance: tuple[Champ, ...], donnees: Any) -> dict:
    """The hub values read in the software's answer. The first line of a hub field wins."""
    valeurs: dict = {}
    for champ in correspondance:
        if champ.hub in valeurs:
            continue
        brut = _prendre(donnees, champ.chemin)
        if brut in (None, ""):
            continue
        valeurs[champ.hub] = champ.depuis(brut) if champ.depuis else brut
    return valeurs


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #

_TRADUCTEURS: dict[str, Traducteur] = {}


def declarer_traducteur(traducteur: Traducteur) -> Traducteur:
    if not _SYSTEME.match(traducteur.systeme):
        raise TraducteurInvalide(
            f"« {traducteur.systeme} »: a translator's name takes lower case letters, digits and underscores."
        )
    for objet in traducteur.objets:
        champs = OBJETS.get(objet.objet)
        if champs is None:
            raise TraducteurInvalide(
                f"{traducteur.systeme}: « {objet.objet} » is not an object of the hub."
            )
        for champ in objet.correspondance:
            if champ.hub not in champs:
                raise TraducteurInvalide(
                    f"{traducteur.systeme}.{objet.objet}: « {champ.hub} » is not a field of the hub."
                )
        for nom in objet.operations:
            if nom not in OPERATIONS:
                raise TraducteurInvalide(
                    f"{traducteur.systeme}.{objet.objet}: « {nom} » is not an operation ({', '.join(OPERATIONS)})."
                )
    existant = _TRADUCTEURS.get(traducteur.systeme)
    if existant is not None and existant is not traducteur:
        raise TraducteurInvalide(f"Translator « {traducteur.systeme} » declared twice.")
    _TRADUCTEURS[traducteur.systeme] = traducteur
    return traducteur


def retirer_traducteur(systeme: str) -> None:
    """Tests only: drop a test translator."""
    _TRADUCTEURS.pop(systeme, None)


def _charger() -> None:
    from api.services.integrations.connectors import (
        actions,
    )


def traducteurs(domaine: str | None = None) -> list[Traducteur]:
    _charger()
    return [
        _TRADUCTEURS[s]
        for s in sorted(_TRADUCTEURS)
        if domaine is None or _TRADUCTEURS[s].domaine == domaine
    ]


def traducteur(systeme: str | None) -> Traducteur | None:
    _charger()
    return _TRADUCTEURS.get(systeme or "")


# --------------------------------------------------------------------------- #
# One operation, through THIS organization's connection
# --------------------------------------------------------------------------- #


async def operer(
    organization_id: int,
    systeme: str,
    objet: str,
    operation: str,
    arguments: dict,
    *,
    delai: float,
) -> Any:
    """Play one operation of a translator. The organization is the server's (D6): the relay
    uses only a connection Nango lists under its tag. Raises ``TraducteurInconnu``,
    ``nango.ConnexionAbsente``, ``nango.NangoIndisponible`` (never the key)."""
    t = traducteur(systeme)
    if t is None:
        raise TraducteurInconnu(f"No translator « {systeme} ».")
    o = t.objet(objet)
    op = o.operations.get(operation) if o else None
    if o is None or op is None:
        raise TraducteurInconnu(f"« {t.libelle} » cannot {operation} « {objet} ».")
    requetes = op.preparer(arguments, o)
    reponse: Any = None
    for requete in requetes if isinstance(requetes, list) else [requetes]:
        reponse = await nango.relayer(
            organization_id, t.integration, requete, delai=delai, base_url=t.base_url
        )
    return op.lire(reponse, arguments, o)
