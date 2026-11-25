"""[.mark] Lot 7b-C5 (décision d'Evan 25/11 8 h 45) : le code ne compose plus de phrase vers la voix ; le modèle muet sur un refus ou sur une question oubliée est RELANCÉ avec le fait.

Garde G2 : ce qui part à la voix est la phrase du modèle, une phrase du § 2 (le fait accompli, jusqu'à C6) ou la phrase réglée de l'agent. Un xfail strict par site qui composait un
texte (S1 silence, S2 relance retenue, S3 relance en échec, S4 cases illisibles, E2a rien n'a changé, E2b question donnée, E2c reprise) ; chaque commit qui ferme un site retire son xfail.
Aucun modèle, aucun appel : des fiches d'appel en mémoire.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes import table_de_parole as TABLE
from api.services.actions_communes.repli import CLE_DU_TOUR, poser_le_fait_bloquant
from api.services.commande import panier as P
from api.services.pipecat import avant_la_requete as AR
from api.services.pipecat.reponse_avalee import ATTRIBUT_PHRASE_DE_REPLI, RepliqueVerifiee
from api.services.workflow import parole_de_la_fiche as PF
from api.services.workflow.cases_selon_l_etat import CLE_DES_CASES_MONTREES

HOMARD = "Nous n'avons pas de pizza au homard."
QUESTION_DU_CODE = "Quelle taille pour la Regina ?"
REGLEE = "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?"
G2 = pytest.mark.xfail(strict=True, raises=AssertionError, reason="C5 : ce site compose encore une phrase (garde G2)")


def _fiche(*, fait_bloquant: str | None = None, question: dict | None = None, rattrapage: bool = False) -> dict:
    """La fiche d'un appel dont l'étape montre la fiche ; au tour 1 : un fait bloquant, une question en attente."""
    fiche: dict = {CLE_DES_CASES_MONTREES: {"fiche": True}, CLE_DU_TOUR: 1, PF.CLE_DES_PAROLES: ["Une pizza au homard."]}
    dossier = P.du_dossier(fiche)
    if question:
        CONV.poser_question(dossier, question)
    if fait_bloquant:
        poser_le_fait_bloquant(fiche, 1, fait_bloquant, "commande")
    if rattrapage:
        etat = PAROLE.etat_du_tour(fiche)
        etat.rattrapage_a_joue = True
        PAROLE.garder(fiche, etat)
    return fiche


def _verificateur(fiche: dict) -> PF.VerificateurDeLaFiche:
    return PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=fiche))


def _question() -> dict:
    return {"id": "Q-1", "type": "variante", "texte": QUESTION_DU_CODE, "nee_au_tour": 0, "article_en_question": "Regina"}


def _morceau(texte):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=texte, tool_calls=None), finish_reason=None)], usage=None)


def test_s1_le_silence_ne_dit_pas_le_texte_du_refus():
    """Client « Une pizza au homard. », le modèle ne rend rien : le code relance avec le fait, il ne dit pas « Nous n'avons pas de pizza au homard. »."""
    retenue = _verificateur(_fiche(fait_bloquant=HOMARD)).controler_le_silence()
    assert retenue is not None and retenue.a_dire is None and retenue.consigne


def test_s2_une_relance_retenue_ne_dit_pas_le_texte_du_refus():
    """La relance du modèle porte un chiffre que rien n'autorise : retenue ; le code ne compose pas le refus à sa place."""
    retenue = _verificateur(_fiche(fait_bloquant=HOMARD)).controler_la_relance("Ça vous fera 15 euros.")
    assert retenue is not None and retenue.a_dire is None


async def test_s3_une_relance_en_echec_dit_la_phrase_reglee_pas_le_refus():
    """429 sur la relance d'une réplique retenue : la phrase réglée de l'agent (P3), jamais le texte du refus composé par le code."""
    verificateur = _verificateur(_fiche(fait_bloquant=HOMARD))

    async def flux():
        yield _morceau("Ça vous fera 15 euros.")

    async def relance_429(_retenue):
        raise RuntimeError("429 Too Many Requests")

    verifie = RepliqueVerifiee(flux(), verificateur.controler, relance_429, None, verificateur.controler_la_relance,
                               lambda *a, **k: verificateur.controler_le_silence(None, **k), lambda: REGLEE)
    dit = "".join(m.choices[0].delta.content or "" for m in [m async for m in verifie])
    assert dit == REGLEE, dit


