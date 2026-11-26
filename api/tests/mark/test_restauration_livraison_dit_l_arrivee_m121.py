"""[.mark] M121 : en livraison, l'enregistrement disait « elle sera prête dans trente et une minutes ». L'heure annoncée d'une livraison
compte le délai de la zone EN ENTIER (E-42) : c'est l'heure à laquelle elle ARRIVE. Le code le dit ; à emporter, « prête » reste."""

from __future__ import annotations

from datetime import timedelta

from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_classeur_carte import JEUDI_MIDI
from api.tests.mark.test_restauration_classeur_commande import brouillon, commerce, enregistrer  # noqa: F401


async def test_une_livraison_dit_quand_elle_arrive(commerce):
    b = brouillon(mode="livraison", adresse={"commune": "Senlis"}, zone_id=commerce.zones["Senlis"], paiement={"moyens": [{"moyen": "carte", "montant": 2680}]})
    r = await enregistrer(commerce, b)
    assert r.statut == "ENREGISTREE" and r.faits["heure_annoncee"] == JEUDI_MIDI + timedelta(minutes=30), r
    assert (r.suggestion, r.faits["mode"], r.faits["quand_dit"]) == ("", "livraison", "dans trente minutes")  # C7 B9 (0e89e408) : plus de texte ; « enregistrée, prête/livrée … » est dans les faits mode et quand_dit


async def test_a_emporter_elle_reste_prete(commerce):
    r = await enregistrer(commerce, brouillon())
    assert (r.suggestion, r.faits["mode"], r.faits["quand_dit"]) == ("", "emporter", "dans vingt minutes")  # C7 B9 (0e89e408) : plus de texte ; « enregistrée, prête/livrée … » est dans les faits mode et quand_dit
