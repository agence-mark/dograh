"""[.mark] Lot 7a, reprises R3, R4, R5 de l'audit : ce que ferme une réponse (``_ferme`` de la commande, ``_repondre`` de la réservation), à comportement égal d'avant le registre."""

from __future__ import annotations

from api.services.actions_communes.resultat import Resultat
from api.services.commande import registre as RQ
from api.tests.mark import test_restauration_reservation as RESERVATION
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation

salle = RESERVATION.salle


def test_r3_le_refus_de_l_etape_de_formule_garde_la_question_seulement_quand_il_est_le_sien():
    """Le refus ``plusieurs_choix`` de la réponse à l'étape (il porte l'identifiant de la question) la garde ; le même refus rendu par le choix entre deux contenus (l'étape,
    le maximum, aucun identifiant de question) l'a toujours fermée."""
    from api.services.commande.briques import formule_a_etapes

    q = {"id": "Q-9", "type": formule_a_etapes.TYPE_DE_LA_QUESTION}
    sa_reponse = Resultat("HORS_CARTE", {"raison": "plusieurs_choix", "question": "Q-9", "valeurs": ["a", "b"]}, "")
    celui_du_choix = Resultat("HORS_CARTE", {"raison": "plusieurs_choix", "etape": "Boisson", "maximum": 1}, "")
    assert RQ._ferme(q, "autre", sa_reponse, ["a", "b"]) is False
    assert RQ._ferme(q, "autre", celui_du_choix, ["a"]) is True


def test_r5_une_heure_faite_d_espaces_ne_ferme_pas_la_question_de_l_heure():
    q = {"id": "Q-2", "type": "heure_proposee"}
    ok = Resultat("OK", {}, "")
    assert RQ._ferme(q, "autre", ok, ["   "]) is False
    assert RQ._ferme(q, "autre", ok, []) is False
    assert RQ._ferme(q, "autre", ok, ["vingt heures"]) is True


async def test_r4_rien_ne_peut_suivre_un_choix_non_compris_dans_la_meme_fiche(salle, monkeypatch):
    """Avant le registre : la question « laquelle ? » n'était remise que si la DERNIÈRE opération de la fiche était le choix non compris. Vérifié : elle l'est toujours (aucune autre case ne passe)."""
    from api.db.bases_clients.restauration_reservation import creer_reservation
    from api.tests.mark.partie_1.test_l07_reservation import SAMEDI_20H, TEL

    for numero, debut, personnes in (("a", SAMEDI_20H, 2), ("b", SAMEDI_20H.replace(day=15, hour=19), 3)):
        r = await creer_reservation(salle.c, salle.a, {"debut": debut, "couverts": personnes, "prenom": "Alice", "telephone": TEL, "appel_id": f"avant-{numero}"})
        assert r.statut == "ENREGISTREE", r
    e = EssaiReservation(salle, monkeypatch)
    a = await e.tour("annuler ma réservation", retrouver_une_reservation_enregistree={})
    q = a["question"]
    suivi = await e.tour("euh bleu, et annulez-la", reponse={"question_id": q["id"], "sens": "autre", "valeurs": ["bleu"]}, annuler_une_reservation_enregistree=True)
    ops = [x["operation"] for x in suivi["resultats"]]
    # Tant que « laquelle ? » attend, la case d'annulation n'est pas montrée : rien ne peut suivre le choix non compris dans la fiche (la dernière opération est donc toujours lui)
    assert ops == ["reponse"], ops
    assert suivi["question"]["id"] == q["id"], suivi.get("question")
