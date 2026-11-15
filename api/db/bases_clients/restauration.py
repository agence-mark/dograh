"""[.mark] Module Restauration, lot 2 : LA couche d'accès au classeur (contrat comptoir ↔ classeur, § 4).

Le seul endroit par où le reste du fork lit et écrit les tables ``resto_*`` de la base d'un client. Il expose EXACTEMENT les
fonctions du contrat ; le travail est dans les fichiers voisins, coupés par sujet :

- ``restauration_carte``    : carte, version, ruptures, état de la caisse, état combiné, import de carte
- ``restauration_commande`` : enregistrer une commande, chemin des statuts, retrouver, planifiées
- ``restauration_remise``   : remises applicables, chiffrées
- ``restauration_client``   : fiche du client, consignes, recherche dans la carte, capacité
- ``restauration_purge``    : conservation de 30 jours

Toutes asynchrones. Premier argument : la connexion de la base du client (rôle ``_ecriture``), puis ``etablissement_id``
(relu dans la session ou l'appel, jamais dans un corps fourni par le modèle). Retour fermé ``Resultat(statut, faits,
suggestion, manque)`` pour tout ce qu'un outil appelle (statuts : ``restauration_commun.STATUTS``). Montants en
centimes ; allergènes ``None`` = inconnu, ``[]`` = aucun. L'heure vient de ``horloge`` (D6), jamais de l'heure réelle.
"""

from api.db.bases_clients.restauration_carte import (
    carte_du_restaurant,
    etat_caisse,
    etat_combine,
    importer_carte,
    poser_rupture,
    ruptures_du_restaurant,
    version_carte,
)
from api.db.bases_clients.restauration_client import (
    chercher_dans_la_liste,
    client_par_numero,
    disponibilites_capacite,
    ecrire_consigne_client,
)
from api.db.bases_clients.restauration_commande import (
    changer_statut,
    commandes_planifiees,
    enregistrer_commande,
    statut_commande,
)
from api.db.bases_clients.restauration_commun import RAISONS_REFUS, STATUTS, Resultat
from api.db.bases_clients.restauration_purge import purger
from api.db.bases_clients.restauration_remise import remises_applicables

__all__ = [
    "carte_du_restaurant",
    "version_carte",
    "ruptures_du_restaurant",
    "etat_caisse",
    "etat_combine",
    "chercher_dans_la_liste",
    "client_par_numero",
    "enregistrer_commande",
    "changer_statut",
    "statut_commande",
    "commandes_planifiees",
    "disponibilites_capacite",
    "remises_applicables",
    "ecrire_consigne_client",
    "importer_carte",
    "poser_rupture",
    "purger",
]

# Les types du retour fermé, importables d'ici sans faire partie des fonctions du contrat.
_ = (RAISONS_REFUS, STATUTS, Resultat)
