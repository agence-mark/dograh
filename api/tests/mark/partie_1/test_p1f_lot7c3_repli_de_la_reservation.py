"""[.mark] Lot 7b-C3, commit 9, repris au lot 7b-C5 (décision d'Evan 25/11 8 h 45) : la porte de la réservation range les FAITS du refus comme fait bloquant du tour ; si le modèle se tait, le code le relance avec eux
(il ne dit plus le texte du refus). Le fait vaut pour un refus de la base, une réservation introuvable, la règle « une seule réservation par appel » (la promesse de transmission seulement si la demande est
transmise) et la capacité non réglée ; rien pour le reste. La fiche de commande n'est pas touchée."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.repli import CLE_DU_TOUR, CLE_FAIT_BLOQUANT, consigne_de_relance, faits_du_fait_bloquant, poser_le_fait_bloquant
from api.db.bases_clients.restauration_reservation import creer_reservation
from api.services.reservation import moteur
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.partie_1.test_l07_reservation import MOTS
from api.tests.mark import test_base_client as _BASE
from api.tests.mark import test_restauration_reservation as _RESA
from api.tests.mark.test_restauration_reservation import demande
from api.services.reservation.porte import refuse_a_dire


base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle


def r(statut, faits=None, suggestion="", manque=None):
    return SimpleNamespace(statut=statut, faits=faits or {}, suggestion=suggestion, manque=manque)


HOMARD = {"statut_du_module": "INTROUVABLE", "manque": None, "faits": {"article": "pizza au homard"}}


def _consigne(essai) -> dict:
    """Ce que la relance du modèle muet recevrait : les faits du refus du tour, puis ce qui est dû."""
    import json

    from api.services.integrations.connectors.catalogue import connecteur

    consigne = consigne_de_relance(essai.etat, essai.fiche_de_l_appel, PAROLE.etat_du_tour(essai.fiche_de_l_appel), connecteur("reservation"))
    return json.loads(consigne[consigne.index("{"):])


def test_un_refus_et_un_introuvable_sont_a_dire():
    assert refuse_a_dire(r("REFUSEE", {"detail": "complet"}, "C'est complet.")) and refuse_a_dire(r("INTROUVABLE", {}, "Je ne trouve pas de réservation."))
    # décision d'Evan 25/11 8 h 45 (lot 7b-C5) : le refus se tient même sans texte de secours (``suggestion`` vide)
    assert refuse_a_dire(r("REFUSEE", {"detail": "complet"}, ""))


def test_une_seule_par_appel_est_a_dire_seulement_quand_la_reservation_de_l_appel_est_annulee():
    dernier = moteur._une_seule_par_appel_annulee("R1")
    assert dernier.suggestion == "", "le texte vit dans la feuille de secours, plus dans le moteur"
    assert refuse_a_dire(dernier)
    assert not refuse_a_dire(r("DEJA_FAIT", {"raison": "deja_une_reservation_dans_cet_appel"}))


def test_la_capacite_non_reglee_est_a_dire():
    assert refuse_a_dire(r("INCOMPLETE", manque="capacite"))


def test_le_reste_n_est_pas_a_dire():
    assert not refuse_a_dire(r("OK", {}, "ok")) and not refuse_a_dire(r("INCOMPLETE", manque="jour")) and not refuse_a_dire(None)


async def test_mini_dialogue_complet_le_fait_bloquant_porte_les_faits_du_refus(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    q = r["question"]
    for i, (couverts, tel) in enumerate(((2, "+33600000001"), (2, "+33600000002"), (4, "+33600000003"), (6, "+33600000004"))):
        assert (await creer_reservation(salle.c, salle.a, demande(couverts=couverts, telephone=tel, appel_id=f"p{i}"))).statut == "ENREGISTREE"
    r = await essai.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    faits = faits_du_fait_bloquant(essai.fiche_de_l_appel)
    assert [f["statut_du_module"] for f in faits] == ["REFUSEE"] and faits[0]["faits"].get("propositions"), faits
    assert _consigne(essai)["a_dire"] == faits  # le modèle muet est relancé avec le refus et les horaires libres, jamais avec « Nous ne pouvons pas… »


async def test_mini_dialogue_une_seule_par_appel_dit_la_transmission_faite(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    r = await essai.tour("j'annule", annuler_une_reservation_enregistree=True)
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    r = await essai.tour("plutôt dimanche à vingt heures pour deux au nom de Bob", personnes=2, jour="dimanche", heure="vingt heures", nom="Bob")
    assert r["faits"].get("transmise_a_l_equipe") is True, r["faits"]
    faits = faits_du_fait_bloquant(essai.fiche_de_l_appel)
    assert [f["statut_du_module"] for f in faits] == ["DEJA_FAIT"] and faits[0]["faits"]["transmise_a_l_equipe"] is True, faits


async def test_une_lecture_de_reservation_ne_touche_pas_au_fait_bloquant_d_une_commande_refusee(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    commande = {"tour": 1, "faits": {"commande": [HOMARD]}}
    essai.fiche_de_l_appel[CLE_FAIT_BLOQUANT] = dict(commande)
    r = await essai.dit(MOTS).lecture(sujet="places_libres", jour="samedi", personnes=4)  # une lecture ne passe pas par la fiche de réservation
    assert r["statut"] == "LU" and essai.fiche_de_l_appel[CLE_FAIT_BLOQUANT] == commande


async def test_mini_dialogue_groupe_trop_grand_le_repli_offre_un_message_a_l_equipe(salle, monkeypatch):
    """R = A. Client « On sera vingt-cinq. », le modèle se tait deux fois : le repli ne renvoie pas la personne au restaurant qu'elle a déjà au téléphone, il pose l'offre en question."""
    essai = EssaiReservation(salle, monkeypatch)
    await essai.tour(MOTS, personnes=25, jour="samedi", heure="vingt heures", nom="Alice")
    consigne = _consigne(essai)
    assert consigne["a_dire"][0]["statut_du_module"] == "REFUSEE" and consigne["a_dire"][0]["faits"]["maximum"] == 6, consigne  # le maximum est le fait que le modèle dit
    assert "appeler le restaurant" not in str(consigne)  # le modèle propose le message à l'équipe d'après les faits, le code ne dit rien


async def test_mini_dialogue_capacite_non_reglee_la_consigne_et_le_texte_nomment_le_meme_geste(salle, monkeypatch):
    """Client « Une table pour quatre samedi. », ni table ni capacité réglées : la consigne du modèle et le texte du repli offrent le même geste, un message à l'équipe."""
    await salle.c.execute("DELETE FROM mark.resto_table WHERE site_id = $1", salle.a)
    await salle.c.execute("UPDATE mark.resto_regle_reservation SET couverts_simultanes = NULL, couverts_max_creneau = NULL WHERE site_id = $1", salle.a)
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    consigne = str(r.get("a_faire")).lower()
    relance = _consigne(essai)
    assert "message" in consigne and "passer" not in consigne, consigne
    assert [f["manque"] for f in relance["a_dire"]] == ["capacite"], relance  # le même fait que la consigne : le modèle offre un message à l'équipe


