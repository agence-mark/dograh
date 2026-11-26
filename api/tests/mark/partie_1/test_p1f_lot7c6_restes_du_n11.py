"""[.mark] Lot 7b-C6, commit 12 d (décision d'Evan 25/11 9 h 30, § 8 bis : les prix D33 passent au modèle) : les restes du n° 11 (risques 5 à 8 du compte rendu 6).

Le code ne compose plus de phrase de prix qu'il ne dit pas (le repli de B8), ne garde plus de clé ni d'état morts (``prix_a_dire``, ``suffixe_lu``) et ne dit plus au modèle que
« les chiffres sont dits par le code ». Sur la vraie source et la vraie porte, sans modèle.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV

from .aides_de_la_commande import a_emporter, premier_article


async def test_la_proposition_ne_compose_plus_de_phrase_de_prix(essai_de):
    """Risque 5 : avant, le moteur composait « Avec cela, je vous propose un Coca-Cola à deux euros. Je vous l'ajoute ? » (repli de B8), gardé dans la question et jamais dit
    (C5 : le modèle est relancé avec la proposition en faits ; C6 n° 11 : il dit le prix). Après : la question garde l'article et le prix, aucune phrase."""
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    q = CONV.question_de(e.p) or {}
    assert q.get("type") == "proposition" and q.get("prix"), q
    assert "repli" not in q and "repli" not in (e.p.get("proposition_en_plus") or {}), (q, e.p.get("proposition_en_plus"))


def test_plus_aucune_cle_ni_etat_mort_du_prix_dit_par_le_code():
    """Risque 6 et ``suffixe_lu`` : plus aucun résultat ne porte ``prix_a_dire`` (C6 n° 11 : le prix lu est un fait, ``prix``), le filtre qui l'écartait et l'état du tour qui gardait le
    prix lu (jamais posé depuis le n° 11) sont retirés. Un état du tour déjà écrit avec ``suffixe_lu`` se relit sans erreur (clé ignorée)."""
    from api.services.actions_communes import parole as PAROLE
    from api.services.commande import lire

    assert not hasattr(lire, "CLE_DU_PRIX_A_DIRE")
    assert "suffixe_lu" not in PAROLE.EtatDuTour.__dataclass_fields__
    fiche = {PAROLE.CLE_DU_TOUR: 4, PAROLE.CLE_ETAT_DU_TOUR: {"tour": 4, "suffixe": "x", "suffixe_lu": None}}
    assert PAROLE.etat_du_tour(fiche).suffixe == "x"


def test_le_rappel_du_chiffre_ne_dit_plus_que_les_chiffres_sont_dits_par_le_code():
    """Risque 7 (règle 6 : le mécanisme et ce qui le décrit changent ensemble) : depuis C6 n° 11, le modèle dit les prix des faits ; la barrière ne retient que le chiffre absent des
    faits. Avant, le modèle relancé lisait « Les chiffres sont dits par le code. » ; après, il lit qu'il ne dit que les chiffres des faits, tels quels."""
    from api.services.actions_communes import barriere_des_chiffres as BC

    assert "dits par le code" not in BC.RAPPEL_DU_CHIFFRE
    assert "faits" in BC.RAPPEL_DU_CHIFFRE and "n'a pas été dite" in BC.RAPPEL_DU_CHIFFRE


def test_le_motif_du_numero_affiche_garde_ne_parle_que_de_la_reservation():
    """Risque 5 du compte rendu 7 (Q2 = A, § 9 du brief) : seule la réservation remplace sa question finale par celle du numéro qui s'affiche ; la commande pose cette question à
    part (le modèle). Le texte montré au restaurant ne nomme plus la commande, et dit ce qui se passe quand la phrase est éteinte (le modèle pose la question)."""
    from api.services.phrases import catalogue as CAT

    m = CAT.MOTIFS[CAT.NUMERO_AFFICHE_GARDE]
    assert "commande" not in m.quand_fr and "order" not in m.quand_en and "réservation" in m.quand_fr, m.quand_fr
    assert "modèle" in m.eteinte_fr, m.eteinte_fr
