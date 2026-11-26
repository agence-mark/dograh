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
