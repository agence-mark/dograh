"""[.mark] Banc A, famille C1 : le code applique une réponse sans lire les mots, ou à la mauvaise question (bilan du 18/11 § 5).

Chaque test rejoue les VRAIS appels du modèle d'un run de la nuit jusqu'au tour fautif, puis joue l'appel fautif tel que Gemma l'a envoyé,
et vérifie ce que le client voulait. Rouge aujourd'hui = faute du module (ou contrat à deux interprètes, étude § 4 E1). Rien n'est corrigé.

| Test | Run, tour | Ce que le client voulait |
|---|---|---|
| c1_1 | 2636 t5 | « Non merci, c'est tout » à la vente en plus : pas de mousse, on passe à la relecture |
| c1_2 | 2650 t4 | « Non, c'est tout » (même cas, autre run) : pas de Coca |
| c1_3 | 2639 t2 | « Euh non, ce sera tout » : pas de Coca (le sens passé est ``accord``) |
| c1_4 | 2642 t4 | « Oui un coca » à la boisson offerte : un Coca au panier, malgré un ``choix`` superflu |
| c1_5 | 2643 t4 | « Oui, mais un Orangina plutôt » : un Orangina au panier, malgré un ``choix`` superflu |
| c1_6 | 2670 t3 | « Oui » à « Vous voulez dire 4 Formaggi ? » : deux 4 Formaggi au panier |
| c1_7 | 2671 t5 | « Une margherita normale » dit après l'adresse : une Margherita au panier, pas une adresse |
| c1_8 | 2643 t1-t2 | les penne bolognaise de la première phrase ne se perdent pas quand une autre ligne est ambiguë |
| a2_* | idem | l'appel qu'un bon modèle aurait fait (``en_plus`` faux, article sans ``choix``) : doit passer (sépare la faute du code de celle du modèle) |
"""

import pytest

from api.tests.mark.banc_a.commun import appel_de, faire_monde, base_essai, base_prete, jouer_reel, trace  # noqa: F401

pytestmark = pytest.mark.banc_a


async def test_c1_1_2636_non_merci_a_la_vente_en_plus(appel_de):
    a = await appel_de()
    await a.rejouer(2636, jusqu_au_tour=4)
    assert a.p.get("proposition_en_plus"), "la vente en plus doit être posée avant le tour fautif\n" + trace(a)
    r = await jouer_reel(a, 2636, 5)  # valider_la_commande {mots: "Non merci, c'est tout", sens: "accord"}
    assert a.quantite_de("Mousse") == 0, "le client a refusé la mousse, elle est au panier" + trace(a)
    assert r.get("statut") != "OK" or not (r["faits"].get("ajoutes")), trace(a)


async def test_c1_2_2650_non_c_est_tout_a_la_vente_en_plus(appel_de):
    a = await appel_de()
    await a.rejouer(2650, jusqu_au_tour=3)
    await jouer_reel(a, 2650, 4)  # valider_la_commande {mots: "Non, c'est tout", sens: "accord"}
    assert a.quantite_de("Coca") == 0, "le client a refusé le Coca, il est au panier" + trace(a)


async def test_c1_3_2639_euh_non_ce_sera_tout(appel_de):
    a = await appel_de()
    await a.rejouer(2639, jusqu_au_tour=1)
    await jouer_reel(a, 2639, 2)  # valider_la_commande {mots: "Euh non, ce sera tout", sens: "accord"}
    assert a.quantite_de("Coca") == 0, "le client a dit non, le Coca est au panier" + trace(a)


async def test_c1_4_2642_la_boisson_offerte_avec_un_choix_superflu(appel_de):
    a = await appel_de()
    await a.rejouer(2642, jusqu_au_tour=3)
    r = await jouer_reel(a, 2642, 4, outil="ajouter_au_panier")  # {articles: "Coca-Cola", choix: "Coca-Cola", sens: "accord"}
    assert r["statut"] in ("OK", "INCOMPLETE") and a.quantite_de("Coca") == 1, "le client a accepté le Coca offert, il n'est pas au panier" + trace(a)


