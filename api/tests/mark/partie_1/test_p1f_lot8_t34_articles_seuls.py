"""[.mark] Lot 8, T34 (Pierre, 27/11 10 h 49, ``decisions-du-coordinateur.md``) : « la même fiche qu'au tour d'avant » se compare sur les ARTICLES SEULS, et non mot pour mot.

Une fiche qui redit au tour suivant le(s) même(s) article(s) que le tour d'avant (même article, même quantité, mêmes variante et options), avec ou sans les autres cases (paiement,
prénom, mode, réponse, « c'est tout »), est traitée comme la fiche identique de (c) : rien n'est appliqué, le modèle demande. Client « Une margherita, par carte. » … « Une margherita. »
/ avant : deux margheritas, rien de demandé / après : une margherita, le modèle demande « Une deuxième margherita, ou c'était la même ? » ; « Une de plus. » → deux.
Restent pris sans question : deux articles dont un seul déjà dit ; une quantité, une variante ou une option différente ; le troisième tour identique après la question (question,
pris, question) ; la fiche refaite dans le même tour (T31 R1, ``test_p1f_lot8_t31_fiche_avec_case_ecartee.py``)."""

from __future__ import annotations

from collections import Counter

from api.tests.mark.partie_1.aides_de_la_commande import a_emporter

MARGHERITA = {"article": "margherita", "quantite": 1, "variante": "Normale"}
REGINA = {"article": "regina", "quantite": 1, "variante": "Normale"}
FIN = {"moyen_de_paiement": "carte_bancaire", "telephone": "0612345678", "prenom": "Léa"}
RAISON = "fiche_identique_au_tour_d_avant"


def _quantites(e) -> Counter:
    c: Counter = Counter()
    for ligne in e.p["lignes"]:
        c[ligne["nom"].casefold()] += ligne["quantite"]
    return c


def _combien(e, article: str) -> int:
    return sum(q for nom, q in _quantites(e).items() if article in nom)


def _margheritas(e) -> int:
    return _combien(e, "margherita")


def _raisons(r: dict) -> set[str]:
    return {str(x) for x in [r.get("raison"), *((x or {}).get("raison") for x in r.get("refus") or [])] if x}


# --------------------------------------------------------------------------- le défaut : une PARTIE de la fiche redite au tour suivant


async def test_l_article_redit_sans_le_paiement_pose_la_question(essai_de):
    """L'exemple de Pierre : « Une margherita, par carte. » puis « Une margherita. » : la question, une seule margherita ; « Une de plus. » en fait deux."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale, par carte", ajouter=[MARGHERITA], moyen_de_paiement="carte_bancaire")
    assert _margheritas(e) == 1
    r = await e.tour("une margherita normale", ajouter=[MARGHERITA])
    assert RAISON in _raisons(r) and _margheritas(e) == 1, r
    assert r["faits"]["articles"] == [{"article": "margherita", "quantite": 1}], r
    r = await e.tour("une de plus", ajouter=[MARGHERITA])
    assert RAISON not in _raisons(r) and _margheritas(e) == 2, r


async def test_l_article_redit_sans_le_paiement_le_numero_et_le_prenom_pose_la_question(essai_de):
    """Les cases du tour d'avant écartées (pas encore montrées) ou prises, peu importe : l'article seul redit est la même fiche."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale, par carte, zéro six douze trente-quatre cinquante-six soixante-dix-huit, c'est Léa", ajouter=[MARGHERITA], **FIN)
    assert _margheritas(e) == 1
    r = await e.tour("une margherita normale", ajouter=[MARGHERITA])
    assert RAISON in _raisons(r) and _margheritas(e) == 1, r


async def test_l_article_redit_avec_d_autres_cases_pose_la_question(essai_de):
    """Le sens inverse : « Une margherita. » puis la même margherita avec le paiement et le prénom. Les articles seuls comptent : la question, jamais un second article sans rien
    demander (le modèle qui recopie sa fiche d'avant en y ajoutant ce que la personne vient de dire)."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    r = await e.tour("par carte, c'est Léa", ajouter=[MARGHERITA], **FIN)
    assert RAISON in _raisons(r) and _margheritas(e) == 1, r


async def test_l_article_redit_avec_c_est_tout_pose_la_question(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    r = await e.tour("une margherita normale, c'est tout", ajouter=[MARGHERITA], c_est_tout=True)
    assert RAISON in _raisons(r) and _margheritas(e) == 1, r


# --------------------------------------------------------------------------- gardés intacts


async def test_deux_articles_dont_un_seul_deja_dit_sont_pris_sans_question(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale, par carte", ajouter=[MARGHERITA], moyen_de_paiement="carte_bancaire")
    r = await e.tour("une margherita normale et une regina normale", ajouter=[MARGHERITA, REGINA])
    assert RAISON not in _raisons(r) and _margheritas(e) == 2 and _combien(e, "regina") == 1, r


async def test_une_quantite_differente_est_prise(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale, par carte", ajouter=[MARGHERITA], moyen_de_paiement="carte_bancaire")
    r = await e.tour("deux margheritas normales", ajouter=[{**MARGHERITA, "quantite": 2}])
    assert RAISON not in _raisons(r) and _margheritas(e) == 3, r


async def test_une_variante_differente_est_prise(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale, par carte", ajouter=[MARGHERITA], moyen_de_paiement="carte_bancaire")
    r = await e.tour("une margherita mega", ajouter=[{**MARGHERITA, "variante": "Mega"}])
    assert RAISON not in _raisons(r) and _margheritas(e) == 2, r


async def test_une_option_differente_est_prise(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale, par carte", ajouter=[MARGHERITA], moyen_de_paiement="carte_bancaire")
    r = await e.tour("une margherita normale base crème", ajouter=[{**MARGHERITA, "supplements": ["crème"]}])
    assert RAISON not in _raisons(r), r


async def test_trois_tours_avec_le_meme_article_question_pris_question(essai_de):
    """(c) tenu sur les articles seuls : la question, puis « un de plus » pris, puis la question encore."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale, par carte", ajouter=[MARGHERITA], moyen_de_paiement="carte_bancaire")
    r = await e.tour("une margherita normale", ajouter=[MARGHERITA])
    assert RAISON in _raisons(r) and _margheritas(e) == 1, r
    r = await e.tour("une de plus, c'est Léa", ajouter=[MARGHERITA], prenom="Léa")
    assert RAISON not in _raisons(r) and _margheritas(e) == 2, r
    r = await e.tour("une margherita normale", ajouter=[MARGHERITA])
    assert RAISON in _raisons(r) and _margheritas(e) == 2, r
