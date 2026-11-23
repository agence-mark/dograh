"""[.mark] Clôture de la Partie 1, correctifs du contrôle long (23/11), sous-agent 1 : trois règles tenues à la source, jamais un cas de plus.

* Famille 1, RC2 + RC13 : tout ou rien PAR CASE, jamais par fiche. « Une regina et un bubble tea » : la regina entre (ou reste gardée du mode et de la zone),
  le bubble tea est dit introuvable ; aucun article connu n'est perdu parce qu'un autre est inconnu.
* Famille 2, RC4 + RC8 + DC5 : une fiche qui annule la commande n'y laisse rien entrer (l'article, le mode, « c'est tout » de la même fiche sont refusés avec
  la raison) et le code dit l'annulation.
* Famille 3, RC10 : « c'est tout » avec un article encore en doute dans le registre ne marque pas la relecture comme faite sans la dire : on finit ce qui
  est commencé avant de relire (ordre du registre), la question en doute reste la seule posée.
"""

from __future__ import annotations

from api.services.commande import registre as RQ
from api.services.commande.porte import CLE_TEXTES_DU_CODE

REGINA = {"article": "regina", "quantite": 1, "variante": "Normale"}
BUBBLE_TEA = {"article": "bubble tea", "quantite": 1}


def _dit_par_le_code(e) -> str:
    return " ".join((e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}).values())


def _noms(e) -> list[str]:
    return [l["nom"] for l in e.p.get("lignes") or []]


async def test_famille_1_l_article_connu_entre_a_cote_d_un_inconnu(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une regina et un bubble tea", ajouter=[REGINA, BUBBLE_TEA])
    assert _noms(e) == ["Regina Normale"], e.p.get("lignes")
    assert "bubble tea" in _dit_par_le_code(e), _dit_par_le_code(e)  # l'inconnu est dit introuvable, il ne prend pas la regina avec lui


async def test_famille_1_l_article_connu_est_garde_du_mode_a_cote_d_un_inconnu(essai_de):
    """Avant le mode, les deux sont gardés tels que dits : la regina n'est pas perdue, le bubble tea est dit introuvable quand le mode les prend."""
    e = await essai_de()
    await e.tour("une regina et un bubble tea", ajouter=[REGINA, BUBBLE_TEA])
    assert {d["texte"] for d in e.p.get("dits_en_attente") or []} == {"regina", "bubble tea"}, e.p.get("dits_en_attente")
    await e.tour("à emporter", mode_de_retrait="emporter")
    assert _noms(e) == ["Regina Normale"], e.p.get("lignes")
    assert "bubble tea" in _dit_par_le_code(e), _dit_par_le_code(e)


async def test_famille_2_annuler_dans_la_fiche_n_y_laisse_rien_entrer(essai_de):
    """« Une regina, et annulez tout » : annulée, le panier reste vide (DC5, RC8) et le code le dit (RC4)."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("une regina, et annulez tout", ajouter=[REGINA], annuler_la_commande=True)
    assert e.p.get("annulee") and not e.p.get("lignes"), e.p.get("lignes")
    assert _dit_par_le_code(e) == "Je ne l'enregistre pas.", _dit_par_le_code(e)
    assert [x["raison"] for x in r.get("refus") or []] == ["commande_annulee"] and r["refus"][0]["a_faire"], r.get("refus")


async def test_famille_2_ni_le_mode_ni_c_est_tout_ne_survivent_a_l_annulation(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    await e.tour("annulez, finalement en livraison, c'est tout", annuler_la_commande=True, mode_de_retrait="livraison", c_est_tout=True)
    assert e.p.get("annulee") and e.p.get("mode") == "emporter" and RQ.phase(e.p) == RQ.ANNULEE, e.p
    assert not e.p.get("relecture") and _dit_par_le_code(e) == "Je ne l'enregistre pas.", _dit_par_le_code(e)


async def test_famille_3_c_est_tout_attend_l_article_en_doute(essai_de):
    """RC10 : l'ambiguïté « Salmone » est ouverte ; « une regina, c'est tout » ne fait pas une relecture que la personne n'entendrait pas."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une salmone", ajouter=[{"article": "salmone", "quantite": 1}])
    q = e.p["question"]
    assert q["type"] == "ambiguite", q
    r = await e.tour("une regina normale, c'est tout", ajouter=[REGINA], c_est_tout=True)
    assert not e.p.get("relecture"), e.p.get("relecture")  # rien de marqué « relu » sans avoir été dit
    assert e.p["question"]["type"] == "ambiguite" and e.p["question"]["id"] == q["id"], e.p["question"]
    assert _noms(e) == ["Regina Normale"] and "c_est_tout" in [x for c in r.get("refus") or [] for x in c["cases"]], r.get("refus")


async def test_famille_2_le_refus_du_reglement_n_annule_pas_l_annulation(essai_de):
    """À la relecture, « annulez, par carte, c'est Léa » : le règlement est refusé (la relecture n'est pas acceptée), l'annulation voulue est faite et dite."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    await e.tour("non merci", reponse={"question_id": e.p["question"]["id"], "sens": "refuse"})
    await e.tour("c'est tout", c_est_tout=True)
    assert e.p["question"]["type"] == "relecture", e.p.get("question")
    await e.tour("annulez, par carte, c'est Léa", annuler_la_commande=True, moyen_de_paiement="carte_bancaire", prenom="Léa")
    assert e.p.get("annulee") and not e.p.get("lignes"), e.p.get("lignes")
    assert _dit_par_le_code(e) == "Je ne l'enregistre pas.", _dit_par_le_code(e)
