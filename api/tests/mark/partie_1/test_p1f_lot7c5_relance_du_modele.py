"""[.mark] Lot 7b-C5 (décision d'Evan 25/11 8 h 45) : le code ne compose plus de phrase vers la voix ; le modèle muet sur un refus ou sur une question oubliée est RELANCÉ avec le fait.

Garde G2 : ce qui part à la voix est la phrase du modèle, une phrase du § 2 (le fait accompli, jusqu'à C6) ou la phrase réglée de l'agent. Un test par site qui composait un
texte (S1 silence, S2 relance retenue, S3 relance en échec, S4 cases illisibles, E2a rien n'a changé, E2b question donnée, E2c reprise), posé en xfail strict au commit 1 puis retiré par le commit qui ferme le site.
Aucun modèle, aucun appel : des fiches d'appel en mémoire.
"""

from __future__ import annotations

from types import SimpleNamespace

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


def _fiche(*, fait_bloquant: str | None = None, question: dict | None = None, rattrapage: bool = False) -> dict:
    """La fiche d'un appel dont l'étape montre la fiche ; au tour 1 : un fait bloquant, une question en attente."""
    fiche: dict = {CLE_DES_CASES_MONTREES: {"fiche": True}, CLE_DU_TOUR: 1, PF.CLE_DES_PAROLES: ["Une pizza au homard."]}
    dossier = P.du_dossier(fiche)
    if question:
        CONV.poser_question(dossier, question)
    if fait_bloquant:
        poser_le_fait_bloquant(fiche, 1, "commande", [{"statut_du_module": "INTROUVABLE", "manque": None, "faits": {"article": "pizza au homard"}}])
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


def test_e2c_une_reprise_ne_compose_pas_la_question_du_code():
    """Client « Pardon ? » : le modèle dit « Pas de souci. » sans question ; le code relance avec la question en attente, il ne la redit pas de sa voix."""
    retenue = _verificateur(_fiche(question=_question(), rattrapage=True)).controler("Pas de souci.")
    assert retenue is not None and retenue.a_dire is None


# --------------------------------------------------------------------------- commit 2 : le fait bloquant porte ses faits à côté du texte


async def test_c2_le_fait_bloquant_de_la_commande_range_ses_faits_a_cote_du_texte(essai_de):
    """Client « Deux reines livrées à Compiègne. » (hors zone) : les faits rangés sont ceux que le modèle reçoit (``refus_de_la_fiche``), le texte de secours n'y est plus (commit 9)."""
    from api.services.actions_communes.repli import CLE_FAIT_BLOQUANT, faits_du_fait_bloquant

    e = await essai_de("casa-italia")
    r = await e.tour("Deux reines normales, livrées au 8 rue Solférino à Compiègne", ajouter=[{"article": "pizza reine", "quantite": 2, "variante": "Normale"}],
                     mode_de_retrait="livraison", adresse="8 Rue Solférino", commune="Compiègne")
    assert r["faits"]["refus_de_la_fiche"], r
    assert faits_du_fait_bloquant(e.fiche_de_l_appel) == r["faits"]["refus_de_la_fiche"]
    assert "commande" in e.fiche_de_l_appel[CLE_FAIT_BLOQUANT]["faits"]


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
    poser_le_fait_bloquant(fiche, 1, "commande", [_refus_de_homard()])
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
    poser_le_fait_bloquant(fiche, 1, "commande", [refus])
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
    """Le plafond est celui du tour de la personne : un second silence du même tour ne relance plus, et ne laisse pas le tour muet (reprise R5) : la phrase réglée est dite."""
    fiche = _fiche_du_homard()
    await _tour_muet(fiche, [None])
    dit, consignes = await _tour_muet(fiche, [None])
    assert consignes == [], consignes
    assert dit == REGLEE, dit


