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


TYPES_DE_PARAMETRE = ("string", "number", "boolean", "integer", "array", "object")


@dataclass(frozen=True)
class Parametre:
    nom: str
    type: str = "string"  # string, number, boolean ; [.mark] Partie 1, lot 2 : integer, array, object
    description: str = ""
    obligatoire: bool = True
    # l-agent-collegue (C7): a closed list. ``choix`` is fixed; ``liste_du_contexte`` names
    # the call-context key whose list is built at pick-up (the model sees it as ``enum``).
    choix: tuple[str, ...] = ()
    liste_du_contexte: str | None = None
    # [.mark] Partie 1, lot 2 (la fiche à cases) : une case typée et imbriquée. ``minimum`` : la plus petite valeur d'un nombre ; ``elements`` :
    # le schéma d'un élément d'une liste (``array``) ; ``proprietes`` : les sous-cases d'un objet (``object``) ; ``obligatoires`` : ses sous-cases
    # requises. Défauts inchangés : un connecteur d'avant rend le même schéma.
    minimum: int | float | None = None
    elements: "Parametre | None" = None
    proprietes: tuple["Parametre", ...] = ()
    obligatoires: tuple[str, ...] = ()
    min_elements: int | None = None  # ``minItems`` d'une liste (« les deux moitiés » : exactement deux)
    max_elements: int | None = None

    def __post_init__(self) -> None:
        if self.type not in TYPES_DE_PARAMETRE:
            raise ValueError(f"Paramètre {self.nom!r} : type {self.type!r} inconnu ({', '.join(TYPES_DE_PARAMETRE)})")
        if self.type == "array" and self.elements is None:
            raise ValueError(f"Paramètre {self.nom!r} : une liste déclare le schéma de ses éléments")
        inconnues = set(self.obligatoires) - {p.nom for p in self.proprietes}
        if inconnues:
            raise ValueError(f"Paramètre {self.nom!r} : sous-cases requises inconnues {sorted(inconnues)}")


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
    # F3 (E77): the NAME of the account of this software the tool keeps, when the organization
    # has several (two Google calendars). Never the model's choice: it comes from the tool.
    compte: str | None = None
    # [.mark] Module Restauration, lot 5: the agent's module settings (its configuration at pick-up), for an INTERNAL action whose module has
    # build settings (``commande_*``). ``None``: not known (a test, a manual set-up), the modules' defaults apply.
    configurations: dict[str, Any] | None = None
    # [.mark] M98 : la phrase du code en vigueur à l'endroit de l'appel (agent qui a la main, étape en cours), ``motif -> PhraseResolue`` : une action
    # interne qui met une phrase réglable dans son résultat la lit ici. ``None`` : pas de moteur (un essai), les règles de ``configurations`` valent.
    phrase_du_code: Callable[[str], Any] | None = None
    # [.mark] Agent fiable (agent B, 17/11) : attendre la passe du greffier en cours (``greffier.rattraper(delai)``), pour une action
    # interne qui lit ce que la personne vient de dire dans la fiche (adresse, prénom, numéro). ``None`` : pas de greffier.
    rattraper: Callable[[float], Any] | None = None


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
    # Lot 24 : the object this action WRITES into during the call (« panier », « reservation »). Two actions that write into the same object
    # never run at the same time in one call (when the agent's guard is on); reads stay parallel. ``None``: not serialised.
    serialise_avec: str | None = None
    # SA-18 (C15) : l'action reste DANS le fork (l'état de l'appel et la base du fork, jamais un tiers ni un message) : un essai rejoué la joue pour de
    # vrai, au lieu de la simuler par « Fait. ». Seule une action d'un connecteur interne, qui n'écrit pas ailleurs que dans l'appel, la déclare.
    local: bool = False
    # SA-49 (M115) : l'action est un ACTE pour la personne qui doit être fait avant la fin (un message laissé à l'équipe), même quand elle n'écrit
    # chez aucun tiers. ``None`` : la règle d'avant (une action qui écrit doit aboutir). Lu par ``action_non_aboutie.outil_doit_aboutir`` ; la case
    # de l'outil à l'écran (``doit_aboutir_avant_la_fin``) passe toujours devant.
    doit_aboutir: bool | None = None


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
    # F3: where the software stands. ``a_essayer`` = coded from the public documentation, proven
    # on recorded answers, never tried on a real test account (the default of a connector);
    # ``pret`` = tried on a test account with Evan (D3); ``a_activer`` = a card only, the vendor
    # opens its API on contract and the connector is coded for the first client of the sector.
    etat: str = "a_essayer"
    editeur: str | None = None
    # Une ACTION OUVERTE : ce que le connecteur a commencé dans l'appel (un panier, une réservation relue) et qui n'est pas fini. Reçoit la fiche de
    # l'appel, rend ``{"outil": "<l'action à appeler pour la finir>"}`` ou ``None``. Lu par le garde de fin d'appel (``action_non_aboutie``) : la fin est
    # refusée une fois tant qu'une action est ouverte. Le mécanisme ne connaît aucun mot de métier : c'est le connecteur qui dit ce qui est ouvert.
    action_ouverte: Callable[[dict], dict | None] | None = None
    # Agent fiable (Evan, 17/11) : L'ÉTAT de ce que le connecteur mène dans l'appel, en quelques lignes de faits (ce qui est pris, ce qui manque
    # ensuite), donné au modèle à chaque requête d'une étape qui porte un de ses outils (``workflow/etat_des_connecteurs.py``) : le modèle pose
    # lui-même la bonne question sans appeler d'outil pour la découvrir. Reçoit la fiche de l'appel et le contexte du décroché, rend un texte ou
    # ``None``. Jamais une consigne de conduite ni une phrase toute faite : des faits. Le mécanisme ne connaît aucun mot de métier.
    etat_pour_le_modele: Callable[[dict, dict], str | None] | None = None
    # Chantier Partie 1, lot 6 (E25, C4) : la ligne de L'ÉTAT DE L'APPEL de ce connecteur (ce qu'il a mené dans l'appel : aucun, commencé,
    # enregistré, annulé), montrée à l'étape qui passe la main (``passer_a`` : l'accueil, et l'accueil repris), à la place de l'état de son étape.
    # Reçoit la fiche de l'appel, rend une ligne ou ``None``. Des faits seulement ; le mécanisme ne connaît aucun mot de métier.
    etat_de_l_appel: Callable[[dict], str | None] | None = None
    # [.mark] Partie 1, lot 2 (E26) : les cases que l'état de l'appel et la carte ouvrent maintenant, en chemins (``reponse``, ``reponse.sens``,
    # ``ajouter[].composition``), d'après la fiche de l'appel ; et la forme qui change avec l'état (``{"requises": {chemin: [...]}, "descriptions":
    # {chemin: texte}}``). Lus avant chaque requête (``workflow/cases_selon_l_etat.py``). Même principe qu'``action_ouverte`` : le connecteur dit,
    # le mécanisme ne sait aucun métier. ``None`` : toutes les cases, toujours (les connecteurs d'avant).
    cases_visibles: Callable[[dict], frozenset[str]] | None = None
    # Chantier Partie 1, lot 6 : pour CET appel, les actions de ce connecteur n'écrivent dans le système d'aucun client (une prise de démo ou
    # d'essai). Reçoit le contexte de l'appel (organisation, run, contexte, configurations), rend un booléen. Lu au seul essai au clavier : vrai,
    # l'action y est jouée pour de vrai ; faux ou absent, elle reste simulée (B42). Le mécanisme ne connaît aucun mot de métier.
    sans_tiers: Callable[[Any], Awaitable[bool]] | None = None
    forme_selon_l_etat: Callable[[dict], dict] | None = None

    def action(self, nom: str) -> Action | None:
        return next((a for a in self.actions if a.nom == nom), None)


