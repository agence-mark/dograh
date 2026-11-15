"""[.mark] Le retour fermé d'un geste de la commande : le même que celui du classeur (``Resultat(statut, faits, suggestion, manque)``).

Seul point de contact du mécanisme commun avec la couche d'accès : le reste du paquet importe d'ici, jamais du classeur.
"""

from api.db.bases_clients.restauration_commun import STATUTS, Resultat

__all__ = ["STATUTS", "Resultat"]
