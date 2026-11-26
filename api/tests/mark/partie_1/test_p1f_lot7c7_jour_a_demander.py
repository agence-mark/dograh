"""[.mark] Lot 7b-C7, B7 : ``jour_a_demander`` (``reservation/porte.py``) double-t-il ``valeur_du_manque`` ? Testé d'abord, retiré seulement s'il double.

Il pose « le jour » dans le constat caché (``du_de_la_fiche``) quand le dernier geste rend ``INCOMPLETE`` sur le jour. À la réservation, l'état dit la même chose
(``ce_qui_manque_ensuite`` : le jour). À la RECHERCHE d'une réservation d'avant sur un jour ambigu (« jeudi », sans nom ni numéro affiché), l'état dit « le nom et le jour
de sa réservation d'avant » alors que seul le jour est à redemander (le nom n'a jamais été demandé) : ``jour_a_demander`` ne double pas, il précise. Il reste.
Vraie porte, vraie base, une source dont le jour est ambigu."""

from __future__ import annotations

from api.services.actions_communes import du as DU
from api.services.actions_communes.resultat import Resultat
from api.services.reservation import etat_pour_le_modele as E
from api.services.reservation.phrases_du_manque import valeur_du_manque
from api.tests.mark import test_base_client as _BASE
from api.tests.mark.partie_1 import aides_de_la_reservation as _RESA
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle  # les fixtures de la base et de la salle, reprises sans import nu

DEUX_JEUDIS = [{"jour": "2026-11-19", "jour_dit": "jeudi dix-neuf novembre"}, {"jour": "2026-11-26", "jour_dit": "jeudi vingt-six novembre"}]


async def _jeudi_ambigu(texte, heure):
    return Resultat("AMBIGU", {"candidats": DEUX_JEUDIS}, "", "jour")


def _manque_du_constat(retour: dict) -> str | None:
    return (retour.get(DU.CLE_DU) or {}).get("manque")


async def test_a_la_reservation_le_jour_a_demander_est_celui_de_l_etat(salle, monkeypatch):
    """Client « Pour deux. » : le jour manque ; ``jour_a_demander`` et l'état disent la même valeur."""
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("pour deux", personnes=2)
    assert _manque_du_constat(r) == E.LE_JOUR == valeur_du_manque(essai.etat), r


async def test_a_la_recherche_sur_un_jour_ambigu_seul_le_jour_est_redemande(salle, monkeypatch):
    """Client « Ma réservation de jeudi. » (numéro masqué, aucun nom) : le jour est à préciser ; l'état seul aurait demandé le nom ET le jour d'avant."""
    essai = EssaiReservation(salle, monkeypatch, appelant=None)
    monkeypatch.setattr(essai.source, "resoudre_une_date", _jeudi_ambigu)
    r = await essai.tour("ma réservation de jeudi", retrouver_une_reservation_enregistree={"jour": "jeudi"})
    assert (r["resultats"][0]["statut_du_module"], r["resultats"][0].get("manque")) == ("INCOMPLETE", "jour"), r
    assert valeur_du_manque(essai.etat) == E.LA_RESERVATION_D_AVANT  # ce que dirait l'état seul
    assert _manque_du_constat(r) == E.LE_JOUR, r  # ``jour_a_demander`` précise : il ne double pas, il reste
