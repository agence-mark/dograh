"""[.mark] Clôture de la Partie 1, lot B1 : deux comportements décidés par Evan le 22/11, posés sur le registre des questions.

* DC3 : une proposition (« un Coca ? ») se ferme au premier « non » ou au premier tour sans « oui » ; elle ne revient pas.
* DC5 : un ajout après une annulation est refusé : la commande n'existe plus ; le code le dit et propose d'en passer une nouvelle ; au « oui », une
  commande neuve (l'article se redit), au « non », rien.
"""

from __future__ import annotations

from api.services.actions_communes.parole import CLE_TEXTES_DU_CODE
from api.services.commande import etape as ETAPE_
from api.services.commande import registre as RQ


async def _proposition(e) -> dict:
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = e.p["question"]
    assert q["type"] == "proposition", q
    return q


async def test_dc3_un_tour_sans_oui_ferme_la_proposition(essai_de):
    e = await essai_de()
    await _proposition(e)
    await e.tour("bien cuite s'il vous plaît", note_generale="bien cuite")  # un tour sans « oui » (la fiche ne répond pas à la proposition)
    assert (e.p.get("question") or {}).get("type") != "proposition", e.p.get("question")
    r = await e.tour("c'est tout", c_est_tout=True)
    assert (e.p.get("question") or {}).get("type") == "relecture", (e.p.get("question"), r)  # elle ne revient pas devant la relecture


async def test_dc3_un_changement_pendant_la_proposition_est_pris_et_la_ferme(essai_de):
    e = await essai_de()
    await _proposition(e)
    await e.tour("en fait mettez-en deux", changer_quantite=[{"ligne": 1, "quantite": 2}])
    assert [l["quantite"] for l in e.p["lignes"]] == [2] and (e.p.get("question") or {}).get("type") != "proposition"


async def _annulee(e) -> None:
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = e.p["question"]
    await e.tour("non, et annulez tout", reponse={"question_id": q["id"], "sens": "refuse"}, annuler_la_commande=True)
    assert ETAPE_.courante(e.p) == RQ.ANNULEE, e.p


async def test_dc5_un_ajout_apres_l_annulation_est_refuse_et_une_nouvelle_commande_proposee(essai_de):
    e = await essai_de()
    await _annulee(e)
    r = await e.tour("et une regina normale", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    assert not e.p.get("lignes") and r["refus"][0]["raison"] == "commande_annulee", r
    q = e.p["question"]
    assert q["type"] == RQ.TYPE_NOUVELLE_COMMANDE, q
    assert RQ.TEXTE_NOUVELLE_COMMANDE in " ".join((e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}).values()), "le code le dit lui-même"
    await e.tour("oui, une regina normale", reponse={"question_id": q["id"], "sens": "accepte"}, ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    assert ETAPE_.courante(e.p) == RQ.EN_COURS and [l["nom"] for l in e.p["lignes"]] == ["Regina Normale"] and e.p.get("mode") == "emporter", e.p


async def test_dc5_non_a_la_nouvelle_commande_ne_change_rien(essai_de):
    e = await essai_de()
    await _annulee(e)
    await e.tour("une regina", ajouter=[{"article": "regina", "quantite": 1, "variante": "Normale"}])
    q = e.p["question"]
    await e.tour("non merci", reponse={"question_id": q["id"], "sens": "refuse"})
    assert ETAPE_.courante(e.p) == RQ.ANNULEE and not e.p.get("question") and not e.p.get("lignes"), e.p