def test_s4_des_cases_illisibles_disent_la_phrase_reglee_pas_le_refus():
    """Aucune requête possible : le fait accompli s'il y en a un, sinon la phrase réglée ; jamais le refus ni la question composés par le code."""
    moteur = SimpleNamespace(_gathered_context=_fiche(fait_bloquant=HOMARD, question=_question()))
    llm = SimpleNamespace(**{ATTRIBUT_PHRASE_DE_REPLI: lambda: REGLEE})
    assert AR.phrase_si_les_cases_sont_illisibles(moteur, llm) == REGLEE


def _entrees(fiche: dict, phrase: str, *, question_donnee: bool = False):
    etat = PAROLE.etat_du_tour(fiche)
    etat.rattrapage_a_joue = True
    p = P.du_dossier(fiche)
    q = CONV.question_de(p)
    if question_donnee and q:
        etat.question_donnee = q["id"]
        q["nee_au_tour"] = etat.tour
    retour = {"statut": "FAIT", "resultats": [], "faits": {}, "rien_change": not question_donnee}
    return TABLE.entrees_du_retour(retour, phrase, etat, [], p, {}, True, None)


def test_e2a_rien_n_a_change_ne_complete_pas_la_phrase_par_la_question_du_code():
    """Client « Et un coca. », la fiche ne change rien, une question attend : le modèle repasse ; le code n'ajoute pas « Quelle taille pour la Regina ? »."""
    decision = TABLE.decider(_entrees(_fiche(question=_question()), "C'est noté."))
    assert decision.a_dire in (None, "C'est noté."), decision


def test_e2b_une_question_deja_donnee_ne_complete_pas_la_phrase_par_la_question_du_code():
    decision = TABLE.decider(_entrees(_fiche(question=_question()), "C'est noté.", question_donnee=True))
    assert decision.a_dire in (None, "C'est noté."), decision


@G2
def test_e2c_une_reprise_ne_compose_pas_la_question_du_code():
    """Client « Pardon ? » : le modèle dit « Pas de souci. » sans question ; le code relance avec la question en attente, il ne la redit pas de sa voix."""
    retenue = _verificateur(_fiche(question=_question(), rattrapage=True)).controler("Pas de souci.")
    assert retenue is not None and retenue.a_dire is None


# --------------------------------------------------------------------------- commit 2 : le fait bloquant porte ses faits à côté du texte


async def test_c2_le_fait_bloquant_de_la_commande_range_ses_faits_a_cote_du_texte(essai_de):
    """Client « Deux reines livrées à Compiègne. » (hors zone) : les faits rangés sont ceux que le modèle reçoit (``refus_de_la_fiche``), le texte reste (comportement égal)."""
    from api.services.actions_communes.repli import CLE_FAIT_BLOQUANT, faits_du_fait_bloquant, phrase_du_fait_bloquant

    e = await essai_de("casa-italia")
    r = await e.tour("Deux reines normales, livrées au 8 rue Solférino à Compiègne", ajouter=[{"article": "pizza reine", "quantite": 2, "variante": "Normale"}],
                     mode_de_retrait="livraison", adresse="8 Rue Solférino", commune="Compiègne")
    assert r["faits"]["refus_de_la_fiche"], r
    assert faits_du_fait_bloquant(e.fiche_de_l_appel) == r["faits"]["refus_de_la_fiche"]
    assert phrase_du_fait_bloquant(e.fiche_de_l_appel) and "commande" in e.fiche_de_l_appel[CLE_FAIT_BLOQUANT]["faits"]


