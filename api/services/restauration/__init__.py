"""[.mark] Module Restauration : la logique de domaine qui vit hors de la couche d'accès à la base du client.

Rangé par sujet : ``caisse/`` (liaison, envoi, synchro, annulation, tickets, ``prises/``, ``caisse_demo/``), ``envois_et_sms/``, ``appel_et_memoire/``
(dont ``conservation``, la purge de 30 jours), ``carte_et_allergenes/`` (dont l'allergie de la commande), ``mesures/``. Les deux sources du moteur
(``source_commande``, ``source_reservation``) restent ici. Le test de la source d'heure (D6) balaie tout ce dossier.
"""
