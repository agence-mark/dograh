"""[.mark] Lot 7b-C0, piège 1 : le journal de ce qui est dit compte un refus par son IDENTITÉ (statut, manque, objet), jamais par le texte de la suggestion.

Un texte de suggestion qui change d'un tour à l'autre (un chiffre variable, la liste des plus proches, un texte de secours réécrit en 7b-C) ne remet jamais le compteur à zéro.
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.actions_communes import journal_du_dit as J
from api.services.commande import porte
from api.services.commande.moteur import articles
from api.services.commande.resultat import Resultat
from api.tests.mark.partie_1.porte_essai import essai_de  # noqa: F401  (fixture)


def _introuvable(dit: str, suggestion: str, proches: list[str] | None = None) -> Resultat:
    return Resultat("INTROUVABLE", {"dit": dit, "plus_proches": proches or []}, suggestion)


def test_l_identite_ignore_le_texte_et_les_listes_et_garde_l_objet():
    a = J.identite_du_refus(_introuvable("zzzquoi", "Je ne trouve pas « zzzquoi ».", ["Coca"]))
    b = J.identite_du_refus(_introuvable("zzzquoi", "Rien de tel chez nous.", ["Fanta", "Sprite"]))
    assert a == b
    assert a != J.identite_du_refus(_introuvable("autrechose", "Je ne trouve pas « autrechose »."))
    assert a != J.identite_du_refus(Resultat("INDISPONIBLE", {"dit": "zzzquoi"}, "x"))
    assert a != J.identite_du_refus(Resultat("INTROUVABLE", {"dit": "zzzquoi"}, "x", "une_raison"))


def test_la_deduplication_des_refus_de_la_fiche_se_fait_par_identite():
    """Deux refus du même objet au texte différent sont UN refus ; un autre objet reste un autre refus."""
    f = SimpleNamespace(bruts=[_introuvable("zzzquoi", "texte un"), _introuvable("zzzquoi", "texte deux"), _introuvable("autre", "texte trois")], dernier=None)
    assert [r.faits["dit"] for r in porte.refusants_de_la_fiche(f)] == ["zzzquoi", "autre"]


async def test_le_compteur_ne_repart_pas_quand_le_texte_de_suggestion_change(essai_de, monkeypatch):
    """Client « un zzzquoi » trois fois, le texte de la suggestion change à chaque tour : issue au 2e, sortie au 3e (le compteur ne repart pas)."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    tour = {"n": 0}

    def liste_changeante(noms):
        tour["n"] += 1
        return f"variante {tour['n']}"

    monkeypatch.setattr(articles, "liste_dite", liste_changeante)
    retours = []
    for _ in range(3):
        retours.append(await e.tour("un zzzquoi", ajouter=[{"article": "zzzquoi", "quantite": 1}]))
    a_faire = [r["a_faire"] for r in retours]
    assert J.A_FAIRE_ISSUE in a_faire[1] and J.A_FAIRE_SORTIE in a_faire[2], a_faire
