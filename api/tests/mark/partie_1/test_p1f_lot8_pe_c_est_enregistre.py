"""[.mark] Lot 8, PE-2, Q4 (point d'étape du 26/11, bilan Q4, choix C) : quand la relance de la confirmation échoue, le client entend « C'est enregistré. ».

Client « Oui, c'est bon. » (il accepte la relecture), le modèle se tait deux fois (ou ne dit jamais l'heure). Avant : « Puis-je faire autre chose pour vous ? » seul, le client
n'entend jamais que sa commande est enregistrée. Après : « C'est enregistré. Puis-je faire autre chose pour vous ? ». Un motif réglé du module des phrases du code, réglable,
commande seulement, jamais dit quand le modèle a parlé (sa phrase part avec la suite du code, sans doublon)."""

from __future__ import annotations

from types import SimpleNamespace

from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark.partie_1.test_p1f_lot7c6_confirmation_au_modele import QUESTION_M108, _dire, _jusqu_a_la_confirmation, _quand

CONFIRMATION = "C'est enregistré."


async def test_le_modele_muet_deux_fois_le_client_entend_c_est_enregistre_puis_la_question(essai_de):
    e, r = await _jusqu_a_la_confirmation(essai_de)
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": ""})
    verif = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel))
    premier = verif.controler_le_silence(None)
    assert premier is not None and premier.consigne and premier.a_dire is None, premier  # la relance du modèle
    second = verif.controler_le_silence(None, sans_relance=True)
    assert second is not None and second.a_dire == f"{CONFIRMATION} {QUESTION_M108}", second


async def test_la_relance_sans_l_heure_dit_c_est_enregistre_avant_la_suite_du_code(essai_de):
    e, r = await _jusqu_a_la_confirmation(essai_de, moyen="especes", rendu_sur=50)
    dit = _dire(e, r, "Très bien.", relance="Très bien.") or ""
    assert dit.startswith(CONFIRMATION) and dit.endswith(QUESTION_M108) and dit.count(CONFIRMATION) == 1, dit
    assert "billet de cinquante" in dit, dit  # la suite du code suit, dans son ordre : confirmation, rendu, question


async def test_le_modele_a_parle_le_code_ne_redit_pas_la_confirmation(essai_de):
    e, r = await _jusqu_a_la_confirmation(essai_de)
    phrase = f"Parfait, c'est enregistré, prête {_quand(e)}."
    dit = _dire(e, r, phrase) or ""
    assert dit == f"{phrase} {QUESTION_M108}" and dit.count("enregistré") == 1, dit


def test_le_motif_est_regle_et_fait_partie_des_phrases_du_code():
    from api.services.phrases.catalogue import MOTIFS, PHRASES_DU_CODE

    motif = MOTIFS["confirmation_reglee"]
    assert motif.variantes_defaut == (CONFIRMATION,) and "confirmation_reglee" in PHRASES_DU_CODE
    assert not motif.verrouille or motif.actif_par_defaut  # réglable : son texte se change à l'écran des phrases