async def test_c2_une_suggestion_vide_garde_la_consigne_du_refus(essai_de, monkeypatch):
    """Sans texte de secours (``suggestion`` vide), la consigne « dis les refus » reste : elle se lit sur les refusants, plus sur le texte."""
    import dataclasses

    from api.services.commande import porte
    from api.services.commande.porte import A_FAIRE_DES_REFUS_A_DIRE

    avant = porte.refusants_de_la_fiche
    monkeypatch.setattr(porte, "refusants_de_la_fiche", lambda f: [dataclasses.replace(r, suggestion="") for r in avant(f)])
    e = await essai_de("casa-italia")
    r = await e.tour("Deux reines normales, livrées au 8 rue Solférino à Compiègne", ajouter=[{"article": "pizza reine", "quantite": 2, "variante": "Normale"}],
                     mode_de_retrait="livraison", adresse="8 Rue Solférino", commune="Compiègne")
    assert A_FAIRE_DES_REFUS_A_DIRE in str(r.get("a_faire")), r


# --------------------------------------------------------------------------- commit 3 : la consigne de relance, une fois par tour


def _faits_de_la_consigne(consigne: str) -> dict:
    import json

    return json.loads(consigne[consigne.index("{"):])


def _refus_de_homard() -> dict:
    return {"statut_du_module": "HORS_CARTE", "manque": None, "faits": {"article": "pizza au homard", "plus_proches": ["Margherita", "Regina"]}}


def test_c3_la_consigne_porte_les_refus_et_la_question_en_faits_jamais_en_phrases():
    """Client « Une pizza au homard. » : la consigne dit le refus (faits) puis la question due (objet), sans le texte de secours ni le texte de la question."""
    from api.services.actions_communes.repli import consigne_de_relance

    fiche = _fiche(question=_question())
    poser_le_fait_bloquant(fiche, 1, HOMARD, "commande", [_refus_de_homard()])
    consigne = consigne_de_relance(P.du_dossier(fiche), fiche, PAROLE.etat_du_tour(fiche))
    assert consigne and HOMARD not in consigne and QUESTION_DU_CODE not in consigne, consigne
    faits = _faits_de_la_consigne(consigne)
    assert faits["a_dire"] == [_refus_de_homard()]
    assert faits["puis"] == {"question": {"id": "Q-1", "type": "variante", "article_en_question": "Regina"}}


def test_c3_sans_question_la_consigne_porte_ce_qui_manque_en_valeur_fermee():
    from api.services.actions_communes.repli import consigne_de_relance

    fiche = _fiche()
    P.du_dossier(fiche)["mode"] = "emporter"
    consigne = consigne_de_relance(P.du_dossier(fiche), fiche, PAROLE.etat_du_tour(fiche))
    assert consigne and _faits_de_la_consigne(consigne) == {"puis": {"manque": "les articles"}}, consigne


def test_c3_une_seule_relance_du_fait_par_tour_de_la_personne():
    """Au deuxième appel du même tour : ``None`` ; la personne reparle : le compteur repart."""
    from api.services.actions_communes.repli import consigne_de_relance

    fiche = _fiche(fait_bloquant=HOMARD)
    etat = PAROLE.etat_du_tour(fiche)
    assert consigne_de_relance(P.du_dossier(fiche), fiche, etat) is not None
    assert consigne_de_relance(P.du_dossier(fiche), fiche, etat) is None
    PAROLE.garder(fiche, etat)
    assert PAROLE.etat_du_tour(fiche).relance_du_fait is True
    fiche[CLE_DU_TOUR] = 2
    assert PAROLE.etat_du_tour(fiche).relance_du_fait is False


def test_c3_rien_a_dire_rien_a_relancer():
    """Un connecteur qui ne manque de rien (le service), sans refus ni question : aucune relance, l'état n'est pas touché."""
    from api.services.actions_communes.repli import consigne_de_relance

    fiche = _fiche()
    etat = PAROLE.etat_du_tour(fiche)
    sans_manque = SimpleNamespace(valeur_du_manque=lambda _dossier, _fiche: None)
    assert consigne_de_relance(P.du_dossier(fiche), fiche, etat, sans_manque) is None and etat.relance_du_fait is False


# --------------------------------------------------------------------------- commit 4 : S1, le silence relance avec le fait


def _reprise(texte: str | None):
    message = SimpleNamespace(content=texte, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=None)


