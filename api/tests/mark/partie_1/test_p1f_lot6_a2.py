"""[.mark] Lot 6, A2 : une erreur tombée APRÈS l'écriture ne fait jamais redire « je n'arrive pas à enregistrer » une commande enregistrée,
et ne joint pas la commande en double au message de l'équipe."""

from __future__ import annotations

from api.services.commande import etape as ETAPE
from api.services.commande import porte

from .aides_de_la_commande import a_emporter, jusqu_a_l_enregistrement, premier_article, refuser_la_proposition


async def test_a2_erreur_apres_l_ecriture_ne_dit_pas_pas_enregistree(essai_de, monkeypatch):
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    vrai = porte.poser_le_minimum

    def tombe_apres_l_ecriture(ctx, p, retour):
        if ETAPE.enregistree(p):
            raise RuntimeError("panne après l'écriture")
        return vrai(ctx, p, retour)

    monkeypatch.setattr(porte, "poser_le_minimum", tombe_apres_l_ecriture)
    await jusqu_a_l_enregistrement(e)
    dernier = e.retours[-1]
    assert e.p.get("enregistree"), dernier
    assert not (dernier.get("faits") or {}).get("indisponible"), dernier
    assert (dernier.get("faits") or {}).get("commande_enregistree") is True, dernier
    assert not e.fiche_de_l_appel.get(porte.CLE_RAPPEL), "la commande ne part pas en double à l'équipe"
    assert porte.CLE_TEXTES_DU_CODE not in e.fiche_de_l_appel or "n'arrive pas" not in str(e.fiche_de_l_appel[porte.CLE_TEXTES_DU_CODE]), e.fiche_de_l_appel


async def _enregistree(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    await jusqu_a_l_enregistrement(e)
    assert e.p.get("enregistree")
    return e


async def test_a2_une_commande_enregistree_n_est_jamais_annoncee_ratee_aux_tours_suivants(essai_de, monkeypatch):
    e = await _enregistree(essai_de)

    def tombe(ctx, p, retour):
        raise RuntimeError("panne au tour suivant")

    monkeypatch.setattr(porte, "poser_le_minimum", tombe)
    await e.tour("c'est prêt à quelle heure ?")
    dernier = e.retours[-1]
    assert not (dernier.get("faits") or {}).get("indisponible"), dernier
    assert not e.fiche_de_l_appel.get(porte.CLE_RAPPEL), "la commande enregistrée ne part pas en double à l'équipe"
    assert "n'arrive pas" not in str(e.fiche_de_l_appel.get(porte.CLE_TEXTES_DU_CODE)), e.fiche_de_l_appel


async def test_a2_apres_la_panne_de_l_enregistrement_l_appel_a_son_issue(essai_de, monkeypatch):
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    vrai = porte.poser_le_minimum

    def tombe_apres_l_ecriture(ctx, p, retour):
        if ETAPE.enregistree(p):
            raise RuntimeError("panne après l'écriture")
        return vrai(ctx, p, retour)

    monkeypatch.setattr(porte, "poser_le_minimum", tombe_apres_l_ecriture)
    await jusqu_a_l_enregistrement(e)
    assert e.fiche_de_l_appel.get("issue_de_l_appel") == "commande_enregistree", e.fiche_de_l_appel
    assert porte.issue_de_fin_d_appel(e.fiche_de_l_appel) is None
