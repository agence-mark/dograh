"""Nuit du 18/11 : l'écran et la lecture de la caisse de démo montrent ce que la caisse a reçu du client (prénom, numéro, adresse) et la note
(consigne pour le livreur) : sans eux, une commande ne peut pas être comparée à ce que la personne a dit."""

from datetime import UTC, datetime

from api.routes.restauration_caisse_demo import _commande_rendue


def test_la_commande_rendue_porte_le_client_l_heure_voulue_et_la_note():
    ligne = {
        "ref": "8cf6206", "private_ref": "60ed0367", "statut": "accepted", "cree_le": datetime(2026, 11, 18, 0, 56, tzinfo=UTC),
        "corps": {
            "service_type": "delivery", "total": "12.90 EUR", "expected_time": "2026-11-18T20:30:00+01:00",
            "customer": {"first_name": "Evan", "phone": "+33788261409", "address_1": "12 rue de la République à Senlis"},
            "customer_notes": "Code 1234, deuxième étage", "items": [], "payments": [],
        },
    }
    rendue = _commande_rendue(ligne)
    assert rendue["client"] == {"prenom": "Evan", "telephone": "+33788261409", "adresse": "12 rue de la République à Senlis", "consigne_livraison": None}
    assert rendue["note"] == "Code 1234, deuxième étage"
    assert rendue["heure_voulue"] == "2026-11-18T20:30:00+01:00"
