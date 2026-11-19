"""[.mark] Banc A, lot 0 (L00-05) : les quatre cas de valeurs de la note de Pierre du 18/11 (§ 4), mot pour mot, vus ROUGES sur la base.

| Test | Phrase | Faute d'aujourd'hui | Lot qui le rend vert |
|---|---|---|---|
| test_deux_retraits | « une reine sans olives et sans câpres » (rejoué sur la Napoli, seule pizza de Casa aux olives et câpres retirables) | seul le dernier retrait est gardé | 3 (articles structurés) |
| test_douze_sans_oignons | « 12 sans oignons » (sur la Campione, aux oignons retirables) | lu comme 12 fois « sans oignons » | 3 (articles structurés) |
| test_une_1664 | « une 1664 » | introuvable sur une carte numérotée | 8 (nom fait de chiffres) |
| test_val_d_oise | « oui, le Val-d'Oise », réponse à « Nointel (Oise) ou Nointel (Val-d'Oise) ? » | la réponse est relue comme une autre commune (Valdoie, Valmondois), Nointel du Val-d'Oise jamais retenue | 4 (commune) |

« Une carte numérotée » : la carte de Casa Italia plus une bière dont le nom est fait de chiffres (`cartes/l00-carte-numerotee.json`,
construite au lot 0 depuis `casa-italia.json`, aucun autre changement).
"""

import json

import pytest

from api.tests.mark.banc_a.commun import appel_de, base_essai, base_prete, faire_monde, trace  # noqa: F401

pytestmark = pytest.mark.banc_a


async def _a_emporter(a):
    """Le mode d'abord : sans lui, l'article est gardé de côté et la faute de valeur ne se voit pas."""
    a.greffier(type_de_commande="à emporter")
    await a.jouer("type_de_commande", {"mode": "à emporter", "mots": "à emporter"})


async def test_deux_retraits(appel_de):
    a = await appel_de()
    await _a_emporter(a)
    await a.jouer("ajouter_au_panier", {"articles": "une napoli normale sans olives et sans câpres", "mots": "une napoli sans olives et sans câpres"})
    retraits = [r for l in a.p["lignes"] for r in (l.get("retires") or [])]
    assert len(a.p["lignes"]) == 1 and len(retraits) == 2, trace(a)


async def test_douze_sans_oignons(appel_de):
    a = await appel_de()
    await _a_emporter(a)
    await a.jouer("ajouter_au_panier", {"articles": "12 campione normales sans oignons", "mots": "12 campione normales, 12 sans oignons"})
    lignes = a.p["lignes"]
    assert len(lignes) == 1 and lignes[0]["quantite"] == 12 and len(lignes[0].get("retires") or []) == 1, trace(a)


async def test_une_1664(appel_de):
    a = await appel_de("l00-carte-numerotee")
    await _a_emporter(a)
    await a.jouer("ajouter_au_panier", {"articles": "une 1664", "mots": "une 1664"})
    assert a.quantite_de("1664") == 1, trace(a)


async def test_val_d_oise(appel_de):
    a = await appel_de()
    a.greffier(type_de_commande="en livraison")
    await a.jouer("type_de_commande", {"mode": "en livraison", "mots": "en livraison"})
    await a.jouer("verifier_adresse", {"adresse": "3 rue de Paris, Nointel", "mots": "au 3 rue de Paris à Nointel"})
    assert {c["insee"] for c in (a.p.get("adresse_en_doute") or {}).get("candidats", [])} >= {"60464", "95452"}, trace(a)
    await a.jouer("verifier_adresse", {"adresse": "3 rue de Paris, Nointel, Val-d'Oise", "mots": "oui, le Val-d'Oise"})
    retenue = json.dumps(a.p.get("adresse"), ensure_ascii=False)
    assert a.p.get("adresse_en_doute") is None and ("95452" in retenue or "95590" in retenue), "Nointel du Val-d'Oise n'est pas retenue" + trace(a)
