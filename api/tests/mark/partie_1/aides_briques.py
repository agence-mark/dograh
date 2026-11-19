"""[.mark] Chantier Partie 1, lots 8 à 15 : les aides communes des tests de briques (une carte d'essai, un appel, l'aller-retour en caisse, le rendu de la fiche).

Un test = un essai à la fois : deux ``Essai`` dans le même test se partagent la source de la porte (le dernier monté gagne).
"""

from __future__ import annotations

import json

from api.db.bases_clients import restauration_commande as RC
from api.db.bases_clients import restauration_ecran
from api.services.restauration.prises.hubrise_traduction import commande_vers_hubrise
from api.tests.mark.partie_1 import rendu_de_la_fiche as RF


def fait(r: dict) -> str:
    return json.dumps(r, ensure_ascii=False, default=str)


def statuts(r: dict) -> list[str]:
    return [x.get("statut_du_module") for x in r.get("resultats") or []]


async def brique(essai_de, code: str, **options):
    e = await essai_de(f"briques/{code}", **options)
    await e.tour("à emporter", mode_de_retrait="emporter")
    repondre_aux_propositions(e)
    return e


def repondre_aux_propositions(e) -> None:
    """Une proposition de vente en plus qui attend une réponse (``reponse`` obligatoire quand la question était déjà posée) : refusée avant le tour suivant."""
    tour = e.tour

    async def tour_qui_refuse(parole: str, **cases):
        q = e.p.get("question") if isinstance(e.p.get("question"), dict) else None
        if q and "reponse" not in cases:
            cases["reponse"] = {"question_id": q["id"], "sens": "refuse" if q.get("type") == "proposition" else "autre"}
        return await tour(parole, **cases)

    e.tour = tour_qui_refuse


async def article_en_caisse(e, code_caisse: str, quantite: int = 1, choix: list[dict] | None = None) -> dict:
    """L'aller-retour en caisse d'une brique : la ligne chiffrée depuis la carte (format commun), la commande, puis le corps ``POST /location/orders``."""
    r = await RC.chiffrer_panier(e.monde.c, e.monde.a, "emporter", [{"code_caisse": code_caisse, "quantite": quantite, "choix": choix or []}])
    assert r.statut == "OK", r
    corps = commande_vers_hubrise({"numero": "n-1", "mode": "emporter", "client": {}, "lignes": r.faits["lignes"]})
    article = corps["items"][0]
    total = int(round(float(article["price"].split()[0]) * 100)) + sum(int(round(float(o["price"].split()[0]) * 100)) * o.get("quantity", 1) for o in article.get("options", []))
    assert total == r.faits["lignes"][0]["prix_unitaire"], (article, r.faits["lignes"])  # la caisse retrouve notre prix
    return article


async def preparer(code: str, e, avec: bool) -> None:
    """Ce que la brique pose en surcouche (le texte du jour) : jamais dans la carte importée."""
    if code == "ART3" and avec:
        assert await restauration_ecran.poser_le_produit_du_moment(e.monde.c, e.monde.a, "P-PLAT-DU-JOUR", "gratin de courgettes et riz", "essai")


async def la_brique_change_la_fiche(code: str, essai_de) -> bool:
    from api.services.commande.briques import registre
    from api.tests.mark.banc_a.commun import carte_de

    carte = carte_de(f"briques/{code}")
    avec = await essai_de(f"briques/{code}")
    await preparer(code, avec, True)
    sans = await essai_de(f"briques/{code}-sans", carte=RF.sans_la_brique(code, carte))
    await preparer(code, sans, False)
    return await RF.la_brique_change_la_fiche(code, avec, sans) if registre.BRIQUES[code] else False


