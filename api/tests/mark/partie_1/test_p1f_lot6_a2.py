"""[.mark] Lot 6, A2 : une erreur tombée APRÈS l'écriture ne fait jamais redire « je n'arrive pas à enregistrer » une commande enregistrée,
et ne joint pas la commande en double au message de l'équipe."""

from __future__ import annotations

from api.services.commande import etape as ETAPE
from api.services.commande import porte

from .test_l04_cuisine import _a_emporter, _jusqu_a_l_enregistrement, _premier_article, _refuser_la_proposition


async def test_a2_erreur_apres_l_ecriture_ne_dit_pas_pas_enregistree(essai_de, monkeypatch):
    e = await essai_de()
    await _a_emporter(e)
    await _premier_article(e)
    await _refuser_la_proposition(e)
    vrai = porte.poser_le_minimum

    def tombe_apres_l_ecriture(ctx, p, retour):
        if ETAPE.enregistree(p):
            raise RuntimeError("panne après l'écriture")
        return vrai(ctx, p, retour)

    monkeypatch.setattr(porte, "poser_le_minimum", tombe_apres_l_ecriture)
    await _jusqu_a_l_enregistrement(e)
    dernier = e.retours[-1]
    assert e.p.get("enregistree"), dernier
    assert not (dernier.get("faits") or {}).get("indisponible"), dernier
    assert (dernier.get("faits") or {}).get("commande_enregistree") is True, dernier
    assert not e.fiche_de_l_appel.get(porte.CLE_RAPPEL), "la commande ne part pas en double à l'équipe"
    assert porte.CLE_TEXTES_DU_CODE not in e.fiche_de_l_appel or "n'arrive pas" not in str(e.fiche_de_l_appel[porte.CLE_TEXTES_DU_CODE]), e.fiche_de_l_appel