def test_r5_sur_la_fiche_le_silence_ne_rend_jamais_none_meme_sans_rien_a_relancer():
    """Reprise R5 : le second silence du tour n'a ni consigne ni fait accompli : une retenue vide (``RepliqueVerifiee`` dit la phrase réglée), jamais ``None``."""
    fiche = _fiche_du_homard()
    v = _verificateur(fiche)
    assert v.controler_le_silence().consigne  # la première fois : la relance du fait
    seconde = v.controler_le_silence()
    assert seconde is not None and not seconde.consigne and not seconde.a_dire and seconde.outil is None, seconde


async def _avec_retenue(retenue, reponses: list):
    """Un flux de texte seul, ``retenue`` rendue par le contrôle ; ``reponses`` sont les relances. Rend (ce qui est dit, les retenues reçues par ``relancer``)."""
    recues: list = []

    async def flux():
        yield _morceau("Je lance la commande.")

    async def relancer(r):
        recues.append(r)
        return _reprise(reponses[len(recues) - 1])

    verifie = RepliqueVerifiee(flux(), lambda texte: retenue, relancer, None, None, None, lambda: REGLEE)
    return "".join(m.choices[0].delta.content or "" for m in [m async for m in verifie]), recues


async def test_r5_une_retenue_sans_consigne_ni_outil_dit_la_phrase_reglee_sans_requete_de_plus():
    from api.services.workflow.verite_des_actions import Retenue

    dit, recues = await _avec_retenue(Retenue("silence", "", ""), ["Un texte qui ne doit jamais partir."])
    assert dit == REGLEE and recues == [], (dit, recues)


async def test_r5_voisin_k8_l_outil_exige_garde_son_outil_et_sa_relance():
    """Le chemin de l'outil exigé (K8) : consigne vide mais ``outil`` : la requête part, avec l'outil, et la réponse de la relance est rendue."""
    from api.services.workflow.verite_des_actions import Retenue

    dit, recues = await _avec_retenue(Retenue("relance", "enregistrer", "", outil="enregistrer"), ["C'est noté."])
    assert dit == "C'est noté." and len(recues) == 1 and recues[0].outil == "enregistrer", (dit, recues)


async def test_r5_voisin_une_relance_retenue_apres_la_relance_du_fait_dit_la_phrase_reglee():
    """``_au_bout`` avec ``relance=True`` (la relance du fait est déjà faite) : consigne vide, rien à dire ; la phrase réglée, aucune requête de plus."""
    fiche = _fiche_du_homard()
    v = _verificateur(fiche)
    assert v.controler_le_silence().consigne  # la relance du fait de ce tour est prise
    retenue = v.controler_la_relance("Ça vous fera 15 euros.")
    assert retenue is not None and not retenue.consigne and not retenue.a_dire, retenue
    dit, consignes = await _tour_avec_texte(fiche, "Ça vous fera 15 euros.", ["C'est 15 euros."])
    assert dit == REGLEE and len(consignes) == 1, (dit, consignes)


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


async def test_r1_une_erreur_imprevue_a_la_relance_du_fait_dit_la_phrase_reglee_sans_lever():
    """Reprise R1 : la relance du fait est une requête comme la première ; une erreur imprévue (ici ``KeyError``) ne sort jamais du flux : la phrase réglée est dite."""
    fiche = _fiche_du_homard()
    verificateur = _verificateur(fiche)
    appels: list[str] = []

    async def flux():
        yield _morceau("Ça vous fera 15 euros.")

    async def relancer(retenue):
        appels.append(retenue.consigne)
        if len(appels) == 1:
            return _reprise("C'est 15 euros.")
        raise KeyError("consigne mal préparée")

    verifie = RepliqueVerifiee(flux(), verificateur.controler, relancer, None, verificateur.controler_la_relance,
                               lambda *a, **k: verificateur.controler_le_silence(None, **k), lambda: REGLEE)
    dit = "".join(m.choices[0].delta.content or "" for m in [m async for m in verifie])
    assert dit == REGLEE and len(appels) == 2, (dit, appels)


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


