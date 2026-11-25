"""[.mark] Lot 7b-C3, commit 9 (COMPORTEMENT, R = A) : la porte de la réservation range le texte du refus comme fait bloquant du tour ; si le modèle se tait deux fois, le code le dit.
Le texte vaut pour un refus de la base, une réservation introuvable, la règle « une seule réservation par appel » (la promesse de transmission seulement si la demande est transmise)
et la capacité non réglée ; rien pour le reste. La fiche de commande n'est pas touchée."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes.repli import CLE_FAIT_BLOQUANT, phrase_du_fait_bloquant, repli_dit_par_le_code
from api.db.bases_clients.restauration_reservation import creer_reservation
from api.services.reservation import moteur
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.partie_1.test_l07_reservation import MOTS
from api.tests.mark import test_base_client as _BASE
from api.tests.mark import test_restauration_reservation as _RESA
from api.tests.mark.test_restauration_reservation import demande
from api.services.reservation import textes_de_secours as TS


base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle


def r(statut, faits=None, suggestion="", manque=None):
    return SimpleNamespace(statut=statut, faits=faits or {}, suggestion=suggestion, manque=manque)


def test_un_refus_et_un_introuvable_disent_leur_suggestion():
    assert TS.du_refus(r("REFUSEE", {"detail": "complet"}, "C'est complet."), False) == "C'est complet."
    assert TS.du_refus(r("INTROUVABLE", {}, "Je ne trouve pas de réservation."), False) == "Je ne trouve pas de réservation."


def test_une_seule_par_appel_ne_promet_la_transmission_que_si_elle_est_faite():
    dernier = moteur._une_seule_par_appel_annulee("R1")
    assert dernier.suggestion == "", "le texte vit dans la feuille de secours, plus dans le moteur"
    court = "Je ne peux prendre qu'une réservation par appel, et celle de cet appel est annulée."
    assert TS.du_refus(dernier, False) == court
    assert TS.du_refus(dernier, True) == f"{court} Je transmets votre demande à l'équipe, elle vous rappelle."


def test_la_capacite_non_reglee_dit_qu_il_n_y_a_pas_de_place_confirmee():
    assert "ne peux pas confirmer une place" in TS.du_refus(r("INCOMPLETE", manque="capacite"), False)
    assert TS.du_refus(r("INCOMPLETE", manque="capacite"), False) == TS.capacite_non_reglee({})


def test_le_reste_ne_dit_rien():
    assert TS.du_refus(r("OK", {}, "ok"), False) == "" and TS.du_refus(r("INCOMPLETE", manque="jour"), False) == ""
    assert TS.du_refus(r("DEJA_FAIT", {"raison": "deja_une_reservation_dans_cet_appel"}), False) == ""


async def test_mini_dialogue_complet_le_fait_bloquant_est_le_refus(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    q = r["question"]
    for i, (couverts, tel) in enumerate(((2, "+33600000001"), (2, "+33600000002"), (4, "+33600000003"), (6, "+33600000004"))):
        assert (await creer_reservation(salle.c, salle.a, demande(couverts=couverts, telephone=tel, appel_id=f"p{i}"))).statut == "ENREGISTREE"
    r = await essai.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    dit = phrase_du_fait_bloquant(essai.fiche_de_l_appel)
    assert dit and dit.startswith("Nous ne pouvons pas") and "Je peux vous proposer" in dit, dit
    assert repli_dit_par_le_code(None, None, essai.fiche_de_l_appel) == dit  # R = A : le modèle se tait deux fois, le repli du code dit le refus


async def test_mini_dialogue_une_seule_par_appel_dit_la_transmission_faite(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    r = await essai.tour("j'annule", annuler_une_reservation_enregistree=True)
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    r = await essai.tour("plutôt dimanche à vingt heures pour deux au nom de Bob", personnes=2, jour="dimanche", heure="vingt heures", nom="Bob")
    assert r["faits"].get("transmise_a_l_equipe") is True, r["faits"]
    assert phrase_du_fait_bloquant(essai.fiche_de_l_appel) == TS.une_seule_par_appel({"transmise": True})


async def test_une_lecture_de_reservation_ne_touche_pas_au_fait_bloquant_d_une_commande_refusee(salle, monkeypatch):
    essai = EssaiReservation(salle, monkeypatch)
    commande = {"tour": 1, "texte": "Il n'y a plus de pizza."}
    essai.fiche_de_l_appel[CLE_FAIT_BLOQUANT] = dict(commande)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    assert r["statut"] != "REFUSEE" and essai.fiche_de_l_appel[CLE_FAIT_BLOQUANT] == commande


async def test_mini_dialogue_groupe_trop_grand_le_repli_offre_un_message_a_l_equipe(salle, monkeypatch):
    """R = A. Client « On sera vingt-cinq. », le modèle se tait deux fois : le repli ne renvoie pas la personne au restaurant qu'elle a déjà au téléphone, il pose l'offre en question."""
    essai = EssaiReservation(salle, monkeypatch)
    await essai.tour(MOTS, personnes=25, jour="samedi", heure="vingt heures", nom="Alice")
    dit = repli_dit_par_le_code(None, None, essai.fiche_de_l_appel)
    assert dit and "appeler le restaurant" not in dit and dit.endswith("?"), dit


async def test_mini_dialogue_capacite_non_reglee_la_consigne_et_le_texte_nomment_le_meme_geste(salle, monkeypatch):
    """Client « Une table pour quatre samedi. », ni table ni capacité réglées : la consigne du modèle et le texte du repli offrent le même geste, un message à l'équipe."""
    await salle.c.execute("DELETE FROM mark.resto_table WHERE site_id = $1", salle.a)
    await salle.c.execute("UPDATE mark.resto_regle_reservation SET couverts_simultanes = NULL, couverts_max_creneau = NULL WHERE site_id = $1", salle.a)
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    consigne = str(r.get("a_faire")).lower()
    dit = repli_dit_par_le_code(None, None, essai.fiche_de_l_appel)
    assert "message" in consigne and "passer" not in consigne, consigne
    assert dit and "message" in dit and dit.endswith("?"), dit
