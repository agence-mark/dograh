"""[.mark] Plan final Partie 1, lot 8b-2 (E7, E8, R1 ; décision d'Evan du 24/11 12 h 10, plan § 17 l.407 : « annuler pendant l'appel = vider le panier, on peut recommander
dans le même appel, DC5 tombe ») : annuler une commande retenue, puis en dire une autre, reprend la MÊME ligne en base (même numéro, même numéro court) ; la caisse ne reçoit
qu'un envoi à la fin, la nouvelle commande, jamais l'annulée ; rien ne se perd.

| Test | Ce qu'il prouve |
|---|---|
| annulée puis une regina | « annulez », « oui », « une regina » : la regina entre, la ligne annulée est rouverte (même numéro court), un envoi à la fin avec la regina seule |
| annulée et la regina dans la même fiche | le « oui » à l'annulation et l'article dans UNE fiche : l'article entre (l'ancien refus « commande_annulee » tombe) |
| annulée, recommandée, annulée | la seconde annulation annule la même ligne ; rien ne part |
| annulée en cours, puis une regina | avant tout enregistrement : « annulez » vide, la regina entre ; aucune question « nouvelle commande » |
"""

from __future__ import annotations

from api.tests.mark.partie_1 import combinaisons as C

REGINA_DITE = {"ajouter": [{"article": "regina", "quantite": 1, "variante": "Normale"}]}


async def _annuler(partie: C.Partie, avec: dict | None = None) -> C.Observation:
    """DC4 : la question posée, puis le « oui » (avec, dans la même fiche, ce que le client dit en plus)."""
    o = await partie._executer("A", "finalement j'annule", {"annuler_une_commande_enregistree": True}, C._inchange)
    q = C.question(o.apres)
    assert q.get("type") == "annulation_enregistree", (q, o.retour)
    return await partie._executer("O", "oui", {"reponse": {"question_id": q.get("id"), "sens": "accepte"}, **(avec or {})}, C._inchange)


async def _jusqu_a_l_enregistrement(partie: C.Partie) -> None:
    """Rejoue ce que dit un client qui a fini : « non » à la proposition, « c'est tout », « oui » par carte, jusqu'à ce que la commande soit enregistrée."""
    for _ in range(8):
        if partie.p.get("enregistree"):
            return
        type_ = C.question(partie.p).get("type")
        if type_ == "proposition":
            await partie.geste("G24")
        elif type_ in ("relecture", "numero_affiche"):
            q = C.question(partie.p)
            await partie._executer("recette", "oui par carte", {"reponse": {"question_id": q["id"], "sens": "accepte"}, "moyen_de_paiement": "carte_bancaire"}, C._inchange)
        else:
            await partie.geste("G20")
    assert partie.p.get("enregistree"), (C.question(partie.p), partie.p.get("etape"))


async def _lignes_de_l_appel(partie: C.Partie) -> list[dict]:
    return [dict(r) for r in await partie.e.monde.c.fetch(
        "SELECT numero::text AS numero, numero_court, statut, total FROM mark.resto_commande WHERE appel_id = $1 ORDER BY cree_le", str(partie.e.ctx.run_id))]


