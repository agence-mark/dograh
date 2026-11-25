"""[.mark] Lot 7a, ligne 61 : le fait accompli que le code a dit (enregistrée, changée, annulée) est UNE entrée du journal de ce qui est dit, plus une seconde mémoire
(``dernier_fait_dit``) à côté. Le repli le redit au lieu de « je n'ai pas compris » ; comme tout le journal, il compte dans ce que la fiche a changé (R1)."""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.actions_communes import du as DU
from api.services.actions_communes import journal_du_dit as J

from .aides_de_la_commande import a_emporter, jusqu_a_l_enregistrement, premier_article, refuser_la_proposition


async def test_apres_l_enregistrement_pardon_redit_la_confirmation_depuis_le_journal(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await premier_article(e)
    await refuser_la_proposition(e)
    await jusqu_a_l_enregistrement(e)
    confirmation = J.fait_accompli(e.p) or ""
    assert confirmation.startswith("Votre commande est enregistrée"), e.p
    from types import SimpleNamespace

    from api.services.workflow import parole_de_la_fiche as PF

    e.montrer()
    silence = PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler_le_silence()
    assert silence is not None and silence.a_dire == confirmation  # décision d'Evan 25/11 8 h 45 (lot 7b-C5) : le modèle muet, rien n'est dû : le fait accompli
    assert "dernier_fait_dit" not in e.p and "dernier_fait_dit" not in e.p.get(CONV.CLE, {})  # plus de seconde mémoire


def test_le_fait_accompli_compte_dans_ce_que_la_personne_vit():
    p: dict = {}
    avant = DU.ce_qui_se_voit(p)
    J.dire_le_fait(p, "Votre commande est enregistrée.", 3)
    assert DU.ce_qui_se_voit(p) != avant
    assert J.fait_accompli(p) == "Votre commande est enregistrée." and J.fait_accompli({}) is None
