"""[.mark] Les 16 permissions de l'équipe .mark : une ligne chacune, vérifiées côté serveur à chaque route.

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
}

# Partie 3, sous-lot 17a (décision n° 1 de Pierre, option A) : une clé d'API n'a QUE ces permissions (liste fermée). Tout le reste lui est
# refusé : publier, appeler, lancer une campagne, créer une clé, régler les modèles, les gestes de l'équipe (droits, rôles, clients, atelier).
# Une permission ajoutée à PERMISSIONS est donc fermée aux clés tant qu'elle n'est pas écrite ici.
PERMISSIONS_DE_CLE: frozenset[str] = frozenset(
    {
        "conversations.voir",  # lire les appels et leur rapport
        "agents.modifier",  # apparence, sites, établissements, équipe, lexique, connaissances, relance d'une action (routes /organizations)
        "connecteurs.autoriser",
        "base_client.connexion_portail",
    }
)

NOM_ADMINISTRATEUR = "Administrateur"
NOM_MEMBRE = "Membre"


def permissions_valides(cles) -> list[str]:
    """Les clés données, dédoublonnées et triées, ou ``ValueError`` si l'une n'existe pas."""
    inconnues = [c for c in cles if c not in PERMISSIONS]
    if inconnues:
        raise ValueError(f"Permission inconnue : {', '.join(sorted(set(inconnues)))}")
    return sorted(set(cles))
