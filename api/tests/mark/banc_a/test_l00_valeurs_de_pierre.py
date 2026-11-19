"""[.mark] Banc A, lot 0 (L00-05) : les quatre cas de valeurs de la note de Pierre du 18/11 (§ 4), mot pour mot, vus ROUGES sur la base.

| Test | Phrase | Faute d'aujourd'hui | Lot qui le rend vert |
|---|---|---|---|
| test_deux_retraits | « une reine sans olives et sans câpres » (rejoué sur la Napoli, seule pizza de Casa aux olives et câpres retirables) | seul le dernier retrait est gardé | 3 (articles structurés) |
| test_douze_sans_oignons | « 12 sans oignons » (sur la Campione, aux oignons retirables) | lu comme 12 fois « sans oignons » | 3 (articles structurés) |
| test_une_1664 | « une 1664 » | introuvable sur une carte numérotée | 8 (nom fait de chiffres) |
| test_val_d_oise | « oui, le Val-d'Oise », réponse à « Nointel (Oise) ou Nointel (Val-d'Oise) ? » | la réponse est relue comme une autre commune (Valdoie, Valmondois), Nointel du Val-d'Oise jamais retenue | 4 (commune) |

Lot 3 (D48) : les deux premiers passent par la fiche (``porte_essai``), articles structurés comme le modèle les écrit au contrat final.

« Une carte numérotée » : la carte de Casa Italia plus une bière dont le nom est fait de chiffres (`cartes/l00-carte-numerotee.json`,
construite au lot 0 depuis `casa-italia.json`, aucun autre changement).
"""

import json
import re

import pytest

from api.tests.mark.banc_a.commun import appel_de, base_essai, base_prete, faire_monde, trace  # noqa: F401
from api.tests.mark.partie_1.porte_essai import essai_de  # noqa: F401

pytestmark = pytest.mark.banc_a


async def test_deux_retraits(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une napoli sans olives et sans câpres", ajouter=[{"article": "napoli", "quantite": 1, "variante": "Normale", "sans": ["olives", "câpres"]}])
    retraits = [r for l in e.p["lignes"] for r in (l.get("retires") or [])]
    assert len(e.p["lignes"]) == 1 and len(retraits) == 2, e.retours


async def test_douze_sans_oignons(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("12 campione normales, 12 sans oignons", ajouter=[{"article": "campione", "quantite": 12, "variante": "Normale", "sans": ["oignons"]}])
    lignes = e.p["lignes"]
    assert len(lignes) == 1 and lignes[0]["quantite"] == 12 and len(lignes[0].get("retires") or []) == 1, e.retours


async def test_une_1664(appel_de):
    a = await appel_de("l00-carte-numerotee")
    await a.jouer_la_fiche("à emporter", {"mode_de_retrait": "emporter"})
    await a.jouer_la_fiche("une 1664", {"ajouter": [{"article": "1664", "quantite": 1}]})
    assert a.quantite_de("1664") == 1, trace(a)


async def test_val_d_oise(appel_de):
    a = await appel_de()
    r = await a.jouer_la_fiche("en livraison au 3 rue de Paris à Nointel", {"mode_de_retrait": "livraison", "adresse": "3 rue de Paris", "commune": "Nointel"})
    assert {"60464", "95452"} <= set(re.findall(r"\b(?:60464|95452)\b", json.dumps(r))), trace(a)
    r = await a.jouer_la_fiche("oui, le Val-d'Oise", {"adresse": "3 rue de Paris", "commune": "Nointel, Val-d'Oise", "reponse": {"question_id": "?", "sens": "accepte"}})
    # Lot 4 : la commune comprise (posée sur l'adresse si elle est livrée ; dite hors zone sinon, comme ici au banc A), jamais Valdoie ni l'Oise.
    retenue = json.dumps(a.p.get("adresse"), ensure_ascii=False) + json.dumps(r, ensure_ascii=False)
    assert ("95452" in retenue or "95590" in retenue) and "60464" not in retenue and "Valdoie" not in retenue, "Nointel du Val-d'Oise n'est pas retenue" + trace(a)
