"""[.mark] Plan final Partie 1, lot 8b-3 (A1, option A d'Evan : ``lot-8-fiche-machee.md`` § 11, « une allergie dite après le oui rouvre la commande ») : l'allergie dite avec le « oui »
de la relecture est lue AVANT l'enregistrement : le greffier est attendu (``rattraper``, ``DELAI_DE_LA_PASSE_DU_DERNIER_TOUR``) sur la seule fiche qui peut enregistrer, l'allergie est
notée et bloque comme les autres, l'accord est redemandé, rien n'est enregistré sans lui.

| Test | Ce qu'il prouve |
|---|---|
| le oui et l'allergie ensemble | greffier lent : l'allergie est notée, la commande n'est pas enregistrée, la relecture repart, le « oui » redonné enregistre |
| une fiche ordinaire | le greffier n'est pas attendu quand la fiche ne peut pas enregistrer (latence) |
| sans greffier | ``rattraper`` absent (clavier) : la fiche se joue comme avant |
"""

from __future__ import annotations

from api.services.restauration.carte_et_allergenes import allergie_de_la_commande as ALLERGIE
from api.tests.mark.partie_1 import aides_de_la_commande as AC
from api.tests.mark.partie_1.aides_briques import brique


def _greffier_lent(e, delais: list[float]) -> None:
    """Un greffier dont la passe finit pendant l'attente : ce qu'il note (l'allergie) n'est dans la fiche de l'appel qu'APRÈS ``rattraper``."""
    async def rattraper(delai: float) -> bool:
        delais.append(delai)
        e.fiche_de_l_appel["allergie"] = "noix"
        return True

    e.ctx.rattraper = rattraper


async def _relecture_dite(essai_de):
    e = await brique(essai_de, "INF6")
    await e.tour("un gâteau aux noix", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    await AC.refuser_la_proposition(e)
    q = await AC.jusqu_au_recapitulatif(e)
    return e, q


async def test_le_oui_et_l_allergie_ensemble_l_allergie_bloque_et_l_accord_est_redemande(essai_de):
    """Modèle (relecture) « … c'est bon pour vous ? » / Client « Oui, et mon fils est allergique aux noix. » (carte, prénom et numéro dits avec) / avant : la commande s'enregistre
    avant que l'allergie soit notée / après : l'allergie est lue d'abord, rien n'est enregistré, la relecture repart ; le « oui » redonné enregistre."""
    e, q = await _relecture_dite(essai_de)
    delais: list[float] = []
    _greffier_lent(e, delais)
    r = await e.tour("oui, et mon fils est allergique aux noix", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire", prenom="Léa", telephone="0612345678")
    assert delais, "le greffier n'a pas été attendu avant l'enregistrement"
    assert ALLERGIE.allergie_connue(e.p) == "noix", e.p.get("notes_du_greffier")
    assert not e.p.get("enregistree"), r  # l'allergie bloque : rien n'est enregistré, l'accord n'est pas pris pour acquis
    assert e.monde.c is not None and not e.source.prise.recues, e.source.prise.recues
    assert not e.p.get("enregistree")
    await AC.jusqu_a_l_enregistrement(e, prenom="Léa", telephone="0612345678")  # la relecture repart, le « oui » redonné enregistre
    assert e.p.get("enregistree") and len(e.source.prise.recues) == 0, e.retours[-1]


async def test_une_fiche_qui_ne_peut_pas_enregistrer_n_attend_pas_le_greffier(essai_de):
    e = await brique(essai_de, "INF6")
    delais: list[float] = []
    _greffier_lent(e, delais)
    await e.tour("un gâteau aux noix", ajouter=[{"article": "gâteau aux noix", "quantite": 1}])
    assert delais == [], delais


async def test_sans_greffier_la_fiche_se_joue_comme_avant(essai_de):
    e, _ = await _relecture_dite(essai_de)
    assert getattr(e.ctx, "rattraper", None) is None
    await AC.jusqu_a_l_enregistrement(e, prenom="Léa", telephone="0612345678")
    assert e.p.get("enregistree")
