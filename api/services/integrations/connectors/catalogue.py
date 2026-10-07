"""[.mark] The declarative catalogue of actions (plan connecteurs-agent D5, D8, D9, D17).

One file per software in ``actions/``; each declares its actions: name, the parameters the
CALLER gives (the model fills them), the client's settings (rules of the trade, filled from the
audit, D9), whether it writes, whether it may be anticipated (D17: read-only actions only), the
request to the relay and the USEFUL result (D8: never the raw answer). A new software = a
declaration; the engine does not change.

Checked at load: an action that writes can never be declared anticipable.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from api.services.integrations.connectors.nango import Requete


@dataclass(frozen=True)
class Parametre:
    nom: str
    type: str = "string"  # string, number, boolean
    description: str = ""
    obligatoire: bool = True


@dataclass(frozen=True)
class ContexteAction:
    """What an action reads besides the caller's parameters: the client's settings and the
    common model of the call (D16), never the organization (the relay takes it)."""

    reglages: dict[str, Any]
    modele: Any  # modele_commun.ModeleDeLAppel


@dataclass(frozen=True)
class Action:
    nom: str
    description: str
    parametres: tuple[Parametre, ...]
    ecrit: bool
    preparer: Callable[[dict[str, Any], ContexteAction], Requete | list[Requete]]
    resultat: Callable[[Any, dict[str, Any], ContexteAction], dict[str, Any]]
    reglages_par_defaut: dict[str, Any] = field(default_factory=dict)
    anticipable_permis: bool = False
    # A second request built from the first answer (e.g. read then compute): optional.
    suite: Callable[[Any, dict[str, Any], ContexteAction], Awaitable[Any]] | None = None


@dataclass(frozen=True)
class Connecteur:
    nom: str  # stable name in tool definitions
    libelle: str
    integration: str  # Nango provider_config_key on the installation
    actions: tuple[Action, ...]
    base_url: str | None = None  # test connectors only (unauthenticated integration)

    def action(self, nom: str) -> Action | None:
        return next((a for a in self.actions if a.nom == nom), None)


class CatalogueInvalide(ValueError):
    pass


_CATALOGUE: dict[str, Connecteur] = {}


def declarer(connecteur: Connecteur) -> Connecteur:
    for action in connecteur.actions:
        if action.ecrit and action.anticipable_permis:
            raise CatalogueInvalide(
                f"{connecteur.nom}.{action.nom} writes: an action that writes is never anticipated (D17)."
            )
        noms = [p.nom for p in action.parametres]
        if len(noms) != len(set(noms)):
            raise CatalogueInvalide(
                f"{connecteur.nom}.{action.nom}: a parameter is declared twice."
            )
        if "organization_id" in noms:
            raise CatalogueInvalide(
                f"{connecteur.nom}.{action.nom}: the organization never travels as a parameter (D6)."
            )
    existant = _CATALOGUE.get(connecteur.nom)
    if existant is not None and existant is not connecteur:
        raise CatalogueInvalide(f"Connector « {connecteur.nom} » declared twice.")
    _CATALOGUE[connecteur.nom] = connecteur
    return connecteur


def retirer(nom: str) -> None:
    """Tests only: drop a test connector."""
    _CATALOGUE.pop(nom, None)


def _charger() -> None:
    from api.services.integrations.connectors import (
        actions,  # noqa: F401 -- declarations
    )


def connecteurs() -> list[Connecteur]:
    _charger()
    return [_CATALOGUE[n] for n in sorted(_CATALOGUE)]


def connecteur(nom: str) -> Connecteur | None:
    _charger()
    return _CATALOGUE.get(nom)


def trouver(nom_connecteur: str, nom_action: str) -> tuple[Connecteur, Action] | None:
    c = connecteur(nom_connecteur)
    if c is None:
        return None
    a = c.action(nom_action)
    return (c, a) if a is not None else None
