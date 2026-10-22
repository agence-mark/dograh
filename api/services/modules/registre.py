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


@dataclass(frozen=True)
class Texte:
    en: str
    fr: str


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

PAR_CODE: dict[str, Module] = {m.code: m for m in MODULES}


def module_du_connecteur(connecteur: str | None) -> Module | None:
    for module in MODULES:
        if connecteur and connecteur in module.connecteurs:
            return module
    return None


def cles_des_modules() -> tuple[str, ...]:
    """Every agent key the modules own, in the registry's order."""
    return tuple(c for m in MODULES for c in m.cles_de_l_agent())
