"""[.mark] Lot 7b-C6, reprise R1 de l'audit (décisions d'Evan 25/11 8 h 45 et 9 h 30, P3) : quand la relance du modèle échoue, le code ne dit que la suite réglée déjà posée
(les motifs de ``PHRASES_DU_CODE`` : numéro, rendu, total après changement, M108), sinon la phrase réglée « pas compris » (P3). Le fait accompli (texte de secours) n'est gardé qu'au
journal, jamais dit à la voix.

Garde G3 qui joue la voix : la vraie porte, la vraie parole et ``RepliqueVerifiee`` (la relance en 429), sans modèle.
Avant : Client « Mettez-en deux. » / code « C'est changé : votre commande fait maintenant … Elle fait maintenant … Puis-je faire autre chose pour vous ? ».
Après : code « Elle fait maintenant … Puis-je faire autre chose pour vous ? ».
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import parole as PAROLE
from api.services.commande import porte as PORTE
from api.services.mots_dits import montant_en_lettres
from api.services.pipecat.reponse_avalee import RepliqueVerifiee
from api.services.phrases.catalogue import REPONSE_PERDUE
from api.services.workflow import parole_de_la_fiche as PF

from .aides_de_la_commande import a_emporter, jusqu_a_l_enregistrement, premier_article, refuser_la_proposition

REGLEE = "Pardon, je n'ai pas bien saisi. Vous pouvez répéter ?"


def _morceau(texte):
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=texte, tool_calls=None), finish_reason=None)], usage=None)


async def _voix_apres_la_fiche(e, r, phrase: str) -> tuple[str, str]:
    """Le modèle écrit ``phrase`` avec la fiche ; jetée, il repasse et redit ``phrase`` ; toute relance du fait tombe en 429. Rend (ce qui part à la voix, la suite réglée posée par la porte)."""
    suite = str((e.fiche_de_l_appel.get(PORTE.CLE_TEXTES_DU_CODE) or {}).get("suffixe") or "")
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": phrase})
    if d.mode == PAROLE.A_DIRE_SEUL:
        return str(d.a_dire), suite
    verificateur = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))

    async def flux():
        yield _morceau(phrase)

    async def relance_429(_retenue):
        raise RuntimeError("429 Too Many Requests")

    verifie = RepliqueVerifiee(flux(), verificateur.controler, relance_429, None, verificateur.controler_la_relance,
                               lambda *a, **k: verificateur.controler_le_silence(None, **k), lambda: REGLEE)
    return "".join(m.choices[0].delta.content or "" for m in [m async for m in verifie]), suite


async def _enregistree(essai_de):
    e = await essai_de("casa-italia")
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    r = await jusqu_a_l_enregistrement(e)
    return e, r


async def test_confirmation_relance_ratee_seule_la_suite_reglee_part(essai_de):
    """Client « Oui, c'est bon. » / modèle « C'est enregistré. » (sans l'heure exigée), relance en 429 / code : la suite réglée seule (M108), jamais « Votre commande est enregistrée… »."""
    e, r = await _enregistree(essai_de)
    dit, suite = await _voix_apres_la_fiche(e, r, "C'est enregistré.")
    assert (J.fait_accompli(e.p) or {}).get("fait") == "enregistree" and "est enregistrée" not in dit, dit  # le fait gardé au journal en faits (B9), jamais redit par le code (reprise R1 de C6)
    assert dit == f"C'est enregistré. {suite}", (dit, suite)  # PE-2 Q4 (BILAN:270) : la confirmation réglée précède la suite ; avant : la suite seule


async def test_changement_relance_ratee_le_total_n_est_dit_qu_une_fois(essai_de):
    """Client « Mettez-en deux. » / modèle « C'est changé, ça fait {total}. » (le total est au code), relance en 429 / code « Elle fait maintenant … Puis-je … ? », le total une seule fois."""
    e, _ = await _enregistree(essai_de)
    r = await e.tour("finalement mettez-en deux", changer_quantite=[{"ligne": e.p["lignes"][0]["n"], "quantite": 2}])
    total = montant_en_lettres(e.p["enregistree"]["total"])
    dit, suite = await _voix_apres_la_fiche(e, r, f"C'est changé, ça fait {total}.")
    assert (J.fait_accompli(e.p) or {}).get("fait") == "changee" and "C'est changé" not in dit, dit  # le fait gardé au journal en faits (B9), jamais redit par le code (reprise R1 de C6)
    assert suite and dit == suite and dit.count(total) == 1, (dit, suite)


async def test_annulation_relance_ratee_la_phrase_reglee_pas_compris(essai_de):
    """Client « Oui, annulez. » / modèle « C'est annulé, vos 12 euros. » (chiffre faux), relance en 429 / code : rien n'est réglé après l'annulation, donc P3 « pas compris »."""
    e, _ = await _enregistree(essai_de)
    await e.tour("annulez ma commande", annuler_une_commande_enregistree=True)
    q = CONV.question_de(e.p)
    r = await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    dit, suite = await _voix_apres_la_fiche(e, r, "C'est annulé, vos 12 euros.")
    assert not suite and dit == REGLEE, (dit, suite)


async def test_fiche_vide_apres_l_enregistrement_la_relance_ratee_dit_p3(essai_de):
    """Client « Ah merci. » / fiche vide deux fois / avant (R1 de C6) : modèle « Avec plaisir. » seul ; T12 (coordinateur 26/11 10 h 45) : la seconde fiche vide était une relance ratée,
    P3 ; PE-2 Q3 (point d'étape du 26/11, BILAN:271) : rien n'est dû, la fiche est vide : la phrase du modèle est dite seule (« Avec plaisir. »)."""
    e, _ = await _enregistree(essai_de)
    r = await e.tour("ah merci")
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "Avec plaisir."})
    r2 = await e.fiche()
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r2, {"a_dire": "Avec plaisir."})
    assert (d.mode, d.a_dire, d.motif) == (PAROLE.A_DIRE_SEUL, "Avec plaisir.", "fait"), d


