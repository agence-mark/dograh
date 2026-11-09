"""[.mark] Les permissions de l'équipe .mark : une ligne chacune, vérifiées côté serveur à chaque route.

Un rôle (table ``mark_roles``) porte un sous-ensemble de ces clés. Le code ne connaît que ces clés : une clé
inconnue est refusée à l'écriture d'un rôle. Les libellés servent à l'écran (Réglages, Équipe et rôles).
"""

from __future__ import annotations

# clé -> (groupe affiché, libellé)
PERMISSIONS: dict[str, tuple[str, str]] = {
    "agents.modifier": ("Agents", "Modifier les agents"),
    "agents.publier": ("Agents", "Publier les agents"),
    "agents.supprimer": ("Agents", "Supprimer et archiver les agents"),
    "builder.lancer": ("Builder IA", "Lancer le builder"),
    "tests.jouer": ("Tests", "Jouer les tests et les bancs"),
    "clients.creer": ("Clients", "Créer un client"),
    "clients.exporter_ramener": ("Clients", "Exporter et ramener un agent"),
    "clients.ouvrir_portail": ("Clients", "Ouvrir le portail d'un client"),
    "cles.gerer": ("Clés", "Gérer les clés"),
    "telephonie.gerer": ("Téléphonie", "Gérer la téléphonie"),
    "conversations.voir": ("Conversations", "Voir les conversations"),
    "donnees.exporter": ("Données", "Exporter les données"),
    "equipe.gerer": ("Équipe", "Gérer les membres et les invitations"),
    "roles.gerer": ("Équipe", "Gérer les rôles"),
    "atelier.regler": ("Atelier", "Régler l'atelier (Labo)"),
    # Partie 3, lot 15 (P-6) : les écritures du Hub (réponses, suivi, notes, témoignages), journalisées depuis la partie 2.
    "relation.ecrire": ("Relation clients", "Écrire dans la relation clients (réponses, notes, témoignages)"),
    # Partie 3, sous-lot 17a : les deux gestes que le portail fait avec la clé du client, chacun avec sa permission (liste fermée des clés).
    "connecteurs.autoriser": ("Clés", "Autoriser, reconnecter et couper les comptes d'un client"),
    "base_client.connexion_portail": ("Clés", "Ouvrir l'accès du portail à la base du client"),
    # Partie 3, SA-17c : fusionner deux contacts, « ce n'est pas la même personne », « ne pas mémoriser » (ouverte à la clé du client).
    "contacts.traiter": ("Clients", "Traiter les contacts d'un client (fusionner, séparer, ne pas mémoriser)"),
    # Partie 3, N3b (décision 20) : lancer la suite de tests d'un agent depuis une automatisation (n8n), avec la clé de l'organisation.
    "tests.automatiser": ("Tests", "Lancer les tests d'un agent depuis une automatisation"),
    # Revue RV (point 3, tranché par Pierre le 05/11) : la permission PROPRE au portail. Elle n'ouvre que les écritures que le portail fait avec la
    # clé du client (apparence, emplacement, établissements, équipe, lexique, connaissances, relance d'une action : ``contrat_portail_fork.json``).
    # Une session d'équipe n'en a pas besoin : elle garde ``agents.modifier`` sur ces routes, exactement comme avant.
    # RV (point 3) : le miroir de Claude Code (conversation rangée avec son agent, sans secret) se range avec la clé MCP de l'organisation ; c'est la seule
    # route ``/builder`` qu'une clé garde (``/builder/miroir``), sous sa propre permission.
    "builder.miroir": ("Builder IA", "Ranger les conversations de Claude Code dans le miroir (clé MCP)"),
    "portail.ecrire": ("Clés", "Écrire dans l'espace d'un client depuis son portail (apparence, établissements, équipe, lexique, connaissances)"),
    # Clôture, lot A (D24) : lire le journal complet de l'équipe (qui a fait quoi, où, depuis l'écran, l'API ou le MCP). Donnée par défaut aux rôles
    # suprêmes (ceux qui gèrent l'équipe) par la migration ; réglable à l'écran comme toute permission.
    "journal.lire": ("Équipe", "Lire le journal de l'équipe"),
}

# Partie 3, sous-lot 17a (décision n° 1 de Pierre, option A) : une clé d'API n'a QUE ces permissions (liste fermée). Tout le reste lui est
# refusé : publier, appeler, lancer une campagne, créer une clé, régler les modèles, les gestes de l'équipe (droits, rôles, clients, atelier).
# Une permission ajoutée à PERMISSIONS est donc fermée aux clés tant qu'elle n'est pas écrite ici.
PERMISSIONS_DE_CLE: frozenset[str] = frozenset(
    {
        "conversations.voir",  # lire les appels et leur rapport
        "builder.miroir",  # RV : seulement ``POST /builder/miroir`` (le hook de Claude Code)
        "portail.ecrire",  # RV : apparence, sites, établissements, équipe, lexique, connaissances, relance d'une action (les routes du contrat du portail)
        "connecteurs.autoriser",
        "base_client.connexion_portail",
        "contacts.traiter",
        "tests.automatiser",  # N3b : seulement les deux routes /automatisation/agents/{id}/tests (jamais tests.jouer, qui ouvre les appels réels)
    }
)

# N3b : un rôle qui joue déjà les tests (``tests.jouer``) peut aussi les lancer depuis une automatisation : aucune migration de rôles,
# la permission est tenue pour accordée à ceux qui ont l'autre (un rôle peut aussi la recevoir seule, depuis l'écran des rôles).
PERMISSIONS_IMPLIQUEES: dict[str, str] = {"tests.automatiser": "tests.jouer"}

# Clôture, lot A (D21) : une clé d'API PORTÉE PAR UN RÔLE a les permissions de ce rôle, bornées par celles de son créateur au moment de l'appel,
# SAUF les gestes de l'équipe elle-même (règle du serveur : une clé n'a jamais les droits, les rôles, ni la création d'un client, ni le journal
# de l'équipe, ni le réglage de l'atelier). Une clé sans rôle garde la liste fermée ``PERMISSIONS_DE_CLE`` (clés du portail).
PERMISSIONS_JAMAIS_PAR_CLE_A_ROLE: frozenset[str] = frozenset(
    {"equipe.gerer", "roles.gerer", "clients.creer", "journal.lire", "atelier.regler", "cles.gerer"}
)

NOM_ADMINISTRATEUR = "Administrateur"
NOM_MEMBRE = "Membre"


def permissions_valides(cles) -> list[str]:
    """Les clés données, dédoublonnées et triées, ou ``ValueError`` si l'une n'existe pas."""
    inconnues = [c for c in cles if c not in PERMISSIONS]
    if inconnues:
        raise ValueError(f"Permission inconnue : {', '.join(sorted(set(inconnues)))}")
    return sorted(set(cles))
