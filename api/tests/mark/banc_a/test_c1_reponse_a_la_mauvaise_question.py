"""[.mark] Banc A, famille C1 : le code applique une réponse sans lire les mots, ou à la mauvaise question (bilan du 18/11 § 5).

Lot 3 (D48) : chaque test rejoue les runs de la nuit écrits en FICHES (``fiches_des_runs.py``) jusqu'au tour fautif, puis joue la fiche de ce tour,
et vérifie la même règle du code qu'avant. Un run qui ne s'écrit pas en fiche sans choisir un sens est en ``xfail(strict=True)`` (a-trancher).

| Test | Run, tour | La règle du code |
|---|---|---|
| c1_1 | 2636 t5 | « Non merci, c'est tout » à la vente en plus : la proposition n'entre pas au panier |
| c1_2 | 2650 t4 | même règle, autre run (xfail : ``sens: accord`` sur un refus dit) |
| c1_3 | 2639 t2 | « Euh non, ce sera tout » : pas de Coca |
| c1_4 | 2642 t4 | « Oui un coca » à la boisson proposée : la proposition au panier |
| c1_5 | 2643 t4 | « Oui, mais un Orangina plutôt » (xfail : le run 2643 ne s'écrit pas sans choix) |
| c1_6 | 2670 t3 | « Oui » à « Vous voulez dire 4 Formaggi ? » (xfail : le run 2670 ne s'écrit pas sans choix) |
| c1_7 | 2671 t5 | « Une margherita normale » dite après l'adresse : une Margherita au panier, pas une adresse |
| c1_8 | 2643 t1-t2 | les penne de la première phrase ne se perdent pas (xfail : run 2643) |
| a2_* | idem | la fiche qu'un bon modèle aurait faite : doit passer |
"""

import pytest

from api.services.actions_communes import conversation as CONV
from api.tests.mark.banc_a.commun import (  # noqa: F401
    TranscriptionManquante,
    appel_de,
    base_essai,
    base_prete,
    faire_monde,
    jouer_tour,
    trace,
)
from api.tests.mark.banc_a.fiches_des_runs import SANS_TRANSCRIPTION

pytestmark = pytest.mark.banc_a


def sans_fiches(run: int):
    return pytest.mark.xfail(strict=True, raises=TranscriptionManquante, reason=f"run {run} sans fiches (a-trancher) : {SANS_TRANSCRIPTION[run]}")


async def test_c1_1_2636_non_merci_a_la_vente_en_plus(appel_de):
    a = await appel_de()
    await a.rejouer(2636, jusqu_au_tour=4)
    assert (CONV.question_de(a.p) or {}).get("type") == "proposition", "la vente en plus doit être posée avant le tour fautif\n" + trace(a)
    proposee = CONV.question_de(a.p).get("article_propose") or "Mousse"
    await jouer_tour(a, 2636, 5)
    assert a.quantite_de(proposee) == 0, "le client a refusé la proposition, elle est au panier" + trace(a)


@sans_fiches(2650)
async def test_c1_2_2650_non_c_est_tout_a_la_vente_en_plus(appel_de):
    a = await appel_de()
    await a.rejouer(2650, jusqu_au_tour=3)
    await jouer_tour(a, 2650, 4)
    assert a.quantite_de("Coca") == 0, "le client a refusé le Coca, il est au panier" + trace(a)


async def test_c1_3_2639_euh_non_ce_sera_tout(appel_de):
    a = await appel_de()
    await a.rejouer(2639, jusqu_au_tour=1)
    await jouer_tour(a, 2639, 2)
    assert a.quantite_de("Coca") == 0, "le client a dit non, le Coca est au panier" + trace(a)


async def test_c1_4_2642_la_boisson_offerte_avec_un_choix_superflu(appel_de):
    a = await appel_de()
    await a.rejouer(2642, jusqu_au_tour=3)
    proposee = (CONV.question_de(a.p) or {}).get("article_propose")
    assert proposee, "précondition : une proposition en attente\n" + trace(a)
    await jouer_tour(a, 2642, 4)
    assert a.quantite_de(proposee) == 1, "le client a accepté la proposition, elle n'est pas au panier" + trace(a)


@sans_fiches(2643)
async def test_c1_5_2643_l_orangina_offert_avec_un_choix_superflu(appel_de):
    a = await appel_de()
    await a.rejouer(2643, jusqu_au_tour=3)
    await jouer_tour(a, 2643, 4)
    assert a.quantite_de("Orangina") == 1, "le client a demandé l'Orangina offert, il n'est pas au panier" + trace(a)


@sans_fiches(2670)
async def test_c1_6_2670_oui_a_une_ambiguite_a_un_candidat(appel_de):
    a = await appel_de()
    await a.rejouer(2670, jusqu_au_tour=2)
    await jouer_tour(a, 2670, 3)
    assert a.quantite_de("4 Formaggi") == 2, "« oui » à « 4 Formaggi ? » : deux 4 Formaggi attendues" + trace(a)


async def test_c1_7_2671_un_article_dit_apres_l_adresse_n_est_pas_une_adresse(appel_de):
    a = await appel_de()
    await a.jouer_la_fiche("livrer", {"mode_de_retrait": "livraison"})
    assert a.p.get("mode") == "livraison" and not a.p.get("zone"), "précondition : l'adresse manque" + trace(a)
    await jouer_tour(a, 2671, 5)
    garde = " ".join(str(d) for d in a.p.get("dits_en_attente") or []).lower()  # sans adresse, l'article est gardé et pris dès qu'elle est posée
    assert (a.quantite_de("Margherita") >= 1 or "margherita" in garde) and not a.p.get("adresse"), "l'article dit est perdu ou pris pour une adresse" + trace(a)


@sans_fiches(2643)
async def test_c1_8_2643_les_penne_de_la_premiere_phrase_ne_se_perdent_pas(appel_de):
    a = await appel_de()
    await a.rejouer(2643, jusqu_au_tour=2)
    assert a.quantite_de("Bolognese") + a.quantite_de("Penne") + a.quantite_de("Pâtes") >= 1, "les penne bolognaise sont perdues" + trace(a)


# --------------------------------------------------------------------------- #
# A2 : la fiche qu'un bon modèle aurait faite (le code doit alors donner le bon panier)
# --------------------------------------------------------------------------- #


async def test_a2_2636_refus_explicite_de_la_vente_en_plus(appel_de):
    a = await appel_de()
    await a.rejouer(2636, jusqu_au_tour=4)
    proposee = (CONV.question_de(a.p) or {}).get("article_propose") or "Mousse"
    await a.jouer_la_fiche("Non merci, c'est tout", {"c_est_tout": True, "reponse": {"question_id": "?", "sens": "refuse"}})
    assert a.quantite_de(proposee) == 0 and (CONV.question_de(a.p) or {}).get("type") == "relecture", trace(a)


async def test_a2_2642_l_article_offert_sans_choix(appel_de):
    a = await appel_de()
    await a.rejouer(2642, jusqu_au_tour=3)
    proposee = (CONV.question_de(a.p) or {}).get("article_propose")
    await a.jouer_la_fiche("Ah super, oui", {"reponse": {"question_id": "?", "sens": "accepte"}})
    assert proposee and a.quantite_de(proposee) == 1, trace(a)
