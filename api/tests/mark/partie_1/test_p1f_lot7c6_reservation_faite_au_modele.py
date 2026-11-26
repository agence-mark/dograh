"""[.mark] Lot 7b-C6, commit 9 (décision d'Evan 25/11 9 h 30, § 8 bis ; P2 : le code vérifie personnes et heure) : réservée, modifiée, annulée passent au modèle.

Avant : code « C'est réservé pour quatre personnes, samedi quatorze novembre à vingt heures, au nom de Paul. ».
Après : modèle « C'est noté, je vous attends samedi à vingt heures pour quatre. ». La phrase du modèle doit dire les personnes et l'heure (barrière) : sans elles, il est relancé une
fois, puis le code redit le fait accompli gardé au journal (jamais un tour muet). La base ne rend plus qu'un texte de secours (nombres en lettres : « trois personnes », plus « 3 »).
Vraie source, vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.db.bases_clients import restauration_reservation as RR
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import parole as PAROLE
from api.services.reservation import porte as PORTE
from api.services.reservation import textes_de_secours as TS
from api.services.workflow import parole_de_la_fiche as PF
from api.services.workflow.etat_des_connecteurs import ATTRIBUT
from api.tests.mark.partie_1.aides_de_la_reservation import salle  # noqa: F401
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401

MOTS = "une table pour quatre samedi à vingt heures au nom de Paul"


def _textes(essai: EssaiReservation) -> dict:
    return dict(essai.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {})


def _dire(essai: EssaiReservation, retour: dict, phrase: str, relance: str | None = None) -> str | None:
    """Ce qui part à la voix quand le modèle écrit ``phrase`` avec la fiche, puis ``relance`` au second passage (``None`` : la même phrase)."""
    fiche = essai.fiche_de_l_appel
    textes = _textes(essai)
    d = PF.decider_apres_la_fiche(fiche, retour, {"a_dire": phrase}, connecteur="reservation")
    fiche[PORTE.CLE_TEXTES_DU_CODE] = textes
    if d.mode == PAROLE.A_DIRE_SEUL:
        return d.a_dire
    verif = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=fiche, **{ATTRIBUT: {"fiche": "reservation"}}))
    seconde = relance if relance is not None else phrase
    retenue = verif.controler(seconde)
    if retenue is None:
        return seconde
    if retenue.a_dire is not None or not retenue.consigne:
        return retenue.a_dire
    suite = verif.controler_la_relance(seconde)
    return suite.a_dire if suite is not None else seconde


async def _reservee(salle, monkeypatch) -> tuple[EssaiReservation, dict]:
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Paul")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    return essai, r


async def test_la_reservation_faite_est_dite_par_le_modele_avec_les_personnes_et_l_heure(salle, monkeypatch):
    """Client « Oui. » / modèle « C'est noté, je vous attends samedi à vingt heures pour quatre. » ; le code ne dit rien."""
    essai, r = await _reservee(salle, monkeypatch)
    textes = _textes(essai)
    assert not textes.get("avant") and not textes.get("suffixe"), textes  # le code ne dit plus « C'est réservé… »
    assert textes.get("chiffres_exiges") == {"personnes": "4", "heure": "vingt heures"}, textes
    assert "C'est réservé" not in str(r), r
    assert J.fait_accompli(essai.etat) == textes.get("fait_accompli") and "quatre personnes" in textes["fait_accompli"], textes  # gardé au journal seulement (reprise R1)
    phrase = "C'est noté, je vous attends samedi à vingt heures pour quatre."
    assert _dire(essai, r, phrase) == phrase


async def test_sans_l_heure_le_modele_est_relance_puis_le_code_ne_redit_plus_le_fait_accompli(salle, monkeypatch):
    """décisions d'Evan 25/11 8 h 45 et 9 h 30 (P3), C5 § 2, coordinateur 26/11 2 h 05 (P3 tel quel) : reprise R1 de C6 : aucune suite réglée après la réservation faite : rien de composé (``RepliqueVerifiee`` dit la phrase réglée « pas compris », P3 ; jamais un tour muet)."""
    essai, r = await _reservee(salle, monkeypatch)
    dit = _dire(essai, r, "C'est noté.", relance="Parfait, c'est fait.")
    assert dit is None, dit


async def test_la_reservation_modifiee_est_dite_par_le_modele(salle, monkeypatch):
    """Client « Finalement on sera cinq. » / « Oui. » / avant, code « C'est modifié : samedi … à vingt heures, 5 personnes. » / après, modèle « C'est changé, cinq personnes samedi à
    vingt heures. »."""
    essai, _ = await _reservee(salle, monkeypatch)
    r = await essai.tour("finalement on sera cinq", personnes=5)
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    textes = _textes(essai)
    assert not textes.get("avant"), textes
    assert textes.get("chiffres_exiges") == {"personnes": "5", "heure": "vingt heures"}, textes
    assert "cinq personnes" in textes.get("fait_accompli", ""), textes  # nombres en lettres
    phrase = "C'est changé, cinq personnes samedi à vingt heures."
    assert _dire(essai, r, phrase) == phrase


async def test_la_reservation_annulee_est_dite_par_le_modele(salle, monkeypatch):
    """Client « Oui, annulez. » / avant, code « C'est annulé. » / après, modèle « C'est fait, votre réservation est annulée. »."""
    essai, _ = await _reservee(salle, monkeypatch)
    r = await essai.tour("je voudrais annuler", annuler_une_reservation_enregistree=True)
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ANNULEE", r
    textes = _textes(essai)
    assert not textes.get("avant") and textes.get("chiffres_exiges") == {}, textes
    phrase = "C'est fait, votre réservation est annulée."
    assert _dire(essai, r, phrase) == phrase


async def test_la_base_ne_rend_que_des_textes_de_secours_en_lettres(salle):
    from api.tests.mark.test_restauration_reservation import creer

    r = await creer(salle)
    assert r.suggestion == TS.reservation_enregistree(r.faits) and "deux personnes" in r.suggestion, r.suggestion
    m = await RR.modifier_reservation(salle.c, salle.a, r.faits["numero"], {"couverts": 3})
    assert m.suggestion == TS.reservation_modifiee(m.faits) and "trois personnes" in m.suggestion and "3" not in m.suggestion, m.suggestion
    a = await RR.annuler_reservation(salle.c, salle.a, r.faits["numero"])
    assert a.suggestion == TS.reservation_annulee(a.faits), a.suggestion
