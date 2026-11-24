"""[.mark] Lot 7b-A, ligne 82 : « je ne peux pas vous garantir » n'est plus une phrase du code. Une information que la fiche ne donne pas (un régime non étiqueté)
est un FAIT (``renseigne: False``) ; la proposition (``phrases_d_information.NON_GARANTI``) est donnée au modèle comme consigne, jamais dite par le code."""

from __future__ import annotations

from api.services.actions_communes import phrases_d_information as INFO

from .aides_briques import brique, fait


async def test_un_regime_non_etiquete_est_un_fait_sans_phrase_du_code(essai_de):
    e = await brique(essai_de, "INF4")
    r = await e.lecture(sujet="allergenes", article="Sandwich poulet", a_eviter="halal")
    assert '"renseigne": false' in fait(r["faits"]), r
    assert "a_faire" not in r["faits"] and "Je ne peux" not in fait(r), r  # aucune phrase rédigée par le code : le fait seul, la consigne à part
    assert r.get("a_faire") == INFO.CONSIGNE_NON_GARANTI, r  # la proposition reste celle du module commun, en consigne
