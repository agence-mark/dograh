"""[.mark] Lot F8 : le registre des modules de l'agent (D120 à D122, M1 à M8).

UN endroit dit, pour chaque module : son interrupteur, ses besoins et ce qui les remplit, les outils qui
lui appartiennent, ses réglages de construction (.mark) et ses réglages terrain (le client). Tout le reste
le lit : les routes du portail, la page de l'agent (par ces routes), l'appel (un module coupé ne laisse
aucun outil, ``appel.py``), la base du client (catalogue de la 020).

⛔ Zéro vocabulaire métier (M1) : un module sait un mécanisme (lire un nombre, une commune, un créneau),
jamais un métier. ⛔ Aucun réglage terrain inventé : l'inventaire du lot 0
(``Labo-agent-vocal/plans/cloture-code-avant-migration/inventaire-modules.md``) n'en trouve qu'au
planificateur (D124). Un module neuf = une entrée ici ; ses clés d'agent vont aussi dans
``CLES_THEME_MODULES`` (``services/groupe/reglages.py``), et un test compare les deux.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Où vit un réglage d'agent.
AGENT = "workflow_configurations"
# Les tables du planificateur dans la base du client (010, 013).
REGLES = "reglage_planificateur"
TYPES = "type_rendez_vous"
# Le magasin commun de la 020 (aucun module n'y déclare encore de réglage).
MAGASIN = "module_reglage"
# Le classeur du module (la base du client, par SA couche d'accès) : un réglage terrain qui vit dans les données du module, pas dans
# une table de réglages. Le registre ne nomme pas la table : seule la couche d'accès du module la connaît.
CLASSEUR = "classeur"


@dataclass(frozen=True)
class Texte:
    en: str
    fr: str


@dataclass(frozen=True)
class Etiquette:
    """Lot 11 : une étiquette que le module pose dans le contexte de l'appel au décroché (``{{cle}}``) : COURTE, stable pendant l'appel, utile à presque
    chaque appel, sans rien à calculer ni garantir (§ 3.3 du plan). Le reste est un outil. Une étiquette n'est jamais une donnée de carte."""

    cle: str
    libelle: Texte
    exemple: str = ""


@dataclass(frozen=True)
class Besoin:
    code: str
    libelle: Texte
    # Un domaine de traducteur (``services/hub/traducteurs.py``) ; ``None`` : une source du fork.
    domaine: str | None = None
    source_interne: Texte | None = None


@dataclass(frozen=True)
class Reglage:
    cle: str
    lieu: str = AGENT
    bloc: str | None = None
    modifiable: bool = True


@dataclass(frozen=True)
class Module:
    code: str
    libelle: Texte
    # La clé de l'agent qui l'allume ; ``None`` : allumé quand une étape porte un de ses outils.
    interrupteur: str | None
    # Les connecteurs internes (``integrations/connectors/actions``) dont les outils lui appartiennent.
    connecteurs: tuple[str, ...] = ()
    # Lot 11 : les connecteurs qui ALLUMENT ce module quand un de leurs outils est sur une étape, sans lui en donner les outils (ils restent
    # à leur propre module, avec son interrupteur). Un module d'ensemble s'allume ainsi par ce que ses modules de base portent.
    signal: tuple[str, ...] = ()
    # Lot 11 : les étiquettes que le module pose au décroché (famille « module » de l'éditeur).
    etiquettes: tuple[Etiquette, ...] = ()
    # Où est la fonction qui lit leurs valeurs (``module.chemin:fonction``, ``async def f(organization_id, workflow_id, appel) -> dict``) et le module
    # dont l'interrupteur les allume (un module d'ensemble n'a pas le sien : il suit celui d'un module de base). ``None`` : lui-même.
    fournisseur_d_etiquettes: str | None = None
    interrupteur_des_etiquettes: str | None = None
    besoins: tuple[Besoin, ...] = ()
    construction: tuple[Reglage, ...] = ()
    terrain: tuple[Reglage, ...] = field(default=())

    def cles_de_l_agent(self) -> tuple[str, ...]:
        """Every key of the agent's configuration this module owns: its switch, then its settings."""
        cles = [self.interrupteur] if self.interrupteur else []
        cles += [r.cle for r in self.construction if r.lieu == AGENT]
        return tuple(cles)


_COMMUNES = Besoin(
    "liste_des_communes",
    Texte("The list of towns", "La liste des communes"),
    source_interne=Texte("National list of French towns (in the fork)", "Liste nationale des communes (dans le fork)"),
)

