"""[.mark] Clôture de la Partie 1, correctifs du contrôle long (23/11), sous-agent 1 : trois règles tenues à la source, jamais un cas de plus.

* Famille 1, RC2 + RC13 : tout ou rien PAR CASE, jamais par fiche. « Une regina et un bubble tea » : la regina entre (ou reste gardée du mode et de la zone),
  le bubble tea est dit introuvable ; aucun article connu n'est perdu parce qu'un autre est inconnu.
* Famille 2, RC4 + RC8 + DC5 : une fiche qui annule la commande n'y laisse rien entrer (l'article, le mode, « c'est tout » de la même fiche sont refusés avec
  la raison) et l'annulation est dite (par le modèle depuis C6 n° 7, décision d'Evan 25/11 9 h 30).
* Famille 3, RC10 : « c'est tout » avec un article encore en doute dans le registre ne marque pas la relecture comme faite sans la dire : on finit ce qui
  est commencé avant de relire (ordre du registre), la question en doute reste la seule posée.
"""

from __future__ import annotations

from api.services.actions_communes import journal_du_dit as J
from api.services.actions_communes import conversation as CONV
from api.services.commande import etape as ETAPE_
from api.services.commande import registre as RQ
from api.services.commande.porte import CLE_TEXTES_DU_CODE

REGINA = {"article": "regina", "quantite": 1, "variante": "Normale"}
BUBBLE_TEA = {"article": "bubble tea", "quantite": 1}


def _dit_par_le_code(e) -> str:
    # C6 (décision d'Evan 25/11 9 h 30) : ce que le code dit à la voix : ``avant`` et ``suffixe`` (les autres textes, valeurs exigées et fait gardé au journal, ne sont pas dits)
    return " ".join(str(v) for k, v in (e.fiche_de_l_appel.get(CLE_TEXTES_DU_CODE) or {}).items() if k in ("avant", "suffixe") and v)


def _noms(e) -> list[str]:
    return [l["nom"] for l in e.p.get("lignes") or []]


def _l_inconnu_est_un_fait_pour_le_modele(r) -> bool:
    """7b-B (Q1) et R = A : l'introuvable n'est plus dit par le code d'avance, c'est un refus donné au modèle en faits (``refus_de_la_fiche``), et sa phrase est celle du fait bloquant, lue par le repli."""
    refus = (r.get("faits") or {}).get("refus_de_la_fiche") or []
    return [(x["statut_du_module"], x["faits"].get("dit")) for x in refus] == [("INTROUVABLE", "bubble tea")]


async def test_famille_1_l_article_connu_entre_a_cote_d_un_inconnu(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("une regina et un bubble tea", ajouter=[REGINA, BUBBLE_TEA])
    assert _noms(e) == ["Regina Normale"], e.p.get("lignes")
    assert _l_inconnu_est_un_fait_pour_le_modele(r), r.get("faits")  # l'inconnu est dit introuvable (par le modèle), il ne prend pas la regina avec lui
    # C6 n° 11 (décision d'Evan 25/11 9 h 30) : le prix de la proposition de boisson qui suit est un fait que le modèle dit ; le code ne dit plus l'introuvable
    assert "bubble tea" not in _dit_par_le_code(e), _dit_par_le_code(e)


async def test_famille_1_l_article_connu_est_garde_du_mode_a_cote_d_un_inconnu(essai_de):
    """Avant le mode, les deux sont gardés tels que dits : la regina n'est pas perdue, le bubble tea est dit introuvable quand le mode les prend."""
    e = await essai_de()
    await e.tour("une regina et un bubble tea", ajouter=[REGINA, BUBBLE_TEA])
    assert {d["texte"] for d in e.p.get("dits_en_attente") or []} == {"regina", "bubble tea"}, e.p.get("dits_en_attente")
    r = await e.tour("à emporter", mode_de_retrait="emporter")
    assert _noms(e) == ["Regina Normale"], e.p.get("lignes")
    assert _l_inconnu_est_un_fait_pour_le_modele(r), r.get("faits")
    assert "bubble tea" not in _dit_par_le_code(e), _dit_par_le_code(e)


async def test_famille_2_annuler_dans_la_fiche_n_y_laisse_rien_entrer(essai_de):
    """« Une regina, et annulez tout » : annulée, le panier reste vide (DC5, RC8) et le code le dit (RC4)."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("une regina, et annulez tout", ajouter=[REGINA], annuler_la_commande=True)
    assert e.p.get("annulee") and not e.p.get("lignes"), e.p.get("lignes")
    assert _dit_par_le_code(e) == "" and J.fait_accompli(e.p) == "Je ne l'enregistre pas.", (_dit_par_le_code(e), J.fait_accompli(e.p))  # C6 n° 7 (décision d'Evan 25/11 9 h 30) : le modèle le dit
    assert [x["raison"] for x in r.get("refus") or []] == ["commande_annulee"] and r["refus"][0]["a_faire"], r.get("refus")


async def test_famille_2_ni_le_mode_ni_c_est_tout_ne_survivent_a_l_annulation(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    await e.tour("annulez, finalement en livraison, c'est tout", annuler_la_commande=True, mode_de_retrait="livraison", c_est_tout=True)
    assert e.p.get("annulee") and e.p.get("mode") == "emporter" and ETAPE_.courante(e.p) == RQ.ANNULEE, e.p
    assert not e.p.get("relecture") and _dit_par_le_code(e) == "" and J.fait_accompli(e.p) == "Je ne l'enregistre pas.", (_dit_par_le_code(e), J.fait_accompli(e.p))  # C6 n° 7 (décision d'Evan 25/11 9 h 30) : le modèle le dit


async def test_famille_3_c_est_tout_attend_l_article_en_doute(essai_de):
    """RC10 : l'ambiguïté « Salmone » est ouverte ; « une regina, c'est tout » ne fait pas une relecture que la personne n'entendrait pas."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une salmone", ajouter=[{"article": "salmone", "quantite": 1}])
    q = CONV.question_de(e.p)
    assert q["type"] == "ambiguite", q
    r = await e.tour("une regina normale, c'est tout", ajouter=[REGINA], c_est_tout=True)
    assert not e.p.get("relecture"), e.p.get("relecture")  # rien de marqué « relu » sans avoir été dit
    assert CONV.question_de(e.p)["type"] == "ambiguite" and CONV.question_de(e.p)["id"] == q["id"], CONV.question_de(e.p)
    assert _noms(e) == ["Regina Normale"] and "c_est_tout" in [x for c in r.get("refus") or [] for x in c["cases"]], r.get("refus")


async def test_famille_2_le_refus_du_reglement_n_annule_pas_l_annulation(essai_de):
    """À la relecture, « annulez, par carte, c'est Léa » : le règlement est refusé (la relecture n'est pas acceptée), l'annulation voulue est faite et dite."""
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    await e.tour("non merci", reponse={"question_id": CONV.question_de(e.p)["id"], "sens": "refuse"})
    await e.tour("c'est tout", c_est_tout=True)
    assert CONV.question_de(e.p)["type"] == "relecture", CONV.question_de(e.p)
    await e.tour("annulez, par carte, c'est Léa", annuler_la_commande=True, moyen_de_paiement="carte_bancaire", prenom="Léa")
    assert e.p.get("annulee") and not e.p.get("lignes"), e.p.get("lignes")
    assert _dit_par_le_code(e) == "" and J.fait_accompli(e.p) == "Je ne l'enregistre pas.", (_dit_par_le_code(e), J.fait_accompli(e.p))  # C6 n° 7 (décision d'Evan 25/11 9 h 30) : le modèle le dit
