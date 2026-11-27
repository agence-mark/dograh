"""[.mark] Plan final Partie 1, lot 8b-3 (défaut créé par 8b-2, audit 8b-2 « À vérifier ») : « Annulez, et mettez-moi une salmone. » (deux « Salmone » à la carte)
annule puis ajoute un article ambigu : la question « laquelle ? » naît ; le panier n'est pas vide (une question est ouverte sur un article), la commande continue : le client
entend la question, jamais l'annulation seule, et l'issue ``commande_annulee`` n'est pas posée (plan § 17 l.407 : annuler = vider, on recommande dans le même appel)."""

from __future__ import annotations

from api.services.actions_communes import issues as ISSUES
from api.tests.mark.partie_1 import combinaisons as C

SALMONE_DITE = {"ajouter": [{"article": "salmone", "quantite": 1}]}


async def test_annulez_et_une_salmone_la_question_laquelle_est_posee_et_la_commande_continue(faire_monde, monkeypatch):
    """Client (commande commencée) « Annulez, et mettez-moi une salmone. » / avant : le panier compte vide, le fait gardé est l'annulation, « laquelle ? » peut ne pas être posée
    / après : modèle « C'est annulé. Une Salmone … ou … ? » ; la commande continue, pas d'issue ``commande_annulee``."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    await partie._executer("recette", "à emporter", {"mode_de_retrait": "emporter"}, C._inchange)
    await partie._executer("recette", "une margherita normale", {"ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}]}, C._plus(C.MARGHERITA))
    o = await partie._executer("G13", "annulez, et une salmone", {"annuler_la_commande": True, **SALMONE_DITE}, C._inchange)
    assert C.question(o.apres).get("type") == "ambiguite", (C.question(o.apres), o.retour)
    assert (o.fiche or {}).get(ISSUES.CLE_DE_L_ISSUE) != "commande_annulee", ((o.fiche or {}).get(ISSUES.CLE_DE_L_ISSUE), o.textes)
    assert ((o.textes or {}).get("fait_accompli") or {}).get("fait") not in ("annulee", "annulee_en_cours"), o.textes  # le code ne répond pas pour l'annulation avant la question née
    assert not o.apres.get("lignes"), o.apres.get("lignes")  # la margherita est bien annulée : annuler = vider