async def test_annulee_puis_une_regina_la_regina_entre_et_la_meme_ligne_part_une_fois(faire_monde, monkeypatch):
    """Client (commande retenue, une margherita) « J'annule. » / modèle « Vous voulez vraiment annuler la commande de … ? » / « Oui. » / « C'est annulé. » / « Finalement, une regina. »
    / avant : la regina est refusée (DC5), « voulez-vous en passer une nouvelle ? » / après : la regina est prise, même numéro de commande, elle part une fois à la fin."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    avant = (await _lignes_de_l_appel(partie))[0]
    o = await _annuler(partie)
    assert o.apres.get("annulee") and not o.apres.get("lignes"), (o.apres.get("etape"), o.apres.get("lignes"))  # annuler = vider le panier
    o = await partie._executer("G1", "finalement, une regina", REGINA_DITE, C._plus(C.REGINA))
    assert dict(C.lignes_de(o.apres)) == {C.REGINA: 1} and C.question(o.apres).get("type") != "nouvelle_commande", (o.apres.get("lignes"), C.question(o.apres), o.retour)
    await _jusqu_a_l_enregistrement(partie)
    ligne = await _lignes_de_l_appel(partie)
    assert [(l["numero"], l["numero_court"], l["statut"]) for l in ligne] == [(avant["numero"], avant["numero_court"], "retenue")], ligne  # la même ligne, rouverte
    assert str(partie.p["enregistree"]["numero"]) == avant["numero"] and partie.p["enregistree"]["numero_court"] == avant["numero_court"], partie.p["enregistree"]
    base = await C.commande_complete(partie.e.monde.c, partie.e.monde.a, avant["numero"])
    assert len(base["lignes"]) == 1 and base["lignes"][0]["quantite"] == 1 and "egina" in base["lignes"][0]["nom"], base["lignes"]
    assert partie.e.source.prise.recues == [], partie.e.source.prise.recues  # rien ne part pendant l'appel
    assert await partie.finir_l_appel() == []
    recues = partie.e.source.prise.recues
    assert [str(r["numero"]) for r in recues] == [avant["numero"]] and partie.e.source.prise.annulees == [], (recues, partie.e.source.prise.annulees)
    assert [l["nom"] for l in recues[0]["lignes"]] == [l["nom"] for l in base["lignes"]], recues[0]["lignes"]


async def test_le_oui_a_l_annulation_et_l_article_dans_la_meme_fiche_l_article_entre(faire_monde, monkeypatch):
    """Client « Oui, et mettez-moi une regina à la place. » (réponse à « vous voulez vraiment annuler ? ») / avant : refus « commande_annulee », la regina perdue / après : annulée,
    puis la regina est prise (l'ordre des cases : vider, puis ajouter)."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    o = await _annuler(partie, REGINA_DITE)
    assert dict(C.lignes_de(o.apres)) == {C.REGINA: 1} and "commande_annulee" not in C._raisons(o.retour), (dict(C.lignes_de(o.apres)), C._raisons(o.retour))


async def test_annulee_recommandee_puis_annulee_encore_la_meme_ligne_reste_annulee(faire_monde, monkeypatch):
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    assert await partie.recette("E16")
    avant = (await _lignes_de_l_appel(partie))[0]
    await _annuler(partie)
    await partie._executer("G1", "finalement, une regina", REGINA_DITE, C._plus(C.REGINA))
    await _jusqu_a_l_enregistrement(partie)
    o = await _annuler(partie)
    assert o.apres.get("annulee"), o.retour
    lignes = await _lignes_de_l_appel(partie)
    assert [(l["numero"], l["statut"]) for l in lignes] == [(avant["numero"], "annulee")], lignes
    assert await partie.finir_l_appel() == [] and partie.e.source.prise.recues == [] and partie.e.source.prise.annulees == []


async def test_annulee_en_cours_puis_une_regina_la_regina_entre_sans_question_de_nouvelle_commande(faire_monde, monkeypatch):
    """Client (commande commencée, pas encore enregistrée) « Annulez tout. » / « Finalement, une regina. » / avant : « voulez-vous en passer une nouvelle ? » / après : la regina est prise."""
    partie = C.Partie(await faire_monde("casa-italia"), monkeypatch)
    await partie._executer("recette", "à emporter", {"mode_de_retrait": "emporter"}, C._inchange)
    await partie._executer("recette", "une margherita normale", {"ajouter": [{"article": "margherita", "quantite": 1, "variante": "Normale"}]}, C._plus(C.MARGHERITA))
    o = await partie._executer("G13", "annulez tout", {"annuler_la_commande": True}, C._vide)
    assert o.apres.get("annulee") and not o.apres.get("lignes"), o.apres
    o = await partie._executer("G1", "finalement, une regina", REGINA_DITE, C._plus(C.REGINA))
    assert dict(C.lignes_de(o.apres)) == {C.REGINA: 1} and C.question(o.apres).get("type") != "nouvelle_commande", (o.apres.get("lignes"), C.question(o.apres), o.retour)
