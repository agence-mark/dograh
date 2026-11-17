"""[.mark] Appel 2631 (Evan, 17/11) : « en livraison » dit deux fois sans qu'aucun outil soit appelé ; le mode jamais posé, la commande
bloquée sur sa question jusqu'à l'échec. Le greffier note le type de commande et le mode de paiement ; le code les prend quand l'outil
ne les a pas reçus. Les outils sont nommés au modèle sous le nom qu'il voit.

| Test | Ce qu'il prouve |
|---|---|
| C1 | le type de commande noté par le greffier est posé avant le geste demandé (ajouter), les articles suivent |
| C2 | rien n'est posé quand le greffier n'a rien noté, ni quand le mode est déjà posé |
| C3 | un mode inventé (« rien de précisé ») est un mode non dit |
| C4 | le moyen de paiement noté se lit dans ses mots |
| C5 | le nom vu par le modèle remplace celui de l'action ; inconnu, l'action reste |
"""

from __future__ import annotations

from types import SimpleNamespace

from api.services.commande import action
from api.services.integrations.connectors.outil import CLE_NOMS_DES_OUTILS, nom_vu, retenir_le_nom
from api.tests.mark.test_base_client import base_essai, base_prete  # noqa: F401
from api.tests.mark.test_commande_kebab_sa52 import Appel, kebab  # noqa: F401


async def test_c1_le_mode_note_par_le_greffier_est_pose(kebab):
    a = await Appel(kebab).charger()
    a.p["question_en_attente"] = "choisir_mode.mode"
    ctx = SimpleNamespace(fiche={"extracted_variables": {"type_de_commande": "à emporter"}}, rattraper=None)
    r = await action.appliquer_le_mode(a.source, a.p, a.regles, ctx, "ajouter", {"articles": "un coca"})
    assert r is None and a.p["mode"] == "emporter", (r, a.p.get("mode"))


async def test_c2_rien_a_poser(kebab):
    a = await Appel(kebab).charger()
    vide = SimpleNamespace(fiche={}, rattraper=None)
    assert await action.appliquer_le_mode(a.source, a.p, a.regles, vide, "ajouter", {}) is None and not a.p.get("mode")
    a.p["mode"] = "emporter"
    ctx = SimpleNamespace(fiche={"type_de_commande": "en livraison"}, rattraper=None)
    assert await action.appliquer_le_mode(a.source, a.p, a.regles, ctx, "ajouter", {}) is None and a.p["mode"] == "emporter"


async def test_c3_un_mode_invente_est_un_mode_non_dit(kebab):
    a = await Appel(kebab).charger()
    assert "mode" not in action.sans_mode_invente(a.source, "choisir_mode", {"mode": "rien de précisé", "mots": "une commande"})
    assert action.sans_mode_invente(a.source, "choisir_mode", {"mode": "à emporter"})["mode"] == "à emporter"


async def test_c4_le_moyen_dans_ses_mots(kebab):
    a = await Appel(kebab).charger()
    assert action.moyen_dit(a.source, "en espèces") == "especes"
    assert action.moyen_dit(a.source, "") is None and action.moyen_dit(a.source, "en bitcoins") is None


def test_c5_le_nom_vu_par_le_modele():
    fiche: dict = {}
    retenir_le_nom(fiche, SimpleNamespace(definition={"config": {"action": "choisir_mode"}}), "type_de_commande")
    assert fiche[CLE_NOMS_DES_OUTILS] == {"choisir_mode": "type_de_commande"}
    assert nom_vu(fiche, "choisir_mode") == "type_de_commande" and nom_vu(fiche, "finaliser") == "finaliser" and nom_vu(None, "x") == "x"
