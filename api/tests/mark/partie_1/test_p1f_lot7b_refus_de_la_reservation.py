"""[.mark] Lot 7b, lignes 26 et 67 (Q1 = A) : le refus de la réservation (complet, une seule réservation par appel) est dit par le modèle, le code ne le dit plus d'avance.

26. Client « Une table pour quatre samedi à vingt heures » (la salle se remplit avant son « oui »). Avant : le code dit « Nous ne pouvons pas à cette heure-là. Je peux vous proposer … » ;
    après : le modèle dit le refus et propose les horaires libres avec ses mots, d'après ``faits.horaires_libres`` (la barrière des chiffres les laisse passer).
67. Client « Annulez samedi et réservez-moi dimanche ». Avant : le code dit « Je ne peux prendre qu'une réservation par appel… Je vous passe à l'équipe » et le tour s'arrête là,
    le transfert promis n'est jamais demandé au modèle ; après : le modèle reçoit le fait et la consigne « passe-la à l'équipe », il dit le refus et passe la personne.
"""

from __future__ import annotations

from api.db.bases_clients.restauration_reservation import creer_reservation
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.barriere_des_chiffres import chiffre_dans_la_phrase
from api.services.actions_communes.du import faits_du_refus
from api.services.reservation import porte as PORTE
from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.partie_1.test_l07_reservation import MOTS
from api.tests.mark import test_base_client as _BASE
from api.tests.mark import test_restauration_reservation as _RESA
from api.tests.mark.test_restauration_reservation import demande

base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle  # les fixtures du classeur, reprises sans import inutile


def _la_demande_est_transmise(essai, r) -> None:
    """Reprise 2 de l'audit : la promesse est tenue. La demande de la nouvelle réservation est écrite pour l'équipe (la liste des rappels de l'appel, comme la commande en panne) et le fait est posé."""
    from api.services.apres_appel import rappels

    assert r["faits"].get("transmise_a_l_equipe") is True, r["faits"]
    demandes = [x for x in essai.fiche_de_l_appel.get(rappels.CLE_RAPPEL) or [] if rappels.origine(x) == rappels.ORIGINE_RESERVATION]
    assert len(demandes) == 1 and "dimanche" in demandes[0]["objet"] and "Bob" in demandes[0]["objet"], demandes
    assert "dimanche" in rappels.resume_du_rappel(demandes[0]), rappels.resume_du_rappel(demandes[0])


async def test_26_complet_le_modele_dit_le_refus_et_propose_les_horaires_libres(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    q = r["question"]
    for i, (couverts, tel) in enumerate(((2, "+33600000001"), (2, "+33600000002"), (4, "+33600000003"), (6, "+33600000004"))):  # quelqu'un d'autre prend la salle
        assert (await creer_reservation(salle.c, salle.a, demande(couverts=couverts, telephone=tel, appel_id=f"p{i}"))).statut == "ENREGISTREE"
    r = await essai.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert not (essai.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}).get("avant"), essai.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE)  # le code ne dit pas le refus
    libres = r["faits"]["horaires_libres"]
    assert libres and all(isinstance(h, str) and h for h in libres), r
    d = PF.decider_apres_la_fiche(essai.fiche_de_l_appel, r, {"a_dire": "Cette heure est complète, mais j'ai de la place à d'autres heures."})
    assert d.mode != PAROLE.A_DIRE_SEUL, d
    dite = f"Cette heure est complète, mais j'ai {libres[0]}, ça vous irait ?"
    assert not chiffre_dans_la_phrase(dite, faits=faits_du_refus(r)), "les horaires libres sont des faits du retour : la barrière les laisse passer"


async def test_67_une_seule_reservation_par_appel_le_modele_dit_le_refus_et_passe_a_l_equipe(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    r = await essai.tour("j'annule", annuler_une_reservation_enregistree=True)
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ANNULEE", r
    r = await essai.tour("et plutôt dimanche à vingt heures pour deux au nom de Bob", personnes=2, jour="dimanche", heure="vingt heures", nom="Bob")
    assert await essai.nombre_de_reservations() == 1  # la règle reste : pas de seconde réservation
    assert not (essai.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}).get("avant"), essai.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE)  # le code ne dit rien
    assert "équipe" in str(r.get("a_faire")) and "une réservation par appel" in str(r.get("a_faire")), r  # la consigne : le dire, puis la demande est transmise
    _la_demande_est_transmise(essai, r)
    d = PF.decider_apres_la_fiche(essai.fiche_de_l_appel, r, {"a_dire": "Je ne prends qu'une réservation par appel ; je vous passe l'équipe pour dimanche."})
    assert d.mode != PAROLE.A_DIRE_SEUL, d  # le modèle a la parole, donc c'est lui qui appelle le transfert
