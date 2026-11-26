"""[.mark] Lot 7b-C6, commit 8 (décision d'Evan 25/11 9 h 30, § 8 bis ; P2 : le code vérifie personnes et heure ; Q2 = A) : les relectures de la réservation passent au modèle.

Avant : code « Je vous réserve pour quatre personnes, samedi 14 novembre à vingt heures, au nom de Paul. Je note ce numéro de téléphone pour vous joindre en cas de problème, c'est bon ? ».
Après : modèle « Samedi vingt heures pour quatre, au nom de Paul. » + code « Je note ce numéro de téléphone pour vous joindre en cas de problème, c'est bon ? » (seule question, à la fin).
La phrase du modèle doit dire les personnes et l'heure (barrière ``porte_les_chiffres``) : sans elles, il est relancé une fois. Un « oui » ne vaut accord que si la relecture a été DITE
(journal du dit, au jeton de la question) ; sinon la relecture se repose. Même geste pour le changement (« recap_modif ») et l'annulation. Vraie source, vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.mots_dits import numero_en_lettres
from api.services.phrases.catalogue import MOTIFS, NUMERO_AFFICHE_GARDE, NUMERO_DICTE_RELU
from api.services.reservation import porte as PORTE
from api.services.workflow import parole_de_la_fiche as PF
from api.services.workflow.etat_des_connecteurs import ATTRIBUT
from api.tests.mark.partie_1.porte_essai_reservation import EssaiReservation
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.partie_1.aides_de_la_reservation import salle  # noqa: F401

MOTS = "une table pour quatre samedi à vingt heures au nom de Paul"
QUESTION_DU_NUMERO_GARDE = MOTIFS[NUMERO_AFFICHE_GARDE].variantes_defaut[0]
RELUE = "Samedi vingt heures pour quatre, au nom de Paul."


def _textes(essai: EssaiReservation) -> dict:
    return dict(essai.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {})


def _dire(essai: EssaiReservation, retour: dict, phrase: str, relance: str | None = None) -> str | None:
    """Ce qui part à la voix quand le modèle écrit ``phrase`` avec la fiche, puis ``relance`` au second passage (``None`` : la même phrase), comme en production (étape de la réservation)."""
    fiche = essai.fiche_de_l_appel
    textes = _textes(essai)
    d = PF.decider_apres_la_fiche(fiche, retour, {"a_dire": phrase}, connecteur="reservation")
    fiche[PORTE.CLE_TEXTES_DU_CODE] = textes  # gardé pour les assertions
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


async def _jusqu_a_la_relecture(salle, monkeypatch, **plus) -> tuple[EssaiReservation, dict]:
    essai = EssaiReservation(salle, monkeypatch, **plus)
    essai.voix = False  # ce qui part à la voix est jugé ici, par la parole (``_dire``)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Paul")
    assert (r.get("question") or {}).get("type") == "recapitulatif", r
    return essai, r


async def test_la_relecture_rend_des_faits_le_code_ne_dit_que_la_question_du_numero_garde(salle, monkeypatch):
    essai, r = await _jusqu_a_la_relecture(salle, monkeypatch)
    textes = _textes(essai)
    assert not textes.get("avant"), textes  # le code ne relit plus la réservation
    assert textes.get("suffixe") == QUESTION_DU_NUMERO_GARDE, textes  # la question réglée du numéro gardé, seule question, à la fin (Q2 = A)
    assert textes.get("chiffres_exiges") == {"personnes": "4", "heure": "vingt heures"}, textes  # P2 : le code vérifie personnes et heure
    assert "Je vous réserve" not in str(r) and r["question"]["texte"] == "", r
    assert r["faits"]["personnes"] == 4 and r["faits"]["prenom"] == "Paul" and r["faits"]["heure"] == "vingt heures", r["faits"]


async def test_la_phrase_du_modele_part_suivie_de_la_question_puis_le_oui_reserve(salle, monkeypatch):
    """Client « Une table pour quatre samedi à vingt heures au nom de Paul. » / modèle « Samedi vingt heures pour quatre, au nom de Paul. » + code « Je note ce numéro …, c'est bon ? »
    / « Oui. » → réservé."""
    essai, r = await _jusqu_a_la_relecture(salle, monkeypatch)
    assert _dire(essai, r, RELUE) == f"{RELUE} {QUESTION_DU_NUMERO_GARDE}"
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    assert await essai.nombre_de_reservations() == 1


async def test_une_relecture_sans_l_heure_est_relancee_et_jamais_dite(salle, monkeypatch):
    """P2 : « Pour quatre, au nom de Paul. » ne dit pas l'heure : relancée une fois ; la relance qui dit l'heure part, suivie de la question du code."""
    essai, r = await _jusqu_a_la_relecture(salle, monkeypatch)
    assert _dire(essai, r, "Pour quatre, au nom de Paul.", relance=RELUE) == f"{RELUE} {QUESTION_DU_NUMERO_GARDE}"


async def test_un_oui_sans_relecture_dite_ne_reserve_pas_la_relecture_se_repose(salle, monkeypatch):
    """La relance a échoué (ni les personnes ni l'heure dites) : seule la question du code est partie. Le « oui » n'enregistre rien ; la relecture est reposée (autre jeton)."""
    essai, r = await _jusqu_a_la_relecture(salle, monkeypatch)
    assert _dire(essai, r, "C'est noté.", relance="Très bien.") == QUESTION_DU_NUMERO_GARDE  # jamais un tour muet
    jeton = CONV.question_de(essai.etat)["jeton"]
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] != "ENREGISTREE" and await essai.nombre_de_reservations() == 0, r
    reposee = CONV.question_de(essai.etat)
    assert reposee["type"] == "recapitulatif" and reposee["jeton"] != jeton, reposee
    assert _textes(essai).get("chiffres_exiges") == {"personnes": "4", "heure": "vingt heures"}


async def test_numero_dicte_le_code_le_relit_avec_la_question_apres_la_phrase_du_modele(salle, monkeypatch):
    """Numéro masqué, dicté : modèle « … » + code « Je note le zéro six …, c'est bon ? » (motif réglé ``numero_dicte_relu`` : le numéro, puis la question, à la fin)."""
    essai = EssaiReservation(salle, monkeypatch, appelant=None)
    essai.voix = False
    await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Paul")
    r = await essai.tour("au zéro six dix vingt trente quarante", telephone="0610203040")
    assert (r.get("question") or {}).get("type") == "recapitulatif", r
    attendue = MOTIFS[NUMERO_DICTE_RELU].variantes_defaut[0].replace("{numero}", numero_en_lettres("+33610203040"))
    assert _textes(essai).get("suffixe") == attendue, _textes(essai)
    assert _dire(essai, r, RELUE) == f"{RELUE} {attendue}"


async def _reservee(salle, monkeypatch) -> EssaiReservation:
    essai = EssaiReservation(salle, monkeypatch)
    r = await essai.tour(MOTS, personnes=4, jour="samedi", heure="vingt heures", nom="Paul")
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ENREGISTREE", r
    essai.voix = False
    return essai


async def test_le_changement_est_relu_par_le_modele_avec_les_personnes_exigees(salle, monkeypatch):
    """Client « Finalement on sera cinq. » / avant, code « Je change votre réservation : cinq personnes. C'est bon ? » / après, modèle « Cinq personnes alors, je change ? »."""
    essai = await _reservee(salle, monkeypatch)
    r = await essai.tour("finalement on sera cinq", personnes=5)
    assert (r.get("question") or {}).get("type") == "recap_modif", r
    textes = _textes(essai)
    assert not textes.get("avant") and not textes.get("suffixe"), textes
    assert textes.get("chiffres_exiges") == {"personnes": "5"}, textes
    assert r["faits"]["ce_qui_change"] == {"personnes": 5}, r["faits"]
    phrase = "Cinq personnes alors, je change ?"
    assert _dire(essai, r, phrase) == phrase
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["resultats"][-1]["statut_du_module"] == "OK", r
    assert await essai.salle.c.fetchval("SELECT couverts FROM mark.resto_reservation") == 5


async def test_un_oui_au_changement_sans_relecture_dite_ne_change_rien(salle, monkeypatch):
    essai = await _reservee(salle, monkeypatch)
    r = await essai.tour("finalement on sera cinq", personnes=5)
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert (CONV.question_de(essai.etat) or {}).get("type") == "recap_modif", r  # reposée
    assert await essai.salle.c.fetchval("SELECT couverts FROM mark.resto_reservation") == 4


async def test_l_annulation_est_demandee_par_le_modele_avec_le_moment_et_les_personnes(salle, monkeypatch):
    """Client « Je voudrais annuler. » / avant, code « Je peux aussi la déplacer. Vous voulez annuler la réservation samedi … pour quatre personnes ? » / après, modèle
    « Je peux aussi la déplacer. Vous voulez annuler samedi vingt heures pour quatre ? » (la question à la fin, reprise R2)."""
    essai = await _reservee(salle, monkeypatch)
    r = await essai.tour("je voudrais annuler", annuler_une_reservation_enregistree=True)
    assert (r.get("question") or {}).get("type") == "annulation", r
    textes = _textes(essai)
    assert not textes.get("avant"), textes
    assert textes.get("chiffres_exiges") == {"personnes": "4", "heure": "vingt heures"}, textes
    assert "déplacer" in str(r.get("a_faire")), r.get("a_faire")  # B5 : le déplacement est proposé (consigne), plus par une phrase du code
    sans_heure = "Vous voulez vraiment annuler ?"
    # reprise R2 de C6 (ordre de « C6 révisée » : la question est toujours la dernière) : la phrase qui finit sur une affirmation est relancée
    bonne = "Je peux aussi la déplacer. Vous voulez annuler samedi vingt heures pour quatre ?"
    assert _dire(essai, r, sans_heure, relance=bonne) == bonne
    r = await essai.tour("oui", reponse={"question_id": r["question"]["id"], "sens": "accepte"})
    assert r["statut"] == "ANNULEE", r


def test_la_reservation_n_a_plus_de_question_dite_par_le_code():
    from api.services.actions_communes.enveloppe import QUESTIONS_DITES_PAR_LE_CODE

    assert QUESTIONS_DITES_PAR_LE_CODE == frozenset({"numero_dicte"})