async def test_c1_5_2643_l_orangina_offert_avec_un_choix_superflu(appel_de):
    a = await appel_de()
    await a.rejouer(2643, jusqu_au_tour=3)
    await jouer_reel(a, 2643, 4, rang=0)  # {articles: "un Orangina offert", choix: "un Orangina plutôt", sens: "modification"}
    assert a.quantite_de("Orangina") == 1, "le client a demandé l'Orangina offert, il n'est pas au panier" + trace(a)


async def test_c1_6_2670_oui_a_une_ambiguite_a_un_candidat(appel_de):
    a = await appel_de()
    await a.rejouer(2670, jusqu_au_tour=2)
    await jouer_reel(a, 2670, 3, rang=0)  # {articles: "deux pizzas 4 fromages en format normal", mots: "Oui", sens: "accord"}
    assert a.quantite_de("4 Formaggi") == 2, "« oui » à « 4 Formaggi ? » : deux 4 Formaggi attendues" + trace(a)


async def test_c1_7_2671_un_article_dit_apres_l_adresse_n_est_pas_une_adresse(appel_de):
    a = await appel_de()
    # Montage : en production la phrase « adresse + consigne » du tour 2 a rendu INTROUVABLE/commune (voir c6_4 : la base de communes de test, elle, retient
    # Chantilly). On pose la même question en attente (celle de l'adresse) par le mode seul.
    a.greffier(type_de_commande="livraison")
    await a.jouer("type_de_commande", {"mode": "livraison", "mots": "livrer"})  # OK/zone : « quelle est l'adresse ? » (comme les tours 2 et 4 de la production)
    assert a.p.get("question_en_attente") == "choisir_mode.adresse" and not a.p.get("zone"), "précondition : question de l'adresse en attente" + trace(a)
    await jouer_reel(a, 2671, 5)  # ajouter_au_panier {articles: "une margherita normale", mots: "Une margherita normale"}
    assert a.quantite_de("Margherita") >= 1, "l'article dit n'est pas au panier (pris pour une adresse ?)" + trace(a)


async def test_c1_8_2643_les_penne_de_la_premiere_phrase_ne_se_perdent_pas(appel_de):
    a = await appel_de()
    await a.rejouer(2643, jusqu_au_tour=2)
    # t1 AMBIGU (margarita) puis t2 « oui » : la ligne des penne bolognaise dite dans la même phrase doit être prise ou faire l'objet d'une question
    penne = a.quantite_de("Bolognese") + a.quantite_de("Penne") + a.quantite_de("Pâtes")
    derniere = a.journal[-1]["retour"]
    assert penne >= 1 or "olognese" in (derniere.get("suggestion") or "") or "penne" in str(derniere.get("faits")).lower(), "les penne bolognaise sont perdues sans un mot" + trace(a)


# --------------------------------------------------------------------------- #
# A2 : l'appel qu'un bon modèle aurait fait (le code doit alors donner le bon panier)
# --------------------------------------------------------------------------- #


async def test_a2_2636_refus_explicite_de_la_vente_en_plus(appel_de):
    a = await appel_de()
    await a.rejouer(2636, jusqu_au_tour=4)
    r = await a.jouer("valider_la_commande", {"mots": "Non merci, c'est tout", "sens": "refus"})
    assert a.quantite_de("Mousse") == 0 and r.get("manque") == "relecture", trace(a)


async def test_a2_2642_l_article_offert_sans_choix(appel_de):
    a = await appel_de()
    await a.rejouer(2642, jusqu_au_tour=3)
    await a.jouer("ajouter_au_panier", {"articles": "Coca-Cola", "mots": "Ah super, oui un coca", "sens": "accord"})
    assert a.quantite_de("Coca") == 1, trace(a)
