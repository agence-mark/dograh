"""[.mark] Clôture de la Partie 1, lot B4 : la garde qui constate (M6), l'état qui fait foi (M2, M7), les défauts muets (M9).

* Deux cases sur la même ligne dans une fiche (« enlevez-la, non mettez-en deux ») : refusées toutes deux AVANT d'exécuter, avec la question (C8).
* « Oui » au Coca proposé ET un Coca dans ``ajouter`` : un seul Coca (appel 530).
* Une case que ce tour ne montre pas n'écarte qu'elle (M9) ; la fiche refaite sans elle ne refait pas ce qui est déjà fait (M6, point 3).
* Enregistrée : le règlement, le numéro et le prénom redonnés ne changent rien et le disent ; un article sans taille ajouté pose sa question.
* « Non » à la relecture : elle reste posée, le modèle demande ce qu'elle veut changer (C3).
"""

from __future__ import annotations

from api.services.actions_communes import conversation as CONV
from api.tests.mark.partie_1.test_cloture_a2_regles_inversees import _jusqu_a_l_enregistrement

REGINA = {"article": "regina", "quantite": 1, "variante": "Normale"}


async def _avec_une_ligne(e) -> None:
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = CONV.question_de(e.p)
    await e.tour("non", reponse={"question_id": q["id"], "sens": "refuse"})


async def test_deux_choses_sur_la_meme_ligne_sont_refusees_avant_d_executer(essai_de):
    e = await essai_de()
    await _avec_une_ligne(e)
    r = await e.tour("enlevez-la, non mettez-en deux", retirer_article=[1], changer_quantite=[{"ligne": 1, "quantite": 2}])
    assert [l["quantite"] for l in e.p["lignes"]] == [1], e.p["lignes"]
    assert r["refus"][0]["raison"] == "conflit_sur_une_ligne" and "demande-lui" in r["refus"][0]["a_faire"], r


