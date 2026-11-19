"""[.mark] Mécanisme commun : la réservation par capacité, côté outils de l'agent (module Restauration, lot 8, E-48).

Un créneau demandé, un nombre de personnes, une capacité que le code calcule (``api/db/bases_clients/capacite.py``) : le modèle choisit comment le dire,
le code tient les faits (disponibilités, règles, place revérifiée à l'enregistrement). Rien ici ne connaît un métier : la capacité et
l'enregistrement viennent d'une SOURCE (``source.py``) ; la restauration en est la première (``services/restauration/source_reservation.py``).

- ``source`` : ce que le moteur demande à la capacité (protocole et registre des sources)
- ``moteur`` : les gestes : disponibilités, réserver, modifier, annuler, retrouver
- ``action`` : les outils du connecteur interne ``reservation``, joués comme les autres actions internes
"""
