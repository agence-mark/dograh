"""[.mark] Lot 8, PE-2, Q3 : le voisin réservation de « Ah merci. » (la table de parole est commune, refus 11 de l'audit).

Réservation enregistrée, client « Ah merci. », le modèle rejoue deux fois une fiche VIDE et rien n'est dû : sa phrase est dite seule, comme à la commande (``test_p1f_lot8_pe_ah_merci``)."""

from __future__ import annotations

from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.du import RIEN_CHANGE
from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark import test_base_client as _BASE
from api.tests.mark.partie_1 import aides_de_la_reservation as _RESA
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle  # les fixtures de la base et de la salle, reprises sans import nu

PHRASE = "Avec plaisir."


async def test_ah_merci_une_fiche_vide_rejouee_dit_la_phrase_du_modele_a_la_reservation(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour("une table pour quatre samedi à vingt heures au nom de Paul", personnes=4, jour="samedi", heure="vingt heures", nom="Paul")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    fiche = essai.fiche_de_l_appel
    r = await essai.fiche()
    d = PF.decider_apres_la_fiche(fiche, r, {"a_dire": PHRASE}, connecteur="reservation")
    assert (d.mode, d.motif) == (PAROLE.SECOND_PASSAGE, RIEN_CHANGE), d  # la relance du tour
    r = await essai.fiche()
    d = PF.decider_apres_la_fiche(fiche, r, {"a_dire": PHRASE}, connecteur="reservation")
    assert (d.mode, d.a_dire, d.motif) == (PAROLE.A_DIRE_SEUL, PHRASE, "fait"), d
