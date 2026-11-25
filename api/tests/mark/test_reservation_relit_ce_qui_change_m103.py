"""[.mark] M103 : « on sera trois » relisait « trois personnes et au nom de Martin » alors que le nom ne change pas. Seul ce qui CHANGE
est pris et relu ; ce que le modèle renvoie tel quel ne se redit pas, et rien qui change ne se relit pas du tout."""

from __future__ import annotations

from api.services.reservation import moteur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_restauration_reservation_outils import Appel, salle  # noqa: F401


async def test_le_nom_qui_ne_change_pas_n_est_pas_relu(salle):
    a = Appel(salle)
    await a.confirmee()  # samedi 20 h, deux personnes, Alice
    r = await moteur.modifier(a.source, a.etat, a.appelant, personnes=3, prenom="Alice")
    assert r.manque == "relecture" and r.faits["ce_qui_change"] == {"personnes": 3}, r  # C6 n° 8 (décision d'Evan 25/11 9 h 30) : ce qui change, en faits
    assert "prenom" not in r.faits["ce_qui_change"]
    fait = await moteur.modifier(a.source, a.etat, a.appelant, personnes=3, prenom="alice", confirmer=True)
    assert fait.statut == "OK" and fait.faits["personnes"] == 3, fait


async def test_rien_qui_change_ne_se_relit_pas(salle):
    a = Appel(salle)
    await a.confirmee()
    r = await moteur.modifier(a.source, a.etat, a.appelant, personnes=2, prenom="Alice")
    assert r.statut == "DEJA_FAIT" and r.faits["inchangee"] is True and r.suggestion.startswith("Rien ne change"), r
    # un vrai changement de nom reste relu
    assert (await moteur.modifier(a.source, a.etat, a.appelant, prenom="Martin")).faits["ce_qui_change"] == {"prenom": "Martin"}  # C6 n° 8 (décision d'Evan 25/11 9 h 30) : en faits