async def _tour_muet(fiche: dict, reponses: list):
    """Le modèle ne rend rien ; ``reponses`` sont ses relances successives. Rend (ce qui est dit, les consignes reçues)."""
    verificateur = _verificateur(fiche)
    consignes: list[str] = []

    async def flux():
        return
        yield  # pragma: no cover

    async def relancer(retenue):
        consignes.append(retenue.consigne)
        return _reprise(reponses[len(consignes) - 1])

    verifie = RepliqueVerifiee(flux(), verificateur.controler, relancer, None, verificateur.controler_la_relance,
                               lambda *a, **k: verificateur.controler_le_silence(None, **k), lambda: REGLEE)
    return "".join(m.choices[0].delta.content or "" for m in [m async for m in verifie]), consignes


def _fiche_du_homard() -> dict:
    fiche = _fiche()
    refus = {"statut_du_module": "INTROUVABLE", "manque": None, "faits": {"article": "pizza au homard", "plus_proches": ["Margherita", "Regina"]}}
    poser_le_fait_bloquant(fiche, 1, HOMARD, "commande", [refus])
    etat = PAROLE.etat_du_tour(fiche)
    etat.faits_du_refus.append(refus)  # ce que la fiche a donné au modèle : ses valeurs passent la barrière des chiffres (« Regina »)
    PAROLE.garder(fiche, etat)
    return fiche


async def test_s1_mini_dialogue_homard_le_modele_muet_est_relance_avec_le_refus():
    """Client « Une pizza au homard. » / modèle muet / avant : code « Nous n'avons pas de pizza au homard. » / après : le modèle, relancé avec le refus, dit « On n'a pas de homard ; une Margherita ou une Regina ? »."""
    dit, consignes = await _tour_muet(_fiche_du_homard(), ["On n'a pas de homard ; une Margherita ou une Regina ?"])
    assert dit == "On n'a pas de homard ; une Margherita ou une Regina ?", dit
    assert len(consignes) == 1 and "INTROUVABLE" in consignes[0] and HOMARD not in consignes[0], consignes


async def test_s1_la_relance_muette_dit_la_phrase_reglee_sans_second_essai():
    """Muet, relance muette : la phrase réglée de l'agent (P3) ; une seule relance du fait."""
    dit, consignes = await _tour_muet(_fiche_du_homard(), [None, None])
    assert dit == REGLEE and len(consignes) == 1, (dit, consignes)


async def test_s1_deux_silences_dans_le_meme_tour_une_relance():
    """Le plafond est celui du tour de la personne : un second silence du même tour ne relance plus."""
    fiche = _fiche_du_homard()
    await _tour_muet(fiche, [None])
    _, consignes = await _tour_muet(fiche, [None])
    assert consignes == [], consignes


# --------------------------------------------------------------------------- commit 5 : S2, la relance retenue relance avec le fait


async def _tour_avec_texte(fiche: dict, texte: str, reponses: list):
    """Le modèle dit ``texte`` (sans outil) ; ``reponses`` sont ses relances successives. Rend (ce qui est dit, les consignes reçues)."""
    verificateur = _verificateur(fiche)
    consignes: list[str] = []

    async def flux():
        yield _morceau(texte)

    async def relancer(retenue):
        consignes.append(retenue.consigne)
        return _reprise(reponses[len(consignes) - 1])

    verifie = RepliqueVerifiee(flux(), verificateur.controler, relancer, None, verificateur.controler_la_relance,
                               lambda *a, **k: verificateur.controler_le_silence(None, **k), lambda: REGLEE)
    return "".join(m.choices[0].delta.content or "" for m in [m async for m in verifie]), consignes


async def test_s2_trois_retenues_deux_relances_au_plus_et_jamais_un_texte_de_secours():
    """Client « Une pizza au homard. » / le modèle répond trois fois « 15 euros » : deux relances au plus, la seconde porte le fait ; ensuite la phrase réglée, jamais le refus composé par le code."""
    dit, consignes = await _tour_avec_texte(_fiche_du_homard(), "Ça vous fera 15 euros.", ["C'est 15 euros.", "Oui, 15 euros."])
    assert dit == REGLEE and len(consignes) == 2, (dit, consignes)
    assert "INTROUVABLE" in consignes[1] and HOMARD not in consignes[1], consignes


