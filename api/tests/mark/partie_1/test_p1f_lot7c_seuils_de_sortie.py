"""[.mark] Lot 7b-C0, trous 1 et 2 : le seuil de la sortie (« je peux laisser un message à l'équipe ») est tenu par la vraie porte de la commande, pour les deux compteurs qui le lisent.

* Trou 1, le journal des refus : le même article inconnu dit ``seuil`` fois donne le refus à dire, puis l'issue, puis la sortie.
* Trou 2, la boucle : la même question de taille laissée sans réponse ``seuil`` fois (``DU.constater``) rend ``Du.boucle`` vrai au ``seuil``, jamais avant.

Le seuil se lit au schéma (la valeur par défaut du réglage de la commande), jamais un nombre écrit ici : une constante plus petite passée à la porte rend ces tests rouges.
"""

from __future__ import annotations

from api.schemas.workflow_configurations import WorkflowConfigurationDefaults as W
from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.du import CLE_DU
from api.services.actions_communes.seuil_de_sortie import CLE_FOIS_AVANT_LA_SORTIE
from api.services.commande import porte
from api.tests.mark.partie_1.porte_essai import essai_de  # noqa: F401  (fixture)

SEUIL = W.model_fields[CLE_FOIS_AVANT_LA_SORTIE].default


async def test_le_meme_article_inconnu_dit_seuil_fois_donne_le_refus_puis_l_issue_puis_la_sortie(essai_de):
    """Client « un zzzquoi » ``seuil`` fois de suite : le refus à dire, puis l'issue à chaque tour d'avant le seuil, puis la sortie au seuil."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    a_faire = [(await e.tour("un zzzquoi", ajouter=[{"article": "zzzquoi", "quantite": 1}]))["a_faire"] for _ in range(SEUIL)]
    assert porte.A_FAIRE_DES_REFUS_A_DIRE in a_faire[0] and J.A_FAIRE_ISSUE not in a_faire[0] and J.A_FAIRE_SORTIE not in a_faire[0], a_faire[0]
    for milieu in a_faire[1:-1]:
        assert J.A_FAIRE_ISSUE in milieu and J.A_FAIRE_SORTIE not in milieu, milieu
    assert J.A_FAIRE_SORTIE in a_faire[-1] and J.A_FAIRE_ISSUE not in a_faire[-1], a_faire[-1]


async def test_la_meme_question_de_taille_sans_reponse_sort_sur_la_boucle_au_seuil_seulement(essai_de):
    """Client « une regina » puis du vide ``seuil`` fois : la question de taille est reposée, ``Du.boucle`` est faux avant le seuil, vrai au seuil."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1}])
    sans_reponse = [await e.tour("euh") for _ in range(SEUIL)]
    boucles = [r[CLE_DU]["boucle"] for r in sans_reponse]
    assert boucles == [False] * (SEUIL - 1) + [True], boucles
    assert J.A_FAIRE_SORTIE in sans_reponse[-1]["a_faire"] and J.A_FAIRE_SORTIE not in str(sans_reponse[SEUIL - 2].get("a_faire")), sans_reponse[-1]["a_faire"]