ETATS = ("a_essayer", "pret", "a_activer")

# V4 : les catégories du catalogue (la colonne de la fenêtre « Catalogue »), dans l'ordre de la maquette. Une catégorie vide n'est pas
# montrée par l'écran. Un connecteur déclaré sans catégorie ici fait échouer ``test_categories_du_catalogue`` : on la choisit en le codant.
CATEGORIES = (
    "CRM",
    "Agenda",
    "Messages",
    "Données",
    "Support",
    "Interventions",
    "Téléphonie",
    "Compta",
    "Immobilier",
    "Santé",
    "Vétérinaire",
    "Nos connecteurs",
)
CATEGORIE_DU_CONNECTEUR: dict[str, str] = {
    "hubspot": "CRM",
    "pipedrive": "CRM",
    "sellsy": "CRM",
    "salesforce": "CRM",
    "teamleader": "CRM",
    "nocrm": "CRM",
    "folk": "CRM",
    "google_agenda": "Agenda",
    "outlook_agenda": "Agenda",
    "calendly": "Agenda",
    "acuity": "Agenda",
    "setmore": "Agenda",
    "twilio_sms": "Messages",
    "gmail": "Messages",
    "slack": "Messages",
    "whatsapp_business": "Messages",
    "google_sheets": "Données",
    "airtable": "Données",
    "notion": "Données",
    "zendesk": "Support",
    "freshdesk": "Support",
    "crisp": "Support",
    "praxedo": "Interventions",
    "pennylane": "Compta",
    "hektor": "Immobilier",
    "apimo": "Immobilier",
    "cosium": "Santé",
    "doctolib": "Santé",
    "vetstoria": "Vétérinaire",
    "planificateur": "Nos connecteurs",
    "equipe": "Nos connecteurs",
    "dossier": "Nos connecteurs",
    "commande": "Nos connecteurs",
    "reservation": "Nos connecteurs",
    "service": "Nos connecteurs",
}


def categorie_de(connecteur: "Connecteur") -> str | None:
    return CATEGORIE_DU_CONNECTEUR.get(connecteur.nom)


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
    if connecteur.etat not in ETATS:
        raise CatalogueInvalide(f"{connecteur.nom}: unknown state « {connecteur.etat} ».")
    if connecteur.etat == "a_activer" and (connecteur.actions or connecteur.interne):
        raise CatalogueInvalide(f"{connecteur.nom}: a card « à activer » has no action.")
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
