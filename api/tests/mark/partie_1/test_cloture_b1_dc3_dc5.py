"""[.mark] Clôture de la Partie 1, lot B1 : deux comportements décidés par Evan le 22/11, posés sur le registre des questions.

* DC3 : une proposition (« un Coca ? ») se ferme au premier « non » ou au premier tour sans « oui » ; elle ne revient pas.
* DC5 : TOMBÉ (§ 17 l.407, décision d'Evan du 24/11 12 h 10) : annuler = vider le panier ; un article dit après entre, dans le même appel.
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.services.commande import etape as ETAPE_
from api.services.commande import registre as RQ


async def _proposition(e) -> dict:
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = CONV.question_de(e.p)
    assert q["type"] == "proposition", q
    return q


async def test_dc3_un_tour_sans_oui_ferme_la_proposition(essai_de):
    e = await essai_de()
    await _proposition(e)
    await e.tour("bien cuite s'il vous plaît", note_generale="bien cuite")  # un tour sans « oui » (la fiche ne répond pas à la proposition)
    assert (CONV.question_de(e.p) or {}).get("type") != "proposition", CONV.question_de(e.p)
    r = await e.tour("c'est tout", c_est_tout=True)
    assert (CONV.question_de(e.p) or {}).get("type") == "relecture", (CONV.question_de(e.p), r)  # elle ne revient pas devant la relecture


async def test_dc3_un_changement_pendant_la_proposition_est_pris_et_la_ferme(essai_de):
    e = await essai_de()
    await _proposition(e)
    await e.tour("en fait mettez-en deux", changer_quantite=[{"ligne": 1, "quantite": 2}])
    assert [l["quantite"] for l in e.p["lignes"]] == [2] and (CONV.question_de(e.p) or {}).get("type") != "proposition"


async def _annulee(e) -> None:
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = CONV.question_de(e.p)
    await e.tour("non, et annulez tout", reponse={"question_id": q["id"], "sens": "refuse"}, annuler_la_commande=True)
    assert ETAPE_.courante(e.p) == RQ.ANNULEE, e.p


async def test_apres_l_annulation_un_ajout_entre_dans_un_panier_vide(essai_de):
    """Périmé (§ 17 l.407, plan final Partie 1 : « annuler = vider, DC5 tombe » ; décision d'Evan du 24/11 12 h 10, ``decisions-du-coordinateur.md:37``) : l'ancien test attendait
    le refus « commande_annulee » et la question « nouvelle commande ». Maintenant l'article entre dans le panier vidé, sans refus ni question, et le mode est gardé."""
    e = await essai_de()
    await _annulee(e)
    assert not e.p.get("lignes"), "annuler = vider le panier"
    r = await e.tour("et une regina normale", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    assert [l["nom"] for l in e.p["lignes"]] == ["Regina Normale"] and not r.get("refus"), (e.p.get("lignes"), r.get("refus"))
    assert ETAPE_.courante(e.p) == RQ.EN_COURS and not e.p.get("annulee") and e.p.get("mode") == "emporter", e.p
    assert (CONV.question_de(e.p) or {}).get("type") != "nouvelle_commande", CONV.question_de(e.p)