MODULES: tuple[Module, ...] = (
    Module(
        "nombres",
        Texte("Numbers and references", "Nombres et références"),
        "conversion_nombres_transcription",
        construction=(Reglage("variables_reference"),),
    ),
    Module(
        "communes_et_voies",
        Texte("Town and street", "Commune et rue"),
        "verification_communes",
        besoins=(
            _COMMUNES,
            Besoin(
                "voies_d_une_commune",
                Texte("The streets of a town", "Les voies d'une commune"),
                source_interne=Texte("National address base (in the fork)", "Base Adresse Nationale (dans le fork)"),
            ),
        ),
        construction=(Reglage("variables_commune"), Reglage("sons_communes"), Reglage("verification_voies")),
    ),
    Module("epellation", Texte("Spelling", "Épellation"), "lecture_epellation"),
    Module(
        "lexique",
        Texte("Trade vocabulary", "Lexique métier"),
        "lexique_metier",
        besoins=(
            Besoin(
                "vocabulaire",
                Texte("The organization's vocabulary", "Le vocabulaire de l'organisation"),
                source_interne=Texte(
                    "Organization settings, theme « Listening »", "Paramètres de l'organisation, thème « Écoute »"
                ),
            ),
        ),
        construction=(Reglage("sons_lexique"),),
    ),
    Module(
        "recherche_liste",
        Texte("Search in a closed list", "Recherche dans une liste"),
        "recherche_dans_une_liste",
        besoins=(
            Besoin(
                "liste",
                Texte("The closed list to search", "La liste fermée à chercher"),
                source_interne=Texte(
                    "The organization's lists (client database), or a list of another module of the same organization",
                    "Les listes de l'organisation (base du client), ou la liste d'un autre module de la même organisation",
                ),
            ),
        ),
        construction=(
            Reglage("recherche_liste_seuil_retenu"),
            Reglage("recherche_liste_seuil_ambigu"),
            Reglage("recherche_liste_son"),
            Reglage("recherche_liste_sens"),
        ),
        # W31 : les synonymes d'un élément, proposés à l'import et actifs après relecture ; ils vivent dans le classeur du module.
        terrain=(Reglage("synonymes", CLASSEUR),),
    ),
    # [.mark] Module Restauration, lot 5 (T-18) : la commande sur un catalogue fermé. Mécanisme commun, aucun mot de métier :
    # la restauration en est la première configuration (le catalogue est sa carte, la zone sa zone de livraison).
    Module(
        "commande",
        Texte("Order on a catalogue", "Commande sur catalogue"),
        "commande_sur_catalogue",
        connecteurs=("commande",),
        besoins=(
            Besoin(
                "liste",
                Texte("The catalogue the caller orders from", "Le catalogue où l'appelant commande"),
                source_interne=Texte(
                    "The organization's catalogue (client database), searched by the closed-list module",
                    "Le catalogue de l'organisation (base du client), cherché par le module de recherche dans une liste",
                ),
            ),
            Besoin(
                "zone",
                Texte("The service zone of the order", "La zone de service de la commande"),
                source_interne=Texte("The establishment's zones (client database)", "Les zones de l'établissement (base du client)"),
            ),
            Besoin(
                "commande",
                Texte("Where the order is saved", "Où la commande est enregistrée"),
                source_interne=Texte("The establishment's order book (client database)", "Le classeur de commandes de l'établissement (base du client)"),
            ),
        ),
        construction=(
            Reglage("commande_ordre_impose"),
            Reglage("commande_relecture_deux_temps"),
            Reglage("commande_vente_en_plus"),
            Reglage("commande_notes_libres"),
            Reglage("commande_mentions_de_remise"),
            Reglage("commande_fois_avant_la_sortie"),
            Reglage("commande_moities_prix"),
        ),
    ),
    Module(
        "controle_des_donnees",
        Texte("Field recognition", "Reconnaissance des champs"),
        "controle_donnees",
        besoins=(_COMMUNES,),
        construction=(
            Reglage("variables_telephone"),
            Reglage("variables_code_postal"),
            Reglage("variables_courriel"),
            Reglage("variables_date"),
        ),
    ),
    Module(
        "equipe",
        Texte("Team and transfers", "Équipe et transferts"),
        "equipe_connue",
        connecteurs=("equipe",),
        besoins=(
            Besoin(
                "equipe",
                Texte("The team", "L'équipe"),
                source_interne=Texte("Client database (« Team and routing »)", "Base du client (« Équipe et routage »)"),
            ),
        ),
    ),
    Module(
        "verification_appelant",
        Texte("Caller verification", "Vérification de l'appelant"),
        "verification_appelant",
        connecteurs=("dossier",),
        besoins=(
            Besoin(
                "lire_un_dossier",
                Texte("Read a record", "Lire un dossier"),
                domaine="dossier",
                source_interne=Texte("Client database (when no software is chosen)", "Base du client (sans logiciel choisi)"),
            ),
        ),
    ),
    Module(
        "planificateur",
        Texte("Appointment planner", "Planificateur de rendez-vous"),
        None,
        connecteurs=("planificateur",),
        besoins=(
            Besoin("lire_les_creneaux", Texte("Read free slots", "Lire les créneaux libres"), domaine="agenda"),
            Besoin("poser_un_rendez_vous", Texte("Book an appointment", "Poser un rendez-vous"), domaine="agenda"),
        ),
        # D124 : ce qui reste à .mark (dans la base du client, organisation puis établissement).
        construction=(
            Reglage("nombre_creneaux", REGLES),
            Reglage("horizon_jours", REGLES),
            Reglage("pas_min", REGLES),
            Reglage("vitesse_kmh", REGLES),
            Reglage("coefficient_trajet", REGLES),
            Reglage("repli", REGLES),
            Reglage("fenetre_equite_jours", REGLES),
            Reglage("sujet_id", TYPES),
        ),
        # D124 : Quand, Quoi, Où, Qui (les jours fériés affichés seulement).
        terrain=(
            Reglage("plages", REGLES, "quand"),
            Reglage("delai_minimal_h", REGLES, "quand"),
            Reglage("jours_feries", REGLES, "quand", modifiable=False),
            Reglage("libelle", TYPES, "quoi"),
            Reglage("duree_min", TYPES, "quoi"),
            Reglage("marge_avant_min", TYPES, "quoi"),
            Reglage("marge_apres_min", TYPES, "quoi"),
            Reglage("actif", TYPES, "quoi"),
            Reglage("zone_communes", REGLES, "ou"),
            Reglage("zone_rayon_km", REGLES, "ou"),
            Reglage("trajets_comptes", REGLES, "ou"),
            Reglage("repartition", REGLES, "qui"),
            Reglage("personne_visible", REGLES, "qui"),
        ),
    ),
)

