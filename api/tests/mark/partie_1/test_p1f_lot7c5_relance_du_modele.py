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


@G2
def test_s1_le_silence_ne_dit_pas_le_texte_du_refus():
    """Client « Une pizza au homard. », le modèle ne rend rien : le code relance avec le fait, il ne dit pas « Nous n'avons pas de pizza au homard. »."""
    retenue = _verificateur(_fiche(fait_bloquant=HOMARD)).controler_le_silence()
    assert retenue is not None and retenue.a_dire is None and retenue.consigne


@G2
def test_s2_une_relance_retenue_ne_dit_pas_le_texte_du_refus():
    """La relance du modèle porte un chiffre que rien n'autorise : retenue ; le code ne compose pas le refus à sa place."""
    retenue = _verificateur(_fiche(fait_bloquant=HOMARD)).controler_la_relance("Ça vous fera 15 euros.")
    assert retenue is not None and retenue.a_dire is None


@G2
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


@G2
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


@G2
def test_e2a_rien_n_a_change_ne_complete_pas_la_phrase_par_la_question_du_code():
    """Client « Et un coca. », la fiche ne change rien, une question attend : le modèle repasse ; le code n'ajoute pas « Quelle taille pour la Regina ? »."""
    decision = TABLE.decider(_entrees(_fiche(question=_question()), "C'est noté."))
    assert decision.a_dire in (None, "C'est noté."), decision


@G2
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
