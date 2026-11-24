"""[.mark] Lot 7a, reprise R1 : toute clé rangée sous ``conversation`` sort de ce que compare ``ce_qui_se_voit`` (la tenue interne), SAUF le journal du dit : une fiche dont le
seul effet est d'y écrire a quand même fait quelque chose (une recherche vaine de plus), elle n'est pas « sans effet »."""

from __future__ import annotations

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.du import CLE_DU, ce_qui_se_voit, du_du_retour
from api.tests.mark import test_restauration_reservation as RESERVATION
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

salle = RESERVATION.salle


def test_une_ecriture_au_journal_du_dit_change_ce_qui_se_voit():
    dossier: dict = {"lignes": []}
    avant = ce_qui_se_voit(dossier)
    J.noter(dossier, "fait")
    assert ce_qui_se_voit(dossier) != avant


def test_le_reste_de_la_conversation_ne_change_pas_ce_qui_se_voit():
    from api.services.actions_communes import conversation as CONV

    dossier: dict = {"lignes": []}
    avant = ce_qui_se_voit(dossier)
    CONV.de(dossier)["tour_de_l_appel"] = 4
    assert ce_qui_se_voit(dossier) == avant


async def test_deux_recherches_vaines_de_suite_ne_sont_pas_une_fiche_sans_effet(salle, monkeypatch):
    """« Au nom de Dupont », rien ; « au nom de Durand alors », rien non plus : la seconde n'écrit qu'au journal ; elle n'est pas « sans effet »."""
    e = EssaiReservation(salle, monkeypatch, appelant=None)
    r = await e.tour("au nom de Dupont, jeudi", jour="jeudi", nom="Dupont", retrouver_une_reservation_enregistree={"jour": "jeudi", "nom": "Dupont"})
    assert r["statut"] == "INTROUVABLE" or r.get("resultats"), r
    r = await e.tour("au nom de Durand alors", jour="jeudi", nom="Durand", retrouver_une_reservation_enregistree={"jour": "jeudi", "nom": "Durand"})
    assert not du_du_retour(r).rien_change and not r[CLE_DU]["rien_change"], r
    assert "rien changé" not in str(r.get("a_faire")), r.get("a_faire")
