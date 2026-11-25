"""[.mark] Lot 7b-C0, reprise D1 : la liste des « plus proches » d'un article introuvable n'a pas de doublon.

Avant : client « une pizza au homard » : ``plus_proches == ["4 Formaggi", "Regina", "4 Formaggi"]`` et la phrase « Le plus proche : 4 Formaggi, Regina ou 4 Formaggi. » (deux entrées de la
carte portent le même libellé). Déjà vrai au commit de départ ``6c23b0b60`` (``articles.py:651``). La phrase elle-même n'est pas touchée : elle sera rendue au modèle en 7b-C1.
"""

from __future__ import annotations


async def test_les_plus_proches_d_un_article_introuvable_n_ont_pas_de_doublon(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("une pizza au homard", ajouter=[{"article": "pizza au homard", "quantite": 1}])
    refus = r["faits"]["refus_de_la_fiche"][0]
    proches = refus["faits"]["plus_proches"]
    assert proches and len(proches) == len(set(proches)), proches
