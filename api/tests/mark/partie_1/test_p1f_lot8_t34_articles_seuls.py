"""[.mark] Lot 8, T34 (Pierre, 27/11 10 h 49, ``decisions-du-coordinateur.md``) : « la même fiche qu'au tour d'avant » se compare sur les ARTICLES SEULS, et non mot pour mot.

Une fiche qui redit au tour suivant le(s) même(s) article(s) que le tour d'avant (même article, même quantité, mêmes variante et options), avec ou sans les autres cases (paiement,
prénom, mode, réponse, « c'est tout »), est traitée comme la fiche identique de (c) : rien n'est appliqué, le modèle demande. Client « Une margherita, par carte. » … « Une margherita. »
/ avant : deux margheritas, rien de demandé / après : une margherita, le modèle demande « Une deuxième margherita, ou c'était la même ? » ; « Une de plus. » → deux.
Restent pris sans question : deux articles dont un seul déjà dit ; une quantité, une variante ou une option différente ; le troisième tour identique après la question (question,
pris, question) ; la fiche refaite dans le même tour (T31 R1, ``test_p1f_lot8_t31_fiche_avec_case_ecartee.py``)."""

from __future__ import annotations

from collections import Counter

from api.services.commande import panier as P
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


async def test_vider_le_panier_et_redire_le_meme_article_est_pris(essai_de):
    """La fiche qui change aussi le panier (« on recommence, une margherita ») reste comparée mot pour mot : l'article redit après le vidage entre, sans question."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    r = await e.tour("on recommence, une margherita normale", ajouter=[MARGHERITA], vider_le_panier=True)
    assert RAISON not in _raisons(r) and _margheritas(e) == 1, r


# --------------------------------------------------------------------------- R2 de l'audit T34 : les cases non prises sont dites au modèle


async def test_r2_la_fiche_refusee_dit_au_modele_les_cases_non_prises(essai_de):
    """La fiche refusée comme identique n'applique RIEN, ni le paiement ni le prénom : le fait le dit au modèle (``faits.cases_non_prises``, des noms de cases, jamais une phrase au
    client), pour qu'il les remette dans la fiche refaite. « Une margherita. » … « Par carte, c'est Léa » (la margherita recopiée) / faits : moyen_de_paiement, telephone, prenom."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    r = await e.tour("par carte, c'est Léa", ajouter=[MARGHERITA], **FIN)
    assert RAISON in _raisons(r), r
    assert sorted(r["faits"].get("cases_non_prises") or []) == sorted(FIN), r
    assert "Léa" not in str(r["faits"].get("cases_non_prises")), r  # des noms de cases, pas les valeurs


async def test_r2_sans_autre_case_aucune_case_non_prise(essai_de):
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    r = await e.tour("une margherita normale", ajouter=[MARGHERITA])
    assert RAISON in _raisons(r) and "cases_non_prises" not in r["faits"], r


async def test_r2_la_consigne_dit_de_refaire_la_fiche_sans_l_article_et_cette_fiche_n_ajoute_rien(essai_de):
    """3e passage d'audit T34 : renvoyée telle quelle dans le même tour, la fiche serait encore refusée comme identique ; la consigne dit donc de refaire la fiche avec les cases
    non prises SANS l'article, tant que le client n'a pas répondu à « un de plus ou le même ? ». La fiche refaite ainsi (paiement, numéro, prénom seuls) n'est pas refusée comme
    identique et n'ajoute aucun article ; avant la relecture, ces cases suivent leur ordre habituel (B4 : redemandées à leur tour)."""
    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    r = await e.tour("par carte, c'est Léa", ajouter=[MARGHERITA], **FIN)
    assert RAISON in _raisons(r), r
    assert "sans l'article" in str(r.get("a_faire")) and "un de plus ou le même" in str(r.get("a_faire")), r.get("a_faire")
    r = await e.fiche(**FIN)
    assert RAISON not in _raisons(r) and _margheritas(e) == 1, r


async def test_r2_la_fiche_refaite_sans_l_article_pose_la_case_non_prise(essai_de):
    """La case non prise, remise seule dans la fiche refaite du même tour, est posée : « Une margherita. » … « Une margherita, à emporter. » / refusée (mode non pris) / fiche
    refaite avec le mode seul : à emporter, une margherita."""
    e = await essai_de()
    await e.tour("une margherita normale", ajouter=[MARGHERITA])
    r = await e.tour("une margherita normale, à emporter", ajouter=[MARGHERITA], mode_de_retrait="emporter")
    assert RAISON in _raisons(r) and r["faits"].get("cases_non_prises") == ["mode_de_retrait"], r
    assert "sans l'article" in str(r.get("a_faire")), r.get("a_faire")
    r = await e.fiche(mode_de_retrait="emporter")
    assert RAISON not in _raisons(r) and e.p.get("mode") == "emporter" and _margheritas(e) == 1, r


# --------------------------------------------------------------------------- garde élargie de T31 : la réponse à une question sur l'article n'est jamais « la même fiche »


async def test_la_formule_redite_avec_la_reponse_a_son_etape_n_est_pas_identique(essai_de):
    """« Un menu burger avec un cheeseburger et un coca. » / « Quelle sauce ? » / « Ketchup. » : le modèle redit le menu avec la réponse. La fiche porte une réponse à la question
    posée sur l'article (étape, options) : elle n'est jamais refusée comme identique (la réponse serait perdue) ; un seul menu, sa sauce posée (D01)."""
    from api.services.actions_communes import conversation as CONV

    e = await essai_de()
    await a_emporter(e)
    menu = {"article": "menu burger", "quantite": 1, "composition": ["cheeseburger", "coca"]}
    await e.tour("un menu burger avec un cheeseburger et un coca", ajouter=[menu])
    q = CONV.question_de(e.p)
    assert q.get("type") in ("etape", "variante"), q
    reponse = {"question_id": q["id"], "valeurs": ["ketchup"], **({} if q["type"] == "etape" else {"sens": "accepte"})}
    r = await e.tour("ketchup", ajouter=[menu], reponse=reponse)
    assert RAISON not in _raisons(r) and _combien(e, "menu") == 1, r


