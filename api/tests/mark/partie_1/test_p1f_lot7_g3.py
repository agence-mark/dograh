"""[.mark] Lot 7a, G3 : ce que le code tient pour mener l'appel vit sous la conversation, jamais à plat dans la commande ou la réservation. Après le lot 6 (registre, numéros,
mémoire des fiches), le journal de ce qui est dit rejoint la conversation, aux deux métiers."""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import journal_du_dit as J
from api.tests.mark import test_restauration_reservation as RESERVATION
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

salle = RESERVATION.salle


def test_le_journal_du_dit_vit_dans_la_conversation():
    p: dict = {}
    assert J.noter(p, "fait", 1) == 1 and J.deja_dit(p, "fait") and J.fois(p, "fait") == 1
    assert J.CLE not in p and J.CLE in p[CONV.CLE], p
    J.oublier(p, "fait")
    assert not J.deja_dit(p, "fait")


async def test_apres_un_refus_le_journal_n_est_pas_a_plat_dans_la_commande(essai_de):
    e = await essai_de()
    await e.tour("en livraison", mode_de_retrait="livraison")
    await e.tour("au 8 rue Solférino à Compiègne", adresse="8 rue Solférino", commune="Compiègne")
    assert J.CLE not in e.p and J.CLE in e.p[CONV.CLE], (sorted(e.p), e.p[CONV.CLE].keys())


async def test_apres_une_fiche_le_journal_n_est_pas_a_plat_dans_la_reservation(salle, monkeypatch):
    e = EssaiReservation(salle, monkeypatch)
    await e.tour("quatre personnes samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    J.noter(e.etat, "essai", 1)
    assert J.CLE not in e.etat and J.CLE in e.etat[CONV.CLE], sorted(e.etat)
