"""[.mark] Lot 7a, ligne 64 : les faits de l'allergie ne sont notés « donnés » qu'une fois que la parole a laissé le modèle les recevoir (plus de réouverture après coup), et
la consigne d'allergie reste donnée au modèle, mot pour mot, même quand un refus naît dans le même retour (consigne du coordinateur : le choix entre consignes est la ligne 28, lot 7b)."""

from __future__ import annotations

from api.services.actions_communes import du as DU
from api.services.actions_communes import parole as PAROLE
from api.services.commande.porte import CLE_TEXTES_DU_CODE
from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as ALLERGIE
from api.services.workflow import parole_de_la_fiche as PF

from .aides_briques import brique


async def _panier_avec_un_article_a_noix(essai_de):
    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau aux noix", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    e.fiche_de_l_appel["allergie"] = "noix"  # le greffier la note
    return e


async def test_l_allergie_non_dite_revient_au_tour_suivant(essai_de):
    """Le code dit sa phrase seule : les faits ne sont pas notés donnés, ils reviennent à la fiche suivante ; dits au modèle (second passage), ils sont notés."""
    e = await _panier_avec_un_article_a_noix(essai_de)
    r = await e.tour("une salade et un gâteau", note_generale="allergique aux noix")
    assert r.get(DU.CLE_FAITS_A_DIRE) and ALLERGIE.allergie_a_donner(e.p) == "noix", r  # rendus au retour, rien n'est noté avant le choix de la parole
    e.fiche_de_l_appel[CLE_TEXTES_DU_CODE] = {"avant": "Je vous relis : une salade. C'est bon ?"}
    assert PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": "x"}).mode == PAROLE.A_DIRE_SEUL
    assert ALLERGIE.allergie_a_donner(e.p) == "noix"
    r2 = await e.fiche()  # le tour suivant : les faits reviennent
    assert r2.get(DU.CLE_FAITS_A_DIRE) and r2["faits"]["allergie"], r2
    assert PF.decider_apres_la_fiche(e.fiche_de_l_appel, r2, {"a_dire": "C'est bien noté pour votre allergie."}).mode == PAROLE.SECOND_PASSAGE
    assert ALLERGIE.allergie_a_donner(e.p) is None  # dits au modèle : notés


async def test_la_consigne_d_allergie_reste_donnee_avec_un_refus(essai_de):
    """« allergique aux noix ; un tiramisu et une pizza au homard » : un article refusé naît dans le même retour, la consigne d'allergie y est toujours, mot pour mot."""
    e = await _panier_avec_un_article_a_noix(essai_de)
    r = await e.tour("un tiramisu et une pizza au homard", note_generale="allergique aux noix",
                     ajouter=[{"article": "tiramisu", "quantite": 1}, {"article": "pizza au homard", "quantite": 1}])
    assert r.get("refus") or r.get("statut") in DU.BLOQUANTS, r  # un refus est né dans ce retour
    assert r.get(DU.CLE_FAITS_A_DIRE) and r["faits"]["allergie"], r
    assert ALLERGIE.A_FAIRE_DE_L_ALLERGIE in str(r.get("a_faire")), r
