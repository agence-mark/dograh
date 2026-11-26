"""[.mark] Lot 8, PE-2, reprise R1 (décision de Pierre, 26/11 22 h 05, ``decisions-du-coordinateur``, option B) : le juge RC4 laisse passer la phrase du modèle dite seule
quand la fiche rejouée est VIDE, qu'aucune question n'attend, qu'aucun manque n'est dû (Q3, BILAN:271). Rien d'autre n'est assoupli : une fiche qui porte une case, ou une question
qui attend, restent une faute RC4. Les deux gardes sont éprouvées sur des observations construites (le code les rend en P3 dans le vrai jeu : seul le juge est ici sous test)."""

from __future__ import annotations

import copy
from collections import Counter

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes.du import CLE_DU
from api.services.actions_communes import parole as PAROLE
from api.tests.mark.partie_1 import combinaisons as C


def _observation(fiche, *, question=None, manque=None):
    """E18 : commande enregistrée, rien ne change ; le code dit la phrase du modèle seule."""
    panier = {"lignes": [], "mode": "emporter", "enregistree": {"numero": 7, "total": 12}}
    if question:
        CONV.poser_question(panier, question)
    retour = {"statut": "OK", CLE_DU: {"manque": manque}} if manque else {"statut": "OK"}
    return C.Observation("G31", panier, copy.deepcopy(panier), retour, {}, PAROLE.Decision(PAROLE.A_DIRE_SEUL, C.ANNONCE, "fait"), Counter(), fiche)


def test_une_fiche_vide_rejouee_sans_rien_de_du_n_est_pas_une_faute_rc4():
    assert C.rc4(_observation({})) == []


def test_une_fiche_non_vide_rejouee_reste_une_faute_rc4():
    """E18 G15·G31 (T12, « Léa. ») : la fiche rejouée porte un changement de mode."""
    assert [r for r, _ in C.rc4(_observation({"mode_de_retrait": "livraison"}))] == ["RC4"]


def test_une_fiche_vide_avec_une_question_en_attente_reste_une_faute_rc4():
    question = {"id": "q1", "type": "choix", "texte": "Sur place ou à emporter ?"}
    assert [r for r, _ in C.rc4(_observation({}, question=question))] == ["RC4"]


def test_une_fiche_vide_avec_un_manque_du_reste_une_faute_rc4():
    assert [r for r, _ in C.rc4(_observation({}, manque="mode"))] == ["RC4"]


async def test_le_vrai_jeu_e18_fiche_vide_puis_rejouee_ne_donne_aucune_faute(faire_monde, monkeypatch):
    """E18 → G30 · G31 (la paire que ``test_profondeur_2[E18]`` jouait rouge) : client « D'accord. », modèle muet deux fois, « C'est noté. » dit seul (Q3)."""
    res = await C.jouer(await faire_monde("casa-italia"), monkeypatch, "E18", ("G30", "G31"))
    assert res.atteint
    assert not res.fautes, "\n".join(f"[{g}] {r} : {d}" for g, r, d in res.fautes)
