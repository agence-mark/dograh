"""[.mark] Lot 8, PE-2, Q3 (point d'étape du 26/11, bilan Q3) : « Ah merci. » ne donne plus « Pardon, je n'ai pas bien saisi ».

Le modèle rejoue deux fois une fiche VIDE (aucune case remplie) et rien n'est dû (aucune question n'attend, rien ne manque, aucune suite réglée) : la relance est ratée, mais la
phrase du modèle est une bonne réponse (un remerciement). Elle est dite seule. Client « Ah merci. » / Avant : « Pardon, je n'ai pas bien saisi. Vous pouvez répéter ? » /
Après : « Avec plaisir. ». Jamais quand la fiche porte une case (« finalement en livraison », rejouée) ni quand quelque chose est dû (la question qui attend : P3, ``test_cloture_b2_du``)."""

from __future__ import annotations

from api.services.actions_communes import parole as PAROLE
from api.services.actions_communes.du import RIEN_CHANGE
from api.services.phrases.catalogue import REPONSE_PERDUE
from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark.partie_1.aides_de_la_commande import jusqu_a_l_enregistrement_de_la_proposition

PHRASE = "Avec plaisir."


async def test_ah_merci_une_fiche_vide_rejouee_dit_la_phrase_du_modele(essai_de):
    e = await essai_de()
    await jusqu_a_l_enregistrement_de_la_proposition(e)
    r = await e.fiche()
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": PHRASE})
    assert (d.mode, d.motif) == (PAROLE.SECOND_PASSAGE, RIEN_CHANGE), d  # la relance du tour
    r = await e.fiche()
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": PHRASE})
    assert (d.mode, d.a_dire, d.motif) == (PAROLE.A_DIRE_SEUL, PHRASE, "fait"), d


async def test_une_fiche_qui_porte_une_case_rejouee_reste_une_relance_ratee(essai_de):
    """Le voisin : la fiche rejouée n'est pas vide (un changement de mode déjà fait) : P3, comme avant."""
    e = await essai_de()
    await jusqu_a_l_enregistrement_de_la_proposition(e)
    cases = {"mode_de_retrait": "livraison"}
    r = await e.tour("finalement en livraison", **cases)
    PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": PHRASE, **cases})
    r = await e.fiche(**cases)
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, r, {"a_dire": PHRASE, **cases})
    assert r.get(RIEN_CHANGE) and (d.mode, d.a_dire, d.motif) == (PAROLE.A_DIRE_SEUL, None, REPONSE_PERDUE), (r, d)
