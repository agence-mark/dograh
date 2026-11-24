"""[.mark] Aides publiques des tests de la commande : les gestes d'un appel jusqu'à l'enregistrement (reprises par les tests des lots suivants)."""

from __future__ import annotations


def question_posee(e) -> dict:
    return e.p.get("question") or {}


async def a_emporter(e):
    return await e.tour("à emporter", mode_de_retrait="emporter")


async def premier_article(e, article: str = "margherita", variante: str = "Normale", parole: str | None = None):
    return await e.tour(parole or f"une {article} {variante.lower()}", ajouter=[{"article": article, "quantite": 1, "variante": variante}])


async def refuser_la_proposition(e):
    if question_posee(e).get("type") == "proposition":
        await e.tour("non merci", reponse={"question_id": question_posee(e)["id"], "sens": "refuse"})


async def oui_au_numero_dicte(e):
    """DC10 : le numéro dicté est relu par le code et attend son « oui »."""
    if question_posee(e).get("type") == "numero_dicte":
        await e.tour("oui", reponse={"question_id": question_posee(e)["id"], "sens": "accepte"})


async def jusqu_au_recapitulatif(e):
    for _ in range(3):
        q = question_posee(e)
        if q.get("type") == "relecture":
            return q
        cases = {"c_est_tout": True, **({"reponse": {"question_id": q["id"], "sens": "refuse"}} if q.get("type") == "proposition" else {})}
        await e.tour("non merci, c'est tout", **cases)
    assert question_posee(e).get("type") == "relecture", e.retours[-1]
    return question_posee(e)


async def jusqu_a_l_enregistrement(e, moyen: str = "carte_bancaire", **plus):
    q = await jusqu_au_recapitulatif(e)
    dit = ", ".join([str(v) for k, v in plus.items() if k != "rendu_sur"] + [f"et un billet de {v} euros" for k, v in plus.items() if k == "rendu_sur"])
    await e.tour(f"oui c'est bon, {dit}", reponse={"question_id": q["id"], "sens": "accepte"}, moyen_de_paiement=moyen, **plus)
    for _ in range(4):
        if e.p.get("enregistree"):
            return e.retours[-1]
        r = e.retours[-1]
        manque = [x.get("manque") for x in r.get("resultats") or []]
        if "confirmer_numero_dicte" in manque:  # DC10 : le numéro dicté relu par le code, son « oui » répond à la question
            await e.tour("oui", reponse={"question_id": question_posee(e)["id"], "sens": "accepte"})
        elif "telephone" in manque or "confirmer_numero" in manque:
            await e.tour("zéro six douze trente-quatre cinquante-six soixante-dix-huit", telephone="0612345678")
        elif "prenom" in manque:
            await e.tour("Léa", prenom="Léa")
        elif "consigne_livreur" in manque:
            await e.tour("aucune", consigne_livreur="aucune")
        else:
            break
    assert e.p.get("enregistree"), e.retours[-1]
    return e.retours[-1]