async def test_s3_la_relance_en_echec_ne_dit_plus_le_fait_accompli_et_garde_la_relance_du_tour():
    """Réplique retenue (chiffre), 429 sur la relance : décisions d'Evan 25/11 8 h 45 et 9 h 30 (P3), C5 § 2, coordinateur 26/11 2 h 05 (P3 tel quel) : reprise R1 de C6 : la phrase réglée (P3), jamais le fait accompli gardé au journal ; la relance du fait n'est pas consommée par ce repli."""
    fiche = _avec_fait_accompli(_fiche_du_homard())

    async def flux():
        yield _morceau("Ça vous fera 15 euros.")

    async def relance_429(_retenue):
        raise RuntimeError("429 Too Many Requests")

    verificateur = _verificateur(fiche)
    verifie = RepliqueVerifiee(flux(), verificateur.controler, relance_429, None, verificateur.controler_la_relance,
                               lambda *a, **k: verificateur.controler_le_silence(None, **k), lambda: REGLEE)
    dit = "".join(m.choices[0].delta.content or "" for m in [m async for m in verifie])
    assert dit == REGLEE, dit
    assert PAROLE.etat_du_tour(fiche).relance_du_fait is False


def test_s4_des_cases_illisibles_ne_disent_plus_le_fait_accompli():
    """décisions d'Evan 25/11 8 h 45 et 9 h 30 (P3), C5 § 2, coordinateur 26/11 2 h 05 (P3 tel quel) : reprise R1 de C6 : aucune requête possible, aucune suite réglée en attente : la phrase réglée, jamais le fait accompli gardé au journal."""
    moteur = SimpleNamespace(_gathered_context=_avec_fait_accompli(_fiche(fait_bloquant=HOMARD)))
    llm = SimpleNamespace(**{ATTRIBUT_PHRASE_DE_REPLI: lambda: REGLEE})
    assert AR.phrase_si_les_cases_sont_illisibles(moteur, llm) == REGLEE


def test_s4_des_cases_illisibles_disent_la_suite_reglee_deja_posee():
    """Reprise R1 de C6 : la suite réglée déjà posée (ici M108) part seule, par le même chemin que la relance ratée (``controler_le_silence(sans_relance=True)``)."""
    fiche = _avec_fait_accompli(_fiche())
    etat = PAROLE.etat_du_tour(fiche)
    etat.suffixe = "Puis-je faire autre chose pour vous ?"
    PAROLE.garder(fiche, etat)
    llm = SimpleNamespace(**{ATTRIBUT_PHRASE_DE_REPLI: lambda: REGLEE})
    assert AR.phrase_si_les_cases_sont_illisibles(SimpleNamespace(_gathered_context=fiche), llm) == "Puis-je faire autre chose pour vous ?"


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


# --------------------------------------------------------------------------- commit 8 : E2c, la reprise relance avec la question


async def test_e2c_mini_dialogue_pardon_le_modele_est_relance_avec_la_question_en_attente():
    """Client « Pardon ? » / avant : modèle « Pas de souci. » + code « Quelle taille pour la Regina ? » / après : le modèle, relancé avec l'objet de la question, dit « Pas de souci : la Regina, en moyenne ou en grande ? »."""
    bonne = "Pas de souci : la Regina, en moyenne ou en grande ?"
    dit, consignes = await _tour_avec_texte(_fiche(question=_question(), rattrapage=True), "Pas de souci.", [bonne])
    assert dit == bonne and len(consignes) == 1, (dit, consignes)
    assert '"article_en_question": "Regina"' in consignes[0] and QUESTION_DU_CODE not in consignes[0], consignes


async def test_e2c_une_seule_reprise_par_tour():
    """Le modèle redit « Pas de souci. » sans la question : sa phrase est dite seule (un plafond par tour), jamais la question du code."""
    dit, consignes = await _tour_avec_texte(_fiche(question=_question(), rattrapage=True), "Pas de souci.", ["Pas de souci."])
    assert dit == "Pas de souci." and len(consignes) == 1, (dit, consignes)


# --------------------------------------------------------------------------- commit 9 : le repli composé est retiré


