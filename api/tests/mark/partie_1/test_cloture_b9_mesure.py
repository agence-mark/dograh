"""[.mark] Clôture de la Partie 1, agent « mesure » (23/11) : les défauts que le test des combinaisons honnête (Pierre 15) a fait apparaître, chacun vu rouge avant son correctif.

| Défaut | Règle | Test |
|---|---|---|
| RC2 : « oui » à une taille + « une margherita et une regina » : la case ``ajouter`` entière était refusée, la regina perdue | refus du seul article déjà en question (D01, B4) | ``test_le_refus_de_l_article_deja_en_question_laisse_entrer_les_autres`` |
| RC1 : « non » à l'heure proposée (fermé) + un article sans taille : la question de l'heure ET celle de la taille dans le même tour | une seule question à la fois (RC1) | ``test_une_seule_question_quand_l_heure_proposee_est_refusee_avec_un_article_sans_taille`` |
| RC13 : une panne à la case N laissait le panier changé par les cases d'avant, le retour muet | tout ou rien par case, même en panne | ``test_combinaisons.py::test_rc13_*`` |
"""

from __future__ import annotations

from api.tests.mark.partie_1 import combinaisons as C


async def test_le_refus_de_l_article_deja_en_question_laisse_entrer_les_autres(faire_monde, monkeypatch):
    monde = await faire_monde("casa-italia")
    p = C.Partie(monde, monkeypatch)
    assert await p.recette("E5")  # une margherita attend sa taille
    o = await p.fusion(("G5", "G23"))  # « oui » + une margherita et une regina normales
    assert C.lignes_de(p.p) == C.Counter({C.MARGHERITA: 1, C.REGINA: 1}), (C.lignes_de(p.p), o.retour)
    assert any(r.get("raison") == "article_deja_en_question" for r in o.retour.get("refus") or []), o.retour  # le refus reste dit au retour


async def test_une_seule_question_quand_l_heure_proposee_est_refusee_avec_un_article_sans_taille(faire_monde, monkeypatch):
    monde = await faire_monde("casa-italia")
    r = await C.jouer(monde, monkeypatch, "E9", ("G2+G24", "G4+G24"))
    assert r.atteint and not [f for f in r.fautes if f[1] == "RC1"], r.fautes
