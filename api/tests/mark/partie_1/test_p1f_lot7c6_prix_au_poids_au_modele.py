"""[.mark] Lot 7b-C6, commit 11d (décision d'Evan 25/11 9 h 30, § 8 bis : les prix D33 passent au modèle, vérifiés par la barrière des chiffres).

Prix au poids (QTE1). Avant : modèle « C'est noté. » + code « trois cents grammes de houmous : cinq euros quarante. ».
Après : modèle « Trois cents grammes de houmous, ça fait cinq euros quarante. » : le prix de la ligne est un fait du retour (``prix_au_poids``), que le modèle dit et que la barrière
laisse passer ; un autre prix est retenu. Sur la vraie source et la vraie porte, sans modèle.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import parole as PAROLE
from api.services.commande import contrat, porte
from api.services.workflow import parole_de_la_fiche as PF
from api.tests.mark.partie_1.aides_briques import brique


async def _au_poids(essai_de, parole: str, article: str, quantite: int, poids: str):
    e = await brique(essai_de, "QTE1")
    _, objets = await e.source.charger_pour_l_appel()
    e.fiche_de_l_appel[contrat.CLE_DES_OBJETS] = objets
    r = await e.tour(parole, ajouter=[{"article": article, "quantite": quantite, "poids": poids}])
    return e, r


def _textes(e) -> dict:
    return dict(e.fiche_de_l_appel.get(porte.CLE_TEXTES_DU_CODE) or {})


def _jugee(e, retour, phrase: str):
    """La phrase du modèle après la fiche : un prix à dire est un fait qui fait repasser le modèle ; sa phrase est jugée au second passage (``None`` : dite telle quelle)."""
    d = PF.decider_apres_la_fiche(e.fiche_de_l_appel, retour, {"a_dire": "C'est noté."})
    assert d.mode == PAROLE.SECOND_PASSAGE, d
    return PF.VerificateurDeLaFiche(SimpleNamespace(_gathered_context=e.fiche_de_l_appel)).controler(phrase)


async def test_le_prix_au_poids_est_un_fait_du_retour_et_le_code_ne_le_dit_plus(essai_de):
    e, r = await _au_poids(essai_de, "trois cents grammes de houmous", "houmous", 1, "trois cents grammes")
    assert [{k: x[k] for k in ("grammes", "quantite", "prix")} for x in r["faits"]["prix_au_poids"]] == [{"grammes": 300, "quantite": 1, "prix": 540}], r["faits"]
    assert "prix_dit_par_le_code_apres_ta_phrase" not in r and not _textes(e).get("suffixe"), (r, _textes(e))
    assert all("prix_a_dire" not in (x.get("faits") or {}) for x in r.get("resultats") or []), r["resultats"]


async def test_plusieurs_portions_donnent_le_total_de_la_ligne_et_l_arrondi(essai_de):
    """Pierre 12 : « deux fois trois cents grammes » : le total de la ligne (dix euros quatre-vingts), jamais le prix d'une portion ; l'arrondi est un fait (``arrondi_a``)."""
    e, r = await _au_poids(essai_de, "deux fois trois cents grammes de houmous", "houmous", 2, "trois cents grammes")
    assert [(x["quantite"], x["prix"]) for x in r["faits"]["prix_au_poids"]] == [(2, 1080)], r["faits"]
    e, r = await _au_poids(essai_de, "deux cent trente grammes de taboulé", "taboulé", 1, "deux cent trente grammes")
    assert [(x["grammes"], x.get("arrondi_a"), x["prix"]) for x in r["faits"]["prix_au_poids"]] == [(250, 250, 625)], r["faits"]


async def test_la_phrase_du_modele_qui_dit_le_prix_au_poids_passe_la_barriere(essai_de):
    e, r = await _au_poids(essai_de, "trois cents grammes de houmous", "houmous", 1, "trois cents grammes")
    assert _jugee(e, r, "Trois cents grammes de houmous, ça fait cinq euros quarante.") is None  # dite telle quelle, rien d'ajouté par le code


async def test_un_autre_prix_que_celui_du_poids_est_retenu(essai_de):
    e, r = await _au_poids(essai_de, "trois cents grammes de houmous", "houmous", 1, "trois cents grammes")
    retenue = _jugee(e, r, "Trois cents grammes de houmous, ça fait neuf euros.")
    assert retenue is not None and retenue.raison == PAROLE.CHIFFRE, retenue