NOMS_RETIRES = ("repli_dit_par_le_code", "_repli_sans_le_fait_bloquant", "_question_ou_manque", "phrase_du_fait_bloquant", "repli_sans_le_fait_bloquant_de", "reprise_apres_la_phrase",
                "phrase_du_fait_bloquant_de", "raison_du_fait_bloquant", "texte_du_manque", "panne_de_la_porte")


def test_c9_aucun_nom_du_repli_compose_ne_reste_dans_le_code():
    """Grep à zéro : ni la fonction, ni son appelant, ni le champ ``textes`` du fait bloquant ; ``TS.du_refus`` non plus (le refus de la réservation se lit par ``refuse_a_dire``)."""
    import re

    from api.outils import inventaire_rustines as I

    reste = []
    # reprise R3 : les textes qui décrivaient l'ancien repli (le texte de secours « lu » ou « dit » par le repli) sont faux depuis le commit 9
    for f in (I.RACINE_API / "services").rglob("*.py"):
        texte = f.read_text(encoding="utf-8")
        reste += [f"{f.name}: {m}" for m in ("lu par le repli", "que le repli dit", "n'est lu que par le repli") if m in texte]
    for dossier in ("services", "db", "routes", "tasks", "mcp_server"):
        for f in (I.RACINE_API / dossier).rglob("*.py"):
            texte = f.read_text(encoding="utf-8")
            reste += [f"{f.name}: {nom}" for nom in NOMS_RETIRES if re.search(rf"\b{nom}\b", texte)]
            reste += [f"{f.name}: du_refus" for _ in [0] if re.search(r"\bdef du_refus\b|\bTS\.du_refus\b", texte)]
    assert not reste, reste


def test_c9_le_manque_du_constat_est_une_valeur_fermee_jamais_une_phrase():
    """``Du.manque`` : la valeur fermée de ce qui manque (``Manque``, la liste de la réservation), lue par la relance ; jamais le texte du catalogue."""
    from api.services.commande.phrases_du_manque import valeur_du_manque

    fiche = _fiche()
    P.du_dossier(fiche)["mode"] = "emporter"
    assert valeur_du_manque(P.du_dossier(fiche)) == "les articles"


# --------------------------------------------------------------------------- commit 10 : l'identité d'une question est sa structure, plus son texte


def _variante(objet: str, texte: str = QUESTION_DU_CODE) -> dict:
    return {"id": "Q-1", "type": "variante", "texte": texte, "article_en_question": objet}


def test_c10_meme_texte_autre_objet_deux_questions():
    """Même numéro, même texte de secours, autre article : ce sont deux questions (avant : une seule, le texte les confondait)."""
    assert CONV.identite_de_la_question(_variante("Regina")) != CONV.identite_de_la_question(_variante("Margherita"))


def test_c10_texte_change_meme_objet_meme_question():
    """Le texte de secours disparaît en C7 : le changer ne crée pas une autre question."""
    assert CONV.identite_de_la_question(_variante("Regina")) == CONV.identite_de_la_question(_variante("Regina", "Une taille pour la Regina ?"))


def test_c10_ce_que_la_personne_vit_se_lit_sur_la_structure_de_la_question():
    from api.services.actions_communes import du as DU

    def vu(q):
        return DU.ce_qui_se_voit({"lignes": [], CONV.CLE: {CONV.CLE_QUESTION: q}})["question"]

    assert vu(_variante("Regina")) == vu(_variante("Regina", "Autre texte ?")) and vu(_variante("Regina")) != vu(_variante("Margherita"))


def test_c10_une_relecture_reposee_avec_un_autre_jeton_reste_une_autre_question():
    """C6 (décision d'Evan 25/11 9 h 30) : le modèle dit la relecture, son texte n'est plus au registre ; son identité est son jeton, neuf à chaque relecture posée."""
    relecture = {"id": "Q-2", "type": "relecture", "texte": "", "jeton": "a"}
    assert CONV.identite_de_la_question(relecture) != CONV.identite_de_la_question({**relecture, "jeton": "b"})
    assert CONV.identite_de_la_question(relecture) == CONV.identite_de_la_question({**relecture, "texte": "Un autre texte"})
