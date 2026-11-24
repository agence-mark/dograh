"""[.mark] Lot 7b, ``Du.boucle`` : UNE source. La boucle (la même chose redite sans issue) est calculée une fois, par le constat de la sortie de fiche, et vit sur l'exemplaire rangé
dans le retour ; la lecture vive du retour (``du_du_retour``) ne la porte pas, la sortie se lit sur elle par ``une_consigne``, plus par un collage."""

from __future__ import annotations

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes.du import CLE_DU, du_du_retour


async def test_la_meme_chose_redite_trois_fois_sort_sur_la_boucle_rangee(essai_de):
    """Client qui redit trois fois le même article refusé : au troisième tour la sortie est dite au modèle, lue sur ``Du.boucle`` de l'exemplaire rangé ; la lecture vive ne la connaît pas."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    suite = [await e.tour("un zzzquoi", ajouter=[{"article": "zzzquoi", "quantite": 1}]) for _ in range(3)]
    dernier = suite[2]
    assert not suite[0][CLE_DU]["boucle"], suite[0]
    assert dernier[CLE_DU]["boucle"] is True and J.A_FAIRE_SORTIE in dernier["a_faire"], dernier
    assert du_du_retour(dernier).boucle is False, "la lecture vive du retour ne relit pas la boucle : seul l'exemplaire rangé fait foi"
    assert dernier["a_faire"].count(J.A_FAIRE_SORTIE) == 1, dernier["a_faire"]


async def test_la_boucle_qui_se_defait_n_est_plus_dite(essai_de):
    """Une commande qui avance remet le compte à zéro : plus de sortie."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    for _ in range(3):
        await e.tour("un zzzquoi", ajouter=[{"article": "zzzquoi", "quantite": 1}])
    r = await e.tour("une margherita", ajouter=[{"article": "margherita", "quantite": 1}])
    assert not r[CLE_DU]["boucle"] and J.A_FAIRE_SORTIE not in str(r.get("a_faire")), r