async def test_oui_au_coca_et_un_coca_remis_un_seul_coca(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    await e.tour("une margherita normale", ajouter=[{"article": "margherita", "quantite": 1, "variante": "Normale"}])
    q = CONV.question_de(e.p)
    assert q["type"] == "proposition", q
    await e.tour("oui un coca", reponse={"question_id": q["id"], "sens": "accepte"}, ajouter=[{"article": q["article_propose"], "quantite": 1}])
    assert sum(l["quantite"] for l in e.p["lignes"] if l["nom"].casefold().startswith(q["article_propose"].casefold())) == 1, e.p["lignes"]


async def test_une_case_non_montree_n_ecarte_qu_elle_et_la_fiche_refaite_ne_double_rien(essai_de):
    e = await essai_de()
    await e.tour("à emporter", mode_de_retrait="emporter")
    r = await e.tour("une regina normale, mon numéro est le 06 99 99 99 99", ajouter=[REGINA], telephone="0699999999")
    assert r["refus"][0]["raison"] == "case_sans_objet" and len(e.p["lignes"]) == 1, r
    await e.fiche(ajouter=[REGINA])  # le second passage refait la fiche sans le téléphone
    assert sum(l["quantite"] for l in e.p["lignes"]) == 1, e.p["lignes"]


async def test_enregistree_le_reglement_redonne_ne_change_rien_et_le_dit(essai_de):
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    r = await e.tour("par carte, c'est Léa", moyen_de_paiement="carte_bancaire", prenom="Léa")
    assert r["refus"][0]["raison"] == "deja_fait", r


async def test_enregistree_un_article_sans_taille_pose_sa_question(essai_de):
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    await e.tour("et une regina", ajouter=[{"article": "regina", "quantite": 1}])
    assert (CONV.question_de(e.p) or {}).get("type") == "variante", CONV.question_de(e.p)


async def test_non_a_la_relecture_la_garde_posee(essai_de):
    e = await essai_de()
    await _avec_une_ligne(e)
    await e.tour("c'est tout", c_est_tout=True)
    q = CONV.question_de(e.p)
    r = await e.tour("non", reponse={"question_id": q["id"], "sens": "refuse"})
    assert (CONV.question_de(e.p) or {}).get("type") == "relecture" and "demande-lui ce qu'elle veut changer" in str(r), r


async def _statut_en_base(e) -> str | None:
    numero = (e.p.get("enregistree") or {}).get("numero")
    return await e.monde.c.fetchval("SELECT statut FROM mark.resto_commande WHERE numero::text = $1", str(numero)) if numero else None


async def test_revenir_au_panier_d_avant_ne_perd_jamais_la_commande(essai_de):
    """M2 (test des combinaisons, E18) : une Margherita enregistrée, puis deux, puis de nouveau une : le panier retombe sur la clé anti-doublon de la
    première commande, annulée ; l'anti-doublon la rendait comme « déjà faite » et la commande était perdue. Migration 051."""
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    await e.tour("en fait deux", changer_quantite=[{"ligne": 1, "quantite": 2}])
    await e.tour("non, une seule finalement", changer_quantite=[{"ligne": 1, "quantite": 1}])
    assert e.p.get("enregistree") and await _statut_en_base(e) not in (None, "annulee"), (e.retours[-1], await _statut_en_base(e))


async def test_tout_retirer_d_une_commande_enregistree_demande_l_annulation(essai_de):
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    numero = e.p["enregistree"]["numero"]
    await e.tour("enlevez la margherita", retirer_article=[1])
    assert e.p["enregistree"]["numero"] == numero and e.p["lignes"] and await _statut_en_base(e) != "annulee", e.retours[-1]  # rien n'a changé
    assert (CONV.question_de(e.p) or {}).get("type") == "annulation_enregistree", CONV.question_de(e.p)  # DC4 : la confirmation


async def test_passer_en_livraison_sans_adresse_ne_touche_pas_la_caisse(essai_de):
    e = await essai_de()
    await _jusqu_a_l_enregistrement(e)
    numero = e.p["enregistree"]["numero"]
    r = await e.tour("finalement en livraison", mode_de_retrait="livraison")
    assert e.p["enregistree"]["numero"] == numero and e.p["mode"] == "emporter" and await _statut_en_base(e) != "annulee", r
    assert "adresse" in str(r), r  # ce qui manque est dit au modèle


async def test_dc6_non_merci_a_autre_chose_finit_la_prise(essai_de):
    """DC6 (Evan, 22/11) : « Non merci » à « autre chose ? » (question du modèle, aucune question du registre) = la fin de la prise : la relecture."""
    e = await essai_de()
    await _avec_une_ligne(e)
    assert not CONV.question_de(e.p)
    await e.tour("non merci", reponse={"question_id": "Q-9", "sens": "refuse"})
    assert (CONV.question_de(e.p) or {}).get("type") == "relecture", e.retours[-1]


async def _jusqu_au_numero(e, **reglages):
    await _avec_une_ligne(e)
    await e.tour("c'est tout", c_est_tout=True)
    q = CONV.question_de(e.p)
    await e.tour("oui par carte", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement="carte_bancaire")
    q = CONV.question_de(e.p)
    assert q["type"] == "numero_affiche", q
    await e.tour("non, notez le zéro six quatre-vingt-dix-neuf", reponse={"question_id": q["id"], "sens": "refuse"})
    return await e.tour("zéro six quatre-vingt-dix-neuf, quatre-vingt-dix-neuf, quatre-vingt-dix-neuf, quatre-vingt-dix-neuf, c'est Léa",
                        telephone="0699999999", prenom="Léa")


async def test_dc10_le_numero_dicte_est_relu_et_attend_le_oui(essai_de):
    from api.services.commande import registre as RQ

    e = await essai_de()
    await _jusqu_au_numero(e)
    q = CONV.question_de(e.p) or {}
    dit = " ".join((e.fiche_de_l_appel.get("textes_du_code_de_la_fiche") or {}).values())
    assert q.get("type") == RQ.TYPE_DU_NUMERO_DICTE and not e.p.get("enregistree") and "quatre-vingt-dix-neuf" in dit and dit.count("Je note") == 1, (q, dit)
    await e.tour("oui", reponse={"question_id": q["id"], "sens": "accepte"})
    assert e.p.get("enregistree"), e.retours[-1]


async def test_dc10_eteint_le_numero_dicte_est_enregistre_sans_relecture(essai_de, monkeypatch):
    from api.services.commande import porte

    monkeypatch.setattr(porte, "question_du_numero_dicte", lambda ctx: None)
    e = await essai_de()
    await _jusqu_au_numero(e)
    assert e.p.get("enregistree"), e.retours[-1]