async def test_dans_un_meme_tour_un_refus_puis_une_reservation_enregistree_le_repli_ne_redit_pas_le_refus(salle, monkeypatch):
    """Le fait bloquant du refus ne survit pas à ce qui le remplace dans le même tour : la réservation est relue sans refus, le repli ne dit plus « groupe trop grand »."""
    essai = EssaiReservation(salle, monkeypatch)
    await essai.dit(MOTS).fiche(personnes=25, jour="samedi", heure="vingt heures", nom="Alice")
    assert faits_du_fait_bloquant(essai.fiche_de_l_appel), "le refus est bien posé"
    r = await essai.fiche(personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    assert r["statut"] != "REFUSEE" and r["question"]["type"] == "recapitulatif", r
    assert faits_du_fait_bloquant(essai.fiche_de_l_appel) == [], faits_du_fait_bloquant(essai.fiche_de_l_appel)


async def test_mini_dialogue_pizza_au_homard_et_table_la_commande_refusee_reste_dite_apres_la_reservation(salle, monkeypatch):
    """R5 (a). Client « Une pizza au homard et une table pour deux ce soir. », le modèle se tait : la relance porte le homard refusé ET la réservation, la personne ne croit pas sa pizza commandée."""
    essai = EssaiReservation(salle, monkeypatch)
    essai.dit(MOTS)
    poser_le_fait_bloquant(essai.fiche_de_l_appel, essai.fiche_de_l_appel[CLE_DU_TOUR], "commande", [HOMARD])  # la commande refuse le homard dans ce tour
    r = await essai.fiche(personnes=2, jour="samedi", heure="vingt heures", nom="Paul")
    assert r["statut"] not in ("REFUSEE", "INTROUVABLE"), r  # la réservation avance dans le même tour, sans refus
    assert faits_du_fait_bloquant(essai.fiche_de_l_appel) == [HOMARD], faits_du_fait_bloquant(essai.fiche_de_l_appel)  # la réservation, sans refus, ne retire pas celui de la commande


async def test_une_fiche_de_commande_sans_refus_ne_retire_pas_le_refus_de_la_table(salle, monkeypatch):
    """R5 (b), ordre inverse : le refus de la réservation reste quand la porte de la commande pose « aucun »."""
    essai = EssaiReservation(salle, monkeypatch)
    await essai.dit(MOTS).fiche(personnes=25, jour="samedi", heure="vingt heures", nom="Alice")
    refus = faits_du_fait_bloquant(essai.fiche_de_l_appel)
    assert refus
    poser_le_fait_bloquant(essai.fiche_de_l_appel, None, "commande")  # ce que fait la porte de la commande au début d'une fiche (porte.py)
    assert faits_du_fait_bloquant(essai.fiche_de_l_appel) == refus


async def test_les_deux_refus_du_tour_sont_dits_ensemble_dans_l_ordre_d_ecriture(salle, monkeypatch):
    """R5 : la relance porte les faits bloquants du tour des deux métiers, dans l'ordre d'écriture."""
    essai = EssaiReservation(salle, monkeypatch)
    essai.dit(MOTS)
    poser_le_fait_bloquant(essai.fiche_de_l_appel, essai.fiche_de_l_appel[CLE_DU_TOUR], "commande", [HOMARD])
    await essai.fiche(personnes=25, jour="samedi", heure="vingt heures", nom="Alice")
    faits = faits_du_fait_bloquant(essai.fiche_de_l_appel)
    assert len(faits) == 2 and faits[0] == HOMARD and faits[1]["statut_du_module"] != HOMARD["statut_du_module"], faits
    assert _consigne(essai)["a_dire"] == faits


async def test_au_tour_suivant_aucun_fait_bloquant_n_est_dit(salle, monkeypatch):
    """R5 (d) : les faits du tour d'avant ne sont jamais redits."""
    essai = EssaiReservation(salle, monkeypatch)
    essai.fiche_de_l_appel[CLE_DU_TOUR] = 1
    poser_le_fait_bloquant(essai.fiche_de_l_appel, 1, "commande", [HOMARD])
    poser_le_fait_bloquant(essai.fiche_de_l_appel, 1, "reservation", [{"statut_du_module": "REFUSEE", "manque": None, "faits": {}}])
    assert faits_du_fait_bloquant(essai.fiche_de_l_appel)
    essai.fiche_de_l_appel[CLE_DU_TOUR] = 2
    assert faits_du_fait_bloquant(essai.fiche_de_l_appel) == []
