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
    # l-agent-collegue (C7): a closed list. ``choix`` is fixed; ``liste_du_contexte`` names
    # the call-context key whose list is built at pick-up (the model sees it as ``enum``).
    choix: tuple[str, ...] = ()
    liste_du_contexte: str | None = None


@dataclass(frozen=True)
class ContexteAction:
    """What an action reads besides the caller's parameters: the client's settings and the
    common model of the call (D16), never the organization (the relay takes it).

    l-agent-collegue (L5): an INTERNAL action also reads the call itself -- its organization
    (the engine's, D6), its context (read only: the establishment served, the opening state,
    the sentences), its run and its record (where it notes what it did for the after-call)."""

    reglages: dict[str, Any]
    modele: Any  # modele_commun.ModeleDeLAppel
    organization_id: int | None = None
    appel: dict[str, Any] = field(default_factory=dict)
    run_id: int | None = None
    fiche: dict | None = None


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
    # l-agent-collegue (L4, H6): what a successful run leaves for the hub, in its common
    # format (an appointment booked: ``systeme``, ``agenda``, ``id_externe``, ``debut``…).
    # Noted in the record, written in the client's database after the call. Optional.
    au_hub: Callable[[dict[str, Any], dict[str, Any], ContexteAction], dict | None] | None = None


@dataclass(frozen=True)
class Connecteur:
    nom: str  # stable name in tool definitions
    libelle: str
    integration: str  # Nango provider_config_key on the installation
    actions: tuple[Action, ...]
    base_url: str | None = None  # test connectors only (unauthenticated integration)
    # l-agent-collegue (constat 2 of L0): an INTERNAL connector runs in the fork, without
    # Nango and without the client's software (e.g. ``equipe``). Its actions are played by
    # their own handler (``gestionnaire_interne``), never through the relay.
    interne: bool = False
    gestionnaire_interne: Callable[..., Any] | None = None
    # l-agent-collegue (L5): an internal connector may instead give the COMPUTATION of its
    # actions, ``executer_interne(action, arguments, ctx, delai_s)`` -> the useful result;
    # it is then run like any action (deadline, anticipation, stamps), never by the relay.
    executer_interne: Callable[..., Awaitable[dict]] | None = None
    # An action of this connector may transfer the call (registered as a workflow-control
    # boundary, with the transfer's deadline). The team's ``diriger_vers_personne`` does.
    peut_transferer: bool = False

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
    if connecteur.interne and (
        connecteur.gestionnaire_interne is None and connecteur.executer_interne is None
    ):
        raise CatalogueInvalide(
            f"{connecteur.nom}: an internal connector needs its handler or its computation."
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