# [.mark] Lot 11 du chantier module : le module d'ensemble « Restauration ». SON SIGNAL D'ALLUMAGE, pour un agent : un outil d'un de ses
# connecteurs sur une étape (``commande`` par signal, ses outils restent au module ``commande`` et à son interrupteur ; ``reservation`` et
# ``service`` lui appartiennent). C'est ce que lit ``mark.module_agent`` (donc la purge de 30 jours des copies d'appel, ``conservation.py``).
# Le portail garde son propre réglage par établissement (le drapeau « module actif » de la migration 030) : il dit si l'ÉCRAN du restaurant est ouvert,
# pas quel agent porte le module ; les deux ne se déduisent pas l'un de l'autre.
RESTAURATION = Module(
    "restauration",
    Texte("Restaurant", "Restauration"),
    None,
    connecteurs=("reservation", "service"),
    signal=("commande",),
    construction=(Reglage("reservation_fois_avant_la_sortie"),),  # lot 7b (M6) : la clé de la réservation ; celle de la commande est au module commande
    fournisseur_d_etiquettes="api.services.restauration.appel_et_memoire.etiquettes:valeurs",
    interrupteur_des_etiquettes="commande",
    # § 3.3 : ce qui est court, stable et utile à presque chaque appel. Le nom, l'adresse, l'état d'ouverture et la prochaine ouverture sont déjà
    # posés par l'établissement (``etablissement``, ``adresse_etablissement``, ``etat_ouverture``, ``reouverture``) : ils ne sont pas répétés ici.
    etiquettes=(
        Etiquette("commande_types_ouverts", Texte("Order › Open types", "Commande › Types ouverts"), "à emporter et en livraison"),
        Etiquette("livraison_phrase_des_zones", Texte("Delivery › Zones sentence", "Livraison › Phrase des zones"), "Nous livrons Beauvais et Auneuil."),
        Etiquette("commande_minimum", Texte("Order › Minimum", "Commande › Minimum"), "15 euros en livraison"),
        Etiquette("commande_paiements_acceptes", Texte("Order › Accepted payments", "Commande › Paiements acceptés"), "par carte et en espèces"),
        Etiquette("appel_client_reconnu", Texte("Call › Known customer", "Appel › Client reconnu"), "Karim"),
        Etiquette("commande_derniere", Texte("Order › Last order", "Commande › Dernière commande"), "une Regina Normale et un Coca-Cola, à emporter"),
        Etiquette("equipe_motifs", Texte("Team › Reasons", "Équipe › Motifs"), "une réclamation, ou un appel au sujet d'une commande déjà passée"),
    ),
    besoins=(
        Besoin(
            "classeur",
            Texte("The establishment's record book", "Le classeur de l'établissement"),
            source_interne=Texte(
                "The establishment's orders, bookings and settings (client database)",
                "Les commandes, réservations et réglages de l'établissement (base du client)",
            ),
        ),
    ),
)
MODULES = (*MODULES, RESTAURATION)

PAR_CODE: dict[str, Module] = {m.code: m for m in MODULES}


def module_du_connecteur(connecteur: str | None) -> Module | None:
    for module in MODULES:
        if connecteur and connecteur in module.connecteurs:
            return module
    return None


def cles_des_modules() -> tuple[str, ...]:
    """Every agent key the modules own, in the registry's order."""
    return tuple(c for m in MODULES for c in m.cles_de_l_agent())