async def test_s2_mini_dialogue_la_relance_du_fait_repare_la_reponse():
    """Hors zone : avant, le code disait « Nous ne livrons pas … À emporter ? » ; après, le modèle relancé avec le refus le dit avec ses mots."""
    bonne = "Désolé, on ne livre pas là-bas ; vous préférez venir la chercher ?"
    dit, consignes = await _tour_avec_texte(_fiche_du_homard(), "Ça vous fera 15 euros.", ["C'est 15 euros.", bonne])
    assert dit == bonne and len(consignes) == 2, (dit, consignes)


# --------------------------------------------------------------------------- commit 6 : S3 et S4, l'échec dit le fait accompli ou la phrase réglée


def _avec_fait_accompli(fiche: dict) -> dict:
    from api.services.actions_communes import journal_du_dit as J

    J.dire_le_fait(P.du_dossier(fiche), "Votre commande est enregistrée.", 1)
    return fiche


async def test_s3_la_relance_en_echec_dit_le_fait_accompli_et_garde_la_relance_du_tour():
    """Réplique retenue (chiffre), 429 sur la relance : le fait accompli que le code a dit (§ 2), pas la phrase réglée ; la relance du fait n'est pas consommée par ce repli."""
    fiche = _avec_fait_accompli(_fiche_du_homard())

    async def flux():
        yield _morceau("Ça vous fera 15 euros.")

    async def relance_429(_retenue):
        raise RuntimeError("429 Too Many Requests")

    verificateur = _verificateur(fiche)
    verifie = RepliqueVerifiee(flux(), verificateur.controler, relance_429, None, verificateur.controler_la_relance,
                               lambda *a, **k: verificateur.controler_le_silence(None, **k), lambda: REGLEE)
    dit = "".join(m.choices[0].delta.content or "" for m in [m async for m in verifie])
    assert dit == "Votre commande est enregistrée.", dit
    assert PAROLE.etat_du_tour(fiche).relance_du_fait is False


def test_s4_des_cases_illisibles_disent_le_fait_accompli_s_il_y_en_a_un():
    moteur = SimpleNamespace(_gathered_context=_avec_fait_accompli(_fiche(fait_bloquant=HOMARD)))
    llm = SimpleNamespace(**{ATTRIBUT_PHRASE_DE_REPLI: lambda: REGLEE})
    assert AR.phrase_si_les_cases_sont_illisibles(moteur, llm) == "Votre commande est enregistrée."


# --------------------------------------------------------------------------- commit 7 : E2a et E2b, la table relance au lieu de compléter


def _entrees_du_manque(fiche: dict, phrase: str):
    from api.services.actions_communes import du as DU

    etat = PAROLE.etat_du_tour(fiche)
    etat.rattrapage_a_joue = True
    retour = {"statut": "FAIT", "resultats": [], "faits": {}, "rien_change": True, DU.CLE_DU: {"manque": "les articles"}}
    return TABLE.entrees_du_retour(retour, phrase, etat, [], P.du_dossier(fiche), {}, True, None)


def test_e2a_un_manque_du_donne_un_second_passage_une_fois_puis_la_phrase_seule():
    """Client « Et un coca. » / avant : modèle « C'est noté. » + code « Qu'est-ce que je vous mets ? » / après : le modèle repasse (« Un coca, c'est noté ; autre chose ? »), une fois ; ensuite sa phrase seule."""
    e = _entrees_du_manque(_fiche(), "C'est noté.")
    assert TABLE.decider(e).mode == PAROLE.SECOND_PASSAGE and e.etat.relance_du_fait
    decision = TABLE.decider(e)
    assert decision.mode == PAROLE.A_DIRE_SEUL and decision.a_dire == "C'est noté.", decision


def test_e2a_une_phrase_qui_pose_une_question_est_dite_seule():
    e = _entrees_du_manque(_fiche(), "C'est noté ; autre chose ?")
    decision = TABLE.decider(e)
    assert decision.mode == PAROLE.A_DIRE_SEUL and decision.a_dire == "C'est noté ; autre chose ?" and not e.etat.relance_du_fait, decision


def test_e2b_le_prix_a_dire_apres_la_phrase_survit_au_second_passage():
    e = _entrees(_fiche(question=_question()), "C'est noté.", question_donnee=True)
    e.suffixe_avant = "Cela fait deux euros."
    assert TABLE.decider(e).mode == PAROLE.SECOND_PASSAGE and e.etat.suffixe == "Cela fait deux euros."
