"""[.mark] Agent B (Evan, 17/11) : les outils pour les actions métier, le reste au greffier. La commande lit l'adresse, le prénom, le numéro et
l'allergie notés par le greffier ; la zone et le minimum sont appliqués par le code dès que l'adresse est notée, en attendant la passe en
cours (le tour de retard, comme Nuances de Feu).

| Test | Ce qu'il prouve |
|---|---|
| B1 | l'adresse notée par le greffier pose la zone (le modèle n'a passé aucune adresse) |
| B2 | les notes se lisent dans ``extracted_variables`` comme dans la fiche |
| B3 | la note pas encore écrite est attendue (rattrapage du greffier), puis appliquée |
| B4 | une adresse déjà essayée n'est pas revérifiée à chaque outil |
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.commande import moteur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_commande_kebab_sa52 import Appel, kebab  # noqa: F401


async def _en_livraison(kebab):
    a = await Appel(kebab).charger()
    await moteur.choisir_mode(a.source, a.p, a.regles, "livraison")
    return a










def test_b5_une_commande_qui_attend_sa_reponse_n_est_jamais_perdue_par_une_fin(monkeypatch):
    """Appel 2624 : la fin refusée au tour 7 laissait passer celle du tour 11, à l'approbation de la relecture : commande perdue."""
    from api.services.workflow import action_non_aboutie as g

    ouvertes = [{"connecteur": "commande", "outil": "finaliser", "attend_une_reponse": True}]
    fiche = {g.CLE_FICHE_REFUS: True, g.CLE_FICHE_MARQUE: {"tour": 7, "journal": 6, "de_suite": 1}, g.CLE_TOUR_APPELANT: 11}
    assert g._attend_au_nouveau_tour(fiche, ouvertes) is True
    fiche[g.CLE_TOUR_APPELANT] = 7
    assert g._attend_au_nouveau_tour(fiche, ouvertes) is False  # jamais deux refus dans le même tour
    assert g._attend_au_nouveau_tour({**fiche, g.CLE_TOUR_APPELANT: 11}, [{**ouvertes[0], "attend_une_reponse": False}]) is False
