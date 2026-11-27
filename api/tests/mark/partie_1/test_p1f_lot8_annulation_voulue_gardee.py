"""[.mark] Lot 8b-2 (commit dd64d0e8, RC4) : le refus d'une AUTRE case de la fiche n'écarte pas l'annulation voulue.

Client (commande commencée, une margherita, pas encore relue) « Annulez tout, et livrez-moi par drone. » / le mode « drone » n'est pas à la carte (valeur hors liste, refus de cette case)
/ avant : le refus écartait aussi « annuler », la commande restait pleine et le modèle ne disait pas l'annulation / après : le panier est vidé, l'annulation est le fait gardé."""

from __future__ import annotations

from api.tests.mark.partie_1 import combinaisons as C


async def test_un_mode_refuse_n_ecarte_pas_l_annulation_voulue(faire_monde, monkeypatch):
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    await partie._executer("recette", "à emporter", {"mode_de_retrait": "emporter"}, C._inchange)
    await partie._executer("recette", "une margherita normale", {"ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}]}, C._plus(C.MARGHERITA))
    o = await partie._executer("G13", "annulez tout, et livrez-moi par drone", {"annuler_la_commande": True, "mode_de_retrait": "drone"}, C._vide)
    assert "mode_de_retrait" in str(o.retour.get("cases_refusees")), o.retour.get("cases_refusees")  # l'autre case est bien refusée
    assert "annuler_la_commande" in (o.retour.get("cases_executees") or []), o.retour.get("cases_executees")
    assert o.apres.get("annulee") and not o.apres.get("lignes"), (o.apres.get("annulee"), o.apres.get("lignes"))
    assert (o.textes or {}).get("fait_accompli") == {"fait": "annulee_en_cours"}, o.textes
