"""[.mark] Mécanisme commun : la commande sur catalogue (module « Commande », plan du chantier Restauration, lot 5, T-18).

Un panier qui se remplit PENDANT l'appel, article par article, depuis un catalogue fermé que le code tient (prix, choix obligatoires,
maximums, ruptures). Le modèle choisit comment le dire ; le code tient les faits (E-01). Rien ici ne connaît un métier : le catalogue,
l'état d'ouverture, le chiffrage et l'enregistrement viennent d'une SOURCE (``source.py``) ; la restauration en est la première
(``api/services/restauration/source_commande.py``).

- ``panier``  : l'état du panier dans la fiche de l'appel (survit à un compactage, se joint à une panne)
- ``lecture`` : ce que dit l'appelant, découpé en quantités et en morceaux
- ``source``  : ce que le moteur demande au catalogue (le protocole et le registre des sources)
- ``moteur``  : les gestes : choisir le mode, ajouter, modifier, retirer, vider, voir, finaliser
- ``parole``  : les montants en toutes lettres et les phrases proposées
"""