def _etat_avec_la_phrase_reglee() -> PAROLE.EtatDuTour:
    return PAROLE.EtatDuTour(fiches=1, relance_du_fait=True, rattrapage_a_joue=True, rattrapage_refus_joue=True,
                             suffixe="Puis-je faire autre chose pour vous ?", ancre="Q-3", exiges={})


def test_mineur_tranche_la_phrase_reglee_dite_emporte_son_ancre():
    """Mineur (2) de l'audit de la tranche : la phrase réglée partie à la voix (après la phrase du modèle, ou seule après une relance ratée) ne laisse pas son ancre (C7 a) derrière elle."""
    etat = _etat_avec_la_phrase_reglee()
    assert PAROLE.avec_le_suffixe("D'accord.", etat) == "D'accord. Puis-je faire autre chose pour vous ?" and (etat.suffixe, etat.ancre) == (None, None), etat
    etat = _etat_avec_la_phrase_reglee()
    assert PAROLE.la_suite_reglee(etat) == "Puis-je faire autre chose pour vous ?" and (etat.suffixe, etat.ancre) == (None, None), etat


def test_mineur_tranche_la_relance_qui_pose_encore_la_question_vide_aussi_l_ancre():
    """Voisin : la phrase du modèle pose encore la question que le code dit après elle, la relance du tour est prise : seule la phrase réglée part, et son ancre avec elle."""
    fiche = {PAROLE.CLE_DU_TOUR: 1}
    PAROLE.garder(fiche, replace(_etat_avec_la_phrase_reglee(), tour=1))
    retenue = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=fiche))._retenue("Autre chose ?", relance=True)
    etat = PAROLE.etat_du_tour(fiche)
    assert retenue is not None and retenue.raison == PAROLE.CE_QUE_LE_CODE_DIT and retenue.a_dire == "Puis-je faire autre chose pour vous ?", retenue
    assert (etat.suffixe, etat.ancre) == (None, None), etat
