"""[.mark] Lot 7b-C6, reprise R2 de l'audit (ordre de « C6 révisée » : la question est toujours la dernière ; décision d'Evan 25/11 8 h 45 : une question due oubliée relance le modèle).

Quand le code ne dit aucune suite après la phrase du modèle et qu'une question vient de naître ou attend (DC4, la proposition, la relecture de la réservation sans numéro à relire,
son changement, son annulation), la phrase du modèle doit POSER la question (« ? » à la fin) ; sinon le modèle repasse, puis il est relancé une fois avec ``consigne_des_chiffres_exiges``
(aucun mécanisme neuf). Avant : Client « Annulez ma commande. » / modèle « C'est entendu, j'annule votre commande de dix euros quatre-vingt-dix. » part tel quel (rien n'est annulé, le
client croit que c'est fait). Après : relancé une fois, puis la question part. Vraie source, vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.commande import registre as RQ
from api.services.mots_dits import montant_en_lettres
from api.services.workflow import parole_de_la_fiche as PF
from api.services.workflow.etat_des_connecteurs import ATTRIBUT
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark import test_base_client as _BASE
from api.tests.mark.partie_1 import aides_de_la_reservation as _RESA

from .aides_de_la_commande import a_emporter, jusqu_a_l_enregistrement, premier_article, refuser_la_proposition

base_essai, base_prete, salle = _BASE.base_essai, _BASE.base_prete, _RESA.salle  # les fixtures de la base et de la salle, reprises sans import nu

MOTS = "une table pour quatre samedi à vingt heures au nom de Paul"


def _verificateur(fiche: dict, connecteur: str | None) -> PF.VerificateurDeLaFiche:
    return PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=fiche, **({ATTRIBUT: {"fiche": connecteur}} if connecteur else {})))


def _passages(fiche: dict, retour: dict, phrase: str, seconde: str, connecteur: str | None = None) -> tuple[PAROLE.Decision, object]:
    """La décision au retour de la fiche (``phrase``), puis le contrôle de la phrase libre du second passage (``seconde``)."""
    d = PF.decider_apres_la_fiche(fiche, retour, {"a_dire": phrase}, connecteur=connecteur)
    return d, (None if d.mode == PAROLE.A_DIRE_SEUL else _verificateur(fiche, connecteur).controler(seconde))


async def _annulation_demandee(essai_de):
    e = await essai_de("casa-italia")
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    await jusqu_a_l_enregistrement(e)
    montant = montant_en_lettres(e.p["enregistree"]["total"])
    r = await e.tour("annulez ma commande", annuler_une_commande_enregistree=True)
    assert (CONV.question_de(e.p) or {}).get("type") == RQ.TYPE_ANNULATION, r
    return e, r, montant


async def test_dc4_une_affirmation_sans_question_n_est_pas_dite_le_modele_repasse(essai_de):
    e, r, montant = await _annulation_demandee(essai_de)
    affirme = f"C'est entendu, j'annule votre commande de {montant}."
    d, retenue = _passages(e.fiche_de_l_appel, r, affirme, affirme)
    assert d.mode == PAROLE.SECOND_PASSAGE, d
    assert retenue is not None and retenue.raison == PAROLE.CHIFFRES_EXIGES and retenue.consigne and "?" in retenue.consigne, retenue
    assert not e.p.get("annulee")


async def test_dc4_la_relance_qui_pose_la_question_part(essai_de):
    e, r, montant = await _annulation_demandee(essai_de)
    bonne = f"Vous voulez vraiment annuler la commande de {montant} ?"
    d, retenue = _passages(e.fiche_de_l_appel, r, f"C'est entendu, j'annule votre commande de {montant}.", bonne)
    assert d.mode == PAROLE.SECOND_PASSAGE and retenue is None, (d, retenue)


async def test_dc4_voisin_la_question_posee_d_emblee_part_seule(essai_de):
    e, r, montant = await _annulation_demandee(essai_de)
    bonne = f"Vous voulez vraiment annuler la commande de {montant} ?"
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": bonne})
    assert (d.mode, d.a_dire) == (PAROLE.A_DIRE_SEUL, bonne), d


async def test_la_proposition_sans_question_n_est_pas_dite(essai_de):
    """Client « Une margherita. » / modèle « Avec ça, un Coca à deux euros. » (sans « ? ») / le modèle repasse."""
    e = await essai_de()
    await a_emporter(e)
    r = await premier_article(e)
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "proposition" and not q.get("offerte"), q
    prix = montant_en_lettres(r["faits"]["proposition_a_poser"]["prix"])
    affirme = f"Avec ça, je vous mets un {q['article_propose']} à {prix}."
    d, retenue = _passages(e.fiche_de_l_appel, r, affirme, affirme)
    assert d.mode == PAROLE.SECOND_PASSAGE and retenue is not None and retenue.consigne, (d, retenue)


async def test_la_confirmation_voisine_sans_question_part_avec_sa_suite(essai_de):
    """Voisin : la confirmation (le code dit la suite M108, la question) : sa phrase sans « ? » part, rien ne change."""
    e = await essai_de("casa-italia")
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    r = await jusqu_a_l_enregistrement(e)
    phrase = f"C'est noté, votre commande sera prête {e.p['enregistree']['quand_dit']}."
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase})
    assert d.mode == PAROLE.A_DIRE_SEUL and d.a_dire.startswith(phrase), d


async def _reservee(salle, monkeypatch) -> EssaiReservation:
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Paul")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    essai.voix = False
    return essai


async def test_le_changement_de_la_reservation_sans_question_n_est_pas_dit(salle, monkeypatch):
    """Client « Finalement on sera cinq. » / modèle « Cinq personnes, c'est noté. » (rien n'est changé) / le modèle repasse ; « Cinq personnes alors, je change ? » part."""
    essai = await _reservee(salle, monkeypatch)
    r = await essai.tour("finalement on sera cinq", personnes=5)
    assert (r.get("question") or {}).get("type") == "recap_modif", r
    d, retenue = _passages(essai.fiche_de_l_appel, r, "Cinq personnes, c'est noté.", "Cinq personnes alors, je change ?", connecteur="reservation")
    assert d.mode == PAROLE.SECOND_PASSAGE and retenue is None, (d, retenue)


async def test_l_annulation_de_la_reservation_sans_question_est_relancee(salle, monkeypatch):
    essai = await _reservee(salle, monkeypatch)
    r = await essai.tour("je voudrais annuler", annuler_une_reservation_enregistree=True)
    assert (r.get("question") or {}).get("type") == "annulation", r
    affirme = "J'annule samedi vingt heures pour quatre."
    d, retenue = _passages(essai.fiche_de_l_appel, r, affirme, affirme, connecteur="reservation")
    assert d.mode == PAROLE.SECOND_PASSAGE and retenue is not None and retenue.consigne, (d, retenue)
