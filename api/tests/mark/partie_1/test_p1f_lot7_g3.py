"""[.mark] Lot 7a, G3 : ce que le code tient pour mener l'appel vit sous la conversation, jamais à plat dans la commande ou la réservation. Après le lot 6 (registre, numéros,
mémoire des fiches), le journal de ce qui est dit rejoint la conversation, aux deux métiers."""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import du as DU
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


# --- La question posée est un fait de la conversation (fiche du lot 7 § 3.1, ligne G3) ---


CLES_DE_LA_COMMANDE = frozenset({
    "a_planifier", "adresse", "client", "codes_dits", "commune_hors_zone", "connu", "consigne", "derniere_lecture", "derniere_lecture_mode", "dits_en_attente",
    "enregistree", "etape", "heure_voulue", "heure_voulue_dite", "lignes", "mentions_de_remise", "mode", "mode_dit", "moment_du_jour", "moment_voulu", "note",
    "notes_du_greffier", "paiement", "presse", "prochaine_ligne", "reglement_voulu", "relecture", "remise_refusee", "remises_du_code", "vente_en_plus_faite",
    "version", "zone", CONV.CLE,
})
CLES_DE_LA_RESERVATION = frozenset({"brouillon", "lecture", "numero_affiche", CONV.CLE})


def test_la_question_se_lit_par_la_lecture_publique_aux_deux_metiers():
    for dossier in ({"lignes": []}, {"brouillon": {}}):
        assert CONV.question_de(dossier) is None
        q = {"type": "relecture", "id": "Q-1", "texte": "C'est bon ?"}
        CONV.poser_question(dossier, q)
        assert CONV.question_de(dossier) == q and CONV.CLE in dossier and "question" not in dossier, dossier
        CONV.poser_question(dossier, None)
        assert CONV.question_de(dossier) is None


async def test_apres_une_fiche_la_commande_ne_garde_que_ses_cles(essai_de):
    e = await essai_de()
    await e.tour("en livraison", mode_de_retrait="livraison")
    await e.tour("au 8 rue Solférino à Compiègne", adresse="8 rue Solférino", commune="Compiègne")
    assert set(e.p) - CLES_DE_LA_COMMANDE == set(), sorted(set(e.p) - CLES_DE_LA_COMMANDE)


async def test_apres_une_fiche_la_reservation_ne_garde_que_ses_cles(salle, monkeypatch):
    e = EssaiReservation(salle, monkeypatch)
    await e.tour("quatre personnes samedi à vingt heures au nom d'Alice", personnes=4, jour="samedi", heure="vingt heures", nom="Alice")
    assert CONV.question_de(e.etat), "la réservation pose sa relecture : la question existe"
    assert set(e.etat) - CLES_DE_LA_RESERVATION == set(), sorted(set(e.etat) - CLES_DE_LA_RESERVATION)


def test_ce_qui_se_voit_voit_toujours_un_changement_de_question_aux_deux_metiers():
    """Le verdict « la commande a-t-elle changé ? » ne bouge pas avec le déplacement : une autre question est vue, seule ou avec un article."""
    for base in ({"lignes": []}, {"brouillon": {}}):
        dossier = {**base}
        CONV.poser_question(dossier, {"type": "relecture", "id": "Q-1", "texte": "C'est bon ?"})
        avant = DU.ce_qui_se_voit(dossier)
        assert DU.ce_qui_se_voit(dossier) == avant
        CONV.poser_question(dossier, {"type": "relecture", "id": "Q-2", "texte": "On confirme ?"})
        assert DU.ce_qui_se_voit(dossier) != avant, "la question seule a changé : la fiche a eu un effet"
        CONV.poser_question(dossier, {"type": "relecture", "id": "Q-1", "texte": "C'est bon ?"})
        assert DU.ce_qui_se_voit(dossier) == avant, "la même question reposée : aucun effet"
    commande = {"lignes": [{"ref": "a", "quantite": 1, "n": 1}]}
    CONV.poser_question(commande, {"type": "relecture", "id": "Q-1", "texte": "C'est bon ?"})
    avant = DU.ce_qui_se_voit(commande)
    commande["lignes"].append({"ref": "b", "quantite": 1, "n": 2})
    CONV.poser_question(commande, {"type": "relecture", "id": "Q-2", "texte": "On confirme ?"})
    assert DU.ce_qui_se_voit(commande) != avant
    CONV.de(commande)["tour_de_l_appel"] = 9
    assert DU.ce_qui_se_voit(commande) == DU.ce_qui_se_voit(commande)
