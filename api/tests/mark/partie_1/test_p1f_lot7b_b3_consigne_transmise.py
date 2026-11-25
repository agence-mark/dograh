"""[.mark] Lot 7b-B, second passage, ligne 67 : la consigne au modèle ne parle de la transmission que quand elle est faite, et ne promet jamais « passer à l'équipe ».

Client « Annulez samedi, réservez-moi dimanche ». Avant : « Je vous passe l'équipe » (la consigne disait « passe-la à l'équipe » même sans transmission).
Après : la demande est transmise, l'équipe rappelle ; si la transmission n'a pas eu lieu, rien n'est promis.
"""

from __future__ import annotations

from api.services.reservation import porte as PORTE
from api.tests.mark import test_restauration_reservation as _RESA
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.partie_1.test_l07_reservation import MOTS

salle = _RESA.salle


async def _annuler_puis_redemander(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    r = await essai.tour("j'annule", annuler_une_reservation_enregistree=True)
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ANNULEE", r
    return await essai.tour("et plutôt dimanche à vingt heures pour deux au nom de Bob", personnes=2, jour="dimanche", heure="vingt heures", nom="Bob")


async def test_transmission_faite_la_consigne_dit_transmise_et_ne_dit_pas_passe(salle, monkeypatch):
    r = await _annuler_puis_redemander(salle, monkeypatch)
    consigne = str(r.get("a_faire")).lower()
    assert r["faits"].get("transmise_a_l_equipe") is True, r["faits"]
    assert "transmise" in consigne and "une réservation par appel" in consigne, consigne
    assert "passe" not in consigne, consigne


async def test_transmission_non_faite_rien_n_est_promis(salle, monkeypatch):
    monkeypatch.setattr(PORTE, "_transmettre_la_demande_a_l_equipe", lambda ctx, demande: False)
    r = await _annuler_puis_redemander(salle, monkeypatch)
    consigne = str(r.get("a_faire")).lower()
    assert "transmise_a_l_equipe" not in r["faits"], r["faits"]
    assert "une réservation par appel" in consigne, consigne
    for promesse in ("équipe", "passe", "transmis", "rappel"):
        assert promesse not in consigne, (promesse, consigne)
