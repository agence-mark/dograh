"""[.mark] Cards « À activer » (U3 sexies, point 8, F3): software whose vendor opens its API on contract.

A card has no action. The vendor signs the contract in the client's name, and the connector is coded
for the first client of the sector who gives us the access (E75). Nothing here calls anything.
"""

from __future__ import annotations

from api.services.integrations.connectors.catalogue import Connecteur, declarer

SUR_CONTRAT = tuple(
    declarer(Connecteur(nom=nom, libelle=libelle, integration=nom, actions=(), etat="a_activer", editeur=editeur))
    for nom, libelle, editeur in (
        ("hektor", "Hektor", "La Boîte Immo"),
        ("apimo", "Apimo", "Apimo"),
        ("cosium", "Cosium", "Cosium"),
        ("vetstoria", "Vetstoria", "Vetstoria"),
        ("praxedo", "Praxedo", "Praxedo"),
    )
)
