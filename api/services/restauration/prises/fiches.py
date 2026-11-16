"""[.mark] Module Restauration, lot 3 : les quatre fiches de capacités du chantier (``fiches-capacites.md``).

HubRise (vraie caisse, ou caisse de démo du lot 20 : même fiche, adresse différente) · imprimante Star CloudPRNT ·
portail (le classeur est maître) · test (tests automatiques seulement). Les valeurs viennent de la note de Pierre du 13/11,
de la documentation HubRise lue le 15/11 et des réponses enregistrées (``hubrise-reponses/``, numéro en commentaire).
"""

from __future__ import annotations

from dataclasses import replace

from api.services.restauration.prises.capacites import Capacites

ADRESSES_HUBRISE = ("https://api.hubrise.com/v1", "https://manager.hubrise.com")

HUBRISE = Capacites(
    carte="lue", carte_notifiee=True,  # 02, 04 ; catalog.update
    ruptures="lues", ruptures_posees_par_nous=True,  # 05, 06 : inventaire produits ET options, expires_at
    etat_restaurant="lu_et_envoye",  # 07, 08 : order_acceptance normal, débordé + minutes, pause + reprise
    temps_preparation=True, horaires=True,  # 01
    commande_non_payee=True,  # 12
    controle_avant_creation=False,  # 13, 14 : HubRise ne recalcule rien
    annulation=True,  # statut cancelled
    etapes=frozenset({"recue", "acceptee", "en_preparation", "prete", "terminee", "refusee", "annulee"}),  # 21, 22
    anti_doublon="chercher_avant_renvoi",  # 20 : private_ref
    notifications="signees",  # X-HubRise-Hmac-SHA256, 6 tentatives de 1 à 32 min
    clients_lus=True,  # 10, 11 : ?phone= en E.164
    remises_lues=True,  # discounts et deals de la carte
    represente=frozenset({"retrait", "formules", "tva_par_mode", "allergenes", "plusieurs_paiements"}),  # ni imbrication ni second téléphone
    limites=(
        "500 requêtes par minute, 2 500 par heure, 10 000 par jour",
        "lecture des commandes : 10 par minute",
        "réponse à un message en moins de 20 secondes",
        "compte gratuit : 5 commandes par mois",
    ),
    adresses_permises=ADRESSES_HUBRISE,  # D4, D5 ; la caisse de démo ajoute la sienne (Labo seulement, ``adresses.py``)
)

IMPRIMANTE = Capacites(
    carte="non", carte_notifiee=False,
    ruptures="non", ruptures_posees_par_nous=False,
    etat_restaurant="non", temps_preparation=False, horaires=False,
    commande_non_payee=True, controle_avant_creation=False, annulation=False,
    etapes=frozenset({"recue", "imprimee"}),  # ticket récupéré ; imprimé (étape propre du journal du ticket)
    anti_doublon="notre_table",
    notifications="interrogation",  # l'imprimante interroge toutes les 5 s
    clients_lus=False, remises_lues=False,
    represente=frozenset({"imbrication", "retrait", "formules", "allergenes", "plusieurs_paiements", "second_telephone"}),  # imprimés en clair
    limites=(
        "la confirmation de l'impression peut se perdre (repli prévu)",
        "statuts papier et capot",
    ),
    adresses_permises=(),  # aucune sortante : c'est l'imprimante qui vient
)

PORTAIL = Capacites(
    carte="lue", carte_notifiee=False,
    ruptures="lues", ruptures_posees_par_nous=True,
    etat_restaurant="lu", temps_preparation=True, horaires=True,
    commande_non_payee=True, controle_avant_creation=False, annulation=True,
    etapes=frozenset({"recue", "acceptee", "en_preparation", "prete", "terminee", "refusee", "annulee"}),  # changées à la main par le Rush
    anti_doublon="notre_table",
    notifications="aucune",  # rien à recevoir : le classeur est la source
    clients_lus=True, remises_lues=True,
    represente=frozenset({"imbrication", "retrait", "formules", "tva_par_mode", "allergenes", "horaires_carte", "plusieurs_paiements", "second_telephone"}),
    limites=(),
    adresses_permises=(),
)

# Test : tout va bien côté caisse (comme HubRise), sans adresse : jamais d'appel sortant. Jamais proposée à l'écran,
# jamais branchable sur un établissement (``registre.py`` la refuse hors tests).
TEST = replace(HUBRISE, adresses_permises=(), limites=())
TEST_SANS_ACCEPTEE = replace(TEST, etapes=TEST.etapes - {"acceptee"})  # prouve ``TRANSMISE`` (lot 3)

FICHES: dict[str, Capacites] = {
    "hubrise": HUBRISE,
    "imprimante": IMPRIMANTE,
    "portail": PORTAIL,
    "test": TEST,
}