# --------------------------------------------------------------------------- R1 de l'audit T34 : la dispense ne couvre que la réponse qui complète l'article en question


REGINA_SANS_TAILLE = {"article": "regina", "quantite": 1}


async def test_r1_la_reponse_qui_ne_choisit_rien_ne_dispense_pas_l_article_redit(essai_de):
    """« Une regina. » / « Quelle taille ? » / « Euh, je sais pas » : le modèle redit la regina avec une réponse ``autre`` sans valeur. Elle ne complète rien : la fiche est jugée
    sur ses articles (T34), la question « un de plus ou le même ? », jamais une seconde regina sans rien demander."""
    from api.services.actions_communes import conversation as CONV

    e = await essai_de()
    await a_emporter(e)
    await e.tour("une regina", ajouter=[REGINA_SANS_TAILLE])
    q = CONV.question_de(e.p)
    assert q and q.get("type") == "variante" and _combien(e, "regina") == 1, q
    r = await e.tour("euh, je sais pas", ajouter=[REGINA_SANS_TAILLE], reponse={"question_id": q["id"], "sens": "autre"})
    assert _combien(e, "regina") == 1, r
    assert RAISON in _raisons(r), r


async def test_r1_l_autre_article_redit_avec_la_reponse_pose_la_question(essai_de):
    """« Une margherita et une regina. » (la margherita prise, la regina attend sa taille) / « Normale. » : le modèle redit la margherita ET la regina avec la réponse. La regina est
    complétée par la réponse ; la margherita redite est jugée comme T34 : la question, jamais une seconde margherita sans rien demander, et la taille n'est pas perdue (la fiche est
    refaite avec la réponse seule)."""
    from api.services.actions_communes import conversation as CONV

    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale et une regina", ajouter=[MARGHERITA, REGINA_SANS_TAILLE])
    q = CONV.question_de(e.p)
    assert q and q.get("type") == "variante" and _margheritas(e) == 1 and _combien(e, "regina") == 1, q
    reponse = {"question_id": q["id"], "sens": "accepte", "valeurs": ["Normale"]}
    r = await e.tour("normale", ajouter=[MARGHERITA, REGINA_SANS_TAILLE], reponse=reponse)
    assert _margheritas(e) == 1 and _combien(e, "regina") == 1, r
    assert RAISON in _raisons(r) and "reponse" in (r["faits"].get("cases_non_prises") or []), r
    r = await e.fiche(reponse=reponse)
    assert RAISON not in _raisons(r) and _margheritas(e) == 1 and _combien(e, "regina") == 1, r
    assert not P.a_completer(e.p), e.p  # la regina a sa taille


async def _cas_2_refuse(essai_de):
    """Le cas 2 de R1 jusqu'à la fiche refusée : la margherita prise, la regina qui attend sa taille, « Normale » redite avec les deux articles. Rend (l'essai, le retour, la réponse)."""
    from api.services.actions_communes import conversation as CONV

    e = await essai_de()
    await a_emporter(e)
    await e.tour("une margherita normale et une regina", ajouter=[MARGHERITA, REGINA_SANS_TAILLE])
    q = CONV.question_de(e.p)
    reponse = {"question_id": q["id"], "sens": "accepte", "valeurs": ["Normale"]}
    r = await e.tour("normale", ajouter=[MARGHERITA, REGINA_SANS_TAILLE], reponse=reponse)
    assert RAISON in _raisons(r), r
    return e, r, reponse


async def test_r1_les_articles_rendus_au_modele_sont_ceux_que_la_reponse_ne_complete_pas(essai_de):
    """Audit du correctif R1, point 1 : ``faits.articles`` (ce que le modèle demande « un de plus ou le même ? ») ne porte que la margherita ; la regina vient d'avoir sa taille,
    la redemander ferait croire au client qu'elle est en double."""
    _, r, _ = await _cas_2_refuse(essai_de)
    assert r["faits"]["articles"] == [{"article": "margherita", "quantite": 1}], r["faits"]


async def test_r1_la_fiche_jamais_refaite_laisse_la_taille_en_attente_et_bloque_la_relecture(essai_de):
    """Audit du correctif R1, point 2 (garde) : le modèle ne refait PAS la fiche avec la réponse seule. La regina attend toujours sa taille, sa question reste posée ; « c'est
    tout » ne mène jamais à la relecture avec le total tant que la taille manque : elle n'est jamais perdue en silence."""
    from api.services.actions_communes import conversation as CONV

    e, _, _ = await _cas_2_refuse(essai_de)
    assert P.a_completer(e.p), e.p
    for _ in range(3):
        q = CONV.question_de(e.p) or {}
        assert q.get("type") == "variante", q
        r = await e.tour("non merci, c'est tout", c_est_tout=True, **FIN)
        assert (CONV.question_de(e.p) or {}).get("type") != "relecture" and not e.p.get("relecture"), (e.p.get("relecture"), r)
        assert P.a_completer(e.p) and _margheritas(e) == 1 and _combien(e, "regina") == 1, e.p
