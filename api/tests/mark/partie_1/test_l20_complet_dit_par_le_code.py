"""Lot 20 (banc final, n2) : « complet à 21 h 30 » : la phrase du modèle qui propose d'autres heures porte des chiffres, la barrière des chiffres la
retenait trois fois et le code disait « Pardon, je n'ai pas bien saisi ». Source : le code ne disait jamais lui-même le refus et ses propositions.
Garde sur l'état : un refus ``complet`` de la réservation est dit par le code, mot pour mot (comme la relecture)."""

from api.services.actions_communes.resultat import Resultat
from api.services.reservation.porte import textes_du_code


def test_le_refus_complet_et_ses_heures_sont_dits_par_le_code():
    refus = Resultat("REFUSEE", {"raison": "autre", "detail": "complet", "propositions": [{"heure_dite": "20 h 30"}, {"heure_dite": "22 h"}]},
                     "Nous ne pouvons pas à cette heure-là. Je peux vous proposer 20 h 30 ou 22 h.")
    assert textes_du_code({}, refus, "reserver", None, False) == {"avant": refus.suggestion}


def test_un_autre_refus_reste_dit_par_le_modele():
    refus = Resultat("REFUSEE", {"raison": "autre", "detail": "passee"}, "Cette réservation est passée.")
    assert textes_du_code({}, refus, "annuler", None, False) == {}
