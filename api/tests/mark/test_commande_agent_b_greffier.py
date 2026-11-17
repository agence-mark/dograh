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

from api.services.commande import action, moteur
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_commande_kebab_sa52 import Appel, kebab  # noqa: F401


async def _en_livraison(kebab):
    a = await Appel(kebab).charger()
    await moteur.choisir_mode(a.source, a.p, a.regles, "livraison")
    return a


async def test_b1_l_adresse_notee_pose_la_zone(kebab):
    a = await _en_livraison(kebab)
    ctx = SimpleNamespace(fiche={"adresse_livraison": "5 rue Louis Boilet", "commune": "Pont-Sainte-Maxence"}, rattraper=None)
    r = await action.appliquer_la_zone(a.source, a.p, a.regles, ctx, attendre=False)
    assert r is not None and r.statut == "RETENU" and a.p["zone"], r


async def test_b2_les_notes_dans_extracted_variables():
    ctx = SimpleNamespace(fiche={"extracted_variables": {"prenom": "Evan", "numero_dicte": "0788261409", "allergie": ""}})
    assert action.notes_du_greffier(ctx) == {"prenom": "Evan", "telephone": "0788261409"}


async def test_b3_la_note_en_cours_est_attendue(kebab):
    a = await _en_livraison(kebab)
    fiche: dict = {}

    async def rattraper(delai):
        fiche.update({"adresse_livraison": "5 rue Louis Boilet", "commune": "Pont-Sainte-Maxence"})
        return True

    r = await action.appliquer_la_zone(a.source, a.p, a.regles, SimpleNamespace(fiche=fiche, rattraper=rattraper), attendre=True)
    assert r is not None and a.p["zone"], r


async def test_b4_une_adresse_deja_essayee_n_est_pas_reverifiee(kebab):
    a = await _en_livraison(kebab)
    ctx = SimpleNamespace(fiche={"adresse_livraison": "rue inconnue", "commune": "Nullepart"}, rattraper=None)
    premier = await action.appliquer_la_zone(a.source, a.p, a.regles, ctx, attendre=False)
    assert premier is not None
    assert await action.appliquer_la_zone(a.source, a.p, a.regles, ctx, attendre=False) is None
