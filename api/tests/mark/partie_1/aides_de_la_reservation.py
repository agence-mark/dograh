"""[.mark] Aides publiques des tests de la réservation : la base de test d'une salle (fixture ``salle``) et ses constantes, reprises d'un seul endroit pour que les tests du lot
n'importent plus de noms d'un autre fichier de test."""

from api.tests.mark import test_restauration_reservation as _RESERVATION

salle = _RESERVATION.salle  # la fixture de la réservation, reprise telle quelle
SAMEDI_20H = _RESERVATION.SAMEDI_20H
TEL = _RESERVATION.TEL
